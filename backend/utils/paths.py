from pathlib import Path
import os
from fastapi import HTTPException
from settings import sandbox_root

def resolve_path(p: str) -> Path:
    # On Windows, a path like "/C:/..." should be "C:/..."
    if os.name == "nt" and p.startswith("/") and len(p) > 2 and p[1].lower() in "abcdefghijklmnopqrstuvwxyz" and p[2] == ":":
        p = p[1:]
    
    try:
        path = Path(p).expanduser().resolve()
    except Exception:
        raise HTTPException(status_code=400, detail="Некорректный путь")
    root = sandbox_root()
    if root is not None:
        try:
            path.relative_to(root)
        except Exception:
            raise HTTPException(status_code=403, detail="Путь вне песочницы")
    return path
