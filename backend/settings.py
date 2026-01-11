from pydantic import BaseModel
from pathlib import Path
import os

class Settings(BaseModel):
    SANDBOX_ROOT: str = os.getenv("SANDBOX_ROOT", "")
    PREVIEW_CACHE_MAX_ITEMS: int = int(os.getenv("PREVIEW_CACHE_MAX_ITEMS", "256"))
    MAX_UPLOAD_MB: int = int(os.getenv("MAX_UPLOAD_MB", "200"))

settings = Settings()

def sandbox_root() -> Path | None:
    if not settings.SANDBOX_ROOT.strip():
        return None
    return Path(settings.SANDBOX_ROOT).expanduser().resolve()
