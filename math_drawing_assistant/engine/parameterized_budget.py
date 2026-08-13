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
_FLOAT64_EPSILON_DENOMINATOR_BITS = 53
_OVAL_SEGMENT_CAPACITY = 4
_OVAL_CANDIDATE_ANGLE_CAPACITY = 9
_OVAL_INTERVAL_CAPACITY = 4
# Maximum simultaneously-live exact integer values across center/axis projection,
# boundary-root comparisons, outward-bound proofs, and one normalized residual.
_OVAL_EXACT_LIVE_BIGINT_VALUES = (
    "coefficient_a",
    "coefficient_c",
    "coefficient_d",
    "coefficient_e",
    "coefficient_f",
    "center_x_numerator",
    "center_x_denominator",
    "center_y_numerator",
    "center_y_denominator",
    "axis_x_numerator",
    "axis_x_denominator",
    "axis_y_numerator",
    "axis_y_denominator",
    "edge_numerator",
    "edge_denominator",
    "delta_numerator",
    "delta_denominator",
    "delta_square_numerator",
    "delta_square_denominator",
    "float_x_numerator",
    "float_x_denominator",
    "float_y_numerator",
    "float_y_denominator",
    "x_square_numerator",
    "x_square_denominator",
    "y_square_numerator",
    "y_square_denominator",
    "term_a_numerator",
    "term_c_numerator",
    "term_d_numerator",
    "term_e_numerator",
    "polynomial_numerator",
    "polynomial_denominator",
    "scale_numerator",
    "scale_denominator",
    "residual_numerator",
    "residual_denominator",
    "comparison_cross_product_left",
    "comparison_cross_product_right",
    "outward_bound_cross_product",
)


def _oval_exact_max_integer_bits(limits: ApplicationLimits) -> int:
    """Return a conservative bit bound for every exact oval integer."""

    if type(limits) is not ApplicationLimits:
        raise TypeError("oval exact bit bound requires exact ApplicationLimits.")
    limits.__post_init__()

    # A canonical coefficient has magnitude < 10**D.  Because 10 < 2**4,
    # D decimal digits need at most 4*D binary bits.  A finite float64 Fraction
    # needs at most 1,075 bits in either numerator or denominator: the largest
    # finite numerator is below 2**1_024 and a subnormal denominator is 2**1_074.
    coefficient_bits = 4 * limits.max_equation_canonical_coefficient_digits
    float_ratio_bits = _FLOAT64_MAX_EXPONENT_MAGNITUDE + 1

    # center = -d/(2a) has numerator <= C and denominator <= C+1 bits.
    # q = d**2*c + e**2*a - 4*a*c*f needs <= 3*C+3 bits, and an axis square
    # q/(4*a**2*c) needs <= 3*C+3 bits in either reduced component.  Subtracting
    # a float edge from a center produces numerator <= C+F+2 and denominator
    # <= C+F+1; squaring doubles those widths.  Fraction comparison then forms
    # the two unreduced cross-products, whose larger side is bounded below.
    outward_comparison_bits = 5 * coefficient_bits + 2 * float_ratio_bits + 6

    # normalized_oval_residual squares two float ratios, multiplies by one
    # coefficient, sums five non-negative terms, and divides polynomial by
    # scale.  Aligning the shared power-of-two denominators can shift a term by
    # at most 2*F bits, so each five-term sum needs <= C+4*F+3 numerator bits
    # and <= 2*F denominator bits.  The final Fraction division cross-products
    # therefore need at most C+6*F+3 bits.  Comparing that residual against an
    # integer multiple of 2**-52 adds at most the 53-bit denominator of 2**52.
    normalized_residual_comparison_bits = (
        coefficient_bits
        + 6 * float_ratio_bits
        + 3
        + _FLOAT64_EPSILON_DENOMINATOR_BITS
    )
    return max(outward_comparison_bits, normalized_residual_comparison_bits)


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


