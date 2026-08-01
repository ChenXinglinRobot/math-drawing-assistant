"""Production orchestration for the single-item M1 scene pipeline."""

from __future__ import annotations

from dataclasses import dataclass

from math_drawing_assistant.config import ApplicationLimits, DEFAULT_LIMITS
from math_drawing_assistant.engine.renderer import (
    RenderCancelled,
    render_explicit_png,
)
from math_drawing_assistant.engine.render_plan_builder import RenderPlanBuilder
from math_drawing_assistant.engine.samplers import (
    CancellationProbe,
    SampledExplicitFunction,
    SamplingCancelled,
    sample_explicit_function,
)
from math_drawing_assistant.engine.spec_builder import build_explicit_scene_spec
from math_drawing_assistant.engine.validators import analyze_explicit_function
from math_drawing_assistant.engine.viewport_resolver import (
    resolve_single_explicit_viewport,
)
from math_drawing_assistant.models.errors import ErrorCode, ErrorInfo
from math_drawing_assistant.models.requests import PlotItemRequest, PlotSceneRequest
from math_drawing_assistant.models.results import PlotItemResult, PlotSceneResult
from math_drawing_assistant.models.state import InputSource, PlotKind
from math_drawing_assistant.models.viewport import ResolvedViewport


@dataclass(frozen=True, slots=True)
class SceneRenderExecutor:
    """Execute the only production M1 scene path without depending on workers."""

    limits: ApplicationLimits = DEFAULT_LIMITS

    def execute(
        self,
        request: PlotSceneRequest,
        cancellation: CancellationProbe,
    ) -> PlotSceneResult:
        """Validate, plan, sample, and render one explicit-function request."""

        item_or_error = _validated_m1_item(request)
        if isinstance(item_or_error, ErrorInfo):
            item = request.items[0] if len(request.items) == 1 else None
            return _failure(request, item_or_error, item=item)
        item = item_or_error

        if _is_cancelled(cancellation):
            return _cancelled(request)

        validated_or_error = analyze_explicit_function(
            item.input_text,
            limits=self.limits,
        )
        if isinstance(validated_or_error, ErrorInfo):
            return _failure(request, validated_or_error, item=item)
        validated = validated_or_error

        if _is_cancelled(cancellation):
            return _cancelled(request)

        scene_or_error = build_explicit_scene_spec(
            item,
            validated,
            limits=self.limits,
        )
        if isinstance(scene_or_error, ErrorInfo):
            return _failure(
                request,
                scene_or_error,
                item=item,
                normalized_input=validated.normalized_input,
                plot_kind=validated.plot_kind,
            )
        scene_spec = scene_or_error

        if _is_cancelled(cancellation):
            return _cancelled(request)

        viewport_resolution = resolve_single_explicit_viewport(
            scene_spec,
            request.viewport,
            limits=self.limits,
        )
        if viewport_resolution.error is not None:
            return _failure(
                request,
                viewport_resolution.error,
                item=item,
                normalized_input=validated.normalized_input,
                plot_kind=validated.plot_kind,
            )
        resolved_viewport = viewport_resolution.viewport
        if type(resolved_viewport) is not ResolvedViewport:
            raise TypeError("viewport resolver returned no exact ResolvedViewport")
        viewport_warnings = (
            ()
            if viewport_resolution.warning is None
            else (viewport_resolution.warning.code.value,)
        )

        if _is_cancelled(cancellation):
            return _cancelled(request)

        plan_or_error = RenderPlanBuilder(limits=self.limits).build(
            scene_spec,
            resolved_viewport,
            image_width=request.image_width,
            image_height=request.image_height,
            dpi=request.dpi,
            show_grid=request.show_grid,
            show_legend=request.show_legend,
        )
        if isinstance(plan_or_error, ErrorInfo):
            return _failure(
                request,
                plan_or_error,
                item=item,
                normalized_input=validated.normalized_input,
                plot_kind=validated.plot_kind,
                resolved_viewport=resolved_viewport,
                warnings=viewport_warnings,
            )
        plan = plan_or_error

        if _is_cancelled(cancellation):
            return _cancelled(request)

        sampling_outcome = sample_explicit_function(
            plan,
            cancellation_probe=cancellation,
        )
        if type(sampling_outcome) is SamplingCancelled:
            return _cancelled(request)
        if isinstance(sampling_outcome, ErrorInfo):
            return _failure(
                request,
                sampling_outcome,
                item=item,
                normalized_input=validated.normalized_input,
                plot_kind=validated.plot_kind,
                resolved_viewport=resolved_viewport,
                warnings=viewport_warnings,
            )
        if type(sampling_outcome) is not SampledExplicitFunction:
            raise TypeError("sampler returned an unsupported outcome")
        sampling_warnings = tuple(
            warning.code.value for warning in sampling_outcome.warnings
        )
        all_warnings = viewport_warnings + sampling_warnings

        if _is_cancelled(cancellation):
            return _cancelled(request)

        render_outcome = render_explicit_png(
            plan,
            sampling_outcome,
            cancellation_probe=cancellation,
        )
        if type(render_outcome) is RenderCancelled:
            return _cancelled(request)
        if isinstance(render_outcome, ErrorInfo):
            return _failure(
                request,
                render_outcome,
                item=item,
                normalized_input=validated.normalized_input,
                plot_kind=validated.plot_kind,
                resolved_viewport=resolved_viewport,
                warnings=all_warnings,
            )
        if type(render_outcome) is not bytes:
            raise TypeError("renderer returned an unsupported outcome")

        if _is_cancelled(cancellation):
            return _cancelled(request)

        item_result = PlotItemResult(
            item_id=item.item_id,
            success=True,
            normalized_input=validated.normalized_input,
            plot_kind=validated.plot_kind,
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
            warnings=all_warnings,
        )


