from __future__ import annotations

import ast
from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


ALLOWED_IMPORTS = {"pandas", "numpy", "plotly", "plotly.express", "plotly.graph_objects"}


class SandboxValidationError(Exception):
    pass


def _validate_code(code: str) -> None:
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [n.name for n in node.names]
            for name in names:
                if not any(name == allowed or name.startswith(f"{allowed}.") for allowed in ALLOWED_IMPORTS):
                    raise SandboxValidationError(f"Import not allowed: {name}")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in {"open", "exec", "eval", "__import__", "compile"}:
                raise SandboxValidationError(f"Operation not allowed: {node.func.id}")


def execute_restricted(code: str, dataframes: dict[str, pd.DataFrame]) -> Any:
    _validate_code(code)
    safe_globals = {
        "__builtins__": {"len": len, "min": min, "max": max, "sum": sum, "range": range},
        "pd": pd,
        "px": px,
        "go": go,
    }
    safe_locals = dict(dataframes)
    exec(code, safe_globals, safe_locals)
    return safe_locals.get("result")
