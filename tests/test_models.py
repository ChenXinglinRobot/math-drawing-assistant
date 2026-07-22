"""Focused stage-2 tests for immutable cross-component model contracts."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, dataclass
from math import inf, nan

import pytest

from math_drawing_assistant.models import (
    AspectRequest,
    ErrorInfo,
    InputSource,
    PlotItemRequest,
    PlotItemResult,
    PlotKind,
    PlotSceneRequest,
    PlotSceneResult,
    PlotSceneSpec,
    RenderPlan,
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
        aspect=AspectRequest.EQUAL,
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
        "aspect": AspectRequest.AUTO,
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


def test_viewport_source_has_only_manual_probe_and_fallback_origins() -> None:
    assert [source.name for source in ViewportSource] == [
        "MANUAL",
        "AUTO_PROBE",
        "AUTO_FALLBACK",
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
            )
        ],
    )
    assert result.png_bytes == b"png"
    assert isinstance(result.png_bytes, bytes)
    assert isinstance(result.item_results, tuple)
