"""Behavioral and construction-budget tests for the restricted parser."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, is_dataclass, replace
from typing import cast

import pytest

from math_drawing_assistant.config import ApplicationLimits, DEFAULT_LIMITS
from math_drawing_assistant.engine import (
    NormalizedInput,
    ParsedEquationInput,
    ParsedExpressionInput,
    normalize_input,
    parse_input,
    split_equation,
    tokenize,
)
from math_drawing_assistant.models import (
    BinaryOpNode,
    BinaryOperator,
    ConstantNode,
    ErrorCode,
    ErrorInfo,
    FunctionCallNode,
    NumberNode,
    RestrictedExpression,
    SourceSpan,
    SymbolNode,
    UnaryOpNode,
    UnaryOperator,
)


def _parse(
    text: str,
    *,
    limits: ApplicationLimits = DEFAULT_LIMITS,
) -> ParsedExpressionInput | ParsedEquationInput | ErrorInfo:
    normalized = normalize_input(text, limits=limits)
    assert isinstance(normalized, NormalizedInput), normalized
    tokens = tokenize(normalized, limits=limits)
    assert isinstance(tokens, tuple), tokens
    split = split_equation(tokens)
    assert not isinstance(split, ErrorInfo), split
    return parse_input(split, limits=limits)


def _expression(text: str) -> ParsedExpressionInput:
    parsed = _parse(text)
    assert isinstance(parsed, ParsedExpressionInput), parsed
    return parsed


def test_ast_contracts_are_frozen_slotted_typed_and_keep_tuple_arguments() -> None:
    parsed = _expression("log(x,2)")
    root = parsed.expression
    assert isinstance(root, FunctionCallNode)
    assert isinstance(root.arguments, tuple)

    node_types = (
        NumberNode,
        SymbolNode,
        UnaryOpNode,
        BinaryOpNode,
        FunctionCallNode,
    )
    for node_type in node_types:
        assert is_dataclass(node_type)
        assert node_type.__dataclass_params__.frozen is True
        assert "__dict__" not in node_type.__dict__
        assert all(field.type is not None for field in fields(node_type))

    with pytest.raises(FrozenInstanceError):
        root.name = "sin"  # type: ignore[misc]  # frozen contract probe


def test_restricted_leaf_constructors_enforce_closed_lexemes_and_names() -> None:
    span = SourceSpan(0, 1)

    for lexeme in ("", "1..2", "1.", "."):
        with pytest.raises(ValueError):
            NumberNode(span, span, lexeme)
    with pytest.raises(ValueError):
        SymbolNode(span, span, "z")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        ConstantNode(span, span, "tau")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        FunctionCallNode(
            span,
            span,
            "unknown",  # type: ignore[arg-type]
            (NumberNode(span, span, "1"),),
        )


def test_restricted_parent_constructors_reject_open_or_mutable_payloads() -> None:
    span = SourceSpan(0, 1)
    number = NumberNode(span, span, "1")
    invalid_payloads = ({"items": []}, [number], object())

    for payload in invalid_payloads:
        invalid = cast(RestrictedExpression, payload)
        with pytest.raises(TypeError):
            UnaryOpNode(span, span, UnaryOperator.NEGATIVE, invalid)
        with pytest.raises(TypeError):
            BinaryOpNode(span, span, BinaryOperator.ADD, invalid, number)
        with pytest.raises(TypeError):
            BinaryOpNode(span, span, BinaryOperator.ADD, number, invalid)
        with pytest.raises(TypeError):
            FunctionCallNode(span, span, "sin", (invalid,))

    with pytest.raises(TypeError):
        FunctionCallNode(
            span,
            span,
            "sin",
            cast(tuple[RestrictedExpression, ...], [number]),
        )
    with pytest.raises(ValueError):
        FunctionCallNode(span, span, "sin", (number, number))


def test_function_argument_tuple_is_detached_from_a_mutable_source_list() -> None:
    span = SourceSpan(0, 1)
    number = NumberNode(span, span, "1")
    argument_buffer = [number]
    call = FunctionCallNode(span, span, "sin", tuple(argument_buffer))

    argument_buffer.append(NumberNode(span, span, "2"))
    assert call.arguments == (number,)


def test_unary_minus_binds_less_tightly_than_power() -> None:
    root = _expression("-x^2").expression

    assert isinstance(root, UnaryOpNode)
    assert root.operator is UnaryOperator.NEGATIVE
    assert isinstance(root.operand, BinaryOpNode)
    assert root.operand.operator is BinaryOperator.POWER


def test_parentheses_preserve_negative_base_before_power() -> None:
    root = _expression("(-x)^2").expression

    assert isinstance(root, BinaryOpNode)
    assert root.operator is BinaryOperator.POWER
    assert isinstance(root.left, UnaryOpNode)
    assert root.left.operator is UnaryOperator.NEGATIVE


def test_negative_exponent_and_outer_negative_have_the_required_shape() -> None:
    root = _expression("-x^-2").expression

    assert isinstance(root, UnaryOpNode)
    power = root.operand
    assert isinstance(power, BinaryOpNode)
    assert power.operator is BinaryOperator.POWER
    assert isinstance(power.right, UnaryOpNode)
    assert power.right.operator is UnaryOperator.NEGATIVE
    assert isinstance(power.right.operand, NumberNode)
    assert power.right.operand.lexeme == "2"


def test_power_is_right_associative_without_constant_folding() -> None:
    root = _expression("x^2^3").expression

    assert isinstance(root, BinaryOpNode)
    assert root.operator is BinaryOperator.POWER
    assert isinstance(root.right, BinaryOpNode)
    assert root.right.operator is BinaryOperator.POWER
    assert isinstance(root.right.left, NumberNode)
    assert root.right.left.lexeme == "2"
    assert isinstance(root.right.right, NumberNode)
    assert root.right.right.lexeme == "3"


@pytest.mark.parametrize(
    ("text", "outer", "inner"),
    [
        ("x/2*3", BinaryOperator.MULTIPLY, BinaryOperator.DIVIDE),
        ("x-2+3", BinaryOperator.ADD, BinaryOperator.SUBTRACT),
    ],
)
def test_same_precedence_operators_are_left_associative(
    text: str,
    outer: BinaryOperator,
    inner: BinaryOperator,
) -> None:
    root = _expression(text).expression

    assert isinstance(root, BinaryOpNode)
    assert root.operator is outer
    assert isinstance(root.left, BinaryOpNode)
    assert root.left.operator is inner


@pytest.mark.parametrize("text", ["2x", "2(x+1)", "(x+1)(x-1)"])
def test_only_published_implicit_multiplication_pairs_are_constructed(text: str) -> None:
    root = _expression(text).expression

    assert isinstance(root, BinaryOpNode)
    assert root.operator is BinaryOperator.MULTIPLY
    assert root.implicit is True


@pytest.mark.parametrize(
    "text",
    ["x2", "x(x+1)", "(x+1)x", "2sin(x)", "2pi", "sin(x)abs(x)"],
)
def test_unpublished_implicit_multiplication_pairs_are_rejected(text: str) -> None:
    result = _parse(text)

    assert isinstance(result, ErrorInfo)
    assert result.code is ErrorCode.IMPLICIT_MULTIPLICATION_NOT_ALLOWED
    assert result.source_location is not None


def test_bar_uses_the_same_abs_function_node_as_function_syntax() -> None:
    bar = _expression("|x|").expression
    function = _expression("abs(x)").expression

    assert isinstance(bar, FunctionCallNode)
    assert isinstance(function, FunctionCallNode)
    assert bar.name == function.name == "abs"
    assert len(bar.arguments) == len(function.arguments) == 1
    assert isinstance(bar.arguments[0], SymbolNode)


def test_parallel_bars_and_function_nested_abs_are_supported() -> None:
    parallel = _expression("|x|+|x+1|").expression
    nested = _expression("abs(abs(x))").expression

    assert isinstance(parallel, BinaryOpNode)
    assert isinstance(parallel.left, FunctionCallNode)
    assert isinstance(parallel.right, FunctionCallNode)
    assert isinstance(nested, FunctionCallNode)
    assert isinstance(nested.arguments[0], FunctionCallNode)


def test_directly_nested_bars_are_rejected_without_backtracking() -> None:
    result = _parse("||x||")

    assert isinstance(result, ErrorInfo)
    assert result.code is ErrorCode.NESTED_ABSOLUTE_VALUE
    assert result.source_location == SourceSpan(1, 2)


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("sin", ErrorCode.FUNCTION_CALL_REQUIRED),
        ("sin()", ErrorCode.FUNCTION_ARGUMENT_ERROR),
        ("sin(x,1)", ErrorCode.FUNCTION_ARGUMENT_ERROR),
        ("sqrt()", ErrorCode.FUNCTION_ARGUMENT_ERROR),
        ("sqrt(x,2)", ErrorCode.FUNCTION_ARGUMENT_ERROR),
        ("log()", ErrorCode.FUNCTION_ARGUMENT_ERROR),
        ("log(x)", ErrorCode.LOG_REQUIRES_BASE),
        ("log(x,)", ErrorCode.FUNCTION_ARGUMENT_ERROR),
        ("log(,10)", ErrorCode.FUNCTION_ARGUMENT_ERROR),
        ("log(x,10,2)", ErrorCode.FUNCTION_ARGUMENT_ERROR),
    ],
)
def test_function_call_shape_and_arity_errors_are_stable(
    text: str,
    code: ErrorCode,
) -> None:
    result = _parse(text)

    assert isinstance(result, ErrorInfo)
    assert result.code is code
    assert result.recoverable is True


def test_expression_and_equation_tokens_are_completely_consumed() -> None:
    expression = _expression("x+1")
    equation = _parse("y=x^2")

    assert expression.metrics.token_count == 3
    assert isinstance(equation, ParsedEquationInput)
    assert equation.metrics.token_count == 5
    assert isinstance(equation.left, SymbolNode)
    assert isinstance(equation.right, BinaryOpNode)


def test_ast_source_spans_follow_unicode_fullwidth_and_many_to_one_mapping() -> None:
    superscript = _expression("x²").expression
    stars = _expression(" x**2 ").expression
    fullwidth = _expression("２（x＋１）").expression
    bars = _expression("｜x｜").expression

    assert superscript.normalized_span == SourceSpan(0, 3)
    assert superscript.source_span == SourceSpan(0, 2)
    assert stars.normalized_span == SourceSpan(0, 3)
    assert stars.source_span == SourceSpan(1, 5)
    assert fullwidth.source_span == SourceSpan(0, 6)
    assert bars.source_span == SourceSpan(0, 3)


def test_ast_node_limit_accepts_inside_and_exact_then_rejects_one_more() -> None:
    limits = replace(DEFAULT_LIMITS, max_ast_nodes=9)

    inside = _parse("x+x+x+x", limits=limits)
    exact = _parse("x+x+x+x+x", limits=limits)
    over = _parse("x+x+x+x+x+x", limits=limits)

    assert isinstance(inside, ParsedExpressionInput)
    assert inside.metrics.ast_node_count == 7
    assert isinstance(exact, ParsedExpressionInput)
    assert exact.metrics.ast_node_count == limits.max_ast_nodes
    assert isinstance(over, ErrorInfo)
    assert over.code is ErrorCode.AST_NODE_LIMIT_EXCEEDED


def test_ast_depth_limit_accepts_inside_and_exact_then_rejects_one_more() -> None:
    limits = replace(DEFAULT_LIMITS, max_nesting_depth=5)

    inside = _parse("---x", limits=limits)
    exact = _parse("----x", limits=limits)
    over = _parse("-----x", limits=limits)

    assert isinstance(inside, ParsedExpressionInput)
    assert inside.metrics.max_ast_depth == 4
    assert isinstance(exact, ParsedExpressionInput)
    assert exact.metrics.max_ast_depth == limits.max_nesting_depth
    assert isinstance(over, ErrorInfo)
    assert over.code is ErrorCode.AST_DEPTH_LIMIT_EXCEEDED


@pytest.mark.parametrize(
    "text",
    [
        "+".join("x" for _ in range(6)),
        "x^" + "^".join("2" for _ in range(5)),
    ],
)
def test_overlong_addition_and_power_chains_use_the_ast_depth_gate(text: str) -> None:
    limits = replace(DEFAULT_LIMITS, max_nesting_depth=5)

    result = _parse(text, limits=limits)
    assert isinstance(result, ErrorInfo)
    assert result.code is ErrorCode.AST_DEPTH_LIMIT_EXCEEDED


def test_literal_exponent_limit_accepts_inside_and_exact_then_rejects_one_more() -> None:
    limits = replace(DEFAULT_LIMITS, max_absolute_exponent=5)

    assert isinstance(_parse("x^4", limits=limits), ParsedExpressionInput)
    exact = _parse("x^-5", limits=limits)
    over = _parse("x^6", limits=limits)

    assert isinstance(exact, ParsedExpressionInput)
    assert exact.metrics.max_absolute_literal_exponent == 5
    assert isinstance(over, ErrorInfo)
    assert over.code is ErrorCode.EXPONENT_OUT_OF_RANGE


def test_decimal_literal_exponents_use_the_documented_narrow_rejection() -> None:
    result = _parse("x^0.5")

    assert isinstance(result, ErrorInfo)
    assert result.code is ErrorCode.UNSUPPORTED_EXPONENT


def test_function_argument_budget_fails_before_parsing_an_extra_argument() -> None:
    limits = replace(DEFAULT_LIMITS, max_function_arguments=2)

    assert isinstance(_parse("sin(x)", limits=limits), ParsedExpressionInput)
    assert isinstance(_parse("log(x,2)", limits=limits), ParsedExpressionInput)
    over = _parse("log(x,2,3)", limits=limits)

    assert isinstance(over, ErrorInfo)
    assert over.code is ErrorCode.FUNCTION_ARGUMENT_ERROR


@pytest.mark.parametrize(
    ("text", "limit_field", "expected_span", "expected_message"),
    [
        (
            "123/1",
            "max_rational_numerator_digits",
            SourceSpan(0, 3),
            "分数分子超过当前安全上限。",
        ),
        (
            "+123/1",
            "max_rational_numerator_digits",
            SourceSpan(0, 4),
            "分数分子超过当前安全上限。",
        ),
        (
            "-123/1",
            "max_rational_numerator_digits",
            SourceSpan(0, 4),
            "分数分子超过当前安全上限。",
        ),
        (
            "1/123",
            "max_rational_denominator_digits",
            SourceSpan(2, 5),
            "分数分母超过当前安全上限。",
        ),
        (
            "1/+123",
            "max_rational_denominator_digits",
            SourceSpan(2, 6),
            "分数分母超过当前安全上限。",
        ),
        (
            "1/-123",
            "max_rational_denominator_digits",
            SourceSpan(2, 6),
            "分数分母超过当前安全上限。",
        ),
    ],
)
@pytest.mark.parametrize(
    ("maximum", "expect_error"),
    [(4, False), (3, False), (2, True)],
    ids=["inside", "exact", "over-by-one"],
)
def test_signed_rational_literal_limits_are_independent_and_preserve_diagnostics(
    text: str,
    limit_field: str,
    expected_span: SourceSpan,
    expected_message: str,
    maximum: int,
    expect_error: bool,
) -> None:
    replacements = {
        "max_rational_numerator_digits": 7,
        "max_rational_denominator_digits": 11,
        limit_field: maximum,
    }
    limits = replace(DEFAULT_LIMITS, **replacements)
    result = _parse(text, limits=limits)

    if not expect_error:
        assert isinstance(result, ParsedExpressionInput)
        return
    assert isinstance(result, ErrorInfo)
    assert result.code is ErrorCode.RATIONAL_LITERAL_TOO_LONG
    assert result.user_message == expected_message
    assert result.source_location == expected_span
    assert result.recoverable is True
