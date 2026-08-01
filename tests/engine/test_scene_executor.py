"""Stage 11A tests for the sole production M1 scene orchestration."""

from __future__ import annotations

import ast
from dataclasses import replace
import inspect
from pathlib import Path
import struct

import pytest

from math_drawing_assistant.config import DEFAULT_LIMITS
from math_drawing_assistant.engine import scene_executor as scene_executor_module
from math_drawing_assistant.engine.scene_executor import SceneRenderExecutor
from math_drawing_assistant.models.errors import ErrorCode, ErrorInfo
from math_drawing_assistant.models.requests import PlotItemRequest, PlotSceneRequest
from math_drawing_assistant.models.results import PlotSceneResult
from math_drawing_assistant.models.state import (
    AspectRequest,
    InputSource,
    PlotKind,
    ViewportMode,
    ViewportSource,
)
from math_drawing_assistant.models.viewport import ViewportRequest


_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_ROOT = Path(__file__).resolve().parents[2]


class _Probe:
    def __init__(self, *, cancelled: bool = False) -> None:
        self.cancelled = cancelled

    def cancel(self) -> None:
        self.cancelled = True

    def is_cancelled(self) -> bool:
        return self.cancelled


class _CancelInsideModule:
    def __init__(self, filename: str) -> None:
        self.filename = filename

    def is_cancelled(self) -> bool:
        frame = inspect.currentframe()
        assert frame is not None
        frame = frame.f_back
        while frame is not None:
            if Path(frame.f_code.co_filename).name == self.filename:
                return True
            frame = frame.f_back
        return False


def _request(
    text: str = "x^2",
    *,
    request_id: int = 17,
    scene_revision: int = 23,
    viewport: ViewportRequest | None = None,
    requested_plot_kind: PlotKind = PlotKind.AUTO,
    input_source: InputSource = InputSource.MANUAL,
    image_width: int = 400,
    image_height: int = 300,
    style_key: str | None = "primary",
) -> PlotSceneRequest:
    return PlotSceneRequest(
        request_id=request_id,
        scene_revision=scene_revision,
        items=(
            PlotItemRequest(
                item_id="item-a",
                input_text=text,
                input_source=input_source,
                requested_plot_kind=requested_plot_kind,
                display_order=0,
                style_key=style_key,
            ),
        ),
        viewport=viewport
        or ViewportRequest(
            mode=ViewportMode.MANUAL,
            x_min=-5,
            x_max=5,
            y_min=-5,
            y_max=25,
        ),
        image_width=image_width,
        image_height=image_height,
        dpi=96,
        show_grid=True,
        show_legend=False,
    )


def _execute(
    request: PlotSceneRequest,
    *,
    executor: SceneRenderExecutor | None = None,
    probe: object | None = None,
) -> PlotSceneResult:
    return (executor or SceneRenderExecutor()).execute(
        request,
        probe or _Probe(),  # type: ignore[arg-type]
    )


def _png_size(png_bytes: bytes) -> tuple[int, int]:
    assert png_bytes.startswith(_PNG_SIGNATURE)
    assert png_bytes[12:16] == b"IHDR"
    return struct.unpack(">II", png_bytes[16:24])


@pytest.mark.parametrize(
    "requested_plot_kind",
    [PlotKind.AUTO, PlotKind.EXPLICIT_FUNCTION],
)
def test_single_explicit_scene_succeeds_with_complete_result_metadata(
    requested_plot_kind: PlotKind,
) -> None:
    result = _execute(
        _request(
            "x²",
            request_id=101,
            scene_revision=44,
            requested_plot_kind=requested_plot_kind,
        ),
    )

    assert result.success is True
    assert result.request_id == 101
    assert result.scene_revision == 44
    assert result.error is None
    assert result.png_bytes is not None
    assert _png_size(result.png_bytes) == (400, 300)
    assert result.resolved_viewport is not None
    assert len(result.item_results) == 1
    item_result = result.item_results[0]
    assert item_result.success is True
    assert item_result.item_id == "item-a"
    assert item_result.normalized_input == "x^2"
    assert item_result.plot_kind is PlotKind.EXPLICIT_FUNCTION
    assert item_result.style_key == "primary"
    assert result.elapsed_ms == ()


