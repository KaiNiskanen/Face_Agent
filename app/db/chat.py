import asyncpg
from typing import List
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage

async def verify_project_ownership(conn: asyncpg.Connection, project_id: str, user_id: str) -> bool:
    row = await conn.fetchrow(
        "SELECT 1 FROM public.projects WHERE id = $1 AND user_id = $2 LIMIT 1",
        project_id, user_id
    )
    return row is not None

async def add_user_message(conn: asyncpg.Connection, project_id: str, user_id: str, content: str) -> None:
    await conn.execute(
        "INSERT INTO public.project_chat_messages (project_id, user_id, role, content) VALUES ($1, $2, 'user', $3)",
        project_id, user_id, content
    )

async def get_messages(conn: asyncpg.Connection, project_id: str, limit: int = 50) -> List[BaseMessage]:
    """
    Read the most recent N messages (roles: user/assistant) and return them oldest -> newest.
    System prompt is injected in-memory and is never read from Postgres.
    """
    rows = await conn.fetch(
        """
        SELECT role, content
        FROM public.project_chat_messages
        WHERE project_id = $1 AND role IN ('user', 'assistant')
        ORDER BY id DESC
        LIMIT $2
        """,
        project_id,
        limit,
    )

    messages: List[BaseMessage] = []
    # Reverse so callers get chronological order for model context.
    for row in reversed(rows):
        role = row["role"]
        content = row["content"]
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            messages.append(AIMessage(content=content))
    return messages

async def add_assistant_message(conn: asyncpg.Connection, project_id: str, content: str) -> None:
    """Persist assistant response. user_id is NULL for assistant rows."""
    await conn.execute(
        "INSERT INTO public.project_chat_messages (project_id, user_id, role, content) VALUES ($1, NULL, 'assistant', $2)",
        project_id,
        content,
    )
