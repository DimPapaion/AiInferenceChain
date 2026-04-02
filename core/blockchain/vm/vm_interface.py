"""
VMInterface — abstract base for InferenceChain smart contract execution.

The rest of the codebase always talks to this interface.
Swap simple_vm.py for an EVM adapter at any point without touching anything else.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class ExecutionResult:
    """Outcome of a contract deploy or call."""
    success:      bool
    return_value: Any            = None
    gas_used:     int            = 0
    error:        str | None     = None
    state_diff:   dict[str, Any] = None   # keys changed in contract state

    def __post_init__(self) -> None:
        if self.state_diff is None:
            self.state_diff = {}


class VMInterface(ABC):
    """
    Abstract VM — implement this to plug in any execution engine.

    Implementations:
      - SimpleVM  (core/blockchain/vm/simple_vm.py)  — current
      - EVMAdapter (core/blockchain/vm/evm_adapter.py) — future
    """

    @abstractmethod
    def deploy(
        self,
        bytecode:         str,
        abi:              dict,
        constructor_args: list[Any],
        deployer:         str,
        contract_address: str,
    ) -> ExecutionResult:
        """
        Deploy a new contract.

        Args:
            bytecode:         serialised VM bytecode
            abi:              function signatures dict
            constructor_args: arguments passed to the constructor
            deployer:         address of the deploying account
            contract_address: pre-computed address (from Chain)

        Returns:
            ExecutionResult with success flag and optional error.
        """

    @abstractmethod
    def call(
        self,
        contract_address: str,
        function:         str,
        args:             list[Any],
        caller:           str,
        value:            float,
        contract_state:   dict,
    ) -> ExecutionResult:
        """
        Call a function on a deployed contract.

        Args:
            contract_address: target contract
            function:         function name to invoke
            args:             positional arguments
            caller:           address initiating the call
            value:            INFER tokens sent with the call
            contract_state:   current mutable state of the contract

        Returns:
            ExecutionResult — state_diff contains state changes to apply.
        """

    @abstractmethod
    def get_abi(self, contract_address: str) -> dict | None:
        """Return the ABI of a deployed contract, or None if not found."""
