"""Gates and tagging shared by every `/admin` endpoint.

Two authorization tiers, both scoped to the `virtual-lab-svc`
Keycloak service:

  * ``platform_read`` — admin **or** maintainer; the baseline applied
    to the whole namespace (list/inspect endpoints).
  * ``platform_admin`` — admin only; added per-route on every mutation.

Roles are independent Keycloak groups (`admin` does not imply
`maintainer`), hence the explicit role set on the read gate.
"""

from virtual_labs.core.gate.service import ServiceGate
from virtual_labs.infrastructure.settings import settings

# `custom_openapi` hides every operation whose tag starts with this
# prefix from the production schema. Subrouters must build their tag
# from the constant so a new router cannot silently leak into prod.
PLATFORM_ADMIN_TAG_PREFIX = "Platform Admin"

platform_read = ServiceGate(settings.VLAB_SERVICE_NAME, role=("admin", "maintainer"))
platform_admin = ServiceGate(settings.VLAB_SERVICE_NAME)
