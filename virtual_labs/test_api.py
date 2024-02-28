from fastapi.testclient import TestClient
from .api import app

client = TestClient(app)


def test_dummy_root():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"msg": "Virtual Labs API"}
