"""Expression/equation boundary tests without mathematical interpretation."""

from __future__ import annotations

import pytest

from math_drawing_assistant.engine import (
    EquationInput,
    ExpressionInput,
    NormalizedInput,
    Token,
    normalize_input,
    split_equation,
    tokenize,
)
from math_drawing_assistant.models import ErrorCode, ErrorInfo, SourceSpan


def _tokens(text: str) -> tuple[Token, ...]:
    normalized = normalize_input(text)
    assert isinstance(normalized, NormalizedInput), normalized
    result = tokenize(normalized)
    assert isinstance(result, tuple), result
    return result


def test_expression_keeps_the_complete_token_tuple_and_ranges() -> None:
    tokens = _tokens(" x² ")
    result = split_equation(tokens)

    assert isinstance(result, ExpressionInput)
    assert result.tokens is tokens
    assert result.normalized_span == SourceSpan(0, 3)
    assert result.source_span == SourceSpan(1, 3)


@pytest.mark.parametrize("text", ["y=x^2", "x=y", "y+1=x+2"])
def test_single_equals_splits_without_swapping_or_algebra(text: str) -> None:
    result = split_equation(_tokens(text))

    assert isinstance(result, EquationInput)
    left = tuple(token.lexeme for token in result.left_tokens)
    right = tuple(token.lexeme for token in result.right_tokens)
    expected_left, expected_right = text.split("=")
    assert "".join(left) == expected_left
    assert "".join(right) == expected_right


def test_equation_side_ranges_map_to_original_text() -> None:
    result = split_equation(_tokens(" y = x² "))

    assert isinstance(result, EquationInput)
    assert result.left_normalized_span == SourceSpan(0, 1)
    assert result.right_normalized_span == SourceSpan(2, 5)
    assert result.left_source_span == SourceSpan(1, 2)
    assert result.right_source_span == SourceSpan(5, 7)


def test_empty_token_tuple_is_rejected() -> None:
    result = split_equation(())

    assert isinstance(result, ErrorInfo)
    assert result.code is ErrorCode.EMPTY_INPUT
    assert result.source_location == SourceSpan(0, 0)


def test_empty_left_side_is_rejected_at_equals_boundary() -> None:
    result = split_equation(_tokens("=x"))

    assert isinstance(result, ErrorInfo)
    assert result.code is ErrorCode.EQUATION_LEFT_EMPTY
    assert result.source_location == SourceSpan(0, 0)


def test_empty_right_side_is_rejected_even_for_direct_splitter_input() -> None:
    complete = _tokens("x=0")
    result = split_equation(complete[:-1])

    assert isinstance(result, ErrorInfo)
    assert result.code is ErrorCode.EQUATION_RIGHT_EMPTY
    assert result.source_location == SourceSpan(2, 2)


def test_multiple_equals_are_rejected_at_the_second_equals() -> None:
    result = split_equation(_tokens("x=y=1"))

    assert isinstance(result, ErrorInfo)
    assert result.code is ErrorCode.MULTIPLE_EQUALS
    assert result.source_location == SourceSpan(3, 4)


@pytest.mark.parametrize("text", ["x>1", "x<=1", "x≤1", "x≠1"])
def test_inequality_is_rejected_before_splitter_can_receive_tokens(text: str) -> None:
    normalized = normalize_input(text)
    assert isinstance(normalized, NormalizedInput)
    result = tokenize(normalized)

    assert isinstance(result, ErrorInfo)
    assert result.code is ErrorCode.UNSUPPORTED_RELATION
