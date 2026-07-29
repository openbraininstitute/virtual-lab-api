from http import HTTPStatus
from uuid import uuid4

import pytest

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.gate.service import ServiceGate
from virtual_labs.infrastructure.kc.grant import AuthUserGrants

SERVICE = "virtual-lab-svc"

platform_read = ServiceGate(SERVICE, role=("admin", "maintainer"))
platform_admin = ServiceGate(SERVICE)


def make_user(groups: list[str]) -> AuthUserGrants:
    return AuthUserGrants(
        sid=str(uuid4()),
        sub=str(uuid4()),
        username="tester",
        email="tester@test.com",
        email_verified=True,
        groups=groups,
    )


async def assert_denied(gate: ServiceGate, user: AuthUserGrants) -> None:
    with pytest.raises(VliError) as exc_info:
        await gate((user, "token"))
    assert exc_info.value.http_status_code == HTTPStatus.FORBIDDEN
    assert exc_info.value.error_code == VliErrorCode.NOT_ALLOWED_OP


@pytest.mark.asyncio
async def test_admin_passes_read_and_write_gates() -> None:
    user = make_user([f"/service/{SERVICE}/admin"])

    assert await platform_read((user, "token")) is user
    assert await platform_admin((user, "token")) is user


@pytest.mark.asyncio
async def test_maintainer_passes_read_gate_only() -> None:
    user = make_user([f"/service/{SERVICE}/maintainer"])

    assert await platform_read((user, "token")) is user
    await assert_denied(platform_admin, user)


@pytest.mark.asyncio
async def test_user_without_service_groups_is_denied() -> None:
    user = make_user([f"/vlab/{uuid4()}/admin", f"/proj/{uuid4()}/{uuid4()}/member"])

    await assert_denied(platform_read, user)
    await assert_denied(platform_admin, user)


@pytest.mark.asyncio
async def test_role_of_another_service_is_denied() -> None:
    user = make_user(["/service/entitycore/admin"])

    await assert_denied(platform_read, user)
    await assert_denied(platform_admin, user)


@pytest.mark.asyncio
async def test_single_role_string_form_still_works() -> None:
    gate = ServiceGate(SERVICE, role="operator")

    assert await gate((make_user([f"/service/{SERVICE}/operator"]), "token"))
    await assert_denied(gate, make_user([f"/service/{SERVICE}/admin"]))
