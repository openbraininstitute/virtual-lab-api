import pytest
from pydantic import ValidationError

from virtual_labs.infrastructure.settings import Settings


@pytest.mark.parametrize(
    "name",
    ["SENTRY_TRACES_SAMPLE_RATE", "SENTRY_PROFILE_SESSION_SAMPLE_RATE"],
)
@pytest.mark.parametrize("value", [-0.1, 1.1])
def test_settings_invalid_sentry_sample_rate(name: str, value: float) -> None:
    with pytest.raises(ValidationError, match=name):
        Settings.model_validate({name: value})
