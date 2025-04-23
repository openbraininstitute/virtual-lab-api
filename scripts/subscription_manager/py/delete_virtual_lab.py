import argparse
import asyncio
import os
import sys
from datetime import datetime
from http import HTTPStatus
from typing import Optional
from uuid import UUID

from dotenv import load_dotenv
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (AsyncSession, async_sessionmaker,
                                    create_async_engine)

# Add project root to sys.path for relative imports
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, project_root)

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode # noqa E402
from virtual_labs.core.exceptions.identity_error import IdentityError # noqa E402
from virtual_labs.core.exceptions.nexus_error import NexusError # noqa E402
from virtual_labs.external.nexus.delete_organization import delete_nexus_organization # noqa E402
from virtual_labs.infrastructure.db import models # noqa E402
# Assuming kc models might be needed for group deletion logic if not handled by repo
# from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.repositories.group_repo import GroupMutationRepository # noqa E402
from virtual_labs.repositories.user_repo import UserMutationRepository # noqa E402
# Assuming accounting use cases might be needed if not handled elsewhere
# from virtual_labs.usecases import accounting as accounting_cases

# Load environment variables from .env files
load_dotenv(".env.local")
load_dotenv() # Load default .env file as well

DEFAULT_DATABASE_URL = "postgresql+asyncpg://vlm:vlm@localhost:15432/vlm"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)

async def delete_virtual_lab_data(
    db: AsyncSession, virtual_lab_id: Optional[UUID], user_id: UUID
) -> bool:
    """
    Prepare deletion statements for virtual lab data (if ID provided) and user-specific data.
    Does NOT commit the transaction.

    Args:
        db: Database session
        virtual_lab_id: UUID of the virtual lab to potentially delete, or None.
        user_id: UUID of the user whose data should be cleaned up

    Returns:
        bool: True if deletion preparation was successful, False on logical errors (like ownership mismatch).
              Raises SQLAlchemyError on database execution issues.
    """
    lab_deleted = False
    logger.info(f"Preparing database deletions for user {user_id} (VL ID: {virtual_lab_id or 'N/A'}).")

    try:
        # 1. Handle Virtual Lab and related data deletion (if virtual_lab_id is provided)
        if virtual_lab_id:
            virtual_lab = await db.get(models.VirtualLab, virtual_lab_id)
            if not virtual_lab:
                logger.error(f"Inconsistency: virtual_lab_id {virtual_lab_id} provided but not found in DB. Aborting deletion prep.")
                return False # Indicate logical failure

            # Verify ownership
            if virtual_lab.owner_id != user_id:
                logger.error(f"Ownership Check Failed: User {user_id} is not the owner of virtual lab {virtual_lab_id} (Owner: {virtual_lab.owner_id}). Aborting deletion prep.")
                return False # Indicate logical failure

            logger.info(f"Found virtual lab {virtual_lab_id} owned by user {user_id}. Preparing lab-specific deletions.")

            # Delete Projects and their related data (Stars, Invites, Bookmarks, Notebooks)
            project_stmt = select(models.Project.id).where(models.Project.virtual_lab_id == virtual_lab_id)
            project_ids = (await db.execute(project_stmt)).scalars().all()

            if project_ids:
                logger.info(f"Preparing deletion for {len(project_ids)} projects and related data in VL {virtual_lab_id}.")
                project_id_list = list(project_ids) # Convert to list for 'in_'

                # Delete related items first using bulk deletes where possible
                await db.execute(delete(models.ProjectStar).where(models.ProjectStar.project_id.in_(project_id_list)))
                await db.execute(delete(models.ProjectInvite).where(models.ProjectInvite.project_id.in_(project_id_list)))
                await db.execute(delete(models.Bookmark).where(models.Bookmark.project_id.in_(project_id_list)))
                # Add Notebook deletion if model exists
                # await db.execute(delete(models.Notebook).where(models.Notebook.project_id.in_(project_id_list)))

                # Delete Projects themselves
                await db.execute(delete(models.Project).where(models.Project.id.in_(project_id_list)))
                logger.info(f"Prepared deletion for projects: {project_id_list}")

            # Delete Virtual Lab Invites
            await db.execute(delete(models.VirtualLabInvite).where(models.VirtualLabInvite.virtual_lab_id == virtual_lab_id))
            logger.info(f"Prepared deletion for invites associated with VL {virtual_lab_id}.")

            # Delete Payment Methods associated with the Virtual Lab
            await db.execute(delete(models.PaymentMethod).where(models.PaymentMethod.virtual_lab_id == virtual_lab_id))
            logger.info(f"Prepared deletion for payment methods associated with VL {virtual_lab_id}.")

            # Delete the Virtual Lab itself
            logger.info(f"Preparing deletion for virtual lab {virtual_lab_id} itself.")
            await db.delete(virtual_lab) # Mark for deletion
            lab_deleted = True

        else:
            logger.info(f"No virtual_lab_id provided. Skipping lab-specific deletion, proceeding with user data cleanup for user {user_id}.")

        # 2. Handle User-specific data deletion (Subscriptions, Payments, StripeUser) - ALWAYS runs
        logger.info(f"Preparing deletion of subscriptions and related data for user {user_id}.")

        # Find subscription IDs for the user
        sub_stmt = select(models.Subscription.id).where(models.Subscription.user_id == user_id)
        subscription_ids = (await db.execute(sub_stmt)).scalars().all()

        if subscription_ids:
            sub_id_list = list(subscription_ids)
            logger.info(f"Found {len(sub_id_list)} subscriptions for user {user_id}.")

            # Delete associated Subscription Payments first
            await db.execute(delete(models.SubscriptionPayment).where(models.SubscriptionPayment.subscription_id.in_(sub_id_list)))
            logger.info(f"Prepared deletion for payments associated with subscriptions: {sub_id_list}")

            # Delete Subscriptions (handles Free/Paid via inheritance/cascades if set up)
            await db.execute(delete(models.Subscription).where(models.Subscription.id.in_(sub_id_list)))
            logger.info(f"Prepared deletion for subscriptions: {sub_id_list}")
        else:
            logger.info(f"No subscriptions found for user {user_id}.")

        # Delete StripeUser record for the user
        await db.execute(delete(models.StripeUser).where(models.StripeUser.user_id == user_id))
        logger.info(f"Prepared deletion for StripeUser record for user {user_id}.")

        # Log final state before returning
        if lab_deleted:
            logger.info(f"Database operations successfully prepared for virtual lab {virtual_lab_id} and user {user_id}.")
        else:
            logger.info(f"Database operations successfully prepared for user {user_id} (no associated virtual lab processed).")
        return True # Indicate successful preparation

    except SQLAlchemyError as e:
        logger.error(f"Database error during deletion preparation for user {user_id} (VL: {virtual_lab_id or 'N/A'}): {e}")
        raise # Re-raise to be caught by the transaction handler

    except Exception as e:
        # Catch any other unexpected error during preparation
        logger.error(f"Unexpected error during deletion preparation for user {user_id} (VL: {virtual_lab_id or 'N/A'}): {e}")
        raise # Re-raise to be caught by the transaction handler

