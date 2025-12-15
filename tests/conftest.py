import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.api.deps import verify_token

@pytest.fixture
def client():
    # Override auth for functional tests
    app.dependency_overrides[verify_token] = lambda: "test-user-id"
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