def test_auto_y_resolution_is_returned_from_the_formal_resolver() -> None:
    request = _request(
        "x^2",
        viewport=ViewportRequest(mode=ViewportMode.AUTO, x_min=-2, x_max=2),
    )

    result = _execute(request)

    assert result.success is True
    assert result.resolved_viewport is not None
    assert result.resolved_viewport.source is ViewportSource.AUTO_PROBE
    assert result.resolved_viewport.aspect is AspectRequest.AUTO
    assert result.resolved_viewport.x_min == -2
    assert result.resolved_viewport.x_max == 2
    assert result.resolved_viewport.y_min < result.resolved_viewport.y_max


def test_unreliable_auto_range_falls_back_and_aggregates_real_warning_codes() -> None:
    request = _request(
        "sqrt(0.000064-x^2)",
        viewport=ViewportRequest(mode=ViewportMode.AUTO),
        image_width=800,
    )

    result = _execute(request)

    assert result.success is True
    assert result.resolved_viewport is not None
    assert result.resolved_viewport.source is ViewportSource.AUTO_FALLBACK
    assert (
        result.resolved_viewport.x_min,
        result.resolved_viewport.x_max,
        result.resolved_viewport.y_min,
        result.resolved_viewport.y_max,
    ) == (-10, 10, -10, 10)
    assert result.warnings == (
        "auto_viewport_fallback",
        "partial_domain_omitted",
    )
    assert result.item_results[0].warnings == ("partial_domain_omitted",)


def test_manual_four_bounds_and_requested_aspect_take_priority() -> None:
    viewport = ViewportRequest(
        mode=ViewportMode.MANUAL,
        x_min=-3,
        x_max=7,
        y_min=-11,
        y_max=13,
        aspect_request=AspectRequest.EQUAL,
    )

    result = _execute(_request("x", viewport=viewport))

    assert result.success is True
    assert result.resolved_viewport is not None
    assert result.resolved_viewport.source is ViewportSource.MANUAL
    assert result.resolved_viewport.aspect is AspectRequest.EQUAL
    assert (
        result.resolved_viewport.x_min,
        result.resolved_viewport.x_max,
        result.resolved_viewport.y_min,
        result.resolved_viewport.y_max,
    ) == (-3, 7, -11, 13)


def test_empty_scene_is_a_structured_request_failure() -> None:
    request = _request()
    object.__setattr__(request, "items", ())

    result = _execute(request)

    assert result.success is False
    assert result.png_bytes is None
    assert result.item_results == ()
    assert result.error is not None
    assert result.error.code is ErrorCode.INVALID_REQUEST
    assert result.error.field_name == "items"


def test_multiple_items_are_rejected_before_analysis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _request().items[0]
    second = replace(first, item_id="item-b", display_order=1)
    request = replace(_request(), items=(first, second))
    monkeypatch.setattr(
        scene_executor_module,
        "analyze_explicit_function",
        lambda *args, **kwargs: pytest.fail("analyzer must not run"),
    )

    result = _execute(request)

    assert result.success is False
    assert result.error is not None
    assert result.error.code is ErrorCode.INVALID_REQUEST
    assert result.error.field_name == "items"


@pytest.mark.parametrize(
    ("plot_kind", "input_source", "field_name"),
    [
        (PlotKind.LINE_EQUATION, InputSource.MANUAL, "requested_plot_kind"),
        (PlotKind.CONIC_EQUATION, InputSource.MANUAL, "requested_plot_kind"),
        (PlotKind.AUTO, InputSource.OCR, "input_source"),
    ],
)
def test_non_m1_plot_kinds_and_ocr_are_rejected(
    plot_kind: PlotKind,
    input_source: InputSource,
    field_name: str,
) -> None:
    result = _execute(
        _request(
            requested_plot_kind=plot_kind,
            input_source=input_source,
        ),
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.code is ErrorCode.INVALID_REQUEST
    assert result.error.field_name == field_name
    assert result.error.item_id == "item-a"
    assert result.item_results[0].error is result.error


def test_syntax_failure_preserves_item_and_source_location() -> None:
    result = _execute(_request("x+"))

    assert result.success is False
    assert result.png_bytes is None
    assert result.error is not None
    assert result.error.code is ErrorCode.ILLEGAL_TRAILING
    assert result.error.item_id == "item-a"
    assert result.error.source_location is not None
    assert result.item_results[0].error is result.error


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("image_width", DEFAULT_LIMITS.min_image_width - 1),
        ("image_height", DEFAULT_LIMITS.min_image_height - 1),
        ("dpi", DEFAULT_LIMITS.min_dpi - 1),
    ],
)
def test_invalid_output_parameters_fail_through_the_formal_plan_builder(
    field_name: str,
    value: int,
) -> None:
    request = replace(_request(), **{field_name: value})

    result = _execute(request)

    assert result.success is False
    assert result.png_bytes is None
    assert result.resolved_viewport is not None
    assert result.error is not None
    assert result.error.code is ErrorCode.INVALID_REQUEST
    assert result.error.field_name == "output"


