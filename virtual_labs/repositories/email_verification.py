from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.expression import false, true

from virtual_labs.infrastructure.db.models import EmailVerificationCode


class EmailValidationQueryRepository:
    session: AsyncSession

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def check_email_verified(
        self,
        email: str,
        virtual_lab_name: str,
        user_id: UUID,
    ):
        """Check if an email already exists and validated in the database."""

        query = select(EmailVerificationCode).filter(
            EmailVerificationCode.email == email,
            EmailVerificationCode.user_id == user_id,
            EmailVerificationCode.virtual_lab_name == virtual_lab_name,
            EmailVerificationCode.is_verified == true(),
        )
        email_verification_code = await self.session.scalar(statement=query)

        return email_verification_code is not None

    async def get_verification_code(
        self,
        email: str,
        user_id: UUID,
        virtual_lab_name: str,
    ):
        now = datetime.utcnow()
        result = await self.session.execute(
            select(EmailVerificationCode)
            .filter(
                EmailVerificationCode.email == email,
                EmailVerificationCode.user_id == user_id,
                EmailVerificationCode.virtual_lab_name == virtual_lab_name,
                EmailVerificationCode.is_verified == false(),
                EmailVerificationCode.expires_at >= now,
            )
            .order_by(EmailVerificationCode.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_latest_verification_code_entry(
        self,
        email: str,
        user_id: UUID,
        virtual_lab_name: str,
    ):
        """Get the most recent lock time for unverified tokens"""

        stmt = (
            select(EmailVerificationCode)
            .filter(
                EmailVerificationCode.email == email,
                EmailVerificationCode.user_id == user_id,
                EmailVerificationCode.virtual_lab_name == virtual_lab_name,
                EmailVerificationCode.is_verified == false(),
                EmailVerificationCode.expires_at >= datetime.utcnow(),
            )
            .order_by(EmailVerificationCode.created_at.desc())
            .limit(1)
        )

        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class EmailValidationMutationRepository:
    session: AsyncSession

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def invalidate_previous_tokens(
        self,
        email: str,
    ):
        """Mark all previous unused tokens for the email as used."""

        stmt = (
            update(EmailVerificationCode)
            .where(
                EmailVerificationCode.email == email,
                EmailVerificationCode.is_verified == false(),
            )
            .values({"is_verified": True})
        )
        await self.session.execute(stmt)
        await self.session.commit()

    async def generate_verification_token(
        self,
        email: str,
        user_id: UUID,
        virtual_lab_name: str,
        code: str,
        token_expiry: int = 1,
    ) -> str:
        """Generate and store a new verification token."""

        expires_at = datetime.utcnow() + timedelta(hours=token_expiry)

        verification_code = EmailVerificationCode(
            email=email,
            code=code,
            expires_at=expires_at,
            user_id=user_id,
            virtual_lab_name=virtual_lab_name,
        )

        self.session.add(verification_code)
        await self.session.commit()
        await self.session.refresh(verification_code)

        return code
