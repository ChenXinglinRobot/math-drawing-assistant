"""Stage 8B single-function viewport resolution with a separate probe budget."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from math import isfinite

import numpy as np

from math_drawing_assistant.config import ApplicationLimits, DEFAULT_LIMITS
from math_drawing_assistant.engine.numeric_executor import (
    NumericExecutionCost,
    NumericExecutionResult,
    estimate_numeric_execution_cost,
    execute_explicit_function,
)
from math_drawing_assistant.engine.parameterized_budget import (
    estimate_line_exact_workspace_bytes,
    estimate_oval_exact_workspace_bytes,
)
from math_drawing_assistant.engine.oval_geometry import project_oval_geometry
from math_drawing_assistant.models.errors import (
    ErrorCode,
    ErrorInfo,
    ViewportWarning,
    ViewportWarningCode,
)
from math_drawing_assistant.models.plot_specs import (
    CircleSpec,
    EllipseSpec,
    ExplicitFunctionSpec,
    HyperbolaSpec,
    LineSpec,
    ParabolaSpec,
    PlotSceneSpec,
)
from math_drawing_assistant.models.state import (
    AspectRequest,
    ResolvedAspect,
    ViewportMode,
    ViewportSource,
)
from math_drawing_assistant.models.viewport import ResolvedViewport, ViewportRequest


@dataclass(frozen=True, slots=True)
class ViewportResolution:
    """One resolved viewport or one typed error, with an optional warning."""

    viewport: ResolvedViewport | None = None
    warning: ViewportWarning | None = None
    error: ErrorInfo | None = None

    def __post_init__(self) -> None:
        if (self.viewport is None) == (self.error is None):
            raise ValueError("ViewportResolution needs exactly one viewport or error.")
        if self.viewport is not None and type(self.viewport) is not ResolvedViewport:
            raise TypeError("viewport must be an exact ResolvedViewport or None.")
        if self.error is not None and type(self.error) is not ErrorInfo:
            raise TypeError("error must be an exact ErrorInfo or None.")
        if self.warning is not None and type(self.warning) is not ViewportWarning:
            raise TypeError("warning must be an exact ViewportWarning or None.")
        if self.error is not None and self.warning is not None:
            raise ValueError("ViewportResolution errors cannot carry warnings.")


_GEOMETRY_SPEC_TYPES = (
    LineSpec,
    CircleSpec,
    EllipseSpec,
    HyperbolaSpec,
    ParabolaSpec,
)
_SINGLE_ITEM_SPEC_TYPES = (ExplicitFunctionSpec, *_GEOMETRY_SPEC_TYPES)


def resolve_single_item_viewport(
    scene_spec: PlotSceneSpec,
    viewport_request: ViewportRequest,
    *,
    limits: ApplicationLimits = DEFAULT_LIMITS,
) -> ViewportResolution:
    """Resolve one exact Stage 13 item without building a render plan."""

    limits_error = _validate_limits(limits)
    if limits_error is not None:
        return _failure(limits_error)

    spec_or_error = _validated_single_spec(scene_spec, limits=limits)
    if isinstance(spec_or_error, ErrorInfo):
        return _failure(spec_or_error)
    spec = spec_or_error

    request_or_error = _validated_request(viewport_request)
    if isinstance(request_or_error, ErrorInfo):
        return _failure(request_or_error)
    request = request_or_error
    aspect = _resolved_aspect(spec, request.aspect_request)

    if request.mode is ViewportMode.MANUAL:
        return _resolve_manual(request, aspect=aspect, limits=limits)
    if type(spec) is ExplicitFunctionSpec:
        return _resolve_auto(spec, request, aspect=aspect, limits=limits)
    if type(spec) is LineSpec:
        return _resolve_auto_line(spec, request, aspect=aspect, limits=limits)
    if type(spec) in {CircleSpec, EllipseSpec}:
        return _resolve_auto_oval(spec, request, aspect=aspect, limits=limits)
    return _failure(
        _contract_error(
            "viewport_strategy",
            "automatic geometry viewport strategy is not implemented in stage 14B-1",
            item_id=spec.item_id,
        ),
    )


def resolve_single_explicit_viewport(
    scene_spec: PlotSceneSpec,
    viewport_request: ViewportRequest,
    *,
    limits: ApplicationLimits = DEFAULT_LIMITS,
) -> ViewportResolution:
    """Compatibility wrapper for the unified single-item viewport resolver."""

    return resolve_single_item_viewport(
        scene_spec,
        viewport_request,
        limits=limits,
    )


def _validate_limits(limits: object) -> ErrorInfo | None:
    if type(limits) is not ApplicationLimits:
        return _contract_error("viewport_limits", "resolver requires ApplicationLimits")
    try:
        limits.__post_init__()
    except (AttributeError, TypeError, ValueError):
        return _contract_error("viewport_limits", "viewport limits contract mismatch")
    return None


def _validated_single_spec(
    scene_spec: object,
    *,
    limits: ApplicationLimits,
) -> (
    ExplicitFunctionSpec
    | LineSpec
    | CircleSpec
    | EllipseSpec
    | HyperbolaSpec
    | ParabolaSpec
    | ErrorInfo
):
    if type(scene_spec) is not PlotSceneSpec:
        return _invalid_request("scene_spec", "resolver requires an exact PlotSceneSpec")
    if len(scene_spec.items) != 1:
        return _invalid_request("scene_spec", "resolver requires exactly one scene item")
    spec = scene_spec.items[0]
    if type(spec) not in _SINGLE_ITEM_SPEC_TYPES:
        return _invalid_request(
            "scene_spec",
            "resolver requires one exact supported Stage 13 item",
        )
    try:
        scene_spec.__post_init__()
        spec.__post_init__()
        if type(spec) is not ExplicitFunctionSpec:
            spec.coefficients.__post_init__()
            spec.provenance.__post_init__()
            spec.provenance.normalized_span.__post_init__()
            spec.provenance.source_span.__post_init__()
    except (AttributeError, TypeError, ValueError):
        return _contract_error("scene_spec", "single-item scene contract mismatch")
    spec_limits_version = (
        spec.limits_version
        if type(spec) is ExplicitFunctionSpec
        else spec.provenance.limits_version
    )
    if spec_limits_version != limits.version:
        return _contract_error("scene_spec", "spec limits version is not active")
    return spec


def _validated_request(viewport_request: object) -> ViewportRequest | ErrorInfo:
    if type(viewport_request) is not ViewportRequest:
        return _invalid_request(
            "viewport_request",
            "resolver requires an exact ViewportRequest",
        )
    if type(viewport_request.mode) is not ViewportMode:
        return _invalid_viewport("mode", "viewport mode is not published")
    if type(viewport_request.aspect_request) is not AspectRequest:
        return _invalid_viewport("aspect_request", "viewport aspect is not published")
    for name in ("x_min", "x_max", "y_min", "y_max"):
        value = getattr(viewport_request, name)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return _invalid_viewport(name, "viewport bound is not numeric")
        if not isfinite(float(value)):
            return _invalid_viewport(name, "viewport bound is not finite")
    return viewport_request


def _resolved_aspect(
    spec: ExplicitFunctionSpec | LineSpec | CircleSpec | EllipseSpec | HyperbolaSpec | ParabolaSpec,
    request: AspectRequest,
) -> ResolvedAspect:
    if request is AspectRequest.AUTO:
        return ResolvedAspect.AUTO
    if request is AspectRequest.EQUAL:
        return ResolvedAspect.EQUAL
    if request is not AspectRequest.DEFAULT:
        raise ValueError("aspect request is not published")
    if type(spec) in {ExplicitFunctionSpec, LineSpec}:
        return ResolvedAspect.AUTO
    return ResolvedAspect.EQUAL


def _resolve_manual(
    request: ViewportRequest,
    *,
    aspect: ResolvedAspect,
    limits: ApplicationLimits,
) -> ViewportResolution:
    bounds_or_error = _request_bounds(request, limits=limits)
    if isinstance(bounds_or_error, ErrorInfo):
        return _failure(bounds_or_error)
    x_min, x_max, y_min, y_max = bounds_or_error
    resolved_or_error = _resolved_viewport(
        x_min,
        x_max,
        y_min,
        y_max,
        aspect,
        ViewportSource.MANUAL,
        limits=limits,
    )
    if isinstance(resolved_or_error, ErrorInfo):
        return _failure(resolved_or_error)
    return ViewportResolution(viewport=resolved_or_error)


def _resolve_auto(
    spec: ExplicitFunctionSpec,
    request: ViewportRequest,
    *,
    aspect: ResolvedAspect,
    limits: ApplicationLimits,
) -> ViewportResolution:
    if request.y_min is not None or request.y_max is not None:
        return _failure(
            _invalid_viewport(
                "y_min" if request.y_min is not None else "y_max",
                "automatic viewports derive both y bounds",
            ),
        )

    x_bounds_or_error = _auto_x_bounds(request, limits=limits)
    if isinstance(x_bounds_or_error, ErrorInfo):
        return _failure(x_bounds_or_error)
    x_min, x_max, uses_default_x = x_bounds_or_error

    cost_or_error = estimate_numeric_execution_cost(spec, limits=limits)
    if isinstance(cost_or_error, ErrorInfo):
        return _failure(cost_or_error)
    if type(cost_or_error) is not NumericExecutionCost:
        return _failure(_contract_error("numeric_probe", "cost result type mismatch"))

    estimated_bytes = _estimate_probe_bytes(
        limits.viewport_probe_points,
        cost_or_error,
    )
    if estimated_bytes > limits.max_viewport_probe_bytes:
        return _failure(
            ErrorInfo(
                code=ErrorCode.VIEWPORT_PROBE_BUDGET_EXCEEDED,
                user_message="Automatic viewport probing exceeds the configured budget.",
                technical_message="probe byte estimate exceeds max_viewport_probe_bytes",
                item_id=spec.item_id,
                field_name="max_viewport_probe_bytes",
                recoverable=True,
            ),
        )

    try:
        x_values = np.linspace(
            x_min,
            x_max,
            limits.viewport_probe_points,
            dtype=np.float64,
        )
    except (MemoryError, TypeError, ValueError):
        return _failure(
            ErrorInfo(
                code=ErrorCode.VIEWPORT_PROBE_BUDGET_EXCEEDED,
                user_message="Automatic viewport probing cannot allocate its approved grid.",
                technical_message="approved probe grid allocation failed",
                item_id=spec.item_id,
                field_name="viewport_probe_points",
                recoverable=True,
            ),
        )

    execution = execute_explicit_function(spec, x_values, limits=limits)
    if isinstance(execution, ErrorInfo):
        return _failure(execution)
    if type(execution) is not NumericExecutionResult:
        return _failure(
            _contract_error("numeric_probe", "numeric result type mismatch"),
        )
    if execution.cost != cost_or_error:
        return _failure(
            _contract_error("numeric_probe", "numeric result cost mismatch"),
        )

    y_bounds_or_reason = _probe_y_bounds(
        execution,
        x_values,
        limits=limits,
    )
    if isinstance(y_bounds_or_reason, ErrorInfo):
        return _failure(y_bounds_or_reason)
    if isinstance(y_bounds_or_reason, str):
        return _fallback_resolution(
            request,
            aspect=aspect,
            x_min=x_min,
            x_max=x_max,
            uses_default_x=uses_default_x,
            item_id=spec.item_id,
            reason=y_bounds_or_reason,
            limits=limits,
        )

    y_min, y_max = y_bounds_or_reason
    resolved_or_error = _resolved_viewport(
        x_min,
        x_max,
        y_min,
        y_max,
        aspect,
        ViewportSource.AUTO_PROBE,
        limits=limits,
    )
    if isinstance(resolved_or_error, ErrorInfo):
        return _fallback_resolution(
            request,
            aspect=aspect,
            x_min=x_min,
            x_max=x_max,
            uses_default_x=uses_default_x,
            item_id=spec.item_id,
            reason="probe range is outside viewport limits",
            limits=limits,
        )
    return ViewportResolution(viewport=resolved_or_error)


def _resolve_auto_line(
    spec: LineSpec,
    request: ViewportRequest,
    *,
    aspect: ResolvedAspect,
    limits: ApplicationLimits,
) -> ViewportResolution:
    """Resolve one exact general line without probing or fallback."""

    if request.y_min is not None or request.y_max is not None:
        return _failure(
            _invalid_viewport(
                "y_min" if request.y_min is not None else "y_max",
                "automatic line viewports derive both y bounds",
            ),
        )
    x_bounds_or_error = _auto_x_bounds(request, limits=limits)
    if isinstance(x_bounds_or_error, ErrorInfo):
        return _failure(x_bounds_or_error)
    x_min, x_max, uses_default_x = x_bounds_or_error

    try:
        exact_workspace_bytes = estimate_line_exact_workspace_bytes(limits)
    except MemoryError:
        return _failure(_line_probe_budget_error(spec.item_id, "workspace estimate failed"))
    except (AttributeError, TypeError, ValueError):
        return _failure(
            _contract_error(
                "viewport_limits",
                "line exact-workspace contract mismatch",
                item_id=spec.item_id,
            ),
        )
    if exact_workspace_bytes > limits.max_viewport_probe_bytes:
        return _failure(
            _line_probe_budget_error(
                spec.item_id,
                "line exact workspace exceeds max_viewport_probe_bytes",
            ),
        )

    try:
        denominator = spec.d * spec.d + spec.e * spec.e
        anchor_x = Fraction(-spec.d * spec.f, denominator)
        anchor_y = Fraction(-spec.e * spec.f, denominator)
        if uses_default_x:
            x_exact = _bounded_exact_centered_range(
                anchor_x,
                Fraction(limits.default_auto_x_max - limits.default_auto_x_min),
                limits=limits,
            )
            y_exact = _bounded_exact_centered_range(
                anchor_y,
                Fraction(limits.fallback_auto_y_max - limits.fallback_auto_y_min),
                limits=limits,
            )
            if x_exact is None or y_exact is None:
                return _failure(
                    _numeric_range_error(
                        spec.item_id,
                        "line anchor cannot be enclosed by the configured viewport",
                    ),
                )
            x_values = _finite_fraction_range(x_exact)
            y_values = _finite_fraction_range(y_exact)
        else:
            x_values = (x_min, x_max)
            if spec.e == 0:
                y_exact = _bounded_exact_centered_range(
                    anchor_y,
                    Fraction(limits.fallback_auto_y_max - limits.fallback_auto_y_min),
                    limits=limits,
                )
            else:
                left_x = Fraction.from_float(x_min)
                right_x = Fraction.from_float(x_max)
                left_y = -(spec.d * left_x + spec.f) / spec.e
                right_y = -(spec.d * right_x + spec.f) / spec.e
                lower_y = min(left_y, right_y)
                upper_y = max(left_y, right_y)
                data_span = upper_y - lower_y
                padding = max(
                    Fraction(limits.viewport_absolute_padding),
                    data_span
                    * Fraction(limits.viewport_relative_padding_percent, 100),
                )
                chosen_span = max(
                    Fraction(limits.min_viewport_span),
                    Fraction(2 * limits.viewport_absolute_padding),
                    data_span + 2 * padding,
                )
                y_exact = _bounded_exact_centered_range(
                    (lower_y + upper_y) / 2,
                    chosen_span,
                    limits=limits,
                )
            if y_exact is None:
                return _failure(
                    _numeric_range_error(
                        spec.item_id,
                        "derived line y range is outside the supported numeric range",
                    ),
                )
            y_values = _finite_fraction_range(y_exact)
        if x_values is None or y_values is None:
            return _failure(
                _numeric_range_error(
                    spec.item_id,
                    "derived line viewport cannot be represented as finite float64",
                ),
            )
    except MemoryError:
        return _failure(_line_probe_budget_error(spec.item_id, "exact line workspace failed"))
    except (OverflowError, ZeroDivisionError):
        return _failure(
            _numeric_range_error(
                spec.item_id,
                "exact line viewport arithmetic is outside the supported range",
            ),
        )

    resolved_or_error = _resolved_viewport(
        x_values[0],
        x_values[1],
        y_values[0],
        y_values[1],
        aspect,
        ViewportSource.AUTO_GEOMETRY,
        limits=limits,
    )
    if isinstance(resolved_or_error, ErrorInfo):
        return _failure(
            _numeric_range_error(
                spec.item_id,
                "derived line viewport is outside the configured finite range",
            ),
        )
    return ViewportResolution(viewport=resolved_or_error)


def _resolve_auto_oval(
    spec: CircleSpec | EllipseSpec,
    request: ViewportRequest,
    *,
    aspect: ResolvedAspect,
    limits: ApplicationLimits,
) -> ViewportResolution:
    """Resolve one complete exact circle or ellipse without probing or fallback."""

    for name in ("x_min", "x_max", "y_min", "y_max"):
        if getattr(request, name) is not None:
            return _failure(
                _invalid_viewport(
                    name,
                    "automatic circle and ellipse viewports derive all four bounds",
                ),
            )
    try:
        exact_workspace_bytes = estimate_oval_exact_workspace_bytes(limits)
    except MemoryError:
        return _failure(_oval_probe_budget_error(spec.item_id, "workspace estimate failed"))
    except (AttributeError, TypeError, ValueError):
        return _failure(
            _contract_error(
                "viewport_limits",
                "oval exact-workspace contract mismatch",
                item_id=spec.item_id,
            ),
        )
    if exact_workspace_bytes > limits.max_viewport_probe_bytes:
        return _failure(
            _oval_probe_budget_error(
                spec.item_id,
                "oval exact workspace exceeds max_viewport_probe_bytes",
            ),
        )

    try:
        geometry = project_oval_geometry(spec)
        x_bounds = _fit_oval_axis(
            geometry.x_lower,
            geometry.x_upper,
            limits=limits,
        )
        y_bounds = _fit_oval_axis(
            geometry.y_lower,
            geometry.y_upper,
            limits=limits,
        )
    except MemoryError:
        return _failure(_oval_probe_budget_error(spec.item_id, "exact oval workspace failed"))
    except (AttributeError, OverflowError, TypeError, ValueError):
        return _failure(
            _oval_numeric_range_error(
                spec.item_id,
                "exact oval geometry cannot be represented as finite float64",
            ),
        )
    if x_bounds is None or y_bounds is None:
        return _failure(
            _oval_numeric_range_error(
                spec.item_id,
                "complete oval bounds cannot fit the configured viewport limits",
            ),
        )
    resolved_or_error = _resolved_viewport(
        x_bounds[0],
        x_bounds[1],
        y_bounds[0],
        y_bounds[1],
        aspect,
        ViewportSource.AUTO_GEOMETRY,
        limits=limits,
    )
    if isinstance(resolved_or_error, ErrorInfo):
        return _failure(
            _oval_numeric_range_error(
                spec.item_id,
                "derived oval viewport is outside the configured finite range",
            ),
        )
    return ViewportResolution(viewport=resolved_or_error)


def _fit_oval_axis(
    data_lower: float,
    data_upper: float,
    *,
    limits: ApplicationLimits,
) -> tuple[float, float] | None:
    """Pad one outward geometry range and translate at absolute limits without shrinking."""

    if not isfinite(data_lower) or not isfinite(data_upper) or data_lower >= data_upper:
        return None
    absolute_limit = float(limits.max_viewport_absolute_coordinate)
    if data_lower < -absolute_limit or data_upper > absolute_limit:
        return None
    data_span = data_upper - data_lower
    if not isfinite(data_span) or data_span <= 0.0:
        return None
    padding = max(
        float(limits.viewport_absolute_padding),
        data_span * float(limits.viewport_relative_padding_percent) / 100.0,
    )
    chosen_span = max(
        float(limits.min_viewport_span),
        2.0 * float(limits.viewport_absolute_padding),
        data_span + 2.0 * padding,
    )
    if not isfinite(chosen_span) or chosen_span > limits.max_viewport_span:
        return None
    center = data_lower + data_span / 2.0
    lower = center - chosen_span / 2.0
    upper = center + chosen_span / 2.0
    if lower < -absolute_limit:
        upper += -absolute_limit - lower
        lower = -absolute_limit
    if upper > absolute_limit:
        lower += absolute_limit - upper
        upper = absolute_limit
    lower = min(lower, data_lower)
    upper = max(upper, data_upper)
    span = upper - lower
    if (
        not isfinite(lower)
        or not isfinite(upper)
        or lower >= upper
        or lower < -absolute_limit
        or upper > absolute_limit
        or span < limits.min_viewport_span
        or span > limits.max_viewport_span
    ):
        return None
    return (lower, upper)


def _bounded_exact_centered_range(
    center: Fraction,
    span: Fraction,
    *,
    limits: ApplicationLimits,
) -> tuple[Fraction, Fraction] | None:
    """Center a fixed span and translate it at the absolute boundary without shrinking."""

    absolute_limit = Fraction(limits.max_viewport_absolute_coordinate)
    if span <= 0 or span > 2 * absolute_limit:
        return None
    if center < -absolute_limit or center > absolute_limit:
        return None
    lower = center - span / 2
    upper = center + span / 2
    if lower < -absolute_limit:
        shift = -absolute_limit - lower
        lower += shift
        upper += shift
    if upper > absolute_limit:
        shift = absolute_limit - upper
        lower += shift
        upper += shift
    if lower >= upper or lower < -absolute_limit or upper > absolute_limit:
        return None
    return (lower, upper)


def _finite_fraction_range(
    values: tuple[Fraction, Fraction],
) -> tuple[float, float] | None:
    try:
        lower = float(values[0])
        upper = float(values[1])
    except OverflowError:
        return None
    if not isfinite(lower) or not isfinite(upper) or lower >= upper:
        return None
    return (lower, upper)


def _request_bounds(
    request: ViewportRequest,
    *,
    limits: ApplicationLimits,
) -> tuple[float, float, float, float] | ErrorInfo:
    values = (request.x_min, request.x_max, request.y_min, request.y_max)
    if any(value is None for value in values):
        return _invalid_viewport(
            "bounds",
            "manual viewport requires four boundaries",
        )
    assert request.x_min is not None and request.x_max is not None
    assert request.y_min is not None and request.y_max is not None
    x_or_error = _validated_axis(
        request.x_min,
        request.x_max,
        "x",
        limits=limits,
    )
    if isinstance(x_or_error, ErrorInfo):
        return x_or_error
    y_or_error = _validated_axis(
        request.y_min,
        request.y_max,
        "y",
        limits=limits,
    )
    if isinstance(y_or_error, ErrorInfo):
        return y_or_error
    return (x_or_error[0], x_or_error[1], y_or_error[0], y_or_error[1])


def _auto_x_bounds(
    request: ViewportRequest,
    *,
    limits: ApplicationLimits,
) -> tuple[float, float, bool] | ErrorInfo:
    if (request.x_min is None) != (request.x_max is None):
        return _invalid_viewport(
            "x_min" if request.x_min is None else "x_max",
            "automatic viewport requires both x bounds or neither",
        )
    if request.x_min is None:
        x_or_error = _validated_axis(
            limits.default_auto_x_min,
            limits.default_auto_x_max,
            "x",
            limits=limits,
        )
        if isinstance(x_or_error, ErrorInfo):
            return x_or_error
        return (x_or_error[0], x_or_error[1], True)
    assert request.x_max is not None
    x_or_error = _validated_axis(
        request.x_min,
        request.x_max,
        "x",
        limits=limits,
    )
    if isinstance(x_or_error, ErrorInfo):
        return x_or_error
    return (x_or_error[0], x_or_error[1], False)


def _validated_axis(
    minimum: float | int,
    maximum: float | int,
    axis: str,
    *,
    limits: ApplicationLimits,
) -> tuple[float, float] | ErrorInfo:
    minimum_value = float(minimum)
    maximum_value = float(maximum)
    if not isfinite(minimum_value) or not isfinite(maximum_value):
        return _invalid_viewport(f"{axis}_bounds", "viewport bounds must be finite")
    if minimum_value >= maximum_value:
        return _invalid_viewport(
            f"{axis}_bounds",
            "viewport minimum must be smaller than maximum",
        )
    if max(abs(minimum_value), abs(maximum_value)) > (
        limits.max_viewport_absolute_coordinate
    ):
        return _invalid_viewport(
            f"{axis}_bounds",
            "viewport coordinate exceeds the configured limit",
        )
    span = maximum_value - minimum_value
    if span < limits.min_viewport_span or span > limits.max_viewport_span:
        return _invalid_viewport(
            f"{axis}_bounds",
            "viewport span is outside the configured limits",
        )
    return (minimum_value, maximum_value)


def _estimate_probe_bytes(points: int, cost: NumericExecutionCost) -> int:
    """Conservatively count all probe allocations before any NumPy array exists."""

    float64_bytes = np.dtype(np.float64).itemsize
    vector_bytes = points * float64_bytes
    input_grid = vector_bytes
    numeric_peak = vector_bytes * cost.max_live_float64_vectors
    retained_output = vector_bytes
    finite_mask = points
    finite_compression = vector_bytes
    quantile_workspace = vector_bytes * 2
    resolver_buffers = vector_bytes
    return (
        input_grid
        + numeric_peak
        + retained_output
        + finite_mask
        + finite_compression
        + quantile_workspace
        + resolver_buffers
    )


def _probe_y_bounds(
    execution: NumericExecutionResult,
    x_values: np.ndarray,
    *,
    limits: ApplicationLimits,
) -> tuple[float, float] | str | ErrorInfo:
    value = execution.value
    if type(value) is float:
        if not isfinite(value):
            return "constant result is not finite"
        return _minimum_span_range(value, limits=limits)
    if type(value) is not np.ndarray:
        return _contract_error("numeric_probe", "numeric result has an invalid value type")
    if (
        value.dtype != np.dtype(np.float64)
        or value.ndim != 1
        or value.shape != x_values.shape
        or value.flags.writeable
        or np.shares_memory(value, x_values)
    ):
        return _contract_error(
            "numeric_probe",
            "numeric result violates the vector ownership contract",
        )

    finite_mask = np.isfinite(value)
    finite_count = int(np.count_nonzero(finite_mask))
    if finite_count < limits.min_finite_probe_values:
        return "too few finite probe values"
    finite_values = value[finite_mask]
    try:
        quantiles = np.quantile(
            finite_values,
            (
                limits.viewport_quantile_low_percent / 100,
                limits.viewport_quantile_high_percent / 100,
            ),
            method="linear",
        )
        lower = float(quantiles[0])
        upper = float(quantiles[1])
    except (FloatingPointError, IndexError, TypeError, ValueError):
        return "robust probe statistics are unavailable"
    if not isfinite(lower) or not isfinite(upper) or lower > upper:
        return "robust probe statistics are unreliable"
    if lower == upper:
        return _minimum_span_range(lower, limits=limits)

    data_span = upper - lower
    padding = max(
        float(limits.viewport_absolute_padding),
        data_span * limits.viewport_relative_padding_percent / 100,
    )
    return _minimum_span_range(
        (lower + upper) / 2,
        span=data_span + 2 * padding,
        limits=limits,
    )


def _minimum_span_range(
    center: float,
    *,
    limits: ApplicationLimits,
    span: float | None = None,
) -> tuple[float, float] | str:
    chosen_span = max(
        float(limits.min_viewport_span),
        float(limits.viewport_absolute_padding) * 2,
        0.0 if span is None else span,
    )
    lower = center - chosen_span / 2
    upper = center + chosen_span / 2
    if not isfinite(lower) or not isfinite(upper) or lower >= upper:
        return "derived probe range is not finite"
    return (lower, upper)


def _fallback_resolution(
    request: ViewportRequest,
    *,
    aspect: ResolvedAspect,
    x_min: float,
    x_max: float,
    uses_default_x: bool,
    item_id: str,
    reason: str,
    limits: ApplicationLimits,
) -> ViewportResolution:
    if uses_default_x:
        fallback_x_min = float(limits.fallback_auto_x_min)
        fallback_x_max = float(limits.fallback_auto_x_max)
    else:
        fallback_x_min = x_min
        fallback_x_max = x_max
    resolved_or_error = _resolved_viewport(
        fallback_x_min,
        fallback_x_max,
        float(limits.fallback_auto_y_min),
        float(limits.fallback_auto_y_max),
        aspect,
        ViewportSource.AUTO_FALLBACK,
        limits=limits,
    )
    if isinstance(resolved_or_error, ErrorInfo):
        return _failure(resolved_or_error)
    return ViewportResolution(
        viewport=resolved_or_error,
        warning=ViewportWarning(
            code=ViewportWarningCode.AUTO_VIEWPORT_FALLBACK,
            user_message="Automatic viewport probing was unreliable; a safe fallback is used.",
            technical_message=reason,
            item_id=item_id,
        ),
    )


def _resolved_viewport(
    x_min: float,
    x_max: float,
    y_min: float,
    y_max: float,
    aspect: ResolvedAspect,
    source: ViewportSource,
    *,
    limits: ApplicationLimits,
) -> ResolvedViewport | ErrorInfo:
    x_or_error = _validated_axis(x_min, x_max, "x", limits=limits)
    if isinstance(x_or_error, ErrorInfo):
        return x_or_error
    y_or_error = _validated_axis(y_min, y_max, "y", limits=limits)
    if isinstance(y_or_error, ErrorInfo):
        return y_or_error
    try:
        return ResolvedViewport(
            x_min=x_or_error[0],
            x_max=x_or_error[1],
            y_min=y_or_error[0],
            y_max=y_or_error[1],
            aspect=aspect,
            source=source,
        )
    except (TypeError, ValueError):
        return _contract_error("resolved_viewport", "resolved viewport model rejected range")


def _failure(error: ErrorInfo) -> ViewportResolution:
    return ViewportResolution(error=error)


def _invalid_request(field_name: str, technical_message: str) -> ErrorInfo:
    return ErrorInfo(
        code=ErrorCode.INVALID_REQUEST,
        user_message="The viewport resolution request is invalid.",
        technical_message=technical_message,
        field_name=field_name,
        recoverable=True,
    )


def _invalid_viewport(field_name: str, technical_message: str) -> ErrorInfo:
    return ErrorInfo(
        code=ErrorCode.INVALID_VIEWPORT,
        user_message="Viewport bounds are invalid.",
        technical_message=technical_message,
        field_name=field_name,
        recoverable=True,
    )


def _contract_error(
    field_name: str,
    technical_message: str,
    *,
    item_id: str | None = None,
) -> ErrorInfo:
    return ErrorInfo(
        code=ErrorCode.INTERNAL_ERROR,
        user_message="The viewport resolution contract is invalid.",
        technical_message=technical_message,
        item_id=item_id,
        field_name=field_name,
        recoverable=False,
    )


def _line_probe_budget_error(item_id: str, technical_message: str) -> ErrorInfo:
    return ErrorInfo(
        code=ErrorCode.VIEWPORT_PROBE_BUDGET_EXCEEDED,
        user_message="Automatic line viewport calculation exceeds the configured budget.",
        technical_message=technical_message,
        item_id=item_id,
        field_name="max_viewport_probe_bytes",
        recoverable=True,
    )


def _oval_probe_budget_error(item_id: str, technical_message: str) -> ErrorInfo:
    return ErrorInfo(
        code=ErrorCode.VIEWPORT_PROBE_BUDGET_EXCEEDED,
        user_message="Automatic circle or ellipse viewport calculation exceeds the configured budget.",
        technical_message=technical_message,
        item_id=item_id,
        field_name="max_viewport_probe_bytes",
        recoverable=True,
    )


def _oval_numeric_range_error(item_id: str, technical_message: str) -> ErrorInfo:
    return ErrorInfo(
        code=ErrorCode.NUMERIC_RANGE_UNSUPPORTED,
        user_message="The circle or ellipse is outside the currently supported numeric range.",
        technical_message=technical_message,
        item_id=item_id,
        field_name="viewport_numeric_range",
        recoverable=True,
    )


def _numeric_range_error(item_id: str, technical_message: str) -> ErrorInfo:
    return ErrorInfo(
        code=ErrorCode.NUMERIC_RANGE_UNSUPPORTED,
        user_message="The line is outside the currently supported numeric range.",
        technical_message=technical_message,
        item_id=item_id,
        field_name="viewport_numeric_range",
        recoverable=True,
    )


__all__ = [
    "ViewportResolution",
    "resolve_single_item_viewport",
    "resolve_single_explicit_viewport",
]
