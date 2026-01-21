from pydantic import BaseModel
from typing import Literal, Optional

class FsEntry(BaseModel):
    name: str
    path: str
    type: Literal["file","directory"]
    size: Optional[int] = None
    mtime: Optional[float] = None
    preview_path: Optional[str] = None

class MoveRequest(BaseModel):
    src: str
    dst: str

class CreateFoldersRequest(BaseModel):
    path: str

class UpdateCountsRequest(BaseModel):
    path: str
