from pydantic import BaseModel
from typing import Literal

class FsEntry(BaseModel):
    name: str
    path: str
    type: Literal["file","directory"]
    size: int | None = None
    mtime: float | None = None
    preview_path: str | None = None

class MoveRequest(BaseModel):
    src: str
    dst: str
