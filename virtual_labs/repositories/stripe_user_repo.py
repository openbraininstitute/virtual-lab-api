from typing import Optional
from uuid import UUID

from loguru import logger
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.infrastructure.db.models import StripeUser


class StripeUserQueryRepository:
    """
    repository for querying StripeUser records.
    """

    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session

    async def get_by_user_id(self, user_id: UUID) -> Optional[StripeUser]:
        """
        Get a StripeUser by user_id.

        Args:
            user_id: The owner's UUID

        Returns:
            Optional[StripeUser]: The StripeUser if found, None otherwise
        """

        query = select(StripeUser).where(StripeUser.user_id == user_id)
        result = await self.db_session.execute(query)
        return result.scalars().first()

    async def get_by_stripe_customer_id(
        self, stripe_customer_id: str
    ) -> Optional[StripeUser]:
        """
        Get a StripeUser by stripe_customer_id.

        Args:
            stripe_customer_id: The Stripe customer ID

        Returns:
            Optional[StripeUser]: The StripeUser if found, None otherwise
        """
        try:
            query = select(StripeUser).where(
                StripeUser.stripe_costumer_id == stripe_customer_id
            )
            result = await self.db_session.execute(query)
            return result.scalars().first()
        except SQLAlchemyError as e:
            logger.error(
                f"Error querying StripeUser by stripe_customer_id {stripe_customer_id}: {str(e)}"
            )
            return None


class StripeUserMutationRepository:
    """
    Repository for creating and modifying StripeUser records.
    """

    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session

    async def create(
        self, user_id: UUID, stripe_customer_id: str
    ) -> Optional[StripeUser]:
        """
        Create a new StripeUser.

        Args:
            user_id: The owner's UUID
            stripe_customer_id: The Stripe customer ID

        Returns:
            Optional[StripeUser]: The created StripeUser if successful, None otherwise
        """
        try:
            stripe_user = StripeUser(
                user_id=user_id, stripe_costumer_id=stripe_customer_id
            )
            self.db_session.add(stripe_user)
            await self.db_session.commit()
            await self.db_session.refresh(stripe_user)
            return stripe_user
        except SQLAlchemyError as e:
            await self.db_session.rollback()
            logger.error(
                f"Error creating StripeUser for user_id {user_id} with stripe_customer_id {stripe_customer_id}: {str(e)}"
            )
            return None

    async def update_stripe_customer_id(
        self, user_id: UUID, stripe_customer_id: str
    ) -> Optional[StripeUser]:
        """
        Update the Stripe customer ID for a user.

        Args:
            user_id: The owner's UUID
            stripe_customer_id: The new Stripe customer ID

        Returns:
            Optional[StripeUser]: The updated StripeUser if successful, None otherwise
        """
        try:
            query_repo = StripeUserQueryRepository(db_session=self.db_session)
            stripe_user = await query_repo.get_by_user_id(user_id)

            if not stripe_user:
                return await self.create(user_id, stripe_customer_id)

            stripe_user.stripe_costumer_id = stripe_customer_id
            await self.db_session.commit()
            await self.db_session.refresh(stripe_user)
            return stripe_user
        except SQLAlchemyError as e:
            await self.db_session.rollback()
            logger.error(
                f"Error updating stripe_customer_id for user_id {user_id}: {str(e)}"
            )
            return None

    async def delete(self, user_id: UUID) -> bool:
        """
        Delete a StripeUser by user_id.

        Args:
            user_id: The owner's UUID

        Returns:
            bool: True if deleted successfully, False otherwise
        """
        try:
            query_repo = StripeUserQueryRepository(db_session=self.db_session)
            stripe_user = await query_repo.get_by_user_id(user_id)

            if not stripe_user:
                logger.warning(
                    f"StripeUser with user_id {user_id} not found for deletion"
                )
                return False

            await self.db_session.delete(stripe_user)
            await self.db_session.commit()
            return True
        except SQLAlchemyError as e:
            await self.db_session.rollback()
            logger.error(f"Error deleting StripeUser for user_id {user_id}: {str(e)}")
            return False
