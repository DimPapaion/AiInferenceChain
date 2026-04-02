"""
SimpleVM — lightweight stack-based contract execution engine.

Opcodes:
  PUSH <value>              — push literal onto stack
  POP                       — discard top of stack
  LOAD <key>                — push contract_state[key] onto stack
  STORE <key>               — pop top of stack, save to contract_state[key]
  ADD / SUB / MUL / DIV     — arithmetic on top two stack values
  EQ / LT / GT              — comparison, push bool result
  AND / OR / NOT            — logical ops
  ASSERT                    — pop top; raise if falsy
  TRANSFER <to> <amount>    — transfer INFER from contract balance
  BALANCE <address>         — push balance of address onto stack
  CALLER                    — push caller address onto stack
  VALUE                     — push INFER value sent with the call
  JUMP <label>              — unconditional jump to label
  JUMPI <label>             — conditional jump (pop condition)
  LABEL <name>              — define a jump target
  RETURN                    — pop top and set as return value, halt
  HALT                      — end execution (return None)

Bytecode format: list of instruction strings, one per line.
  Example:
    PUSH 100
    LOAD balance
    GT
    ASSERT
    LOAD balance
    PUSH 100
    SUB
    STORE balance
    RETURN
"""

from __future__ import annotations

from typing import Any

from .vm_interface import VMInterface, ExecutionResult
from ..constants import CONTRACT_GAS_LIMIT


class SimpleVMError(Exception):
    pass


class SimpleVM(VMInterface):
    def __init__(self) -> None:
        # contract_address → {bytecode, abi}
        self._contracts: dict[str, dict] = {}

    # ── VMInterface ───────────────────────────────────────────────────────────

    def deploy(
        self,
        bytecode:         str,
        abi:              dict,
        constructor_args: list[Any],
        deployer:         str,
        contract_address: str,
    ) -> ExecutionResult:
        self._contracts[contract_address] = {
            "bytecode": bytecode,
            "abi":      abi,
        }
        return ExecutionResult(success=True, gas_used=1)

    def call(
        self,
        contract_address: str,
        function:         str,
        args:             list[Any],
        caller:           str,
        value:            float,
        contract_state:   dict,
    ) -> ExecutionResult:
        contract = self._contracts.get(contract_address)
        if contract is None:
            return ExecutionResult(
                success=False,
                error=f"Contract {contract_address} not found",
            )

        abi = contract["abi"]
        if function not in abi:
            return ExecutionResult(
                success=False,
                error=f"Function '{function}' not in ABI",
            )

        # Resolve function bytecode from ABI entry
        fn_bytecode = abi[function].get("bytecode", contract["bytecode"])
        instructions = _parse(fn_bytecode)

        try:
            result, state_diff, gas = _execute(
                instructions  = instructions,
                args          = args,
                caller        = caller,
                value         = value,
                state         = dict(contract_state),   # work on a copy
                gas_limit     = CONTRACT_GAS_LIMIT,
            )
            return ExecutionResult(
                success      = True,
                return_value = result,
                gas_used     = gas,
                state_diff   = state_diff,
            )
        except SimpleVMError as e:
            return ExecutionResult(success=False, error=str(e))
        except Exception as e:
            return ExecutionResult(success=False, error=f"VM error: {e}")

    def get_abi(self, contract_address: str) -> dict | None:
        c = self._contracts.get(contract_address)
        return c["abi"] if c else None


# ── Execution engine ──────────────────────────────────────────────────────────

def _parse(bytecode: str) -> list[list[str]]:
    """Parse bytecode string into a list of [opcode, *operands] lists."""
    instructions = []
    for line in bytecode.strip().splitlines():
        parts = line.strip().split()
        if parts:
            instructions.append(parts)
    return instructions