# --- External Service Deletion Logic ---

async def delete_keycloak_groups(admin_group_id: str, member_group_id: str) -> bool:
    """
    Delete the Keycloak groups associated with a virtual lab asynchronously.

    Args:
        admin_group_id: ID of the admin group
        member_group_id: ID of the member group

    Returns:
        bool: True if deletion was successful or group not found, False on error.
    """
    group_repo = GroupMutationRepository()
    success = True

    for group_id, group_name in [(admin_group_id, "admin"), (member_group_id, "member")]:
        try:
            logger.info(f"Attempting to delete Keycloak {group_name} group {group_id}")
            await group_repo.delete_group(group_id=group_id)
            logger.info(f"Successfully deleted Keycloak {group_name} group {group_id}")
        except IdentityError as error:
            # Consider "Not Found" as success in a deletion script context
            if "not found" in str(error).lower():
                 logger.warning(f"Keycloak {group_name} group {group_id} not found. Assuming already deleted.")
            else:
                logger.error(f"IdentityError deleting Keycloak {group_name} group {group_id}: {error}")
                success = False # Mark as failed
        except Exception as error:
            logger.error(f"Unknown error deleting Keycloak {group_name} group {group_id}: {error}")
            success = False # Mark as failed

    return success


async def delete_nexus_organization_wrapper(nexus_organization_id: str) -> bool:
    """
    Wrapper to delete the Nexus organization associated with a virtual lab.

    Args:
        nexus_organization_id: ID of the Nexus organization

    Returns:
        bool: True if deletion was successful or org not found, False on error.
    """
    try:
        logger.info(f"Attempting to delete Nexus organization {nexus_organization_id}")
        # Assuming delete_nexus_organization is async
        await delete_nexus_organization(nexus_org_id=nexus_organization_id)
        logger.info(f"Successfully deleted Nexus organization {nexus_organization_id}")
        return True
    except NexusError as error:
         # Consider "Not Found" as success in a deletion script context
        if "not found" in str(error).lower() or "404" in str(error): # Adjust based on actual error message/code
            logger.warning(f"Nexus organization {nexus_organization_id} not found. Assuming already deleted.")
            return True
        else:
            logger.error(f"NexusError deleting Nexus organization {nexus_organization_id}: {error}")
            return False # Indicate failure
    except Exception as error:
        logger.error(f"Unknown error deleting Nexus organization {nexus_organization_id}: {error}")
        return False # Indicate failure

