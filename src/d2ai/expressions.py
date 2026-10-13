"""Safe evaluation of small arithmetic expressions used for derived columns.

Domain rules such as unit conversions ("(water_temp_f - 32) * 5 / 9") are
written in configuration files. This module evaluates them without `eval`,
allowing only arithmetic, comparisons, a few functions, and column names.
"""

from __future__ import annotations

import ast
import operator
from typing import Any, Mapping

_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPS = {ast.USub: operator.neg, ast.UAdd: operator.pos}
_COMPARE_OPS = {
    ast.Lt: operator.lt, ast.LtE: operator.le, ast.Gt: operator.gt,
    ast.GtE: operator.ge, ast.Eq: operator.eq, ast.NotEq: operator.ne,
}
_FUNCTIONS = {"abs": abs, "min": min, "max": max, "round": round}


class ExpressionError(ValueError):
    """Raised when an expression uses something that is not allowed."""


def compile_expression(text: str) -> ast.Expression:
    tree = ast.parse(text, mode="eval")
    for node in ast.walk(tree):
        allowed = (
            ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Name,
            ast.Load, ast.Call, ast.Compare, *_BIN_OPS, *_UNARY_OPS, *_COMPARE_OPS,
        )
        if not isinstance(node, allowed):
            raise ExpressionError(f"not allowed in expression {text!r}: {type(node).__name__}")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in _FUNCTIONS:
                raise ExpressionError(f"only {sorted(_FUNCTIONS)} may be called in {text!r}")
    return tree


def evaluate(tree: ast.Expression, row: Mapping[str, Any]) -> Any:
    """Evaluate a compiled expression against one row. Missing inputs give None."""

    def _eval(node: ast.AST) -> Any:
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            if node.id in _FUNCTIONS:
                return _FUNCTIONS[node.id]
            value = row.get(node.id)
            if value is None:
                raise _Missing
            return value
        if isinstance(node, ast.UnaryOp):
            return _UNARY_OPS[type(node.op)](_eval(node.operand))
        if isinstance(node, ast.BinOp):
            return _BIN_OPS[type(node.op)](_eval(node.left), _eval(node.right))
        if isinstance(node, ast.Compare):
            left = _eval(node.left)
            for op, comparator in zip(node.ops, node.comparators):
                right = _eval(comparator)
                if not _COMPARE_OPS[type(op)](left, right):
                    return False
                left = right
            return True
        if isinstance(node, ast.Call):
            func = _FUNCTIONS[node.func.id]  # type: ignore[union-attr]
            return func(*[_eval(arg) for arg in node.args])
        raise ExpressionError(f"unsupported node {type(node).__name__}")

    try:
        return _eval(tree)
    except _Missing:
        return None
    except ZeroDivisionError:
        return None


class _Missing(Exception):
    pass
