// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title EtherVault
/// @notice Users deposit ETH and withdraw it later. The owner can pause withdrawals.
contract EtherVault {
    mapping(address => uint256) public balances;
    address public owner;
    bool public paused;

    event Deposit(address indexed user, uint256 amount);
    event Withdraw(address indexed user, uint256 amount);

    constructor() {
        owner = msg.sender;
    }

    function deposit() external payable {
        require(msg.value > 0, "zero deposit");
        balances[msg.sender] += msg.value;
        emit Deposit(msg.sender, msg.value);
    }

    function withdraw() external {
        require(!paused, "paused");
        uint256 amount = balances[msg.sender];
        require(amount > 0, "nothing to withdraw");

        (bool ok, ) = msg.sender.call{value: amount}("");
        require(ok, "transfer failed");

        balances[msg.sender] = 0;
        emit Withdraw(msg.sender, amount);
    }

    function setOwner(address newOwner) external {
        owner = newOwner;
    }

    function setPaused(bool value) external {
        require(msg.sender == owner, "not owner");
        paused = value;
    }
}
