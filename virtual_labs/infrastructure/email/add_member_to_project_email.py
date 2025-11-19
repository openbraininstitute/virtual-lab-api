from fastapi_mail import FastMail, MessageSchema, MessageType
from loguru import logger
from pydantic import UUID4, BaseModel, NameEmail

from virtual_labs.core.exceptions.email_error import EmailError
from virtual_labs.infrastructure.email.config import email_config
from virtual_labs.infrastructure.email.email_utils import (
    generate_email_to_add_user_to_project,
)
from virtual_labs.infrastructure.settings import settings


class EmailDetails(BaseModel):
    recipient: str
    inviter_name: str
    lab_name: str
    lab_id: UUID4
    project_id: UUID4
    project_name: str


async def send_add_member_to_project_email(details: EmailDetails) -> str:
    try:
        project_link = f"{settings.DEPLOYMENT_NAMESPACE}/app/virtual-lab/lab/{details.lab_id}/project/{details.project_id}/home"
        body_html = generate_email_to_add_user_to_project(
            details.project_name, details.lab_name, project_link, details.inviter_name
        )
        message = MessageSchema(
            subject=f"You have been given access to OBI's project titled {details.project_name}",
            recipients=[NameEmail("", details.recipient)],
            body=body_html,
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
                "inviter_name": details.inviter_name,
                "project_name": details.project_name,
                "lab_name": details.lab_name,
                "project_link": project_link,
            },
        )
        fm = FastMail(email_config)
        await fm.send_message(
            message, template_name="add_member_to_project_template.html"
        )
        logger.debug(f"Project link {project_link} emailed to user {details.recipient}")
        return project_link
    except Exception as error:
        logger.error(
            f"Project link {project_link} could not be emailed to user {details.recipient} because of error {error}"
        )
        raise EmailError(
            message=f"Project link {project_link} could not be emailed to user {details.recipient}",
            detail=str(error),
        ) from error