# --- Main Orchestration Logic ---

async def delete_virtual_lab_orchestrator(
    db: AsyncSession, virtual_lab_id: Optional[UUID], user_id: UUID
) -> bool:
    """
    Orchestrates the deletion process: DB prep, external services (if applicable).

    Args:
        db: Database session
        virtual_lab_id: ID of the virtual lab to delete (if found), otherwise None.
        user_id: ID of the user whose data is being processed.

    Returns:
        bool: True if database preparation was successful (commit should proceed), False otherwise (rollback).
    """
    admin_group_id = None
    member_group_id = None
    nexus_organization_id = None
    lab_found_and_owned = False

    # 1. Fetch VL details if ID is provided (needed for external service IDs)
    if virtual_lab_id:
        # We already confirmed existence and ownership in main_async_runner before calling this,
        # but fetching again within the transaction is safer and gets the related IDs.
        virtual_lab = await db.get(models.VirtualLab, virtual_lab_id)
        if virtual_lab and virtual_lab.owner_id == user_id:
            lab_found_and_owned = True
            admin_group_id = virtual_lab.admin_group_id
            member_group_id = virtual_lab.member_group_id
            nexus_organization_id = virtual_lab.nexus_organization_id
            logger.info(f"Confirmed VL {virtual_lab_id} owned by {user_id}. IDs captured for external cleanup.")
        elif not virtual_lab:
             logger.error(f"Orchestrator Inconsistency: VL {virtual_lab_id} not found in DB within transaction. Aborting.")
             return False
        else: # virtual_lab.owner_id != user_id
             logger.error(f"Orchestrator Ownership Check Failed: VL {virtual_lab_id} owner is {virtual_lab.owner_id}, expected {user_id}. Aborting.")
             return False

    # 2. Prepare Database Deletions (Crucial Step)
    # This function handles both lab-specific and user-specific data based on virtual_lab_id
    db_prep_success = await delete_virtual_lab_data(db, virtual_lab_id, user_id)
    if not db_prep_success:
        logger.error("Database deletion preparation failed. Aborting commit.")
        return False # Signal failure to main runner for rollback

    # If DB prep succeeded, proceed with external deletions (best effort)

    # 3. Delete Keycloak Groups (only if lab was found)
    kc_success = True # Assume success if not applicable
    if lab_found_and_owned and admin_group_id and member_group_id:
        kc_success = await delete_keycloak_groups(admin_group_id, member_group_id)
        if not kc_success:
            logger.warning(f"Keycloak group deletion failed or partially failed for lab {virtual_lab_id}. Database changes will still be committed.")
            # Non-fatal for DB commit

    # 4. Delete Nexus Organization (only if lab was found)
    nexus_success = True # Assume success if not applicable
    if lab_found_and_owned and nexus_organization_id:
        nexus_success = await delete_nexus_organization_wrapper(nexus_organization_id)
        if not nexus_success:
            logger.warning(f"Nexus organization deletion failed for lab {virtual_lab_id}. Database changes will still be committed.")
            # Non-fatal for DB commit

    # 5. Delete Accounting Resources (Placeholder - Implement if needed)
    # accounting_success = True
    # if lab_found_and_owned:
    #     # Add accounting deletion logic here
    #     pass

    # The decision to commit only depends on the database preparation step
    logger.info("Database preparation successful. External cleanup attempted.")
    return True # Indicate success to main runner for commit

# --- Main Execution Flow ---

