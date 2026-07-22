"""Build the single-item stage 8A explicit-function scene specification."""

from __future__ import annotations

from math_drawing_assistant.config import ApplicationLimits, DEFAULT_LIMITS
from math_drawing_assistant.models.errors import ErrorCode, ErrorInfo
from math_drawing_assistant.models.plot_specs import (
    ExplicitFunctionSpec,
    PlotSceneSpec,
    ValidatedExplicitExpression,
    _validate_validated_explicit_expression,
)
from math_drawing_assistant.models.requests import PlotItemRequest
from math_drawing_assistant.models.state import PlotKind


def build_explicit_function_spec(
    item_request: PlotItemRequest,
    validated_expression: ValidatedExplicitExpression,
    *,
    limits: ApplicationLimits = DEFAULT_LIMITS,
) -> ExplicitFunctionSpec | ErrorInfo:
    """Bind one validated expression to the identity held by its request."""

    if type(item_request) is not PlotItemRequest:
        raise TypeError("item_request must be an exact PlotItemRequest.")
    if not isinstance(limits, ApplicationLimits):
        raise TypeError("limits must be an ApplicationLimits value.")

    item_id = item_request.item_id
    if type(item_id) is not str or not item_id.strip():
        return _request_error(
            "绘图项标识无效，请重新提交。",
            "item_id is not a non-blank string",
            field_name="item_id",
        )
    if item_request.requested_plot_kind not in {
        PlotKind.AUTO,
        PlotKind.EXPLICIT_FUNCTION,
    }:
        return _request_error(
            "请求的绘图类型与已验证的显函数不一致。",
            "requested plot kind is incompatible with explicit function",
            item_id=item_id,
            field_name="requested_plot_kind",
        )

    try:
        checked = _validate_validated_explicit_expression(
            validated_expression,
            active_limits_version=limits.version,
        )
        if checked.plot_kind is not PlotKind.EXPLICIT_FUNCTION:
            raise ValueError("validated plot kind is not explicit function")
        return ExplicitFunctionSpec(
            item_id=item_id,
            validated_expression=checked,
        )
    except (AttributeError, TypeError, ValueError):
        return _contract_error(item_id)


def build_explicit_scene_spec(
    item_request: PlotItemRequest,
    validated_expression: ValidatedExplicitExpression,
    *,
    limits: ApplicationLimits = DEFAULT_LIMITS,
) -> PlotSceneSpec | ErrorInfo:
    """Build the authoritative one-item scene tuple for stage 8A."""

    item_spec = build_explicit_function_spec(
        item_request,
        validated_expression,
        limits=limits,
    )
    if isinstance(item_spec, ErrorInfo):
        return item_spec
    return PlotSceneSpec(items=(item_spec,))


def _request_error(
    user_message: str,
    technical_message: str,
    *,
    item_id: str | None = None,
    field_name: str,
) -> ErrorInfo:
    return ErrorInfo(
        code=ErrorCode.INVALID_REQUEST,
        user_message=user_message,
        technical_message=technical_message,
        item_id=item_id,
        field_name=field_name,
        recoverable=True,
    )


def _contract_error(item_id: str) -> ErrorInfo:
    return ErrorInfo(
        code=ErrorCode.INTERNAL_ERROR,
        user_message="已验证表达式契约无效，请重新提交公式。",
        technical_message="validated explicit expression contract mismatch",
        item_id=item_id,
        field_name="validated_expression",
        recoverable=False,
    )


__all__ = ["build_explicit_function_spec", "build_explicit_scene_spec"]
