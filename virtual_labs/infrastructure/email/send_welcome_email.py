from fastapi_mail import FastMail, MessageSchema, MessageType
from loguru import logger
from pydantic import NameEmail

from virtual_labs.infrastructure.email.config import email_config
from virtual_labs.infrastructure.settings import settings


async def send_welcome_email(recipient: str) -> str:
    try:
        message = MessageSchema(
            subject="Start your Simulation Journey!",
            recipients=[NameEmail("", recipient)],
            body="",
            subtype=MessageType.html,
            template_body={},
            attachments=[
                {
                    "file": "virtual_labs/infrastructure/email/assets/advertisement-video-poster.webp",
                    "headers": {
                        "Content-ID": "<advertisement-video-poster@openbraininstitute.org>",
                        "Content-Disposition": 'inline; filename="advertisement-video-poster.webp"',
                    },
                    "mime_type": "image",
                    "mime_subtype": "webp",
                },
                {
                    "file": "virtual_labs/infrastructure/email/assets/youtube-filled-light-40.png",
                    "headers": {
                        "Content-ID": "<youtube-filled-light-40@openbraininstitute.org>",
                        "Content-Disposition": 'inline; filename="youtube-filled-light-40.png"',
                    },
                    "mime_type": "image",
                    "mime_subtype": "png",
                },
                {
                    "file": "virtual_labs/infrastructure/email/assets/open-brain-institute-logo-large.png",
                    "headers": {
                        "Content-ID": "<open-brain-institute-logo-large@openbraininstitute.org>",
                        "Content-Disposition": 'inline; filename="open-brain-institute-logo-large.png"',
                    },
                    "mime_type": "image",
                    "mime_subtype": "png",
                },
                {
                    "file": "virtual_labs/infrastructure/email/assets/twitter-filled-light-40.png",
                    "headers": {
                        "Content-ID": "<twitter-filled-light-40@openbraininstitute.org>",
                        "Content-Disposition": 'inline; filename="twitter-filled-light-40.png"',
                    },
                    "mime_type": "image",
                    "mime_subtype": "png",
                },
                {
                    "file": "virtual_labs/infrastructure/email/assets/linkedin-filled-light-40.png",
                    "headers": {
                        "Content-ID": "<linkedin-filled-light-40@openbraininstitute.org>",
                        "Content-Disposition": 'inline; filename="linkedin-filled-light-40.png"',
                    },
                    "mime_type": "image",
                    "mime_subtype": "png",
                },
            ]
            if email_config.TEMPLATE_FOLDER is not None
            else [],
            headers={"X-SES-CONFIGURATION-SET": settings.AWS_SES_CONFIGURATION_SET},
        )
        fm = FastMail(email_config)
        await fm.send_message(message, template_name="welcome.html")
        logger.info(f"A welcome email has been sent to {recipient}")
        return f"email sent successfully to {recipient}"
    except Exception as error:
        logger.error(f"Unable to send a welcome email to {recipient}!\n{error}")
        return f"email has not been sent to {recipient}"
