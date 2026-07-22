"""Immutable project-owned AST nodes for the restricted formula language."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal, TypeAlias, TypeGuard

from math_drawing_assistant.models.errors import SourceSpan


VariableName: TypeAlias = Literal["x", "y"]
ConstantName: TypeAlias = Literal["pi", "E"]
FunctionName: TypeAlias = Literal[
    "sin",
    "cos",
    "tan",
    "sqrt",
    "abs",
    "exp",
    "log",
    "ln",
    "lg",
]

_VARIABLE_NAMES = frozenset({"x", "y"})
_CONSTANT_NAMES = frozenset({"pi", "E"})
_FUNCTION_ARITIES = {
    "sin": 1,
    "cos": 1,
    "tan": 1,
    "sqrt": 1,
    "abs": 1,
    "exp": 1,
    "log": 2,
    "ln": 1,
    "lg": 1,
}


def _is_number_lexeme(value: str) -> bool:
    if not value or value.count(".") > 1:
        return False
    if "." not in value:
        return value.isascii() and value.isdigit()
    integer, decimal = value.split(".")
    if not decimal or not decimal.isascii() or not decimal.isdigit():
        return False
    return not integer or (integer.isascii() and integer.isdigit())


def _is_restricted_node(value: object) -> TypeGuard[RestrictedExpression]:
    return type(value) in _RESTRICTED_NODE_TYPES


class UnaryOperator(str, Enum):
    """Closed prefix-operator set."""

    POSITIVE = "+"
    NEGATIVE = "-"


class BinaryOperator(str, Enum):
    """Closed binary-operator set."""

    ADD = "+"
    SUBTRACT = "-"
    MULTIPLY = "*"
    DIVIDE = "/"
    POWER = "^"


@dataclass(frozen=True, slots=True)
class SourceLocatedNode:
    """Shared normalized and original source ranges for every AST node."""

    normalized_span: SourceSpan
    source_span: SourceSpan

    def __post_init__(self) -> None:
        if type(self.normalized_span) is not SourceSpan:
            raise TypeError("normalized_span must be a SourceSpan.")
        if type(self.source_span) is not SourceSpan:
            raise TypeError("source_span must be a SourceSpan.")
        if self.normalized_span.start == self.normalized_span.end:
            raise ValueError("An AST node must cover normalized input.")
        if self.source_span.start == self.source_span.end:
            raise ValueError("An AST node must cover original input.")


@dataclass(frozen=True, slots=True)
class NumberNode(SourceLocatedNode):
    """A bounded numeric lexeme retained as text."""

    lexeme: str

    def __post_init__(self) -> None:
        SourceLocatedNode.__post_init__(self)
        if type(self.lexeme) is not str:
            raise TypeError("NumberNode.lexeme must be a string.")
        if not _is_number_lexeme(self.lexeme):
            raise ValueError("NumberNode.lexeme must be an unsigned numeric lexeme.")


@dataclass(frozen=True, slots=True)
class SymbolNode(SourceLocatedNode):
    """One approved variable token."""

    name: VariableName

    def __post_init__(self) -> None:
        SourceLocatedNode.__post_init__(self)
        if type(self.name) is not str:
            raise TypeError("SymbolNode.name must be a string.")
        if self.name not in _VARIABLE_NAMES:
            raise ValueError("SymbolNode.name must be x or y.")


@dataclass(frozen=True, slots=True)
class ConstantNode(SourceLocatedNode):
    """One approved named constant token."""

    name: ConstantName

    def __post_init__(self) -> None:
        SourceLocatedNode.__post_init__(self)
        if type(self.name) is not str:
            raise TypeError("ConstantNode.name must be a string.")
        if self.name not in _CONSTANT_NAMES:
            raise ValueError("ConstantNode.name must be pi or E.")


@dataclass(frozen=True, slots=True)
class UnaryOpNode(SourceLocatedNode):
    """A prefix unary operation."""

    operator: UnaryOperator
    operand: RestrictedExpression

    def __post_init__(self) -> None:
        SourceLocatedNode.__post_init__(self)
        if not isinstance(self.operator, UnaryOperator):
            raise TypeError("UnaryOpNode.operator must be a UnaryOperator.")
        if not _is_restricted_node(self.operand):
            raise TypeError("UnaryOpNode.operand must be a restricted AST node.")


@dataclass(frozen=True, slots=True)
class BinaryOpNode(SourceLocatedNode):
    """A binary operation, including approved implicit multiplication."""

    operator: BinaryOperator
    left: RestrictedExpression
    right: RestrictedExpression
    implicit: bool = False

    def __post_init__(self) -> None:
        SourceLocatedNode.__post_init__(self)
        if not isinstance(self.operator, BinaryOperator):
            raise TypeError("BinaryOpNode.operator must be a BinaryOperator.")
        if not _is_restricted_node(self.left):
            raise TypeError("BinaryOpNode.left must be a restricted AST node.")
        if not _is_restricted_node(self.right):
            raise TypeError("BinaryOpNode.right must be a restricted AST node.")
        if not isinstance(self.implicit, bool):
            raise TypeError("BinaryOpNode.implicit must be a bool.")
        if self.implicit and self.operator is not BinaryOperator.MULTIPLY:
            raise ValueError("Only multiplication can be implicit.")


@dataclass(frozen=True, slots=True)
class FunctionCallNode(SourceLocatedNode):
    """A call to one named function from the closed tokenizer whitelist."""

    name: FunctionName
    arguments: tuple[RestrictedExpression, ...]

    def __post_init__(self) -> None:
        SourceLocatedNode.__post_init__(self)
        if type(self.name) is not str:
            raise TypeError("FunctionCallNode.name must be a string.")
        if self.name not in _FUNCTION_ARITIES:
            raise ValueError("FunctionCallNode.name must be an approved function.")
        if type(self.arguments) is not tuple:
            raise TypeError("FunctionCallNode.arguments must be a tuple.")
        if not all(_is_restricted_node(argument) for argument in self.arguments):
            raise TypeError(
                "FunctionCallNode.arguments must contain only restricted AST nodes.",
            )
        expected_arity = _FUNCTION_ARITIES[self.name]
        if len(self.arguments) != expected_arity:
            raise ValueError(
                f"FunctionCallNode {self.name} requires {expected_arity} argument(s).",
            )


RestrictedExpression: TypeAlias = (
    NumberNode
    | SymbolNode
    | ConstantNode
    | UnaryOpNode
    | BinaryOpNode
    | FunctionCallNode
)

_RESTRICTED_NODE_TYPES = (
    NumberNode,
    SymbolNode,
    ConstantNode,
    UnaryOpNode,
    BinaryOpNode,
    FunctionCallNode,
)


def _validate_restricted_expression(
    expression: object,
) -> frozenset[VariableName]:
    """Recheck one complete AST graph and return its referenced variables."""

    variables: set[VariableName] = set()
    stack: list[object] = [expression]
    while stack:
        node = stack.pop()
        if not _is_restricted_node(node):
            raise TypeError("expression must contain only restricted AST nodes.")
        node.__post_init__()
        if isinstance(node, SymbolNode):
            variables.add(node.name)
        elif isinstance(node, UnaryOpNode):
            stack.append(node.operand)
        elif isinstance(node, BinaryOpNode):
            stack.extend((node.right, node.left))
        elif isinstance(node, FunctionCallNode):
            stack.extend(reversed(node.arguments))
    return frozenset(variables)


__all__ = [
    "BinaryOpNode",
    "BinaryOperator",
    "ConstantName",
    "ConstantNode",
    "FunctionCallNode",
    "FunctionName",
    "NumberNode",
    "RestrictedExpression",
    "SourceLocatedNode",
    "SymbolNode",
    "UnaryOpNode",
    "UnaryOperator",
    "VariableName",
]
