import json
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, field_validator
from uuid import UUID


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    project_id: UUID
    chatInput: str
    selected_ids: list[str] = Field(default_factory=list)
    thumb_urls: list[str] = Field(default_factory=list)

    @field_validator("selected_ids", "thumb_urls", mode="before")
    @classmethod
    def normalize_list(cls, v: Any) -> list[str]:
        if v is None or v == "":
            return []
        if isinstance(v, list):
            return [str(x) for x in v]
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
            except json.JSONDecodeError:
                raise ValueError("Invalid JSON string")
            if not isinstance(parsed, list):
                raise ValueError("Expected JSON list")
            return [str(x) for x in parsed]
        raise ValueError("Expected list or JSON-string list")


def sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"
