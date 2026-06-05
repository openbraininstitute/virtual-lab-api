"""Maps virtual-lab `DomainError`s to the API-facing `VliError`."""

from __future__ import annotations

from http import HTTPStatus

from virtual_labs.core.exceptions.api_error import VliErrorCode
from virtual_labs.core.ledger.translator import TranslationEntry, build_translator

from .errors import (
    AccountingAccountProvisioningError,
    KeycloakGroupMembershipError,
    KeycloakGroupProvisioningError,
    OwnerAlreadyHasVirtualLabError,
    StripeCustomerProvisioningError,
    UserContextLoadError,
    UserNotAuthorizedToCreateVirtualLabError,
    VirtualLabNameAlreadyExistsError,
    VirtualLabNameConflictError,
    VirtualLabPersistenceError,
)

_EXTERNAL = TranslationEntry(
    VliErrorCode.EXTERNAL_SERVICE_ERROR, HTTPStatus.BAD_GATEWAY
)
_FORBIDDEN = TranslationEntry(VliErrorCode.FORBIDDEN_OPERATION, HTTPStatus.FORBIDDEN)
_CONFLICT = TranslationEntry(VliErrorCode.ENTITY_ALREADY_EXISTS, HTTPStatus.CONFLICT)


to_vli_error, translate_domain_errors = build_translator(
    {
        OwnerAlreadyHasVirtualLabError: _FORBIDDEN,
        VirtualLabNameAlreadyExistsError: _CONFLICT,
        VirtualLabNameConflictError: _CONFLICT,
        UserContextLoadError: TranslationEntry(
            VliErrorCode.SERVER_ERROR, HTTPStatus.INTERNAL_SERVER_ERROR
        ),
        KeycloakGroupProvisioningError: _EXTERNAL,
        KeycloakGroupMembershipError: _EXTERNAL,
        UserNotAuthorizedToCreateVirtualLabError: TranslationEntry(
            VliErrorCode.NOT_ALLOWED_OP, HTTPStatus.FORBIDDEN
        ),
        AccountingAccountProvisioningError: _EXTERNAL,
        StripeCustomerProvisioningError: _EXTERNAL,
        VirtualLabPersistenceError: TranslationEntry(
            VliErrorCode.DATABASE_ERROR, HTTPStatus.BAD_REQUEST
        ),
    }
)
