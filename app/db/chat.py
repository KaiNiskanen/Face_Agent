import asyncpg

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
