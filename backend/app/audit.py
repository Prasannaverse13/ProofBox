"""Tamper evident audit trail and report export.

Every job event is chained: hash_n = sha256(hash_n-1 + canonical(event_n)).
Changing, removing or reordering any event breaks every hash after it. The
chain head is signed with an HMAC key kept on the server, so a report can be
checked later against the server that produced it.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from typing import Any

from .config import settings

GENESIS = "0" * 64
_key: bytes | None = None


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False)


def link(prev: str, event: dict[str, Any]) -> str:
    body = {k: event[k] for k in ("seq", "t", "type", "data")}
    return hashlib.sha256((prev + canonical(body)).encode()).hexdigest()


def signing_key() -> bytes:
    global _key
    if _key is None:
        env = os.environ.get("PROOFBOX_SIGNING_KEY", "")
        if env:
            _key = env.encode()
        else:
            path = settings.data_dir / ".signing_key"
            if not path.exists():
                path.write_text(secrets.token_hex(32))
                path.chmod(0o600)
            _key = path.read_text().strip().encode()
    return _key


def sign(head: str) -> str:
    return hmac.new(signing_key(), head.encode(), hashlib.sha256).hexdigest()


def verify_chain(events: list[dict[str, Any]], signature: str | None = None) -> dict[str, Any]:
    prev = GENESIS
    for i, ev in enumerate(events):
        if ev.get("seq") != i or ev.get("prev") != prev:
            return {"valid": False, "broken_at": i, "events": len(events), "head": prev}
        expected = link(prev, ev)
        if ev.get("hash") != expected:
            return {"valid": False, "broken_at": i, "events": len(events), "head": prev}
        prev = expected
    out: dict[str, Any] = {"valid": True, "broken_at": None, "events": len(events), "head": prev}
    if signature is not None:
        out["signature_valid"] = hmac.compare_digest(sign(prev), signature)
    return out


# ------------------------------------------------------------------ reports

SARIF_LEVEL = {"critical": "error", "high": "error", "medium": "warning", "low": "note"}


def _source_label(source: dict[str, Any]) -> str:
    return source.get("url") or f"sample:{source.get('sample')}"


def report_json(job: dict[str, Any], chain: dict[str, Any]) -> dict[str, Any]:
    return {
        "tool": "ProofBox",
        "job": job["id"],
        "source": job["source"],
        "state": job["state"],
        "summary": job.get("summary", ""),
        "findings": job.get("findings", []),
        "containment": job.get("containment", []),
        "policy_denials": job.get("policy", []),
        "audit": {**chain, "signature": job.get("signature")},
    }


def report_sarif(job: dict[str, Any], chain: dict[str, Any]) -> dict[str, Any]:
    rules, results = [], []
    for f in job.get("findings", []):
        rules.append({
            "id": f["id"],
            "name": f["title"],
            "shortDescription": {"text": f["title"]},
            "fullDescription": {"text": f.get("claim", "")},
            "properties": {"security-severity": {"critical": "9.5", "high": "8.0", "medium": "5.5", "low": "3.0"}.get(f["severity"], "5.0")},
        })
        fix = f.get("fix") or {}
        res: dict[str, Any] = {
            "ruleId": f["id"],
            "level": SARIF_LEVEL.get(f["severity"], "warning"),
            "message": {"text": f"{f.get('claim', '')} Proven in sandbox by {f.get('test_path')} (exit {f.get('exit_code')})."},
            "locations": [{"physicalLocation": {
                "artifactLocation": {"uri": f.get("file") or ""},
                "region": {"startLine": int(f.get("line") or 1)},
            }}],
            "properties": {"proven": True, "proof_command": f.get("command"), "fix_verified": bool(fix.get("verified"))},
        }
        if fix.get("diff"):
            res["properties"]["fix_diff"] = fix["diff"]
        results.append(res)
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {"driver": {"name": "ProofBox", "informationUri": "https://github.com/", "rules": rules}},
            "results": results,
            "properties": {"audit_head": chain.get("head"), "audit_valid": chain.get("valid"), "signature": job.get("signature")},
        }],
    }


def report_markdown(job: dict[str, Any], chain: dict[str, Any]) -> str:
    findings = job.get("findings", [])
    lines = [
        f"# ProofBox report: {_source_label(job['source'])}",
        "",
        f"Job `{job['id']}` · state **{job['state']}** · {len(findings)} proven findings · "
        f"{sum(1 for f in findings if (f.get('fix') or {}).get('verified'))} verified fixes · "
        f"{len(job.get('containment', []))} attacks contained · {len(job.get('policy', []))} commands denied by policy",
        "",
    ]
    if job.get("summary"):
        lines += [job["summary"], ""]
    for f in findings:
        fix = f.get("fix") or {}
        lines += [
            f"## {f['id']} · {f['title']}",
            "",
            f"**Severity:** {f['severity']} · **Where:** `{f.get('file')}:{f.get('line')}` · **Proof attempts:** {f.get('attempts', 1)}",
            "",
            f.get("claim", ""),
            "",
            f"**Proof** `{f.get('command')}` (exit {f.get('exit_code')}, {f.get('duration')}s)",
            "",
            "```",
            (f.get("test_code") or "").rstrip(),
            "```",
            "",
            "<details><summary>Sandbox output</summary>",
            "",
            "```",
            (f.get("output") or "").rstrip(),
            "```",
            "</details>",
            "",
        ]
        if fix.get("diff"):
            status = "verified" if fix.get("verified") else "not verified"
            lines += [
                f"**Fix ({status}):** {fix.get('summary', '')}",
                "",
                "```diff",
                fix["diff"].rstrip(),
                "```",
                "",
                f"Proof after fix: exit {fix.get('proof_exit')} ({'bug gone' if fix.get('bug_gone') else 'bug still there'}). "
                + (f"Repo tests after fix: exit {fix.get('regress_exit')}." if fix.get("regress_command") else ""),
                "",
            ]
    if job.get("containment"):
        lines += ["## Contained", ""]
        lines += [f"- **{c['kind']}** {c['message']}" for c in job["containment"]]
        lines.append("")
    if job.get("policy"):
        lines += ["## Denied by policy", ""]
        lines += [f"- `{p['command']}` · {p['rule']} · {p['reason']}" for p in job["policy"]]
        lines.append("")
    lines += [
        "## Audit trail",
        "",
        f"- Events: {chain.get('events')}",
        f"- Chain valid: {chain.get('valid')}",
        f"- Head hash: `{chain.get('head')}`",
        f"- Server signature (HMAC SHA256 of head): `{job.get('signature') or 'pending'}`",
        "",
    ]
    return "\n".join(lines)
