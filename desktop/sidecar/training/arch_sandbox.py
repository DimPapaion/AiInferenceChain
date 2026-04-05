"""
Architecture upload validation.
Checks the user-supplied architecture.py for unsafe imports/calls,
then does a dry forward pass to verify output shape.
"""
import ast
import sys
import importlib.util
import traceback
import tempfile
import os
from pathlib import Path
from typing import Any

# Modules that must never appear in user-supplied architecture files
BLOCKED_IMPORTS = frozenset([
    "os", "sys", "subprocess", "socket", "shutil", "builtins",
    "importlib", "ctypes", "pickle", "shelve", "marshal",
    "pathlib", "glob", "tempfile", "signal", "atexit",
    "__builtin__",
])

BLOCKED_CALLS = frozenset(["exec", "eval", "compile", "__import__", "open"])


class UnsafeCodeError(ValueError):
    pass


def ast_safety_check(source: str) -> None:
    """
    Walk the AST and block dangerous imports / calls.
    Raises UnsafeCodeError if anything suspicious is found.
    """
    tree = ast.parse(source)

    for node in ast.walk(tree):
        # import x  /  import x as y
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in BLOCKED_IMPORTS:
                    raise UnsafeCodeError(f"Blocked import: {alias.name}")

        # from x import y
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                root = node.module.split(".")[0]
                if root in BLOCKED_IMPORTS:
                    raise UnsafeCodeError(f"Blocked import: {node.module}")

        # exec(...) / eval(...) / open(...) etc.
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id in BLOCKED_CALLS:
                    raise UnsafeCodeError(f"Blocked call: {node.func.id}()")
            elif isinstance(node.func, ast.Attribute):
                if node.func.attr in BLOCKED_CALLS:
                    raise UnsafeCodeError(f"Blocked call: .{node.func.attr}()")


def load_model_class(source: str, tmp_dir: str):
    """
    Write source to a temp file and import it in an isolated manner.
    Returns the first nn.Module subclass found in the module.
    """
    fpath = os.path.join(tmp_dir, "_user_arch.py")
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(source)

    spec = importlib.util.spec_from_file_location("_user_arch", fpath)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    import torch.nn as nn
    candidates = [
        v for v in vars(mod).values()
        if isinstance(v, type) and issubclass(v, nn.Module) and v is not nn.Module
    ]
    if not candidates:
        raise ValueError("No nn.Module subclass found in the file.")
    return candidates[0]


def dry_run(model_cls: Any, num_classes: int, input_shape=(1, 3, 32, 32)):
    """
    Instantiate the model and run a random forward pass.
    Returns output shape on success.
    """
    import torch
    try:
        model = model_cls(num_classes=num_classes)
    except TypeError:
        model = model_cls()

    model.eval()
    with torch.no_grad():
        dummy = torch.randn(*input_shape)
        out = model(dummy)

    return list(out.shape)


def validate_architecture(source: str, num_classes: int = 10):
    """
    Full validation pipeline:
      1. AST safety scan
      2. Load model class
      3. Dry forward pass
    Returns dict with 'ok', 'output_shape', 'model_name', or 'error'.
    """
    try:
        ast_safety_check(source)
    except UnsafeCodeError as e:
        return {"ok": False, "error": f"Unsafe code detected: {e}"}
    except SyntaxError as e:
        return {"ok": False, "error": f"Syntax error: {e}"}

    with tempfile.TemporaryDirectory() as tmp:
        try:
            model_cls = load_model_class(source, tmp)
            output_shape = dry_run(model_cls, num_classes)
            return {
                "ok": True,
                "model_name": model_cls.__name__,
                "output_shape": output_shape,
            }
        except Exception as e:
            return {"ok": False, "error": traceback.format_exc(limit=5)}
