import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass
class Settings:
    MODEL_NAME: str

def _load_settings() -> Settings:
    if not os.getenv("OPENAI_API_KEY"):
        raise ValueError("OPENAI_API_KEY required")
    return Settings(MODEL_NAME=os.getenv("MODEL_NAME", "gpt-4o"))

settings = _load_settings()
