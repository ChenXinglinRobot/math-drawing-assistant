"""Qt-independent PNG rendering for one approved explicit-function plan."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import TypeAlias

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from math_drawing_assistant.config import DEFAULT_LIMITS
from math_drawing_assistant.engine.samplers import (
    CancellationProbe,
    SampledExplicitFunction,
    SamplingCancelled,
    SamplingOutcome,
    _sampled_explicit_function_matches_approved_plan,
)
from math_drawing_assistant.models.errors import ErrorCode, ErrorInfo
from math_drawing_assistant.models.plot_specs import ExplicitFunctionSpec, PlotSceneSpec
from math_drawing_assistant.models.render_plan import (
    ExplicitRenderItemPlan,
    RenderPlan,
    validate_approved_render_plan,
)
from math_drawing_assistant.models.state import ResolvedAspect


_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_CURVE_COLOR = "#1f77b4"
_CURVE_LINE_WIDTH = 1.5


@dataclass(frozen=True, slots=True)
class RenderCancelled:
    """Independent cancellation outcome for one rendering item."""

    item_id: str

    def __post_init__(self) -> None:
        if type(self.item_id) is not str or not self.item_id.strip():
            raise ValueError("item_id must be a non-empty string.")


RenderOutcome: TypeAlias = bytes | RenderCancelled | ErrorInfo


def render_explicit_png(
    plan: RenderPlan,
    sampling_outcome: SamplingOutcome,
    *,
    cancellation_probe: CancellationProbe | None = None,
) -> RenderOutcome:
    """Render one formally sampled explicit function to owned PNG bytes."""

    # Approval is intentionally the first operation. In particular, no
    # Matplotlib object or BytesIO exists before this check succeeds.
    try:
        approved_plan = validate_approved_render_plan(plan)
    except MemoryError:
        return _resource_error(
            None,
            "approved render-plan validation allocation failed",
        )
    except (AttributeError, TypeError, ValueError):
        return _internal_error(None, "approved render-plan validation failed")

    # Formal approval guarantees this exact scalar item plan. Read only its
    # identity here so typed upstream outcomes remain the second operation.
    item_plan = approved_plan.item_plan
    if type(item_plan) is not ExplicitRenderItemPlan:
        return _internal_error(None, "approved render-plan item contract failed")
    item_id = item_plan.item_id

    if isinstance(sampling_outcome, ErrorInfo):
        if (
            sampling_outcome.item_id is not None
            and sampling_outcome.item_id != item_id
        ):
            return _internal_error(item_id, "sampling error item identity mismatch")
        return sampling_outcome

    if type(sampling_outcome) is SamplingCancelled:
        if sampling_outcome.item_id != item_id:
            return _internal_error(
                item_id,
                "sampling cancellation item identity mismatch",
            )
        return RenderCancelled(item_id)

    if type(sampling_outcome) is not SampledExplicitFunction:
        return _internal_error(item_id, "sampling outcome type mismatch")
    sampled = sampling_outcome

    context_or_error = _validated_render_context(approved_plan)
    if isinstance(context_or_error, ErrorInfo):
        return context_or_error
    context_item_id, spec, item_plan = context_or_error
    if context_item_id != item_id:
        return _internal_error(item_id, "approved plan item identity mismatch")

    sample_error = _validate_sampled_contract(
        approved_plan,
        sampled,
        item_id=item_id,
        item_plan=item_plan,
    )
    if sample_error is not None:
        return sample_error

    memory_budget = approved_plan.memory_budget
    if memory_budget is None:
        return _internal_error(item_id, "approved render-plan memory budget is missing")
    approved_png_limit = min(
        memory_budget.png_buffer_reserve_bytes,
        memory_budget.png_copy_bytes,
    )

    cancelled_or_error = _poll_cancellation(
        cancellation_probe,
        item_id=item_id,
    )
    if isinstance(cancelled_or_error, ErrorInfo):
        return cancelled_or_error
    if cancelled_or_error:
        return RenderCancelled(item_id)

    figure: Figure | None = None
    canvas: FigureCanvasAgg | None = None
    axes: object | None = None
    buffer: BytesIO | None = None
    try:
        figure = Figure(
            figsize=(
                approved_plan.image_width / approved_plan.dpi,
                approved_plan.image_height / approved_plan.dpi,
            ),
            dpi=approved_plan.dpi,
        )
        canvas = FigureCanvasAgg(figure)
        axes = figure.add_subplot(1, 1, 1)
        buffer = BytesIO()

        viewport = approved_plan.resolved_viewport
        axes.set_autoscale_on(False)
        axes.set_xlim(viewport.x_min, viewport.x_max)
        axes.set_ylim(viewport.y_min, viewport.y_max)
        if viewport.aspect is ResolvedAspect.AUTO:
            axes.set_aspect("auto")
        elif viewport.aspect is ResolvedAspect.EQUAL:
            axes.set_aspect("equal", adjustable="box")
        else:
            return _internal_error(item_id, "resolved viewport aspect mismatch")

        _configure_axes(axes, approved_plan)

        for segment_index, (start_value, stop_value) in enumerate(
            sampled.segment_ranges,
        ):
            cancelled_or_error = _poll_cancellation(
                cancellation_probe,
                item_id=item_id,
            )
            if isinstance(cancelled_or_error, ErrorInfo):
                return cancelled_or_error
            if cancelled_or_error:
                return RenderCancelled(item_id)

            start = int(start_value)
            stop = int(stop_value)
            label = (
                spec.normalized_input
                if approved_plan.show_legend and segment_index == 0
                else None
            )
            axes.plot(
                sampled.x[start:stop],
                sampled.y[start:stop],
                color=_CURVE_COLOR,
                linewidth=_CURVE_LINE_WIDTH,
                label=label,
            )

        # Artist creation must never become an implicit viewport resolver.
        axes.set_xlim(viewport.x_min, viewport.x_max)
        axes.set_ylim(viewport.y_min, viewport.y_max)
        if approved_plan.show_legend:
            axes.legend(loc="upper right")

        cancelled_or_error = _poll_cancellation(
            cancellation_probe,
            item_id=item_id,
        )
        if isinstance(cancelled_or_error, ErrorInfo):
            return cancelled_or_error
        if cancelled_or_error:
            return RenderCancelled(item_id)

        # Agg's direct PNG path draws and serializes this task-private full
        # canvas.  Unlike FigureCanvasBase.print_figure, it does not consult
        # savefig.bbox or perform a tight-bounding-box layout pass.
        canvas.print_png(buffer)

        cancelled_or_error = _poll_cancellation(
            cancellation_probe,
            item_id=item_id,
        )
        if isinstance(cancelled_or_error, ErrorInfo):
            return cancelled_or_error
        if cancelled_or_error:
            return RenderCancelled(item_id)

        buffer.seek(0, 2)
        actual_png_bytes = buffer.tell()
        if actual_png_bytes > approved_png_limit:
            return _resource_error(
                item_id,
                "encoded PNG exceeds approved plan limit",
            )
        if not _png_header_matches_plan(buffer, approved_plan):
            return _render_error(item_id, "PNG header or dimensions mismatch")

        png_bytes = buffer.getvalue()

        cancelled_or_error = _poll_cancellation(
            cancellation_probe,
            item_id=item_id,
        )
        if isinstance(cancelled_or_error, ErrorInfo):
            return cancelled_or_error
        if cancelled_or_error:
            return RenderCancelled(item_id)
        return png_bytes
    except MemoryError:
        return _resource_error(item_id, "MemoryError: rendering allocation failed")
    except Exception as exc:
        return _render_error(
            item_id,
            f"{type(exc).__name__}: Matplotlib or PNG encoding failed",
        )
    finally:
        if buffer is not None:
            buffer.close()
        if axes is not None:
            try:
                axes.clear()
            except Exception:
                pass
        if figure is not None:
            try:
                figure.clear()
            except Exception:
                pass
        axes = None
        canvas = None
        figure = None
        buffer = None


def _validated_render_context(
    plan: RenderPlan,
) -> tuple[str, ExplicitFunctionSpec, ExplicitRenderItemPlan] | ErrorInfo:
    try:
        scene = plan.scene_spec
        if type(scene) is not PlotSceneSpec or len(scene.items) != 1:
            raise ValueError("scene must contain one exact explicit item")
        spec = scene.items[0]
        if type(spec) is not ExplicitFunctionSpec:
            raise TypeError("scene item must be an exact explicit function")
        item_plan = plan.item_plan
        if type(item_plan) is not ExplicitRenderItemPlan:
            raise TypeError("explicit render item plan is missing")
        if item_plan.item_id != spec.item_id:
            raise ValueError("plan item identities do not match")
        if plan.limits_version != DEFAULT_LIMITS.version:
            raise ValueError("render plan limits version is not active")
        if plan.show_legend and (
            type(spec.normalized_input) is not str
            or not spec.normalized_input.strip()
        ):
            raise ValueError("legend label is unavailable")
        return spec.item_id, spec, item_plan
    except MemoryError:
        return _resource_error(
            None,
            "render context construction allocation failed",
        )
    except (AttributeError, TypeError, ValueError):
        return _internal_error(None, "approved render-plan item contract failed")


def _validate_sampled_contract(
    plan: RenderPlan,
    sampled: SampledExplicitFunction,
    *,
    item_id: str,
    item_plan: ExplicitRenderItemPlan,
) -> ErrorInfo | None:
    try:
        if not _sampled_explicit_function_matches_approved_plan(sampled, plan):
            raise ValueError("sampled plan contract does not match")
        if sampled.item_id != item_id or item_plan.item_id != item_id:
            raise ValueError("sampled item identity does not match")
        sampled.__post_init__()
        if sampled.x.shape[0] != item_plan.sample_count:
            raise ValueError("sample count does not match approved plan")
        if sampled.y.shape[0] != sampled.x.shape[0]:
            raise ValueError("sample vector lengths do not match")
        if sampled.segment_ranges.shape[0] > item_plan.max_segment_count:
            raise ValueError("sample segment count exceeds approved plan")
        if sampled.segment_ranges.shape[0] == 0:
            return _no_visible_error(item_id)
        for start_value, stop_value in sampled.segment_ranges:
            start = int(start_value)
            stop = int(stop_value)
            if start < 0 or stop > sampled.x.shape[0] or stop - start < 2:
                raise ValueError("sample segment range is invalid")
    except MemoryError:
        return _resource_error(
            item_id,
            "sampled provenance validation allocation failed",
        )
    except (AttributeError, IndexError, TypeError, ValueError):
        return _internal_error(item_id, "sampled result contract validation failed")
    return None


def _configure_axes(axes: object, plan: RenderPlan) -> None:
    """Apply the minimal fixed stage-9 axes and layout policy."""

    viewport = plan.resolved_viewport
    figure = axes.get_figure()
    figure.subplots_adjust(left=0.12, right=0.94, bottom=0.12, top=0.94)

    axes.set_xlabel("x")
    axes.set_ylabel("y", rotation=0)
    axes.xaxis.set_label_coords(1.015, -0.04)
    axes.yaxis.set_label_coords(-0.04, 1.015)
    axes.grid(plan.show_grid)
    axes.set_axisbelow(True)

    y_axis_position: tuple[str, float]
    if viewport.x_min <= 0.0 <= viewport.x_max:
        y_axis_position = ("data", 0.0)
    elif viewport.x_min > 0.0:
        y_axis_position = ("axes", 0.0)
    else:
        y_axis_position = ("axes", 1.0)

    x_axis_position: tuple[str, float]
    if viewport.y_min <= 0.0 <= viewport.y_max:
        x_axis_position = ("data", 0.0)
    elif viewport.y_min > 0.0:
        x_axis_position = ("axes", 0.0)
    else:
        x_axis_position = ("axes", 1.0)

    axes.spines["left"].set_position(y_axis_position)
    axes.spines["bottom"].set_position(x_axis_position)
    axes.spines["right"].set_visible(False)
    axes.spines["top"].set_visible(False)
    axes.yaxis.set_ticks_position("left")
    axes.xaxis.set_ticks_position("bottom")


def _png_header_matches_plan(buffer: BytesIO, plan: RenderPlan) -> bool:
    position = buffer.tell()
    try:
        buffer.seek(0)
        header = buffer.read(24)
    finally:
        buffer.seek(position)
    return (
        len(header) == 24
        and header[:8] == _PNG_SIGNATURE
        and header[12:16] == b"IHDR"
        and int.from_bytes(header[16:20], "big") == plan.image_width
        and int.from_bytes(header[20:24], "big") == plan.image_height
    )


def _poll_cancellation(
    probe: CancellationProbe | None,
    *,
    item_id: str,
) -> bool | ErrorInfo:
    if probe is None:
        return False
    try:
        result = probe.is_cancelled()
    except Exception:
        return _internal_error(item_id, "cancellation probe raised unexpectedly")
    if type(result) is not bool:
        return _internal_error(item_id, "cancellation probe did not return bool")
    return result


def _internal_error(item_id: str | None, technical_message: str) -> ErrorInfo:
    return ErrorInfo(
        code=ErrorCode.INTERNAL_ERROR,
        user_message="渲染契约无效，请重新提交公式。",
        technical_message=technical_message,
        item_id=item_id,
        field_name="rendering",
        recoverable=False,
    )


def _no_visible_error(item_id: str) -> ErrorInfo:
    return ErrorInfo(
        code=ErrorCode.NO_VISIBLE_CURVE,
        user_message="当前视口内没有可绘制曲线，请调整坐标范围。",
        technical_message="no drawable sampled segment",
        item_id=item_id,
        field_name="rendering_visibility",
        recoverable=True,
    )


def _resource_error(item_id: str | None, technical_message: str) -> ErrorInfo:
    return ErrorInfo(
        code=ErrorCode.RESOURCE_LIMIT_EXCEEDED,
        user_message="渲染结果超过资源限制，请缩小输出规模后重试。",
        technical_message=technical_message,
        item_id=item_id,
        field_name="png_bytes",
        recoverable=True,
    )


def _render_error(item_id: str, technical_message: str) -> ErrorInfo:
    return ErrorInfo(
        code=ErrorCode.RENDER_FAILED,
        user_message="图像渲染失败，请重试。",
        technical_message=technical_message,
        item_id=item_id,
        field_name="rendering",
        recoverable=True,
    )


__all__ = [
    "RenderCancelled",
    "RenderOutcome",
    "render_explicit_png",
]
