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
    invitee_name: str | None = None
    inviter_name: str
    invite_id: UUID4

    lab_id: UUID4
    lab_name: str

    project_id: UUID4 | None = None
    project_name: str | None = None


async def send_invite(details: EmailDetails) -> str:
    try:
        origin = (
            InviteOrigin.LAB if details.project_id is None else InviteOrigin.PROJECT
        )
        display_origin = "virtual lab" if origin is InviteOrigin.LAB else "project"
        invite_token = generate_encrypted_invite_token(details.invite_id, origin)
        invite_link = generate_invite_link(invite_token)
        invite_html = generate_invite_html(
            invite_link, lab_name=details.lab_name, project_name=details.project_name
        )

        message = MessageSchema(
            subject=f"Invitation to OBI {display_origin}",
            recipients=[details.recipient],
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
                "invitee_name": details.invitee_name,
                "inviter_name": details.inviter_name,
                "invite_link": invite_link,
                "discover_link": f"{settings.LANDING_NAMESPACE}",
                "origin": display_origin,
                "invited_to": details.lab_name
                if origin is InviteOrigin.LAB
                else details.project_name,
            },
        )
        fm = FastMail(email_config)
        await fm.send_message(message, template_name="invitation_template.html")
        logger.debug(f"Invite link {invite_link} emailed to user {details.recipient}")
        return invite_link
    except Exception as error:
        logger.error(
            f"Invite ID {details.invite_id} could not be emailed to user {details.recipient} because of error {error}"
        )
        raise EmailError(
            message=f"Invite ID {details.invite_id} could not be emailed to user {details.recipient}",
            detail=str(error),
        ) from error
