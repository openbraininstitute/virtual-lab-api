"""Send a claim-link email to a student after seat assignment."""

from fastapi_mail import FastMail, MessageSchema, MessageType
from loguru import logger
from pydantic import UUID4, BaseModel, NameEmail

from virtual_labs.core.exceptions.email_error import EmailError
from virtual_labs.infrastructure.email.config import email_config
from virtual_labs.infrastructure.settings import settings


class EnrolmentClaimEmailDetails(BaseModel):
    recipient_email: str
    student_id: str
    enrolment_id: UUID4
    course_id: UUID4


fm_executor = FastMail(email_config)


def _generate_claim_link(enrolment_id: UUID4) -> str:
    return f"{settings.INVITE_LINK_BASE}/course-enrolment?enrolment_id={enrolment_id}"


async def send_enrolment_claim_email(details: EnrolmentClaimEmailDetails) -> str:
    """Send a claim-link email to the student. Returns the claim link on success."""
    claim_link = _generate_claim_link(details.enrolment_id)
    try:
        html_body = (
            f"You have been enrolled in a course. "
            f"Please click the link below to claim your enrolment:<br/>"
            f'<a href="{claim_link}">{claim_link}</a>'
        )

        message = MessageSchema(
            subject="Claim your course enrolment",
            recipients=[NameEmail("", details.recipient_email)],
            body=html_body,
            subtype=MessageType.html,
            headers={"X-SES-CONFIGURATION-SET": settings.AWS_SES_CONFIGURATION_SET},
        )

        await fm_executor.send_message(message=message)
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
