from __future__ import annotations

import ast
from collections.abc import Mapping

import sympy as sp

from felra.expressions import UnsafeExpressionError

_BINARY_OPERATORS = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.Pow: lambda a, b: a**b,
}
_UNARY_OPERATORS = {
    ast.UAdd: lambda a: +a,
    ast.USub: lambda a: -a,
}
_FUNCTIONS = {
    "abs": sp.Abs,
    "sqrt": sp.sqrt,
    "exp": sp.exp,
    "log": sp.log,
    "sin": sp.sin,
    "cos": sp.cos,
    "tan": sp.tan,
    "asin": sp.asin,
    "acos": sp.acos,
    "atan": sp.atan,
    "sinh": sp.sinh,
    "cosh": sp.cosh,
    "tanh": sp.tanh,
}
_CONSTANTS = {"pi": sp.pi, "e": sp.E}

_ASSUMPTION_KEYWORDS = {
    "real",
    "positive",
    "negative",
    "nonnegative",
    "nonpositive",
    "nonzero",
    "integer",
    "rational",
    "complex",
}


def make_symbols(
    variables: tuple[str, ...],
    assumptions: Mapping[str, tuple[str, ...]],
) -> dict[str, sp.Symbol]:
    """Build SymPy symbols for declared variables, applying declared assumptions.

    Unassumed variables default to ``real=True`` — FELRA's symbolic checks operate
    over real-valued research quantities, not the complex plane, unless a variable
    is explicitly declared ``complex``.
    """

    symbols: dict[str, sp.Symbol] = {}
    for name in variables:
        keywords = assumptions.get(name, ())
        for keyword in keywords:
            if keyword not in _ASSUMPTION_KEYWORDS:
                raise UnsafeExpressionError(
                    f"Unsupported symbolic assumption {keyword!r} for variable {name!r}"
                )
        kwargs = {keyword: True for keyword in keywords}
        if "complex" not in keywords and "real" not in kwargs:
            kwargs.setdefault("real", True)
        symbols[name] = sp.Symbol(name, **kwargs)
    return symbols


def _evaluate(node: ast.AST, symbols: Mapping[str, sp.Symbol]) -> sp.Expr:
    if isinstance(node, ast.Expression):
        return _evaluate(node.body, symbols)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool):
            raise UnsafeExpressionError("Boolean constants are not valid in symbolic expressions")
        if isinstance(node.value, (int, float)):
            return sp.nsimplify(node.value, rational=False)
        raise UnsafeExpressionError("Only numeric constants are allowed")
    if isinstance(node, ast.Name):
        if node.id in symbols:
            return symbols[node.id]
        if node.id in _CONSTANTS:
            return _CONSTANTS[node.id]
        raise UnsafeExpressionError(f"Unknown symbol {node.id!r}")
    if isinstance(node, ast.BinOp):
        operation = _BINARY_OPERATORS.get(type(node.op))
        if operation is None:
            raise UnsafeExpressionError(f"Unsupported binary operator {type(node.op).__name__}")
        return operation(_evaluate(node.left, symbols), _evaluate(node.right, symbols))
    if isinstance(node, ast.UnaryOp):
        operation = _UNARY_OPERATORS.get(type(node.op))
        if operation is None:
            raise UnsafeExpressionError(f"Unsupported unary operator {type(node.op).__name__}")
        return operation(_evaluate(node.operand, symbols))
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _FUNCTIONS:
            raise UnsafeExpressionError("Only approved symbolic functions may be called")
        if node.keywords:
            raise UnsafeExpressionError("Keyword arguments are not supported")
        function = _FUNCTIONS[node.func.id]
        return function(*[_evaluate(argument, symbols) for argument in node.args])
    raise UnsafeExpressionError(f"Unsupported syntax node {type(node).__name__}")


def parse_symbolic_expression(expression: str, symbols: Mapping[str, sp.Symbol]) -> sp.Expr:
    """Safely parse an algebraic expression into a SymPy expression.

    Deliberately narrower than :func:`felra.expressions.evaluate_expression`: only
    arithmetic (``+ - * / **``) and the approved function whitelist are supported —
    comparisons, Boolean logic, and conditionals are not meaningful for symbolic
    algebra and are rejected rather than silently coerced.
    """

    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise UnsafeExpressionError(f"Invalid expression syntax: {exc.msg}") from exc
    return _evaluate(tree, symbols)
