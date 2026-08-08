"""Bind sealed equation analysis results to immutable item specifications."""

from __future__ import annotations

from math_drawing_assistant.config.limits import ApplicationLimits, DEFAULT_LIMITS
from math_drawing_assistant.engine.equation_classifier import (
    CircleGeometry,
    EllipseGeometry,
    EquationGeometryResult,
    HyperbolaGeometry,
    LineGeometry,
    ParabolaGeometry,
)
from math_drawing_assistant.engine.equation_validator import (
    ValidatedEquationInput,
    _validate_validated_equation_input,
)
from math_drawing_assistant.models.plot_specs import (
    CircleSpec,
    EllipseSpec,
    HyperbolaSpec,
    LineSpec,
    ParabolaSpec,
    PrimitiveEquationCoefficients,
)


class EquationSpecBuilderError(ValueError):
    """A fixed, operand-free failure at the equation Spec boundary."""


def build_equation_spec(
    item_id: str,
    validated: ValidatedEquationInput,
    coefficients: PrimitiveEquationCoefficients,
    geometry: EquationGeometryResult,
    *,
    limits: ApplicationLimits = DEFAULT_LIMITS,
) -> LineSpec | CircleSpec | EllipseSpec | HyperbolaSpec | ParabolaSpec:
    """Project one formally classified equation into its matching Spec type."""

    if type(item_id) is not str or not item_id.strip():
        raise EquationSpecBuilderError("equation specification contract mismatch")
    if type(limits) is not ApplicationLimits:
        raise TypeError("limits must be an exact ApplicationLimits.")

    checked = _validate_validated_equation_input(validated, limits=limits)
    if type(coefficients) is not PrimitiveEquationCoefficients:
        raise EquationSpecBuilderError("equation specification contract mismatch")
    try:
        PrimitiveEquationCoefficients.__post_init__(coefficients)
    except (TypeError, ValueError):
        raise EquationSpecBuilderError(
            "equation specification contract mismatch",
        ) from None

    geometry_type = type(geometry)
    if geometry_type not in (
        LineGeometry,
        CircleGeometry,
        EllipseGeometry,
        HyperbolaGeometry,
        ParabolaGeometry,
    ):
        raise EquationSpecBuilderError("equation specification contract mismatch")
    if geometry.coefficients is not coefficients:
        raise EquationSpecBuilderError("equation specification contract mismatch")
    try:
        geometry.__post_init__()
        if geometry_type is LineGeometry:
            return LineSpec(item_id, coefficients, checked.provenance)
        if geometry_type is CircleGeometry:
            return CircleSpec(
                item_id,
                coefficients,
                checked.provenance,
                geometry.center_x,
                geometry.center_y,
                geometry.radius_squared,
            )
        if geometry_type is EllipseGeometry:
            return EllipseSpec(
                item_id,
                coefficients,
                checked.provenance,
                geometry.center_x,
                geometry.center_y,
                geometry.semi_axis_x_squared,
                geometry.semi_axis_y_squared,
                geometry.major_axis,
            )
        if geometry_type is HyperbolaGeometry:
            return HyperbolaSpec(
                item_id,
                coefficients,
                checked.provenance,
                geometry.center_x,
                geometry.center_y,
                geometry.semi_transverse_squared,
                geometry.semi_conjugate_squared,
                geometry.transverse_axis,
            )
        if geometry_type is ParabolaGeometry:
            return ParabolaSpec(
                item_id,
                coefficients,
                checked.provenance,
                geometry.vertex_x,
                geometry.vertex_y,
                geometry.focal_parameter,
                geometry.opening,
            )
    except (TypeError, ValueError):
        raise EquationSpecBuilderError(
            "equation specification contract mismatch",
        ) from None
    raise EquationSpecBuilderError("equation specification contract mismatch")


__all__ = ["EquationSpecBuilderError", "build_equation_spec"]