def _validated_m1_item(
    request: PlotSceneRequest,
) -> PlotItemRequest | ErrorInfo:
    if type(request) is not PlotSceneRequest:
        raise TypeError("request must be an exact PlotSceneRequest")
    if type(request.items) is not tuple:
        return _invalid_request("items", "scene items must be an exact tuple")
    if not request.items:
        return _invalid_request("items", "M1 scene is empty")
    if len(request.items) != 1:
        return _invalid_request("items", "M1 requires exactly one scene item")

    item = request.items[0]
    if type(item) is not PlotItemRequest:
        return _invalid_request("items", "M1 item contract is not exact")
    if item.input_source is not InputSource.MANUAL:
        return _invalid_request(
            "input_source",
            "M1 accepts manual text input only",
            item_id=item.item_id,
        )
    if item.requested_plot_kind not in {
        PlotKind.AUTO,
        PlotKind.EXPLICIT_FUNCTION,
    }:
        return _invalid_request(
            "requested_plot_kind",
            "M1 accepts only auto or explicit-function requests",
            item_id=item.item_id,
        )
    return item


def _is_cancelled(cancellation: CancellationProbe) -> bool:
    result = cancellation.is_cancelled()
    if type(result) is not bool:
        raise TypeError("CancellationProbe.is_cancelled() must return bool")
    return result


def _cancelled(request: PlotSceneRequest) -> PlotSceneResult:
    """Return the error-free sentinel suppressed by the Actor result gate."""

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
    resolved_viewport: ResolvedViewport | None = None,
    warnings: tuple[str, ...] = (),
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
                style_key=item.style_key,
                warnings=warnings,
                error=item_error,
            ),
        )
    return PlotSceneResult(
        request_id=request.request_id,
        scene_revision=request.scene_revision,
        success=False,
        item_results=item_results,
        resolved_viewport=resolved_viewport,
        warnings=warnings,
        error=item_error,
    )


def _error_with_item_id(error: ErrorInfo, item_id: str) -> ErrorInfo:
    if error.item_id is not None:
        return error
    return ErrorInfo(
        code=error.code,
        user_message=error.user_message,
        technical_message=error.technical_message,
        item_id=item_id,
        field_name=error.field_name,
        source_location=error.source_location,
        recoverable=error.recoverable,
    )


def _invalid_request(
    field_name: str,
    technical_message: str,
    *,
    item_id: str | None = None,
) -> ErrorInfo:
    return ErrorInfo(
        code=ErrorCode.INVALID_REQUEST,
        user_message="当前阶段只支持一个手动输入的显函数绘图项。",
        technical_message=technical_message,
        item_id=item_id,
        field_name=field_name,
        recoverable=True,
    )


__all__ = ["SceneRenderExecutor"]
