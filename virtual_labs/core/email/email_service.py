from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType
from loguru import logger
from pydantic import UUID4, BaseModel, EmailStr

from virtual_labs.core.email.email_utils import (
    get_encrypted_invite_token,
    get_invite_html,
    get_invite_link,
)
from virtual_labs.core.exceptions.email_error import EmailError
from virtual_labs.infrastructure.settings import settings

email_config = ConnectionConfig(
    MAIL_USERNAME=settings.MAIL_USERNAME,
    MAIL_PASSWORD=settings.MAIL_PASSWORD,
    MAIL_FROM=settings.MAIL_FROM,
    MAIL_PORT=settings.MAIL_PORT,
    MAIL_SERVER=settings.MAIL_SERVER,
    MAIL_STARTTLS=settings.MAIL_STARTTLS,
    MAIL_SSL_TLS=settings.MAIL_SSL_TLS,
    USE_CREDENTIALS=settings.USE_CREDENTIALS,
    VALIDATE_CERTS=settings.VALIDATE_CERTS,
)


class EmailDetails(BaseModel):
    recipient: EmailStr
    invite_id: UUID4

    lab_id: UUID4
    lab_name: str

    project_id: UUID4 | None = None
    project_name: str | None = None


async def send_invite(details: EmailDetails) -> str:
    try:
        invite_token = get_encrypted_invite_token(details.invite_id)
        invite_link = get_invite_link(
            invite_token, lab_id=details.lab_id, project_id=details.project_id
        )
        invite_html = get_invite_html(
            invite_link, lab_name=details.lab_name, project_name=details.project_name
        )

        message = MessageSchema(
            subject="Fastapi-Mail module",
            recipients=[details.recipient],
            body=invite_html,
            subtype=MessageType.html,
        )

        fm = FastMail(email_config)
        await fm.send_message(message)
        logger.debug(f"Invite link {invite_link} emailed to users {details.recipient}")
        return invite_link
    except Exception as error:
        logger.error(
            f"Invite ID {details.invite_id} could not be emailed to user {details.recipient} because of error {error}"
        )
        raise EmailError(
            message=f"Invite ID {details.invite_id} could not be emailed to user {details.recipient}",
            detail=str(error),
        )
