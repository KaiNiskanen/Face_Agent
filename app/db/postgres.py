import asyncpg
from app.config import settings

async def create_db_pool() -> asyncpg.Pool:
    # statement_cache_size=0 is required for Supabase Transaction Pooler
    return await asyncpg.create_pool(dsn=settings.DB_URI, statement_cache_size=0)