def test_probe_budget_failure_precedes_formal_sampling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        scene_executor_module,
        "sample_explicit_function",
        lambda *args, **kwargs: pytest.fail("sampler must not run"),
    )
    limits = replace(DEFAULT_LIMITS, max_viewport_probe_bytes=1)
    executor = SceneRenderExecutor(limits=limits)
    request = _request(viewport=ViewportRequest(mode=ViewportMode.AUTO))

    result = _execute(request, executor=executor)

    assert result.success is False
    assert result.error is not None
    assert result.error.code is ErrorCode.VIEWPORT_PROBE_BUDGET_EXCEEDED


def test_final_plan_budget_failure_precedes_formal_sampling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        scene_executor_module,
        "sample_explicit_function",
        lambda *args, **kwargs: pytest.fail("sampler must not run"),
    )
    limits = replace(DEFAULT_LIMITS, max_estimated_memory_bytes=1)

    result = _execute(_request(), executor=SceneRenderExecutor(limits=limits))

    assert result.success is False
    assert result.error is not None
    assert result.error.code is ErrorCode.RESOURCE_LIMIT_EXCEEDED
    assert result.error.field_name == "max_estimated_memory_bytes"


def test_cancellation_before_analyzer_is_neutral_and_skips_analysis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        scene_executor_module,
        "analyze_explicit_function",
        lambda *args, **kwargs: pytest.fail("analyzer must not run"),
    )

    result = _execute(_request(), probe=_Probe(cancelled=True))

    assert result.success is False
    assert result.png_bytes is None
    assert result.error is None
    assert result.item_results == ()


