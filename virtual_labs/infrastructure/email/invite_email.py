from fastapi_mail import FastMail, MessageSchema, MessageType
from loguru import logger
from pydantic import UUID4, BaseModel, EmailStr

from virtual_labs.core.exceptions.email_error import EmailError
from virtual_labs.infrastructure.email.config import email_config
from virtual_labs.infrastructure.email.email_utils import (
    InviteOrigin,
    generate_encrypted_invite_token,
    generate_invite_html,
    generate_invite_link,
)
from virtual_labs.infrastructure.settings import settings


class EmailDetails(BaseModel):
    recipient: EmailStr
    inviter_name: str
    invite_id: UUID4

    lab_id: UUID4
    lab_name: str

    project_id: UUID4 | None = None
    project_name: str | None = None


fm_executor = FastMail(email_config)


async def send_invite(payload: EmailDetails) -> str:
    try:
        origin = (
            InviteOrigin.LAB if payload.project_id is None else InviteOrigin.PROJECT
        )
        display_origin = "virtual lab" if origin is InviteOrigin.LAB else "project"
        invite_token = generate_encrypted_invite_token(payload.invite_id, origin)
        invite_link = generate_invite_link(invite_token)
        invite_html = generate_invite_html(
            invite_link=invite_link,
            lab_name=payload.lab_name,
            project_name=payload.project_name,
        )

        message = MessageSchema(
            subject=f"Invitation to OBI {display_origin}",
            recipients=[payload.recipient],
            body=invite_html,
            subtype=MessageType.html,
            attachments=[
                {
                    "file": "virtual_labs/infrastructure/email/assets/logo.png",
                    "headers": {
                        "Content-ID": "logo",
                        "Content-Disposition": 'inline; filename="logo.png"',  # For inline images only
                    },
                    "mime_type": "image",
                    "mime_subtype": "png",
                    "Content-Type": "multipart/related",
                },
            ],
            template_body={
                "inviter_name": payload.inviter_name,
                "invite_link": invite_link,
                "discover_link": f"{settings.LANDING_NAMESPACE}",
                "origin": display_origin,
                "invited_to": payload.lab_name
                if origin is InviteOrigin.LAB
                else payload.project_name,
            },
        )

        await fm_executor.send_message(
            message=message,
            html_template="invitation_template.html",
            plain_template="invitation_template.txt",
        )
        logger.debug(f"Invite link {invite_link} emailed to user {payload.recipient}")
        return invite_link
    except Exception as error:
        logger.error(
            f"Invite ID {payload.invite_id} could not be emailed to user {payload.recipient} because of error {error}"
        )
        raise EmailError(
            message=f"Invite ID {payload.invite_id} could not be emailed to user {payload.recipient}",
            detail=str(error),
        ) from error
