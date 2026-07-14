from __future__ import annotations

import ast
import operator
from collections.abc import Mapping
from typing import Any

import numpy as np


class UnsafeExpressionError(ValueError):
    """Raised when an expression uses syntax outside FELRA's numerical subset."""


_BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.BitAnd: np.logical_and,
    ast.BitOr: np.logical_or,
}
_UNARY_OPERATORS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
    ast.Not: np.logical_not,
    ast.Invert: np.logical_not,
}
_COMPARISON_OPERATORS = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
}
_FUNCTIONS = {
    "abs": np.abs,
    "sqrt": np.sqrt,
    "exp": np.exp,
    "log": np.log,
    "log10": np.log10,
    "sin": np.sin,
    "cos": np.cos,
    "tan": np.tan,
    "arcsin": np.arcsin,
    "arccos": np.arccos,
    "arctan": np.arctan,
    "minimum": np.minimum,
    "maximum": np.maximum,
    "clip": np.clip,
    "where": np.where,
    "isfinite": np.isfinite,
    "isnan": np.isnan,
}
_CONSTANTS = {"pi": np.pi, "e": np.e, "inf": np.inf}


def _evaluate(node: ast.AST, variables: Mapping[str, Any]) -> Any:
    if isinstance(node, ast.Expression):
        return _evaluate(node.body, variables)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool | int | float):
            return node.value
        raise UnsafeExpressionError("Only Boolean and numeric constants are allowed")
    if isinstance(node, ast.Name):
        if node.id in variables:
            return variables[node.id]
        if node.id in _CONSTANTS:
            return _CONSTANTS[node.id]
        raise UnsafeExpressionError(f"Unknown name {node.id!r}")
    if isinstance(node, ast.BinOp):
        operation = _BINARY_OPERATORS.get(type(node.op))
        if operation is None:
            raise UnsafeExpressionError(f"Unsupported binary operator {type(node.op).__name__}")
        return operation(_evaluate(node.left, variables), _evaluate(node.right, variables))
    if isinstance(node, ast.UnaryOp):
        operation = _UNARY_OPERATORS.get(type(node.op))
        if operation is None:
            raise UnsafeExpressionError(f"Unsupported unary operator {type(node.op).__name__}")
        return operation(_evaluate(node.operand, variables))
    if isinstance(node, ast.BoolOp):
        values = [_evaluate(value, variables) for value in node.values]
        operation = np.logical_and if isinstance(node.op, ast.And) else np.logical_or
        result = values[0]
        for value in values[1:]:
            result = operation(result, value)
        return result
    if isinstance(node, ast.Compare):
        left = _evaluate(node.left, variables)
        comparisons: list[Any] = []
        for operator_node, comparator in zip(node.ops, node.comparators, strict=True):
            operation = _COMPARISON_OPERATORS.get(type(operator_node))
            if operation is None:
                raise UnsafeExpressionError(
                    f"Unsupported comparison {type(operator_node).__name__}"
                )
            right = _evaluate(comparator, variables)
            comparisons.append(operation(left, right))
            left = right
        result = comparisons[0]
        for comparison in comparisons[1:]:
            result = np.logical_and(result, comparison)
        return result
    if isinstance(node, ast.IfExp):
        return np.where(
            _evaluate(node.test, variables),
            _evaluate(node.body, variables),
            _evaluate(node.orelse, variables),
        )
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _FUNCTIONS:
            raise UnsafeExpressionError("Only approved numerical functions may be called")
        if node.keywords:
            raise UnsafeExpressionError("Keyword arguments are not supported")
        function = _FUNCTIONS[node.func.id]
        return function(*[_evaluate(argument, variables) for argument in node.args])
    raise UnsafeExpressionError(f"Unsupported syntax node {type(node).__name__}")


def evaluate_expression(expression: str, variables: Mapping[str, Any]) -> Any:
    """Safely evaluate a numerical expression without Python ``eval``.

    The supported subset includes arithmetic, comparisons, Boolean composition,
    conditional expressions, and a conservative list of NumPy functions.
    """

    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise UnsafeExpressionError(f"Invalid expression syntax: {exc.msg}") from exc
    return _evaluate(tree, variables)