def _execute(
    instructions: list[list[str]],
    args:         list[Any],
    caller:       str,
    value:        float,
    state:        dict,
    gas_limit:    int,
) -> tuple[Any, dict, int]:
    """
    Execute instructions.
    Returns (return_value, state_diff, gas_used).
    state_diff contains only the keys that were modified.
    """
    stack: list[Any]    = list(args)   # seed stack with call arguments
    labels: dict[str, int] = {}
    original_state = dict(state)
    gas = 0
    pc  = 0                            # program counter

    # First pass: collect label positions
    for i, instr in enumerate(instructions):
        if instr[0] == "LABEL":
            labels[instr[1]] = i

    # Execution loop
    return_value: Any = None

    while pc < len(instructions):
        if gas >= gas_limit:
            raise SimpleVMError(f"Gas limit ({gas_limit}) exceeded")

        instr = instructions[pc]
        op    = instr[0].upper()
        gas  += 1
        pc   += 1

        match op:
            case "PUSH":
                val = instr[1]
                # Try numeric coercion
                try:
                    val = int(val)
                except ValueError:
                    try:
                        val = float(val)
                    except ValueError:
                        pass   # keep as string
                stack.append(val)

            case "POP":
                _require_stack(stack, 1)
                stack.pop()

            case "LOAD":
                key = instr[1]
                stack.append(state.get(key, 0))

            case "STORE":
                key = instr[1]
                _require_stack(stack, 1)
                state[key] = stack.pop()

            case "ADD":
                _require_stack(stack, 2)
                b, a = stack.pop(), stack.pop()
                stack.append(a + b)

            case "SUB":
                _require_stack(stack, 2)
                b, a = stack.pop(), stack.pop()
                stack.append(a - b)

            case "MUL":
                _require_stack(stack, 2)
                b, a = stack.pop(), stack.pop()
                stack.append(a * b)

            case "DIV":
                _require_stack(stack, 2)
                b, a = stack.pop(), stack.pop()
                if b == 0:
                    raise SimpleVMError("Division by zero")
                stack.append(a / b)

            case "EQ":
                _require_stack(stack, 2)
                b, a = stack.pop(), stack.pop()
                stack.append(a == b)

            case "LT":
                _require_stack(stack, 2)
                b, a = stack.pop(), stack.pop()
                stack.append(a < b)

            case "GT":
                _require_stack(stack, 2)
                b, a = stack.pop(), stack.pop()
                stack.append(a > b)

            case "AND":
                _require_stack(stack, 2)
                b, a = stack.pop(), stack.pop()
                stack.append(bool(a) and bool(b))

            case "OR":
                _require_stack(stack, 2)
                b, a = stack.pop(), stack.pop()
                stack.append(bool(a) or bool(b))

            case "NOT":
                _require_stack(stack, 1)
                stack.append(not stack.pop())

            case "ASSERT":
                _require_stack(stack, 1)
                if not stack.pop():
                    raise SimpleVMError("Assertion failed")

            case "CALLER":
                stack.append(caller)

            case "VALUE":
                stack.append(value)

            case "BALANCE":
                addr = instr[1] if len(instr) > 1 else stack.pop()
                stack.append(state.get(f"_balance_{addr}", 0.0))

            case "TRANSFER":
                to     = instr[1]
                amount = float(instr[2]) if len(instr) > 2 else stack.pop()
                contract_bal = state.get("_contract_balance", 0.0)
                if contract_bal < amount:
                    raise SimpleVMError("Insufficient contract balance for transfer")
                state["_contract_balance"] = contract_bal - amount
                state[f"_transfer_{to}"] = state.get(f"_transfer_{to}", 0.0) + amount

            case "JUMP":
                label = instr[1]
                if label not in labels:
                    raise SimpleVMError(f"Unknown label: {label}")
                pc = labels[label] + 1   # jump past the LABEL instruction

            case "JUMPI":
                label = instr[1]
                _require_stack(stack, 1)
                if stack.pop():
                    if label not in labels:
                        raise SimpleVMError(f"Unknown label: {label}")
                    pc = labels[label] + 1

            case "LABEL":
                pass   # already handled in pre-pass

            case "RETURN":
                if stack:
                    return_value = stack.pop()
                break

            case "HALT":
                break

            case _:
                raise SimpleVMError(f"Unknown opcode: {op}")

    # Compute state diff
    state_diff = {k: v for k, v in state.items() if original_state.get(k) != v}
    return return_value, state_diff, gas


def _require_stack(stack: list, n: int) -> None:
    if len(stack) < n:
        raise SimpleVMError(f"Stack underflow: need {n} items, have {len(stack)}")
