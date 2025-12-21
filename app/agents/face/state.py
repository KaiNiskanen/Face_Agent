import operator
from typing import Annotated, NotRequired
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage

class FaceAgentState(TypedDict):
    messages: Annotated[list[BaseMessage], operator.add]
    project_id: str
    selected_ids: list[str]
    thumb_urls: list[str]
    selection_count: int

    # Bundle A: optional server-owned context. Kept optional to avoid breaking state construction sites.
    requested_aspect: NotRequired[str | None]
    # Bundle A: optional client-provided model (accepted from JSON key "model" via alias in ChatRequest).
    client_model: NotRequired[str | None]
