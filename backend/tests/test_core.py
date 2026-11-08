import pytest

from app.llm import parse_action
from app.sandbox import DockerSandbox, scan_containment
from app.sources import GIT_URL


def test_parse_action_plain():
    a = parse_action('{"thought": "x", "action": "list_files", "args": {}}')
    assert a["action"] == "list_files"


def test_parse_action_fenced_with_prose():
    a = parse_action('Sure.\n```json\n{"action": "run", "args": {"command": "ls {a}"}}\n```')
    assert a["args"]["command"] == "ls {a}"


def test_parse_action_rejects_garbage():
    with pytest.raises(ValueError):
        parse_action("no json here")


def test_containment_scan_finds_guards():
    out = "rm: cannot remove '/etc': Read-only file system\nTemporary failure in name resolution\n[Errno 11] Resource temporarily unavailable"
    kinds = {e["kind"] for e in scan_containment(out, 1, False)}
    assert {"filesystem", "network", "processes"} <= kinds


def test_containment_timeout():
    kinds = {e["kind"] for e in scan_containment("", 137, True)}
    assert "timeout" in kinds


def test_docker_args_lock_everything_down():
    args = " ".join(DockerSandbox("abc").docker_run_args())
    for flag in ["--network none", "--read-only", "--cap-drop ALL", "no-new-privileges", "--user 1000:1000", "--pids-limit"]:
        assert flag in args
    assert "API_KEY" not in args


@pytest.mark.parametrize("url,ok", [
    ("https://github.com/foo/bar", True),
    ("https://github.com/foo/bar.git", True),
    ("http://github.com/foo/bar", False),
    ("https://evil.com/foo/bar", False),
    ("file:///etc/passwd", False),
    ("https://github.com/foo/bar/../../x", False),
])
def test_git_url_allowlist(url, ok):
    assert bool(GIT_URL.match(url)) is ok


# ------------------------------------------------------------------ policy

@pytest.mark.parametrize("cmd,rule", [
    ("curl http://x.example", "net.fetch"),
    ("pip install requests", "pkg.install"),
    ("npm i left-pad", "pkg.install"),
    ("sudo id", "priv.escalate"),
    ("ls /var/run/docker.sock", "host.escape"),
    ("rm -rf --no-preserve-root /", "fs.wipe"),
    ("echo x > /etc/cron.d/x", "persist.cron"),
    ("cat /proc/self/environ", "secret.read"),
])
def test_policy_denies(cmd, rule):
    from app.policy import check
    d = check(cmd)
    assert not d.allowed and d.rule == rule


@pytest.mark.parametrize("cmd", [
    "python -m pytest -q -s proofbox_tests/test_x.py",
    "node proofbox_tests/alg_none.js",
    "forge test --offline --match-path test/P.t.sol -vv",
    "rm -rf proofbox_tests/tmp",
])
def test_policy_allows(cmd):
    from app.policy import check
    assert check(cmd).allowed


# ------------------------------------------------------------------ audit chain

def test_audit_chain_detects_tampering(tmp_path, monkeypatch):
    from app import audit
    from app.jobs import Job
    monkeypatch.setenv("PROOFBOX_SIGNING_KEY", "test-key")
    audit._key = None
    job = Job(id="abc", source={"type": "sample", "sample": "x"})
    data = {"title": "a"}
    job.emit("log", {"message": "one"})
    job.emit("finding", data)
    data["title"] = "changed after emit"  # must not change history
    job.emit("done", {"state": "done"})
    head = job.events[-1]["hash"]
    sig = audit.sign(head)
    ok = audit.verify_chain(job.events, sig)
    assert ok["valid"] and ok["signature_valid"] and job.events[1]["data"]["title"] == "a"
    job.events[1]["data"]["title"] = "forged"
    bad = audit.verify_chain(job.events, sig)
    assert not bad["valid"] and bad["broken_at"] == 1
    audit._key = None
