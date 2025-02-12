from fastapi_mail import FastMail, MessageSchema, MessageType
from loguru import logger

from virtual_labs.core.exceptions.email_error import EmailError
from virtual_labs.domain.email import VerificationCodeEmailDetails
from virtual_labs.infrastructure.email.config import email_config
from virtual_labs.infrastructure.email.email_utils import (
    generate_email_verification_html,
)


async def send_verification_code_email(details: VerificationCodeEmailDetails) -> str:
    try:
        invite_html = generate_email_verification_html(
            code=details.code,
        )
        message = MessageSchema(
            subject="Your Verification Code",
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
                "code": details.code,
            },
        )
        fm = FastMail(email_config)
        await fm.send_message(message, template_name="email_verification_code.html")
    except Exception as error:
        logger.error(
            f"Invite ID {details.invite_id} could not be emailed to user {details.recipient} because of error {error}"
        )
        raise EmailError(
            message=f"Invite ID {details.invite_id} could not be emailed to user {details.recipient}",
            detail=str(error),
        ) from error
