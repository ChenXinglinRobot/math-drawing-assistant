"""Exact half-open source-map behavior for the stage 6 front end."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from math_drawing_assistant.engine import NormalizedInput, SourceMap, normalize_input
from math_drawing_assistant.models import ErrorInfo, SourceSpan


def _normalized(text: str) -> NormalizedInput:
    result = normalize_input(text)
    assert isinstance(result, NormalizedInput), result
    return result


def test_unicode_superscript_mapping_is_exact_after_outer_spaces() -> None:
    normalized = _normalized(" x² ")
    source_map = normalized.source_map

    assert normalized.text == "x^2"
    assert source_map.character_spans == (
        SourceSpan(1, 2),
        SourceSpan(2, 3),
        SourceSpan(2, 3),
    )
    assert source_map.map_normalized_span(SourceSpan(0, 3)) == SourceSpan(1, 3)
    assert source_map.map_token_span(SourceSpan(1, 2)) == SourceSpan(2, 3)
    assert tuple(source_map.map_offset(index) for index in range(4)) == (
        SourceSpan(1, 1),
        SourceSpan(2, 2),
        SourceSpan(2, 2),
        SourceSpan(3, 3),
    )


def test_double_asterisk_many_to_one_mapping_is_exact() -> None:
    source_map = _normalized("x**2").source_map

    assert source_map.normalized_text == "x^2"
    assert source_map.character_spans == (
        SourceSpan(0, 1),
        SourceSpan(1, 3),
        SourceSpan(3, 4),
    )
    assert source_map.source_span_for_character(1) == SourceSpan(1, 3)
    assert source_map.map_token_span(SourceSpan(1, 2)) == SourceSpan(1, 3)
    assert source_map.map_normalized_span(SourceSpan(0, 3)) == SourceSpan(0, 4)


def test_deleted_spaces_keep_later_characters_at_original_positions() -> None:
    source_map = _normalized("  x + y  ").source_map

    assert source_map.normalized_text == "x+y"
    assert source_map.character_spans == (
        SourceSpan(2, 3),
        SourceSpan(4, 5),
        SourceSpan(6, 7),
    )
    assert source_map.map_normalized_span(SourceSpan(2, 3)) == SourceSpan(6, 7)


def test_fullwidth_replacement_keeps_original_character_spans() -> None:
    source_map = _normalized("（１２）＝３").source_map

    assert source_map.normalized_text == "(12)=3"
    assert source_map.character_spans == tuple(
        SourceSpan(index, index + 1) for index in range(6)
    )


def test_empty_source_map_has_a_defined_zero_boundary() -> None:
    source_map = SourceMap("", "", ())

    assert source_map.map_offset(0) == SourceSpan(0, 0)
    assert source_map.map_normalized_span(SourceSpan(0, 0)) == SourceSpan(0, 0)


def test_source_map_is_frozen_and_rejects_invalid_contracts() -> None:
    source_map = SourceMap("x", "x", (SourceSpan(0, 1),))
    with pytest.raises(FrozenInstanceError):
        source_map.original_text = "y"  # type: ignore[misc]  # frozen contract probe

    with pytest.raises(ValueError, match="one source span"):
        SourceMap("x", "x", ())
    with pytest.raises(ValueError, match="non-empty span"):
        SourceMap("x", "x", (SourceSpan(0, 0),))
    with pytest.raises(ValueError, match="monotonic"):
        SourceMap(
            "xy",
            "xy",
            (SourceSpan(1, 2), SourceSpan(0, 1)),
        )
    with pytest.raises(ValueError, match="beyond"):
        SourceMap("x", "x", (SourceSpan(0, 2),))


def test_invalid_indexes_never_produce_a_misleading_span() -> None:
    source_map = _normalized("x²").source_map

    with pytest.raises(IndexError):
        source_map.source_span_for_character(-1)
    with pytest.raises(IndexError):
        source_map.source_span_for_character(3)
    with pytest.raises(IndexError):
        source_map.map_offset(4)
    with pytest.raises(IndexError):
        source_map.map_normalized_span(SourceSpan(0, 4))
    with pytest.raises(TypeError):
        source_map.map_offset(True)  # type: ignore[arg-type]


def test_normalizer_failures_remain_structured_not_source_maps() -> None:
    result = normalize_input(" x @ ")

    assert isinstance(result, ErrorInfo)
    assert result.source_location == SourceSpan(3, 4)
