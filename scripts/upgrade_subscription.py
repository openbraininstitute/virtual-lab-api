import argparse
import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Self, Tuple

import asyncssh
from asyncssh import SSHClientConnection, SSHListener
from dotenv import load_dotenv
from loguru import logger
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, project_root)

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.infrastructure.db.models import (
    FreeSubscription,
    PaidSubscription,
    PaymentStatus,
    Subscription,
    SubscriptionPayment,
    SubscriptionSource,
    SubscriptionStatus,
    SubscriptionTier,
    SubscriptionTierEnum,
    SubscriptionType,
    VirtualLab,
)

load_dotenv(".env.local")

logger.configure(handlers=[{"sink": sys.stdout, "format": "[{line}] {message}"}])

class DatabaseConnection:
    _engine: Optional[AsyncEngine] = None
    _session_maker: Optional[async_sessionmaker[AsyncSession]] = None
    _ssh_tunnel: Optional[SSHListener] = None
    _ssh_conn: Optional[SSHClientConnection] = None

    def __init__(self) -> None:
        self._engine = None
        self._session_maker = None
        self._ssh_conn = None
        self._ssh_tunnel = None

    async def initialize(self, use_ssh_tunnel: bool = False) -> Self:
        """init database connection, SSH tunnel (optional)"""

        postgres_user = os.getenv("POSTGRES_USER")
        postgres_password = os.getenv("POSTGRES_PASSWORD")
        postgres_host = os.getenv("POSTGRES_HOST")
        postgres_port = os.getenv("POSTGRES_PORT")
        postgres_db = os.getenv("POSTGRES_DB")
        db_uri = f"postgresql+asyncpg://{postgres_user}:{postgres_password}@{postgres_host}:{postgres_port}/{postgres_db}"

        if use_ssh_tunnel:
            ssh_host = os.getenv("SSH_HOST")
            ssh_port = int(os.getenv("SSH_PORT", "22"))
            ssh_username = os.getenv("SSH_USERNAME")
            ssh_private_key_path = os.getenv("SSH_PRIVATE_KEY_PATH")
            
            logger.info(f"Establishing SSH tunnel to {ssh_host}:{ssh_port}")
            self._ssh_conn = await asyncssh.connect(
                host=ssh_host,
                port=ssh_port,
                username=ssh_username,
                client_keys=[ssh_private_key_path],
                known_hosts=None,
            )
            self._ssh_tunnel = await self._ssh_conn.forward_local_port(
                "", 0, postgres_host, int(postgres_port)
            )
            local_port = self._ssh_tunnel.get_port()
            db_uri = f"postgresql+asyncpg://{postgres_user}:{postgres_password}@localhost:{local_port}/{postgres_db}"
            logger.info(f"SSH tunnel established on local port {local_port}")


        debug_echo = os.getenv("DEBUG_DATABASE_ECHO", "False").lower() == "true"
        self._engine = create_async_engine(db_uri, echo=debug_echo)
        self._session_maker = async_sessionmaker(
            autoflush=False, autocommit=False, bind=self._engine
        )
        logger.info(
            f"✅ database connected {' via SSH tunnel' if use_ssh_tunnel else ''}"
        )
        return self

    async def close(self) -> None:
        """close database connection and SSH tunnel if open."""
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
            self._session_maker = None

        if self._ssh_tunnel is not None:
            self._ssh_tunnel.close()
            self._ssh_tunnel = None

        if self._ssh_conn is not None:
            self._ssh_conn.close()
            await self._ssh_conn.wait_closed()
            self._ssh_conn = None
        
        logger.info("\n")
        logger.info("✅ database connection closed")

    def session(self) -> async_sessionmaker[AsyncSession]:
        """gett database session maker."""
        if self._session_maker is None:
            raise VliError(
                "Database not initialized. Call initialize() first.",
                error_code=VliErrorCode.DATABASE_URI_NOT_SET,
            )
        return self._session_maker


