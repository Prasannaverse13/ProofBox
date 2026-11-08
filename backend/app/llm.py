"""Thin client for Vultr Serverless Inference.

Vultr exposes an OpenAI compatible API at https://api.vultrinference.com/v1,
so the official openai SDK works by swapping the base URL. All agent LLM
calls go through here.
"""

from __future__ import annotations

import json
import re
from typing import Any

from openai import AsyncOpenAI

from .config import settings

_client: AsyncOpenAI | None = None


def client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.inference_api_key or "missing",
            base_url=settings.inference_base_url,
            timeout=120,
            max_retries=2,
        )
    return _client


async def chat(messages: list[dict[str, Any]], *, temperature: float = 0.2, max_tokens: int = 2048) -> str:
    resp = await client().chat.completions.create(
        model=settings.model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content or ""


async def list_models() -> list[str]:
    if settings.demo_mode:
        return []
    try:
        page = await client().models.list()
        return [m.id for m in page.data]
    except Exception:  # noqa: BLE001 - health check must never raise
        return []


_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.S)


def parse_action(text: str) -> dict[str, Any]:
    """Pull the first JSON object out of a model reply. Models sometimes wrap
    JSON in code fences or add prose, so be forgiving."""
    candidates: list[str] = []
    m = _FENCE.search(text)
    if m:
        candidates.append(m.group(1))
    # Balanced brace scan for the first top level object.
    start = text.find("{")
    while start != -1:
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidates.append(text[start : i + 1])
                    break
        start = text.find("{", start + 1) if not candidates else -1
    for c in candidates:
        try:
            obj = json.loads(c)
            if isinstance(obj, dict) and "action" in obj:
                obj.setdefault("args", {})
                return obj
        except json.JSONDecodeError:
            continue
    raise ValueError("No JSON action found in model reply")
