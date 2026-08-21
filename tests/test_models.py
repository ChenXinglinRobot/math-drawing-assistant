"""Focused stage-2 tests for immutable cross-component model contracts."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, dataclass
from math import inf, nan

import pytest

from math_drawing_assistant.models import (
    AspectRequest,
    ConcretePlotType,
    ErrorInfo,
    InputSource,
    PlotItemRequest,
    PlotItemDiagnostics,
    PlotItemResult,
    PlotKind,
    PlotSceneRequest,
    PlotSceneResult,
    PlotSceneSpec,
    RenderPlan,
    ResolvedAspect,
    ResolvedViewport,
    TaskPhase,
    ViewportMode,
    ViewportRequest,
    ViewportSource,
)


@dataclass(frozen=True, slots=True)
class _ExampleItemSpec:
    item_id: str
    plot_kind: PlotKind


def _item(item_id: str = "item-1") -> PlotItemRequest:
    return PlotItemRequest(
        item_id=item_id,
        input_text="y=x",
        input_source=InputSource.MANUAL,
        requested_plot_kind=PlotKind.AUTO,
        display_order=0,
    )


def _viewport() -> ViewportRequest:
    return ViewportRequest(
        mode=ViewportMode.AUTO,
        aspect_request=AspectRequest.AUTO,
    )


def _resolved_viewport() -> ResolvedViewport:
    return ResolvedViewport(
        x_min=-5,
        x_max=5,
        y_min=-4,
        y_max=4,
        aspect=ResolvedAspect.EQUAL,
        source=ViewportSource.MANUAL,
    )


def _scene_request(
    items: tuple[PlotItemRequest, ...] | list[PlotItemRequest] | None = None,
) -> PlotSceneRequest:
    return PlotSceneRequest(
        request_id=1,
        scene_revision=0,
        items=(_item(),) if items is None else items,
        viewport=_viewport(),
        image_width=800,
        image_height=600,
        dpi=96,
        show_grid=True,
        show_legend=True,
    )


def test_models_are_frozen_and_collection_snapshots_are_tuples() -> None:
    item_list = [_item()]
    request = _scene_request(item_list)
    item_list.append(_item("item-2"))

    spec_list = [_ExampleItemSpec("item-1", PlotKind.EXPLICIT_FUNCTION)]
    scene_spec = PlotSceneSpec(spec_list)
    spec_list.append(_ExampleItemSpec("item-2", PlotKind.LINE_EQUATION))

    warning_list = ["viewport clipped"]
    result = PlotSceneResult(
        request_id=1,
        scene_revision=0,
        success=True,
        png_bytes=b"png",
        warnings=warning_list,
    )
    warning_list.append("later mutation")

    plan = RenderPlan(
        scene_spec=scene_spec,
        resolved_viewport=_resolved_viewport(),
        image_width=800,
        image_height=600,
        dpi=96,
        plan_version="stage-2",
        limits_version="stage-2",
    )
    error = ErrorInfo(code="invalid_input", user_message="Invalid input.")

    assert request.items == (_item(),)
    assert scene_spec.items == (
        _ExampleItemSpec("item-1", PlotKind.EXPLICIT_FUNCTION),
    )
    assert result.warnings == ("viewport clipped",)
    assert isinstance(request.items, tuple)
    assert isinstance(scene_spec.items, tuple)
    assert isinstance(result.warnings, tuple)

    with pytest.raises(FrozenInstanceError):
        request.image_width = 1000  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        scene_spec.items = ()  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        plan.dpi = 120  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        error.code = "other"  # type: ignore[misc]


def test_all_concrete_cross_component_models_use_frozen_slots() -> None:
    concrete_models = (
        ErrorInfo,
        PlotItemRequest,
        PlotItemResult,
        PlotSceneRequest,
        PlotSceneResult,
        PlotSceneSpec,
        RenderPlan,
        ResolvedViewport,
        ViewportRequest,
    )

    for model in concrete_models:
        assert model.__dataclass_params__.frozen is True
        assert "__dict__" not in model.__dict__


def test_single_plot_is_a_one_item_scene_and_empty_or_duplicate_items_fail() -> None:
    one_item_scene = _scene_request((_item(),))

    assert len(one_item_scene.items) == 1

    with pytest.raises(ValueError, match="must not be empty"):
        _scene_request(())
    with pytest.raises(ValueError, match="unique"):
        _scene_request((_item("same"), _item("same")))


def test_aspect_request_only_belongs_to_viewport_request() -> None:
    request = _scene_request()

    assert request.viewport.aspect_request is AspectRequest.AUTO
    assert not hasattr(request, "aspect_request")


def test_manual_viewport_request_requires_all_bounds() -> None:
    with pytest.raises(ValueError, match="require"):
        ViewportRequest(
            mode=ViewportMode.MANUAL,
            x_min=-1,
            x_max=1,
            y_min=-1,
            aspect_request=AspectRequest.EQUAL,
        )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"x_min": nan}, "finite"),
        ({"x_max": inf}, "finite"),
        ({"x_min": 1, "x_max": 1}, "smaller"),
        ({"x_min": 2, "x_max": 1}, "smaller"),
        ({"y_min": 1, "y_max": 1}, "smaller"),
        ({"y_min": 2, "y_max": 1}, "smaller"),
    ],
)
def test_resolved_viewport_rejects_invalid_final_ranges(
    kwargs: dict[str, float],
    message: str,
) -> None:
    resolved_kwargs = {
        "x_min": -1.0,
        "x_max": 1.0,
        "y_min": -1.0,
        "y_max": 1.0,
        "aspect": ResolvedAspect.AUTO,
        "source": ViewportSource.AUTO_PROBE,
    }
    resolved_kwargs.update(kwargs)

    with pytest.raises(ValueError, match=message):
        ResolvedViewport(**resolved_kwargs)


def test_task_phase_has_only_the_six_approved_values() -> None:
    assert [phase.name for phase in TaskPhase] == [
        "IDLE",
        "CAPTURING",
        "RECOGNIZING",
        "REVIEWING",
        "RENDERING",
        "SHUTTING_DOWN",
    ]


def test_viewport_source_includes_the_reserved_geometry_origin() -> None:
    assert [source.name for source in ViewportSource] == [
        "MANUAL",
        "AUTO_PROBE",
        "AUTO_FALLBACK",
        "AUTO_GEOMETRY",
    ]


def test_results_use_immutable_bytes_not_gui_or_mutable_buffers() -> None:
    with pytest.raises(TypeError, match="bytes"):
        PlotSceneResult(
            request_id=1,
            scene_revision=0,
            success=True,
            png_bytes=bytearray(b"png"),  # type: ignore[arg-type]
        )

    result = PlotSceneResult(
        request_id=1,
        scene_revision=0,
        success=True,
        png_bytes=b"png",
        item_results=[
            PlotItemResult(
                item_id="item-1",
                success=True,
                plot_kind=PlotKind.EXPLICIT_FUNCTION,
                concrete_plot_type=ConcretePlotType.EXPLICIT_FUNCTION,
            )
        ],
    )
    assert result.png_bytes == b"png"
    assert isinstance(result.png_bytes, bytes)
    assert isinstance(result.item_results, tuple)


def test_concrete_plot_type_is_closed_and_orthogonal_to_plot_kind() -> None:
    assert [(value.name, value.value) for value in ConcretePlotType] == [
        ("EXPLICIT_FUNCTION", "explicit_function"),
        ("GENERAL_LINE", "general_line"),
        ("CIRCLE", "circle"),
        ("ELLIPSE", "ellipse"),
        ("HYPERBOLA", "hyperbola"),
        ("PARABOLA", "parabola"),
    ]
    for concrete, kind in (
        (ConcretePlotType.EXPLICIT_FUNCTION, PlotKind.EXPLICIT_FUNCTION),
        (ConcretePlotType.GENERAL_LINE, PlotKind.LINE_EQUATION),
        (ConcretePlotType.CIRCLE, PlotKind.CONIC_EQUATION),
        (ConcretePlotType.ELLIPSE, PlotKind.CONIC_EQUATION),
        (ConcretePlotType.HYPERBOLA, PlotKind.CONIC_EQUATION),
        (ConcretePlotType.PARABOLA, PlotKind.CONIC_EQUATION),
    ):
        result = PlotItemResult(
            item_id="item",
            success=True,
            plot_kind=kind,
            concrete_plot_type=concrete,
        )
        assert result.concrete_plot_type is concrete


def test_item_result_enforces_failure_identity_style_and_owned_warnings() -> None:
    error = ErrorInfo(
        code="invalid_input",
        user_message="invalid",
        item_id="item",
    )
    warning_list = ["first", "second"]
    result = PlotItemResult(
        item_id="item",
        success=False,
        style_key="primary",
        warnings=warning_list,
        error=error,
    )
    warning_list.append("later")
    assert result.warnings == ("first", "second")
    with pytest.raises(ValueError, match="must contain an error"):
        PlotItemResult(item_id="item", success=False)
    with pytest.raises(ValueError, match="match"):
        PlotItemResult(
            item_id="item",
            success=False,
            error=ErrorInfo(
                code="invalid_input",
                user_message="invalid",
                item_id="other",
            ),
        )
    with pytest.raises(ValueError, match="style_key"):
        PlotItemResult(item_id="item", success=True, style_key=" ")
    with pytest.raises(ValueError, match="duplicate"):
        PlotItemResult(item_id="item", success=True, warnings=("same", "same"))


def test_item_diagnostics_require_a_matching_concrete_type() -> None:
    diagnostics = PlotItemDiagnostics(planned_sample_point_count=10)
    with pytest.raises(ValueError, match="present together"):
        PlotItemResult(
            item_id="item",
            success=True,
            plot_kind=PlotKind.EXPLICIT_FUNCTION,
        )
    with pytest.raises(ValueError, match="known concrete"):
        PlotItemResult(
            item_id="item",
            success=True,
            diagnostics=diagnostics,
        )
    with pytest.raises(ValueError, match="does not match"):
        PlotItemResult(
            item_id="item",
            success=True,
            plot_kind=PlotKind.LINE_EQUATION,
            concrete_plot_type=ConcretePlotType.CIRCLE,
        )
