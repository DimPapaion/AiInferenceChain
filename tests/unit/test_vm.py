"""
Unit tests for core/blockchain/vm/simple_vm.py
"""

import pytest
from core.blockchain import SimpleVM, ExecutionResult

CALLER   = "a" * 40
CONTRACT = "c" * 40


def deploy(vm, bytecode, abi=None):
    abi = abi or {"main": {"bytecode": bytecode}}
    result = vm.deploy(
        bytecode=bytecode, abi=abi,
        constructor_args=[], deployer=CALLER,
        contract_address=CONTRACT,
    )
    assert result.success
    return CONTRACT


def call(vm, function, args=None, state=None, value=0.0):
    return vm.call(
        contract_address=CONTRACT,
        function=function,
        args=args or [],
        caller=CALLER,
        value=value,
        contract_state=state or {},
    )


class TestDeploy:
    def test_deploy_succeeds(self):
        vm  = SimpleVM()
        res = vm.deploy("PUSH 1\nRETURN", {"main": {}}, [], CALLER, CONTRACT)
        assert res.success

    def test_get_abi_after_deploy(self):
        vm  = SimpleVM()
        abi = {"main": {"bytecode": "PUSH 1\nRETURN"}}
        vm.deploy("PUSH 1\nRETURN", abi, [], CALLER, CONTRACT)
        assert vm.get_abi(CONTRACT) == abi

    def test_get_abi_unknown_contract(self):
        vm = SimpleVM()
        assert vm.get_abi("unknown") is None


class TestArithmetic:
    def test_push_return(self):
        vm  = SimpleVM()
        deploy(vm, "PUSH 42\nRETURN")
        res = call(vm, "main")
        assert res.success
        assert res.return_value == 42

    def test_add(self):
        vm = SimpleVM()
        deploy(vm, "PUSH 10\nPUSH 20\nADD\nRETURN")
        res = call(vm, "main")
        assert res.return_value == 30

    def test_sub(self):
        vm = SimpleVM()
        deploy(vm, "PUSH 30\nPUSH 10\nSUB\nRETURN")
        res = call(vm, "main")
        assert res.return_value == 20

    def test_mul(self):
        vm = SimpleVM()
        deploy(vm, "PUSH 6\nPUSH 7\nMUL\nRETURN")
        res = call(vm, "main")
        assert res.return_value == 42

    def test_div(self):
        vm = SimpleVM()
        deploy(vm, "PUSH 100\nPUSH 4\nDIV\nRETURN")
        res = call(vm, "main")
        assert res.return_value == pytest.approx(25.0)

    def test_div_by_zero_fails(self):
        vm = SimpleVM()
        deploy(vm, "PUSH 10\nPUSH 0\nDIV\nRETURN")
        res = call(vm, "main")
        assert not res.success
        assert "zero" in res.error.lower()


class TestStateOperations:
    def test_store_and_load(self):
        vm = SimpleVM()
        deploy(vm, "PUSH 99\nSTORE balance\nLOAD balance\nRETURN")
        res = call(vm, "main", state={})
        assert res.success
        assert res.return_value == 99
        assert res.state_diff["balance"] == 99

    def test_load_missing_key_returns_zero(self):
        vm = SimpleVM()
        deploy(vm, "LOAD missing_key\nRETURN")
        res = call(vm, "main", state={})
        assert res.return_value == 0

    def test_state_diff_only_contains_changed_keys(self):
        vm = SimpleVM()
        deploy(vm, "PUSH 5\nSTORE x\nRETURN")
        res = call(vm, "main", state={"x": 5, "y": 10})
        # x unchanged (5→5), y not touched
        assert "y" not in res.state_diff


class TestComparisons:
    def test_eq_true(self):
        vm = SimpleVM()
        deploy(vm, "PUSH 5\nPUSH 5\nEQ\nRETURN")
        assert call(vm, "main").return_value is True

    def test_eq_false(self):
        vm = SimpleVM()
        deploy(vm, "PUSH 5\nPUSH 6\nEQ\nRETURN")
        assert call(vm, "main").return_value is False

    def test_gt(self):
        vm = SimpleVM()
        deploy(vm, "PUSH 10\nPUSH 3\nGT\nRETURN")
        assert call(vm, "main").return_value is True

    def test_lt(self):
        vm = SimpleVM()
        deploy(vm, "PUSH 3\nPUSH 10\nLT\nRETURN")
        assert call(vm, "main").return_value is True


class TestControlFlow:
    def test_assert_passes(self):
        vm = SimpleVM()
        deploy(vm, "PUSH 1\nASSERT\nPUSH 42\nRETURN")
        res = call(vm, "main")
        assert res.success
        assert res.return_value == 42

    def test_assert_fails(self):
        vm = SimpleVM()
        deploy(vm, "PUSH 0\nASSERT\nPUSH 42\nRETURN")
        res = call(vm, "main")
        assert not res.success
        assert "assertion" in res.error.lower()

    def test_jump(self):
        vm = SimpleVM()
        bytecode = "JUMP end\nPUSH 999\nLABEL end\nPUSH 1\nRETURN"
        deploy(vm, bytecode)
        res = call(vm, "main")
        assert res.return_value == 1   # 999 was skipped

    def test_jumpi_conditional_taken(self):
        vm = SimpleVM()
        bytecode = "PUSH 1\nJUMPI done\nPUSH 0\nRETURN\nLABEL done\nPUSH 1\nRETURN"
        deploy(vm, bytecode)
        res = call(vm, "main")
        assert res.return_value == 1

    def test_jumpi_conditional_not_taken(self):
        vm = SimpleVM()
        bytecode = "PUSH 0\nJUMPI done\nPUSH 99\nRETURN\nLABEL done\nPUSH 1\nRETURN"
        deploy(vm, bytecode)
        res = call(vm, "main")
        assert res.return_value == 99


class TestContextOps:
    def test_caller(self):
        vm = SimpleVM()
        deploy(vm, "CALLER\nRETURN")
        res = call(vm, "main")
        assert res.return_value == CALLER

    def test_value(self):
        vm = SimpleVM()
        deploy(vm, "VALUE\nRETURN")
        res = call(vm, "main", value=25.0)
        assert res.return_value == pytest.approx(25.0)


class TestGasLimit:
    def test_gas_limit_exceeded(self):
        from core.blockchain.constants import CONTRACT_GAS_LIMIT
        from core.blockchain.vm.simple_vm import SimpleVM as SVM, _parse, _execute
        # Build a program longer than gas limit
        instructions = [["PUSH", "1"]] * (CONTRACT_GAS_LIMIT + 10)
        with pytest.raises(Exception, match="Gas limit"):
            _execute(instructions, args=[], caller=CALLER, value=0.0,
                     state={}, gas_limit=CONTRACT_GAS_LIMIT)


class TestUnknownContract:
    def test_call_unknown_contract_fails(self):
        vm  = SimpleVM()
        res = vm.call("unknown_contract", "main", [], CALLER, 0.0, {})
        assert not res.success
        assert "not found" in res.error
