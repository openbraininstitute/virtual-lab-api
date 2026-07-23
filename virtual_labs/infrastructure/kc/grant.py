"""User membership grants derived from Keycloak group paths.

Keycloak emits group memberships as path strings:

    /vlab/{vlab_id}/{role}                       # role ∈ {admin, member}
    /proj/{vlab_id}/{project_id}/{role}          # role ∈ {admin, member}
    /service/{service_name}/{role}               # role is service-specific

`Grants` is an immutable per-request view that lets call sites do
membership checks without re-querying Keycloak:

    auth.grants.virtual_labs.admin                # frozenset[UUID]
    auth.grants.virtual_labs.member               # frozenset[UUID]
    auth.grants.virtual_labs.all                  # admin ∪ member
    auth.grants.virtual_labs.is_admin(vlab_id)    # bool

    auth.grants.projects.admin                    # frozenset[UUID]
    auth.grants.projects.is_member(project_id)    # bool
    auth.grants.projects.role_for(project_id)     # "admin" | "member" | None

    auth.grants.services.admin                    # frozenset[str]
    auth.grants.services.has("entitycore")        # bool — default role=admin
    auth.grants.services.has("entitycore", "x")   # bool — explicit role

The structure is populated from the `groups` claim (when a Keycloak
client-scope mapper exists for it) or from a `/userinfo` round-trip.
When no groups are available, `Grants.empty()` returns a fully-empty
view — every `is_admin` / `is_member` check returns `False` safely.
This makes the grants surface safe to read unconditionally; callers
that need it can adopt incrementally.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from dataclasses import dataclass, field
from functools import cached_property
from http import HTTPStatus
from typing import Any, Literal, cast
from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials
from keycloak import KeycloakError  # type: ignore[import-untyped]
from loguru import logger
from pydantic import ConfigDict

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.infrastructure.kc.auth import auth_header
from virtual_labs.infrastructure.kc.config import kc_auth
from virtual_labs.infrastructure.kc.models import AuthUser

ResourceRole = Literal["admin", "member", "waitlisted"]


@dataclass(frozen=True, slots=True)
class ResourceGrants:
    """Admin / member sets for a resource keyed by UUID (vlab or project)."""

    admin: frozenset[UUID] = frozenset()
    member: frozenset[UUID] = frozenset()

    @property
    def all(self) -> frozenset[UUID]:
        return self.admin | self.member

    def is_admin(self, resource_id: UUID) -> bool:
        return resource_id in self.admin

    def is_member(self, resource_id: UUID) -> bool:
        return resource_id in self.member

    def has_access(self, resource_id: UUID) -> bool:
        return resource_id in self.admin or resource_id in self.member

    def role_for(self, resource_id: UUID) -> ResourceRole | None:
        if resource_id in self.admin:
            return "admin"
        if resource_id in self.member:
            return "member"
        return None


@dataclass(frozen=True, slots=True)
class ProjectGrants(ResourceGrants):
    """Project memberships with a back-reference to each project's
    parent vlab.

    The vlab portion of the project group path
    (`/proj/{vlab_id}/{project_id}/{role}`) is captured here so that
    authorization rules like "a vlab admin may access every project
    in their vlab" can be expressed without a DB round-trip.
    """

    waitlisted: frozenset[UUID] = frozenset()
    _vlab_by_project: dict[UUID, UUID] = field(default_factory=dict)

    @property
    def all(self) -> frozenset[UUID]:
        return self.admin | self.member | self.waitlisted

    def vlab_of(self, project_id: UUID) -> UUID | None:
        """Return the vlab id this project belongs to, when known."""
        return self._vlab_by_project.get(project_id)


@dataclass(frozen=True, slots=True)
class ServiceGrants:
    """Service-name keyed grants. Services may use arbitrary role names,
    so we expose the well-known admin/member shortcuts and a generic
    `has(service, role)` for everything else."""

    admin: frozenset[str] = frozenset()
    member: frozenset[str] = frozenset()
    _roles_by_service: dict[str, frozenset[str]] = field(default_factory=dict)

    @property
    def all(self) -> frozenset[str]:
        """All service names the user has any role in."""
        return frozenset(self._roles_by_service)

    def is_admin(self, service: str) -> bool:
        return service in self.admin

    def is_member(self, service: str) -> bool:
        return service in self.member

    def roles_for(self, service: str) -> frozenset[str]:
        return self._roles_by_service.get(service, frozenset())

    def has(self, service: str, role: str = "admin") -> bool:
        return role in self._roles_by_service.get(service, frozenset())


@dataclass(frozen=True, slots=True)
class Grants:
    virtual_labs: ResourceGrants = field(default_factory=ResourceGrants)
    projects: ProjectGrants = field(default_factory=ProjectGrants)
    services: ServiceGrants = field(default_factory=ServiceGrants)

    @classmethod
    def empty(cls) -> Grants:
        return cls()

    @classmethod
    def from_groups(cls, groups: Iterable[str] | None) -> Grants:
        """Parse Keycloak group paths into a `Grants` instance.

        Unknown path shapes, malformed UUIDs, and unknown roles are
        silently skipped. The caller is never asked to handle parser
        failures — Keycloak group naming is config-driven and we don't
        want a single odd path to break authentication."""
        if not groups:
            return cls()
        return _build_grants(groups)


def _build_grants(groups: Iterable[str]) -> Grants:
    vlab_admin: set[UUID] = set()
    vlab_member: set[UUID] = set()
    proj_admin: set[UUID] = set()
    proj_member: set[UUID] = set()
    proj_waitlisted: set[UUID] = set()
    proj_vlab: dict[UUID, UUID] = {}
    svc_admin: set[str] = set()
    svc_member: set[str] = set()
    svc_roles: dict[str, set[str]] = {}

    for raw in groups:
        parts = raw.strip("/").split("/")
        match parts:
            case ["vlab", vid, role]:
                rid = _parse_uuid(vid)
                if rid is None:
                    continue
                if role == "admin":
                    vlab_admin.add(rid)
                elif role == "member":
                    vlab_member.add(rid)

            case ["proj", vlab_part, pid, role]:
                pid_uuid = _parse_uuid(pid)
                if pid_uuid is None:
                    continue
                vid_uuid = _parse_uuid(vlab_part)
                if vid_uuid is not None:
                    proj_vlab[pid_uuid] = vid_uuid
                if role == "admin":
                    proj_admin.add(pid_uuid)
                elif role == "member":
                    proj_member.add(pid_uuid)
                elif role == "waitlisted":
                    proj_waitlisted.add(pid_uuid)

            case ["service", svc_name, role]:
                svc_roles.setdefault(svc_name, set()).add(role)
                if role == "admin":
                    svc_admin.add(svc_name)
                elif role == "member":
                    svc_member.add(svc_name)

            case _:
                # Unknown shape — skip rather than fail authentication.
                continue

    return Grants(
        virtual_labs=ResourceGrants(
            admin=frozenset(vlab_admin),
            member=frozenset(vlab_member),
        ),
        projects=ProjectGrants(
            admin=frozenset(proj_admin),
            member=frozenset(proj_member),
            waitlisted=frozenset(proj_waitlisted),
            _vlab_by_project=proj_vlab,
        ),
        services=ServiceGrants(
            admin=frozenset(svc_admin),
            member=frozenset(svc_member),
            _roles_by_service={k: frozenset(v) for k, v in svc_roles.items()},
        ),
    )


def _parse_uuid(value: str) -> UUID | None:
    try:
        return UUID(value)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Auth payload that carries grants
# ---------------------------------------------------------------------------


class AuthUserGrants(AuthUser):
    """`AuthUser` extended with Keycloak group memberships.

    Lives alongside the legacy `AuthUser` so existing dependencies and
    routes are untouched. New endpoints that want structured
    authorization opt in by depending on an auth function that returns
    this subclass — typically one that has fetched the `/userinfo`
    payload (or read a `groups` JWT claim once the realm has the
    mapper configured) and passed `groups=...` here.

    Since this subclasses `AuthUser`, every consumer that accepts an
    `AuthUser` accepts an `AuthUserGrants` too. The reverse is not
    true: only code that explicitly depends on `AuthUserGrants` can
    read `.grants`.
    """

    groups: list[str] = []

    # Pydantic v2 treats `cached_property` as a field unless told
    # otherwise; `ignored_types` keeps it a normal descriptor with
    # per-instance caching.
    model_config = ConfigDict(
        populate_by_name=True,
        ignored_types=(cached_property,),
    )

    @cached_property
    def grants(self) -> Grants:
        """Structured view of group memberships.

        Safe to read even when `groups` is empty — returns
        `Grants.empty()` rather than raising.
        """
        return Grants.from_groups(self.groups)

    @cached_property
    def id(self) -> UUID:
        """The Keycloak `sub` claim parsed as a UUID.

        Raises `ValueError` only if the token's `sub` is not a UUID,
        which would indicate a misconfigured realm — never expected at
        runtime.
        """
        return UUID(self.sub)

    @cached_property
    def full_name(self) -> str:
        """Best-effort full name; falls back to `username` when the
        `name` claim is missing (matches the KC mapper convention
        where `name = given_name + " " + family_name`)."""
        return self.name or self.username

    # NB: no `email` override here — `email` is a real Pydantic field on
    # `AuthUser`, stored in the instance `__dict__`. Since `cached_property`
    # is a non-data descriptor, the field value always wins on attribute
    # lookup, so a `cached_property def email` would be dead code (and
    # `return self.email` inside it would be infinite recursion if it ever
    # fired). Read `self.email` directly.

    def in_group(self, group_path: str) -> bool:
        """Raw Keycloak group-path membership check.

        Accepts either the canonical form (`/vlab/.../admin`) or the
        no-leading-slash form. Use this when you need to check a
        custom group shape that the structured `grants` view does not
        model (ad-hoc roles, future path patterns, etc.). For the
        well-known vlab/project/service paths, prefer the typed
        helpers below.
        """
        normalized = group_path if group_path.startswith("/") else f"/{group_path}"
        return normalized in self.groups

    def is_vlab_admin(self, vlab_id: UUID) -> bool:
        return self.grants.virtual_labs.is_admin(vlab_id)

    def is_vlab_member(self, vlab_id: UUID) -> bool:
        return self.grants.virtual_labs.is_member(vlab_id)

    def has_vlab_access(self, vlab_id: UUID) -> bool:
        """True if the user is admin *or* member of the vlab."""
        return self.grants.virtual_labs.has_access(vlab_id)

    def is_project_admin(self, project_id: UUID) -> bool:
        return self.grants.projects.is_admin(project_id)

    def is_project_member(self, project_id: UUID) -> bool:
        return self.grants.projects.is_member(project_id)

    def has_project_access(self, project_id: UUID) -> bool:
        return self.grants.projects.has_access(project_id)

    def vlab_of_project(self, project_id: UUID) -> UUID | None:
        """Parent vlab id of a project, taken from the JWT — None if
        the user has no membership in that project."""
        return self.grants.projects.vlab_of(project_id)

    def is_vlab_admin_of_project(self, project_id: UUID) -> bool:
        """True when the user is admin of the vlab that owns the
        project. Useful for `vlab admin → project access` rules."""
        vlab_id = self.grants.projects.vlab_of(project_id)
        return vlab_id is not None and self.is_vlab_admin(vlab_id)

    def is_service_admin(self, service: str) -> bool:
        return self.grants.services.is_admin(service)

    def has_service_role(self, service: str, role: str = "admin") -> bool:
        return self.grants.services.has(service, role)


# FastAPI dependency
async def parse_auth_grants(
    header: HTTPAuthorizationCredentials = Depends(auth_header),
) -> tuple[AuthUserGrants, str]:
    """FastAPI dependency that returns an `AuthUserGrants` for the
    current request.

    Decodes the JWT and fetches `/userinfo` from Keycloak in parallel,
    then merges the two payloads so the returned object carries every
    claim the legacy `verify_jwt` returned (sid, sub, email,
    email_verified, username, name) plus `groups` — the Keycloak
    group paths — which feeds the `.grants` view and the
    `is_vlab_admin` / `is_project_admin` / etc. helpers.

    Behaves like `a_verify_jwt` toward callers: returns a
    `(user, token)` tuple, raises `VliError(AUTHORIZATION_ERROR)` on
    any failure. Use it only on endpoints that actually need
    group-based authorization — it costs one extra round-trip to
    Keycloak (the `/userinfo` call).

    Token revocation is implicitly checked: Keycloak returns 401 from
    `/userinfo` for a revoked or inactive token, so we get the same
    safety property as the introspection call in `a_verify_jwt`
    without a separate round-trip.
    """
    if not header:
        raise VliError(
            error_code=VliErrorCode.AUTHORIZATION_ERROR,
            http_status_code=HTTPStatus.UNAUTHORIZED,
            message="No Authentication was provided",
            details="The supplied authentication is not authorized to access",
        )

    token = header.credentials

    try:
        decoded, userinfo = await asyncio.gather(
            kc_auth.a_decode_token(token=token, validate=True),
            kc_auth.a_userinfo(token=token),
        )
    except KeycloakError as exc:
        logger.error(
            "Keycloak rejected token during parse_auth_grants "
            f"(code={exc.response_code}): {exc.error_message}"
        )
        raise VliError(
            error_code=VliErrorCode.AUTHORIZATION_ERROR,
            http_status_code=exc.response_code or HTTPStatus.UNAUTHORIZED,
            message="Invalid authentication session",
            details=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception(f"Auth error in parse_auth_grants: {exc}")
        raise VliError(
            error_code=VliErrorCode.AUTHORIZATION_ERROR,
            http_status_code=HTTPStatus.UNAUTHORIZED,
            message="Invalid authentication session",
            details=str(exc),
        ) from exc

    claims = cast(dict[str, Any], decoded)
    info = cast(dict[str, Any], userinfo)
    groups = info.get("groups") or []

    claims["groups"] = list(groups)

    try:
        user = AuthUserGrants(**claims)
    except Exception as exc:
        raise VliError(
            error_code=VliErrorCode.INVALID_REQUEST,
            http_status_code=HTTPStatus.BAD_REQUEST,
            message="Generating authentication details failed",
            details=f"exc: {exc}, decoded_token: {claims}",
        ) from exc

    return user, token
