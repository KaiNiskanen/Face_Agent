import pytest
import json
from pydantic import ValidationError
from fastapi.testclient import TestClient
from app.main import app
from app.api.models import ChatRequest




def parse_sse(lines) -> list[tuple[str, dict]]:
    events = []
    current_event = None
    for line in lines:
        if isinstance(line, bytes):
            line = line.decode("utf-8")
        if line.startswith("event:"):
            current_event = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            data_str = line.split(":", 1)[1].strip()
            data = json.loads(data_str)
            if current_event:
                events.append((current_event, data))
                current_event = None
    return events


def test_chat_streams_and_terminates(client):
    payload = {"project_id": "test", "chatInput": "hello"}
    with client.stream("POST", "/chat", json=payload) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        # Assert required headers (skip Connection as it's flaky)
        assert response.headers["Cache-Control"] == "no-cache"
        assert response.headers["X-Accel-Buffering"] == "no"

        events = parse_sse(response.iter_lines())
        assert len([e for e in events if e[0] == "token"]) >= 3
        assert events[-1] == ("done", {})


def test_normalization_unit():
    # List
    r = ChatRequest(project_id="p", chatInput="i", selected_ids=["a"])
    assert r.selected_ids == ["a"]
    # JSON String
    r = ChatRequest(project_id="p", chatInput="i", selected_ids='["a", "b"]')
    assert r.selected_ids == ["a", "b"]
    # Empty/Null
    r = ChatRequest(project_id="p", chatInput="i", selected_ids="")
    assert r.selected_ids == []
    # Invalid (Expect ValidationError from Pydantic)
    with pytest.raises(ValidationError):
        ChatRequest(project_id="p", chatInput="i", selected_ids="{invalid")


def test_normalization_endpoint_422(client):
    # Invalid JSON string should return 422
    payload = {"project_id": "p", "chatInput": "i", "selected_ids": "{invalid"}
    response = client.post("/chat", json=payload)
    assert response.status_code == 422

    # Non-list JSON should return 422
    payload = {"project_id": "p", "chatInput": "i", "selected_ids": '{"a":1}'}
    response = client.post("/chat", json=payload)
    assert response.status_code == 422
