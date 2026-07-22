"""Phase 5 tests for the centralized immutable limits contract."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path
import re

import pytest

from math_drawing_assistant.config import (
    DEFAULT_LIMITS,
    LIMITS_VERSION,
    ApplicationLimits,
    LimitStatus,
)


def _input_counts_at_limits() -> dict[str, int]:
    return {
        "character_count": DEFAULT_LIMITS.max_input_characters,
        "token_count": DEFAULT_LIMITS.max_tokens,
        "ast_node_count": DEFAULT_LIMITS.max_ast_nodes,
        "nesting_depth": DEFAULT_LIMITS.max_nesting_depth,
        "numeric_digits": DEFAULT_LIMITS.max_numeric_digits,
        "decimal_places": DEFAULT_LIMITS.max_decimal_places,
        "rational_numerator_digits": (
            DEFAULT_LIMITS.max_rational_numerator_digits
        ),
        "rational_denominator_digits": (
            DEFAULT_LIMITS.max_rational_denominator_digits
        ),
        "absolute_exponent": DEFAULT_LIMITS.max_absolute_exponent,
        "function_arguments": DEFAULT_LIMITS.max_function_arguments,
    }


def _scene_counts_at_limits() -> dict[str, int]:
    return {
        "item_count": DEFAULT_LIMITS.max_scene_items,
        "sample_points_per_item": DEFAULT_LIMITS.max_sample_points_per_item,
        "total_sample_points": DEFAULT_LIMITS.max_total_sample_points,
        "branches_per_item": DEFAULT_LIMITS.max_branches_per_item,
        "total_branches": DEFAULT_LIMITS.max_total_branches,
        "estimated_memory_bytes": DEFAULT_LIMITS.max_estimated_memory_bytes,
    }


def test_default_limits_are_frozen_positive_and_versioned() -> None:
    assert DEFAULT_LIMITS.version == LIMITS_VERSION
    assert DEFAULT_LIMITS.status is LimitStatus.INITIAL_SAFETY
    assert DEFAULT_LIMITS.__dataclass_params__.frozen is True
    assert "__dict__" not in ApplicationLimits.__dict__

    signed_range_fields = {
        "default_auto_x_min",
        "default_auto_x_max",
        "fallback_auto_x_min",
        "fallback_auto_x_max",
        "fallback_auto_y_min",
        "fallback_auto_y_max",
    }
    for field in fields(DEFAULT_LIMITS):
        if field.name in {"version", "status"}:
            continue
        value = getattr(DEFAULT_LIMITS, field.name)
        assert isinstance(value, int)
        assert not isinstance(value, bool)
        if field.name not in signed_range_fields:
            assert value > 0

    with pytest.raises(FrozenInstanceError):
        DEFAULT_LIMITS.max_tokens = DEFAULT_LIMITS.max_tokens + 1  # type: ignore[misc]  # frozen contract probe


def test_limit_relationships_are_validated_during_construction() -> None:
    assert DEFAULT_LIMITS.min_image_width <= DEFAULT_LIMITS.max_image_width
    assert DEFAULT_LIMITS.min_image_height <= DEFAULT_LIMITS.max_image_height
    assert DEFAULT_LIMITS.min_dpi <= DEFAULT_LIMITS.max_dpi
    assert (
        DEFAULT_LIMITS.max_sample_points_per_item
        <= DEFAULT_LIMITS.max_total_sample_points
    )
    assert DEFAULT_LIMITS.max_branches_per_item <= DEFAULT_LIMITS.max_total_branches

    with pytest.raises(ValueError, match="min_image_width"):
        replace(
            DEFAULT_LIMITS,
            min_image_width=DEFAULT_LIMITS.max_image_width + 1,
        )
    with pytest.raises(ValueError, match="sample_points"):
        replace(
            DEFAULT_LIMITS,
            max_sample_points_per_item=(
                DEFAULT_LIMITS.max_total_sample_points + 1
            ),
        )
    with pytest.raises(ValueError, match="branches"):
        replace(
            DEFAULT_LIMITS,
            max_branches_per_item=DEFAULT_LIMITS.max_total_branches + 1,
        )
    with pytest.raises(ValueError, match="viewport_span"):
        replace(
            DEFAULT_LIMITS,
            min_viewport_span=DEFAULT_LIMITS.max_viewport_span + 1,
        )
    with pytest.raises(ValueError, match="quantile"):
        replace(
            DEFAULT_LIMITS,
            viewport_quantile_low_percent=(
                DEFAULT_LIMITS.viewport_quantile_high_percent
            ),
        )


@pytest.mark.parametrize(
    ("argument", "limit_field"),
    [
        ("character_count", "max_input_characters"),
        ("token_count", "max_tokens"),
        ("ast_node_count", "max_ast_nodes"),
        ("nesting_depth", "max_nesting_depth"),
        ("numeric_digits", "max_numeric_digits"),
        ("decimal_places", "max_decimal_places"),
        ("rational_numerator_digits", "max_rational_numerator_digits"),
        ("rational_denominator_digits", "max_rational_denominator_digits"),
        ("absolute_exponent", "max_absolute_exponent"),
        ("function_arguments", "max_function_arguments"),
    ],
)
def test_input_complexity_accepts_boundary_and_rejects_overflow(
    argument: str,
    limit_field: str,
) -> None:
    counts = _input_counts_at_limits()
    DEFAULT_LIMITS.validate_input_complexity(**counts)

    counts[argument] = getattr(DEFAULT_LIMITS, limit_field) + 1
    with pytest.raises(ValueError, match=argument):
        DEFAULT_LIMITS.validate_input_complexity(**counts)


@pytest.mark.parametrize(
    ("argument", "limit_field"),
    [
        ("item_count", "max_scene_items"),
        ("sample_points_per_item", "max_sample_points_per_item"),
        ("total_sample_points", "max_total_sample_points"),
        ("branches_per_item", "max_branches_per_item"),
        ("total_branches", "max_total_branches"),
        ("estimated_memory_bytes", "max_estimated_memory_bytes"),
    ],
)
def test_scene_resources_accept_boundary_and_reject_overflow(
    argument: str,
    limit_field: str,
) -> None:
    counts = _scene_counts_at_limits()
    DEFAULT_LIMITS.validate_scene_resources(**counts)

    counts[argument] = getattr(DEFAULT_LIMITS, limit_field) + 1
    with pytest.raises(ValueError, match=argument):
        DEFAULT_LIMITS.validate_scene_resources(**counts)


def test_item_resource_counts_cannot_exceed_supplied_scene_totals() -> None:
    counts = _scene_counts_at_limits()
    counts["total_sample_points"] = counts["sample_points_per_item"] - 1
    with pytest.raises(ValueError, match="sample_points_per_item"):
        DEFAULT_LIMITS.validate_scene_resources(**counts)

    counts = _scene_counts_at_limits()
    counts["total_branches"] = counts["branches_per_item"] - 1
    with pytest.raises(ValueError, match="branches_per_item"):
        DEFAULT_LIMITS.validate_scene_resources(**counts)


def test_image_dpi_and_png_boundaries_are_explicit() -> None:
    DEFAULT_LIMITS.validate_output(
        image_width=DEFAULT_LIMITS.min_image_width,
        image_height=DEFAULT_LIMITS.min_image_height,
        dpi=DEFAULT_LIMITS.min_dpi,
        png_bytes=0,
    )
    DEFAULT_LIMITS.validate_output(
        image_width=DEFAULT_LIMITS.max_image_width,
        image_height=DEFAULT_LIMITS.max_image_height,
        dpi=DEFAULT_LIMITS.max_dpi,
        png_bytes=DEFAULT_LIMITS.max_png_bytes,
    )

    invalid_values = (
        {"image_width": DEFAULT_LIMITS.min_image_width - 1},
        {"image_width": DEFAULT_LIMITS.max_image_width + 1},
        {"image_height": DEFAULT_LIMITS.min_image_height - 1},
        {"image_height": DEFAULT_LIMITS.max_image_height + 1},
        {"dpi": DEFAULT_LIMITS.min_dpi - 1},
        {"dpi": DEFAULT_LIMITS.max_dpi + 1},
        {"png_bytes": DEFAULT_LIMITS.max_png_bytes + 1},
    )
    defaults = {
        "image_width": DEFAULT_LIMITS.min_image_width,
        "image_height": DEFAULT_LIMITS.min_image_height,
        "dpi": DEFAULT_LIMITS.min_dpi,
        "png_bytes": 0,
    }
    for replacement in invalid_values:
        with pytest.raises(ValueError):
            DEFAULT_LIMITS.validate_output(**(defaults | replacement))


def test_limit_validators_reject_bool_as_an_integer() -> None:
    counts = _input_counts_at_limits()
    counts["token_count"] = True
    with pytest.raises(TypeError, match="token_count"):
        DEFAULT_LIMITS.validate_input_complexity(**counts)


def test_supported_formulas_limit_index_tracks_dataclass_fields() -> None:
    document = (
        Path(__file__).parents[1] / "docs" / "supported-formulas.md"
    ).read_text(encoding="utf-8")
    section = document.split("<!-- LIMIT_FIELD_INDEX_START -->", 1)[1].split(
        "<!-- LIMIT_FIELD_INDEX_END -->",
        1,
    )[0]
    documented = set(re.findall(r"^\| `([^`]+)` \|", section, re.MULTILINE))
    expected = {field.name for field in fields(ApplicationLimits)}

    assert documented == expected