def estimate_oval_exact_workspace_bytes(limits: ApplicationLimits) -> int:
    """Bound the simultaneous Python integers used by exact oval arithmetic."""

    max_integer_bits = _oval_exact_max_integer_bits(limits)
    bigint_digits = (
        max_integer_bits + sys.int_info.bits_per_digit - 1
    ) // sys.int_info.bits_per_digit
    bytes_per_bigint = sys.getsizeof(0) + bigint_digits * sys.int_info.sizeof_digit
    return len(_OVAL_EXACT_LIVE_BIGINT_VALUES) * bytes_per_bigint


def build_oval_parameterized_memory_budget(
    *,
    sample_count: int,
    batch_size: int,
    image_width: int,
    image_height: int,
    limits: ApplicationLimits,
) -> ParameterizedRenderMemoryBudget:
    """Return the shared Circle/Ellipse budget used by Builder and sampler."""

    for name, value in (
        ("sample_count", sample_count),
        ("batch_size", batch_size),
        ("image_width", image_width),
        ("image_height", image_height),
    ):
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{name} must be an integer.")
        if value < 1:
            raise ValueError(f"{name} must be positive.")
    if batch_size > sample_count:
        raise ValueError("batch_size must not exceed sample_count.")
    if type(limits) is not ApplicationLimits:
        raise TypeError("oval budget requires exact ApplicationLimits.")
    limits.__post_init__()

    final_vector_bytes = sample_count * _FLOAT64_BYTES
    exact_workspace_bytes = estimate_oval_exact_workspace_bytes(limits)
    interval_planning_bytes = (
        _OVAL_CANDIDATE_ANGLE_CAPACITY * _FLOAT64_BYTES
        + _OVAL_CANDIDATE_ANGLE_CAPACITY * _BOOL_BYTES
        + _OVAL_INTERVAL_CAPACITY * 2 * _FLOAT64_BYTES
    )
    return ParameterizedRenderMemoryBudget(
        final_x_bytes=final_vector_bytes,
        final_y_bytes=final_vector_bytes,
        artist_data_bytes=2 * final_vector_bytes,
        segment_index_range_bytes=(
            _OVAL_SEGMENT_CAPACITY * 2 * _INT64_BYTES
        ),
        segment_metadata_bytes=(
            _OVAL_SEGMENT_CAPACITY * 2 * _INT64_BYTES
        ),
        parameter_batch_bytes=batch_size * _FLOAT64_BYTES,
        transcendental_workspace_bytes=2 * batch_size * _FLOAT64_BYTES,
        validation_workspace_bytes=(
            exact_workspace_bytes
            + interval_planning_bytes
            + batch_size * _BOOL_BYTES
            + batch_size * _FLOAT64_BYTES
        ),
        rgba_canvas_bytes=image_width * image_height * _RGBA_BYTES_PER_PIXEL,
        png_buffer_reserve_bytes=limits.max_png_bytes,
        png_copy_bytes=limits.max_png_bytes,
    )


def plan_oval_batch_size(
    *,
    sample_count: int,
    preferred_batch_points: int,
    image_width: int,
    image_height: int,
    limits: ApplicationLimits,
) -> int:
    """Derive the largest allowed deterministic oval batch using the shared budget."""

    for name, value in (
        ("sample_count", sample_count),
        ("preferred_batch_points", preferred_batch_points),
    ):
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{name} must be an integer.")
        if value < 1:
            raise ValueError(f"{name} must be positive.")
    preferred = min(sample_count, preferred_batch_points)
    minimum_budget = build_oval_parameterized_memory_budget(
        sample_count=sample_count,
        batch_size=1,
        image_width=image_width,
        image_height=image_height,
        limits=limits,
    )
    if minimum_budget.total_bytes > limits.max_estimated_memory_bytes:
        raise ValueError("oval budget cannot fit a one-point batch.")
    one_point_batch_bytes = (
        _FLOAT64_BYTES
        + 2 * _FLOAT64_BYTES
        + _BOOL_BYTES
        + _FLOAT64_BYTES
    )
    available_growth = limits.max_estimated_memory_bytes - minimum_budget.total_bytes
    return min(preferred, 1 + available_growth // one_point_batch_bytes)


__all__: list[str] = []
