"""Stage 15-B production coverage for the unified single-item executor."""

from __future__ import annotations

from dataclasses import replace
import struct

import numpy as np
import pytest

from math_drawing_assistant.engine import scene_executor as executor_module
from math_drawing_assistant.engine.renderer import RenderCancelled
from math_drawing_assistant.engine.scene_executor import SceneRenderExecutor
from math_drawing_assistant.engine.viewport_resolver import ViewportResolution
from math_drawing_assistant.models import (
    ConcretePlotType,
    ErrorCode,
    ErrorInfo,
    InputSource,
    PlotItemRequest,
    PlotKind,
    PlotSceneRequest,
    ViewportMode,
    ViewportRequest,
)


class _Probe:
    def __init__(self, cancelled: bool = False) -> None:
        self.cancelled = cancelled

    def is_cancelled(self) -> bool:
        return self.cancelled


def _request(
    text: str,
    *,
    kind: PlotKind = PlotKind.AUTO,
    source: InputSource = InputSource.MANUAL,
    viewport: ViewportRequest | None = None,
    image_width: int = 400,
) -> PlotSceneRequest:
    return PlotSceneRequest(
        request_id=91,
        scene_revision=7,
        items=(
            PlotItemRequest(
                item_id="stage15b-item",
                input_text=text,
                input_source=source,
                requested_plot_kind=kind,
                display_order=0,
                style_key="primary",
            ),
        ),
        viewport=viewport
        or ViewportRequest(
            mode=ViewportMode.MANUAL,
            x_min=-10,
            x_max=10,
            y_min=-10,
            y_max=10,
        ),
        image_width=image_width,
        image_height=300,
        dpi=96,
        show_grid=True,
        show_legend=False,
    )


def _execute(request: PlotSceneRequest, probe: _Probe | None = None):
    return SceneRenderExecutor().execute(request, probe or _Probe())


def _png_size(value: bytes) -> tuple[int, int]:
    assert value.startswith(b"\x89PNG\r\n\x1a\n")
    assert value[12:16] == b"IHDR"
    return struct.unpack(">II", value[16:24])


@pytest.mark.parametrize(
    ("text", "plot_kind", "concrete_type"),
    [
        ("y=x^2", PlotKind.EXPLICIT_FUNCTION, ConcretePlotType.EXPLICIT_FUNCTION),
        ("x+y=1", PlotKind.LINE_EQUATION, ConcretePlotType.GENERAL_LINE),
        ("x^2+y^2=25", PlotKind.CONIC_EQUATION, ConcretePlotType.CIRCLE),
        ("x^2/9+y^2/4=1", PlotKind.CONIC_EQUATION, ConcretePlotType.ELLIPSE),
        ("x^2/9-y^2/4=1", PlotKind.CONIC_EQUATION, ConcretePlotType.HYPERBOLA),
        ("x^2=4*y", PlotKind.CONIC_EQUATION, ConcretePlotType.PARABOLA),
    ],
)
def test_six_exact_types_complete_the_same_production_contract(
    text: str,
    plot_kind: PlotKind,
    concrete_type: ConcretePlotType,
) -> None:
    result = _execute(_request(text))

    assert result.success is True
    assert result.error is None
    assert result.png_bytes is not None
    assert _png_size(result.png_bytes) == (400, 300)
    assert len(result.item_results) == 1
    item = result.item_results[0]
    assert item.success is True
    assert item.plot_kind is plot_kind
    assert item.concrete_plot_type is concrete_type
    assert item.normalized_input is not None
    assert item.diagnostics is not None
    assert result.diagnostics is not None
    assert item.diagnostics.planned_sample_point_count == (
        item.diagnostics.actual_sampled_point_count
    )
    assert item.diagnostics.sampled_segment_count is not None
    assert item.diagnostics.visible_segment_count is not None
    assert (
        0
        < item.diagnostics.visible_segment_count
        <= item.diagnostics.sampled_segment_count
    )
    assert result.diagnostics.total_planned_sample_point_count == (
        item.diagnostics.planned_sample_point_count
    )
    assert result.diagnostics.total_actual_sampled_point_count == (
        item.diagnostics.actual_sampled_point_count
    )
    assert result.diagnostics.approved_estimated_memory_bytes > 0
    assert result.diagnostics.final_png_byte_count == len(result.png_bytes)
    assert [timing.stage for timing in result.elapsed_ms] == [
        "request_validation",
        "analysis",
        "viewport_resolution",
        "render_plan",
        "sampling",
        "rendering",
    ]


