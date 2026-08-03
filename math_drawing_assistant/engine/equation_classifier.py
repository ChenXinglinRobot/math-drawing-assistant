"""Exact geometry classification for canonical line and conic coefficients."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from fractions import Fraction
from typing import TypeAlias

from math_drawing_assistant.config.limits import ApplicationLimits, DEFAULT_LIMITS
from math_drawing_assistant.engine.exact_rational import (
    ExactLimitComponent,
    ExactRationalLimitExceeded,
    ensure_canonical_integer_within_limit,
    ensure_fraction_within_limits,
)
from math_drawing_assistant.models.plot_specs import (
    AxisOrientation,
    ParabolaOpening,
    PrimitiveEquationCoefficients,
)


_INVARIANT_MESSAGE = "equation geometry classification invariant violated"


class EquationGeometryFailureKind(str, Enum):
    """Closed failures produced by exact equation geometry classification."""

    ROTATED_CONIC_NOT_SUPPORTED = "rotated_conic_not_supported"
    DEGENERATE_CONIC = "degenerate_conic"
    CONIC_HAS_NO_REAL_POINTS = "conic_has_no_real_points"
    RESOURCE_LIMIT_EXCEEDED = "resource_limit_exceeded"


class EquationGeometryError(ValueError):
    """A typed, operand-free geometry classification failure."""

    __slots__ = ("kind", "exact_limit_component", "exact_limit")

    kind: EquationGeometryFailureKind
    exact_limit_component: ExactLimitComponent | None
    exact_limit: int | None

    def __init__(
        self,
        kind: EquationGeometryFailureKind,
        exact_limit_component: ExactLimitComponent | None = None,
        exact_limit: int | None = None,
    ) -> None:
        if type(kind) is not EquationGeometryFailureKind:
            raise TypeError("kind must be an exact EquationGeometryFailureKind")

        if kind is EquationGeometryFailureKind.RESOURCE_LIMIT_EXCEEDED:
            if type(exact_limit_component) is not ExactLimitComponent:
                raise TypeError(
                    "resource failures require an exact ExactLimitComponent",
                )
            if type(exact_limit) is not int:
                raise TypeError("resource failures require a positive exact int limit")
            if exact_limit <= 0:
                raise ValueError("resource failure limit must be positive")
            message = (
                "equation geometry classification failed "
                f"(resource_limit_exceeded: {exact_limit_component.value}, "
                f"limit={exact_limit})"
            )
        else:
            if exact_limit_component is not None or exact_limit is not None:
                raise ValueError(
                    "non-resource failures must not carry exact limit metadata",
                )
            message = f"equation geometry classification failed ({kind.value})"

        self.kind = kind
        self.exact_limit_component = exact_limit_component
        self.exact_limit = exact_limit
        super().__init__(message)


def _require_coefficients(value: object) -> PrimitiveEquationCoefficients:
    if type(value) is not PrimitiveEquationCoefficients:
        raise TypeError("coefficients must be an exact PrimitiveEquationCoefficients")
    return value


def _require_fraction(value: object, name: str) -> Fraction:
    if type(value) is not Fraction:
        raise TypeError(f"{name} must be an exact Fraction")
    return value


def _require_axis_orientation(value: object, name: str) -> AxisOrientation:
    if type(value) is not AxisOrientation:
        raise TypeError(f"{name} must be an exact AxisOrientation")
    return value


def _require_parabola_opening(value: object) -> ParabolaOpening:
    if type(value) is not ParabolaOpening:
        raise TypeError("opening must be an exact ParabolaOpening")
    return value


@dataclass(frozen=True, slots=True)
class LineGeometry:
    """Canonical coefficients for one nondegenerate general line."""

    coefficients: PrimitiveEquationCoefficients

    def __post_init__(self) -> None:
        coefficients = _require_coefficients(self.coefficients)
        if coefficients.a != 0 or coefficients.b != 0 or coefficients.c != 0:
            raise ValueError("line geometry must not contain quadratic terms")
        if coefficients.d == 0 and coefficients.e == 0:
            raise ValueError("line geometry must contain a variable term")


@dataclass(frozen=True, slots=True)
class CircleGeometry:
    """Exact center and squared radius of one nondegenerate circle."""

    coefficients: PrimitiveEquationCoefficients
    center_x: Fraction
    center_y: Fraction
    radius_squared: Fraction

    def __post_init__(self) -> None:
        coefficients = _require_coefficients(self.coefficients)
        _require_fraction(self.center_x, "center_x")
        _require_fraction(self.center_y, "center_y")
        radius_squared = _require_fraction(self.radius_squared, "radius_squared")
        if coefficients.b != 0:
            raise ValueError("circle geometry must not contain an xy term")
        if coefficients.a != coefficients.c or coefficients.a <= 0:
            raise ValueError("circle quadratic coefficients must be equal and positive")
        if radius_squared <= 0:
            raise ValueError("radius_squared must be positive")


@dataclass(frozen=True, slots=True)
class EllipseGeometry:
    """Exact center and squared semi-axes of one axis-aligned ellipse."""

    coefficients: PrimitiveEquationCoefficients
    center_x: Fraction
    center_y: Fraction
    semi_axis_x_squared: Fraction
    semi_axis_y_squared: Fraction
    major_axis: AxisOrientation

    def __post_init__(self) -> None:
        coefficients = _require_coefficients(self.coefficients)
        _require_fraction(self.center_x, "center_x")
        _require_fraction(self.center_y, "center_y")
        semi_x = _require_fraction(
            self.semi_axis_x_squared,
            "semi_axis_x_squared",
        )
        semi_y = _require_fraction(
            self.semi_axis_y_squared,
            "semi_axis_y_squared",
        )
        major_axis = _require_axis_orientation(self.major_axis, "major_axis")
        if coefficients.b != 0:
            raise ValueError("ellipse geometry must not contain an xy term")
        if coefficients.a <= 0 or coefficients.c <= 0:
            raise ValueError("ellipse quadratic coefficients must be positive")
        if coefficients.a == coefficients.c:
            raise ValueError("circle coefficients cannot construct ellipse geometry")
        if semi_x <= 0 or semi_y <= 0 or semi_x == semi_y:
            raise ValueError("ellipse semi-axis squares must be distinct and positive")
        expected_axis = (
            AxisOrientation.HORIZONTAL
            if semi_x > semi_y
            else AxisOrientation.VERTICAL
        )
        if major_axis is not expected_axis:
            raise ValueError("major_axis must identify the larger semi-axis")


@dataclass(frozen=True, slots=True)
class HyperbolaGeometry:
    """Exact center and squared axes of one axis-aligned hyperbola."""

    coefficients: PrimitiveEquationCoefficients
    center_x: Fraction
    center_y: Fraction
    semi_transverse_squared: Fraction
    semi_conjugate_squared: Fraction
    transverse_axis: AxisOrientation

    def __post_init__(self) -> None:
        coefficients = _require_coefficients(self.coefficients)
        _require_fraction(self.center_x, "center_x")
        _require_fraction(self.center_y, "center_y")
        transverse = _require_fraction(
            self.semi_transverse_squared,
            "semi_transverse_squared",
        )
        conjugate = _require_fraction(
            self.semi_conjugate_squared,
            "semi_conjugate_squared",
        )
        _require_axis_orientation(self.transverse_axis, "transverse_axis")
        a = coefficients.a
        c = coefficients.c
        if coefficients.b != 0:
            raise ValueError("hyperbola geometry must not contain an xy term")
        if not ((a > 0 and c < 0) or (a < 0 and c > 0)):
            raise ValueError("hyperbola quadratic coefficients must have opposite signs")
        if transverse <= 0 or conjugate <= 0:
            raise ValueError("hyperbola axis squares must be positive")


@dataclass(frozen=True, slots=True)
class ParabolaGeometry:
    """Exact vertex and focal parameter of one axis-aligned parabola."""

    coefficients: PrimitiveEquationCoefficients
    vertex_x: Fraction
    vertex_y: Fraction
    focal_parameter: Fraction
    opening: ParabolaOpening

    def __post_init__(self) -> None:
        coefficients = _require_coefficients(self.coefficients)
        _require_fraction(self.vertex_x, "vertex_x")
        _require_fraction(self.vertex_y, "vertex_y")
        focal_parameter = _require_fraction(
            self.focal_parameter,
            "focal_parameter",
        )
        opening = _require_parabola_opening(self.opening)
        a = coefficients.a
        c = coefficients.c
        if coefficients.b != 0:
            raise ValueError("parabola geometry must not contain an xy term")
        if (a == 0) == (c == 0):
            raise ValueError("parabola geometry must contain one squared variable")
        if focal_parameter == 0:
            raise ValueError("focal_parameter must not be zero")
        if a != 0:
            if coefficients.e == 0:
                raise ValueError("vertical parabola must contain a y term")
            expected = (
                ParabolaOpening.UP
                if focal_parameter > 0
                else ParabolaOpening.DOWN
            )
        else:
            if coefficients.d == 0:
                raise ValueError("horizontal parabola must contain an x term")
            expected = (
                ParabolaOpening.RIGHT
                if focal_parameter > 0
                else ParabolaOpening.LEFT
            )
        if opening is not expected:
            raise ValueError("opening must match the squared variable and focal parameter")


EquationGeometryResult: TypeAlias = (
    LineGeometry
    | CircleGeometry
    | EllipseGeometry
    | HyperbolaGeometry
    | ParabolaGeometry
)


def _bounded_geometry_fraction(
    numerator: int,
    denominator: int,
    *,
    limits: ApplicationLimits,
) -> Fraction:
    if type(numerator) is not int:
        raise TypeError("numerator must be an exact int")
    if type(denominator) is not int:
        raise TypeError("denominator must be an exact int")
    if denominator == 0:
        raise RuntimeError(_INVARIANT_MESSAGE)
    reduced = Fraction(numerator, denominator)
    return ensure_fraction_within_limits(reduced, limits=limits)


def classify_equation_geometry(
    coefficients: PrimitiveEquationCoefficients,
    *,
    limits: ApplicationLimits = DEFAULT_LIMITS,
) -> EquationGeometryResult:
    """Classify canonical coefficients using bounded exact arithmetic only."""

    coefficients = _require_coefficients(coefficients)
    if type(limits) is not ApplicationLimits:
        raise TypeError("limits must be an exact ApplicationLimits")

    a = coefficients.a
    b = coefficients.b
    c = coefficients.c
    d = coefficients.d
    e = coefficients.e
    f = coefficients.f

    try:
        for value in (a, b, c, d, e, f):
            ensure_canonical_integer_within_limit(value, limits=limits)

        if a == 0 and b == 0 and c == 0:
            if d == 0 and e == 0:
                raise ValueError("equation geometry requires a variable term")
            return LineGeometry(coefficients)

        if b != 0:
            raise EquationGeometryError(
                EquationGeometryFailureKind.ROTATED_CONIC_NOT_SUPPORTED,
            )

        if a != 0 and c != 0:
            q = d * d * c + e * e * a - 4 * a * c * f
            center_x = _bounded_geometry_fraction(-d, 2 * a, limits=limits)
            center_y = _bounded_geometry_fraction(-e, 2 * c, limits=limits)
            signed_x = _bounded_geometry_fraction(
                q,
                4 * a * a * c,
                limits=limits,
            )
            signed_y = _bounded_geometry_fraction(
                q,
                4 * a * c * c,
                limits=limits,
            )

            if a == c:
                if signed_x != signed_y:
                    raise RuntimeError(_INVARIANT_MESSAGE)
                if signed_x == 0:
                    raise EquationGeometryError(
                        EquationGeometryFailureKind.DEGENERATE_CONIC,
                    )
                if signed_x < 0:
                    raise EquationGeometryError(
                        EquationGeometryFailureKind.CONIC_HAS_NO_REAL_POINTS,
                    )
                return CircleGeometry(
                    coefficients,
                    center_x,
                    center_y,
                    signed_x,
                )

            same_sign = (a > 0 and c > 0) or (a < 0 and c < 0)
            if same_sign:
                if signed_x == 0 or signed_y == 0:
                    raise EquationGeometryError(
                        EquationGeometryFailureKind.DEGENERATE_CONIC,
                    )
                if signed_x < 0 or signed_y < 0:
                    raise EquationGeometryError(
                        EquationGeometryFailureKind.CONIC_HAS_NO_REAL_POINTS,
                    )
                if signed_x == signed_y:
                    raise RuntimeError(_INVARIANT_MESSAGE)
                major_axis = (
                    AxisOrientation.HORIZONTAL
                    if signed_x > signed_y
                    else AxisOrientation.VERTICAL
                )
                return EllipseGeometry(
                    coefficients,
                    center_x,
                    center_y,
                    signed_x,
                    signed_y,
                    major_axis,
                )

            if q == 0:
                raise EquationGeometryError(
                    EquationGeometryFailureKind.DEGENERATE_CONIC,
                )
            if signed_x > 0 and signed_y < 0:
                return HyperbolaGeometry(
                    coefficients,
                    center_x,
                    center_y,
                    signed_x,
                    -signed_y,
                    AxisOrientation.HORIZONTAL,
                )
            if signed_y > 0 and signed_x < 0:
                return HyperbolaGeometry(
                    coefficients,
                    center_x,
                    center_y,
                    signed_y,
                    -signed_x,
                    AxisOrientation.VERTICAL,
                )
            raise RuntimeError(_INVARIANT_MESSAGE)

        if a != 0 and c == 0:
            axis_center_x = _bounded_geometry_fraction(-d, 2 * a, limits=limits)
            if e != 0:
                vertex_y = _bounded_geometry_fraction(
                    d * d - 4 * a * f,
                    4 * a * e,
                    limits=limits,
                )
                focal_parameter = _bounded_geometry_fraction(
                    -e,
                    4 * a,
                    limits=limits,
                )
                opening = (
                    ParabolaOpening.UP
                    if focal_parameter > 0
                    else ParabolaOpening.DOWN
                )
                return ParabolaGeometry(
                    coefficients,
                    axis_center_x,
                    vertex_y,
                    focal_parameter,
                    opening,
                )
            discriminant_x = d * d - 4 * a * f
            if discriminant_x >= 0:
                raise EquationGeometryError(
                    EquationGeometryFailureKind.DEGENERATE_CONIC,
                )
            raise EquationGeometryError(
                EquationGeometryFailureKind.CONIC_HAS_NO_REAL_POINTS,
            )

        if a == 0 and c != 0:
            axis_center_y = _bounded_geometry_fraction(-e, 2 * c, limits=limits)
            if d != 0:
                vertex_x = _bounded_geometry_fraction(
                    e * e - 4 * c * f,
                    4 * c * d,
                    limits=limits,
                )
                focal_parameter = _bounded_geometry_fraction(
                    -d,
                    4 * c,
                    limits=limits,
                )
                opening = (
                    ParabolaOpening.RIGHT
                    if focal_parameter > 0
                    else ParabolaOpening.LEFT
                )
                return ParabolaGeometry(
                    coefficients,
                    vertex_x,
                    axis_center_y,
                    focal_parameter,
                    opening,
                )
            discriminant_y = e * e - 4 * c * f
            if discriminant_y >= 0:
                raise EquationGeometryError(
                    EquationGeometryFailureKind.DEGENERATE_CONIC,
                )
            raise EquationGeometryError(
                EquationGeometryFailureKind.CONIC_HAS_NO_REAL_POINTS,
            )

        raise RuntimeError(_INVARIANT_MESSAGE)
    except ExactRationalLimitExceeded as exc:
        mapped_error = EquationGeometryError(
            EquationGeometryFailureKind.RESOURCE_LIMIT_EXCEEDED,
            exc.component,
            exc.limit,
        )
        raise mapped_error from None


__all__ = [
    "LineGeometry",
    "CircleGeometry",
    "EllipseGeometry",
    "HyperbolaGeometry",
    "ParabolaGeometry",
    "EquationGeometryResult",
    "EquationGeometryFailureKind",
    "EquationGeometryError",
    "classify_equation_geometry",
]
