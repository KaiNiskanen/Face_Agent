import pytest
import jwt
import time
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings
from app.api.deps import verify_token

@pytest.fixture
def auth_client():
    # Ensure no overrides leak into auth tests
    app.dependency_overrides.clear()
    return TestClient(app)

def create_token(exp_seconds=3600, aud=None, iss=None, sub="test-user"):
    aud = aud or settings.JWT_AUDIENCE
    iss = iss or f"{settings.SUPABASE_URL}/auth/v1"
    payload = {
        "sub": sub,
        "aud": aud,
        "iss": iss,
        "exp": int(time.time()) + exp_seconds,
    }
    return jwt.encode(payload, settings.SUPABASE_JWT_SECRET, algorithm="HS256")

def test_no_token(auth_client):
    r = auth_client.post("/chat", json={})
    assert r.status_code in [401, 403]  # HTTPBearer can return 403, but sometimes 401 depending on version

def test_valid_token(auth_client):
    token = create_token()
    # Expect 422 because body is empty, proving auth passed
    r = auth_client.post("/chat", headers={"Authorization": f"Bearer {token}"}, json={})
    assert r.status_code == 422

def test_expired_token(auth_client):
    token = create_token(exp_seconds=-100)  # Exceed 30s leeway
    r = auth_client.post("/chat", headers={"Authorization": f"Bearer {token}"}, json={})
    assert r.status_code == 401

def test_wrong_audience(auth_client):
    token = create_token(aud="wrong")
    r = auth_client.post("/chat", headers={"Authorization": f"Bearer {token}"}, json={})
    assert r.status_code == 401

def test_wrong_issuer(auth_client):
    token = create_token(iss="https://wrong/iss")
    r = auth_client.post("/chat", headers={"Authorization": f"Bearer {token}"}, json={})
    assert r.status_code == 401
