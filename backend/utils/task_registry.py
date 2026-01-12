from __future__ import annotations
import asyncio
import uuid
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Callable, Any

from models.jobs import JobCreateRequest, JobStatus, JobResult

@dataclass
class _Job:
    job_id: str
    req: JobCreateRequest
    status: str = "queued"
    progress: int = 0
    stage: str = ""
    message: str = ""
    result: Optional[JobResult] = None
    error: Optional[str] = None
    created_at: float = field(default_factory=lambda: time.time())
    task: Optional[asyncio.Task] = None

class TaskRegistry:
    def __init__(self):
        self._jobs: Dict[str, _Job] = {}
        self._lock = asyncio.Lock()
        self._subscribers: set[asyncio.Queue] = set()

    async def create(self, req: JobCreateRequest) -> str:
        async with self._lock:
            job_id = str(uuid.uuid4())
            self._jobs[job_id] = _Job(job_id=job_id, req=req)
            await self._emit(job_id)
            return job_id

    async def start(self, job_id: str, coro_factory: Callable[[], Any]) -> None:
        async with self._lock:
            job = self._jobs[job_id]
            job.status = "running"
            job.progress = 1
            job.stage = "start"
            job.message = "Запуск"
            await self._emit(job_id)
            job.task = asyncio.create_task(self._runner(job_id, coro_factory))

    async def _runner(self, job_id: str, coro_factory: Callable[[], Any]) -> None:
        try:
            await coro_factory()
            await self.set_completed(job_id)
        except asyncio.CancelledError:
            await self.set_cancelled(job_id)
            raise
        except Exception as e:
            await self.set_failed(job_id, str(e))

    async def update(self, job_id: str, *, progress: Optional[int] = None, stage: Optional[str] = None, message: Optional[str] = None, result: Optional[JobResult] = None) -> None:
        async with self._lock:
            job = self._jobs[job_id]
            if progress is not None:
                job.progress = max(0, min(100, int(progress)))
            if stage is not None:
                job.stage = stage
            if message is not None:
                job.message = message
            if result is not None:
                job.result = result
            await self._emit(job_id)

    async def set_completed(self, job_id: str) -> None:
        async with self._lock:
            job = self._jobs[job_id]
            job.status = "completed"
            job.progress = 100
            job.stage = "done"
            job.message = "Готово"
            await self._emit(job_id)

    async def set_failed(self, job_id: str, error: str) -> None:
        async with self._lock:
            job = self._jobs[job_id]
            job.status = "failed"
            job.error = error
            job.progress = 100
            job.stage = "error"
            job.message = "Ошибка"
            await self._emit(job_id)

    async def set_cancelled(self, job_id: str) -> None:
        async with self._lock:
            job = self._jobs[job_id]
            job.status = "cancelled"
            job.progress = 100
            job.stage = "cancelled"
            job.message = "Отменено"
            await self._emit(job_id)

    async def cancel(self, job_id: str) -> None:
        async with self._lock:
            job = self._jobs[job_id]
            if job.task and not job.task.done():
                job.task.cancel()

    async def get(self, job_id: str) -> JobStatus:
        async with self._lock:
            return self._to_status(self._jobs[job_id])

    async def list(self) -> list[JobStatus]:
        async with self._lock:
            jobs = list(self._jobs.values())
            jobs.sort(key=lambda j: j.created_at, reverse=True)
            return [self._to_status(j) for j in jobs]

    async def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        async with self._lock:
            self._subscribers.add(q)
        return q

    async def unsubscribe(self, q: asyncio.Queue) -> None:
        async with self._lock:
            self._subscribers.discard(q)

    async def _emit(self, job_id: str) -> None:
        dead = []
        for q in list(self._subscribers):
            try:
                q.put_nowait(job_id)
            except Exception:
                dead.append(q)
        for q in dead:
            self._subscribers.discard(q)

    def _to_status(self, j: _Job) -> JobStatus:
        return JobStatus(
            job_id=j.job_id,
            status=j.status,
            progress=j.progress,
            stage=j.stage,
            message=j.message,
            result=j.result,
            error=j.error,
        )

registry = TaskRegistry()
