from keycloak import KeycloakAdmin  # type: ignore

from virtual_labs.infrastructure.settings import settings

"""
    will have many realms 
    so for every realm we should configure another instance of connection
    or we should have service account and then use the credentials for every realm
    change realm_name depends on the user token for further ops
"""
masterRealmAdmin = KeycloakAdmin(
    server_url=settings.KC_SERVER_URI,
    username=settings.KC_USER_NAME,
    password=settings.KC_PASSWORD,
    realm_name="master",
)


def get_realm_pool(realm: str) -> KeycloakAdmin | None:
    if realm == "master":
        return masterRealmAdmin
    return None
