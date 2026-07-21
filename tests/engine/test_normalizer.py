"""Behavioral tests for explicit stage 6 normalization."""

from __future__ import annotations

import pytest

from math_drawing_assistant.config import DEFAULT_LIMITS
from math_drawing_assistant.engine import NormalizedInput, normalize_input
from math_drawing_assistant.models import ErrorCode, ErrorInfo, SourceSpan


def _normalized_text(text: str) -> str:
    result = normalize_input(text)
    assert isinstance(result, NormalizedInput), result
    return result.text


@pytest.mark.parametrize("text", ["x^2", "x**2", "x²"])
def test_equivalent_power_spellings_have_one_normal_form(text: str) -> None:
    assert _normalized_text(text) == "x^2"


def test_superscript_three_and_vertical_bars_are_lexically_preserved() -> None:
    assert _normalized_text("x³") == "x^3"
    assert _normalized_text("|x|") == "|x|"


def test_approved_fullwidth_characters_convert_one_by_one() -> None:
    assert _normalized_text("（１２．５＋３）＝１５．５") == "(12.5+3)=15.5"
    assert _normalized_text("｜x｜") == "|x|"


def test_only_approved_math_symbols_are_converted() -> None:
    assert _normalized_text(" x − 2 × 3 · 4 ÷ 5 ") == "x-2*3*4/5"


def test_ascii_spaces_are_removed_at_outer_and_token_boundaries() -> None:
    assert _normalized_text("  2 ( x + 1 )  ") == "2(x+1)"


@pytest.mark.parametrize("text", ["s in(x)", "p i", "1 2", "1 .5"])
def test_spaces_cannot_merge_identifier_or_number_tokens(text: str) -> None:
    result = normalize_input(text)

    assert isinstance(result, ErrorInfo)
    assert result.code is ErrorCode.INVALID_INPUT
    assert result.source_location is not None


@pytest.mark.parametrize("text", ["", " ", "    "])
def test_empty_or_space_only_input_is_rejected(text: str) -> None:
    result = normalize_input(text)

    assert isinstance(result, ErrorInfo)
    assert result.code is ErrorCode.EMPTY_INPUT
    assert result.source_location == SourceSpan(0, len(text))
    assert result.recoverable is True


@pytest.mark.parametrize(
    ("text", "offset"),
    [
        ("x\ny", 1),
        ("x;y", 1),
        ("x\ty", 1),
        ("x@y", 1),
        ("x∑y", 1),
        ("｜ｘ｜", 1),
    ],
)
def test_unapproved_characters_are_not_deleted_or_ignored(
    text: str,
    offset: int,
) -> None:
    result = normalize_input(text)

    assert isinstance(result, ErrorInfo)
    assert result.code is ErrorCode.UNKNOWN_CHARACTER
    assert result.source_location == SourceSpan(offset, offset + 1)


def test_fullwidth_conversion_does_not_shift_a_later_error() -> None:
    result = normalize_input("１＋＠")

    assert isinstance(result, ErrorInfo)
    assert result.code is ErrorCode.UNKNOWN_CHARACTER
    assert result.source_location == SourceSpan(2, 3)


def test_character_limit_is_checked_before_space_removal_or_expansion() -> None:
    at_limit = " " * (DEFAULT_LIMITS.max_input_characters - 1) + "x"
    over_limit = at_limit + " "

    result = normalize_input(at_limit)
    assert isinstance(result, NormalizedInput)
    assert result.text == "x"

    result = normalize_input(over_limit)
    assert isinstance(result, ErrorInfo)
    assert result.code is ErrorCode.INPUT_TOO_LONG
    assert result.source_location == SourceSpan(
        DEFAULT_LIMITS.max_input_characters,
        DEFAULT_LIMITS.max_input_characters + 1,
    )


def test_technical_messages_never_echo_the_complete_formula() -> None:
    raw = "private-lesson-formula@marker"
    result = normalize_input(raw)

    assert isinstance(result, ErrorInfo)
    assert result.technical_message is not None
    assert raw not in result.technical_message
