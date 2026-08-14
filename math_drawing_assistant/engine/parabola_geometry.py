"""Private exact and float64 geometry for axis-aligned parabolas."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from fractions import Fraction
from math import inf, isfinite, nextafter

from math_drawing_assistant.models.plot_specs import ParabolaOpening, ParabolaSpec


_MAX_FLOAT64 = sys.float_info.max


@dataclass(frozen=True, slots=True)
class ParabolaExecutionGeometry:
    """One non-cached private execution projection of an exact parabola Spec."""

    spec: ParabolaSpec
    vertex_x: Fraction
    vertex_y: Fraction
    focal_parameter: Fraction
    opening: ParabolaOpening
    vertex_x_float: float
    vertex_y_float: float
    focal_parameter_float: float
    two_focal_parameter_float: float
    auto_x_lower: float
    auto_x_upper: float
    auto_y_lower: float
    auto_y_upper: float

    @property
    def has_vertical_axis(self) -> bool:
        return self.opening in {ParabolaOpening.UP, ParabolaOpening.DOWN}


def project_parabola_geometry(spec: ParabolaSpec) -> ParabolaExecutionGeometry:
    """Project one exact ParabolaSpec into finite, non-collapsed execution values."""

    if type(spec) is not ParabolaSpec:
        raise TypeError("parabola geometry requires an exact ParabolaSpec.")
    spec.__post_init__()
    vertex_x_float = _finite_fraction_float(spec.vertex_x, "vertex_x")
    vertex_y_float = _finite_fraction_float(spec.vertex_y, "vertex_y")
    focal_parameter_float = _finite_fraction_float(
        spec.focal_parameter,
        "focal_parameter",
    )
    two_focal_parameter_float = _finite_fraction_float(
        2 * spec.focal_parameter,
        "two_focal_parameter",
    )
    if focal_parameter_float == 0.0 or two_focal_parameter_float == 0.0:
        raise OverflowError("parabola focal parameter collapses in float64.")

    absolute_parameter = abs(spec.focal_parameter)
    if spec.opening in {ParabolaOpening.UP, ParabolaOpening.DOWN}:
        exact_x_lower = spec.vertex_x - 2 * absolute_parameter
        exact_x_upper = spec.vertex_x + 2 * absolute_parameter
        exact_y_lower = min(spec.vertex_y, spec.vertex_y + spec.focal_parameter)
        exact_y_upper = max(spec.vertex_y, spec.vertex_y + spec.focal_parameter)
    elif spec.opening in {ParabolaOpening.LEFT, ParabolaOpening.RIGHT}:
        exact_x_lower = min(spec.vertex_x, spec.vertex_x + spec.focal_parameter)
        exact_x_upper = max(spec.vertex_x, spec.vertex_x + spec.focal_parameter)
        exact_y_lower = spec.vertex_y - 2 * absolute_parameter
        exact_y_upper = spec.vertex_y + 2 * absolute_parameter
    else:
        raise TypeError("parabola opening is not exact.")
    auto_x_lower, auto_x_upper = _outward_fraction_bounds(
        exact_x_lower,
        exact_x_upper,
        "parabola automatic x bounds",
    )
    auto_y_lower, auto_y_upper = _outward_fraction_bounds(
        exact_y_lower,
        exact_y_upper,
        "parabola automatic y bounds",
    )

    geometry = ParabolaExecutionGeometry(
        spec=spec,
        vertex_x=spec.vertex_x,
        vertex_y=spec.vertex_y,
        focal_parameter=spec.focal_parameter,
        opening=spec.opening,
        vertex_x_float=vertex_x_float,
        vertex_y_float=vertex_y_float,
        focal_parameter_float=focal_parameter_float,
        two_focal_parameter_float=two_focal_parameter_float,
        auto_x_lower=auto_x_lower,
        auto_x_upper=auto_x_upper,
        auto_y_lower=auto_y_lower,
        auto_y_upper=auto_y_upper,
    )
    vertex = parabola_parameter_point(geometry, 0.0)
    negative_teaching = parabola_parameter_point(geometry, -1.0)
    positive_teaching = parabola_parameter_point(geometry, 1.0)
    if (
        negative_teaching == vertex
        or positive_teaching == vertex
        or negative_teaching == positive_teaching
    ):
        raise OverflowError("parabola teaching window collapses in float64.")
    return geometry


def parabola_parameter_point(
    geometry: ParabolaExecutionGeometry,
    parameter: float,
) -> tuple[float, float]:
    """Evaluate the frozen parameterization without first producing Inf or NaN."""

    if type(geometry) is not ParabolaExecutionGeometry:
        raise TypeError("geometry must be an exact ParabolaExecutionGeometry.")
    if type(parameter) is not float or not isfinite(parameter):
        raise ValueError("parabola parameter must be a finite exact float.")

    parameter_squared = _finite_product(
        parameter,
        parameter,
        "parabola squared parameter",
    )
    cross_term = _finite_product(
        geometry.two_focal_parameter_float,
        parameter,
        "parabola cross-axis coordinate",
    )
    opening_term = _finite_product(
        geometry.focal_parameter_float,
        parameter_squared,
        "parabola opening-axis coordinate",
    )
    if geometry.has_vertical_axis:
        x_value = _finite_add(
            geometry.vertex_x_float,
            cross_term,
            "parabola x coordinate",
        )
        y_value = _finite_add(
            geometry.vertex_y_float,
            opening_term,
            "parabola y coordinate",
        )
    else:
        x_value = _finite_add(
            geometry.vertex_x_float,
            opening_term,
            "parabola x coordinate",
        )
        y_value = _finite_add(
            geometry.vertex_y_float,
            cross_term,
            "parabola y coordinate",
        )
    return (x_value, y_value)


def normalized_parabola_residual(
    geometry: ParabolaExecutionGeometry,
    x_value: float,
    y_value: float,
) -> Fraction:
    """Return the exact normalized primitive-equation residual for one float point."""

    if type(geometry) is not ParabolaExecutionGeometry:
        raise TypeError("geometry must be an exact ParabolaExecutionGeometry.")
    if type(x_value) is not float or type(y_value) is not float:
        raise TypeError("parabola residual coordinates must be exact floats.")
    if not isfinite(x_value) or not isfinite(y_value):
        raise ValueError("parabola residual coordinates must be finite.")
    x = Fraction.from_float(x_value)
    y = Fraction.from_float(y_value)
    x_squared = x * x
    y_squared = y * y
    coefficients = geometry.spec.coefficients
    polynomial = (
        coefficients.a * x_squared
        + coefficients.c * y_squared
        + coefficients.d * x
        + coefficients.e * y
        + coefficients.f
    )
    scale = (
        abs(coefficients.a) * max(Fraction(1), abs(x_squared))
        + abs(coefficients.c) * max(Fraction(1), abs(y_squared))
        + abs(coefficients.d) * max(Fraction(1), abs(x))
        + abs(coefficients.e) * max(Fraction(1), abs(y))
        + abs(coefficients.f)
    )
    if scale == 0:
        raise ZeroDivisionError("parabola residual scale is zero.")
    return abs(polynomial) / scale


def _finite_fraction_float(value: Fraction, name: str) -> float:
    if type(value) is not Fraction:
        raise TypeError(f"{name} must be an exact Fraction.")
    try:
        converted = float(value)
    except OverflowError as exc:
        raise OverflowError(f"{name} cannot be represented as float64.") from exc
    if not isfinite(converted):
        raise OverflowError(f"{name} cannot be represented as finite float64.")
    return converted


def _outward_fraction_bounds(
    exact_lower: Fraction,
    exact_upper: Fraction,
    name: str,
) -> tuple[float, float]:
    """Convert one exact interval to finite float64 bounds without inward rounding."""

    if type(exact_lower) is not Fraction or type(exact_upper) is not Fraction:
        raise TypeError(f"{name} require exact Fraction endpoints.")
    if exact_lower >= exact_upper:
        raise ValueError(f"{name} must be ordered and non-empty.")
    lower = _finite_fraction_float(exact_lower, f"{name} lower")
    upper = _finite_fraction_float(exact_upper, f"{name} upper")
    while Fraction.from_float(lower) > exact_lower:
        lower = nextafter(lower, -inf)
        if not isfinite(lower):
            raise OverflowError(f"{name} lower endpoint has no finite enclosure.")
    while Fraction.from_float(upper) < exact_upper:
        upper = nextafter(upper, inf)
        if not isfinite(upper):
            raise OverflowError(f"{name} upper endpoint has no finite enclosure.")
    if lower >= upper:
        raise OverflowError(f"{name} collapse in float64.")
    return (lower, upper)


def _finite_product(left: float, right: float, name: str) -> float:
    if not isfinite(left) or not isfinite(right):
        raise OverflowError(f"{name} factors must be finite.")
    if left != 0.0 and right != 0.0 and abs(left) > _MAX_FLOAT64 / abs(right):
        raise OverflowError(f"{name} would overflow float64.")
    result = left * right
    if not isfinite(result):
        raise OverflowError(f"{name} is not finite.")
    return result


def _finite_add(base: float, offset: float, name: str) -> float:
    if not isfinite(base) or not isfinite(offset):
        raise OverflowError(f"{name} inputs must be finite.")
    if offset > 0.0 and base > _MAX_FLOAT64 - offset:
        raise OverflowError(f"{name} would overflow float64.")
    if offset < 0.0 and base < -_MAX_FLOAT64 - offset:
        raise OverflowError(f"{name} would overflow float64.")
    result = base + offset
    if not isfinite(result):
        raise OverflowError(f"{name} is not finite.")
    return result


__all__: list[str] = []
