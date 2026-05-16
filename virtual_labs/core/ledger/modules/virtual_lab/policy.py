"""Creation policies for virtual labs.

* It specifies whether owner uniqueness must be enforced
* It determines the welcome bonus amount to grant
* It controls whether post-commit side effects should run:
    * setting Keycloak custom properties
    * sending the welcome email
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from virtual_labs.infrastructure.settings import settings


def _welcome_bonus_credits() -> Decimal:
    return (
        settings.WELCOME_BONUS_CREDITS if settings.ENABLE_WELCOME_BONUS else Decimal(0)
    )


@dataclass(frozen=True, slots=True)
class VirtualLabCreationPolicy:
    enforce_single_workspace: bool
    welcome_bonus: Decimal
    enable_billing: (
        bool  # provision Stripe customer + stage StripeUser + insert free subscription
    )
    run_post_commit_actions: bool


REGULAR_LAB_POLICY = VirtualLabCreationPolicy(
    enforce_single_workspace=True,
    welcome_bonus=_welcome_bonus_credits(),
    enable_billing=True,
    run_post_commit_actions=True,
)


COURSE_LAB_POLICY = VirtualLabCreationPolicy(
    enforce_single_workspace=False,
    welcome_bonus=Decimal(0),
    enable_billing=False,
    run_post_commit_actions=False,
)
