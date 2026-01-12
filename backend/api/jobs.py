from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
import asyncio
import json

from models.jobs import JobCreateRequest, JobStatus, JobResult
from utils.task_registry import registry
from utils.paths import resolve_path
from core.pipeline import process_folder

router = APIRouter()

@router.post("/", response_model=JobStatus)
async def create_job(req: JobCreateRequest):
    folder = resolve_path(req.path)
    if not folder.exists() or not folder.is_dir():
        raise HTTPException(status_code=404, detail="Папка не найдена")

    job_id = await registry.create(req)

    async def runner():
        def progress(pct: int, msg: str):
            # гарантируем постановку update в очередь event loop
            asyncio.get_running_loop().create_task(
                registry.update(job_id, progress=pct, stage="run", message=msg)
            )

        result_dict = await process_folder(folder, joint_mode=req.jointMode, singletons=True, progress=progress)
        await registry.update(job_id, result=JobResult(**result_dict), stage="done", message="Готово")

    await registry.start(job_id, runner)
    return await registry.get(job_id)

@router.get("/", response_model=list[JobStatus])
async def list_jobs():
    return await registry.list()

@router.get("/stream")
async def stream():
    # Always create a subscription for EventSource
    try:
        q = await registry.subscribe()
    except Exception as e:
        # If subscription fails for some reason, create a dummy queue
        q = asyncio.Queue(maxsize=200)
        print(f"SSE: Created dummy queue due to error: {e}")

    async def gen():
        try:
            # Send initial ping
            yield "event: ping\ndata: {}\n\n"
            while True:
                try:
                    # Wait for job updates with timeout
                    job_id = await asyncio.wait_for(q.get(), timeout=30.0)
                    payload = json.dumps({"job_id": job_id}, ensure_ascii=False)
                    print(f"SSE: Sending update for job {job_id}")
                    yield f"event: update\ndata: {payload}\n\n"
                except asyncio.TimeoutError:
                    # Send periodic ping to keep connection alive
                    yield "event: ping\ndata: {}\n\n"
                except Exception as e:
                    print(f"SSE: Error in message loop: {e}")
                    break
        except Exception as e:
            print(f"SSE error: {e}")
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
        finally:
            try:
                await registry.unsubscribe(q)
            except:
                pass

    response = StreamingResponse(gen(), media_type="text/event-stream")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["Connection"] = "keep-alive"
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET"
    return response

@router.get("/{job_id}", response_model=JobStatus)
async def get_job(job_id: str):
    try:
        return await registry.get(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Задача не найдена")

@router.post("/{job_id}/cancel")
async def cancel_job(job_id: str):
    await registry.cancel(job_id)
    return {"ok": True}
