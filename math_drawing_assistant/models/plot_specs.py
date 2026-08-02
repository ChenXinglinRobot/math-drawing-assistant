"""Minimal typed boundary for validated plot specifications."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from fractions import Fraction
from math import gcd
from typing import Literal, Protocol, TypeAlias, runtime_checkable

from math_drawing_assistant.models.errors import SourceSpan
from math_drawing_assistant.models.restricted_ast import (
    RestrictedExpression,
    _validate_restricted_expression,
)
from math_drawing_assistant.models.state import PlotKind


ExplicitExpressionSource: TypeAlias = Literal[
    "expression",
    "y_equals",
    "equals_y",
]

_VALIDATION_CONTRACT_SEAL = object()


@dataclass(frozen=True, slots=True)
class _ValidatedExpressionContract:
    """Internal receipt proving parser and active limits versions matched."""

    limits_version: str
    _seal: object

    def __post_init__(self) -> None:
        if self._seal is not _VALIDATION_CONTRACT_SEAL:
            raise TypeError("Validated expression contracts are issued internally.")
        if type(self.limits_version) is not str or not self.limits_version:
            raise ValueError("limits_version must be a non-empty string.")


def _issue_validated_expression_contract(
    *,
    parser_limits_version: str,
    active_limits_version: str,
) -> _ValidatedExpressionContract:
    if type(parser_limits_version) is not str or not parser_limits_version:
        raise ValueError("parser_limits_version must be a non-empty string.")
    if type(active_limits_version) is not str or not active_limits_version:
        raise ValueError("active_limits_version must be a non-empty string.")
    if parser_limits_version != active_limits_version:
        raise ValueError("Parser and active limits versions must match.")
    return _ValidatedExpressionContract(
        limits_version=active_limits_version,
        _seal=_VALIDATION_CONTRACT_SEAL,
    )


@dataclass(frozen=True, slots=True, init=False)
class ValidatedExplicitExpression:
    """A controlled stage 7 result, before a caller injects an item identity."""

    expression: RestrictedExpression
    normalized_input: str
    normalized_span: SourceSpan
    source_span: SourceSpan
    source_form: ExplicitExpressionSource
    free_variables: tuple[Literal["x"], ...]
    limits_version: str
    _contract: _ValidatedExpressionContract = field(repr=False)

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError(
            "ValidatedExplicitExpression is created by the validated stage 7 entry.",
        )

    @property
    def plot_kind(self) -> PlotKind:
        """Return the only plot kind delivered by stage 7."""

        return PlotKind.EXPLICIT_FUNCTION


def _create_validated_explicit_expression(
    *,
    expression: RestrictedExpression,
    normalized_input: str,
    normalized_span: SourceSpan,
    source_span: SourceSpan,
    source_form: ExplicitExpressionSource,
    free_variables: tuple[Literal["x"], ...],
    contract: _ValidatedExpressionContract,
) -> ValidatedExplicitExpression:
    if type(contract) is not _ValidatedExpressionContract:
        raise TypeError("contract must be an issued validated expression contract.")
    contract.__post_init__()
    variables = _validate_restricted_expression(expression)
    if "y" in variables:
        raise ValueError("A validated explicit expression must not contain y.")
    expected_free_variables: tuple[Literal["x"], ...] = (
        ("x",) if "x" in variables else ()
    )
    if type(free_variables) is not tuple or free_variables != expected_free_variables:
        raise ValueError("free_variables must match the restricted AST.")
    if type(normalized_input) is not str or not normalized_input:
        raise ValueError("normalized_input must be a non-empty string.")
    if type(normalized_span) is not SourceSpan:
        raise TypeError("normalized_span must be a SourceSpan.")
    if type(source_span) is not SourceSpan:
        raise TypeError("source_span must be a SourceSpan.")
    if expression.normalized_span != normalized_span:
        raise ValueError("normalized_span must match the expression root.")
    if expression.source_span != source_span:
        raise ValueError("source_span must match the expression root.")
    if source_form not in {"expression", "y_equals", "equals_y"}:
        raise ValueError("source_form must be a published explicit source form.")

    result = object.__new__(ValidatedExplicitExpression)
    object.__setattr__(result, "expression", expression)
    object.__setattr__(result, "normalized_input", normalized_input)
    object.__setattr__(result, "normalized_span", normalized_span)
    object.__setattr__(result, "source_span", source_span)
    object.__setattr__(result, "source_form", source_form)
    object.__setattr__(result, "free_variables", free_variables)
    object.__setattr__(result, "limits_version", contract.limits_version)
    object.__setattr__(result, "_contract", contract)
    return _validate_validated_explicit_expression(
        result,
        active_limits_version=contract.limits_version,
    )


def _validate_validated_explicit_expression(
    value: object,
    *,
    active_limits_version: str,
) -> ValidatedExplicitExpression:
    """Recheck the stage 7 receipt before a later trusted boundary uses it."""

    if type(value) is not ValidatedExplicitExpression:
        raise TypeError("value must be an exact ValidatedExplicitExpression.")
    if type(active_limits_version) is not str or not active_limits_version:
        raise ValueError("active_limits_version must be a non-empty string.")

    contract = getattr(value, "_contract", None)
    if type(contract) is not _ValidatedExpressionContract:
        raise TypeError("validated expression is missing its issued contract.")
    contract.__post_init__()
    if value.limits_version != contract.limits_version:
        raise ValueError("validated expression and receipt versions must match.")
    if value.limits_version != active_limits_version:
        raise ValueError("validated expression limits version is not active.")

    variables = _validate_restricted_expression(value.expression)
    if "y" in variables:
        raise ValueError("A validated explicit expression must not contain y.")
    expected_free_variables: tuple[Literal["x"], ...] = (
        ("x",) if "x" in variables else ()
    )
    if type(value.free_variables) is not tuple:
        raise TypeError("free_variables must be a tuple.")
    if value.free_variables != expected_free_variables:
        raise ValueError("free_variables must match the restricted AST.")
    if type(value.normalized_input) is not str or not value.normalized_input:
        raise ValueError("normalized_input must be a non-empty string.")
    if type(value.normalized_span) is not SourceSpan:
        raise TypeError("normalized_span must be a SourceSpan.")
    if type(value.source_span) is not SourceSpan:
        raise TypeError("source_span must be a SourceSpan.")
    if value.expression.normalized_span != value.normalized_span:
        raise ValueError("normalized_span must match the expression root.")
    if value.expression.source_span != value.source_span:
        raise ValueError("source_span must match the expression root.")
    if value.source_form not in {"expression", "y_equals", "equals_y"}:
        raise ValueError("source_form must be a published explicit source form.")
    if value.plot_kind is not PlotKind.EXPLICIT_FUNCTION:
        raise ValueError("validated expression must be an explicit function.")
    return value


@dataclass(frozen=True, slots=True)
class ExplicitFunctionSpec:
    """One explicit function bound to its stable request item identity."""

    item_id: str
    validated_expression: ValidatedExplicitExpression

    def __post_init__(self) -> None:
        if type(self.item_id) is not str or not self.item_id.strip():
            raise ValueError("ExplicitFunctionSpec.item_id must be a valid string.")
        if type(self.validated_expression) is not ValidatedExplicitExpression:
            raise TypeError(
                "validated_expression must be a ValidatedExplicitExpression.",
            )
        _validate_validated_explicit_expression(
            self.validated_expression,
            active_limits_version=self.validated_expression.limits_version,
        )

    @property
    def expression(self) -> RestrictedExpression:
        """Return the exact restricted AST issued by stage 7."""

        return self.validated_expression.expression

    @property
    def normalized_input(self) -> str:
        """Return the normalized expression snapshot from stage 7."""

        return self.validated_expression.normalized_input

    @property
    def normalized_span(self) -> SourceSpan:
        """Return the normalized expression root span."""

        return self.validated_expression.normalized_span

    @property
    def source_span(self) -> SourceSpan:
        """Return the original expression root span."""

        return self.validated_expression.source_span

    @property
    def source_form(self) -> ExplicitExpressionSource:
        """Return whether the expression came from an expression or direct y form."""

        return self.validated_expression.source_form

    @property
    def free_variables(self) -> tuple[Literal["x"], ...]:
        """Return the validated free-variable tuple."""

        return self.validated_expression.free_variables

    @property
    def limits_version(self) -> str:
        """Return the limits contract that validated this expression."""

        return self.validated_expression.limits_version

    @property
    def plot_kind(self) -> PlotKind:
        """Return the only plot kind represented by this specification."""

        return PlotKind.EXPLICIT_FUNCTION


@dataclass(frozen=True, slots=True)
class PrimitiveEquationCoefficients:
    """Primitive, sign-normalized coefficients for an equation equal to zero."""

    a: int
    b: int
    c: int
    d: int
    e: int
    f: int

    def __post_init__(self) -> None:
        values = (self.a, self.b, self.c, self.d, self.e, self.f)
        if any(type(value) is not int for value in values):
            raise TypeError("Equation coefficients must be exact integers.")
        nonzero = tuple(value for value in values if value != 0)
        if not nonzero:
            raise ValueError("Equation coefficients must not all be zero.")
        common_divisor = 0
        for value in nonzero:
            common_divisor = gcd(common_divisor, abs(value))
        if common_divisor != 1:
            raise ValueError("Equation coefficients must be primitive.")
        if nonzero[0] < 0:
            raise ValueError("The first nonzero equation coefficient must be positive.")


@dataclass(frozen=True, slots=True)
class EquationProvenance:
    """Normalized and original source locations for a classified equation."""

    normalized_input: str
    normalized_span: SourceSpan
    source_span: SourceSpan
    limits_version: str

    def __post_init__(self) -> None:
        if type(self.normalized_input) is not str:
            raise TypeError("normalized_input must be a string.")
        if not self.normalized_input:
            raise ValueError("normalized_input must not be empty.")
        if type(self.normalized_span) is not SourceSpan:
            raise TypeError("normalized_span must be a SourceSpan.")
        if type(self.source_span) is not SourceSpan:
            raise TypeError("source_span must be a SourceSpan.")
        if self.normalized_span.start == self.normalized_span.end:
            raise ValueError("normalized_span must not be empty.")
        if self.source_span.start == self.source_span.end:
            raise ValueError("source_span must not be empty.")
        if self.normalized_span.end > len(self.normalized_input):
            raise ValueError("normalized_span must fit normalized_input.")
        if type(self.limits_version) is not str:
            raise TypeError("limits_version must be a string.")
        if not self.limits_version.strip():
            raise ValueError("limits_version must not be blank.")


class AxisOrientation(str, Enum):
    """An axis aligned with one coordinate direction."""

    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"


class ParabolaOpening(str, Enum):
    """The opening direction of an axis-aligned parabola."""

    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"


def _validate_equation_spec_common(
    item_id: object,
    coefficients: object,
    provenance: object,
) -> None:
    if type(item_id) is not str or not item_id.strip():
        raise ValueError("item_id must be a valid string.")
    if type(coefficients) is not PrimitiveEquationCoefficients:
        raise TypeError("coefficients must be PrimitiveEquationCoefficients.")
    if type(provenance) is not EquationProvenance:
        raise TypeError("provenance must be EquationProvenance.")


def _require_fraction(value: object, field_name: str) -> Fraction:
    if type(value) is not Fraction:
        raise TypeError(f"{field_name} must be an exact Fraction.")
    return value


@dataclass(frozen=True, slots=True)
class LineSpec:
    """A validated general line in canonical implicit form."""

    item_id: str
    coefficients: PrimitiveEquationCoefficients
    provenance: EquationProvenance

    def __post_init__(self) -> None:
        _validate_equation_spec_common(
            self.item_id,
            self.coefficients,
            self.provenance,
        )
        if any((self.coefficients.a, self.coefficients.b, self.coefficients.c)):
            raise ValueError("LineSpec must not contain quadratic terms.")
        if self.coefficients.d == 0 and self.coefficients.e == 0:
            raise ValueError("LineSpec must contain a variable term.")

    @property
    def d(self) -> int:
        return self.coefficients.d

    @property
    def e(self) -> int:
        return self.coefficients.e

    @property
    def f(self) -> int:
        return self.coefficients.f

    @property
    def plot_kind(self) -> PlotKind:
        return PlotKind.LINE_EQUATION


@dataclass(frozen=True, slots=True)
class CircleSpec:
    """A validated nondegenerate circle with exact geometry."""

    item_id: str
    coefficients: PrimitiveEquationCoefficients
    provenance: EquationProvenance
    center_x: Fraction
    center_y: Fraction
    radius_squared: Fraction

    def __post_init__(self) -> None:
        _validate_equation_spec_common(
            self.item_id,
            self.coefficients,
            self.provenance,
        )
        _require_fraction(self.center_x, "center_x")
        _require_fraction(self.center_y, "center_y")
        radius_squared = _require_fraction(self.radius_squared, "radius_squared")
        if self.coefficients.b != 0:
            raise ValueError("CircleSpec must not contain an xy term.")
        if self.coefficients.a != self.coefficients.c or self.coefficients.a <= 0:
            raise ValueError("CircleSpec quadratic coefficients must be equal and positive.")
        if radius_squared <= 0:
            raise ValueError("radius_squared must be positive.")

    @property
    def plot_kind(self) -> PlotKind:
        return PlotKind.CONIC_EQUATION


@dataclass(frozen=True, slots=True)
class EllipseSpec:
    """A validated noncircular, axis-aligned ellipse with exact geometry."""

    item_id: str
    coefficients: PrimitiveEquationCoefficients
    provenance: EquationProvenance
    center_x: Fraction
    center_y: Fraction
    semi_axis_x_squared: Fraction
    semi_axis_y_squared: Fraction
    major_axis: AxisOrientation

    def __post_init__(self) -> None:
        _validate_equation_spec_common(
            self.item_id,
            self.coefficients,
            self.provenance,
        )
        _require_fraction(self.center_x, "center_x")
        _require_fraction(self.center_y, "center_y")
        semi_x = _require_fraction(self.semi_axis_x_squared, "semi_axis_x_squared")
        semi_y = _require_fraction(self.semi_axis_y_squared, "semi_axis_y_squared")
        if type(self.major_axis) is not AxisOrientation:
            raise TypeError("major_axis must be an AxisOrientation.")
        if self.coefficients.b != 0:
            raise ValueError("EllipseSpec must not contain an xy term.")
        if self.coefficients.a <= 0 or self.coefficients.c <= 0:
            raise ValueError("EllipseSpec quadratic coefficients must be positive.")
        if self.coefficients.a == self.coefficients.c:
            raise ValueError("A circle must use CircleSpec.")
        if semi_x <= 0 or semi_y <= 0 or semi_x == semi_y:
            raise ValueError("EllipseSpec semi-axis squares must be distinct and positive.")
        expected_axis = (
            AxisOrientation.HORIZONTAL if semi_x > semi_y else AxisOrientation.VERTICAL
        )
        if self.major_axis is not expected_axis:
            raise ValueError("major_axis must identify the larger semi-axis.")

    @property
    def plot_kind(self) -> PlotKind:
        return PlotKind.CONIC_EQUATION


@dataclass(frozen=True, slots=True)
class HyperbolaSpec:
    """A validated axis-aligned hyperbola with exact geometry."""

    item_id: str
    coefficients: PrimitiveEquationCoefficients
    provenance: EquationProvenance
    center_x: Fraction
    center_y: Fraction
    semi_transverse_squared: Fraction
    semi_conjugate_squared: Fraction
    transverse_axis: AxisOrientation

    def __post_init__(self) -> None:
        _validate_equation_spec_common(
            self.item_id,
            self.coefficients,
            self.provenance,
        )
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
        if type(self.transverse_axis) is not AxisOrientation:
            raise TypeError("transverse_axis must be an AxisOrientation.")
        a = self.coefficients.a
        c = self.coefficients.c
        if self.coefficients.b != 0:
            raise ValueError("HyperbolaSpec must not contain an xy term.")
        if not ((a > 0 and c < 0) or (a < 0 and c > 0)):
            raise ValueError("HyperbolaSpec quadratic coefficients must have opposite signs.")
        if transverse <= 0 or conjugate <= 0:
            raise ValueError("HyperbolaSpec axis squares must be positive.")

    @property
    def plot_kind(self) -> PlotKind:
        return PlotKind.CONIC_EQUATION


@dataclass(frozen=True, slots=True)
class ParabolaSpec:
    """A validated axis-aligned parabola with exact geometry."""

    item_id: str
    coefficients: PrimitiveEquationCoefficients
    provenance: EquationProvenance
    vertex_x: Fraction
    vertex_y: Fraction
    focal_parameter: Fraction
    opening: ParabolaOpening

    def __post_init__(self) -> None:
        _validate_equation_spec_common(
            self.item_id,
            self.coefficients,
            self.provenance,
        )
        _require_fraction(self.vertex_x, "vertex_x")
        _require_fraction(self.vertex_y, "vertex_y")
        focal_parameter = _require_fraction(
            self.focal_parameter,
            "focal_parameter",
        )
        if type(self.opening) is not ParabolaOpening:
            raise TypeError("opening must be a ParabolaOpening.")
        a = self.coefficients.a
        c = self.coefficients.c
        if self.coefficients.b != 0:
            raise ValueError("ParabolaSpec must not contain an xy term.")
        if (a == 0) == (c == 0):
            raise ValueError("ParabolaSpec must contain exactly one squared variable.")
        if focal_parameter == 0:
            raise ValueError("focal_parameter must not be zero.")
        if a != 0:
            expected = (
                ParabolaOpening.UP
                if focal_parameter > 0
                else ParabolaOpening.DOWN
            )
        else:
            expected = (
                ParabolaOpening.RIGHT
                if focal_parameter > 0
                else ParabolaOpening.LEFT
            )
        if self.opening is not expected:
            raise ValueError("opening must match the squared variable and focal parameter.")

    @property
    def plot_kind(self) -> PlotKind:
        return PlotKind.CONIC_EQUATION


@runtime_checkable
class PlotItemSpec(Protocol):
    """Contract fulfilled by future validated, immutable item specifications."""

    @property
    def item_id(self) -> str:
        """Return the item identity inherited from its request."""

    @property
    def plot_kind(self) -> PlotKind:
        """Return the classified plot kind."""


@dataclass(frozen=True, slots=True)
class PlotSceneSpec:
    """Validated snapshot of all items in a scene."""

    items: tuple[PlotItemSpec, ...]

    def __post_init__(self) -> None:
        item_snapshot = tuple(self.items)
        if not item_snapshot:
            raise ValueError("PlotSceneSpec.items must not be empty.")
        if not all(isinstance(item, PlotItemSpec) for item in item_snapshot):
            raise TypeError("items must satisfy the PlotItemSpec contract.")

        item_ids = tuple(item.item_id for item in item_snapshot)
        if len(set(item_ids)) != len(item_ids):
            raise ValueError("PlotSceneSpec item_id values must be unique.")
        object.__setattr__(self, "items", item_snapshot)
