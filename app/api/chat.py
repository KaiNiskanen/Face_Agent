import time
import asyncio
import uuid
import asyncpg
from typing import AsyncGenerator
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from app.logging import get_logger
from app.api.models import ChatRequest, sse_event
from app.config import settings
from app.api.deps import verify_token
from app.db.chat import add_user_message, add_assistant_message, get_messages, verify_project_ownership
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from app.agents.face.graph import build_face_graph
from app.agents.face.state import FaceAgentState
from app.agents.face.vision import build_human_message
from app.agents.face.prompts import SYSTEM_PROMPT

router = APIRouter()
logger = get_logger("chat")

async def stream_agent(
    state: FaceAgentState,
    request_id: str,
    pool: asyncpg.Pool,
    project_id: str,
) -> AsyncGenerator[str, None]:
    start_time = time.time()
    token_count = 0
    observed_events = set()
    full_content_parts: list[str] = []
    
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
                    # Buffer tokens so we can persist the assistant message after streaming completes.
                    full_content_parts.append(content)
                    yield sse_event("token", {"content": content})
        
        # Persist assistant row only after streaming finishes (never before). If empty, write nothing.
        combined_content = "".join(full_content_parts)
        if combined_content:
            async with pool.acquire() as conn:
                await add_assistant_message(conn, project_id, combined_content)
        
        elapsed = time.time() - start_time
        
        if token_count == 0:
            logger.warning(f"[{request_id}] zero tokens streamed. Observed events: {list(observed_events)[:5]}")
            
        logger.info(f"[{request_id}] complete | elapsed={elapsed:.2f}s | tokens={token_count}")
        yield sse_event("done", {})
    except asyncio.CancelledError:
        # Treat disconnect as a stream error for persistence rules:
        # persist partial content only if any tokens were streamed; otherwise persist nothing.
        combined_content = "".join(full_content_parts)
        if combined_content:
            async def _persist() -> None:
                async with pool.acquire() as conn:
                    await add_assistant_message(conn, project_id, combined_content)

            try:
                # Shield the whole persist path (including pool.acquire) inside a cancelled task.
                await asyncio.shield(_persist())
            except Exception as db_err:
                logger.error(f"[{request_id}] failed to save partial assistant content on disconnect: {db_err}")

        logger.info(f"[{request_id}] client disconnected")
        raise
    except Exception as e:
        logger.error(f"[{request_id}] error: {e}")
        # On any stream error: persist partial content only if any tokens were streamed; otherwise persist nothing.
        combined_content = "".join(full_content_parts)
        if combined_content:
            try:
                async with pool.acquire() as conn:
                    await add_assistant_message(conn, project_id, combined_content)
            except Exception as db_err:
                logger.error(f"[{request_id}] failed to save partial assistant content on error: {db_err}")
        yield sse_event("error", {"message": str(e), "code": "stream_error"})
        yield sse_event("done", {})

@router.post("/chat")
async def chat(request: ChatRequest, req: Request, user_id: str = Depends(verify_token)):
    # No request_id field/idempotency in the API contract; request_id here is for logging only.
    
    pool = req.app.state.db_pool
    project_id_str = str(request.project_id)
    
    # Safety: ensure history is always defined in the success path.
    history = []
    
    async with pool.acquire() as conn:
        # 1. Ownership Check
        if not await verify_project_ownership(conn, project_id_str, user_id):
            raise HTTPException(status_code=403, detail="Access denied")
            
        # 2. Insert User Message
        await add_user_message(conn, project_id_str, user_id, request.chatInput)

        # 3. Fetch History (roles user/assistant only, limit 50, oldest -> newest)
        history = await get_messages(conn, project_id_str, limit=50)

    # Dedupe rule: we inserted the current user message as text-only into DB, but we want the image-aware
    # `build_human_message(...)` version in memory. Drop the last history entry only if it matches this request.
    if history and isinstance(history[-1], HumanMessage) and history[-1].content == request.chatInput:
        history.pop()

    request_id = str(uuid.uuid4())[:8]
    
    selection_count = len(request.selected_ids)
    thumb_urls_received = len(request.thumb_urls)
    thumb_urls_used = min(thumb_urls_received, 4)
    thumb_urls_dropped = thumb_urls_received - thumb_urls_used
    logger.info(
        f"[{request_id}] request | user_id={user_id} | "
        f"project_id={request.project_id} "
        f"selection_count={selection_count} "
        f"thumb_urls_received={thumb_urls_received} "
        f"thumb_urls_used={thumb_urls_used} "
        f"thumb_urls_dropped={thumb_urls_dropped}"
    )
    thumb_urls_capped = request.thumb_urls[:4]
    state: FaceAgentState = {
        # Inject SYSTEM_PROMPT in-memory only; never store it in Postgres.
        "messages": [SystemMessage(content=SYSTEM_PROMPT)] + history + [build_human_message(request.chatInput, thumb_urls_capped)],
        # FaceAgentState declares project_id as str, so keep state consistent.
        "project_id": project_id_str,
        "selected_ids": request.selected_ids,
        "thumb_urls": thumb_urls_capped,
        "selection_count": selection_count,
    }
    return StreamingResponse(
        stream_agent(state, request_id, pool, project_id_str),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
