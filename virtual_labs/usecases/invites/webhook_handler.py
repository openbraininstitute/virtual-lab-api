import hashlib
import hmac
from http import HTTPStatus
from uuid import UUID

from pydantic import EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.types import UserRoleEnum
from virtual_labs.domain.invite import InvitePayload
from virtual_labs.infrastructure.settings import settings
from virtual_labs.repositories.project_repo import ProjectQueryRepository
from virtual_labs.usecases.project.invite_user_to_project import invite_user_to_project


def compute_webhook_signature(body: bytes, secret: str) -> str:
    """Compute HMAC-SHA256 signature for a webhook payload."""
    return hmac.HMAC(
        secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()


def verify_webhook_signature(signature: str, body: bytes) -> None:
    """
    Verify the webhook signature.

    The sender computes: HMAC-SHA256(body, secret) and hex-encodes the digest.
    We compute the same and compare using a timing-safe comparison.
    """
    if not settings.INVITE_WEBHOOK_SECRET:
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message="Webhook secret is not configured",
        )

    expected = compute_webhook_signature(body, settings.INVITE_WEBHOOK_SECRET)

    if not hmac.compare_digest(signature, expected):
        raise VliError(
            error_code=VliErrorCode.INVALID_PARAMETER,
            http_status_code=HTTPStatus.UNAUTHORIZED,
            message="Invalid webhook signature",
        )


async def handle_invite_webhook(
    session: AsyncSession,
    *,
    signature: str,
    body: bytes,
    virtual_lab_id: str,
    project_id: str,
    inviter_id: str,
    invitee_email: EmailStr,
    invitee_name: str,
) -> dict:
    """
    Handle an incoming webhook to invite a user to a project.

    Steps:
    1. Verify the webhook signature
    2. Verify the virtual lab and project exist
    3. Send an invite to the project
    """
    # 1. Verify signature
    verify_webhook_signature(signature, body)

    vlab_uuid = UUID(virtual_lab_id)
    project_uuid = UUID(project_id)
    inviter_uuid = UUID(inviter_id)

    # 2. Verify virtual lab and project exist
    pqr = ProjectQueryRepository(session)
    try:
        await pqr.retrieve_one_project_strict(
            virtual_lab_id=vlab_uuid,
            project_id=project_uuid,
        )
    except Exception:
        raise VliError(
            error_code=VliErrorCode.INVALID_REQUEST,
            http_status_code=HTTPStatus.NOT_FOUND,
            message=f"Project {project_id} not found in virtual lab {virtual_lab_id}",
        )

    # 3. Send invite to the project (x_user_id is the inviter)
    await invite_user_to_project(
        session=session,
        virtual_lab_id=vlab_uuid,
        project_id=project_uuid,
        inviter_id=inviter_uuid,
        invite_details=InvitePayload(
            email=invitee_email,
            role=UserRoleEnum.member,
        ),
    )

    return {
        "message": "Invite sent successfully",
        "virtual_lab_id": virtual_lab_id,
        "project_id": project_id,
        "invitee_email": invitee_email,
        "invitee_name": invitee_name,
    }
