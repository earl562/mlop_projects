"""Deterministic, sandboxed arithmetic for the chat agent.

The agent must never do arithmetic "in its head" — LLM mental math is where the
Kevin Woo session produced wrong $/unit, wrong total project cost, and fabricated
density numbers. This evaluates a plain arithmetic expression with a restricted
AST (numbers and + - * / // % ** and parentheses only) so there is no code-exec
surface: no names, calls, attributes, indexing, or comprehensions are allowed.
"""

from __future__ import annotations

import ast
import operator
from typing import Callable

_BINOPS: dict[type[ast.operator], Callable[[float, float], float]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARYOPS: dict[type[ast.unaryop], Callable[[float], float]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

# Guard rails — keep a single expression cheap and bounded (no DoS via 9**9**9).
_MAX_EXPR_LEN = 200
_MAX_POW_EXPONENT = 100


class CalcError(ValueError):
    """Raised when an expression is unsafe, malformed, or not pure arithmetic."""


def _eval(node: ast.AST) -> float:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise CalcError("only numeric literals are allowed")
        return float(node.value)
    if isinstance(node, ast.BinOp):
        op = _BINOPS.get(type(node.op))
        if op is None:
            raise CalcError(f"operator {type(node.op).__name__} is not allowed")
        left, right = _eval(node.left), _eval(node.right)
        if type(node.op) is ast.Pow and abs(right) > _MAX_POW_EXPONENT:
            raise CalcError("exponent too large")
        if type(node.op) in (ast.Div, ast.FloorDiv, ast.Mod) and right == 0:
            raise CalcError("division by zero")
        return op(left, right)
    if isinstance(node, ast.UnaryOp):
        uop = _UNARYOPS.get(type(node.op))
        if uop is None:
            raise CalcError(f"unary {type(node.op).__name__} is not allowed")
        return uop(_eval(node.operand))
    raise CalcError(f"{type(node).__name__} is not allowed — arithmetic expressions only")


def safe_calculate(expression: str) -> float:
    """Evaluate a pure arithmetic expression. Raises ``CalcError`` on anything else.

    >>> safe_calculate("7 * 750000")
    5250000.0
    >>> safe_calculate("(4500000 - 280000 - 350*7710) / 7")  # doctest: +ELLIPSIS
    216...
    """
    if not isinstance(expression, str) or not expression.strip():
        raise CalcError("empty expression")
    if len(expression) > _MAX_EXPR_LEN:
        raise CalcError("expression too long")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise CalcError(f"could not parse: {exc.msg}") from exc
    result = _eval(tree.body)
    if result != result or result in (float("inf"), float("-inf")):  # NaN/inf guard
        raise CalcError("result is not a finite number")
    return float(result)
