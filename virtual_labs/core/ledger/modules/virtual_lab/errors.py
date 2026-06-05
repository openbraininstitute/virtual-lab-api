"""Domain errors for the create-virtual-lab use case.

each subclass declares the subset of `context` keys that are safe to
echo back to clients via `safe_context`
"""

from __future__ import annotations

from virtual_labs.core.ledger import DomainError


# pre-check failures
class OwnerAlreadyHasVirtualLabError(DomainError):
    description = "The user already owns a virtual lab and cannot create another."
    safe_context = frozenset({"owner_id"})


class VirtualLabNameAlreadyExistsError(DomainError):
    description = "A virtual lab with this name already exists."
    safe_context = frozenset({"name"})


# preflight
class UserContextLoadError(DomainError):
    description = "Could not load the user's identity from the auth provider."
    safe_context = frozenset({"owner_id"})


# external provisioning
class KeycloakGroupProvisioningError(DomainError):
    description = "Failed to create the admin/member groups in the auth provider."


class KeycloakGroupMembershipError(DomainError):
    description = "Failed to attach the owner to the admin group."


class UserNotAuthorizedToCreateVirtualLabError(DomainError):
    description = "The user is not authorized to create a virtual lab."
    safe_context = frozenset({"owner_id"})


class AccountingAccountProvisioningError(DomainError):
    description = "Failed to create the accounting account for the virtual lab."


class StripeCustomerProvisioningError(DomainError):
    description = "Failed to register the user with the payment provider."


# persistence
class VirtualLabPersistenceError(DomainError):
    description = "The virtual lab could not be saved to the database."


class VirtualLabNameConflictError(DomainError):
    description = "A virtual lab with this name was created concurrently."
    safe_context = frozenset({"name"})
