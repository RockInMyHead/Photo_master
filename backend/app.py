from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api import fs, jobs

app = FastAPI(title="Photo Face Sorter API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def no_store_api(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response

app.include_router(fs.router, prefix="/api/fs", tags=["fs"])
app.include_router(jobs.router, prefix="/api/jobs", tags=["jobs"])

@app.get("/api/health")
def health():
    return {"ok": True}
