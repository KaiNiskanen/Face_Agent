from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.chat import router as chat_router

from contextlib import asynccontextmanager
from app.db.postgres import create_db_pool

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db_pool = await create_db_pool()
    yield
    await app.state.db_pool.close()

app = FastAPI(title="Face Agent", version="0.1.0", lifespan=lifespan)

from app.config import settings

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(chat_router)


@app.get("/health")
def health():
    return {"status": "ok"}
