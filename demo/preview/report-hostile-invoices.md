# ProofBox report: sample:hostile-invoices

Job `65d168edcf36492f` · state **done** · 2 proven findings · 2 verified fixes · 6 attacks contained · 1 commands denied by policy

The test suite is hostile: it tried to steal env vars, phone home, wipe the disk, install a cron job, spawn hundreds of processes, allocate 2 GB and hang forever. Every attempt was contained and the box was replaced before the audit. Two real bugs were proven: a critical path traversal in load_template and lost cents in split_bill. Both got patches that were verified in the sandbox: each proof now fails and the original tests still pass. One guess about apply_discount failed its proof and was dropped, and an attempt to install a package was stopped by the policy guard.

## F1 · split_bill silently loses cents

**Severity:** high · **Where:** `invoice_tools/money.py:15` · **Proof attempts:** 1

split_bill floors every share and drops the remainder, so a 10.00 bill split three ways only collects 9.99.

**Proof** `python -m pytest -q -s -p no:cacheprovider --noconftest proofbox_tests/test_split.py` (exit 0, 1.02s)

```
from invoice_tools import split_bill


def test_split_bill_loses_cents():
    shares = split_bill(1000, 3)
    lost = 1000 - sum(shares)
    assert lost > 0, 'shares add up, no bug'
    print(f'\nPROOFBOX_CONFIRMED split_bill(1000, 3) = {shares} sums to {sum(shares)}, {lost} cent lost')
```

<details><summary>Sandbox output</summary>

```

PROOFBOX_CONFIRMED split_bill(1000, 3) = [333, 333, 333] sums to 999, 1 cent lost
.
1 passed in 0.01s
```
</details>

**Fix (verified):** Use divmod and give one extra cent to the first `rest` people so shares always sum to the total.

```diff
--- a/invoice_tools/money.py
+++ b/invoice_tools/money.py
@@ -12,5 +12,5 @@
     """Split a bill between people. The shares must add up to the total."""
     if people <= 0:
         raise ValueError("people must be positive")
-    share = total_cents // people
-    return [share] * people
+    share, rest = divmod(total_cents, people)
+    return [share + 1] * rest + [share] * (people - rest)
```

Proof after fix: exit 1 (bug gone). Repo tests after fix: exit 0.

## F3 · Path traversal in load_template

**Severity:** critical · **Where:** `invoice_tools/templates.py:10` · **Proof attempts:** 1

load_template joins an untrusted name onto the template folder, so ?template=../../etc/passwd reads any file the server can read.

**Proof** `python -m pytest -q -s -p no:cacheprovider --noconftest proofbox_tests/test_traversal.py` (exit 0, 0.83s)

```
from invoice_tools import load_template


def test_template_traversal_reads_system_file():
    leaked = load_template('../../../../../../etc/passwd')
    assert 'root:' in leaked
    print('\nPROOFBOX_CONFIRMED read /etc/passwd through load_template: ' + leaked.splitlines()[0])
```

<details><summary>Sandbox output</summary>

```

PROOFBOX_CONFIRMED read /etc/passwd through load_template: root:x:0:0:root:/root:/bin/sh
.
1 passed in 0.01s
```
</details>

**Fix (verified):** Resolve the path with realpath and reject names that leave the templates folder.

```diff
--- a/invoice_tools/templates.py
+++ b/invoice_tools/templates.py
@@ -7,6 +7,8 @@
 
 def load_template(name: str) -> str:
     # Names come straight from the HTTP query string, e.g. ?template=modern.txt
-    path = os.path.join(TEMPLATE_DIR, name)
+    path = os.path.realpath(os.path.join(TEMPLATE_DIR, name))
+    if os.path.dirname(path) != os.path.realpath(TEMPLATE_DIR):
+        raise ValueError("template name escapes the template folder")
     with open(path, encoding="utf-8") as fh:
         return fh.read()
```

Proof after fix: exit 1 (bug gone). Repo tests after fix: exit 0.

## Contained

- **filesystem** Write to the root filesystem was blocked (read only)
- **network** Outbound network call was blocked (no network)
- **processes** Process explosion was capped by the pids limit
- **permissions** Destructive command was denied (non root, caps dropped)
- **memory** Memory bomb hit the memory ceiling
- **timeout** Runaway command was killed at the 30s limit

## Denied by policy

- `pip install pytest-timeout` · pkg.install · Installing packages is not allowed. Use the standard library and what the repo already has.

## Audit trail

- Events: 48
- Chain valid: True
- Head hash: `99e11ed52a1886770f2c0de00e5549dbe29d39fca92e1e98e2265f6607445540`
- Server signature (HMAC SHA256 of head): `fd104e4e12f718af721c6e8dc8f2cb40f220148707815241b66db3b5e68ca7b6`
