from datetime import datetime, timedelta

from pydantic import EmailStr
from sqlalchemy import false, select, true, update
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.infrastructure.db.models import EmailVerificationToken


class EmailValidationQueryRepository:
    session: AsyncSession

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def check_email_exists(
        self,
        email: EmailStr,
    ):
        """Check if an email already exists and validated in the database."""

        query = select(EmailVerificationToken).filter(
            EmailVerificationToken.email == email,
            EmailVerificationToken.is_used == true(),
        )
        email_verification_token = await self.session.scalar(statement=query)
        return email_verification_token

    async def get_verification_token(self, email: EmailStr):
        now = datetime.utcnow()
        result = await self.session.execute(
            select(EmailVerificationToken)
            .filter(
                EmailVerificationToken.email == email,
                EmailVerificationToken.is_used == False,
                EmailVerificationToken.expires_at >= now,
            )
            .order_by(EmailVerificationToken.created_at.desc())
            .limit(1)
        )
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
            update(EmailVerificationToken)
            .where(
                EmailVerificationToken.email == email,
                EmailVerificationToken.is_used == false(),
            )
            .values({"is_used": True})
        )
        await self.session.execute(stmt)
        await self.session.commit()

    async def generate_verification_token(
        self,
        email: str,
        code: str,
        token_expiry: int = 1,
    ) -> str:
        """Generate and store a new verification token."""

        expires_at = datetime.utcnow() + timedelta(hours=token_expiry)

        verification_token = EmailVerificationToken(
            email=email,
            token=code,
            expires_at=expires_at,
        )
        await self.session.add(verification_token)
        await self.session.commit()
        await self.session.refresh(verification_token)

        return code
