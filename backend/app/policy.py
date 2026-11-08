"""Command policy guard.

Every command the agent wants to run is checked here before it reaches the
sandbox. The sandbox would contain these anyway; the policy is a second layer
that stops the agent from even trying, logs the attempt, and tells the model
why so it can pick a safe path. Defense in depth, and a clear audit trail.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MAX_COMMAND_CHARS = 2000


@dataclass(frozen=True)
class Rule:
    id: str
    pattern: re.Pattern
    reason: str


def _r(rule_id: str, regex: str, reason: str) -> Rule:
    return Rule(rule_id, re.compile(regex, re.IGNORECASE), reason)


RULES: tuple[Rule, ...] = (
    _r("net.fetch", r"\b(curl|wget|nc|ncat|netcat|telnet|ssh|scp|sftp|rsync|ftp)\b",
       "Network tools are not allowed. The sandbox has no network and proofs must be offline."),
    _r("net.python", r"\b(requests\.|urllib\.request|http\.client|socket\.socket)",
       "Inline network code is not allowed in commands."),
    _r("pkg.install", r"\b(pip3?|uv|poetry|npm|pnpm|yarn|apt(-get)?|apk|gem|cargo|go)\s+(install|add|get|i)\b",
       "Installing packages is not allowed. Use the standard library and what the repo already has."),
    _r("priv.escalate", r"\b(sudo|su|doas|chroot|nsenter|unshare|setcap|chmod\s+[ugo]*\+s)\b",
       "Privilege changes are not allowed."),
    _r("host.escape", r"(/var/run/docker\.sock|\bdocker\b|\bmount\b|/proc/sysrq|/sys/fs/cgroup|/dev/(mem|kmem|sd[a-z]))",
       "Touching the container runtime, mounts or host devices is not allowed."),
    _r("fs.wipe", r"\brm\s+(-\S+\s+)*(/|/\*|~|\$HOME)(\s|$)",
       "Wiping the filesystem root or home is not allowed."),
    _r("proc.bomb", r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:",
       "Fork bombs are not allowed."),
    _r("persist.cron", r"(/etc/cron|crontab\b|/etc/rc\.local|systemctl\b|\.bashrc\b|\.profile\b)",
       "Persistence hooks are not allowed."),
    _r("secret.read", r"(/etc/shadow|\.ssh/|\.aws/|\.docker/config|/proc/\d+/environ|/proc/self/environ)",
       "Reading credential locations is not allowed."),
)


@dataclass
class Decision:
    allowed: bool
    rule: str = ""
    reason: str = ""

    def to_dict(self) -> dict:
        return {"allowed": self.allowed, "rule": self.rule, "reason": self.reason}


def check(command: str) -> Decision:
    cmd = command or ""
    if not cmd.strip():
        return Decision(False, "cmd.empty", "Empty command.")
    if len(cmd) > MAX_COMMAND_CHARS:
        return Decision(False, "cmd.size", f"Command longer than {MAX_COMMAND_CHARS} characters. Write a file and run it.")
    for rule in RULES:
        if rule.pattern.search(cmd):
            return Decision(False, rule.id, rule.reason)
    return Decision(True)


def describe() -> list[dict]:
    return [{"id": r.id, "reason": r.reason} for r in RULES]
