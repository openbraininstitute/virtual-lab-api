#!/usr/bin/env python
import argparse
import asyncio
import os
import sys
import uuid
import json
from datetime import datetime
from typing import Optional, List, Dict, Any

from dotenv import load_dotenv
from loguru import logger
from sqlalchemy import or_, select, delete, and_
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.generic_exceptions import EntityNotFound

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import stripe
from virtual_labs.infrastructure.db.config import session_pool, settings, initialize_db, close_db
from virtual_labs.infrastructure.db.models import (
    VirtualLab,
    Project,
    VirtualLabInvite,
    ProjectInvite,
    ProjectStar,
    Bookmark,
    Notebook,
    SubscriptionPayment,
    Subscription,
    PaidSubscription,
    FreeSubscription,
    StripeUser,
)
from virtual_labs.repositories.labs import get_virtual_lab_async, get_virtual_lab_soft
from virtual_labs.repositories.group_repo import GroupMutationRepository


def lab_to_dict(lab: VirtualLab) -> Dict[str, Any]:
    """Convert VirtualLab object to a dictionary for JSON serialization."""

    lab_id = str(lab.id) if lab.id else None
    owner_id = str(lab.owner_id) if lab.owner_id else None

    
    return {
        "id": lab_id,
        "name": lab.name,
        "description": lab.description,
        "owner_id": owner_id,
        "reference_email": lab.reference_email,
        "admin_group_id": lab.admin_group_id,
        "member_group_id": lab.member_group_id,
        "nexus_organization_id": lab.nexus_organization_id,
        "entity": lab.entity,
        "created_at": lab.created_at.isoformat() if lab.created_at else None,
        "updated_at": lab.updated_at.isoformat() if lab.updated_at else None,
    }


async def cancel_stripe_subscription(stripe_subscription_id: str) -> None:
    """
    Cancel a Stripe subscription immediately
    
    Args:
        stripe_subscription_id: The ID of the Stripe subscription to cancel
    """
    try:
        subscription = stripe.Subscription.delete(stripe_subscription_id, params={ })
        logger.info(f"Canceled Stripe subscription {stripe_subscription_id}")
        return subscription
    except Exception as e:
        logger.error(f"Error canceling Stripe subscription {stripe_subscription_id}: {e}")
        return None


async def delete_keycloak_groups(lab: VirtualLab, projects: List[Project]) -> None:
    """
    Delete Keycloak groups for the virtual lab and all its projects
    
    Args:
        lab: Virtual lab object
        projects: List of project objects
    """
    group_repo = GroupMutationRepository()
    
    for project in projects:
        try:
            admin_group_id = project.admin_group_id
            member_group_id = project.member_group_id
            
            if admin_group_id:
                group_repo.delete_group(group_id=admin_group_id)
                print(f"    ✓ Deleted Keycloak admin group {admin_group_id} for project {project.id}")
            
            if member_group_id:
                group_repo.delete_group(group_id=member_group_id)
                print(f"    ✓ Deleted Keycloak member group {member_group_id} for project {project.id}")
                
        except Exception as e:
            print(f"    ❌ Error deleting Keycloak groups for project {project.id}: {e}")
    
    try:
        admin_group_id = lab.admin_group_id
        if admin_group_id:
            group_repo.delete_group(group_id=admin_group_id)
            print(f"✅ Deleted Keycloak admin group {admin_group_id}")
        
        member_group_id = lab.member_group_id
        if member_group_id:
            group_repo.delete_group(group_id=member_group_id)
            print(f"✅ Deleted Keycloak member group  {member_group_id}")
            
    except Exception as e:
        print(f"❌ Error deleting Keycloak groups for lab {lab.id}: {e}")