async def main_async_runner(user_id: UUID) -> None:
    """
    Sets up DB connection, finds the user's VL (if any), and runs logic within a transaction.
    """
    logger.info(f"Connecting to database: {DATABASE_URL.split('@')[-1]}") # Basic obfuscation
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session_factory = async_sessionmaker(engine, expire_on_commit=False)

    virtual_lab_id: Optional[UUID] = None
    virtual_lab_found = False

    async with async_session_factory() as session:
        try:
            # Attempt to find the Virtual Lab owned by the user
            logger.info(f"Searching for Virtual Lab owned by user {user_id}...")
            stmt = select(models.VirtualLab).where(models.VirtualLab.owner_id == user_id)
            result = await session.execute(stmt)
            virtual_lab = result.scalar_one_or_none()

            if virtual_lab:
                virtual_lab_id = virtual_lab.id
                virtual_lab_found = True
                logger.info(f"Found Virtual Lab {virtual_lab_id} owned by user {user_id}.")
            else:
                logger.info(f"No Virtual Lab found owned by user {user_id}. Proceeding with user data cleanup only.")

            # Start the transaction block implicitly with 'async with session.begin():'
            # However, we need finer control to call external services before commit.
            # So, we manage the transaction manually with session.commit() / session.rollback()

            logger.info("Starting deletion orchestration...")
            # Pass potentially None virtual_lab_id to the orchestrator
            orchestration_success = await delete_virtual_lab_orchestrator(session, virtual_lab_id, user_id)

            if orchestration_success:
                await session.commit()
                log_msg = f"Successfully committed deletions for User {user_id}"
                if virtual_lab_found:
                    log_msg += f" (including VL {virtual_lab_id})."
                else:
                    log_msg += " (no associated VL found)."
                logger.info(f"✅ {log_msg}")
            else:
                logger.warning(f"Orchestration indicated failure for User {user_id} (VL: {virtual_lab_id or 'N/A'}). Rolling back database changes.")
                await session.rollback()
                sys.exit(1) # Exit with error code if process failed pre-commit

        except SQLAlchemyError as e:
             logger.exception(f"A database error occurred during the deletion process for User {user_id} (VL: {virtual_lab_id or 'N/A'}): {e}")
             await session.rollback()
             logger.info("Transaction rolled back due to database error.")
             sys.exit(1)
        except Exception as e:
            logger.exception(f"An unexpected critical error occurred during deletion for User {user_id} (VL: {virtual_lab_id or 'N/A'}): {e}")
            await session.rollback()
            logger.info("Transaction rolled back due to unexpected error.")
            sys.exit(1) # Exit with error code on exception
        finally:
             # Ensure engine is disposed (important for scripts)
             await engine.dispose()


def run() -> None:
    """Parses arguments, sets up logging, and runs the main async runner."""
    parser = argparse.ArgumentParser(
        description="Physically delete a User's subscriptions/data and their owned Virtual Lab (if any) with related data."
    )
    parser.add_argument("user_id", type=UUID, help="The UUID of the User whose data and potential Virtual Lab should be deleted.")

    args = parser.parse_args()

    # Configure Loguru
    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        # "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>" # Optional: more detail
         "<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>" # Simpler format
    )
    logger.remove() # Remove default handler
    logger.add(sys.stderr, format=log_format, level="INFO") # Add console logger
    # Optional: Add file logger
    # logger.add(f"delete_user_{args.user_id}_{{time:YYYYMMDD_HHmmss}}.log", rotation="1 day", level="DEBUG")

    logger.info(f"⚙️  Initiating deletion process for User ID: {args.user_id}")

    try:
        # Call main_async_runner with only user_id
        asyncio.run(main_async_runner(user_id=args.user_id))
        # Success message is now logged within main_async_runner after commit
    except SystemExit as e:
         if e.code == 1:
              logger.error("❌ Deletion process failed. Check logs above for details.")
         # else: # Normal exit (code 0) - already logged success
              # logger.info("ℹ️ Deletion process finished.")
    except KeyboardInterrupt:
        logger.warning("\nScript interrupted by user. Transaction likely rolled back.")
        sys.exit(130) # Standard exit code for Ctrl+C
    except Exception as e:
         # Catch-all for unexpected errors outside the main runner's try/except
         logger.exception(f"An unexpected error occurred in the run function: {e}")
         sys.exit(1)


if __name__ == "__main__":
    run()