@pytest.mark.parametrize(
    "stage_name",
    ["analyze_explicit_function", "build_explicit_scene_spec"],
)
def test_cancellation_at_early_stage_boundaries_is_neutral(
    stage_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe = _Probe()
    original = getattr(scene_executor_module, stage_name)

    def cancel_after_stage(*args: object, **kwargs: object) -> object:
        outcome = original(*args, **kwargs)
        probe.cancel()
        return outcome

    monkeypatch.setattr(scene_executor_module, stage_name, cancel_after_stage)

    result = _execute(_request(), probe=probe)

    assert result.success is False
    assert result.png_bytes is None
    assert result.error is None


def test_cancellation_after_viewport_and_plan_boundaries_is_neutral(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for stage in ("viewport", "plan"):
        probe = _Probe()
        if stage == "viewport":
            original = scene_executor_module.resolve_single_explicit_viewport

            def cancel_after_viewport(*args: object, **kwargs: object) -> object:
                outcome = original(*args, **kwargs)
                probe.cancel()
                return outcome

            with monkeypatch.context() as context:
                context.setattr(
                    scene_executor_module,
                    "resolve_single_explicit_viewport",
                    cancel_after_viewport,
                )
                result = _execute(_request(), probe=probe)
        else:
            original_build = scene_executor_module.RenderPlanBuilder.build

            def cancel_after_plan(*args: object, **kwargs: object) -> object:
                outcome = original_build(*args, **kwargs)
                probe.cancel()
                return outcome

            with monkeypatch.context() as context:
                context.setattr(
                    scene_executor_module.RenderPlanBuilder,
                    "build",
                    cancel_after_plan,
                )
                result = _execute(_request(), probe=probe)

        assert result.success is False
        assert result.png_bytes is None
        assert result.error is None


@pytest.mark.parametrize("module_name", ["samplers.py", "renderer.py"])
def test_sampler_and_renderer_cancellation_are_neutral(module_name: str) -> None:
    result = _execute(_request(), probe=_CancelInsideModule(module_name))

    assert result.success is False
    assert result.png_bytes is None
    assert result.error is None
    assert result.item_results == ()


def test_cancelled_request_does_not_poison_a_later_valid_request() -> None:
    executor = SceneRenderExecutor()
    cancelled = _execute(
        _request(request_id=1),
        executor=executor,
        probe=_Probe(cancelled=True),
    )
    recovered = _execute(_request(request_id=2), executor=executor)

    assert cancelled.success is False
    assert cancelled.error is None
    assert recovered.success is True
    assert recovered.request_id == 2


@pytest.mark.parametrize("stage_name", ["sample_explicit_function", "render_explicit_png"])
def test_structured_stage_errors_become_scene_and_item_failures(
    stage_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = ErrorInfo(
        code=ErrorCode.INTERNAL_ERROR,
        user_message="绘图阶段契约无效。",
        technical_message=f"{stage_name} contract failure",
        field_name="stage",
        recoverable=False,
    )
    monkeypatch.setattr(scene_executor_module, stage_name, lambda *args, **kwargs: error)

    result = _execute(_request())

    assert result.success is False
    assert result.png_bytes is None
    assert result.error is not None
    assert result.error.code is ErrorCode.INTERNAL_ERROR
    assert result.error.item_id == "item-a"
    assert result.item_results[0].error is result.error


@pytest.mark.parametrize(
    "unexpected",
    [RuntimeError("private formula"), MemoryError()],
)
def test_unexpected_exception_propagates_out_of_scene_executor(
    unexpected: Exception,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_unexpected(*args: object, **kwargs: object) -> object:
        raise unexpected

    monkeypatch.setattr(
        scene_executor_module,
        "analyze_explicit_function",
        raise_unexpected,
    )

    with pytest.raises(type(unexpected)):
        _execute(_request())


def test_actor_boundary_desensitizes_unexpected_failure_and_then_recovers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from math_drawing_assistant.workers.cancellation import CancellationToken
    from math_drawing_assistant.workers import render_actor as actor_module

    executor = SceneRenderExecutor()
    original = scene_executor_module.analyze_explicit_function

    def raise_unexpected(*args: object, **kwargs: object) -> object:
        raise RuntimeError("secret-input C:/private/path")

    monkeypatch.setattr(
        scene_executor_module,
        "analyze_explicit_function",
        raise_unexpected,
    )
    failed = actor_module._execute_task(
        executor,
        actor_module._RenderTask(_request(request_id=31), CancellationToken()),
    )
    monkeypatch.setattr(
        scene_executor_module,
        "analyze_explicit_function",
        original,
    )
    recovered = actor_module._execute_task(
        executor,
        actor_module._RenderTask(_request(request_id=32), CancellationToken()),
    )

    assert failed.success is False
    assert failed.error is not None
    assert failed.error.code is ErrorCode.INTERNAL_ERROR
    assert "secret" not in failed.error.user_message
    assert failed.error.technical_message is None
    assert recovered.success is True
    assert recovered.request_id == 32


def test_scene_executor_has_no_forbidden_dependency_or_second_render_path() -> None:
    source_path = Path(scene_executor_module.__file__).resolve()
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_modules.add(node.module)

    forbidden_roots = ("PySide6", "matplotlib", "tests", "plot_engine")
    assert not any(
        module == root or module.startswith(f"{root}.")
        for module in imported_modules
        for root in forbidden_roots
    )
    assert not any(".workers" in module for module in imported_modules)
    assert "render_explicit_png" in source
    assert "sample_explicit_function" in source
    assert "FigureCanvasAgg" not in source
    assert "pyplot" not in source

    production_root = _ROOT / "math_drawing_assistant"
    renderer_callers: list[Path] = []
    for path in production_root.rglob("*.py"):
        parsed = ast.parse(path.read_text(encoding="utf-8"))
        if any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "render_explicit_png"
            for node in ast.walk(parsed)
        ):
            renderer_callers.append(path)
        assert not any(
            isinstance(node, ast.ImportFrom)
            and node.module is not None
            and (node.module == "tests" or node.module.startswith("tests."))
            for node in ast.walk(parsed)
        )
    assert renderer_callers == [source_path]
