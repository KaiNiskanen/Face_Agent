import time
import asyncio
import uuid
from typing import AsyncGenerator
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from app.logging import get_logger
from app.api.models import ChatRequest, sse_event
from app.config import settings
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage

from app.agents.face.graph import build_face_graph
from app.agents.face.state import FaceAgentState
from app.agents.face.vision import build_human_message
from app.agents.face.prompts import SYSTEM_PROMPT

router = APIRouter()
logger = get_logger("chat")

async def stream_agent(state: FaceAgentState, request_id: str) -> AsyncGenerator[str, None]:
    start_time = time.time()
    token_count = 0
    observed_events = set()
    
    try:
        llm = ChatOpenAI(model=settings.MODEL_NAME, streaming=True)
        graph = build_face_graph(llm)
        
        stream_events = {"on_chat_model_stream", "on_llm_stream"}
        
        async for event in graph.astream_events(state, version="v2"):
            kind = event.get("event")
            if kind:
                observed_events.add(kind)
                
            if kind in stream_events:
                chunk = event.get("data", {}).get("chunk")
                # Safe content coercion
                content = chunk.content if chunk and hasattr(chunk, "content") and isinstance(chunk.content, str) else ""
                
                if content:
                    token_count += 1
                    yield sse_event("token", {"content": content})
        
        elapsed = time.time() - start_time
        
        if token_count == 0:
            logger.warning(f"[{request_id}] zero tokens streamed. Observed events: {list(observed_events)[:5]}")
            
        logger.info(f"[{request_id}] complete | elapsed={elapsed:.2f}s | tokens={token_count}")
        yield sse_event("done", {})
    except asyncio.CancelledError:
        logger.info(f"[{request_id}] client disconnected")
        return
    except Exception as e:
        logger.error(f"[{request_id}] error: {e}")
        yield sse_event("error", {"message": str(e), "code": "stream_error"})
        yield sse_event("done", {})

@router.post("/chat")
async def chat(request: ChatRequest):
    request_id = str(uuid.uuid4())[:8]
    
    selection_count = len(request.selected_ids)
    thumb_urls_received = len(request.thumb_urls)
    thumb_urls_used = min(thumb_urls_received, 4)
    thumb_urls_dropped = thumb_urls_received - thumb_urls_used
    logger.info(
        f"[{request_id}] request | "
        f"project_id={request.project_id} "
        f"selection_count={selection_count} "
        f"thumb_urls_received={thumb_urls_received} "
        f"thumb_urls_used={thumb_urls_used} "
        f"thumb_urls_dropped={thumb_urls_dropped}"
    )
    thumb_urls_capped = request.thumb_urls[:4]
    state: FaceAgentState = {
        "messages": [
            SystemMessage(content=SYSTEM_PROMPT),
            build_human_message(request.chatInput, thumb_urls_capped)
        ],
        "project_id": request.project_id,
        "selected_ids": request.selected_ids,
        "thumb_urls": thumb_urls_capped,
        "selection_count": selection_count,
    }
    return StreamingResponse(
        stream_agent(state, request_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