@pytest.mark.parametrize("text", ["x=2", "x+y=1", "2x-y+3=0", "y+1=x+2"])
def test_four_formal_general_lines_use_the_unified_executor(text: str) -> None:
    result = _execute(_request(text))
    assert result.success is True
    assert result.item_results[0].plot_kind is PlotKind.LINE_EQUATION
    assert result.item_results[0].concrete_plot_type is ConcretePlotType.GENERAL_LINE


REQUESTED_KIND_MATRIX = (
    ("y=2*x+1", PlotKind.AUTO, True, None),
    ("y=2*x+1", PlotKind.EXPLICIT_FUNCTION, True, None),
    ("y=2*x+1", PlotKind.LINE_EQUATION, False, ErrorCode.INVALID_REQUEST),
    ("y=2*x+1", PlotKind.CONIC_EQUATION, False, ErrorCode.INVALID_REQUEST),
    ("x=y", PlotKind.AUTO, True, None),
    ("x=y", PlotKind.EXPLICIT_FUNCTION, True, None),
    ("x=y", PlotKind.LINE_EQUATION, False, ErrorCode.INVALID_REQUEST),
    ("x=y", PlotKind.CONIC_EQUATION, False, ErrorCode.INVALID_REQUEST),
    ("x=2", PlotKind.AUTO, True, None),
    ("x=2", PlotKind.EXPLICIT_FUNCTION, False, ErrorCode.UNSUPPORTED_EQUATION),
    ("x=2", PlotKind.LINE_EQUATION, True, None),
    ("x=2", PlotKind.CONIC_EQUATION, False, ErrorCode.INVALID_REQUEST),
    ("x+y=1", PlotKind.AUTO, True, None),
    ("x+y=1", PlotKind.EXPLICIT_FUNCTION, False, ErrorCode.UNSUPPORTED_EQUATION),
    ("x+y=1", PlotKind.LINE_EQUATION, True, None),
    ("x+y=1", PlotKind.CONIC_EQUATION, False, ErrorCode.INVALID_REQUEST),
    ("x^2+y^2=25", PlotKind.AUTO, True, None),
    ("x^2+y^2=25", PlotKind.EXPLICIT_FUNCTION, False, ErrorCode.UNSUPPORTED_EQUATION),
    ("x^2+y^2=25", PlotKind.LINE_EQUATION, False, ErrorCode.INVALID_REQUEST),
    ("x^2+y^2=25", PlotKind.CONIC_EQUATION, True, None),
    ("x^2=4*y", PlotKind.AUTO, True, None),
    ("x^2=4*y", PlotKind.EXPLICIT_FUNCTION, False, ErrorCode.UNSUPPORTED_EQUATION),
    ("x^2=4*y", PlotKind.LINE_EQUATION, False, ErrorCode.INVALID_REQUEST),
    ("x^2=4*y", PlotKind.CONIC_EQUATION, True, None),
    ("y=x+y", PlotKind.AUTO, True, None),
    (
        "y=x+y",
        PlotKind.EXPLICIT_FUNCTION,
        False,
        ErrorCode.EXPLICIT_FUNCTION_Y_NOT_ALLOWED,
    ),
    ("y=x+y", PlotKind.LINE_EQUATION, True, None),
    ("y=x+y", PlotKind.CONIC_EQUATION, False, ErrorCode.INVALID_REQUEST),
)


@pytest.mark.parametrize(
    ("text", "kind", "success", "error_code"),
    REQUESTED_KIND_MATRIX,
)
def test_requested_kind_matrix_matches_the_analyzer_contract(
    text: str,
    kind: PlotKind,
    success: bool,
    error_code: ErrorCode | None,
) -> None:
    result = _execute(_request(text, kind=kind))
    assert result.success is success
    if success:
        assert result.error is None
    else:
        assert result.error is not None
        assert result.error.code is error_code
        assert result.item_results[0].normalized_input is None
        assert result.item_results[0].plot_kind is None
        assert result.item_results[0].concrete_plot_type is None
        assert result.item_results[0].diagnostics is None


def test_manual_empty_multi_ocr_and_wrong_request_type_are_gated() -> None:
    ocr = _execute(_request("x", source=InputSource.OCR))
    assert ocr.error is not None and ocr.error.field_name == "input_source"
    empty_request = _request("x")
    object.__setattr__(empty_request, "items", ())
    empty = _execute(empty_request)
    assert empty.item_results == ()
    assert empty.error is not None and empty.error.field_name == "items"
    first = _request("x").items[0]
    multi = _execute(replace(_request("x"), items=(first, replace(first, item_id="b"))))
    assert multi.item_results == ()
    with pytest.raises(TypeError, match="exact PlotSceneRequest"):
        SceneRenderExecutor().execute(object(), _Probe())  # type: ignore[arg-type]


