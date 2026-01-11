from pathlib import Path
from fastapi import HTTPException
from settings import sandbox_root

def resolve_path(p: str) -> Path:
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
