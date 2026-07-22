"""Stage 7 classifier for the narrow M1 explicit-function boundary."""

from __future__ import annotations

from dataclasses import dataclass

from math_drawing_assistant.engine.parser import (
    ParseMetrics,
    ParsedEquationInput,
    ParsedExpressionInput,
    ParsedInput,
)
from math_drawing_assistant.models.errors import ErrorCode, ErrorInfo, SourceSpan
from math_drawing_assistant.models.plot_specs import ExplicitExpressionSource
from math_drawing_assistant.models.restricted_ast import (
    BinaryOpNode,
    ConstantNode,
    FunctionCallNode,
    NumberNode,
    RestrictedExpression,
    SymbolNode,
    UnaryOpNode,
)
from math_drawing_assistant.models.state import PlotKind


@dataclass(frozen=True, slots=True)
class ExplicitFunctionCandidate:
    """A classified expression that still requires semantic validation."""

    expression: RestrictedExpression
    normalized_span: SourceSpan
    source_span: SourceSpan
    source_form: ExplicitExpressionSource
    metrics: ParseMetrics
    plot_kind: PlotKind = PlotKind.EXPLICIT_FUNCTION

    def __post_init__(self) -> None:
        if self.plot_kind is not PlotKind.EXPLICIT_FUNCTION:
            raise ValueError("Stage 7 candidates must be explicit functions.")


def classify_plot(
    parsed_input: ParsedInput,
) -> ExplicitFunctionCandidate | ErrorInfo:
    """Classify only expression, y=rhs, and lhs=y without algebraic solving."""

    if isinstance(parsed_input, ParsedExpressionInput):
        return ExplicitFunctionCandidate(
            expression=parsed_input.expression,
            normalized_span=parsed_input.normalized_span,
            source_span=parsed_input.source_span,
            source_form="expression",
            metrics=parsed_input.metrics,
        )
    if not isinstance(parsed_input, ParsedEquationInput):
        raise TypeError("parsed_input must be a parsed expression or equation.")

    left_is_y = _is_symbol(parsed_input.left, "y")
    right_is_y = _is_symbol(parsed_input.right, "y")
    if left_is_y:
        y_location = _first_symbol_span(parsed_input.right, "y")
        if y_location is not None:
            return _y_error(y_location)
        return ExplicitFunctionCandidate(
            expression=parsed_input.right,
            normalized_span=parsed_input.right_normalized_span,
            source_span=parsed_input.right_source_span,
            source_form="y_equals",
            metrics=parsed_input.metrics,
        )
    if right_is_y:
        y_location = _first_symbol_span(parsed_input.left, "y")
        if y_location is not None:
            return _y_error(y_location)
        return ExplicitFunctionCandidate(
            expression=parsed_input.left,
            normalized_span=parsed_input.left_normalized_span,
            source_span=parsed_input.left_source_span,
            source_form="equals_y",
            metrics=parsed_input.metrics,
        )

    equation_span = SourceSpan(
        parsed_input.left_source_span.start,
        parsed_input.right_source_span.end,
    )
    return _error(
        ErrorCode.UNSUPPORTED_EQUATION,
        "当前不支持该方程形式，请暂时改写为 y=... 的显函数形式。",
        "equation is outside the stage 7 direct-y explicit forms",
        equation_span,
    )


def _is_symbol(expression: RestrictedExpression, name: str) -> bool:
    return isinstance(expression, SymbolNode) and expression.name == name


def _first_symbol_span(
    expression: RestrictedExpression,
    name: str,
) -> SourceSpan | None:
    stack: list[RestrictedExpression] = [expression]
    while stack:
        node = stack.pop()
        if isinstance(node, SymbolNode):
            if node.name == name:
                return node.source_span
        elif isinstance(node, UnaryOpNode):
            stack.append(node.operand)
        elif isinstance(node, BinaryOpNode):
            stack.extend((node.right, node.left))
        elif isinstance(node, FunctionCallNode):
            stack.extend(reversed(node.arguments))
        elif isinstance(node, (NumberNode, ConstantNode)):
            continue
        else:
            raise TypeError("The parsed AST contains an unknown node type.")
    return None


def _y_error(source_location: SourceSpan) -> ErrorInfo:
    return _error(
        ErrorCode.EXPLICIT_FUNCTION_Y_NOT_ALLOWED,
        "显函数右侧只能使用自变量 x，不能再次使用 y。",
        "y appears outside the direct isolated equation side",
        source_location,
    )


def _error(
    code: ErrorCode,
    user_message: str,
    technical_message: str,
    source_location: SourceSpan,
) -> ErrorInfo:
    return ErrorInfo(
        code=code,
        user_message=user_message,
        technical_message=technical_message,
        field_name="input_text",
        source_location=source_location,
        recoverable=True,
    )


__all__ = ["ExplicitFunctionCandidate", "classify_plot"]
