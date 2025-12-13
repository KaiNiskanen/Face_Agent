import operator
from typing import TypedDict, Annotated
from langchain_core.messages import BaseMessage

class FaceAgentState(TypedDict):
    messages: Annotated[list[BaseMessage], operator.add]
    project_id: str
    selected_ids: list[str]
    thumb_urls: list[str]
    selection_count: int
