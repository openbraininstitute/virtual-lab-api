import pytest
from fastapi.testclient import TestClient

from .api import app

client = TestClient(app)


@pytest.mark.skip(reason="needs mock db connection")
def test_dummy_root() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == "server is running."
