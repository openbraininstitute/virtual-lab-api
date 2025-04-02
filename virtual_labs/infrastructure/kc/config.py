from typing import Dict

import httpx
from keycloak import KeycloakAdmin, KeycloakOpenID  # type: ignore

from virtual_labs.infrastructure.settings import settings

"""
    will have many realms 
    or we should have service account and then use the credentials for every realm
    change realm_name depends on the user token for further ops
"""

KEYCLOAK_HEALTH_URL = f"{settings.KC_SERVER_URI}/realms/{settings.KC_REALM_NAME}/.well-known/openid-configuration"

kc_realm = KeycloakAdmin(
    server_url=settings.KC_SERVER_URI,
    client_id=settings.KC_CLIENT_ID,
    client_secret_key=settings.KC_CLIENT_SECRET,
    realm_name=settings.KC_REALM_NAME,
)


kc_auth = KeycloakOpenID(
    client_id=settings.KC_CLIENT_ID,
    client_secret_key=settings.KC_CLIENT_SECRET,
    realm_name=settings.KC_REALM_NAME,
    server_url=settings.KC_SERVER_URI,
    verify=True,
)


async def get_health_status(httpx_client: httpx.AsyncClient) -> Dict[str, str]:
    """Check keycloak connection health."""
    try:
        response = await httpx_client.get(KEYCLOAK_HEALTH_URL)
        server_info = await kc_realm.a_get_server_info()

        if response.status_code == 200:
            return {
                "status": "ok",
                "keycloak": "up",
                "version": server_info.get("systemInfo", {}).get("version", "unknown"),
            }
        else:
            return {
                "status": "degraded",
                "keycloak": f"unexpected status {response.status_code}",
            }
    except Exception as e:
        return {"status": "degraded", "keycloak": f"error {str(e)}"}
