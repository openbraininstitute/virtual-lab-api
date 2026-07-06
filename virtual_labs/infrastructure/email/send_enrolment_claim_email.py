"""Send a claim-link email to a student after seat assignment."""

from fastapi_mail import FastMail, MessageSchema, MessageType
from loguru import logger
from pydantic import UUID4, BaseModel, EmailStr, NameEmail

from virtual_labs.core.exceptions.email_error import EmailError
from virtual_labs.infrastructure.email.config import email_config
from virtual_labs.infrastructure.settings import settings


class EnrolmentClaimEmailDetails(BaseModel):
    recipient_email: EmailStr
    enrolment_id: UUID4
    course_name: str


fm_executor = FastMail(email_config)


def _generate_claim_link(enrolment_id: UUID4) -> str:
    return f"{settings.INVITE_LINK_BASE}/course-enrolment?enrolment_id={enrolment_id}"


async def send_enrolment_claim_email(details: EnrolmentClaimEmailDetails) -> str:
    """Send a claim-link email to the student. Returns the claim link on success."""
    claim_link = _generate_claim_link(details.enrolment_id)
    try:
        message = MessageSchema(
            subject="You've been enrolled in a course — Open Brain Platform",
            recipients=[NameEmail("", details.recipient_email)],
            body="",
            subtype=MessageType.html,
            attachments=[
                {
                    "file": "virtual_labs/infrastructure/email/assets/logo.png",
                    "headers": {
                        "Content-ID": "logo",
                        "Content-Disposition": 'inline; filename="logo.png"',
                    },
                    "mime_type": "image",
                    "mime_subtype": "png",
                    "Content-Type": "multipart/related",
                },
            ],
            template_body={
                "course_name": details.course_name,
                "claim_link": claim_link,
                "discover_link": f"{settings.LANDING_NAMESPACE}",
            },
            headers={"X-SES-CONFIGURATION-SET": settings.AWS_SES_CONFIGURATION_SET},
        )

        await fm_executor.send_message(
            message=message,
            html_template="course_enrolment_claim.html",
            plain_template="course_enrolment_claim.txt",
        )
        logger.debug(
            f"Enrolment claim link emailed to {details.recipient_email} "
            f"(enrolment_id={details.enrolment_id})"
        )
        return claim_link
    except Exception as error:
        logger.error(
            f"Failed to email claim link to {details.recipient_email} "
            f"(enrolment_id={details.enrolment_id}): {error}"
        )
        raise EmailError(
            message=f"Could not email claim link to {details.recipient_email}",
            detail=str(error),
        ) from error
