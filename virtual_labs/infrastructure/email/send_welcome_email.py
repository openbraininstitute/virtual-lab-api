from fastapi_mail import FastMail, MessageSchema, MessageType
from loguru import logger

from virtual_labs.infrastructure.email.config import email_config


async def send_welcome_email(recipient: str) -> str:
    try:
        message = MessageSchema(
            subject="Start your Simulation Journey!",
            recipients=[recipient],
            body="",
            subtype=MessageType.html,
            template_body={},
        )
        fm = FastMail(email_config)
        await fm.send_message(message, template_name="welcome.html")
        logger.info(f"A welcome email has been sent to {recipient}")
        return f"email sent successfully to {recipient}"
    except Exception as error:
        logger.error(f"Unable to send a welcome email to {recipient}!\n{error}")
        return f"email has not been sent to {recipient}"
