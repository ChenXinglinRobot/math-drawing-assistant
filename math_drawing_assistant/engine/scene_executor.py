"""Production orchestration for the sole single-item manual scene pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter_ns

from math_drawing_assistant.config import ApplicationLimits, DEFAULT_LIMITS
from math_drawing_assistant.engine import _sample_geometry_curve_for_scene
from math_drawing_assistant.engine.plot_analyzer import analyze_plot_item
from math_drawing_assistant.engine.renderer import (
    RenderCancelled,
    render_sampled_curve_png,
)
from math_drawing_assistant.engine.render_plan_builder import RenderPlanBuilder
from math_drawing_assistant.engine.samplers import (
    CancellationProbe,
    ParameterizedSamplingDiagnostics,
    SampledExplicitFunction,
    SampledParameterizedCurve,
    SamplingCancelled,
    SamplingWarning,
    sample_explicit_function,
)
from math_drawing_assistant.engine.viewport_resolver import resolve_single_item_viewport
from math_drawing_assistant.models.diagnostics import (
    PlotItemDiagnostics,
    PlotSceneDiagnostics,
    StageTiming,
)
from math_drawing_assistant.models.errors import ErrorCode, ErrorInfo
from math_drawing_assistant.models.plot_specs import PlotItemSpec, PlotSceneSpec
from math_drawing_assistant.models.render_plan import RenderPlan
from math_drawing_assistant.models.requests import PlotItemRequest, PlotSceneRequest
from math_drawing_assistant.models.results import (
    ConcretePlotType,
    PlotItemResult,
    PlotSceneResult,
    _item_plan_matches_concrete_type,
    _plot_result_metadata_for_spec,
)
from math_drawing_assistant.models.state import InputSource, PlotKind
from math_drawing_assistant.models.viewport import ResolvedViewport


@dataclass(frozen=True, slots=True)
class SceneRenderExecutor:
    """Execute the only production M1/M1.5 single-item manual scene path."""

    limits: ApplicationLimits = DEFAULT_LIMITS

    def execute(
        self,
        request: PlotSceneRequest,
        cancellation: CancellationProbe,
    ) -> PlotSceneResult:
        """Validate, analyze, plan, sample, and render one manual plot item."""

        timings: list[StageTiming] = []
        started = perf_counter_ns()
        item_or_error = _validated_single_manual_item(request)
        _record_timing(timings, "request_validation", started)
        if isinstance(item_or_error, ErrorInfo):
            return _failure(
                request,
                item_or_error,
                item=_single_exact_item(request),
                elapsed_ms=tuple(timings),
            )
        item = item_or_error

        if _is_cancelled(cancellation):
            return _cancelled(request)

        started = perf_counter_ns()
        spec_or_error = analyze_plot_item(item, limits=self.limits)
        if isinstance(spec_or_error, ErrorInfo):
            _record_timing(timings, "analysis", started)
            return _failure(
                request,
                spec_or_error,
                item=item,
                elapsed_ms=tuple(timings),
            )
        metadata_or_error = _validated_spec_metadata(spec_or_error, item.item_id)
        if isinstance(metadata_or_error, ErrorInfo):
            _record_timing(timings, "analysis", started)
            return _failure(
                request,
                metadata_or_error,
                item=item,
                elapsed_ms=tuple(timings),
            )
        spec, normalized_input, plot_kind, concrete_plot_type = metadata_or_error
        try:
            scene_spec = PlotSceneSpec(items=(spec,))
        except (TypeError, ValueError):
            _record_timing(timings, "analysis", started)
            return _failure(
                request,
                _internal_error(item.item_id, "analyzed scene contract failed"),
                item=item,
                normalized_input=normalized_input,
                plot_kind=plot_kind,
                concrete_plot_type=concrete_plot_type,
                elapsed_ms=tuple(timings),
            )
        _record_timing(timings, "analysis", started)

        if _is_cancelled(cancellation):
            return _cancelled(request)

        started = perf_counter_ns()
        viewport_resolution = resolve_single_item_viewport(
            scene_spec,
            request.viewport,
            limits=self.limits,
        )
        _record_timing(timings, "viewport_resolution", started)
        if viewport_resolution.error is not None:
            return _failure(
                request,
                viewport_resolution.error,
                item=item,
                normalized_input=normalized_input,
                plot_kind=plot_kind,
                concrete_plot_type=concrete_plot_type,
                elapsed_ms=tuple(timings),
            )
        resolved_viewport = viewport_resolution.viewport
        if type(resolved_viewport) is not ResolvedViewport:
            return _failure(
                request,
                _internal_error(item.item_id, "viewport resolver outcome contract failed"),
                item=item,
                normalized_input=normalized_input,
                plot_kind=plot_kind,
                concrete_plot_type=concrete_plot_type,
                elapsed_ms=tuple(timings),
            )
        viewport_warnings = (
            ()
            if viewport_resolution.warning is None
            else (viewport_resolution.warning.code.value,)
        )

        if _is_cancelled(cancellation):
            return _cancelled(request)

        started = perf_counter_ns()
        plan_or_error = RenderPlanBuilder(limits=self.limits).build(
            scene_spec,
            resolved_viewport,
            image_width=request.image_width,
            image_height=request.image_height,
            dpi=request.dpi,
            show_grid=request.show_grid,
            show_legend=request.show_legend,
        )
        _record_timing(timings, "render_plan", started)
        if isinstance(plan_or_error, ErrorInfo):
            return _failure(
                request,
                plan_or_error,
                item=item,
                normalized_input=normalized_input,
                plot_kind=plot_kind,
                concrete_plot_type=concrete_plot_type,
                resolved_viewport=resolved_viewport,
                scene_warnings=viewport_warnings,
                elapsed_ms=tuple(timings),
            )
        plan_error = _validate_dispatch_plan(plan_or_error, spec, item.item_id)
        if plan_error is not None:
            return _failure(
                request,
                plan_error,
                item=item,
                normalized_input=normalized_input,
                plot_kind=plot_kind,
                concrete_plot_type=concrete_plot_type,
                resolved_viewport=resolved_viewport,
                scene_warnings=viewport_warnings,
                elapsed_ms=tuple(timings),
            )
        plan = plan_or_error
        item_plan = plan.item_plan
        memory_budget = plan.memory_budget
        if item_plan is None or memory_budget is None:
            return _failure(
                request,
                _internal_error(item.item_id, "approved plan diagnostics are missing"),
                item=item,
                normalized_input=normalized_input,
                plot_kind=plot_kind,
                concrete_plot_type=concrete_plot_type,
                resolved_viewport=resolved_viewport,
                scene_warnings=viewport_warnings,
                elapsed_ms=tuple(timings),
            )
        planned_item_diagnostics = PlotItemDiagnostics(
            planned_sample_point_count=item_plan.sample_count,
        )
        planned_scene_diagnostics = PlotSceneDiagnostics(
            total_planned_sample_point_count=item_plan.sample_count,
            total_actual_sampled_point_count=None,
            approved_estimated_memory_bytes=memory_budget.total_bytes,
        )

        if _is_cancelled(cancellation):
            return _cancelled(request)

        started = perf_counter_ns()
        if concrete_plot_type is ConcretePlotType.EXPLICIT_FUNCTION:
            sampling_outcome = sample_explicit_function(
                plan,
                cancellation_probe=cancellation,
            )
            expected_sample_type = SampledExplicitFunction
        else:
            sampling_outcome = _sample_geometry_curve_for_scene(
                plan,
                cancellation_probe=cancellation,
            )
            expected_sample_type = SampledParameterizedCurve
        _record_timing(timings, "sampling", started)

        if type(sampling_outcome) is SamplingCancelled:
            if sampling_outcome.item_id == item.item_id:
                return _cancelled(request)
            return _sampling_failure(
                request,
                item,
                normalized_input,
                plot_kind,
                concrete_plot_type,
                resolved_viewport,
                viewport_warnings,
                planned_item_diagnostics,
                planned_scene_diagnostics,
                tuple(timings),
                _internal_error(item.item_id, "sampling cancellation item identity mismatch"),
            )
        if isinstance(sampling_outcome, ErrorInfo):
            return _sampling_failure(
                request,
                item,
                normalized_input,
                plot_kind,
                concrete_plot_type,
                resolved_viewport,
                viewport_warnings,
                planned_item_diagnostics,
                planned_scene_diagnostics,
                tuple(timings),
                sampling_outcome,
            )
        if type(sampling_outcome) is not expected_sample_type:
            return _sampling_failure(
                request,
                item,
                normalized_input,
                plot_kind,
                concrete_plot_type,
                resolved_viewport,
                viewport_warnings,
                planned_item_diagnostics,
                planned_scene_diagnostics,
                tuple(timings),
                _internal_error(item.item_id, "sampling outcome type mismatch"),
            )
        completed_or_error = _completed_sampling_contract(
            sampling_outcome,
            plan,
            item.item_id,
        )
        if isinstance(completed_or_error, ErrorInfo):
            return _sampling_failure(
                request,
                item,
                normalized_input,
                plot_kind,
                concrete_plot_type,
                resolved_viewport,
                viewport_warnings,
                planned_item_diagnostics,
                planned_scene_diagnostics,
                tuple(timings),
                completed_or_error,
            )
        item_diagnostics, scene_diagnostics, sampling_warnings = completed_or_error
        scene_warnings = _stable_unique(viewport_warnings + sampling_warnings)

        if _is_cancelled(cancellation):
            return _cancelled(request)

        started = perf_counter_ns()
        render_outcome = render_sampled_curve_png(
            plan,
            sampling_outcome,
            cancellation_probe=cancellation,
        )
        _record_timing(timings, "rendering", started)
        if type(render_outcome) is RenderCancelled:
            if render_outcome.item_id == item.item_id:
                return _cancelled(request)
            render_outcome = _internal_error(
                item.item_id,
                "render cancellation item identity mismatch",
            )
        if isinstance(render_outcome, ErrorInfo):
            return _failure(
                request,
                render_outcome,
                item=item,
                normalized_input=normalized_input,
                plot_kind=plot_kind,
                concrete_plot_type=concrete_plot_type,
                resolved_viewport=resolved_viewport,
                item_warnings=sampling_warnings,
                scene_warnings=scene_warnings,
                item_diagnostics=item_diagnostics,
                scene_diagnostics=scene_diagnostics,
                elapsed_ms=tuple(timings),
            )
        if type(render_outcome) is not bytes:
            return _failure(
                request,
                _internal_error(item.item_id, "renderer outcome type mismatch"),
                item=item,
                normalized_input=normalized_input,
                plot_kind=plot_kind,
                concrete_plot_type=concrete_plot_type,
                resolved_viewport=resolved_viewport,
                item_warnings=sampling_warnings,
                scene_warnings=scene_warnings,
                item_diagnostics=item_diagnostics,
                scene_diagnostics=scene_diagnostics,
                elapsed_ms=tuple(timings),
            )

        if _is_cancelled(cancellation):
            return _cancelled(request)

        final_scene_diagnostics = PlotSceneDiagnostics(
            total_planned_sample_point_count=(
                scene_diagnostics.total_planned_sample_point_count
            ),
            total_actual_sampled_point_count=(
                scene_diagnostics.total_actual_sampled_point_count
            ),
            approved_estimated_memory_bytes=(
                scene_diagnostics.approved_estimated_memory_bytes
            ),
            final_png_byte_count=len(render_outcome),
        )
        item_result = PlotItemResult(
            item_id=item.item_id,
            success=True,
            normalized_input=normalized_input,
            plot_kind=plot_kind,
            concrete_plot_type=concrete_plot_type,
            diagnostics=item_diagnostics,
            style_key=item.style_key,
            warnings=sampling_warnings,
        )
        return PlotSceneResult(
            request_id=request.request_id,
            scene_revision=request.scene_revision,
            success=True,
            png_bytes=render_outcome,
            item_results=(item_result,),
            resolved_viewport=resolved_viewport,
            warnings=scene_warnings,
            elapsed_ms=tuple(timings),
            diagnostics=final_scene_diagnostics,
        )


def _sampling_failure(
    request: PlotSceneRequest,
    item: PlotItemRequest,
    normalized_input: str,
    plot_kind: PlotKind,
    concrete_plot_type: ConcretePlotType,
    resolved_viewport: ResolvedViewport,
    viewport_warnings: tuple[str, ...],
    item_diagnostics: PlotItemDiagnostics,
    scene_diagnostics: PlotSceneDiagnostics,
    elapsed_ms: tuple[StageTiming, ...],
    error: ErrorInfo,
) -> PlotSceneResult:
    return _failure(
        request,
        error,
        item=item,
        normalized_input=normalized_input,
        plot_kind=plot_kind,
        concrete_plot_type=concrete_plot_type,
        resolved_viewport=resolved_viewport,
        scene_warnings=viewport_warnings,
        item_diagnostics=item_diagnostics,
        scene_diagnostics=scene_diagnostics,
        elapsed_ms=elapsed_ms,
    )


def _validated_single_manual_item(
    request: PlotSceneRequest,
) -> PlotItemRequest | ErrorInfo:
    if type(request) is not PlotSceneRequest:
        raise TypeError("request must be an exact PlotSceneRequest")
    if type(request.items) is not tuple:
        return _invalid_request("items", "scene items must be an exact tuple")
    if not request.items:
        return _invalid_request("items", "manual scene is empty")
    if len(request.items) != 1:
        return _invalid_request("items", "manual production requires one scene item")
    item = request.items[0]
    if type(item) is not PlotItemRequest:
        return _invalid_request("items", "manual item contract is not exact")
    if item.input_source is not InputSource.MANUAL:
        return _invalid_request(
            "input_source",
            "manual production rejects non-manual input",
            item_id=item.item_id,
        )
    return item


def _single_exact_item(request: PlotSceneRequest) -> PlotItemRequest | None:
    if type(request.items) is tuple and len(request.items) == 1:
        item = request.items[0]
        if type(item) is PlotItemRequest:
            return item
    return None


def _validated_spec_metadata(
    value: object,
    item_id: str,
) -> tuple[PlotItemSpec, str, PlotKind, ConcretePlotType] | ErrorInfo:
    metadata = _plot_result_metadata_for_spec(value, item_id)
    if metadata is None:
        return _internal_error(item_id, "analyzed spec contract validation failed")
    normalized_input, plot_kind, concrete_plot_type = metadata
    return value, normalized_input, plot_kind, concrete_plot_type


def _validate_dispatch_plan(
    value: object,
    spec: PlotItemSpec,
    item_id: str,
) -> ErrorInfo | None:
    if type(value) is not RenderPlan:
        return _internal_error(item_id, "render plan outcome type mismatch")
    try:
        if type(value.scene_spec) is not PlotSceneSpec:
            raise TypeError
        if type(value.scene_spec.items) is not tuple or len(value.scene_spec.items) != 1:
            raise ValueError
        plan_spec = value.scene_spec.items[0]
        if type(plan_spec) is not type(spec) or plan_spec.item_id != item_id:
            raise ValueError
        metadata = _plot_result_metadata_for_spec(spec, item_id)
        if metadata is None:
            raise TypeError
        concrete_plot_type = metadata[2]
        item_plan = value.item_plan
        if not _item_plan_matches_concrete_type(
            item_plan,
            concrete_plot_type,
            item_id,
        ):
            raise ValueError
        if value.memory_budget is None:
            raise ValueError
    except (AttributeError, TypeError, ValueError):
        return _internal_error(item_id, "spec and render plan dispatch mismatch")
    return None


def _completed_sampling_contract(
    sampled: SampledExplicitFunction | SampledParameterizedCurve,
    plan: RenderPlan,
    item_id: str,
) -> tuple[PlotItemDiagnostics, PlotSceneDiagnostics, tuple[str, ...]] | ErrorInfo:
    try:
        sampled.__post_init__()
        if sampled.item_id != item_id:
            raise ValueError
        item_plan = plan.item_plan
        memory_budget = plan.memory_budget
        if item_plan is None or memory_budget is None:
            raise ValueError
        actual_point_count = int(sampled.x.shape[0])
        sampled_segment_count = int(sampled.segment_ranges.shape[0])
        visible_segment_count = sampled.visible_segment_count
        if actual_point_count != item_plan.sample_count:
            raise ValueError
        if type(sampled) is SampledParameterizedCurve:
            if type(sampled.diagnostics) is not ParameterizedSamplingDiagnostics:
                raise TypeError
            if (
                sampled.diagnostics.sampled_point_count != actual_point_count
                or sampled.diagnostics.sampled_segment_count != sampled_segment_count
            ):
                raise ValueError
        warning_codes = _sampling_warning_codes(sampled.warnings)
        item_diagnostics = PlotItemDiagnostics(
            planned_sample_point_count=item_plan.sample_count,
            actual_sampled_point_count=actual_point_count,
            sampled_segment_count=sampled_segment_count,
            visible_segment_count=visible_segment_count,
        )
        scene_diagnostics = PlotSceneDiagnostics(
            total_planned_sample_point_count=item_plan.sample_count,
            total_actual_sampled_point_count=actual_point_count,
            approved_estimated_memory_bytes=memory_budget.total_bytes,
        )
    except (AttributeError, TypeError, ValueError):
        return _internal_error(item_id, "sampled result diagnostics contract failed")
    return item_diagnostics, scene_diagnostics, warning_codes


def _sampling_warning_codes(warnings: object) -> tuple[str, ...]:
    if type(warnings) is not tuple or not all(
        type(warning) is SamplingWarning for warning in warnings
    ):
        raise TypeError("sampling warnings must be an exact typed tuple")
    codes = tuple(warning.code.value for warning in warnings)
    if len(codes) != len(set(codes)):
        raise ValueError("sampling warning codes must not repeat")
    return codes


def _stable_unique(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _record_timing(
    timings: list[StageTiming],
    stage: str,
    started_ns: int,
) -> None:
    timings.append(
        StageTiming(
            stage=stage,
            elapsed_ms=(perf_counter_ns() - started_ns) / 1_000_000,
        ),
    )


def _is_cancelled(cancellation: CancellationProbe) -> bool:
    result = cancellation.is_cancelled()
    if type(result) is not bool:
        raise TypeError("CancellationProbe.is_cancelled() must return bool")
    return result


def _cancelled(request: PlotSceneRequest) -> PlotSceneResult:
    """Return the fully neutral sentinel suppressed by the Actor result gate."""

    return PlotSceneResult(
        request_id=request.request_id,
        scene_revision=request.scene_revision,
        success=False,
    )


def _failure(
    request: PlotSceneRequest,
    error: ErrorInfo,
    *,
    item: PlotItemRequest | None = None,
    normalized_input: str | None = None,
    plot_kind: PlotKind | None = None,
    concrete_plot_type: ConcretePlotType | None = None,
    resolved_viewport: ResolvedViewport | None = None,
    item_warnings: tuple[str, ...] = (),
    scene_warnings: tuple[str, ...] = (),
    item_diagnostics: PlotItemDiagnostics | None = None,
    scene_diagnostics: PlotSceneDiagnostics | None = None,
    elapsed_ms: tuple[StageTiming, ...] = (),
) -> PlotSceneResult:
    item_error = error
    item_results: tuple[PlotItemResult, ...] = ()
    if item is not None:
        item_error = _error_with_item_id(error, item.item_id)
        item_results = (
            PlotItemResult(
                item_id=item.item_id,
                success=False,
                normalized_input=normalized_input,
                plot_kind=plot_kind,
                concrete_plot_type=concrete_plot_type,
                diagnostics=item_diagnostics,
                style_key=item.style_key,
                warnings=item_warnings,
                error=item_error,
            ),
        )
    return PlotSceneResult(
        request_id=request.request_id,
        scene_revision=request.scene_revision,
        success=False,
        item_results=item_results,
        resolved_viewport=resolved_viewport,
        warnings=scene_warnings,
        error=item_error,
        elapsed_ms=elapsed_ms,
        diagnostics=scene_diagnostics,
    )


def _error_with_item_id(error: ErrorInfo, item_id: str) -> ErrorInfo:
    if error.item_id == item_id:
        return error
    if error.item_id is not None:
        return _internal_error(item_id, "stage error item identity mismatch")
    return ErrorInfo(
        code=error.code,
        user_message=error.user_message,
        technical_message=error.technical_message,
        item_id=item_id,
        field_name=error.field_name,
        source_location=error.source_location,
        recoverable=error.recoverable,
    )


def _internal_error(item_id: str, technical_message: str) -> ErrorInfo:
    return ErrorInfo(
        code=ErrorCode.INTERNAL_ERROR,
        user_message="绘图阶段内部契约无效，请重试。",
        technical_message=technical_message,
        item_id=item_id,
        recoverable=False,
    )


def _invalid_request(
    field_name: str,
    technical_message: str,
    *,
    item_id: str | None = None,
) -> ErrorInfo:
    return ErrorInfo(
        code=ErrorCode.INVALID_REQUEST,
        user_message="当前阶段只支持一个手动输入的绘图项。",
        technical_message=technical_message,
        item_id=item_id,
        field_name=field_name,
        recoverable=True,
    )


__all__ = ["SceneRenderExecutor"]
