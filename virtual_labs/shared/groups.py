"""Keycloak group path constants, sourced from application settings."""

from virtual_labs.infrastructure.settings import settings

VLAB_SERVICE_ADMIN_GROUP: str = settings.VLAB_SERVICE_ADMIN_GROUP
VLAB_SERVICE_MAINTAINER_GROUP: str = settings.VLAB_SERVICE_MAINTAINER_GROUP
ENTITYCORE_SERVICE_ADMIN_GROUP: str = settings.ENTITYCORE_SERVICE_ADMIN_GROUP
