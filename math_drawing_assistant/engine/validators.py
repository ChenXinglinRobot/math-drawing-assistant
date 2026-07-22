"""Typed semantic validation and the sole stage 7 production analysis entry."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal, TypeGuard

from math_drawing_assistant.config import ApplicationLimits, DEFAULT_LIMITS
from math_drawing_assistant.engine.equation_splitter import split_equation
from math_drawing_assistant.engine.normalizer import NormalizedInput, normalize_input
from math_drawing_assistant.engine.parser import parse_input
from math_drawing_assistant.engine.plot_classifier import (
    ExplicitFunctionCandidate,
    classify_plot,
)
from math_drawing_assistant.engine.tokenizer import (
    APPROVED_CONSTANTS,
    APPROVED_FUNCTIONS,
    APPROVED_VARIABLES,
    tokenize,
)
from math_drawing_assistant.models.errors import ErrorCode, ErrorInfo, SourceSpan
from math_drawing_assistant.models.plot_specs import (
    ValidatedExplicitExpression,
    _create_validated_explicit_expression,
    _issue_validated_expression_contract,
)
from math_drawing_assistant.models.restricted_ast import (
    BinaryOpNode,
    BinaryOperator,
    ConstantNode,
    FunctionCallNode,
    NumberNode,
    RestrictedExpression,
    SymbolNode,
    UnaryOpNode,
    UnaryOperator,
)


_UNARY_OPERATORS = frozenset({UnaryOperator.POSITIVE, UnaryOperator.NEGATIVE})
_BINARY_OPERATORS = frozenset(
    {
        BinaryOperator.ADD,
        BinaryOperator.SUBTRACT,
        BinaryOperator.MULTIPLY,
        BinaryOperator.DIVIDE,
        BinaryOperator.POWER,
    },
)
_SINGLE_ARGUMENT_FUNCTIONS = frozenset(
    {"sin", "cos", "tan", "sqrt", "abs", "exp", "ln", "lg"},
)
_EXACT_NODE_TYPES = frozenset(
    {
    NumberNode,
    SymbolNode,
    ConstantNode,
    UnaryOpNode,
    BinaryOpNode,
    FunctionCallNode,
    },
)


@dataclass(frozen=True, slots=True)
class ExplicitValidation:
    """Semantic confirmation used for composition, not a production Plot Spec."""

    candidate: ExplicitFunctionCandidate
    free_variables: tuple[Literal["x"], ...]


def analyze_explicit_function(
    input_text: str,
    *,
    limits: ApplicationLimits = DEFAULT_LIMITS,
) -> ValidatedExplicitExpression | ErrorInfo:
    """Run the one production-safe stage 7 path from raw text to validation."""

    if not isinstance(input_text, str):
        raise TypeError("input_text must be a string.")
    if not isinstance(limits, ApplicationLimits):
        raise TypeError("limits must be an ApplicationLimits value.")

    normalized = normalize_input(input_text, limits=limits)
    if isinstance(normalized, ErrorInfo):
        return normalized
    tokens = tokenize(normalized, limits=limits)
    if isinstance(tokens, ErrorInfo):
        return _map_unclosed_delimiter_to_eof(tokens, normalized)
    split = split_equation(tokens)
    if isinstance(split, ErrorInfo):
        return split
    parsed = parse_input(split, limits=limits)
    if isinstance(parsed, ErrorInfo):
        return parsed
    candidate = classify_plot(parsed)
    if isinstance(candidate, ErrorInfo):
        return candidate
    validation = validate_explicit_candidate(
        candidate,
        limits=limits,
    )
    if isinstance(validation, ErrorInfo):
        return validation
    contract = _issue_validated_expression_contract(
        parser_limits_version=validation.candidate.metrics.limits_version,
        active_limits_version=limits.version,
    )
    return _create_validated_explicit_expression(
        expression=validation.candidate.expression,
        normalized_input=normalized.text,
        normalized_span=validation.candidate.normalized_span,
        source_span=validation.candidate.source_span,
        source_form=validation.candidate.source_form,
        free_variables=validation.free_variables,
        contract=contract,
    )


def validate_explicit_candidate(
    candidate: ExplicitFunctionCandidate,
    *,
    limits: ApplicationLimits = DEFAULT_LIMITS,
) -> ExplicitValidation | ErrorInfo:
    """Validate a typed classifier result without repeating parser budgets."""

    if not isinstance(candidate, ExplicitFunctionCandidate):
        raise TypeError("candidate must be an ExplicitFunctionCandidate.")
    if not isinstance(limits, ApplicationLimits):
        raise TypeError("limits must be an ApplicationLimits value.")

    metrics = candidate.metrics
    if metrics.limits_version != limits.version:
        return _error(
            ErrorCode.INVALID_AST,
            "表达式验证版本不一致，请重新提交。",
            "parser metrics limits version mismatch",
            candidate.source_span,
        )
    try:
        limits.validate_input_complexity(
            character_count=0,
            token_count=metrics.token_count,
            ast_node_count=metrics.ast_node_count,
            nesting_depth=metrics.max_ast_depth,
            numeric_digits=0,
            decimal_places=0,
            rational_numerator_digits=0,
            rational_denominator_digits=0,
            absolute_exponent=metrics.max_absolute_literal_exponent,
            function_arguments=metrics.max_function_arguments,
        )
    except (TypeError, ValueError):
        return _error(
            ErrorCode.INVALID_AST,
            "表达式未通过结构预算，请重新提交。",
            "parser metrics failed centralized defensive validation",
            candidate.source_span,
        )

    structural_error = _validate_exact_restricted_tree(
        candidate.expression,
        root_span=candidate.source_span,
    )
    if structural_error is not None:
        return structural_error

    variables: set[str] = set()
    stack: list[RestrictedExpression] = [candidate.expression]
    while stack:
        node = stack.pop()
        if type(node) is NumberNode:
            if not _is_number_lexeme(node.lexeme):
                return _invalid_node("malformed numeric lexeme", node.source_span)
            continue
        if type(node) is SymbolNode:
            if node.name not in APPROVED_VARIABLES:
                return _invalid_node("symbol outside tokenizer whitelist", node.source_span)
            if node.name == "y":
                return _error(
                    ErrorCode.EXPLICIT_FUNCTION_Y_NOT_ALLOWED,
                    "显函数只能使用自变量 x，不能包含 y。",
                    "explicit function contains y",
                    node.source_span,
                )
            variables.add(node.name)
            continue
        if type(node) is ConstantNode:
            if node.name not in APPROVED_CONSTANTS:
                return _invalid_node("constant outside tokenizer whitelist", node.source_span)
            continue
        if type(node) is UnaryOpNode:
            if node.operator not in _UNARY_OPERATORS:
                return _invalid_node("unapproved unary operator", node.source_span)
            if not _is_exact_restricted_node(node.operand):
                return _invalid_node("unknown unary operand", node.source_span)
            stack.append(node.operand)
            continue
        if type(node) is BinaryOpNode:
            if node.operator not in _BINARY_OPERATORS:
                return _invalid_node("unapproved binary operator", node.source_span)
            if node.implicit and node.operator is not BinaryOperator.MULTIPLY:
                return _invalid_node("invalid implicit operator marker", node.source_span)
            if not _is_exact_restricted_node(node.left) or not _is_exact_restricted_node(
                node.right,
            ):
                return _invalid_node("unknown binary operand", node.source_span)
            if node.operator is BinaryOperator.POWER:
                exponent_error = _validate_exponent_form(node)
                if exponent_error is not None:
                    return exponent_error
            stack.extend((node.right, node.left))
            continue
        if type(node) is FunctionCallNode:
            if node.name not in APPROVED_FUNCTIONS:
                return _invalid_node("function outside tokenizer whitelist", node.source_span)
            if not all(_is_exact_restricted_node(argument) for argument in node.arguments):
                return _invalid_node("unknown function argument node", node.source_span)
            if node.name in _SINGLE_ARGUMENT_FUNCTIONS:
                if len(node.arguments) != 1:
                    return _error(
                        ErrorCode.FUNCTION_ARGUMENT_ERROR,
                        "函数参数数量不正确，请按支持的写法修改。",
                        "single-argument function failed defensive arity check",
                        node.source_span,
                    )
            elif node.name == "log":
                if len(node.arguments) == 1:
                    return _error(
                        ErrorCode.LOG_REQUIRES_BASE,
                        "请改用 ln(x)、lg(x) 或 log(x, b)。",
                        "log call omitted its required base",
                        node.source_span,
                    )
                if len(node.arguments) != 2:
                    return _error(
                        ErrorCode.FUNCTION_ARGUMENT_ERROR,
                        "log 必须写成 log(x, b)。",
                        "log failed defensive arity check",
                        node.source_span,
                    )
                if not _is_valid_log_base(node.arguments[1]):
                    return _error(
                        ErrorCode.INVALID_LOG_BASE,
                        "log 的底数必须是大于 0 且不等于 1 的数字字面量。",
                        "log base failed the stage 7 literal contract",
                        node.arguments[1].source_span,
                    )
            else:
                return _invalid_node("function lacks a published arity", node.source_span)
            stack.extend(reversed(node.arguments))
            continue
        return _invalid_node("unknown restricted AST node", candidate.source_span)

    free_variables: tuple[Literal["x"], ...] = ("x",) if "x" in variables else ()
    return ExplicitValidation(
        candidate=candidate,
        free_variables=free_variables,
    )


def _is_exact_restricted_node(value: object) -> TypeGuard[RestrictedExpression]:
    """Return whether value is one of the project-owned AST node classes exactly."""

    return type(value) in _EXACT_NODE_TYPES


def _validate_exact_restricted_tree(
    expression: object,
    *,
    root_span: SourceSpan,
) -> ErrorInfo | None:
    """Reject unknown nodes and subclasses before applying semantic validation."""

    stack: list[tuple[object, SourceSpan]] = [(expression, root_span)]
    while stack:
        node, parent_span = stack.pop()
        if not _is_exact_restricted_node(node):
            return _invalid_node("unknown or subclass restricted AST node", parent_span)
        if type(node) is UnaryOpNode:
            stack.append((node.operand, node.source_span))
        elif type(node) is BinaryOpNode:
            stack.extend(
                (
                    (node.right, node.source_span),
                    (node.left, node.source_span),
                ),
            )
        elif type(node) is FunctionCallNode:
            stack.extend((argument, node.source_span) for argument in node.arguments)
    return None


def _validate_exponent_form(node: BinaryOpNode) -> ErrorInfo | None:
    if _is_signed_integer_literal(node.right):
        return None
    if _is_literal_power_chain(node.right):
        return None
    if (
        type(node.left) is NumberNode
        and node.left.lexeme == "2"
        and type(node.right) is SymbolNode
        and node.right.name == "x"
    ):
        return None
    return _error(
        ErrorCode.UNSUPPORTED_EXPONENT,
        "当前仅支持整数指数、整数幂链和 2^x；其他指数形式暂未开放。",
        "exponent form is outside the narrow stage 7 contract",
        node.right.source_span,
    )


def _is_signed_integer_literal(expression: RestrictedExpression) -> bool:
    if type(expression) is NumberNode:
        return "." not in expression.lexeme
    return (
        type(expression) is UnaryOpNode
        and type(expression.operand) is NumberNode
        and "." not in expression.operand.lexeme
    )


def _is_literal_power_chain(expression: RestrictedExpression) -> bool:
    if type(expression) is not BinaryOpNode:
        return False
    if expression.operator is not BinaryOperator.POWER:
        return False
    if type(expression.left) is not NumberNode or "." in expression.left.lexeme:
        return False
    return _is_signed_integer_literal(expression.right) or _is_literal_power_chain(
        expression.right,
    )


def _is_valid_log_base(expression: RestrictedExpression) -> bool:
    if type(expression) is not NumberNode:
        return False
    try:
        value = Decimal(expression.lexeme)
    except InvalidOperation:
        return False
    return value.is_finite() and value > 0 and value != 1


def _is_number_lexeme(lexeme: str) -> bool:
    if not lexeme or lexeme.count(".") > 1:
        return False
    if "." not in lexeme:
        return lexeme.isascii() and lexeme.isdigit()
    integer, decimal = lexeme.split(".")
    if not decimal or not decimal.isascii() or not decimal.isdigit():
        return False
    return not integer or (integer.isascii() and integer.isdigit())


def _map_unclosed_delimiter_to_eof(
    error: ErrorInfo,
    normalized: NormalizedInput,
) -> ErrorInfo:
    if error.code is not ErrorCode.DELIMITER_MISMATCH:
        return error
    location = error.source_location
    if location is None:
        return error
    opening_delimiter = any(
        source_span == location and character in {"(", "|"}
        for character, source_span in zip(
            normalized.text,
            normalized.source_map.character_spans,
            strict=True,
        )
    )
    if not opening_delimiter:
        return error
    eof = len(normalized.source_map.original_text)
    return ErrorInfo(
        code=error.code,
        user_message="输入结束前缺少闭合括号或竖线，请补全后重试。",
        technical_message="unclosed delimiter mapped to original EOF",
        item_id=error.item_id,
        field_name=error.field_name,
        source_location=SourceSpan(eof, eof),
        recoverable=error.recoverable,
    )


def _invalid_node(technical_message: str, source_location: SourceSpan) -> ErrorInfo:
    return _error(
        ErrorCode.INVALID_AST,
        "表达式包含当前版本不支持的结构。",
        technical_message,
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


__all__ = [
    "ExplicitValidation",
    "analyze_explicit_function",
    "validate_explicit_candidate",
]
