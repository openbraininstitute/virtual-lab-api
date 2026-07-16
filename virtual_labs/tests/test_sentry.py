import pytest
import sentry_sdk

from virtual_labs.infrastructure.sentry import init_sentry
from virtual_labs.infrastructure.settings import settings


def test_init_sentry(monkeypatch: pytest.MonkeyPatch) -> None:
    # with release=None the SDK falls back to auto-detecting the git SHA
    monkeypatch.setattr(settings, "APP_VERSION", "1.2.3")

    init_sentry()

    client = sentry_sdk.get_client()
    assert client.is_active()
    assert client.transport is None  # without a DSN nothing is sent
    assert client.options["environment"] == settings.DEPLOYMENT_ENV
    assert client.options["release"] == "1.2.3"
    assert client.options["traces_sample_rate"] == settings.SENTRY_TRACES_SAMPLE_RATE
    assert (
        client.options["profile_session_sample_rate"]
        == settings.SENTRY_PROFILE_SESSION_SAMPLE_RATE
    )
    assert client.options["profile_lifecycle"] == "trace"
