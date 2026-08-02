"""Stage 13A-2 tests for canonical equation values and typed plot specs."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, replace
from decimal import Decimal
from fractions import Fraction

import pytest

from math_drawing_assistant.models.errors import SourceSpan
from math_drawing_assistant.models.plot_specs import (
    AxisOrientation,
    CircleSpec,
    EllipseSpec,
    EquationProvenance,
    HyperbolaSpec,
    LineSpec,
    ParabolaOpening,
    ParabolaSpec,
    PlotItemSpec,
    PlotSceneSpec,
    PrimitiveEquationCoefficients,
)
from math_drawing_assistant.models.state import PlotKind


def _provenance() -> EquationProvenance:
    return EquationProvenance(
        normalized_input="x^2+y^2=1",
        normalized_span=SourceSpan(0, 9),
        source_span=SourceSpan(4, 15),
        limits_version="limits-test",
    )


def _line(item_id: str = "line") -> LineSpec:
    return LineSpec(
        item_id=item_id,
        coefficients=PrimitiveEquationCoefficients(0, 0, 0, 2, -1, 3),
        provenance=_provenance(),
    )


def _circle(item_id: str = "circle") -> CircleSpec:
    return CircleSpec(
        item_id=item_id,
        coefficients=PrimitiveEquationCoefficients(1, 0, 1, 0, 0, -1),
        provenance=_provenance(),
        center_x=Fraction(0),
        center_y=Fraction(0),
        radius_squared=Fraction(1),
    )


def _ellipse(item_id: str = "ellipse") -> EllipseSpec:
    return EllipseSpec(
        item_id=item_id,
        coefficients=PrimitiveEquationCoefficients(4, 0, 9, 0, 0, -36),
        provenance=_provenance(),
        center_x=Fraction(0),
        center_y=Fraction(0),
        semi_axis_x_squared=Fraction(9),
        semi_axis_y_squared=Fraction(4),
        major_axis=AxisOrientation.HORIZONTAL,
    )


def _hyperbola(item_id: str = "hyperbola") -> HyperbolaSpec:
    return HyperbolaSpec(
        item_id=item_id,
        coefficients=PrimitiveEquationCoefficients(4, 0, -9, 0, 0, -36),
        provenance=_provenance(),
        center_x=Fraction(0),
        center_y=Fraction(0),
        semi_transverse_squared=Fraction(9),
        semi_conjugate_squared=Fraction(4),
        transverse_axis=AxisOrientation.HORIZONTAL,
    )


def _parabola(item_id: str = "parabola") -> ParabolaSpec:
    return ParabolaSpec(
        item_id=item_id,
        coefficients=PrimitiveEquationCoefficients(1, 0, 0, 0, -4, 0),
        provenance=_provenance(),
        vertex_x=Fraction(0),
        vertex_y=Fraction(0),
        focal_parameter=Fraction(1),
        opening=ParabolaOpening.UP,
    )


@pytest.mark.parametrize(
    "values",
    [
        (0, 0, 0, 1, 0, -2),
        (0, 0, 0, 1, 1, -1),
        (0, 0, 0, 2, -1, 3),
        (1, 0, 1, 0, 0, -25),
        (4, 0, 9, 0, 0, -36),
        (4, 0, -9, 0, 0, -36),
        (4, 0, -9, 0, 0, 36),
        (1, 0, 0, 0, -4, 0),
    ],
)
def test_primitive_coefficients_accept_canonical_values(
    values: tuple[int, int, int, int, int, int],
) -> None:
    coefficients = PrimitiveEquationCoefficients(*values)

    assert tuple(getattr(coefficients, name) for name in "abcdef") == values
    assert [field.name for field in fields(coefficients)] == list("abcdef")
    assert coefficients == PrimitiveEquationCoefficients(*values)
    assert hash(coefficients) == hash(PrimitiveEquationCoefficients(*values))
    assert "__dict__" not in type(coefficients).__dict__


@pytest.mark.parametrize(
    "values",
    [
        (0, 0, 0, 0, 0, 0),
        (0, 0, 0, -1, 0, 2),
        (-1, 0, -1, 0, 0, 25),
        (0, 0, 0, 2, 0, -4),
        (2, 0, 0, 4, 0, 6),
    ],
)
def test_primitive_coefficients_reject_noncanonical_values(
    values: tuple[int, int, int, int, int, int],
) -> None:
    with pytest.raises(ValueError):
        PrimitiveEquationCoefficients(*values)


@pytest.mark.parametrize(
    ("index", "bad_value"),
    [
        (0, True),
        (1, False),
        (2, 1.0),
        (3, Fraction(1)),
        (4, Decimal("1")),
        (5, "1"),
        (0, None),
    ],
)
def test_primitive_coefficients_require_exact_ints(
    index: int,
    bad_value: object,
) -> None:
    values: list[object] = [1, 0, 0, 0, -4, 0]
    values[index] = bad_value

    with pytest.raises(TypeError):
        PrimitiveEquationCoefficients(*values)  # type: ignore[arg-type]


def test_primitive_coefficients_are_frozen_slots_and_do_not_normalize() -> None:
    coefficients = PrimitiveEquationCoefficients(0, 0, 0, 2, -1, 3)

    assert hash(coefficients)
    assert not hasattr(coefficients, "__dict__")
    with pytest.raises(FrozenInstanceError):
        coefficients.d = 1  # type: ignore[misc]
    with pytest.raises(ValueError):
        PrimitiveEquationCoefficients(0, 0, 0, 4, -2, 6)
    with pytest.raises(ValueError):
        PrimitiveEquationCoefficients(0, 0, 0, -2, 1, -3)


def test_equation_provenance_preserves_exact_values() -> None:
    provenance = EquationProvenance(
        normalized_input=" x=2 ",
        normalized_span=SourceSpan(1, 4),
        source_span=SourceSpan(10, 13),
        limits_version=" version-with-spaces ",
    )

    assert provenance.normalized_input == " x=2 "
    assert provenance.limits_version == " version-with-spaces "
    assert hash(provenance)
    assert not hasattr(provenance, "__dict__")
    with pytest.raises(FrozenInstanceError):
        provenance.limits_version = "other"  # type: ignore[misc]
    for forbidden in (
        "raw_input",
        "original_input",
        "source_map",
        "tokens",
        "ast",
        "metrics",
        "receipt",
    ):
        assert not hasattr(provenance, forbidden)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"normalized_input": ""},
        {"limits_version": ""},
        {"limits_version": " \t"},
        {"normalized_span": SourceSpan(2, 2)},
        {"source_span": SourceSpan(3, 3)},
        {"normalized_span": SourceSpan(0, 20)},
    ],
)
def test_equation_provenance_rejects_invalid_values(kwargs: dict[str, object]) -> None:
    values: dict[str, object] = {
        "normalized_input": "x=2",
        "normalized_span": SourceSpan(0, 3),
        "source_span": SourceSpan(5, 8),
        "limits_version": "v1",
    }
    values.update(kwargs)

    with pytest.raises(ValueError):
        EquationProvenance(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"normalized_input": 1},
        {"normalized_span": (0, 3)},
        {"source_span": (0, 3)},
        {"limits_version": 1},
    ],
)
def test_equation_provenance_rejects_invalid_types(kwargs: dict[str, object]) -> None:
    values: dict[str, object] = {
        "normalized_input": "x=2",
        "normalized_span": SourceSpan(0, 3),
        "source_span": SourceSpan(5, 8),
        "limits_version": "v1",
    }
    values.update(kwargs)

    with pytest.raises(TypeError):
        EquationProvenance(**values)  # type: ignore[arg-type]


def test_direction_enums_have_only_the_frozen_members() -> None:
    assert [(member.name, member.value) for member in AxisOrientation] == [
        ("HORIZONTAL", "horizontal"),
        ("VERTICAL", "vertical"),
    ]
    assert [(member.name, member.value) for member in ParabolaOpening] == [
        ("UP", "up"),
        ("DOWN", "down"),
        ("LEFT", "left"),
        ("RIGHT", "right"),
    ]
    for enum_type in (AxisOrientation, ParabolaOpening):
        for forbidden in ("AUTO", "UNKNOWN", "DIAGONAL", "ROTATED", "NONE"):
            assert not hasattr(enum_type, forbidden)


@pytest.mark.parametrize(
    "coefficients",
    [
        PrimitiveEquationCoefficients(0, 0, 0, 2, -1, 3),
        PrimitiveEquationCoefficients(0, 0, 0, 1, 0, -2),
        PrimitiveEquationCoefficients(0, 0, 0, 0, 1, 3),
    ],
)
def test_line_spec_supports_general_vertical_and_horizontal_lines(
    coefficients: PrimitiveEquationCoefficients,
) -> None:
    spec = LineSpec("line", coefficients, _provenance())

    assert spec.plot_kind is PlotKind.LINE_EQUATION
    assert (spec.d, spec.e, spec.f) == (
        coefficients.d,
        coefficients.e,
        coefficients.f,
    )
    assert {field.name for field in fields(spec)} == {
        "item_id",
        "coefficients",
        "provenance",
    }


@pytest.mark.parametrize(
    "coefficients",
    [
        PrimitiveEquationCoefficients(1, 0, 0, 0, -1, 0),
        PrimitiveEquationCoefficients(0, 1, 0, 0, 0, 1),
        PrimitiveEquationCoefficients(0, 0, 0, 0, 0, 1),
    ],
)
def test_line_spec_rejects_non_line_structure(
    coefficients: PrimitiveEquationCoefficients,
) -> None:
    with pytest.raises(ValueError):
        LineSpec("line", coefficients, _provenance())


def test_circle_spec_accepts_origin_and_translated_exact_geometry() -> None:
    origin = _circle()
    translated = CircleSpec(
        "translated",
        PrimitiveEquationCoefficients(1, 0, 1, -4, 2, -4),
        _provenance(),
        Fraction(2),
        Fraction(-1),
        Fraction(9),
    )

    assert origin.plot_kind is PlotKind.CONIC_EQUATION
    assert translated.center_x == Fraction(2)
    assert translated.center_y == Fraction(-1)
    assert translated.radius_squared == Fraction(9)
    assert type(origin) is not EllipseSpec
    assert not hasattr(origin, "is_circle")
    assert not hasattr(origin, "radius")


@pytest.mark.parametrize(
    "coefficients",
    [
        PrimitiveEquationCoefficients(1, 1, 1, 0, 0, -1),
        PrimitiveEquationCoefficients(1, 0, 2, 0, 0, -1),
        PrimitiveEquationCoefficients(0, 0, 1, 0, 0, -1),
    ],
)
def test_circle_spec_rejects_invalid_coefficient_shape(
    coefficients: PrimitiveEquationCoefficients,
) -> None:
    with pytest.raises(ValueError):
        CircleSpec(
            "circle",
            coefficients,
            _provenance(),
            Fraction(0),
            Fraction(0),
            Fraction(1),
        )


@pytest.mark.parametrize("radius_squared", [Fraction(0), Fraction(-1)])
def test_circle_spec_rejects_nonpositive_radius_squared(
    radius_squared: Fraction,
) -> None:
    with pytest.raises(ValueError):
        replace(_circle(), radius_squared=radius_squared)


def test_ellipse_spec_accepts_both_major_axes() -> None:
    horizontal = _ellipse()
    vertical = EllipseSpec(
        "vertical",
        PrimitiveEquationCoefficients(9, 0, 4, 0, 0, -36),
        _provenance(),
        Fraction(1, 2),
        Fraction(-3, 2),
        Fraction(4),
        Fraction(9),
        AxisOrientation.VERTICAL,
    )

    assert horizontal.major_axis is AxisOrientation.HORIZONTAL
    assert vertical.major_axis is AxisOrientation.VERTICAL


@pytest.mark.parametrize(
    ("semi_x", "semi_y", "axis"),
    [
        (Fraction(0), Fraction(4), AxisOrientation.VERTICAL),
        (Fraction(9), Fraction(0), AxisOrientation.HORIZONTAL),
        (Fraction(4), Fraction(4), AxisOrientation.HORIZONTAL),
        (Fraction(9), Fraction(4), AxisOrientation.VERTICAL),
    ],
)
def test_ellipse_spec_rejects_invalid_axis_geometry(
    semi_x: Fraction,
    semi_y: Fraction,
    axis: AxisOrientation,
) -> None:
    with pytest.raises(ValueError):
        EllipseSpec(
            "ellipse",
            PrimitiveEquationCoefficients(4, 0, 9, 0, 0, -36),
            _provenance(),
            Fraction(0),
            Fraction(0),
            semi_x,
            semi_y,
            axis,
        )


@pytest.mark.parametrize(
    "coefficients",
    [
        PrimitiveEquationCoefficients(1, 1, 2, 0, 0, -1),
        PrimitiveEquationCoefficients(0, 0, 1, 1, 0, -1),
        PrimitiveEquationCoefficients(1, 0, 0, 0, 1, -1),
        PrimitiveEquationCoefficients(1, 0, 1, 0, 0, -1),
    ],
)
def test_ellipse_spec_rejects_invalid_coefficient_shape(
    coefficients: PrimitiveEquationCoefficients,
) -> None:
    with pytest.raises(ValueError):
        replace(_ellipse(), coefficients=coefficients)


def test_hyperbola_spec_accepts_either_declared_transverse_axis() -> None:
    horizontal = _hyperbola()
    vertical = HyperbolaSpec(
        "vertical",
        horizontal.coefficients,
        _provenance(),
        Fraction(1),
        Fraction(-1),
        Fraction(4),
        Fraction(9),
        AxisOrientation.VERTICAL,
    )

    assert horizontal.transverse_axis is AxisOrientation.HORIZONTAL
    assert vertical.transverse_axis is AxisOrientation.VERTICAL


@pytest.mark.parametrize(
    "coefficients",
    [
        PrimitiveEquationCoefficients(1, 1, -1, 0, 0, -1),
        PrimitiveEquationCoefficients(0, 0, 1, 1, 0, -1),
        PrimitiveEquationCoefficients(1, 0, 0, 0, 1, -1),
        PrimitiveEquationCoefficients(1, 0, 1, 0, 0, -1),
    ],
)
def test_hyperbola_spec_rejects_invalid_coefficient_shape(
    coefficients: PrimitiveEquationCoefficients,
) -> None:
    with pytest.raises(ValueError):
        HyperbolaSpec(
            "hyperbola",
            coefficients,
            _provenance(),
            Fraction(0),
            Fraction(0),
            Fraction(1),
            Fraction(1),
            AxisOrientation.HORIZONTAL,
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"semi_transverse_squared": Fraction(0)},
        {"semi_transverse_squared": Fraction(-1)},
        {"semi_conjugate_squared": Fraction(0)},
        {"semi_conjugate_squared": Fraction(-1)},
    ],
)
def test_hyperbola_spec_rejects_nonpositive_axis_squares(
    changes: dict[str, Fraction],
) -> None:
    with pytest.raises(ValueError):
        replace(_hyperbola(), **changes)


@pytest.mark.parametrize(
    ("coefficients", "focal", "opening"),
    [
        (PrimitiveEquationCoefficients(1, 0, 0, 0, -4, 0), Fraction(1), ParabolaOpening.UP),
        (PrimitiveEquationCoefficients(1, 0, 0, 0, 4, 0), Fraction(-1), ParabolaOpening.DOWN),
        (PrimitiveEquationCoefficients(0, 0, 1, -4, 0, 0), Fraction(1), ParabolaOpening.RIGHT),
        (PrimitiveEquationCoefficients(0, 0, 1, 4, 0, 0), Fraction(-1), ParabolaOpening.LEFT),
    ],
)
def test_parabola_spec_accepts_all_opening_directions(
    coefficients: PrimitiveEquationCoefficients,
    focal: Fraction,
    opening: ParabolaOpening,
) -> None:
    spec = ParabolaSpec(
        "parabola",
        coefficients,
        _provenance(),
        Fraction(3, 2),
        Fraction(-5, 2),
        focal,
        opening,
    )

    assert spec.opening is opening


@pytest.mark.parametrize(
    ("coefficients", "focal", "opening"),
    [
        (PrimitiveEquationCoefficients(0, 1, 0, 1, 0, 0), Fraction(1), ParabolaOpening.RIGHT),
        (PrimitiveEquationCoefficients(0, 0, 0, 1, 0, 0), Fraction(1), ParabolaOpening.RIGHT),
        (PrimitiveEquationCoefficients(1, 0, 1, 0, 0, -1), Fraction(1), ParabolaOpening.UP),
        (PrimitiveEquationCoefficients(1, 0, 0, 0, -4, 0), Fraction(0), ParabolaOpening.UP),
        (PrimitiveEquationCoefficients(1, 0, 0, 0, -4, 0), Fraction(1), ParabolaOpening.LEFT),
        (PrimitiveEquationCoefficients(0, 0, 1, -4, 0, 0), Fraction(1), ParabolaOpening.UP),
        (PrimitiveEquationCoefficients(1, 0, 0, 0, 4, 0), Fraction(-1), ParabolaOpening.UP),
    ],
)
def test_parabola_spec_rejects_invalid_local_geometry(
    coefficients: PrimitiveEquationCoefficients,
    focal: Fraction,
    opening: ParabolaOpening,
) -> None:
    with pytest.raises(ValueError):
        ParabolaSpec(
            "parabola",
            coefficients,
            _provenance(),
            Fraction(0),
            Fraction(0),
            focal,
            opening,
        )


@pytest.mark.parametrize(
    "factory",
    [_line, _circle, _ellipse, _hyperbola, _parabola],
)
def test_all_equation_specs_are_frozen_slotted_hashable_protocol_items(factory: object) -> None:
    spec = factory()  # type: ignore[operator]

    assert spec.__dataclass_params__.frozen is True
    assert not hasattr(spec, "__dict__")
    assert hash(spec)
    assert isinstance(spec, PlotItemSpec)
    assert isinstance(type(spec).plot_kind, property)
    with pytest.raises(FrozenInstanceError):
        spec.item_id = "other"  # type: ignore[misc]
    with pytest.raises((AttributeError, FrozenInstanceError, TypeError)):
        spec.plot_kind = PlotKind.AUTO  # type: ignore[misc]
    with pytest.raises(TypeError):
        type(spec)(**{  # type: ignore[call-arg]
            **{field.name: getattr(spec, field.name) for field in fields(spec)},
            "plot_kind": spec.plot_kind,
        })


@pytest.mark.parametrize("factory", [_line, _circle, _ellipse, _hyperbola, _parabola])
def test_all_equation_specs_reject_blank_item_ids(factory: object) -> None:
    with pytest.raises(ValueError):
        factory(" \t")  # type: ignore[operator]


def test_all_specs_reject_wrong_common_and_geometry_types() -> None:
    with pytest.raises(TypeError):
        LineSpec("line", (0, 0, 0, 1, 0, 0), _provenance())  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        LineSpec("line", PrimitiveEquationCoefficients(0, 0, 0, 1, 0, 0), object())  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        CircleSpec("circle", _circle().coefficients, _provenance(), 0, Fraction(0), Fraction(1))  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        CircleSpec("circle", _circle().coefficients, _provenance(), Fraction(0), Fraction(0), 1)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        EllipseSpec("ellipse", _ellipse().coefficients, _provenance(), Fraction(0), Fraction(0), Fraction(9), Fraction(4), "horizontal")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        HyperbolaSpec("hyperbola", _hyperbola().coefficients, _provenance(), Fraction(0), Fraction(0), Fraction(1), Fraction(1), "horizontal")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        ParabolaSpec("parabola", _parabola().coefficients, _provenance(), Fraction(0), Fraction(0), 1, ParabolaOpening.UP)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        ParabolaSpec("parabola", _parabola().coefficients, _provenance(), Fraction(0), Fraction(0), Fraction(1), "up")  # type: ignore[arg-type]

    exact_geometry_fields = (
        (_circle(), ("center_x", "center_y", "radius_squared")),
        (
            _ellipse(),
            (
                "center_x",
                "center_y",
                "semi_axis_x_squared",
                "semi_axis_y_squared",
            ),
        ),
        (
            _hyperbola(),
            (
                "center_x",
                "center_y",
                "semi_transverse_squared",
                "semi_conjugate_squared",
            ),
        ),
        (_parabola(), ("vertex_x", "vertex_y", "focal_parameter")),
    )
    for spec, field_names in exact_geometry_fields:
        for field_name in field_names:
            with pytest.raises(TypeError):
                replace(spec, **{field_name: 1})


def test_plot_scene_accepts_mixed_equation_specs_without_model_changes() -> None:
    items = (_line(), _circle(), _ellipse(), _hyperbola(), _parabola())
    scene = PlotSceneSpec(items=items)

    assert scene.items is items
    assert tuple(item.item_id for item in scene.items) == (
        "line",
        "circle",
        "ellipse",
        "hyperbola",
        "parabola",
    )
    with pytest.raises(ValueError):
        PlotSceneSpec(items=())
    with pytest.raises(ValueError):
        PlotSceneSpec(items=(_line("same"), _circle("same")))


def test_equation_specs_exclude_forbidden_structures() -> None:
    module = __import__(
        "math_drawing_assistant.models.plot_specs",
        fromlist=["plot_specs"],
    )
    for forbidden_type in (
        "ConicSpec",
        "BaseConicSpec",
        "ImplicitConicSpec",
        "EquationSpecBase",
    ):
        assert not hasattr(module, forbidden_type)

    forbidden_fields = {
        "x_min",
        "x_max",
        "y_min",
        "y_max",
        "suggested_range",
        "auto_viewport",
        "resolved_viewport",
        "visible_interval",
        "parameter_interval",
        "sample_points",
        "samples",
        "branches",
        "segments",
        "sampling_strategy",
        "sampling_policy",
        "render_plan",
        "slope",
        "intercept",
        "asymptotes",
        "focus",
        "directrix",
        "eccentricity",
        "rotation_angle",
    }
    for model in (LineSpec, CircleSpec, EllipseSpec, HyperbolaSpec, ParabolaSpec):
        names = {field.name for field in fields(model)}
        assert names.isdisjoint(forbidden_fields)
    assert {field.name for field in fields(LineSpec)}.isdisjoint({"d", "e", "f"})
