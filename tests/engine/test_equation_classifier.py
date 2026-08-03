"""Stage 13C tests for exact line and axis-aligned conic classification."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, fields, replace
from fractions import Fraction
import inspect
from pathlib import Path
from typing import get_args

import pytest

from math_drawing_assistant.config.limits import ApplicationLimits, DEFAULT_LIMITS
from math_drawing_assistant.engine import equation_classifier as classifier_module
from math_drawing_assistant.engine.equation_classifier import (
    CircleGeometry,
    EllipseGeometry,
    EquationGeometryError,
    EquationGeometryFailureKind,
    EquationGeometryResult,
    HyperbolaGeometry,
    LineGeometry,
    ParabolaGeometry,
    classify_equation_geometry,
)
from math_drawing_assistant.engine.equation_polynomial import canonicalize_equation
from math_drawing_assistant.engine.equation_splitter import (
    EquationInput,
    ExpressionInput,
    split_equation,
)
from math_drawing_assistant.engine.exact_rational import ExactLimitComponent
from math_drawing_assistant.engine.normalizer import NormalizedInput, normalize_input
from math_drawing_assistant.engine.parser import (
    ParsedEquationInput,
    ParsedExpressionInput,
    parse_input,
)
from math_drawing_assistant.engine.tokenizer import tokenize
from math_drawing_assistant.models.errors import ErrorCode
from math_drawing_assistant.models.plot_specs import (
    AxisOrientation,
    ParabolaOpening,
    PrimitiveEquationCoefficients,
)


class _FractionSubclass(Fraction):
    pass


class _CoefficientSubclass(PrimitiveEquationCoefficients):
    pass


class _LimitsSubclass(ApplicationLimits):
    pass


def _canonical(
    text: str,
    *,
    limits: ApplicationLimits = DEFAULT_LIMITS,
) -> PrimitiveEquationCoefficients:
    normalized = normalize_input(text, limits=limits)
    assert isinstance(normalized, NormalizedInput)
    tokens = tokenize(normalized, limits=limits)
    assert isinstance(tokens, tuple)
    split = split_equation(tokens)
    assert isinstance(split, (ExpressionInput, EquationInput))
    parsed = parse_input(split, limits=limits)
    assert isinstance(parsed, (ParsedExpressionInput, ParsedEquationInput))
    assert isinstance(parsed, ParsedEquationInput)
    return canonicalize_equation(parsed.left, parsed.right, limits=limits)


def _geometry(
    text: str,
    *,
    limits: ApplicationLimits = DEFAULT_LIMITS,
) -> EquationGeometryResult:
    return classify_equation_geometry(_canonical(text, limits=limits), limits=limits)


def _failure(
    coefficients: PrimitiveEquationCoefficients,
    kind: EquationGeometryFailureKind,
    *,
    limits: ApplicationLimits = DEFAULT_LIMITS,
) -> EquationGeometryError:
    with pytest.raises(EquationGeometryError) as exception:
        classify_equation_geometry(coefficients, limits=limits)
    assert exception.value.kind is kind
    return exception.value


def test_failure_kind_is_the_exact_error_registry_subset() -> None:
    expected = {
        EquationGeometryFailureKind.ROTATED_CONIC_NOT_SUPPORTED: (
            ErrorCode.ROTATED_CONIC_NOT_SUPPORTED
        ),
        EquationGeometryFailureKind.DEGENERATE_CONIC: ErrorCode.DEGENERATE_CONIC,
        EquationGeometryFailureKind.CONIC_HAS_NO_REAL_POINTS: (
            ErrorCode.CONIC_HAS_NO_REAL_POINTS
        ),
        EquationGeometryFailureKind.RESOURCE_LIMIT_EXCEEDED: (
            ErrorCode.RESOURCE_LIMIT_EXCEEDED
        ),
    }
    assert list(EquationGeometryFailureKind) == list(expected)
    assert all(kind.value == code.value for kind, code in expected.items())


def test_geometry_error_has_exact_metadata_and_safe_fixed_messages() -> None:
    rotated = EquationGeometryError(
        EquationGeometryFailureKind.ROTATED_CONIC_NOT_SUPPORTED,
    )
    assert isinstance(rotated, ValueError)
    assert type(rotated.kind) is EquationGeometryFailureKind
    assert rotated.exact_limit_component is None
    assert rotated.exact_limit is None
    assert str(rotated) == (
        "equation geometry classification failed (rotated_conic_not_supported)"
    )

    resource = EquationGeometryError(
        EquationGeometryFailureKind.RESOURCE_LIMIT_EXCEEDED,
        ExactLimitComponent.CANONICAL_INTEGER,
        768,
    )
    assert resource.exact_limit_component is ExactLimitComponent.CANONICAL_INTEGER
    assert resource.exact_limit == 768
    assert str(resource) == (
        "equation geometry classification failed "
        "(resource_limit_exceeded: canonical integer, limit=768)"
    )
    assert EquationGeometryError.__slots__ == (
        "kind",
        "exact_limit_component",
        "exact_limit",
    )
    assert "coefficients" not in vars(resource)


@pytest.mark.parametrize("kind", [True, "degenerate_conic", object()])
def test_geometry_error_requires_exact_failure_kind(kind: object) -> None:
    with pytest.raises(TypeError):
        EquationGeometryError(kind)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("component", "limit"),
    [
        (None, 1),
        ("canonical integer", 1),
        (ExactLimitComponent.CANONICAL_INTEGER, None),
        (ExactLimitComponent.CANONICAL_INTEGER, True),
        (ExactLimitComponent.CANONICAL_INTEGER, "768"),
    ],
)
def test_resource_error_requires_complete_exact_metadata(
    component: object,
    limit: object,
) -> None:
    with pytest.raises(TypeError):
        EquationGeometryError(
            EquationGeometryFailureKind.RESOURCE_LIMIT_EXCEEDED,
            component,  # type: ignore[arg-type]
            limit,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("limit", [0, -1])
def test_resource_error_requires_positive_limit(limit: int) -> None:
    with pytest.raises(ValueError):
        EquationGeometryError(
            EquationGeometryFailureKind.RESOURCE_LIMIT_EXCEEDED,
            ExactLimitComponent.CANONICAL_INTEGER,
            limit,
        )


@pytest.mark.parametrize(
    "kind",
    [
        EquationGeometryFailureKind.ROTATED_CONIC_NOT_SUPPORTED,
        EquationGeometryFailureKind.DEGENERATE_CONIC,
        EquationGeometryFailureKind.CONIC_HAS_NO_REAL_POINTS,
    ],
)
def test_non_resource_errors_reject_limit_metadata(
    kind: EquationGeometryFailureKind,
) -> None:
    with pytest.raises(ValueError):
        EquationGeometryError(
            kind,
            ExactLimitComponent.CANONICAL_INTEGER,
            768,
        )


def test_module_all_and_classifier_signature_are_frozen() -> None:
    expected = {
        "LineGeometry",
        "CircleGeometry",
        "EllipseGeometry",
        "HyperbolaGeometry",
        "ParabolaGeometry",
        "EquationGeometryResult",
        "EquationGeometryFailureKind",
        "EquationGeometryError",
        "classify_equation_geometry",
    }
    assert set(classifier_module.__all__) == expected
    assert len(classifier_module.__all__) == len(expected)

    parameters = list(inspect.signature(classify_equation_geometry).parameters.values())
    assert [parameter.name for parameter in parameters] == ["coefficients", "limits"]
    assert parameters[0].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert parameters[1].kind is inspect.Parameter.KEYWORD_ONLY
    assert parameters[1].default is DEFAULT_LIMITS


def test_classifier_rejects_wrong_and_subclassed_boundary_types() -> None:
    coefficients = PrimitiveEquationCoefficients(0, 0, 0, 1, 0, -2)
    subclassed_coefficients = _CoefficientSubclass(0, 0, 0, 1, 0, -2)
    limits_values = {
        field.name: getattr(DEFAULT_LIMITS, field.name)
        for field in fields(ApplicationLimits)
    }
    subclassed_limits = _LimitsSubclass(**limits_values)

    for bad in (None, coefficients.a, subclassed_coefficients):
        with pytest.raises(TypeError):
            classify_equation_geometry(bad)  # type: ignore[arg-type]
    for bad in (None, True, subclassed_limits):
        with pytest.raises(TypeError):
            classify_equation_geometry(coefficients, limits=bad)  # type: ignore[arg-type]


def test_pure_constant_vector_is_an_internal_call_contract_error() -> None:
    coefficients = PrimitiveEquationCoefficients(0, 0, 0, 0, 0, 1)
    with pytest.raises(ValueError, match="variable term"):
        classify_equation_geometry(coefficients)


def test_geometry_classes_have_exact_fields_and_value_model_properties() -> None:
    expected_fields = {
        LineGeometry: ("coefficients",),
        CircleGeometry: ("coefficients", "center_x", "center_y", "radius_squared"),
        EllipseGeometry: (
            "coefficients",
            "center_x",
            "center_y",
            "semi_axis_x_squared",
            "semi_axis_y_squared",
            "major_axis",
        ),
        HyperbolaGeometry: (
            "coefficients",
            "center_x",
            "center_y",
            "semi_transverse_squared",
            "semi_conjugate_squared",
            "transverse_axis",
        ),
        ParabolaGeometry: (
            "coefficients",
            "vertex_x",
            "vertex_y",
            "focal_parameter",
            "opening",
        ),
    }
    values = (
        LineGeometry(PrimitiveEquationCoefficients(0, 0, 0, 1, 0, -2)),
        CircleGeometry(
            PrimitiveEquationCoefficients(1, 0, 1, 0, 0, -1),
            Fraction(0),
            Fraction(0),
            Fraction(1),
        ),
        EllipseGeometry(
            PrimitiveEquationCoefficients(4, 0, 9, 0, 0, -36),
            Fraction(0),
            Fraction(0),
            Fraction(9),
            Fraction(4),
            AxisOrientation.HORIZONTAL,
        ),
        HyperbolaGeometry(
            PrimitiveEquationCoefficients(4, 0, -9, 0, 0, -36),
            Fraction(0),
            Fraction(0),
            Fraction(9),
            Fraction(4),
            AxisOrientation.HORIZONTAL,
        ),
        ParabolaGeometry(
            PrimitiveEquationCoefficients(1, 0, 0, 0, -4, 0),
            Fraction(0),
            Fraction(0),
            Fraction(1),
            ParabolaOpening.UP,
        ),
    )
    for value in values:
        assert tuple(field.name for field in fields(value)) == expected_fields[type(value)]
        assert not hasattr(value, "__dict__")
        assert hash(value)
        with pytest.raises(FrozenInstanceError):
            value.coefficients = value.coefficients  # type: ignore[misc]


def test_result_union_is_exactly_the_five_concrete_geometry_types() -> None:
    assert set(get_args(EquationGeometryResult)) == {
        LineGeometry,
        CircleGeometry,
        EllipseGeometry,
        HyperbolaGeometry,
        ParabolaGeometry,
    }
    for forbidden in (
        "ConicGeometry",
        "GeometryKind",
        "ConicType",
        "is_circle",
        "is_ellipse",
    ):
        assert not hasattr(classifier_module, forbidden)


def test_geometry_constructors_require_exact_coefficients_and_fractions() -> None:
    circle_coefficients = PrimitiveEquationCoefficients(1, 0, 1, 0, 0, -1)
    subclassed = _CoefficientSubclass(1, 0, 1, 0, 0, -1)
    with pytest.raises(TypeError):
        LineGeometry(subclassed)
    with pytest.raises(TypeError):
        CircleGeometry(
            circle_coefficients,
            _FractionSubclass(0),
            Fraction(0),
            Fraction(1),
        )
    with pytest.raises(TypeError):
        CircleGeometry(
            circle_coefficients,
            Fraction(0),
            Fraction(0),
            1,  # type: ignore[arg-type]
        )


def test_geometry_constructors_enforce_local_shape_sign_and_direction() -> None:
    with pytest.raises(ValueError):
        LineGeometry(PrimitiveEquationCoefficients(1, 0, 0, 0, -4, 0))
    with pytest.raises(ValueError):
        CircleGeometry(
            PrimitiveEquationCoefficients(1, 0, 1, 0, 0, -1),
            Fraction(0),
            Fraction(0),
            Fraction(0),
        )
    with pytest.raises(ValueError):
        EllipseGeometry(
            PrimitiveEquationCoefficients(4, 0, 9, 0, 0, -36),
            Fraction(0),
            Fraction(0),
            Fraction(9),
            Fraction(4),
            AxisOrientation.VERTICAL,
        )
    with pytest.raises(ValueError):
        HyperbolaGeometry(
            PrimitiveEquationCoefficients(4, 0, 9, 0, 0, -36),
            Fraction(0),
            Fraction(0),
            Fraction(9),
            Fraction(4),
            AxisOrientation.HORIZONTAL,
        )
    with pytest.raises(ValueError):
        ParabolaGeometry(
            PrimitiveEquationCoefficients(1, 0, 0, 1, 0, 0),
            Fraction(0),
            Fraction(0),
            Fraction(1),
            ParabolaOpening.UP,
        )
    with pytest.raises(ValueError):
        ParabolaGeometry(
            PrimitiveEquationCoefficients(1, 0, 0, 0, -4, 0),
            Fraction(0),
            Fraction(0),
            Fraction(1),
            ParabolaOpening.DOWN,
        )


def test_hyperbola_constructor_does_not_recompute_declared_axis() -> None:
    coefficients = PrimitiveEquationCoefficients(4, 0, -9, 0, 0, -36)
    horizontal = HyperbolaGeometry(
        coefficients,
        Fraction(0),
        Fraction(0),
        Fraction(9),
        Fraction(4),
        AxisOrientation.HORIZONTAL,
    )
    vertical = HyperbolaGeometry(
        coefficients,
        Fraction(0),
        Fraction(0),
        Fraction(9),
        Fraction(4),
        AxisOrientation.VERTICAL,
    )
    assert horizontal.transverse_axis is AxisOrientation.HORIZONTAL
    assert vertical.transverse_axis is AxisOrientation.VERTICAL


def test_direct_geometry_construction_does_not_apply_default_limits() -> None:
    huge = Fraction(10**128)
    value = CircleGeometry(
        PrimitiveEquationCoefficients(1, 0, 1, 0, 0, -1),
        huge,
        -huge,
        huge,
    )
    assert value.radius_squared is huge


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ((0, 0, 0, 1, 0, -2), LineGeometry),
        ((0, 0, 0, 1, 1, -1), LineGeometry),
        ((0, 0, 0, 0, 1, 3), LineGeometry),
    ],
)
def test_general_line_matrix(
    values: tuple[int, int, int, int, int, int],
    expected: type[LineGeometry],
) -> None:
    result = classify_equation_geometry(PrimitiveEquationCoefficients(*values))
    assert type(result) is expected
    assert result.coefficients == PrimitiveEquationCoefficients(*values)


@pytest.mark.parametrize(
    "values",
    [
        (0, 1, 0, 0, 0, 0),
        (0, 1, 0, 0, 0, -1),
        (1, 2, 1, 0, 0, 0),
    ],
)
def test_rotation_gate_precedes_degenerate_classification(
    values: tuple[int, int, int, int, int, int],
) -> None:
    _failure(
        PrimitiveEquationCoefficients(*values),
        EquationGeometryFailureKind.ROTATED_CONIC_NOT_SUPPORTED,
    )


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        (
            (1, 0, 1, 0, 0, -25),
            CircleGeometry(
                PrimitiveEquationCoefficients(1, 0, 1, 0, 0, -25),
                Fraction(0),
                Fraction(0),
                Fraction(25),
            ),
        ),
        (
            (1, 0, 1, -4, 2, -4),
            CircleGeometry(
                PrimitiveEquationCoefficients(1, 0, 1, -4, 2, -4),
                Fraction(2),
                Fraction(-1),
                Fraction(9),
            ),
        ),
        (
            (4, 0, 9, 0, 0, -36),
            EllipseGeometry(
                PrimitiveEquationCoefficients(4, 0, 9, 0, 0, -36),
                Fraction(0),
                Fraction(0),
                Fraction(9),
                Fraction(4),
                AxisOrientation.HORIZONTAL,
            ),
        ),
        (
            (9, 0, 4, 0, 0, -36),
            EllipseGeometry(
                PrimitiveEquationCoefficients(9, 0, 4, 0, 0, -36),
                Fraction(0),
                Fraction(0),
                Fraction(4),
                Fraction(9),
                AxisOrientation.VERTICAL,
            ),
        ),
        (
            (4, 0, 9, -8, 36, 4),
            EllipseGeometry(
                PrimitiveEquationCoefficients(4, 0, 9, -8, 36, 4),
                Fraction(1),
                Fraction(-2),
                Fraction(9),
                Fraction(4),
                AxisOrientation.HORIZONTAL,
            ),
        ),
        (
            (4, 0, -9, 0, 0, -36),
            HyperbolaGeometry(
                PrimitiveEquationCoefficients(4, 0, -9, 0, 0, -36),
                Fraction(0),
                Fraction(0),
                Fraction(9),
                Fraction(4),
                AxisOrientation.HORIZONTAL,
            ),
        ),
        (
            (4, 0, -9, 0, 0, 36),
            HyperbolaGeometry(
                PrimitiveEquationCoefficients(4, 0, -9, 0, 0, 36),
                Fraction(0),
                Fraction(0),
                Fraction(4),
                Fraction(9),
                AxisOrientation.VERTICAL,
            ),
        ),
        (
            (4, 0, -9, -8, -36, -68),
            HyperbolaGeometry(
                PrimitiveEquationCoefficients(4, 0, -9, -8, -36, -68),
                Fraction(1),
                Fraction(-2),
                Fraction(9),
                Fraction(4),
                AxisOrientation.HORIZONTAL,
            ),
        ),
    ],
)
def test_center_conic_success_matrix(
    values: tuple[int, int, int, int, int, int],
    expected: EquationGeometryResult,
) -> None:
    assert classify_equation_geometry(PrimitiveEquationCoefficients(*values)) == expected


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("x^2+y^2=0", EquationGeometryFailureKind.DEGENERATE_CONIC),
        ("x^2+y^2+1=0", EquationGeometryFailureKind.CONIC_HAS_NO_REAL_POINTS),
        ("x^2+2*y^2=0", EquationGeometryFailureKind.DEGENERATE_CONIC),
        ("x^2+2*y^2+1=0", EquationGeometryFailureKind.CONIC_HAS_NO_REAL_POINTS),
        ("x^2-y^2=0", EquationGeometryFailureKind.DEGENERATE_CONIC),
    ],
)
def test_center_conic_rejection_matrix(
    text: str,
    kind: EquationGeometryFailureKind,
) -> None:
    _failure(_canonical(text), kind)


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        (
            (1, 0, 0, 0, -4, 0),
            (Fraction(0), Fraction(0), Fraction(1), ParabolaOpening.UP),
        ),
        (
            (1, 0, 0, 0, 4, 0),
            (Fraction(0), Fraction(0), Fraction(-1), ParabolaOpening.DOWN),
        ),
        (
            (0, 0, 1, -4, 0, 0),
            (Fraction(0), Fraction(0), Fraction(1), ParabolaOpening.RIGHT),
        ),
        (
            (0, 0, 1, 4, 0, 0),
            (Fraction(0), Fraction(0), Fraction(-1), ParabolaOpening.LEFT),
        ),
        (
            (1, 0, 0, -4, -8, -4),
            (Fraction(2), Fraction(-1), Fraction(2), ParabolaOpening.UP),
        ),
        (
            (0, 0, 1, 4, 2, -11),
            (Fraction(3), Fraction(-1), Fraction(-1), ParabolaOpening.LEFT),
        ),
    ],
)
def test_parabola_success_matrix(
    values: tuple[int, int, int, int, int, int],
    expected: tuple[Fraction, Fraction, Fraction, ParabolaOpening],
) -> None:
    result = classify_equation_geometry(PrimitiveEquationCoefficients(*values))
    assert isinstance(result, ParabolaGeometry)
    assert (result.vertex_x, result.vertex_y, result.focal_parameter, result.opening) == (
        expected
    )


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("x^2=0", EquationGeometryFailureKind.DEGENERATE_CONIC),
        ("x^2=4", EquationGeometryFailureKind.DEGENERATE_CONIC),
        ("x^2+1=0", EquationGeometryFailureKind.CONIC_HAS_NO_REAL_POINTS),
        ("y^2=0", EquationGeometryFailureKind.DEGENERATE_CONIC),
        ("y^2=4", EquationGeometryFailureKind.DEGENERATE_CONIC),
        ("y^2+1=0", EquationGeometryFailureKind.CONIC_HAS_NO_REAL_POINTS),
    ],
)
def test_single_square_degenerate_and_no_real_matrix(
    text: str,
    kind: EquationGeometryFailureKind,
) -> None:
    _failure(_canonical(text), kind)


@pytest.mark.parametrize(
    ("text", "geometry_type", "properties"),
    [
        ("x=2", LineGeometry, {}),
        (
            "(x+y)^2+(x-y)^2=4",
            CircleGeometry,
            {"radius_squared": Fraction(2)},
        ),
        (
            "(x-1)^2/9+(y+2)^2/4=1",
            EllipseGeometry,
            {
                "center_x": Fraction(1),
                "center_y": Fraction(-2),
                "semi_axis_x_squared": Fraction(9),
                "semi_axis_y_squared": Fraction(4),
            },
        ),
        (
            "4*x^2-9*y^2=36",
            HyperbolaGeometry,
            {"transverse_axis": AxisOrientation.HORIZONTAL},
        ),
        (
            "4*x^2-9*y^2+36=0",
            HyperbolaGeometry,
            {"transverse_axis": AxisOrientation.VERTICAL},
        ),
        (
            "(x-2)^2=8*(y+1)",
            ParabolaGeometry,
            {"vertex_x": Fraction(2), "vertex_y": Fraction(-1)},
        ),
        (
            "(y-1)^2=4*(x+2)",
            ParabolaGeometry,
            {"vertex_x": Fraction(-2), "vertex_y": Fraction(1)},
        ),
    ],
)
def test_real_13b2_to_13c_connection(
    text: str,
    geometry_type: type[EquationGeometryResult],
    properties: dict[str, object],
) -> None:
    result = _geometry(text)
    assert type(result) is geometry_type
    for name, expected in properties.items():
        assert getattr(result, name) == expected


def test_real_rotated_connection_keeps_rotation_priority() -> None:
    _failure(
        _canonical("(x+y)^2=0"),
        EquationGeometryFailureKind.ROTATED_CONIC_NOT_SUPPORTED,
    )


@pytest.mark.parametrize(
    "forms",
    [
        (
            "2*x-y+3=0",
            "0=2*x-y+3",
            "4*x-2*y+6=0",
            "-2*x+y-3=0",
        ),
        (
            "x^2+y^2=25",
            "25=x^2+y^2",
            "4*x^2+4*y^2=100",
        ),
    ],
)
def test_equivalent_inputs_share_canonical_coefficients_and_geometry(
    forms: tuple[str, ...],
) -> None:
    coefficients = tuple(_canonical(form) for form in forms)
    geometries = tuple(classify_equation_geometry(value) for value in coefficients)
    assert all(value == coefficients[0] for value in coefficients)
    assert all(value == geometries[0] for value in geometries)


def test_active_k_gate_precedes_rotation_and_preserves_metadata() -> None:
    limit = DEFAULT_LIMITS.max_equation_canonical_coefficient_digits
    coefficients = PrimitiveEquationCoefficients(1, 10**limit, 0, 0, 0, 0)
    error = _failure(
        coefficients,
        EquationGeometryFailureKind.RESOURCE_LIMIT_EXCEEDED,
    )
    assert error.exact_limit_component is ExactLimitComponent.CANONICAL_INTEGER
    assert error.exact_limit == limit
    assert str(10**limit) not in str(error)
    assert error.__cause__ is None
    assert error.__suppress_context__ is True


def test_geometry_fraction_numerator_limit_and_active_custom_limits() -> None:
    coefficients = PrimitiveEquationCoefficients(
        1,
        0,
        0,
        0,
        -4 * 10**128,
        0,
    )
    error = _failure(
        coefficients,
        EquationGeometryFailureKind.RESOURCE_LIMIT_EXCEEDED,
    )
    assert error.exact_limit_component is ExactLimitComponent.COEFFICIENT_NUMERATOR
    assert error.exact_limit == 128

    wider = replace(
        DEFAULT_LIMITS,
        version="test-wider-equation-geometry",
        max_equation_coefficient_numerator_digits=129,
        max_equation_canonical_coefficient_digits=769,
    )
    result = classify_equation_geometry(coefficients, limits=wider)
    assert isinstance(result, ParabolaGeometry)
    assert result.focal_parameter == Fraction(10**128)


def test_geometry_fraction_denominator_limit_preserves_metadata() -> None:
    coefficients = PrimitiveEquationCoefficients(
        25 * 10**126,
        0,
        0,
        0,
        -1,
        0,
    )
    error = _failure(
        coefficients,
        EquationGeometryFailureKind.RESOURCE_LIMIT_EXCEEDED,
    )
    assert error.exact_limit_component is ExactLimitComponent.COEFFICIENT_DENOMINATOR
    assert error.exact_limit == 128


def test_axis_center_resource_gate_precedes_degenerate_result() -> None:
    small = replace(
        DEFAULT_LIMITS,
        version="test-small-equation-geometry",
        max_rational_numerator_digits=1,
        max_rational_denominator_digits=1,
        max_equation_coefficient_numerator_digits=1,
        max_equation_coefficient_denominator_digits=1,
        max_equation_canonical_coefficient_digits=6,
    )
    coefficients = PrimitiveEquationCoefficients(5, 0, 0, 1, 0, 0)
    error = _failure(
        coefficients,
        EquationGeometryFailureKind.RESOURCE_LIMIT_EXCEEDED,
        limits=small,
    )
    assert error.exact_limit_component is ExactLimitComponent.COEFFICIENT_DENOMINATOR
    assert error.exact_limit == 1


def test_large_k_bounded_coefficients_keep_exact_sign_classification() -> None:
    magnitude = 10**300 + 1
    wide_exact = replace(
        DEFAULT_LIMITS,
        version="test-wide-exact-sign-classification",
        max_equation_coefficient_numerator_digits=400,
        max_equation_coefficient_denominator_digits=400,
        max_equation_canonical_coefficient_digits=2_400,
    )
    coefficients = PrimitiveEquationCoefficients(
        magnitude,
        0,
        -magnitude + 1,
        0,
        0,
        -1,
    )
    result = classify_equation_geometry(coefficients, limits=wide_exact)
    assert isinstance(result, HyperbolaGeometry)
    assert result.transverse_axis is AxisOrientation.HORIZONTAL
    assert result.semi_transverse_squared > 0
    assert result.semi_conjugate_squared > 0


def test_production_module_static_structure_matches_the_frozen_boundary() -> None:
    path = Path(classifier_module.__file__)
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    approved_roots = {
        "__future__",
        "dataclasses",
        "enum",
        "fractions",
        "typing",
        "math_drawing_assistant.config.limits",
        "math_drawing_assistant.engine.exact_rational",
        "math_drawing_assistant.models.plot_specs",
    }
    imports = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert imports <= approved_roots
    assert not any(isinstance(node, (ast.Import, ast.Assert)) for node in ast.walk(tree))

    forbidden_calls = {
        "eval",
        "exec",
        "float",
        "sqrt",
        "hypot",
        "isclose",
        "solve",
        "factor",
        "expand",
        "simplify",
    }
    called_names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert called_names.isdisjoint(forbidden_calls)

    forbidden_names = {
        "Decimal",
        "ErrorCode",
        "ErrorInfo",
        "SourceSpan",
        "RestrictedExpression",
        "canonicalize_equation",
        "parser",
        "tokenizer",
        "equation_polynomial",
        "PlotItemSpec",
        "LineSpec",
        "CircleSpec",
        "EllipseSpec",
        "HyperbolaSpec",
        "ParabolaSpec",
        "RenderPlan",
    }
    referenced_names = {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    }
    assert referenced_names.isdisjoint(forbidden_names)

    loops = [node for node in ast.walk(tree) if isinstance(node, (ast.For, ast.While))]
    assert len(loops) == 1
    loop = loops[0]
    assert isinstance(loop, ast.For)
    assert isinstance(loop.iter, ast.Tuple)
    assert len(loop.iter.elts) == 6


def test_geometry_constructors_do_not_read_limits_or_reclassify() -> None:
    path = Path(classifier_module.__file__)
    tree = ast.parse(path.read_text(encoding="utf-8"))
    geometry_names = {
        "LineGeometry",
        "CircleGeometry",
        "EllipseGeometry",
        "HyperbolaGeometry",
        "ParabolaGeometry",
    }
    classes = {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name in geometry_names
    }
    assert set(classes) == geometry_names
    for node in classes.values():
        names = {child.id for child in ast.walk(node) if isinstance(child, ast.Name)}
        assert "DEFAULT_LIMITS" not in names
        assert "ensure_fraction_within_limits" not in names
        assert "ensure_canonical_integer_within_limit" not in names
        assert "classify_equation_geometry" not in names


def test_hyperbola_local_sign_check_uses_comparisons_not_multiplication() -> None:
    path = Path(classifier_module.__file__)
    tree = ast.parse(path.read_text(encoding="utf-8"))
    hyperbola = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "HyperbolaGeometry"
    )
    assert not any(isinstance(node, ast.Mult) for node in ast.walk(hyperbola))
