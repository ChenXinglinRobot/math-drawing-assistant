"""Stage 13D-3 tests for the sealed equation-to-Spec projection."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, fields, replace
from fractions import Fraction
from pathlib import Path

import pytest

import math_drawing_assistant.engine.equation_classifier as classifier_module
import math_drawing_assistant.engine.equation_polynomial as polynomial_module
import math_drawing_assistant.engine.equation_validator as validator_module
import math_drawing_assistant.engine.parser as parser_module
from math_drawing_assistant.config.limits import DEFAULT_LIMITS
from math_drawing_assistant.engine.equation_classifier import (
    CircleGeometry,
    EllipseGeometry,
    HyperbolaGeometry,
    LineGeometry,
    ParabolaGeometry,
    classify_equation_geometry,
)
from math_drawing_assistant.engine.equation_polynomial import canonicalize_equation
from math_drawing_assistant.engine.equation_spec_builder import (
    EquationSpecBuilderError,
    build_equation_spec,
)
from math_drawing_assistant.engine.equation_splitter import split_equation
from math_drawing_assistant.engine.equation_validator import (
    EquationValidationError,
    ValidatedEquationInput,
    _validate_validated_equation_input,
    validate_equation_candidate,
)
from math_drawing_assistant.engine.normalizer import normalize_input
from math_drawing_assistant.engine.parser import parse_input
from math_drawing_assistant.engine.plot_classifier import (
    EquationCandidate,
    classify_plot_route,
)
from math_drawing_assistant.engine.tokenizer import tokenize
from math_drawing_assistant.models.errors import ErrorInfo, SourceSpan
from math_drawing_assistant.models.plot_specs import (
    AxisOrientation,
    CircleSpec,
    EllipseSpec,
    HyperbolaSpec,
    LineSpec,
    ParabolaOpening,
    ParabolaSpec,
    PrimitiveEquationCoefficients,
)
from math_drawing_assistant.models.state import PlotKind


def _analysis_parts(
    text: str,
) -> tuple[
    ValidatedEquationInput,
    PrimitiveEquationCoefficients,
    LineGeometry
    | CircleGeometry
    | EllipseGeometry
    | HyperbolaGeometry
    | ParabolaGeometry,
]:
    normalized = normalize_input(text)
    assert not isinstance(normalized, ErrorInfo)
    tokens = tokenize(normalized)
    assert not isinstance(tokens, ErrorInfo)
    split = split_equation(tokens)
    assert not isinstance(split, ErrorInfo)
    parsed = parse_input(split)
    assert not isinstance(parsed, ErrorInfo)
    candidate = classify_plot_route(parsed)
    assert type(candidate) is EquationCandidate
    validated = validate_equation_candidate(candidate, normalized)
    validated = _validate_validated_equation_input(
        validated,
        limits=DEFAULT_LIMITS,
    )
    coefficients = canonicalize_equation(
        validated.parsed_input.left,
        validated.parsed_input.right,
    )
    geometry = classify_equation_geometry(coefficients)
    return validated, coefficients, geometry


@pytest.mark.parametrize(
    ("text", "expected_type", "expected_coefficients", "expected_geometry"),
    (
        (
            "x+y=1",
            LineSpec,
            (0, 0, 0, 1, 1, -1),
            (),
        ),
        (
            "x^2+y^2=25",
            CircleSpec,
            (1, 0, 1, 0, 0, -25),
            (Fraction(0), Fraction(0), Fraction(25)),
        ),
        (
            "x^2/9+y^2/4=1",
            EllipseSpec,
            (4, 0, 9, 0, 0, -36),
            (
                Fraction(0),
                Fraction(0),
                Fraction(9),
                Fraction(4),
                AxisOrientation.HORIZONTAL,
            ),
        ),
        (
            "x^2/9-y^2/4=1",
            HyperbolaSpec,
            (4, 0, -9, 0, 0, -36),
            (
                Fraction(0),
                Fraction(0),
                Fraction(9),
                Fraction(4),
                AxisOrientation.HORIZONTAL,
            ),
        ),
        (
            "x^2=4*y",
            ParabolaSpec,
            (1, 0, 0, 0, -4, 0),
            (
                Fraction(0),
                Fraction(0),
                Fraction(1),
                ParabolaOpening.UP,
            ),
        ),
    ),
)
def test_five_geometry_types_map_field_for_field_to_five_specs(
    text: str,
    expected_type: type[object],
    expected_coefficients: tuple[int, int, int, int, int, int],
    expected_geometry: tuple[object, ...],
) -> None:
    validated, coefficients, geometry = _analysis_parts(text)

    spec = build_equation_spec(
        "equation-item",
        validated,
        coefficients,
        geometry,
    )

    assert type(spec) is expected_type
    assert spec.item_id == "equation-item"
    assert spec.provenance is validated.provenance
    assert spec.coefficients is coefficients
    assert tuple(getattr(spec.coefficients, name) for name in "abcdef") == (
        expected_coefficients
    )
    if type(spec) is LineSpec:
        assert expected_geometry == ()
        assert spec.plot_kind is PlotKind.LINE_EQUATION
    elif type(spec) is CircleSpec:
        assert (
            spec.center_x,
            spec.center_y,
            spec.radius_squared,
        ) == expected_geometry
        assert spec.plot_kind is PlotKind.CONIC_EQUATION
    elif type(spec) is EllipseSpec:
        assert (
            spec.center_x,
            spec.center_y,
            spec.semi_axis_x_squared,
            spec.semi_axis_y_squared,
            spec.major_axis,
        ) == expected_geometry
        assert spec.plot_kind is PlotKind.CONIC_EQUATION
    elif type(spec) is HyperbolaSpec:
        assert (
            spec.center_x,
            spec.center_y,
            spec.semi_transverse_squared,
            spec.semi_conjugate_squared,
            spec.transverse_axis,
        ) == expected_geometry
        assert spec.plot_kind is PlotKind.CONIC_EQUATION
    elif type(spec) is ParabolaSpec:
        assert (
            spec.vertex_x,
            spec.vertex_y,
            spec.focal_parameter,
            spec.opening,
        ) == expected_geometry
        assert spec.plot_kind is PlotKind.CONIC_EQUATION
    else:
        raise AssertionError("unexpected equation Spec type")


@pytest.mark.parametrize("item_id", ["", "   ", 1, None])
def test_builder_requires_a_validated_item_identity(item_id: object) -> None:
    validated, coefficients, geometry = _analysis_parts("x=2")

    with pytest.raises(EquationSpecBuilderError):
        build_equation_spec(
            item_id,  # type: ignore[arg-type]
            validated,
            coefficients,
            geometry,
        )


def test_forged_receipt_is_rejected() -> None:
    validated, coefficients, geometry = _analysis_parts("x=2")
    forged = object.__new__(ValidatedEquationInput)
    object.__setattr__(forged, "parsed_input", validated.parsed_input)
    object.__setattr__(forged, "provenance", validated.provenance)
    object.__setattr__(forged, "free_variables", validated.free_variables)

    with pytest.raises(TypeError):
        build_equation_spec("item", forged, coefficients, geometry)


def test_stolen_receipt_contract_is_rejected() -> None:
    first, _, _ = _analysis_parts("x=2")
    second, coefficients, geometry = _analysis_parts("y+1=3")
    object.__setattr__(second, "_contract", first._contract)

    with pytest.raises(EquationValidationError):
        build_equation_spec("item", second, coefficients, geometry)


def test_tampered_receipt_is_rejected() -> None:
    validated, coefficients, geometry = _analysis_parts("x=2")
    object.__setattr__(validated, "free_variables", ("y",))

    with pytest.raises(EquationValidationError):
        build_equation_spec("item", validated, coefficients, geometry)


def test_receipt_from_incompatible_limits_is_rejected() -> None:
    validated, coefficients, geometry = _analysis_parts("x=2")
    incompatible = replace(DEFAULT_LIMITS, version="limits-13d3-incompatible")

    with pytest.raises(EquationValidationError):
        build_equation_spec(
            "item",
            validated,
            coefficients,
            geometry,
            limits=incompatible,
        )


def test_geometry_and_coefficients_must_share_formal_result_identity() -> None:
    validated, coefficients, _ = _analysis_parts("x^2+y^2=25")
    equal_but_distinct = PrimitiveEquationCoefficients(1, 0, 1, 0, 0, -25)
    geometry = CircleGeometry(
        equal_but_distinct,
        Fraction(0),
        Fraction(0),
        Fraction(25),
    )

    with pytest.raises(EquationSpecBuilderError):
        build_equation_spec("item", validated, coefficients, geometry)


def test_unknown_geometry_type_is_rejected() -> None:
    validated, coefficients, _ = _analysis_parts("x=2")

    with pytest.raises(EquationSpecBuilderError):
        build_equation_spec(
            "item",
            validated,
            coefficients,
            object(),  # type: ignore[arg-type]
        )


def test_tampered_exact_geometry_is_rejected_without_recomputation() -> None:
    validated, coefficients, geometry = _analysis_parts("x^2+y^2=25")
    assert type(geometry) is CircleGeometry
    object.__setattr__(geometry, "radius_squared", Fraction(0))

    with pytest.raises(EquationSpecBuilderError):
        build_equation_spec("item", validated, coefficients, geometry)


def test_built_specs_are_frozen_slotted_and_keep_only_exact_values() -> None:
    for text in (
        "x=2",
        "x^2+y^2=25",
        "x^2/9+y^2/4=1",
        "x^2/9-y^2/4=1",
        "x^2=4*y",
    ):
        validated, coefficients, geometry = _analysis_parts(text)
        spec = build_equation_spec("item", validated, coefficients, geometry)

        assert not hasattr(spec, "__dict__")
        assert all(field.name != "geometry" for field in fields(spec))
        with pytest.raises(FrozenInstanceError):
            spec.item_id = "changed"  # type: ignore[misc]
        for field in fields(spec):
            value = getattr(spec, field.name)
            assert not isinstance(value, (list, dict, set, float))
        for field_name in (
            "center_x",
            "center_y",
            "radius_squared",
            "semi_axis_x_squared",
            "semi_axis_y_squared",
            "semi_transverse_squared",
            "semi_conjugate_squared",
            "vertex_x",
            "vertex_y",
            "focal_parameter",
        ):
            if hasattr(spec, field_name):
                assert type(getattr(spec, field_name)) is Fraction


def test_builder_receipt_check_adds_no_parser_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    validated, coefficients, geometry = _analysis_parts("x=2")

    def forbidden(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise AssertionError("builder must not replay or recompute equation analysis")

    monkeypatch.setattr(validator_module, "tokenize", forbidden)
    monkeypatch.setattr(validator_module, "split_equation", forbidden)
    monkeypatch.setattr(validator_module, "parse_input", forbidden)
    monkeypatch.setattr(parser_module, "parse_input", forbidden)
    monkeypatch.setattr(polynomial_module, "canonicalize_equation", forbidden)
    monkeypatch.setattr(classifier_module, "classify_equation_geometry", forbidden)

    result = build_equation_spec("item", validated, coefficients, geometry)

    assert type(result) is LineSpec


def test_builder_source_has_no_parser_math_or_forbidden_dependencies() -> None:
    path = (
        Path(__file__).parents[2]
        / "math_drawing_assistant"
        / "engine"
        / "equation_spec_builder.py"
    )
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    called_names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }

    assert called_names.isdisjoint(
        {
            "normalize_input",
            "tokenize",
            "split_equation",
            "parse_input",
            "canonicalize_equation",
            "classify_equation_geometry",
        },
    )
    for forbidden in (
        "sympy",
        "numpy",
        "PySide",
        "Qt",
        "float(",
        "eval(",
        "exec(",
        "compile(",
        "_replay_parser",
    ):
        assert forbidden not in source
