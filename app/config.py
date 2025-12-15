import os
from dataclasses import dataclass
from typing import List
from dotenv import load_dotenv

load_dotenv()

@dataclass
class Settings:
    MODEL_NAME: str
    # New Auth Fields
    SUPABASE_URL: str
    SUPABASE_JWT_SECRET: str
    JWT_AUDIENCE: str
    CORS_ORIGINS: List[str]

def _required(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise ValueError(f"{name} required")
    return v

def _load_settings() -> Settings:
    # Existing check
    if not os.getenv("OPENAI_API_KEY"):
        raise ValueError("OPENAI_API_KEY required")

    # New Auth Checks
    cors_origins_str = _required("CORS_ORIGINS")
    cors_origins = [o.strip() for o in cors_origins_str.split(",") if o.strip()]
    
    if "*" in cors_origins:
        raise ValueError("CORS_ORIGINS must not contain '*' when using credentials/auth")

    return Settings(
        # Existing
        MODEL_NAME=os.getenv("MODEL_NAME", "gpt-4o"),
        
        # New
        SUPABASE_URL=_required("SUPABASE_URL").rstrip("/"),
        SUPABASE_JWT_SECRET=_required("SUPABASE_JWT_SECRET"),
        JWT_AUDIENCE=os.getenv("JWT_AUDIENCE", "authenticated"),
        CORS_ORIGINS=cors_origins,
    )

settings = _load_settings()
