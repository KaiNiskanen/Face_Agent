import os
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.api.models import ChatRequest

@pytest.fixture
def client():
    return TestClient(app)

def parse_sse(lines) -> list[tuple[str, dict]]:
    import json
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

@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set")
def test_integration_openai_streaming(client):
    """
    Integration test that hits the real OpenAI API to verify LangGraph streaming.
    This ensures that the event names (on_chat_model_stream) haven't changed
    and that the graph is actually wired up correctly.
    """
    payload = {
        "project_id": "integration_test",
        "chatInput": "Say 'test' and nothing else.",
        "selected_ids": [],
        "thumb_urls": []
    }
    
    with client.stream("POST", "/chat", json=payload) as response:
        assert response.status_code == 200
        events = parse_sse(response.iter_lines())
        
        # Filter for token events
        tokens = [e[1]["content"] for e in events if e[0] == "token"]
        
        # We expect at least one token. 
        # OpenAI might return "Test" or "test" or "Test."
        assert len(tokens) > 0, "No tokens received from OpenAI stream"
        
        # Verify we got a done event
        assert events[-1][0] == "done"
