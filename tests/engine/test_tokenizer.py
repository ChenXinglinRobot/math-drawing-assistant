"""Whitelist, source-location, and resource tests for the tokenizer."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from math_drawing_assistant.config import DEFAULT_LIMITS
from math_drawing_assistant.engine import (
    NormalizedInput,
    Token,
    TokenKind,
    normalize_input,
    tokenize,
)
from math_drawing_assistant.models import ErrorCode, ErrorInfo, SourceSpan


def _tokens(text: str) -> tuple[Token, ...]:
    normalized = normalize_input(text)
    assert isinstance(normalized, NormalizedInput), normalized
    result = tokenize(normalized)
    assert isinstance(result, tuple), result
    return result


@pytest.mark.parametrize("text", ["x^2", "x**2", "x²"])
def test_power_spellings_produce_the_same_token_stream(text: str) -> None:
    tokens = _tokens(text)
    assert tuple((token.kind, token.lexeme) for token in tokens) == (
        (TokenKind.VARIABLE, "x"),
        (TokenKind.POWER, "^"),
        (TokenKind.NUMBER, "2"),
    )


def test_superscript_three_and_absolute_value_tokens() -> None:
    assert tuple(token.lexeme for token in _tokens("x³")) == ("x", "^", "3")
    assert tuple(token.kind for token in _tokens("|x|")) == (
        TokenKind.BAR,
        TokenKind.VARIABLE,
        TokenKind.BAR,
    )


@pytest.mark.parametrize(
    "text",
    ["sin(x)", "cos(x)", "tan(x)", "sqrt(x)", "abs(x)", "exp(x)"],
)
def test_approved_single_argument_function_names_are_tokens(text: str) -> None:
    assert _tokens(text)[0].kind is TokenKind.FUNCTION


@pytest.mark.parametrize("text", ["ln(x)", "lg(x)", "log(x,10)"])
def test_approved_logarithm_names_and_comma_are_tokens(text: str) -> None:
    tokens = _tokens(text)
    assert tokens[0].kind is TokenKind.FUNCTION
    if text.startswith("log"):
        assert TokenKind.COMMA in tuple(token.kind for token in tokens)


def test_variables_and_constants_use_distinct_kinds() -> None:
    tokens = _tokens("x+y+pi+E")

    assert tuple(token.kind for token in tokens[::2]) == (
        TokenKind.VARIABLE,
        TokenKind.VARIABLE,
        TokenKind.CONSTANT,
        TokenKind.CONSTANT,
    )


@pytest.mark.parametrize(
    ("text", "lexemes"),
    [
        ("2x", ("2", "x")),
        ("2(x+1)", ("2", "(", "x", "+", "1", ")")),
        (
            "(x+1)(x-1)",
            ("(", "x", "+", "1", ")", "(", "x", "-", "1", ")"),
        ),
    ],
)
def test_implicit_multiplication_is_only_token_adjacency(
    text: str,
    lexemes: tuple[str, ...],
) -> None:
    tokens = _tokens(text)

    assert tuple(token.lexeme for token in tokens) == lexemes
    assert all(token.kind is not TokenKind.STAR for token in tokens)


def test_tokens_are_frozen_and_map_to_original_source() -> None:
    tokens = _tokens(" x² ")

    assert tokens[0].source_span == SourceSpan(1, 2)
    assert tokens[1].source_span == SourceSpan(2, 3)
    assert tokens[2].source_span == SourceSpan(2, 3)
    with pytest.raises(FrozenInstanceError):
        tokens[0].lexeme = "y"  # type: ignore[misc]  # frozen contract probe


def test_unknown_identifier_is_rejected_as_one_complete_range() -> None:
    normalized = normalize_input("sinh(x)")
    assert isinstance(normalized, NormalizedInput)
    result = tokenize(normalized)

    assert isinstance(result, ErrorInfo)
    assert result.code is ErrorCode.UNKNOWN_IDENTIFIER
    assert result.source_location == SourceSpan(0, 4)


@pytest.mark.parametrize("text", ["x<1", "x>1", "x<=1", "x>=1", "x≤1", "x≥1", "x≠1", "x!=1"])
def test_relations_never_become_parser_tokens(text: str) -> None:
    normalized = normalize_input(text)
    assert isinstance(normalized, NormalizedInput)
    result = tokenize(normalized)

    assert isinstance(result, ErrorInfo)
    assert result.code is ErrorCode.UNSUPPORTED_RELATION
    assert result.source_location is not None


@pytest.mark.parametrize("text", ["x+", "x-", "x*", "x/", "x^", "x,", "-"])
def test_mechanically_incomplete_tails_are_rejected(text: str) -> None:
    normalized = normalize_input(text)
    assert isinstance(normalized, NormalizedInput)
    result = tokenize(normalized)

    assert isinstance(result, ErrorInfo)
    assert result.code is ErrorCode.ILLEGAL_TRAILING


def test_trailing_equals_is_a_structured_empty_right_side_error() -> None:
    normalized = normalize_input("x=")
    assert isinstance(normalized, NormalizedInput)
    result = tokenize(normalized)

    assert isinstance(result, ErrorInfo)
    assert result.code is ErrorCode.EQUATION_RIGHT_EMPTY
    assert result.source_location == SourceSpan(2, 2)


@pytest.mark.parametrize(
    ("text", "span"),
    [
        (")x",
         SourceSpan(0, 1)),
        ("(x", SourceSpan(0, 1)),
        ("|x", SourceSpan(0, 1)),
        ("x|", SourceSpan(1, 2)),
        ("sin(", SourceSpan(3, 4)),
    ],
)
def test_parenthesis_and_bar_mismatches_are_rejected(
    text: str,
    span: SourceSpan,
) -> None:
    normalized = normalize_input(text)
    assert isinstance(normalized, NormalizedInput)
    result = tokenize(normalized)

    assert isinstance(result, ErrorInfo)
    assert result.code is ErrorCode.DELIMITER_MISMATCH
    assert result.source_location == span


def test_numeric_digit_and_decimal_boundaries_read_central_limits() -> None:
    at_digits = "9" * DEFAULT_LIMITS.max_numeric_digits
    over_digits = at_digits + "9"
    assert len(_tokens(at_digits)) == 1

    normalized = normalize_input(over_digits)
    assert isinstance(normalized, NormalizedInput)
    result = tokenize(normalized)
    assert isinstance(result, ErrorInfo)
    assert result.code is ErrorCode.NUMBER_TOO_LONG

    at_decimals = "0." + "1" * DEFAULT_LIMITS.max_decimal_places
    over_decimals = at_decimals + "1"
    assert len(_tokens(at_decimals)) == 1

    normalized = normalize_input(over_decimals)
    assert isinstance(normalized, NormalizedInput)
    result = tokenize(normalized)
    assert isinstance(result, ErrorInfo)
    assert result.code is ErrorCode.NUMBER_TOO_LONG


def _text_with_token_count(count: int) -> str:
    if count % 2:
        return "x" + "-x" * (count // 2)
    return "-x" * (count // 2)


def test_token_count_boundary_is_enforced_during_append() -> None:
    at_limit = _text_with_token_count(DEFAULT_LIMITS.max_tokens)
    assert len(_tokens(at_limit)) == DEFAULT_LIMITS.max_tokens

    normalized = normalize_input(at_limit + "|")
    assert isinstance(normalized, NormalizedInput)
    result = tokenize(normalized)
    assert isinstance(result, ErrorInfo)
    assert result.code is ErrorCode.TOKEN_LIMIT_EXCEEDED
    assert result.source_location == SourceSpan(len(at_limit), len(at_limit) + 1)


def test_nesting_boundary_is_enforced_while_scanning_left_parentheses() -> None:
    at_limit = (
        "(" * DEFAULT_LIMITS.max_nesting_depth
        + "x"
        + ")" * DEFAULT_LIMITS.max_nesting_depth
    )
    assert _tokens(at_limit)

    over_limit = "(" + at_limit + ")"
    normalized = normalize_input(over_limit)
    assert isinstance(normalized, NormalizedInput)
    result = tokenize(normalized)
    assert isinstance(result, ErrorInfo)
    assert result.code is ErrorCode.NESTING_TOO_DEEP
    assert result.source_location == SourceSpan(
        DEFAULT_LIMITS.max_nesting_depth,
        DEFAULT_LIMITS.max_nesting_depth + 1,
    )


def test_numbers_are_preserved_as_text_not_converted_to_numeric_objects() -> None:
    token = _tokens("12345678901234567890.125")[0]

    assert token.kind is TokenKind.NUMBER
    assert token.lexeme == "12345678901234567890.125"
    assert isinstance(token.lexeme, str)


@pytest.mark.parametrize("text", ["1.", "1.2.3", ".5.6"])
def test_incomplete_or_multi_dot_numbers_are_rejected(text: str) -> None:
    normalized = normalize_input(text)
    assert isinstance(normalized, NormalizedInput)
    result = tokenize(normalized)

    assert isinstance(result, ErrorInfo)
    assert result.code is ErrorCode.ILLEGAL_TRAILING
