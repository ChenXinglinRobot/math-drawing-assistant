"""Shared scalar-only memory estimates for Stage 14 parameterized sampling."""

from __future__ import annotations

import sys

from math_drawing_assistant.config import ApplicationLimits
from math_drawing_assistant.models.render_plan import ParameterizedRenderMemoryBudget


_FLOAT64_BYTES = 8
_INT64_BYTES = 8
_BOOL_BYTES = 1
_RGBA_BYTES_PER_PIXEL = 4
_LINE_SAMPLE_COUNT = 2
_LINE_SEGMENT_COUNT = 1
_LINE_BATCH_SIZE = 1
_LINE_INTERSECTION_CANDIDATE_CAPACITY = 4
_LINE_EXACT_TEMPORARY_BIGINT_COUNT = 28
_FLOAT64_MAX_EXPONENT_MAGNITUDE = 1_074


def estimate_line_exact_workspace_bytes(limits: ApplicationLimits) -> int:
    """Bound the temporary Python integers used by exact line arithmetic."""

    if type(limits) is not ApplicationLimits:
        raise TypeError("line exact workspace requires exact ApplicationLimits.")
    limits.__post_init__()
    max_integer_bits = (
        4 * limits.max_equation_canonical_coefficient_digits
        + 2 * _FLOAT64_MAX_EXPONENT_MAGNITUDE
        + 2
    )
    bigint_digits = (
        max_integer_bits + sys.int_info.bits_per_digit - 1
    ) // sys.int_info.bits_per_digit
    bytes_per_bigint = (
        sys.getsizeof(0) + bigint_digits * sys.int_info.sizeof_digit
    )
    return _LINE_EXACT_TEMPORARY_BIGINT_COUNT * bytes_per_bigint


def build_line_parameterized_memory_budget(
    *,
    image_width: int,
    image_height: int,
    limits: ApplicationLimits,
) -> ParameterizedRenderMemoryBudget:
    """Return the single shared budget used by the line Builder and sampler."""

    if isinstance(image_width, bool) or not isinstance(image_width, int):
        raise TypeError("image_width must be an integer.")
    if isinstance(image_height, bool) or not isinstance(image_height, int):
        raise TypeError("image_height must be an integer.")
    if image_width < 1 or image_height < 1:
        raise ValueError("image dimensions must be positive.")

    exact_workspace_bytes = estimate_line_exact_workspace_bytes(limits)
    candidate_bytes = _LINE_INTERSECTION_CANDIDATE_CAPACITY * (
        2 * _FLOAT64_BYTES + _BOOL_BYTES
    )
    candidate_projection_bytes = (
        _LINE_INTERSECTION_CANDIDATE_CAPACITY * _FLOAT64_BYTES
    )
    residual_vector_bytes = _LINE_SAMPLE_COUNT * _FLOAT64_BYTES
    validation_workspace_bytes = (
        exact_workspace_bytes
        + candidate_bytes
        + candidate_projection_bytes
        + residual_vector_bytes
    )

    final_vector_bytes = _LINE_SAMPLE_COUNT * _FLOAT64_BYTES
    return ParameterizedRenderMemoryBudget(
        final_x_bytes=final_vector_bytes,
        final_y_bytes=final_vector_bytes,
        artist_data_bytes=final_vector_bytes * 2,
        segment_index_range_bytes=(
            _LINE_SEGMENT_COUNT * 2 * _INT64_BYTES
        ),
        segment_metadata_bytes=2 * _INT64_BYTES,
        parameter_batch_bytes=(
            _LINE_SAMPLE_COUNT * _FLOAT64_BYTES * _LINE_BATCH_SIZE
        ),
        transcendental_workspace_bytes=0,
        validation_workspace_bytes=validation_workspace_bytes,
        rgba_canvas_bytes=image_width * image_height * _RGBA_BYTES_PER_PIXEL,
        png_buffer_reserve_bytes=limits.max_png_bytes,
        png_copy_bytes=limits.max_png_bytes,
    )


__all__: list[str] = []
