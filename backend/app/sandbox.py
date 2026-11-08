"""The blast radius boundary.

Every command the agent wants to run goes through DockerSandbox. The agent
process itself never executes repo code. Each job gets one fresh container:

* no network (``--network none``)
* read only root filesystem, code lives on a size capped tmpfs
* non root user, all Linux capabilities dropped, no new privileges
* memory, CPU and process count limits
* per command wall clock timeout enforced twice (inside and on the host)
* no secrets: the container gets an empty environment
* destroyed when the job ends, success or failure

When gVisor is installed on the Vultr VM set PROOFBOX_SANDBOX_RUNTIME=runsc
and the same container also gets a user space kernel.
"""

from __future__ import annotations

import asyncio
import io
import re
import shlex
import tarfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .config import settings

MAX_OUTPUT = 24_000  # bytes of stdout+stderr kept per command

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "out", "cache"}


@dataclass
class ExecResult:
    command: str
    exit_code: int
    output: str
    duration: float
    timed_out: bool = False
    truncated: bool = False
    containment: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "command": self.command,
            "exit_code": self.exit_code,
            "output": self.output,
            "duration": round(self.duration, 2),
            "timed_out": self.timed_out,
            "truncated": self.truncated,
            "containment": self.containment,
        }


# Patterns in sandbox output that show a guard doing its job.
CONTAINMENT_PATTERNS: list[tuple[str, str, str]] = [
    (r"Read-only file system", "filesystem", "Write to the root filesystem was blocked (read only)"),
    (r"Network is unreachable|Temporary failure in name resolution|Name or service not known|Could not resolve host|getaddrinfo|ENOTFOUND|EAI_AGAIN",
     "network", "Outbound network call was blocked (no network)"),
    (r"Resource temporarily unavailable|can't fork|Cannot fork|fork: retry", "processes", "Process explosion was capped by the pids limit"),
    (r"rm: cannot remove|rm: can't remove|Permission denied", "permissions", "Destructive command was denied (non root, caps dropped)"),
    (r"MemoryError|Cannot allocate memory|JavaScript heap out of memory|\bKilled\b", "memory", "Memory bomb hit the memory ceiling"),
]


def scan_containment(output: str, exit_code: int, timed_out: bool) -> list[dict]:
    events: list[dict] = []
    seen: set[str] = set()
    for pattern, kind, message in CONTAINMENT_PATTERNS:
        if kind in seen:
            continue
        if re.search(pattern, output):
            seen.add(kind)
            events.append({"kind": kind, "message": message})
    if timed_out:
        events.append({"kind": "timeout", "message": f"Runaway command was killed at the {settings.command_timeout}s limit"})
    elif exit_code == 137 and "memory" not in seen:
        events.append({"kind": "memory", "message": "Process was killed by the memory limit (exit 137)"})
    return events


def _tar_directory(src: Path) -> bytes:
    buf = io.BytesIO()
    total = 0
    limit = settings.max_repo_mb * 1024 * 1024
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for path in sorted(src.rglob("*")):
            rel = path.relative_to(src)
            if any(part in SKIP_DIRS for part in rel.parts):
                continue
            if path.is_symlink():
                # Never follow links out of the repo.
                continue
            if path.is_file():
                total += path.stat().st_size
                if total > limit:
                    raise ValueError(f"Repository is larger than {settings.max_repo_mb} MB")
            info = tar.gettarinfo(str(path), arcname=str(rel))
            info.uid = info.gid = 1000
            info.uname = info.gname = "sandbox"
            if path.is_file():
                with open(path, "rb") as fh:
                    tar.addfile(info, fh)
            elif path.is_dir():
                tar.addfile(info)
    return buf.getvalue()


async def _run(*args: str, stdin: bytes | None = None, timeout: float = 60) -> tuple[int, bytes]:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdin=asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(stdin), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return 124, b"host timeout"
    return proc.returncode or 0, out or b""


class SandboxError(RuntimeError):
    pass


