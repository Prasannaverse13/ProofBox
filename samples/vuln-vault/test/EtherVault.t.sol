// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {EtherVault} from "../src/EtherVault.sol";

contract EtherVaultTest {
    EtherVault vault;

    receive() external payable {}

    function setUp() public {
        vault = new EtherVault();
    }

    function test_DepositAndWithdraw() public {
        vault.deposit{value: 1 ether}();
        require(vault.balances(address(this)) == 1 ether, "balance");
        vault.withdraw();
        require(vault.balances(address(this)) == 0, "cleared");
    }
}
