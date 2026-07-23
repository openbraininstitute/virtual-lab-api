"""Platform-admin (`/admin`) namespace.

Every subrouter is included behind the `platform_read` gate — admin
**or** maintainer role in the `virtual-lab-svc` Keycloak service.
Mutating routes additionally declare `Depends(platform_admin)`
(admin only) themselves. `parse_auth_grants` is dependency-cached per
request, so the stacked gates cost a single Keycloak round-trip.

All tags are built from `deps.PLATFORM_ADMIN_TAG_PREFIX` —
`custom_openapi` matches on the same constant to hide the namespace
from the production schema. The pre-existing `/admin/promotions`
router lives in `routes/promotions.py` and keeps its own legacy
gating.
"""

from fastapi import APIRouter, Depends

from virtual_labs.routes.admin.deps import platform_read
from virtual_labs.routes.admin.labs import router as labs_router
from virtual_labs.routes.admin.payments import router as payments_router
from virtual_labs.routes.admin.plans import router as plans_router
from virtual_labs.routes.admin.projects import router as projects_router
from virtual_labs.routes.admin.subscriptions import router as subscriptions_router
from virtual_labs.routes.admin.users import router as users_router

router = APIRouter(prefix="/admin", dependencies=[Depends(platform_read)])

router.include_router(labs_router)
router.include_router(projects_router)
router.include_router(users_router)
router.include_router(subscriptions_router)
router.include_router(payments_router)
router.include_router(plans_router)
