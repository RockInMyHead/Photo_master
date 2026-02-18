from pydantic import BaseModel
from pathlib import Path
import os
from typing import Optional

class Settings(BaseModel):
    SANDBOX_ROOT: str = os.getenv("SANDBOX_ROOT", "")
    PREVIEW_CACHE_MAX_ITEMS: int = int(os.getenv("PREVIEW_CACHE_MAX_ITEMS", "256"))
    MAX_UPLOAD_MB: int = int(os.getenv("MAX_UPLOAD_MB", "200"))
    # Immich settings (optional, can be overridden in request)
    IMMICH_URL: Optional[str] = os.getenv("IMMICH_URL", None)
    IMMICH_API_KEY: Optional[str] = os.getenv("IMMICH_API_KEY", None)

settings = Settings()

def sandbox_root() -> Optional[Path]:
    if not settings.SANDBOX_ROOT.strip():
        return None
    return Path(settings.SANDBOX_ROOT).expanduser().resolve()