async def delete_virtual_lab_data(db: AsyncSession, lab_id: uuid.UUID) -> None:
    """
    Delete a virtual lab and all related data permanently

    Args:
        db: Database session
        lab_id: UUID of the virtual lab to delete
    """
    try:
        lab = await get_virtual_lab_async(db, lab_id)
        print(f"✅ Found virtual lab: {lab.name} (ID: {lab.id})")
        
        projects_stmt = select(Project).where(Project.virtual_lab_id == lab_id)
        projects_result = await db.execute(projects_stmt)
        projects = projects_result.scalars().all()
        project_ids = [project.id for project in projects]
        
        print(f"✅ Found {len(projects)} projects to delete")
        
        print(f"✅ Deleting Keycloak groups...")
        await delete_keycloak_groups(lab, projects)
        
        for project_id in project_ids:
            await db.execute(
                delete(ProjectInvite).where(ProjectInvite.project_id == project_id)
            )
            print(f"    ✓ Deleted project invites for project {project_id}")
            
            await db.execute(
                delete(ProjectStar).where(ProjectStar.project_id == project_id)
            )
            print(f"    ✓ Deleted project stars for project {project_id}")
            
            await db.execute(
                delete(Bookmark).where(Bookmark.project_id == project_id)
            )
            print(f"    ✓ Deleted bookmarks for project {project_id}")
            
            await db.execute(
                delete(Notebook).where(Notebook.project_id == project_id)
            )
            print(f"    ✓ Deleted notebooks for project {project_id}")
            
            await db.execute(
                delete(Project).where(Project.id == project_id)
            )
            print(f"    ✓ Deleted project {project_id}")
        
        owner_id = uuid.UUID(str(lab.owner_id))  # Convert PostgreSQL UUID to Python UUID
        subs_stmt = select(Subscription).where(Subscription.user_id == owner_id)
        subs_result = await db.execute(subs_stmt)
        subscriptions = subs_result.scalars().all()
        
        if subscriptions:
            print(f"✅ Found {len(subscriptions)} subscriptions for lab {lab_id}")
            subscription_ids = [sub.id for sub in subscriptions]
            
            paid_subs_stmt = select(PaidSubscription).where(PaidSubscription.user_id == owner_id)
            paid_subs_result = await db.execute(paid_subs_stmt)
            paid_subscriptions = paid_subs_result.scalars().all()
            
            if paid_subscriptions:
                print(f"✅ Found {len(paid_subscriptions)} paid subscriptions to cancel in Stripe")
                
                for paid_sub in paid_subscriptions:
                    try:
                        stripe_subscription_id = paid_sub.stripe_subscription_id
                        await cancel_stripe_subscription(stripe_subscription_id)
                        print(f"✅ Canceled Stripe subscription {stripe_subscription_id}")
                    except Exception as e:
                        print(f"❌ Error canceling Stripe subscription {paid_sub.stripe_subscription_id}: {e}")
            
            for sub_id in subscription_ids:
                await db.execute(
                    delete(SubscriptionPayment).where(SubscriptionPayment.subscription_id == sub_id)
                )
            print(f"✅ Deleted subscription payments for lab {lab_id}")
            
            await db.execute(
                delete(SubscriptionPayment).where(SubscriptionPayment.virtual_lab_id == lab_id)
            )
            print(f"✅ Deleted standalone subscription payments for lab {lab_id}")
            
            free_subs_stmt = select(FreeSubscription).where(or_(
                FreeSubscription.virtual_lab_id == lab_id,
                FreeSubscription.user_id == owner_id,
            ))
            free_subs_result = await db.execute(free_subs_stmt)
            free_subscriptions = free_subs_result.scalars().all()
            
            for free_sub in free_subscriptions:
                await db.execute(
                    delete(FreeSubscription).where(FreeSubscription.id == free_sub.id)
                )
            if free_subscriptions:
                print(f"✅ Deleted {len(free_subscriptions)} free subscriptions for lab {lab_id}")
            
            for paid_sub in paid_subscriptions:
                await db.execute(
                    delete(PaidSubscription).where(PaidSubscription.id == paid_sub.id)
                )
            if paid_subscriptions:
                print(f"✅ Deleted {len(paid_subscriptions)} paid subscriptions for lab {lab_id}")
            

            for sub_id in subscription_ids:
                await db.execute(
                    delete(Subscription).where(Subscription.id == sub_id)
                )
            print(f"✅ Deleted {len(subscription_ids)} parent subscriptions for lab {lab_id}")
        
        await db.execute(
            delete(VirtualLabInvite).where(VirtualLabInvite.virtual_lab_id == lab_id)
        )
        print(f"✅ Deleted virtual lab invites for lab {lab_id}")
        

        await db.execute(
            delete(StripeUser).where(StripeUser.user_id == owner_id)
        )
        print(f"✅ Deleted Stripe user for owner {owner_id}")
        

        await db.execute(
            delete(VirtualLab).where(VirtualLab.id == lab_id)
        )
        print(f"✅ Deleted virtual lab {lab_id}")
        
        await db.commit()
        print(f"✅ Successfully deleted virtual lab {lab_id} and all related data")
    
    except Exception as e:
        await db.rollback()
        print(f"❌ Error deleting virtual lab: {e}")
        raise


async def main():
    load_dotenv()
    
    parser = argparse.ArgumentParser(description="Delete a virtual lab and all related data")
    parser.add_argument("--lab-id", type=str, help="UUID of the virtual lab to delete")
    
    args = parser.parse_args()
    lab_id_str = args.lab_id
    
    db_uri = str(settings.DATABASE_URI)
    print(f"\n📊 Database URL: {db_uri}")
    
    stripe.api_key = str(settings.STRIPE_SECRET_KEY)
    if not stripe.api_key:
        print("⚠️  Warning: STRIPE_SECRET_KEY not set. Stripe operations will not work.")
    
    if not lab_id_str:
        lab_id_str = input("\n🔑 Please enter the Virtual Lab ID to delete: ")
    
    try:
        lab_id = uuid.UUID(lab_id_str.strip())
    except ValueError:
        print(f"❌ Invalid UUID format: {lab_id_str}")
        return
    
    print(f"\n🔍 Looking up Virtual Lab with ID: {lab_id}")
    
    try:
        await initialize_db()
        
        async with session_pool.session() as db:
            try:
                lab = await get_virtual_lab_soft(db, lab_id)
                if lab is None:
                    raise EntityNotFound("Virtual lab not found")

                lab_dict = lab_to_dict(lab)
                print("\n📋 Virtual Lab Details:")
                print(json.dumps(lab_dict, indent=2))
                
                confirm = input("\n⚠️  Are you sure you want to delete this Virtual Lab? All data will be permanently deleted. [y/N]: ")
                if confirm.lower() != "y":
                    print("🛑 Deletion cancelled.")
                    return
                
                print("\n🚀 Starting deletion process...")
                await delete_virtual_lab_data(db, lab_id)
                
            except Exception as e:
                print(f"❌ Error: {str(e)}")


    finally:
        await close_db()


def run():
    asyncio.run(main())


if __name__ == "__main__":
    asyncio.run(main()) 