def test_failure_fields_are_preserved_at_each_completed_stage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis = _execute(_request("x+"))
    assert analysis.item_results[0].normalized_input is None
    assert [timing.stage for timing in analysis.elapsed_ms] == [
        "request_validation",
        "analysis",
    ]

    viewport_error = ErrorInfo(
        code=ErrorCode.INVALID_VIEWPORT,
        user_message="invalid viewport",
        recoverable=True,
    )
    with monkeypatch.context() as context:
        context.setattr(
            executor_module,
            "resolve_single_item_viewport",
            lambda *args, **kwargs: ViewportResolution(error=viewport_error),
        )
        viewport = _execute(_request("x^2"))
    assert viewport.item_results[0].normalized_input == "x^2"
    assert viewport.item_results[0].concrete_plot_type is ConcretePlotType.EXPLICIT_FUNCTION
    assert viewport.item_results[0].diagnostics is None
    assert viewport.resolved_viewport is None

    plan = _execute(_request("x^2", image_width=319))
    assert plan.resolved_viewport is not None
    assert plan.item_results[0].diagnostics is None
    assert [timing.stage for timing in plan.elapsed_ms][-1] == "render_plan"

    sampling_error = ErrorInfo(
        code=ErrorCode.INTERNAL_ERROR,
        user_message="sampling failed",
        recoverable=False,
    )
    with monkeypatch.context() as context:
        context.setattr(
            executor_module,
            "sample_explicit_function",
            lambda *args, **kwargs: sampling_error,
        )
        sampling = _execute(_request("x^2"))
    assert sampling.item_results[0].diagnostics is not None
    assert sampling.item_results[0].diagnostics.actual_sampled_point_count is None
    assert sampling.diagnostics is not None
    assert sampling.diagnostics.total_actual_sampled_point_count is None
    assert [timing.stage for timing in sampling.elapsed_ms][-1] == "sampling"

    render_error = ErrorInfo(
        code=ErrorCode.RENDER_FAILED,
        user_message="render failed",
        recoverable=True,
    )
    with monkeypatch.context() as context:
        context.setattr(
            executor_module,
            "render_sampled_curve_png",
            lambda *args, **kwargs: render_error,
        )
        rendering = _execute(_request("x^2/9-y^2/4=1"))
    assert rendering.png_bytes is None
    assert rendering.item_results[0].diagnostics is not None
    assert rendering.item_results[0].diagnostics.actual_sampled_point_count is not None
    assert rendering.diagnostics is not None
    assert rendering.diagnostics.final_png_byte_count is None
    assert rendering.item_results[0].warnings == ("viewport_clipped",)
    assert rendering.warnings == ("viewport_clipped",)
    assert [timing.stage for timing in rendering.elapsed_ms][-1] == "rendering"


@pytest.mark.parametrize(
    "text",
    ["y=100", "(x-100)^2+(y-100)^2=1"],
)
def test_no_visible_curve_never_reaches_renderer(
    text: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        executor_module,
        "render_sampled_curve_png",
        lambda *args, **kwargs: pytest.fail("renderer must not run"),
    )
    result = _execute(_request(text))
    assert result.success is False
    assert result.png_bytes is None
    assert result.error is not None
    assert result.error.code is ErrorCode.NO_VISIBLE_CURVE


def test_viewport_and_sampling_warnings_keep_their_owners_and_order() -> None:
    result = _execute(
        _request(
            "sqrt(0.000064-x^2)",
            viewport=ViewportRequest(mode=ViewportMode.AUTO),
            image_width=800,
        ),
    )
    assert result.success is True
    assert result.warnings == ("auto_viewport_fallback", "partial_domain_omitted")
    assert result.item_results[0].warnings == ("partial_domain_omitted",)

    hyperbola = _execute(_request("x^2/9-y^2/4=1"))
    assert hyperbola.success is True
    assert "viewport_clipped" in hyperbola.warnings
    assert hyperbola.item_results[0].warnings == hyperbola.warnings


