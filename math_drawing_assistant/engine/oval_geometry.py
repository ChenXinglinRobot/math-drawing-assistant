"""Private exact and float64 geometry shared by circles and ellipses."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext
from fractions import Fraction
from math import cos, inf, isfinite, nextafter, sin

from math_drawing_assistant.models.plot_specs import CircleSpec, EllipseSpec


@dataclass(frozen=True, slots=True)
class OvalExecutionGeometry:
    """One non-cached private execution projection of an exact oval Spec."""

    spec: CircleSpec | EllipseSpec
    center_x: Fraction
    center_y: Fraction
    semi_axis_x_squared: Fraction
    semi_axis_y_squared: Fraction
    center_x_float: float
    center_y_float: float
    semi_axis_x_float: float
    semi_axis_y_float: float
    outward_semi_axis_x: float
    outward_semi_axis_y: float
    x_lower: float
    x_upper: float
    y_lower: float
    y_upper: float


def project_oval_geometry(spec: CircleSpec | EllipseSpec) -> OvalExecutionGeometry:
    """Project one exact circle or ellipse into finite scalar execution values."""

    if type(spec) is CircleSpec:
        center_x = spec.center_x
        center_y = spec.center_y
        semi_x_squared = spec.radius_squared
        semi_y_squared = spec.radius_squared
    elif type(spec) is EllipseSpec:
        center_x = spec.center_x
        center_y = spec.center_y
        semi_x_squared = spec.semi_axis_x_squared
        semi_y_squared = spec.semi_axis_y_squared
    else:
        raise TypeError("oval geometry requires an exact CircleSpec or EllipseSpec.")

    spec.__post_init__()
    center_x_float = _finite_fraction_float(center_x, "center_x")
    center_y_float = _finite_fraction_float(center_y, "center_y")
    semi_x_float = _finite_fraction_sqrt(semi_x_squared, "semi_axis_x")
    semi_y_float = _finite_fraction_sqrt(semi_y_squared, "semi_axis_y")
    outward_x = _outward_sqrt(semi_x_squared, semi_x_float)
    outward_y = _outward_sqrt(semi_y_squared, semi_y_float)
    x_lower, x_upper = _outward_axis_bounds(center_x, semi_x_squared, semi_x_float)
    y_lower, y_upper = _outward_axis_bounds(center_y, semi_y_squared, semi_y_float)
    return OvalExecutionGeometry(
        spec=spec,
        center_x=center_x,
        center_y=center_y,
        semi_axis_x_squared=semi_x_squared,
        semi_axis_y_squared=semi_y_squared,
        center_x_float=center_x_float,
        center_y_float=center_y_float,
        semi_axis_x_float=semi_x_float,
        semi_axis_y_float=semi_y_float,
        outward_semi_axis_x=outward_x,
        outward_semi_axis_y=outward_y,
        x_lower=x_lower,
        x_upper=x_upper,
        y_lower=y_lower,
        y_upper=y_upper,
    )


def oval_parameter_point(
    geometry: OvalExecutionGeometry,
    theta: float,
) -> tuple[float, float]:
    """Evaluate the shared angular parameterization with finite scalars."""

    if type(geometry) is not OvalExecutionGeometry:
        raise TypeError("geometry must be an exact OvalExecutionGeometry.")
    if type(theta) is not float or not isfinite(theta):
        raise ValueError("theta must be a finite exact float.")
    x_value = geometry.center_x_float + geometry.semi_axis_x_float * cos(theta)
    y_value = geometry.center_y_float + geometry.semi_axis_y_float * sin(theta)
    if not isfinite(x_value) or not isfinite(y_value):
        raise OverflowError("oval parameter point is not finite.")
    return (x_value, y_value)


def normalized_oval_residual(
    geometry: OvalExecutionGeometry,
    x_value: float,
    y_value: float,
) -> Fraction:
    """Return the exact normalized primitive-equation residual for one float point."""

    if type(geometry) is not OvalExecutionGeometry:
        raise TypeError("geometry must be an exact OvalExecutionGeometry.")
    if type(x_value) is not float or type(y_value) is not float:
        raise TypeError("oval residual coordinates must be exact floats.")
    if not isfinite(x_value) or not isfinite(y_value):
        raise ValueError("oval residual coordinates must be finite.")
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
        raise ZeroDivisionError("oval residual scale is zero.")
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
        raise OverflowError("oval semi-axis has no finite outward float64 bound.")
    return outward


def _outward_axis_bounds(
    center: Fraction,
    axis_squared: Fraction,
    nearest_axis: float,
) -> tuple[float, float]:
    center_float = _finite_fraction_float(center, "center")
    lower = center_float - nearest_axis
    upper = center_float + nearest_axis
    if not isfinite(lower) or not isfinite(upper):
        raise OverflowError("oval bounds are not finite.")
    while not _lower_encloses(center, axis_squared, lower):
        lower = nextafter(lower, -inf)
        if not isfinite(lower):
            raise OverflowError("oval lower bound has no finite representation.")
    while not _upper_encloses(center, axis_squared, upper):
        upper = nextafter(upper, inf)
        if not isfinite(upper):
            raise OverflowError("oval upper bound has no finite representation.")
    if lower >= upper:
        raise OverflowError("oval bounds collapse in float64.")
    return (lower, upper)


def _lower_encloses(center: Fraction, axis_squared: Fraction, candidate: float) -> bool:
    distance = center - Fraction.from_float(candidate)
    return distance >= 0 and distance * distance >= axis_squared


def _upper_encloses(center: Fraction, axis_squared: Fraction, candidate: float) -> bool:
    distance = Fraction.from_float(candidate) - center
    return distance >= 0 and distance * distance >= axis_squared


__all__: list[str] = []