class SubscriptionUpgrade:
    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    async def get_virtual_lab_id(self, user_id: uuid.UUID) -> Optional[uuid.UUID]:
        """find the active virtual lab ID for a given user."""
        logger.debug(f"👀 querying virtual lab for User {user_id}")
        stmt = select(VirtualLab.id).where(
            VirtualLab.owner_id == user_id, VirtualLab.deleted == False
        )
        result = await self.db.execute(stmt)
        lab_id = result.scalar_one_or_none()
        logger.info(
            f"{'found' if lab_id else 'no'} active virtual lab {lab_id if lab_id else ''}"
        )
        return lab_id

    async def get_subscription_tier(self, tier_enum: SubscriptionTierEnum) -> SubscriptionTier:
        """find the active subscription tier details."""
        logger.debug(f"querying active {tier_enum.name} tier")
        stmt = select(SubscriptionTier).where(
            SubscriptionTier.tier == tier_enum, SubscriptionTier.active == True
        )
        result = await self.db.execute(stmt)
        tier = result.scalar_one_or_none()
        if not tier:
            raise ValueError(f"active {tier_enum.name} subscription tier not found")

        logger.info(f"found active {tier_enum.name} tier (ID: {tier.id})")
        return tier

    async def delete_all_subscriptions(self, user_id: uuid.UUID) -> None:
        """delete all subscriptions and their payments for the user."""
        logger.info(f"deleting all subscriptions for User {user_id}")
        
        stmt = select(Subscription.id).where(Subscription.user_id == user_id)
        result = await self.db.execute(stmt)
        sub_ids = result.scalars().all()

        if not sub_ids:
            logger.info(f"No subscriptions found for User {user_id}")
            return
            
        logger.info(f"found {len(sub_ids)} subscriptions to delete")
        logger.info("\n")
        logger.info("ℹ️  Found Subscriptions:")
        logger.info("\n")
        logger.info(f"{'Subscription ID':<40}")
        logger.info(f"{'-' * 40}")
        for sub_id in sub_ids:
            logger.info(f"{str(sub_id):<40}")

        logger.info("\n")
        
        payment_stmt = delete(SubscriptionPayment).where(
            SubscriptionPayment.subscription_id.in_(sub_ids)
        )
        payment_result = await self.db.execute(payment_stmt)
        logger.info(f"deleted {payment_result.rowcount} subscription payments")
        

        paid_stmt = delete(PaidSubscription).where(
            PaidSubscription.id.in_(sub_ids)
        )
        paid_result = await self.db.execute(paid_stmt)
        logger.info(f"deleted {paid_result.rowcount} paid subscriptions")
        

        free_stmt = delete(FreeSubscription).where(
            FreeSubscription.id.in_(sub_ids)
        )
        free_result = await self.db.execute(free_stmt)
        logger.info(f"deleted {free_result.rowcount} free subscriptions")
        

        base_stmt = delete(Subscription).where(
            Subscription.id.in_(sub_ids)
        )
        base_result = await self.db.execute(base_stmt)
        logger.info(f"deleted {base_result.rowcount} base subscriptions")

    async def create_paused_free_subscription(
        self, user_id: uuid.UUID, virtual_lab_id: Optional[uuid.UUID]
    ) -> uuid.UUID:
        """create a new paused free subscription."""
        logger.info(f"creating paused free subscription for User {user_id}")
        
        free_tier = await self.get_subscription_tier(SubscriptionTierEnum.FREE)
        
        now_utc = datetime.now(timezone.utc)
        far_future = now_utc + timedelta(days=365 * 100)  # 100 years
        now_naive = now_utc.replace(tzinfo=None)
        far_future_naive = far_future.replace(tzinfo=None)
        
        free_sub = FreeSubscription(
            user_id=user_id,
            virtual_lab_id=virtual_lab_id,
            tier_id=free_tier.id,
            subscription_type=SubscriptionType.FREE,
            current_period_start=now_naive,
            current_period_end=far_future_naive,
            status=SubscriptionStatus.PAUSED,
            source=SubscriptionSource.SCRIPT,
            usage_count=0,
        )
        
        self.db.add(free_sub)
        await self.db.flush()
        logger.info(f"created paused free subscription with ID: {free_sub.id}")
        return free_sub.id

    async def create_lifetime_pro_subscription(
        self, user_id: uuid.UUID, virtual_lab_id: Optional[uuid.UUID]
    ) -> Tuple[uuid.UUID, uuid.UUID]:
        """create a new pro subscription with 100-year validity."""
        logger.info(f"creating lifetime pro subscription for User {user_id}")
        
        pro_tier = await self.get_subscription_tier(SubscriptionTierEnum.PRO)
        
        now_utc = datetime.now(timezone.utc)
        lifetime = now_utc + timedelta(days=365 * 100)  # 100 years
        now_naive = now_utc.replace(tzinfo=None)
        lifetime_naive = lifetime.replace(tzinfo=None)
        
        stripe_sub_id = f"sub_manual_{uuid.uuid4()}"
        stripe_customer_id = f"cus_manual_{user_id}"
        

        pro_sub = PaidSubscription(
            user_id=user_id,
            virtual_lab_id=virtual_lab_id,
            tier_id=pro_tier.id,
            subscription_type=SubscriptionType.PRO,
            status=SubscriptionStatus.ACTIVE,
            current_period_start=now_naive,
            current_period_end=lifetime_naive,
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
        
        self.db.add(pro_sub)
        await self.db.flush()
        logger.info(f"created lifetime pro subscription with ID: {pro_sub.id}")
        

        payment = SubscriptionPayment(
            subscription_id=pro_sub.id,
            customer_id=stripe_customer_id,
            virtual_lab_id=virtual_lab_id,
            stripe_invoice_id=f"in_manual_{uuid.uuid4()}",
            stripe_payment_intent_id=f"pi_manual_{uuid.uuid4()}",
            stripe_charge_id=f"ch_manual_{uuid.uuid4()}",
            card_brand="manual",
            card_last4="0000",
            card_exp_month=12,
            card_exp_year=datetime.now(timezone.utc).year + 3,
            amount_paid=pro_sub.amount,
            currency=pro_sub.currency,
            status=PaymentStatus.SUCCEEDED,
            period_start=now_naive,
            period_end=lifetime_naive,
            payment_date=now_naive,
            standalone=False,
        )
        
        self.db.add(payment)
        await self.db.flush()
        logger.info(f"created payment record with ID: {payment.id}")
        
        return pro_sub.id, payment.id

    async def upgrade_user_to_pro(self, user_id: uuid.UUID) -> bool:
        """complete subscription upgrade process for a single user."""
        virtual_lab_id = await self.get_virtual_lab_id(user_id)
        logger.info(f"ℹ️  virtual lab ID: {virtual_lab_id}")
        logger.info(f"ℹ️  starting subscription upgrade for User {user_id}")
        await self.delete_all_subscriptions(user_id) 
        await self.create_paused_free_subscription(user_id, virtual_lab_id)     
        pro_sub_id, _ = await self.create_lifetime_pro_subscription(user_id, virtual_lab_id) 
        
        if pro_sub_id:
            logger.info(f"✅ successfully upgraded user {user_id} to pro subscription (ID: {pro_sub_id})")
            return True
        else:
            logger.error(f"failed to upgrade user {user_id} to pro")
            return False



async def upgrade_users(user_ids: List[uuid.UUID], use_ssh_tunnel: bool = False) -> None:
    """upgrade multiple users to pro subscription."""
    db_connection = DatabaseConnection()
    
    try:
        await db_connection.initialize(use_ssh_tunnel=use_ssh_tunnel)
        session_maker = db_connection.session()
        
        success_count = 0
        failure_count = 0
        successful_users = []
        failed_users = []
        
        for user_id in user_ids:
            async with session_maker() as session:
                async with session.begin():
                    upgrader = SubscriptionUpgrade(session)
                    success = await upgrader.upgrade_user_to_pro(user_id)
                    
                    if success:
                        success_count += 1
                        successful_users.append(str(user_id))
                    else:
                        failure_count += 1
                        failed_users.append(str(user_id))
            logger.info("––––––––––––––––––––––––––––––––––––")
        logger.info("\n")
        logger.info(f"ℹ️  Upgrade process completed for {len(user_ids)} users")
        logger.info(f"✅  Success: {success_count}")
        logger.info(f"❌  Failures: {failure_count}")
        

        if successful_users or failed_users:
            logger.info("\n")
            logger.info("ℹ️  Upgrade Results:")
            logger.info(f"{'User ID':<40} | {'Status':<10}")
            logger.info(f"{'-' * 40} | {'-' * 10}")
            
            for user_id in successful_users:
                logger.info(f"{user_id:<40} | SUCCESS")
                
            for user_id in failed_users:
                logger.info(f"{user_id:<40} | FAILED")
            
    finally:
        await db_connection.close()


def parse_user_ids(user_id_str: str) -> List[uuid.UUID]:
    """parse comma separatted user IDs into UUID list."""
    try:
        return [uuid.UUID(user_id.strip()) for user_id in user_id_str.split(',')]
    except ValueError as e:
        raise argparse.ArgumentTypeError(f"Invalid UUID format: {str(e)}")


async def _run_async_impl() -> None:
    parser = argparse.ArgumentParser(
        description="upgrade users to lifetime pro subscriptions"
    )
    parser.add_argument(
        "user_ids",
        type=str,
        help="comma separated list of user UUIDs to upgrade",
    )
    parser.add_argument(
        "--ssh",
        action="store_true",
        help="use ssh tunnel for database connection",
    )
    args = parser.parse_args()
    
    try:
        user_ids = parse_user_ids(args.user_ids)
        if not user_ids:
            logger.error("no valid user IDs provided")
            sys.exit(1)
            
        logger.info(f"starting upgrade process for {len(user_ids)} users")
        logger.info(f"using ssh tunnel: {'yes' if args.ssh else 'no'}")
        
        await upgrade_users(user_ids, use_ssh_tunnel=args.ssh)
        
        logger.info("✅ upgrade process completed")
        
    except Exception as e:
        logger.exception(e)
        logger.error(f"error in upgrade process: {str(e)}")
        sys.exit(1)


def run_async() -> int:
    """
    Entrypoint for poetry script command.
    """
    asyncio.run(_run_async_impl())
    return 0


if __name__ == "__main__":
    run_async()