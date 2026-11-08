"""Fetch the code under audit onto the host. Fetching never executes repo
code: git hooks, submodules, LFS smudge and local file protocols are off."""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import tempfile
from pathlib import Path

from .config import settings

ALLOWED_HOSTS = ("github.com", "gitlab.com", "bitbucket.org", "codeberg.org")
GIT_URL = re.compile(r"^https://(" + "|".join(re.escape(h) for h in ALLOWED_HOSTS) + r")/[\w.\-]+/[\w.\-]+?(\.git)?/?$")


def list_samples() -> list[dict]:
    out = []
    if not settings.samples_dir.exists():
        return out
    for d in sorted(settings.samples_dir.iterdir()):
        meta = d / "PROOFBOX.md"
        if d.is_dir() and meta.exists():
            lines = meta.read_text().splitlines()
            title = lines[0].lstrip("# ").strip() if lines else d.name
            blurb = next((l.strip() for l in lines[1:] if l.strip()), "")
            out.append({"id": d.name, "title": title, "blurb": blurb})
    return out


async def fetch_source(source: dict, dest_root: Path) -> Path:
    kind = source.get("type")
    if kind == "sample":
        sid = str(source.get("sample", ""))
        if not re.fullmatch(r"[\w\-]+", sid):
            raise ValueError("Unknown sample")
        src = settings.samples_dir / sid
        if not src.is_dir():
            raise ValueError("Unknown sample")
        dest = dest_root / sid
        shutil.copytree(src, dest, ignore=shutil.ignore_patterns("PROOFBOX.md"))
        return dest
    if kind == "git":
        url = str(source.get("url", "")).strip()
        if not GIT_URL.match(url):
            raise ValueError("Use a public https link on " + ", ".join(ALLOWED_HOSTS))
        dest = dest_root / "repo"
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_LFS_SKIP_SMUDGE": "1",
            "HOME": str(dest_root),
        }
        proc = await asyncio.create_subprocess_exec(
            "git", "-c", "core.hooksPath=/dev/null", "-c", "protocol.file.allow=never",
            "-c", "core.symlinks=false",
            "clone", "--depth", "1", "--single-branch", "--no-recurse-submodules", "--quiet", url, str(dest),
            env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        )
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=90)
        except asyncio.TimeoutError:
            proc.kill()
            raise ValueError("Clone timed out")
        if proc.returncode != 0:
            raise ValueError("Clone failed: " + out.decode(errors="replace")[-300:])
        shutil.rmtree(dest / ".git", ignore_errors=True)
        return dest
    raise ValueError("Source must be a sample or a git link")


def make_workspace() -> Path:
    return Path(tempfile.mkdtemp(prefix="proofbox-"))


def file_tree(root: Path, limit: int = 300) -> list[str]:
    files = []
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if any(part in {".git", "node_modules", "__pycache__", "out", "cache"} for part in rel.parts):
            continue
        if p.is_file() and not p.is_symlink():
            files.append(f"{rel} ({p.stat().st_size} B)")
        if len(files) >= limit:
            files.append("... more files not shown")
            break
    return files


def read_text(root: Path, rel: str, start: int = 1, end: int | None = None) -> str:
    path = (root / rel).resolve()
    if not str(path).startswith(str(root.resolve())) or not path.is_file() or path.is_symlink():
        raise ValueError(f"No such file: {rel}")
    if path.stat().st_size > 400_000:
        raise ValueError("File too large to read")
    lines = path.read_text(errors="replace").splitlines()
    start = max(1, int(start or 1))
    end = min(len(lines), int(end or start + 220))
    return "\n".join(f"{i:>4}  {lines[i-1]}" for i in range(start, end + 1))


def detect_test_command(root: Path) -> str | None:
    if (root / "foundry.toml").exists():
        return "forge test -vv --offline"
    if (root / "package.json").exists() and '"test"' in (root / "package.json").read_text(errors="ignore"):
        return "npm test --silent"
    if any(root.rglob("test_*.py")) or any(root.rglob("*_test.py")) or (root / "pyproject.toml").exists():
        return "python -m pytest -q -p no:cacheprovider"
    if (root / "go.mod").exists():
        return "go test ./..."
    return None
