"""Narrow M1 classification tests without algebraic solving or rearrangement."""

from __future__ import annotations

import pytest

from math_drawing_assistant.engine import (
    ExplicitFunctionCandidate,
    NormalizedInput,
    ParsedEquationInput,
    ParsedExpressionInput,
    classify_plot,
    normalize_input,
    parse_input,
    split_equation,
    tokenize,
)
from math_drawing_assistant.models import (
    BinaryOpNode,
    ErrorCode,
    ErrorInfo,
    NumberNode,
    PlotKind,
    SourceSpan,
    SymbolNode,
)


def _parsed(text: str) -> ParsedExpressionInput | ParsedEquationInput:
    normalized = normalize_input(text)
    assert isinstance(normalized, NormalizedInput), normalized
    tokens = tokenize(normalized)
    assert isinstance(tokens, tuple), tokens
    split = split_equation(tokens)
    assert not isinstance(split, ErrorInfo), split
    parsed = parse_input(split)
    assert isinstance(parsed, (ParsedExpressionInput, ParsedEquationInput)), parsed
    return parsed


@pytest.mark.parametrize("text", ["x", "x^2", "sin(x)", "2", "pi"])
def test_expression_inputs_are_explicit_function_candidates(text: str) -> None:
    result = classify_plot(_parsed(text))

    assert isinstance(result, ExplicitFunctionCandidate)
    assert result.plot_kind is PlotKind.EXPLICIT_FUNCTION
    assert result.source_form == "expression"


@pytest.mark.parametrize(
    ("text", "source_form", "node_type"),
    [
        ("y=x", "y_equals", SymbolNode),
        ("x=y", "equals_y", SymbolNode),
        ("y=x^2", "y_equals", BinaryOpNode),
        ("x^2=y", "equals_y", BinaryOpNode),
        ("y=2", "y_equals", NumberNode),
        ("2=y", "equals_y", NumberNode),
    ],
)
def test_only_direct_isolated_y_equations_are_swapped_or_selected(
    text: str,
    source_form: str,
    node_type: type[object],
) -> None:
    result = classify_plot(_parsed(text))

    assert isinstance(result, ExplicitFunctionCandidate)
    assert result.source_form == source_form
    assert isinstance(result.expression, node_type)


@pytest.mark.parametrize("text", ["y=y", "y=x+y", "x+y=y"])
def test_direct_y_forms_reject_y_on_the_expression_side(text: str) -> None:
    result = classify_plot(_parsed(text))

    assert isinstance(result, ErrorInfo)
    assert result.code is ErrorCode.EXPLICIT_FUNCTION_Y_NOT_ALLOWED
    assert result.source_location is not None


@pytest.mark.parametrize(
    "text",
    [
        "y+1=x+2",
        "x+y=1",
        "x=2",
        "x^2+y^2=25",
        "y^2=8*x",
        "x^2+y^3=1",
        "y^2=x^3",
        "x^3+y^3=1",
        "sin(x)+y=1",
    ],
)
def test_non_direct_equations_get_one_neutral_stage_error(text: str) -> None:
    result = classify_plot(_parsed(text))

    assert isinstance(result, ErrorInfo)
    assert result.code is ErrorCode.UNSUPPORTED_EQUATION
    assert "当前不支持该方程形式" in result.user_message
    assert "一般一次方程" not in result.user_message
    assert "圆锥曲线" not in result.user_message
    assert result.source_location == SourceSpan(0, len(text))
    assert result.recoverable is True


def test_classifier_does_not_mutate_or_rebuild_the_selected_ast() -> None:
    parsed = _parsed("x^2=y")
    assert isinstance(parsed, ParsedEquationInput)

    result = classify_plot(parsed)

    assert isinstance(result, ExplicitFunctionCandidate)
    assert result.expression is parsed.left
    assert result.metrics is parsed.metrics
