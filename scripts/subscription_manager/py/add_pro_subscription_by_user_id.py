import argparse
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
import asyncio
from typing import Optional, Tuple
from loguru import logger
from dotenv import load_dotenv

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select, delete, update
# Import func for default timestamps
from sqlalchemy.sql import func

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, project_root)

from virtual_labs.infrastructure.db.models import (  # noqa E402
    PaidSubscription,
    PaymentStatus,
    SubscriptionPayment,
    SubscriptionStatus,
    SubscriptionTier,
    SubscriptionTierEnum,
    SubscriptionType,
    VirtualLab,
    SubscriptionSource,
    Subscription,
    FreeSubscription,
)

load_dotenv(".env.local")

DEFAULT_DATABASE_URL = "postgresql+asyncpg://vlm:vlm@localhost:15432/vlm"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)

async def _get_virtual_lab_id(db: AsyncSession, user_id: uuid.UUID) -> Optional[uuid.UUID]:
    """Finds the active virtual lab ID for a given user."""
    logger.debug(f"Querying virtual lab for User {user_id}")
    stmt = select(VirtualLab.id).where(
        VirtualLab.owner_id == user_id, VirtualLab.deleted == False
    )
    result = await db.execute(stmt)
    lab_id = result.scalar_one_or_none()
    if lab_id:
        logger.info(f"Found active Virtual Lab {lab_id} for User {user_id}.")
    else:
        logger.info(f"No active Virtual Lab found for User {user_id}.")
    return lab_id

async def _get_subscription_tier(db: AsyncSession, tier_enum: SubscriptionTierEnum) -> Optional[SubscriptionTier]:
    """Finds the active subscription tier details."""
    logger.debug(f"Querying active {tier_enum.name} tier")
    stmt = select(SubscriptionTier).where(
        SubscriptionTier.tier == tier_enum, SubscriptionTier.active == True
    )
    result = await db.execute(stmt)
    tier = result.scalar_one_or_none()
    if not tier:
        logger.error(f"Active {tier_enum.name} subscription tier not found.")
        return None

    if tier_enum == SubscriptionTierEnum.PRO and not tier.stripe_yearly_price_id:
        logger.error(f"PRO tier {tier.id} missing stripe_yearly_price_id.")
        return None

    logger.info(f"Found active {tier_enum.name} tier (ID: {tier.id}).")
    return tier

async def _cancel_active_paid_subscription(db: AsyncSession, user_id: uuid.UUID) -> bool:
    """Finds and cancels the currently active paid subscription for the user."""
    logger.debug(f"Checking for active paid subscription to cancel for User {user_id}")
    active_sub_stmt = select(Subscription.id).where(
        Subscription.user_id == user_id,
        Subscription.status == SubscriptionStatus.ACTIVE,
        Subscription.type == "paid",
    )
    result = await db.execute(active_sub_stmt)
    existing_active_sub_id = result.scalar_one_or_none()

    if existing_active_sub_id:
        logger.info(f"Found active paid subscription {existing_active_sub_id}. Setting status to CANCELED.")
        cancel_stmt = update(Subscription).where(
            Subscription.id == existing_active_sub_id
        ).values(
            status=SubscriptionStatus.CANCELED,
            updated_at=func.now()
        )
        await db.execute(cancel_stmt)
        logger.info(f"Subscription {existing_active_sub_id} status updated to CANCELED.")
        return True
    else:
        logger.info(f"No active paid subscription found for User {user_id} to cancel.")
        return False 

