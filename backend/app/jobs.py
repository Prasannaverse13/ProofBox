"""In memory job registry with fan out to SSE subscribers and JSON snapshots
on disk so finished reports survive a restart."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from . import audit
from .config import settings


@dataclass
class Job:
    id: str
    source: dict[str, Any]
    created_at: float = field(default_factory=time.time)
    state: str = "queued"  # queued | running | done | failed
    events: list[dict[str, Any]] = field(default_factory=list)
    findings: list[dict[str, Any]] = field(default_factory=list)
    containment: list[dict[str, Any]] = field(default_factory=list)
    policy: list[dict[str, Any]] = field(default_factory=list)
    signature: str = ""
    sandbox: dict[str, Any] = field(default_factory=dict)
    summary: str = ""
    error: str = ""
    finished_at: float | None = None
    _subs: list[asyncio.Queue] = field(default_factory=list, repr=False)

    def emit(self, kind: str, data: dict[str, Any]) -> None:
        # Freeze a copy: later edits to the caller's dict must not change history.
        frozen = json.loads(json.dumps(data, default=str))
        prev = self.events[-1]["hash"] if self.events else audit.GENESIS
        event = {"seq": len(self.events), "t": round(time.time() - self.created_at, 2), "type": kind, "data": frozen}
        event["prev"] = prev
        event["hash"] = audit.link(prev, event)
        self.events.append(event)
        if kind == "sandbox":
            self.sandbox.update(data)
        for q in list(self._subs):
            q.put_nowait(event)

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subs.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        if q in self._subs:
            self._subs.remove(q)

    @property
    def finished(self) -> bool:
        return self.state in ("done", "failed")

    def public(self, with_events: bool = False) -> dict[str, Any]:
        out = {
            "id": self.id,
            "source": self.source,
            "state": self.state,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
            "findings": self.findings,
            "containment": self.containment,
            "policy": self.policy,
            "fixed": sum(1 for f in self.findings if (f.get("fix") or {}).get("verified")),
            "audit_head": self.events[-1]["hash"] if self.events else audit.GENESIS,
            "signature": self.signature,
            "sandbox": self.sandbox,
            "summary": self.summary,
            "error": self.error,
            "proven": sum(1 for f in self.findings if f.get("proven")),
        }
        if with_events:
            out["events"] = self.events
        return out

    def save(self) -> None:
        path = settings.data_dir / f"{self.id}.json"
        path.write_text(json.dumps(self.public(with_events=True), indent=2))


class JobStore:
    def __init__(self) -> None:
        self.jobs: dict[str, Job] = {}

    def create(self, source: dict[str, Any]) -> Job:
        job = Job(id=uuid.uuid4().hex[:16], source=source)
        self.jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        if job_id in self.jobs:
            return self.jobs[job_id]
        path = settings.data_dir / f"{job_id}.json"
        if path.exists() and job_id.isalnum():
            raw = json.loads(path.read_text())
            job = Job(id=raw["id"], source=raw["source"], created_at=raw["created_at"])
            job.state = raw["state"]
            job.events = raw.get("events", [])
            job.findings = raw.get("findings", [])
            job.containment = raw.get("containment", [])
            job.policy = raw.get("policy", [])
            job.signature = raw.get("signature", "")
            job.sandbox = raw.get("sandbox", {})
            job.summary = raw.get("summary", "")
            job.error = raw.get("error", "")
            job.finished_at = raw.get("finished_at")
            self.jobs[job.id] = job
            return job
        return None

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        items = sorted(self.jobs.values(), key=lambda j: j.created_at, reverse=True)[:limit]
        return [j.public() for j in items]


store = JobStore()