def test_duplicate_sampling_warning_codes_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = executor_module._sample_geometry_curve_for_scene

    def duplicate_warning(*args: object, **kwargs: object):
        outcome = original(*args, **kwargs)
        assert hasattr(outcome, "warnings") and outcome.warnings
        object.__setattr__(outcome, "warnings", outcome.warnings + outcome.warnings)
        return outcome

    monkeypatch.setattr(
        executor_module,
        "_sample_geometry_curve_for_scene",
        duplicate_warning,
    )
    monkeypatch.setattr(
        executor_module,
        "render_sampled_curve_png",
        lambda *args, **kwargs: pytest.fail("renderer must not run"),
    )
    result = _execute(_request("x^2/9-y^2/4=1"))
    assert result.error is not None
    assert result.error.code is ErrorCode.INTERNAL_ERROR
    assert result.item_results[0].warnings == ()


def test_cancellation_sentinel_is_completely_neutral() -> None:
    result = _execute(_request("x^2"), _Probe(cancelled=True))
    assert result.success is False
    assert result.error is None
    assert result.png_bytes is None
    assert result.item_results == ()
    assert result.resolved_viewport is None
    assert result.warnings == ()
    assert result.diagnostics is None
    assert result.elapsed_ms == ()


def test_mismatched_stage_error_item_id_becomes_bound_internal_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        executor_module,
        "sample_explicit_function",
        lambda *args, **kwargs: ErrorInfo(
            code=ErrorCode.NO_VISIBLE_CURVE,
            user_message="wrong owner",
            item_id="other-item",
            recoverable=True,
        ),
    )
    monkeypatch.setattr(
        executor_module,
        "render_sampled_curve_png",
        lambda *args, **kwargs: pytest.fail("renderer must not run"),
    )
    result = _execute(_request("x^2"))
    assert result.error is result.item_results[0].error
    assert result.error is not None
    assert result.error.code is ErrorCode.INTERNAL_ERROR
    assert result.error.item_id == "stage15b-item"


@pytest.mark.parametrize(
    "render_outcome",
    (
        RenderCancelled("other-item"),
        ErrorInfo(
            code=ErrorCode.RENDER_FAILED,
            user_message="wrong render owner",
            item_id="other-item",
            recoverable=True,
        ),
    ),
)
def test_mismatched_renderer_outcome_identity_is_not_neutral(
    render_outcome: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        executor_module,
        "render_sampled_curve_png",
        lambda *args, **kwargs: render_outcome,
    )
    result = _execute(_request("x^2"))
    assert result.success is False
    assert result.error is not None
    assert result.error.code is ErrorCode.INTERNAL_ERROR
    assert result.error.item_id == "stage15b-item"
    assert result.item_results[0].diagnostics is not None
    assert result.item_results[0].diagnostics.actual_sampled_point_count is not None


def test_plan_failure_keeps_viewport_warning_scene_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        executor_module.RenderPlanBuilder,
        "build",
        lambda *args, **kwargs: ErrorInfo(
            code=ErrorCode.RESOURCE_LIMIT_EXCEEDED,
            user_message="plan failed",
            recoverable=True,
        ),
    )
    result = _execute(
        _request(
            "sqrt(0.000064-x^2)",
            viewport=ViewportRequest(mode=ViewportMode.AUTO),
            image_width=800,
        ),
    )
    assert result.success is False
    assert result.warnings == ("auto_viewport_fallback",)
    assert result.item_results[0].warnings == ()


def test_item_diagnostics_distinguish_sampled_and_visible_segments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = executor_module.sample_explicit_function

    def reduce_visible_count(*args: object, **kwargs: object):
        sampled = original(*args, **kwargs)
        assert hasattr(sampled, "segment_ranges")
        midpoint = sampled.x.shape[0] // 2
        ranges = np.array(
            ((0, midpoint), (midpoint, sampled.x.shape[0])),
            dtype=np.int64,
        )
        ranges.setflags(write=False)
        object.__setattr__(sampled, "segment_ranges", ranges)
        object.__setattr__(sampled, "visible_segment_count", 1)
        return sampled

    monkeypatch.setattr(executor_module, "sample_explicit_function", reduce_visible_count)
    monkeypatch.setattr(
        executor_module,
        "render_sampled_curve_png",
        lambda *args, **kwargs: b"\x89PNG\r\n\x1a\nsynthetic",
    )
    result = _execute(_request("x"))
    assert result.success is True
    diagnostics = result.item_results[0].diagnostics
    assert diagnostics is not None
    assert diagnostics.sampled_segment_count == 2
    assert diagnostics.visible_segment_count == 1
