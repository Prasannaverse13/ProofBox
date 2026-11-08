"""Runtime settings. Everything comes from environment variables so that no
secret ever has to be written to disk or passed into a sandbox."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    # Vultr Serverless Inference (OpenAI compatible)
    inference_base_url: str = os.environ.get(
        "VULTR_INFERENCE_BASE_URL", "https://api.vultrinference.com/v1"
    )
    inference_api_key: str = os.environ.get("VULTR_INFERENCE_API_KEY", "")
    model: str = os.environ.get("PROOFBOX_MODEL", "kimi-k2-instruct")
    max_agent_steps: int = _int("PROOFBOX_MAX_STEPS", 28)

    # Sandbox boundary
    sandbox_image: str = os.environ.get("PROOFBOX_SANDBOX_IMAGE", "proofbox-sandbox:latest")
    # Set to "runsc" when gVisor is installed on the Vultr VM.
    sandbox_runtime: str = os.environ.get("PROOFBOX_SANDBOX_RUNTIME", "")
    sandbox_memory: str = os.environ.get("PROOFBOX_SANDBOX_MEMORY", "512m")
    sandbox_cpus: str = os.environ.get("PROOFBOX_SANDBOX_CPUS", "1")
    sandbox_pids: int = _int("PROOFBOX_SANDBOX_PIDS", 128)
    sandbox_disk: str = os.environ.get("PROOFBOX_SANDBOX_DISK", "256m")
    command_timeout: int = _int("PROOFBOX_COMMAND_TIMEOUT", 30)
    job_timeout: int = _int("PROOFBOX_JOB_TIMEOUT", 600)
    max_repo_mb: int = _int("PROOFBOX_MAX_REPO_MB", 40)

    # Paths
    root: Path = Path(__file__).resolve().parents[2]
    data_dir: Path = Path(
        os.environ.get("PROOFBOX_DATA_DIR", str(Path(__file__).resolve().parents[1] / "data"))
    )
    samples_dir: Path = field(
        default_factory=lambda: Path(
            os.environ.get(
                "PROOFBOX_SAMPLES_DIR",
                str(Path(__file__).resolve().parents[2] / "samples"),
            )
        )
    )

    @property
    def demo_mode(self) -> bool:
        """No inference key means we replay a scripted agent. The sandbox is
        still real: every command still runs inside a locked container."""
        return not self.inference_api_key


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
