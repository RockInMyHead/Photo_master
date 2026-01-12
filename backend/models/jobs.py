from pydantic import BaseModel
from typing import Literal, Optional

class JobCreateRequest(BaseModel):
    path: str
    includeExcluded: bool = False
    jointMode: Literal["copy","combine"] = "copy"
    postValidate: bool = False

class JobResult(BaseModel):
    moved: int = 0
    copied: int = 0
    clusters: int = 0
    no_faces: int = 0
    unreadable: int = 0

class JobStatus(BaseModel):
    job_id: str
    status: Literal["queued","running","completed","failed","cancelled"]
    progress: int = 0
    stage: str = ""
    message: str = ""
    result: Optional[JobResult] = None
    error: Optional[str] = None