class DockerSandbox:
    def __init__(self, job_id: str, on_event: Callable[[str, dict], None] | None = None, phase: str = "audit"):
        self.job_id = job_id
        self.phase = phase
        self.name = f"proofbox-{job_id[:12]}-{uuid.uuid4().hex[:6]}"
        self.container_id: str | None = None
        self.created_at: float | None = None
        self.destroyed_at: float | None = None
        self.on_event = on_event or (lambda kind, data: None)

    # ----- limits shown in the UI and in the report
    @property
    def limits(self) -> dict:
        return {
            "image": settings.sandbox_image,
            "runtime": settings.sandbox_runtime or "runc",
            "network": "none",
            "memory": settings.sandbox_memory,
            "cpus": settings.sandbox_cpus,
            "pids": settings.sandbox_pids,
            "disk": settings.sandbox_disk,
            "command_timeout_s": settings.command_timeout,
            "root_fs": "read only",
            "user": "1000 (non root)",
            "capabilities": "all dropped",
            "secrets": "none",
        }

    def docker_run_args(self) -> list[str]:
        args = [
            "docker", "run", "-d",
            "--name", self.name,
            "--label", "proofbox=1",
            "--network", "none",
            "--memory", settings.sandbox_memory,
            "--memory-swap", settings.sandbox_memory,
            "--cpus", settings.sandbox_cpus,
            "--pids-limit", str(settings.sandbox_pids),
            "--read-only",
            "--tmpfs", "/tmp:rw,nosuid,nodev,size=64m",
            "--tmpfs", f"/work:rw,exec,nosuid,nodev,size={settings.sandbox_disk},uid=1000,gid=1000,mode=0755",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--user", "1000:1000",
            "--workdir", "/work",
            "--env", "HOME=/tmp",
            "--env", "PYTHONDONTWRITEBYTECODE=1",
            "--ulimit", "nofile=256:256",
        ]
        if settings.sandbox_runtime:
            args += ["--runtime", settings.sandbox_runtime]
        args += [settings.sandbox_image, "sleep", "infinity"]
        return args

    async def start(self) -> None:
        code, out = await _run(*self.docker_run_args(), timeout=90)
        if code != 0:
            raise SandboxError(f"Could not start sandbox: {out.decode(errors='replace')[-600:]}")
        self.container_id = out.decode().strip()[:12]
        self.created_at = time.time()
        self.on_event("sandbox", {"state": "running", "phase": self.phase, "name": self.name, "id": self.container_id, "limits": self.limits})

    async def upload(self, src: Path) -> int:
        data = _tar_directory(src)
        code, out = await _run(
            "docker", "exec", "-i", "-u", "1000:1000", self.name, "tar", "-x", "-C", "/work", "-f", "-",
            stdin=data, timeout=120,
        )
        if code != 0:
            raise SandboxError(f"Upload failed: {out.decode(errors='replace')[-400:]}")
        return len(data)

    async def write_file(self, rel_path: str, content: str) -> None:
        rel = rel_path.lstrip("/")
        if ".." in Path(rel).parts:
            raise SandboxError("Path escapes /work")
        buf = io.BytesIO()
        raw = content.encode()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            info = tarfile.TarInfo(rel)
            info.size = len(raw)
            info.uid = info.gid = 1000
            info.mode = 0o644
            info.mtime = int(time.time())
            tar.addfile(info, io.BytesIO(raw))
        code, out = await _run(
            "docker", "exec", "-i", "-u", "1000:1000", self.name, "tar", "-x", "-C", "/work", "-f", "-",
            stdin=buf.getvalue(), timeout=30,
        )
        if code != 0:
            raise SandboxError(f"Write failed: {out.decode(errors='replace')[-400:]}")

    async def exec(self, command: str, timeout: int | None = None) -> ExecResult:
        if not self.container_id:
            raise SandboxError("Sandbox is not running")
        limit = timeout or settings.command_timeout
        started = time.time()
        # Inner kill with coreutils timeout, outer kill on the host as backup.
        inner = f"timeout -s KILL {limit} sh -c {shlex.quote(command)}"
        code, out = await _run(
            "docker", "exec", "-u", "1000:1000", "-w", "/work", self.name, "sh", "-c", inner,
            timeout=limit + 10,
        )
        duration = time.time() - started
        timed_out = duration >= limit - 0.5 and code in (124, 137)
        text = out.decode(errors="replace")
        truncated = len(text) > MAX_OUTPUT
        if truncated:
            text = text[: MAX_OUTPUT // 2] + "\n...[output truncated]...\n" + text[-MAX_OUTPUT // 2 :]
        result = ExecResult(command, code, text, duration, timed_out, truncated)
        result.containment = scan_containment(text, code, timed_out)
        return result

    async def health(self) -> bool:
        """After something hostile ran, prove the box is still standing."""
        if not self.container_id:
            return False
        code, _ = await _run("docker", "exec", self.name, "true", timeout=15)
        return code == 0

    async def destroy(self) -> None:
        if not self.container_id or self.destroyed_at:
            return
        await _run("docker", "rm", "-f", "-v", self.name, timeout=60)
        self.destroyed_at = time.time()
        self.on_event("sandbox", {"state": "destroyed", "phase": self.phase, "name": self.name, "id": self.container_id,
                                  "lifetime_s": round(self.destroyed_at - (self.created_at or self.destroyed_at), 1)})


async def sweep_orphans() -> int:
    """Remove sandboxes left behind by a crash. Called on startup."""
    code, out = await _run("docker", "ps", "-aq", "--filter", "label=proofbox=1", timeout=30)
    ids = out.decode().split() if code == 0 else []
    if ids:
        await _run("docker", "rm", "-f", *ids, timeout=60)
    return len(ids)


async def docker_status() -> dict:
    code, out = await _run("docker", "image", "inspect", settings.sandbox_image, "--format", "{{.Id}}", timeout=20)
    return {
        "docker": code != 127,
        "image_ready": code == 0,
        "image": settings.sandbox_image,
        "runtime": settings.sandbox_runtime or "runc",
    }
