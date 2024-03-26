from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType
from loguru import logger
from pydantic import BaseModel, EmailStr
from starlette.responses import JSONResponse

from virtual_labs.infrastructure.settings import settings


class EmailSchema(BaseModel):
    email: list[EmailStr]


html = """
<p>Hello world!</p> 
"""

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


async def send_email(email: EmailSchema) -> JSONResponse:
    message = MessageSchema(
        subject="Fastapi-Mail module",
        recipients=email.email,
        body=html,
        subtype=MessageType.html,
    )

    fm = FastMail(email_config)
    await fm.send_message(message)
    logger.debug(f"Email sent to user {email}")
    return JSONResponse(status_code=200, content={"message": "email has been sent"})