async def _delete_all_paid_subscriptions(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Deletes all paid subscriptions and their associated payments for the user."""
    logger.info(f"Mode 'replace_all': Deleting all previous paid subscriptions for User {user_id}.")
    all_paid_subs_stmt = select(Subscription.id).where( 
        Subscription.user_id == user_id,
        Subscription.type == "paid",
    )
    result = await db.execute(all_paid_subs_stmt)
    sub_ids_to_delete = result.scalars().all()

    if sub_ids_to_delete:
        logger.info(f"Found paid subscription IDs to delete: {sub_ids_to_delete}")
        delete_payments_stmt = delete(SubscriptionPayment).where(
            SubscriptionPayment.subscription_id.in_(sub_ids_to_delete)
        )
        payment_del_result = await db.execute(delete_payments_stmt)
        logger.info(f"Deleted {payment_del_result.rowcount} associated payment records.")

        delete_paid_stmt = delete(PaidSubscription).where(
            PaidSubscription.id.in_(sub_ids_to_delete)
        )
        paid_del_result = await db.execute(delete_paid_stmt)
        logger.info(f"Deleted {paid_del_result.rowcount} paid_subscription records.")

        delete_base_stmt = delete(Subscription).where(
            Subscription.id.in_(sub_ids_to_delete)
        )
        base_del_result = await db.execute(delete_base_stmt)
        logger.info(f"Deleted {base_del_result.rowcount} base subscription records.")
    else:
        logger.info("No previous paid subscriptions found to delete.")

async def _handle_existing_paid_subscriptions(db: AsyncSession, user_id: uuid.UUID, mode: str) -> bool:
    """Handles existing paid subscriptions based on the specified mode."""
    logger.debug(f"Handling existing paid subscriptions with mode: {mode}")
    if mode == 'default':
        active_sub_stmt = select(Subscription.id).where(
            Subscription.user_id == user_id,
            Subscription.status == SubscriptionStatus.ACTIVE,
            Subscription.type == "paid",
        )
        result = await db.execute(active_sub_stmt)
        existing_active_sub_id = result.scalar_one_or_none()
        if existing_active_sub_id:
            logger.error(f"An active paid subscription (ID: {existing_active_sub_id}) already exists for User {user_id}. Use --mode cancel_existing or --mode replace_all to override.")
            return False
        return True 

    elif mode == 'cancel_existing':
        await _cancel_active_paid_subscription(db, user_id)
        return True 

    elif mode == 'replace_all':
        await _delete_all_paid_subscriptions(db, user_id)
        return True 

    else:
        logger.error(f"Invalid mode '{mode}' encountered in _handle_existing_paid_subscriptions.")
        return False

def _create_paid_subscription_object(
    user_id: uuid.UUID,
    virtual_lab_id: Optional[uuid.UUID],
    pro_tier: SubscriptionTier,
    now_naive: datetime,
    period_end_naive: datetime
) -> PaidSubscription:
    """Creates a new PaidSubscription object instance (pure function)."""
    logger.debug("Creating PaidSubscription object instance.")
    stripe_sub_id = f"sub_manual_{uuid.uuid4()}"
    stripe_customer_id = f"cus_manual_{user_id}"

    return PaidSubscription(
        user_id=user_id,
        virtual_lab_id=virtual_lab_id,
        tier_id=pro_tier.id,
        subscription_type=SubscriptionType.PRO,
        status=SubscriptionStatus.ACTIVE,
        current_period_start=now_naive,
        current_period_end=period_end_naive,
        stripe_subscription_id=stripe_sub_id,
        stripe_price_id=pro_tier.stripe_yearly_price_id,
        customer_id=stripe_customer_id,
        cancel_at_period_end=False,
        auto_renew=False,
        amount=pro_tier.yearly_amount,
        currency=pro_tier.currency,
        interval="year",
        source=SubscriptionSource.SCRIPT,
    )

def _create_payment_object(
    subscription_id: uuid.UUID,
    customer_id: str, # Stripe customer ID from subscription
    virtual_lab_id: Optional[uuid.UUID],
    amount: int,
    currency: str,
    now_naive: datetime,
    period_end_naive: datetime
) -> SubscriptionPayment:
    """Creates a new SubscriptionPayment object instance (pure function)."""
    logger.debug("Creating SubscriptionPayment object instance.")
    payment_intent_id = f"pi_manual_{uuid.uuid4()}"
    charge_id = f"ch_manual_{uuid.uuid4()}"

    return SubscriptionPayment(
        subscription_id=subscription_id,
        customer_id=customer_id,
        virtual_lab_id=virtual_lab_id,
        stripe_invoice_id=f"in_manual_{uuid.uuid4()}",
        stripe_payment_intent_id=payment_intent_id,
        stripe_charge_id=charge_id,
        card_brand="manual",
        card_last4="0000",
        card_exp_month=12,
        card_exp_year=datetime.now(timezone.utc).year + 3,
        amount_paid=amount,
        currency=currency,
        status=PaymentStatus.SUCCEEDED,
        period_start=now_naive,
        period_end=period_end_naive,
        payment_date=now_naive,
        standalone=False,
    )

async def _find_existing_free_subscription(db: AsyncSession, user_id: uuid.UUID) -> Optional[Subscription]:
    """Finds the latest existing FREE subscription for the user, regardless of status."""
    logger.debug(f"Querying for existing FREE subscription for User {user_id}")
    stmt = select(Subscription).where(
        Subscription.user_id == user_id,
        Subscription.subscription_type == SubscriptionType.FREE,
    ).order_by(Subscription.created_at.desc()).limit(1)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()

async def _pause_subscription(db: AsyncSession, sub_id: uuid.UUID) -> None:
    """Sets the status of a given subscription ID to PAUSED."""
    logger.info(f"Setting status of subscription {sub_id} to PAUSED.")
    stmt = update(Subscription).where(
        Subscription.id == sub_id
    ).values(
        status=SubscriptionStatus.PAUSED,
        updated_at=func.now()
    )
    await db.execute(stmt)
    logger.info(f"Set status of subscription {sub_id} to PAUSED.")

def _create_paused_free_subscription_object(
    user_id: uuid.UUID,
    free_tier: SubscriptionTier,
    now_naive: datetime,
    far_future_naive: datetime
) -> FreeSubscription:
    """Creates a new FreeSubscription object instance in PAUSED state (pure function)."""
    logger.debug("Creating paused FreeSubscription object instance.")
    return FreeSubscription(
        user_id=user_id,
        virtual_lab_id=None,
        tier_id=free_tier.id,
        subscription_type=SubscriptionType.FREE,
        current_period_start=now_naive,
        current_period_end=far_future_naive,
        status=SubscriptionStatus.PAUSED,
        source=SubscriptionSource.SCRIPT,
        usage_count=0,
    )

async def _ensure_free_subscription_paused(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Ensures a FREE subscription exists and is set to PAUSED."""
    logger.info(f"Ensuring FREE subscription is paused for User {user_id}.")
    existing_free_sub = await _find_existing_free_subscription(db, user_id)

    if existing_free_sub:
        if existing_free_sub.status == SubscriptionStatus.ACTIVE:
            await _pause_subscription(db, existing_free_sub.id)
        else:
            logger.info(f"Found existing FREE subscription {existing_free_sub.id} with status {existing_free_sub.status}. No status change needed.")
    else:
        logger.info(f"No FREE subscription found for User {user_id}. Creating a new one in PAUSED state.")
        free_tier = await _get_subscription_tier(db, SubscriptionTierEnum.FREE)
        if not free_tier:
            raise ValueError("Configuration Error: Active FREE subscription tier not found.")

        now_utc = datetime.now(timezone.utc)
        far_future = now_utc + timedelta(days=365 * 100)
        now_naive = now_utc.replace(tzinfo=None)
        far_future_naive = far_future.replace(tzinfo=None)

        new_paused_free_sub = _create_paused_free_subscription_object(
            user_id, free_tier, now_naive, far_future_naive
        )
        db.add(new_paused_free_sub)
        await db.flush()
        logger.info(f"Created new PAUSED FREE subscription (ID: {new_paused_free_sub.id}) for User {user_id}.")


async def run_subscription_logic(db: AsyncSession, user_id: uuid.UUID, mode: str) -> Optional[Tuple[uuid.UUID, uuid.UUID]]:
    """Orchestrates the process of adding a PRO subscription."""
    logger.info(f"Running subscription logic for User {user_id} with mode {mode}")

    # 1. get virtual vab
    virtual_lab_id = await _get_virtual_lab_id(db, user_id)

    # 2. get pro tier details
    pro_tier = await _get_subscription_tier(db, SubscriptionTierEnum.PRO)
    if not pro_tier:
        return None

    # 3. handle existing paid subscriptions
    can_proceed = await _handle_existing_paid_subscriptions(db, user_id, mode)
    if not can_proceed:
        return None 

    # 4. create timestamps
    now_aware = datetime.now(timezone.utc)
    now_naive = now_aware.replace(tzinfo=None)
    period_end_naive = (now_aware + timedelta(days=365)).replace(tzinfo=None)

    # 5. create subscription
    new_subscription = _create_paid_subscription_object(
        user_id, virtual_lab_id, pro_tier, now_naive, period_end_naive,
    )
    db.add(new_subscription)
    await db.flush()
    sub_id = new_subscription.id
    logger.info(f"Created new PaidSubscription record with ID: {sub_id}")

    # 6. Create Payment Object
    new_payment = _create_payment_object(
        subscription_id=sub_id,
        customer_id=new_subscription.customer_id,
        virtual_lab_id=virtual_lab_id,
        amount=new_subscription.amount,
        currency=new_subscription.currency,
        now_naive=now_naive,
        period_end_naive=period_end_naive
    )
    db.add(new_payment)
    await db.flush()
    payment_id = new_payment.id
    logger.info(f"Created SubscriptionPayment record (ID: {payment_id}) for subscription {sub_id}")

    # 7. make sure free subscription is PAUSED
    await _ensure_free_subscription_paused(db, user_id)

    # 8. return ids of created records
    return sub_id, payment_id


async def main_async_runner(user_id: uuid.UUID, mode: str) -> None:
    """Sets up DB connection, runs logic within a transaction."""
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with async_session_factory() as session:
        try:
            result_ids = await run_subscription_logic(session, user_id, mode)
            if result_ids:
                await session.commit()
                sub_id, payment_id = result_ids
                logger.info(f"Successfully committed changes for User {user_id}.")
                logger.info(f"Final PRO Subscription ID: {sub_id}, Payment ID: {payment_id}")
            else:
                logger.warning(f"Subscription logic did not complete successfully for User {user_id}. Rolling back.")
                await session.rollback()
        except Exception as e:
            logger.exception(f"A critical error occurred during operation for user {user_id} with mode '{mode}': {e}")
            await session.rollback()
            logger.info("Transaction rolled back due to error.")
            sys.exit(1)


def run() -> None:
    """Parses arguments, sets up logging, and runs the main async runner."""
    parser = argparse.ArgumentParser(
        description="Manually add a PRO subscription with options for handling existing subscriptions."
    )
    parser.add_argument("user_id", type=uuid.UUID, help="The UUID of the User.")
    parser.add_argument(
        "--mode",
        type=str,
        choices=["default", "cancel_existing", "replace_all"],
        default="default",
        help=(
            "Specify how to handle existing paid subscriptions: "
            "'default' (fail if active exists), "
            "'cancel_existing' (cancel active paid sub), "
            "'replace_all' (delete all paid subs)."
        )
    )
    args = parser.parse_args()

    logger.info("⚙️  Initiating PRO subscription creation for user: ")
    logger.info(f"{args.user_id} with mode: {args.mode}")

    asyncio.run(main_async_runner(user_id=args.user_id, mode=args.mode))

    logger.info("🎉 Subscription creation process finished.")