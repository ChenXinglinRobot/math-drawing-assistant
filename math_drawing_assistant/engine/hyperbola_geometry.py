"""Private exact and float64 geometry for axis-aligned hyperbolas."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext
from fractions import Fraction
from math import acosh, asinh, cosh, inf, isfinite, nextafter, sinh

from math_drawing_assistant.models.plot_specs import AxisOrientation, HyperbolaSpec


_MAX_FLOAT64 = sys.float_info.max
_MAX_SAFE_HYPERBOLIC_PARAMETER = nextafter(acosh(_MAX_FLOAT64), 0.0)
_TEACHING_PARAMETER = asinh(1.0)


@dataclass(frozen=True, slots=True)
class HyperbolaExecutionGeometry:
    """One non-cached private execution projection of an exact hyperbola Spec."""

    spec: HyperbolaSpec
    center_x: Fraction
    center_y: Fraction
    semi_transverse_squared: Fraction
    semi_conjugate_squared: Fraction
    transverse_axis: AxisOrientation
    center_x_float: float
    center_y_float: float
    semi_transverse_float: float
    semi_conjugate_float: float
    outward_semi_transverse: float
    outward_semi_conjugate: float
    auto_x_lower: float
    auto_x_upper: float
    auto_y_lower: float
    auto_y_upper: float
    max_safe_parameter: float


def project_hyperbola_geometry(spec: HyperbolaSpec) -> HyperbolaExecutionGeometry:
    """Project one exact HyperbolaSpec into finite, non-collapsed execution values."""

    if type(spec) is not HyperbolaSpec:
        raise TypeError("hyperbola geometry requires an exact HyperbolaSpec.")
    spec.__post_init__()
    center_x_float = _finite_fraction_float(spec.center_x, "center_x")
    center_y_float = _finite_fraction_float(spec.center_y, "center_y")
    transverse_float = _finite_fraction_sqrt(
        spec.semi_transverse_squared,
        "semi_transverse",
    )
    conjugate_float = _finite_fraction_sqrt(
        spec.semi_conjugate_squared,
        "semi_conjugate",
    )
    outward_transverse = _outward_sqrt(
        spec.semi_transverse_squared,
        transverse_float,
    )
    outward_conjugate = _outward_sqrt(
        spec.semi_conjugate_squared,
        conjugate_float,
    )

    if spec.transverse_axis is AxisOrientation.HORIZONTAL:
        x_extent_squared = 2 * spec.semi_transverse_squared
        y_extent_squared = spec.semi_conjugate_squared
    elif spec.transverse_axis is AxisOrientation.VERTICAL:
        x_extent_squared = spec.semi_conjugate_squared
        y_extent_squared = 2 * spec.semi_transverse_squared
    else:
        raise TypeError("hyperbola transverse axis is not exact.")
    x_extent = _finite_fraction_sqrt(x_extent_squared, "auto_x_extent")
    y_extent = _finite_fraction_sqrt(y_extent_squared, "auto_y_extent")
    auto_x_lower, auto_x_upper = _outward_axis_bounds(
        spec.center_x,
        x_extent_squared,
        x_extent,
    )
    auto_y_lower, auto_y_upper = _outward_axis_bounds(
        spec.center_y,
        y_extent_squared,
        y_extent,
    )

    geometry = HyperbolaExecutionGeometry(
        spec=spec,
        center_x=spec.center_x,
        center_y=spec.center_y,
        semi_transverse_squared=spec.semi_transverse_squared,
        semi_conjugate_squared=spec.semi_conjugate_squared,
        transverse_axis=spec.transverse_axis,
        center_x_float=center_x_float,
        center_y_float=center_y_float,
        semi_transverse_float=transverse_float,
        semi_conjugate_float=conjugate_float,
        outward_semi_transverse=outward_transverse,
        outward_semi_conjugate=outward_conjugate,
        auto_x_lower=auto_x_lower,
        auto_x_upper=auto_x_upper,
        auto_y_lower=auto_y_lower,
        auto_y_upper=auto_y_upper,
        max_safe_parameter=_MAX_SAFE_HYPERBOLIC_PARAMETER,
    )
    negative_vertex = hyperbola_parameter_point(geometry, 0, 0.0)
    positive_vertex = hyperbola_parameter_point(geometry, 1, 0.0)
    if negative_vertex == positive_vertex:
        raise OverflowError("hyperbola mathematical branches collapse in float64.")
    for branch_id in (0, 1):
        first = hyperbola_parameter_point(geometry, branch_id, -_TEACHING_PARAMETER)
        last = hyperbola_parameter_point(geometry, branch_id, _TEACHING_PARAMETER)
        if first == last:
            raise OverflowError("hyperbola teaching segment collapses in float64.")
    return geometry


def hyperbola_parameter_point(
    geometry: HyperbolaExecutionGeometry,
    mathematical_branch_id: int,
    parameter: float,
) -> tuple[float, float]:
    """Evaluate the frozen branch parameterization without producing Inf or NaN."""

    if type(geometry) is not HyperbolaExecutionGeometry:
        raise TypeError("geometry must be an exact HyperbolaExecutionGeometry.")
    if isinstance(mathematical_branch_id, bool) or mathematical_branch_id not in {0, 1}:
        raise ValueError("mathematical_branch_id must be zero or one.")
    if type(parameter) is not float or not isfinite(parameter):
        raise ValueError("hyperbola parameter must be a finite exact float.")
    if abs(parameter) > geometry.max_safe_parameter:
        raise OverflowError("hyperbola parameter exceeds the safe sinh/cosh range.")

    hyperbolic_cosine = cosh(parameter)
    hyperbolic_sine = sinh(parameter)
    sign = -1.0 if mathematical_branch_id == 0 else 1.0
    transverse_term = _finite_product(
        geometry.semi_transverse_float,
        hyperbolic_cosine,
        "hyperbola transverse coordinate",
    )
    conjugate_term = _finite_product(
        geometry.semi_conjugate_float,
        abs(hyperbolic_sine),
        "hyperbola conjugate coordinate",
    )
    conjugate_term = -conjugate_term if hyperbolic_sine < 0.0 else conjugate_term

    if geometry.transverse_axis is AxisOrientation.HORIZONTAL:
        x_value = _finite_add(
            geometry.center_x_float,
            sign * transverse_term,
            "hyperbola x coordinate",
        )
        y_value = _finite_add(
            geometry.center_y_float,
            conjugate_term,
            "hyperbola y coordinate",
        )
    else:
        x_value = _finite_add(
            geometry.center_x_float,
            conjugate_term,
            "hyperbola x coordinate",
        )
        y_value = _finite_add(
            geometry.center_y_float,
            sign * transverse_term,
            "hyperbola y coordinate",
        )
    return (x_value, y_value)


def normalized_hyperbola_residual(
    geometry: HyperbolaExecutionGeometry,
    x_value: float,
    y_value: float,
) -> Fraction:
    """Return the exact normalized primitive-equation residual for one float point."""

    if type(geometry) is not HyperbolaExecutionGeometry:
        raise TypeError("geometry must be an exact HyperbolaExecutionGeometry.")
    if type(x_value) is not float or type(y_value) is not float:
        raise TypeError("hyperbola residual coordinates must be exact floats.")
    if not isfinite(x_value) or not isfinite(y_value):
        raise ValueError("hyperbola residual coordinates must be finite.")
    x = Fraction.from_float(x_value)
    y = Fraction.from_float(y_value)
    coefficients = geometry.spec.coefficients
    polynomial = (
        coefficients.a * x * x
        + coefficients.c * y * y
        + coefficients.d * x
        + coefficients.e * y
        + coefficients.f
    )
    scale = (
        abs(coefficients.a) * max(Fraction(1), abs(x * x))
        + abs(coefficients.c) * max(Fraction(1), abs(y * y))
        + abs(coefficients.d) * max(Fraction(1), abs(x))
        + abs(coefficients.e) * max(Fraction(1), abs(y))
        + abs(coefficients.f)
    )
    if scale == 0:
        raise ZeroDivisionError("hyperbola residual scale is zero.")
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


def _finite_fraction_sqrt(value: Fraction, name: str) -> float:
    if type(value) is not Fraction or value <= 0:
        raise ValueError(f"{name} squared must be a positive exact Fraction.")
    try:
        with localcontext() as context:
            context.prec = 80
            decimal_value = Decimal(value.numerator) / Decimal(value.denominator)
            converted = float(decimal_value.sqrt())
    except (InvalidOperation, OverflowError, ValueError) as exc:
        raise OverflowError(f"{name} cannot be represented as float64.") from exc
    if not isfinite(converted) or converted <= 0.0:
        raise OverflowError(f"{name} cannot be represented as finite positive float64.")
    return converted


def _outward_sqrt(value: Fraction, nearest: float) -> float:
    outward = nearest
    if Fraction.from_float(outward) * Fraction.from_float(outward) < value:
        outward = nextafter(outward, inf)
    if not isfinite(outward):
        raise OverflowError("hyperbola axis has no finite outward float64 bound.")
    return outward


def _outward_axis_bounds(
    center: Fraction,
    extent_squared: Fraction,
    nearest_extent: float,
) -> tuple[float, float]:
    center_float = _finite_fraction_float(center, "center")
    lower = center_float - nearest_extent
    upper = center_float + nearest_extent
    if not isfinite(lower) or not isfinite(upper):
        raise OverflowError("hyperbola automatic bounds are not finite.")
    while not _lower_encloses(center, extent_squared, lower):
        lower = nextafter(lower, -inf)
        if not isfinite(lower):
            raise OverflowError("hyperbola lower bound has no finite representation.")
    while not _upper_encloses(center, extent_squared, upper):
        upper = nextafter(upper, inf)
        if not isfinite(upper):
            raise OverflowError("hyperbola upper bound has no finite representation.")
    if lower >= upper:
        raise OverflowError("hyperbola automatic bounds collapse in float64.")
    return (lower, upper)


def _lower_encloses(center: Fraction, extent_squared: Fraction, candidate: float) -> bool:
    distance = center - Fraction.from_float(candidate)
    return distance >= 0 and distance * distance >= extent_squared


def _upper_encloses(center: Fraction, extent_squared: Fraction, candidate: float) -> bool:
    distance = Fraction.from_float(candidate) - center
    return distance >= 0 and distance * distance >= extent_squared


def _finite_product(left: float, right: float, name: str) -> float:
    if left < 0.0 or right < 0.0 or not isfinite(left) or not isfinite(right):
        raise OverflowError(f"{name} factors must be finite and non-negative.")
    if right != 0.0 and left > _MAX_FLOAT64 / right:
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
