from typing import cast

from virtual_labs.infrastructure.kc.config import kc_auth


def auth(username: str = "test") -> str:
    token = kc_auth.token(username=username, password="test")
    print("TOKEN", token)
    return cast(str, token["access_token"])


def get_headers(username: str = "test") -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {auth(username)}",
    }
