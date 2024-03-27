from datetime import datetime, timedelta

import jwt
from pydantic import UUID4

from virtual_labs.infrastructure.settings import settings


def get_expiration_time() -> str:
    "Returns epoch timestamp for seven days from now as a str. Example: '1712131180000'"
    seven_days = datetime.now() + timedelta(7)
    return seven_days.strftime("%s000")


def get_encrypted_invite_token(invite_id: UUID4) -> str:
    invite_data = {"invite_id": str(invite_id), "expires_at": get_expiration_time()}
    return jwt.encode(invite_data, settings.JWT_SECRET, algorithm="HS256")


# TODO: The links here might need updating depending on the actual lab/project details page where the user should be redirected to.
def get_invite_link(invite_token: str, lab_id: UUID4, project_id: UUID4 | None) -> str:
    if project_id is None:
        return f"https://openbrainplatform.org/mmb-beta/lab/{str(lab_id)}?invite_token={invite_token}"
    else:
        return f"https://openbrainplatform.org/mmb-beta/lab/{str(lab_id)}/project/{str(project_id)}?invite_token={invite_token}"


def get_invite_html(invite_link: str, lab_name: str, project_name: str | None) -> str:
    if project_name is None:
        return f"""
            You have been invited to virtual lab {lab_name}. Please click on the link below to accept the invite:
            <a href="{invite_link}">{invite_link}</a>
        """
    else:
        return f"""
            You have been invited to project {lab_name} within the {lab_name} virtual lab. Please click on the link below to accept the invite:
            {invite_link}
        """
