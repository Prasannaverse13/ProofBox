"""ProofBox agent loop.

The agent reads code on the host (reading is safe) and runs code only inside
the sandbox. A finding counts only when a proof test the agent wrote passes
inside the sandbox and prints the PROOFBOX_CONFIRMED marker. Everything else
is dropped from the report.
"""

from __future__ import annotations

import asyncio
import difflib
import json
import shutil
import time
from pathlib import Path
from typing import Any

from . import audit, llm, policy
from .config import settings
from .demo_plans import demo_plan
from .jobs import Job
from .sandbox import DockerSandbox, ExecResult, SandboxError
from .sources import detect_test_command, fetch_source, file_tree, make_workspace, read_text

MARKER = "PROOFBOX_CONFIRMED"
MAX_FINDINGS = 8
OBS_LIMIT = 6000

SYSTEM_PROMPT = f"""You are ProofBox, a security and correctness auditor that never guesses.
You audit an untrusted code repository. The repository is copied into a locked sandbox at /work:
no network, read only root, non root user, {settings.sandbox_memory} memory, {settings.command_timeout}s per command.
Tools available inside the sandbox: python3 with pytest, node, sh, coreutils, and forge with solc for Solidity.
Nothing can be installed (no network). Use only the standard library and what the repo already has.

Your job:
1. Read the code and find real bugs: security holes (injection, traversal, auth bypass, reentrancy,
   unchecked math, unsafe deserialization) and correctness bugs (wrong math, off by one, bad edge cases).
2. For every suspected bug, write a small proof test that FAILS TO PASS unless the bug is real.
   The proof must exercise the actual repo code, assert the buggy behavior, and print {MARKER} only
   when the bug is demonstrated. For Solidity use a forge test function whose name contains {MARKER}
   (forge prints the function name on PASS); do not import forge-std unless it already exists in lib/.
3. Call prove. Only findings whose proof passes go in the report. If a proof fails, read the output,
   fix the test, and try again at most twice. If you cannot prove it, move on.

Reply with exactly ONE JSON object and nothing else:
{{"thought": "short reasoning", "action": "<name>", "args": {{...}}}}

Actions:
- list_files: {{}}
- read_file: {{"path": "src/app.py", "start": 1, "end": 200}}
- run: {{"command": "python -m pytest -q tests/test_x.py"}}   (runs in the sandbox, cwd /work)
- write_file: {{"path": "proofbox_tests/test_x.py", "content": "..."}}   (writes inside the sandbox only)
- prove: {{"title": "...", "severity": "critical|high|medium|low", "file": "path", "line": 12,
          "claim": "one sentence: what is wrong and the impact",
          "test_path": "proofbox_tests/test_x.py", "test_code": "...full file...",
          "command": "python -m pytest -q -s proofbox_tests/test_x.py"}}
- fix: {{"finding": "F1", "summary": "one sentence: what the patch changes",
        "patches": [{{"path": "src/app.py", "find": "exact old text", "replace": "new text"}}],
        "regress_command": "python -m pytest -q tests"}}
  After a finding is PROVEN, write the smallest patch that removes the bug. ProofBox applies it in the sandbox,
  reruns your proof (it must now FAIL) and runs regress_command (it must PASS, so the patch breaks nothing).
  Only then the fix is marked verified. `find` must match the original file text exactly.
- finish: {{"summary": "two or three sentences for the report"}}

Every command passes a policy guard first: no network tools, no package installs, no privilege changes,
no docker or mounts, no persistence, no credential paths. A denied command does not run; pick another way.

Rules: keep proofs minimal and deterministic. Never try to reach the network or escape the sandbox.
Put proof files under proofbox_tests/ (or test/ for forge). Stop after {MAX_FINDINGS} proven findings.
"""


