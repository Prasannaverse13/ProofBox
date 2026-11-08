"""ProofBox API. Runs on the Vultr VM and owns the agent loop."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field

from . import audit, llm, policy
from .agent import run_job
from .config import settings
from .jobs import store
from .sandbox import docker_status, sweep_orphans
from .sources import list_samples

MAX_CONCURRENT = 2
_slots = asyncio.Semaphore(MAX_CONCURRENT)
_tasks: set[asyncio.Task] = set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    removed = await sweep_orphans()
    if removed:
        print(f"Removed {removed} orphan sandboxes")
    yield
    for t in _tasks:
        t.cancel()
    await sweep_orphans()


app = FastAPI(title="ProofBox", version="1.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class SourceIn(BaseModel):
    type: str = Field(pattern="^(sample|git)$")
    sample: str | None = None
    url: str | None = None


class JobIn(BaseModel):
    source: SourceIn


@app.get("/api/health")
async def health():
    return {
        "ok": True,
        "mode": "demo" if settings.demo_mode else "live",
        "model": settings.model,
        "inference": settings.inference_base_url,
        "sandbox": await docker_status(),
        "limits": {
            "network": "none",
            "memory": settings.sandbox_memory,
            "cpus": settings.sandbox_cpus,
            "pids": settings.sandbox_pids,
            "command_timeout_s": settings.command_timeout,
        },
    }


@app.get("/api/policy")
async def policy_rules():
    return {"rules": policy.describe()}


@app.get("/api/models")
async def models():
    return {"models": await llm.list_models(), "selected": settings.model}


@app.get("/api/samples")
async def samples():
    return {"samples": list_samples()}


@app.get("/api/jobs")
async def jobs():
    return {"jobs": store.recent()}


async def _runner(job):
    async with _slots:
        await run_job(job)


@app.post("/api/jobs", status_code=201)
async def create_job(body: JobIn):
    src = body.source.model_dump(exclude_none=True)
    if src["type"] == "sample" and not src.get("sample"):
        raise HTTPException(422, "sample is required")
    if src["type"] == "git" and not src.get("url"):
        raise HTTPException(422, "url is required")
    job = store.create(src)
    task = asyncio.create_task(_runner(job))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return job.public()


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    job = store.get(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    return job.public(with_events=True)


def _job_or_404(job_id: str):
    job = store.get(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    return job


@app.get("/api/jobs/{job_id}/audit")
async def job_audit(job_id: str):
    """Recompute the hash chain from the stored events and check the server signature."""
    job = _job_or_404(job_id)
    result = audit.verify_chain(job.events, job.signature or None)
    return {**result, "signature": job.signature or None, "finished": job.finished}


@app.get("/api/jobs/{job_id}/report.{fmt}")
async def job_report(job_id: str, fmt: str):
    job = _job_or_404(job_id)
    if not job.finished:
        raise HTTPException(409, "job is still running")
    data = job.public()
    chain = audit.verify_chain(job.events)
    name = f"proofbox-{job.id[:8]}"
    if fmt == "md":
        return PlainTextResponse(audit.report_markdown(data, chain), media_type="text/markdown",
                                 headers={"Content-Disposition": f'attachment; filename="{name}.md"'})
    if fmt == "json":
        return JSONResponse(audit.report_json(data, chain),
                            headers={"Content-Disposition": f'attachment; filename="{name}.json"'})
    if fmt == "sarif":
        return JSONResponse(audit.report_sarif(data, chain), media_type="application/sarif+json",
                            headers={"Content-Disposition": f'attachment; filename="{name}.sarif"'})
    raise HTTPException(404, "format must be md, json or sarif")


@app.get("/api/jobs/{job_id}/events")
async def job_events(job_id: str, request: Request):
    job = store.get(job_id)
    if not job:
        raise HTTPException(404, "job not found")

    async def stream():
        q = job.subscribe()
        try:
            # Replay history first so late joiners see the whole run.
            sent = 0
            for ev in list(job.events):
                yield f"data: {json.dumps(ev)}\n\n"
                sent += 1
            if job.finished:
                return
            while True:
                if await request.is_disconnected():
                    return
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                if ev["seq"] < sent:
                    continue
                yield f"data: {json.dumps(ev)}\n\n"
                if ev["type"] == "done":
                    return
        finally:
            job.unsubscribe(q)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
