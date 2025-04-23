from enum import Enum
from typing import Any, Optional

from virtual_labs.infrastructure.db.models import SubscriptionTierEnum


def parse_subscription_tier(value: str) -> Optional[SubscriptionTierEnum]:
    try:
        return SubscriptionTierEnum(value.lower())
    except ValueError:
        return None


# Assuming `subscription_type` might be an enum or a string
def resolve_tier(subscription_type: Any) -> Optional[SubscriptionTierEnum]:
    value = (
        subscription_type.value
        if isinstance(subscription_type, Enum)
        else str(subscription_type)
    )
    return parse_subscription_tier(value)