def _trim(text: str, limit: int = OBS_LIMIT) -> str:
    if len(text) <= limit:
        return text
    return text[: limit // 2] + "\n...[trimmed]...\n" + text[-limit // 2 :]


class Auditor:
    def __init__(self, job: Job):
        self.job = job
        self.workdir: Path | None = None
        self.repo: Path | None = None
        self.box = DockerSandbox(job.id, on_event=job.emit)
        self.step = 0

    # ------------------------------------------------------------ helpers
    def log(self, message: str, **extra: Any) -> None:
        self.job.emit("log", {"message": message, **extra})

    def _record_containment(self, res: ExecResult, origin: str) -> None:
        for ev in res.containment:
            item = {**ev, "command": res.command, "origin": origin, "step": self.step}
            self.job.containment.append(item)
            self.job.emit("containment", item)

    def _denied(self, command: str, origin: str) -> str | None:
        """Policy check for commands chosen by the agent. Returns the denial text or None."""
        if origin == "baseline":
            return None  # the repo's own test command, chosen by ProofBox, not the model
        decision = policy.check(command)
        if decision.allowed:
            return None
        item = {"command": command[:300], "origin": origin, "step": self.step, **decision.to_dict()}
        self.job.policy.append(item)
        self.job.emit("policy", item)
        return f"POLICY DENIED ({decision.rule}): {decision.reason} The command did not run."

    async def _exec(self, command: str, origin: str) -> ExecResult:
        res = await self.box.exec(command)
        self._record_containment(res, origin)
        if res.containment:
            alive = await self.box.health()
            self.job.emit("integrity", {
                "sandbox_alive": alive,
                "host_files_intact": self._host_intact(),
                "after": command,
            })
        return res

    def _host_intact(self) -> bool:
        # The host copy of the repo is our canary: the sandbox must never touch it.
        return bool(self.repo and self._host_snapshot == self._snapshot(self.repo))

    @staticmethod
    def _snapshot(root: Path) -> tuple:
        return tuple(sorted((str(p.relative_to(root)), p.stat().st_size) for p in root.rglob("*") if p.is_file()))

    # ------------------------------------------------------------ actions
    async def act(self, action: str, args: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        """Run one tool call. Returns (observation text, structured data for UI)."""
        assert self.repo is not None
        if action == "list_files":
            files = file_tree(self.repo)
            return "\n".join(files), {"files": len(files)}
        if action == "read_file":
            text = read_text(self.repo, str(args.get("path", "")), args.get("start", 1), args.get("end"))
            return text, {"path": args.get("path")}
        if action == "write_file":
            await self.box.write_file(str(args["path"]), str(args.get("content", "")))
            return f"wrote {args['path']} in sandbox", {"path": args["path"]}
        if action == "run":
            denied = self._denied(str(args["command"]), "agent")
            if denied:
                return denied, {"denied": True}
            res = await self._exec(str(args["command"]), "agent")
            return (f"exit={res.exit_code} time={res.duration:.1f}s\n{res.output}", res.to_dict())
        if action == "prove":
            return await self._prove(args)
        if action == "fix":
            return await self._fix(args)
        raise ValueError(f"Unknown action: {action}")

    async def _prove(self, args: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        if sum(1 for f in self.job.findings if f["proven"]) >= MAX_FINDINGS:
            return "Finding limit reached. Call finish.", {}
        test_path = str(args.get("test_path", ""))
        test_code = str(args.get("test_code", ""))
        if test_path and test_code:
            await self.box.write_file(test_path, test_code)
        command = str(args.get("command", ""))
        denied = self._denied(command, "proof")
        if denied:
            return denied, {"denied": True}
        res = await self._exec(command, "proof")
        proven = res.exit_code == 0 and MARKER in res.output
        title = str(args.get("title", "Untitled finding"))
        existing = next((f for f in self.job.findings if f["title"] == title), None)
        finding = {
            "id": existing["id"] if existing else f"F{len(self.job.findings) + 1}",
            "title": title,
            "severity": str(args.get("severity", "medium")).lower(),
            "file": args.get("file"),
            "line": args.get("line"),
            "claim": args.get("claim", ""),
            "test_path": test_path,
            "test_code": test_code,
            "command": command,
            "proven": proven,
            "exit_code": res.exit_code,
            "output": _trim(res.output, 3500),
            "duration": round(res.duration, 2),
            "attempts": (existing["attempts"] + 1) if existing else 1,
        }
        if existing:
            existing.update(finding)
        else:
            self.job.findings.append(finding)
        self.job.emit("finding", finding)
        verdict = "PROVEN. The bug is real." if proven else (
            f"NOT PROVEN (exit={res.exit_code}, marker {'found' if MARKER in res.output else 'missing'}). "
            "Fix the proof or move on."
        )
        return f"{verdict}\n{res.output}", {"proven": proven, "exit_code": res.exit_code}


    async def _fix(self, args: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        """Apply a patch in the sandbox, show the proof now fails and the repo tests still pass."""
        assert self.repo is not None
        ref = str(args.get("finding", ""))
        finding = next((f for f in self.job.findings if f["proven"] and ref in (f["id"], f["title"])), None)
        if not finding:
            return f"No proven finding '{ref}'. Fix only proven findings, by id.", {"error": "unknown finding"}
        patches = args.get("patches") or []
        if not isinstance(patches, list) or not patches:
            return "patches must be a non empty list of {path, find, replace}.", {"error": "no patches"}
        regress = str(args.get("regress_command", "")).strip()
        for cmd in (finding["command"], regress):
            if cmd and (denied := self._denied(cmd, "fix")):
                return denied, {"denied": True}

        originals: dict[str, str] = {}
        patched: dict[str, str] = {}
        for p in patches[:6]:
            path = str(p.get("path", "")).lstrip("/")
            src = (self.repo / path).resolve()
            if not src.is_relative_to(self.repo.resolve()) or not src.is_file():
                return f"Cannot patch {path}: not a file in the repo.", {"error": "bad path"}
            base = patched.get(path) or src.read_text(encoding="utf-8", errors="replace")
            originals.setdefault(path, src.read_text(encoding="utf-8", errors="replace"))
            find, repl = str(p.get("find", "")), str(p.get("replace", ""))
            if not find or base.count(find) != 1:
                n = base.count(find) if find else 0
                return f"Patch for {path}: find text matched {n} times, it must match exactly once.", {"error": "find mismatch"}
            patched[path] = base.replace(find, repl, 1)

        diff = "".join(
            "".join(difflib.unified_diff(originals[p].splitlines(True), patched[p].splitlines(True),
                                         fromfile=f"a/{p}", tofile=f"b/{p}"))
            for p in patched
        )
        try:
            for path, text in patched.items():
                await self.box.write_file(path, text)
            proof = await self._exec(finding["command"], "fix")
            bug_gone = not (proof.exit_code == 0 and MARKER in proof.output)
            reg = await self._exec(regress, "fix") if regress else None
        finally:
            # Put the original code back so other proofs still see the real repo.
            for path, text in originals.items():
                await self.box.write_file(path, text)

        regress_ok = bool(reg and reg.exit_code == 0)
        fix = {
            "summary": str(args.get("summary", ""))[:400],
            "files": [{"path": p} for p in patched],
            "diff": diff,
            "bug_gone": bug_gone,
            "proof_exit": proof.exit_code,
            "proof_output": _trim(proof.output, 1500),
            "regress_command": regress,
            "regress_exit": reg.exit_code if reg else None,
            "regress_output": _trim(reg.output, 1500) if reg else "",
            "verified": bug_gone and regress_ok,
        }
        finding["fix"] = fix
        self.job.emit("fix", {"finding": finding["id"], "title": finding["title"], **fix})
        if fix["verified"]:
            verdict = "FIX VERIFIED. The proof now fails and the repo tests pass."
        elif not bug_gone:
            verdict = "FIX REJECTED. The proof still passes, so the bug is still there."
        elif not regress:
            verdict = "FIX NOT VERIFIED. Give a regress_command so the patch is checked against the repo tests."
        else:
            verdict = f"FIX REJECTED. The proof fails now but the repo tests broke (exit {reg.exit_code})."
        return (f"{verdict}\nproof after patch exit={proof.exit_code}\n{_trim(proof.output, 1500)}"
                + (f"\nregress exit={reg.exit_code}\n{_trim(reg.output, 1500)}" if reg else "")), {
            "verified": fix["verified"], "bug_gone": bug_gone}

    # ------------------------------------------------------------ main
    async def run(self) -> None:
        job = self.job
        job.state = "running"
        job.emit("status", {"state": "running", "mode": "demo" if settings.demo_mode else "live",
                            "model": None if settings.demo_mode else settings.model})
        try:
            await asyncio.wait_for(self._run_inner(), timeout=settings.job_timeout)
            job.state = "done"
        except asyncio.TimeoutError:
            job.state = "failed"
            job.error = f"Job hit the {settings.job_timeout}s limit"
        except Exception as exc:  # noqa: BLE001
            job.state = "failed"
            job.error = str(exc)[:500]
        finally:
            try:
                await self.box.destroy()
            except Exception:  # noqa: BLE001
                pass
            if self.workdir:
                shutil.rmtree(self.workdir, ignore_errors=True)
            job.finished_at = time.time()
            proven = [f for f in job.findings if f["proven"]]
            # Unproven guesses never reach the report.
            job.findings = proven
            job.emit("done", {"state": job.state, "error": job.error, "summary": job.summary,
                              "proven": len(proven), "contained": len(job.containment),
                              "fixed": sum(1 for f in proven if (f.get("fix") or {}).get("verified")),
                              "denied": len(job.policy)})
            # Sign the head of the hash chain so the report can be checked later.
            job.signature = audit.sign(job.events[-1]["hash"])
            job.save()

    async def _run_inner(self) -> None:
        job = self.job
        self.workdir = make_workspace()
        self.log("Fetching source", source=job.source)
        self.repo = await fetch_source(job.source, self.workdir)
        self._host_snapshot = self._snapshot(self.repo)
        files = file_tree(self.repo)
        self.log(f"Fetched {len(files)} files")

        # Baseline: run the repo's own tests. This executes untrusted code, so it
        # gets its own throwaway box that is destroyed right after.
        baseline_obs = "No test suite detected."
        test_cmd = detect_test_command(self.repo)
        if test_cmd:
            self.box = DockerSandbox(job.id, on_event=job.emit, phase="baseline")
            await self.box.start()
            size = await self.box.upload(self.repo)
            self.log(f"Copied {size // 1024} KB into baseline sandbox {self.box.container_id}")
            self.step += 1
            job.emit("step", {"n": self.step, "action": "run", "args": {"command": test_cmd},
                              "thought": "Run the repo's own test suite first. This executes untrusted code, so it runs in a throwaway box."})
            res = await self._exec(test_cmd, "baseline")
            job.emit("observation", {"n": self.step, "action": "run", "result": res.to_dict()})
            baseline_obs = f"Baseline `{test_cmd}` exit={res.exit_code}\n{_trim(res.output, 4000)}"
            await self.box.destroy()
            self.log("Baseline box destroyed. Starting a clean box for the audit.")

        self.box = DockerSandbox(job.id, on_event=job.emit, phase="audit")
        await self.box.start()
        size = await self.box.upload(self.repo)
        self.log(f"Copied {size // 1024} KB into audit sandbox {self.box.container_id}")

        if settings.demo_mode:
            await self._demo_loop()
        else:
            await self._llm_loop(files, baseline_obs)

    async def _demo_loop(self) -> None:
        plan = demo_plan(self.job.source)
        self.log("Demo mode: no Vultr inference key set, replaying a scripted agent. Sandbox runs are real.")
        for item in plan:
            self.step += 1
            action, args = item["action"], item.get("args", {})
            self.job.emit("step", {"n": self.step, "action": action, "args": _ui_args(action, args), "thought": item.get("thought", "")})
            await asyncio.sleep(0.35)
            if action == "finish":
                self.job.summary = args.get("summary", "")
                break
            try:
                obs, data = await self.act(action, args)
            except (ValueError, SandboxError, KeyError) as exc:
                obs, data = f"error: {exc}", {"error": str(exc)}
            self.job.emit("observation", {"n": self.step, "action": action, "result": data, "text": _trim(obs, 2500)})

    async def _llm_loop(self, files: list[str], baseline_obs: str) -> None:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": (
                f"Repository files:\n{chr(10).join(files[:200])}\n\n{baseline_obs}\n\n"
                "Start the audit. Reply with one JSON action."
            )},
        ]
        bad_replies = 0
        for _ in range(settings.max_agent_steps):
            reply = await llm.chat(messages)
            messages.append({"role": "assistant", "content": reply})
            try:
                call = llm.parse_action(reply)
            except ValueError:
                bad_replies += 1
                if bad_replies > 3:
                    raise RuntimeError("Model stopped returning valid JSON actions")
                messages.append({"role": "user", "content": "Reply with exactly one JSON object with keys thought, action, args."})
                continue
            action, args = str(call["action"]), call.get("args") or {}
            self.step += 1
            self.job.emit("step", {"n": self.step, "action": action, "args": _ui_args(action, args),
                                   "thought": str(call.get("thought", ""))[:600]})
            if action == "finish":
                self.job.summary = str(args.get("summary", ""))[:1200]
                return
            try:
                obs, data = await self.act(action, args)
            except (ValueError, SandboxError, KeyError, TypeError) as exc:
                obs, data = f"error: {exc}", {"error": str(exc)}
            self.job.emit("observation", {"n": self.step, "action": action, "result": data, "text": _trim(obs, 2500)})
            messages.append({"role": "user", "content": f"Observation for {action}:\n{_trim(obs)}\n\nNext JSON action."})
            # Keep the context bounded: drop old observations, keep system + first message.
            if len(messages) > 30:
                messages = messages[:2] + messages[-26:]
        self.job.summary = self.job.summary or "Step budget reached."


def _ui_args(action: str, args: dict[str, Any]) -> dict[str, Any]:
    """Args as shown in the live log. Long code is shortened."""
    out = {}
    for k, v in args.items():
        if isinstance(v, str) and len(v) > 400:
            out[k] = v[:400] + " ..."
        else:
            out[k] = v
    if action == "prove" and "test_code" in args:
        out["test_code"] = args["test_code"]
    return out


async def run_job(job: Job) -> None:
    await Auditor(job).run()


def dump(obj: Any) -> str:
    return json.dumps(obj, indent=2, default=str)
