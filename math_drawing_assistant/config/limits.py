"""Central resource limits shared by future validation boundaries.

The default values in this module are initial safety limits.  They are not
performance promises and must be calibrated by the benchmark stages before
they can be marked as benchmark-frozen.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from enum import Enum
from typing import Final


class LimitStatus(str, Enum):
    """Calibration state of an application-limits contract."""

    INITIAL_SAFETY = "initial_safety"
    BENCHMARK_FROZEN = "benchmark_frozen"


LIMITS_VERSION: Final[str] = "limits-v1-initial-safety"


def _require_integer(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer.")


def _require_between(value: int, minimum: int, maximum: int, name: str) -> None:
    _require_integer(value, name)
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}.")


def _require_at_most(
    value: int,
    maximum: int,
    name: str,
    *,
    minimum: int = 0,
) -> None:
    _require_between(value, minimum, maximum, name)


@dataclass(frozen=True, slots=True)
class ApplicationLimits:
    """Immutable Phase 5 contract for input, scene, output, and log limits."""

    version: str
    status: LimitStatus

    max_input_characters: int
    max_tokens: int
    max_ast_nodes: int
    max_nesting_depth: int
    max_numeric_digits: int
    max_decimal_places: int
    max_rational_numerator_digits: int
    max_rational_denominator_digits: int
    max_absolute_exponent: int
    max_function_arguments: int

    max_scene_items: int
    max_sample_points_per_item: int
    max_total_sample_points: int
    max_branches_per_item: int
    max_total_branches: int
    max_estimated_memory_bytes: int
    max_png_bytes: int

    min_image_width: int
    max_image_width: int
    min_image_height: int
    max_image_height: int
    min_dpi: int
    max_dpi: int

    max_log_file_bytes: int
    log_backup_count: int
    max_log_field_text_length: int

    def __post_init__(self) -> None:
        if not isinstance(self.version, str):
            raise TypeError("version must be a string.")
        if not self.version.strip():
            raise ValueError("version must not be empty.")
        if not isinstance(self.status, LimitStatus):
            raise TypeError("status must be a LimitStatus.")

        for field in fields(self):
            if field.name in {"version", "status"}:
                continue
            value = getattr(self, field.name)
            _require_integer(value, field.name)
            if value <= 0:
                raise ValueError(f"{field.name} must be positive.")

        self._validate_relationships()

    def _validate_relationships(self) -> None:
        if self.min_image_width > self.max_image_width:
            raise ValueError("min_image_width must not exceed max_image_width.")
        if self.min_image_height > self.max_image_height:
            raise ValueError("min_image_height must not exceed max_image_height.")
        if self.min_dpi > self.max_dpi:
            raise ValueError("min_dpi must not exceed max_dpi.")
        if self.max_sample_points_per_item > self.max_total_sample_points:
            raise ValueError(
                "max_sample_points_per_item must not exceed "
                "max_total_sample_points.",
            )
        if self.max_branches_per_item > self.max_total_branches:
            raise ValueError(
                "max_branches_per_item must not exceed max_total_branches.",
            )

    def validate_input_complexity(
        self,
        *,
        character_count: int,
        token_count: int,
        ast_node_count: int,
        nesting_depth: int,
        numeric_digits: int,
        decimal_places: int,
        rational_numerator_digits: int,
        rational_denominator_digits: int,
        absolute_exponent: int,
        function_arguments: int,
    ) -> None:
        """Validate already-computed input counts without parsing the input."""

        checks = (
            (character_count, self.max_input_characters, "character_count"),
            (token_count, self.max_tokens, "token_count"),
            (ast_node_count, self.max_ast_nodes, "ast_node_count"),
            (nesting_depth, self.max_nesting_depth, "nesting_depth"),
            (numeric_digits, self.max_numeric_digits, "numeric_digits"),
            (decimal_places, self.max_decimal_places, "decimal_places"),
            (
                rational_numerator_digits,
                self.max_rational_numerator_digits,
                "rational_numerator_digits",
            ),
            (
                rational_denominator_digits,
                self.max_rational_denominator_digits,
                "rational_denominator_digits",
            ),
            (
                absolute_exponent,
                self.max_absolute_exponent,
                "absolute_exponent",
            ),
            (
                function_arguments,
                self.max_function_arguments,
                "function_arguments",
            ),
        )
        for value, maximum, name in checks:
            _require_at_most(value, maximum, name)

    def validate_scene_resources(
        self,
        *,
        item_count: int,
        sample_points_per_item: int,
        total_sample_points: int,
        branches_per_item: int,
        total_branches: int,
        estimated_memory_bytes: int,
    ) -> None:
        """Validate supplied scene counts without estimating or allocating them."""

        _require_at_most(item_count, self.max_scene_items, "item_count", minimum=1)
        _require_at_most(
            sample_points_per_item,
            self.max_sample_points_per_item,
            "sample_points_per_item",
            minimum=1,
        )
        _require_at_most(
            total_sample_points,
            self.max_total_sample_points,
            "total_sample_points",
            minimum=1,
        )
        _require_at_most(
            branches_per_item,
            self.max_branches_per_item,
            "branches_per_item",
            minimum=1,
        )
        _require_at_most(
            total_branches,
            self.max_total_branches,
            "total_branches",
            minimum=1,
        )
        _require_at_most(
            estimated_memory_bytes,
            self.max_estimated_memory_bytes,
            "estimated_memory_bytes",
        )
        if sample_points_per_item > total_sample_points:
            raise ValueError(
                "sample_points_per_item must not exceed total_sample_points.",
            )
        if branches_per_item > total_branches:
            raise ValueError("branches_per_item must not exceed total_branches.")

    def validate_output(
        self,
        *,
        image_width: int,
        image_height: int,
        dpi: int,
        png_bytes: int,
    ) -> None:
        """Validate supplied output dimensions and encoded PNG byte length."""

        _require_between(
            image_width,
            self.min_image_width,
            self.max_image_width,
            "image_width",
        )
        _require_between(
            image_height,
            self.min_image_height,
            self.max_image_height,
            "image_height",
        )
        _require_between(dpi, self.min_dpi, self.max_dpi, "dpi")
        _require_at_most(png_bytes, self.max_png_bytes, "png_bytes")


DEFAULT_LIMITS: Final[ApplicationLimits] = ApplicationLimits(
    version=LIMITS_VERSION,
    status=LimitStatus.INITIAL_SAFETY,
    max_input_characters=4_096,
    max_tokens=1_024,
    max_ast_nodes=2_048,
    max_nesting_depth=64,
    max_numeric_digits=128,
    max_decimal_places=64,
    max_rational_numerator_digits=128,
    max_rational_denominator_digits=128,
    max_absolute_exponent=1_000,
    max_function_arguments=8,
    max_scene_items=16,
    max_sample_points_per_item=20_000,
    max_total_sample_points=100_000,
    max_branches_per_item=16,
    max_total_branches=64,
    max_estimated_memory_bytes=256 * 1_024 * 1_024,
    max_png_bytes=32 * 1_024 * 1_024,
    min_image_width=320,
    max_image_width=4_096,
    min_image_height=240,
    max_image_height=4_096,
    min_dpi=72,
    max_dpi=300,
    max_log_file_bytes=5 * 1_024 * 1_024,
    log_backup_count=3,
    max_log_field_text_length=512,
)
