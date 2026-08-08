"""Unified single-item analyzer for explicit functions and equations."""

from __future__ import annotations

from math_drawing_assistant.config.limits import ApplicationLimits, DEFAULT_LIMITS
from math_drawing_assistant.engine.equation_classifier import (
    EquationGeometryError,
    EquationGeometryFailureKind,
    LineGeometry,
    classify_equation_geometry,
)
from math_drawing_assistant.engine.equation_polynomial import (
    EquationPolynomialError,
    PolynomialFailureKind,
    canonicalize_equation,
)
from math_drawing_assistant.engine.equation_spec_builder import (
    EquationSpecBuilderError,
    build_equation_spec,
)
from math_drawing_assistant.engine.equation_splitter import split_equation
from math_drawing_assistant.engine.equation_validator import (
    EquationValidationError,
    ValidatedEquationInput,
    _validate_validated_equation_input,
    validate_equation_candidate,
)
from math_drawing_assistant.engine.normalizer import NormalizedInput, normalize_input
from math_drawing_assistant.engine.parser import parse_input
from math_drawing_assistant.engine.plot_classifier import (
    EquationCandidate,
    ExplicitFunctionCandidate,
    LegacyEquationRejectionReason,
    classify_plot_route,
)
from math_drawing_assistant.engine.spec_builder import build_explicit_function_spec
from math_drawing_assistant.engine.tokenizer import tokenize
from math_drawing_assistant.engine.validators import (
    _issue_validated_explicit_expression,
    validate_explicit_candidate,
)
from math_drawing_assistant.models.errors import ErrorCode, ErrorInfo, SourceSpan
from math_drawing_assistant.models.plot_specs import PlotItemSpec
from math_drawing_assistant.models.requests import PlotItemRequest
from math_drawing_assistant.models.state import InputSource, PlotKind


def analyze_plot_item(
    request: PlotItemRequest,
    *,
    limits: ApplicationLimits = DEFAULT_LIMITS,
) -> PlotItemSpec | ErrorInfo:
    """Analyze one exact item request through the shared typed front end."""

    if type(request) is not PlotItemRequest:
        raise TypeError("request must be an exact PlotItemRequest.")
    if not isinstance(limits, ApplicationLimits):
        raise TypeError("limits must be an ApplicationLimits value.")

    request_error = _validate_request(request)
    if request_error is not None:
        return request_error

    normalized = normalize_input(request.input_text, limits=limits)
    if isinstance(normalized, ErrorInfo):
        return _bind_item_id(normalized, request.item_id)
    tokens = tokenize(normalized, limits=limits)
    if isinstance(tokens, ErrorInfo):
        return _bind_item_id(tokens, request.item_id)
    split = split_equation(tokens)
    if isinstance(split, ErrorInfo):
        return _bind_item_id(split, request.item_id)
    parsed = parse_input(split, limits=limits)
    if isinstance(parsed, ErrorInfo):
        return _bind_item_id(parsed, request.item_id)
    route = classify_plot_route(parsed)

    if isinstance(route, ExplicitFunctionCandidate):
        validation = validate_explicit_candidate(route, limits=limits)
        if isinstance(validation, ErrorInfo):
            return _bind_item_id(validation, request.item_id)
        try:
            validated_expression = _issue_validated_explicit_expression(
                validation,
                normalized,
                limits=limits,
            )
        except (TypeError, ValueError):
            return _internal_error(
                request.item_id,
                "validated explicit expression issuance failed",
                field_name="validated_expression",
            )
        built = build_explicit_function_spec(
            request,
            validated_expression,
            limits=limits,
        )
        if isinstance(built, ErrorInfo):
            return _bind_item_id(built, request.item_id)
        return built

    if type(route) is not EquationCandidate:
        return _internal_error(
            request.item_id,
            "plot classifier returned an unknown typed route",
        )
    return _analyze_equation_route(request, route, normalized, limits=limits)


def _analyze_equation_route(
    request: PlotItemRequest,
    candidate: EquationCandidate,
    normalized: NormalizedInput,
    *,
    limits: ApplicationLimits,
) -> PlotItemSpec | ErrorInfo:
    try:
        validated = validate_equation_candidate(
            candidate,
            normalized,
            limits=limits,
        )
    except EquationValidationError as error:
        return _equation_validation_error(
            error,
            request.item_id,
            fallback=candidate.legacy_source_span,
        )
    except TypeError:
        return _internal_error(
            request.item_id,
            "equation validation boundary contract mismatch",
        )

    try:
        validated = _validate_validated_equation_input(validated, limits=limits)
    except EquationValidationError as error:
        return _equation_validation_error(
            error,
            request.item_id,
            fallback=_validated_source_span(validated, candidate.legacy_source_span),
        )
    except (TypeError, ValueError):
        return _internal_error(
            request.item_id,
            "validated equation receipt contract mismatch",
        )

    try:
        coefficients = canonicalize_equation(
            validated.parsed_input.left,
            validated.parsed_input.right,
            limits=limits,
        )
    except EquationPolynomialError as error:
        return _equation_polynomial_error(error, request.item_id)

    try:
        geometry = classify_equation_geometry(coefficients, limits=limits)
    except EquationGeometryError as error:
        return _equation_geometry_error(
            error,
            request.item_id,
            validated.provenance.source_span,
        )

    try:
        spec = build_equation_spec(
            request.item_id,
            validated,
            coefficients,
            geometry,
            limits=limits,
        )
    except EquationValidationError as error:
        return _equation_validation_error(
            error,
            request.item_id,
            fallback=validated.provenance.source_span,
        )
    except (EquationSpecBuilderError, TypeError):
        return _internal_error(
            request.item_id,
            "equation specification builder contract mismatch",
            field_name="validated_equation",
        )

    requested = request.requested_plot_kind
    if requested is PlotKind.AUTO:
        return spec
    if requested is PlotKind.EXPLICIT_FUNCTION:
        return _legacy_equation_error(candidate, request.item_id)
    if requested is PlotKind.LINE_EQUATION:
        if type(geometry) is LineGeometry:
            return spec
        return _requested_kind_error(request.item_id)
    if requested is PlotKind.CONIC_EQUATION:
        if type(geometry) is not LineGeometry:
            return spec
        return _requested_kind_error(request.item_id)
    return _internal_error(
        request.item_id,
        "request plot kind changed after boundary validation",
    )


def _validate_request(request: PlotItemRequest) -> ErrorInfo | None:
    item_id = request.item_id
    if type(item_id) is not str or not item_id.strip():
        return _invalid_request(
            None,
            "绘图项标识无效，请重新提交。",
            "item_id is not a non-blank string",
            "item_id",
        )
    if not isinstance(request.input_text, str):
        return _invalid_request(
            item_id,
            "公式输入无效，请重新提交。",
            "input_text is not a string",
            "input_text",
        )
    if not isinstance(request.input_source, InputSource):
        return _invalid_request(
            item_id,
            "输入来源无效，请重新提交。",
            "input_source is not a published value",
            "input_source",
        )
    if not isinstance(request.requested_plot_kind, PlotKind):
        return _invalid_request(
            item_id,
            "请求的绘图类型无效，请重新提交。",
            "requested_plot_kind is not a published value",
            "requested_plot_kind",
        )
    if isinstance(request.display_order, bool) or not isinstance(
        request.display_order,
        int,
    ):
        return _invalid_request(
            item_id,
            "绘图顺序无效，请重新提交。",
            "display_order is not an integer",
            "display_order",
        )
    if request.display_order < 0:
        return _invalid_request(
            item_id,
            "绘图顺序无效，请重新提交。",
            "display_order is negative",
            "display_order",
        )
    if request.style_key is not None and (
        not isinstance(request.style_key, str) or not request.style_key
    ):
        return _invalid_request(
            item_id,
            "绘图样式无效，请重新提交。",
            "style_key is not a non-empty string or None",
            "style_key",
        )
    return None


def _bind_item_id(error: ErrorInfo, item_id: str) -> ErrorInfo:
    return ErrorInfo(
        code=error.code,
        user_message=error.user_message,
        technical_message=error.technical_message,
        item_id=item_id,
        field_name=error.field_name,
        source_location=error.source_location,
        recoverable=error.recoverable,
    )


def _legacy_equation_error(
    candidate: EquationCandidate,
    item_id: str,
) -> ErrorInfo:
    reason = candidate.legacy_rejection_reason
    if reason is LegacyEquationRejectionReason.Y_PRESENT_ON_EXPLICIT_SIDE:
        return ErrorInfo(
            code=ErrorCode.EXPLICIT_FUNCTION_Y_NOT_ALLOWED,
            user_message="显函数右侧只能使用自变量 x，不能再次使用 y。",
            technical_message="y appears outside the direct isolated equation side",
            item_id=item_id,
            field_name="input_text",
            source_location=candidate.legacy_source_span,
            recoverable=True,
        )
    if reason is LegacyEquationRejectionReason.OTHER_NON_DIRECT_EQUATION:
        return ErrorInfo(
            code=ErrorCode.UNSUPPORTED_EQUATION,
            user_message="当前不支持该方程形式，请暂时改写为 y=... 的显函数形式。",
            technical_message=(
                "equation is outside the stage 7 direct-y explicit forms"
            ),
            item_id=item_id,
            field_name="input_text",
            source_location=candidate.legacy_source_span,
            recoverable=True,
        )
    return _internal_error(item_id, "unknown legacy equation rejection reason")


def _equation_validation_error(
    error: EquationValidationError,
    item_id: str,
    *,
    fallback: SourceSpan,
) -> ErrorInfo:
    source_location = error.source_span or fallback
    return ErrorInfo(
        code=ErrorCode.INVALID_AST,
        user_message="方程包含当前版本不支持或不可信的结构。",
        technical_message=f"equation validation failed ({error.kind.value})",
        item_id=item_id,
        field_name="input_text",
        source_location=source_location,
        recoverable=True,
    )


def _equation_polynomial_error(
    error: EquationPolynomialError,
    item_id: str,
) -> ErrorInfo:
    kind = error.kind
    if kind is PolynomialFailureKind.NON_RATIONAL_COEFFICIENT:
        code = ErrorCode.EQUATION_NON_RATIONAL_COEFFICIENT
        user_message = "方程系数必须是当前支持的有理数。"
    elif kind is PolynomialFailureKind.NON_POLYNOMIAL:
        code = ErrorCode.EQUATION_NON_POLYNOMIAL
        user_message = "当前只支持一次或二次多项式方程。"
    elif kind is PolynomialFailureKind.VARIABLE_DENOMINATOR:
        code = ErrorCode.EQUATION_VARIABLE_DENOMINATOR
        user_message = "方程暂不支持变量出现在分母中。"
    elif kind is PolynomialFailureKind.ZERO_DENOMINATOR:
        code = ErrorCode.EQUATION_ZERO_DENOMINATOR
        user_message = "方程中存在零分母。"
    elif kind is PolynomialFailureKind.DEGREE_EXCEEDED:
        code = ErrorCode.EQUATION_DEGREE_EXCEEDED
        user_message = "方程次数超过当前支持的二次上限。"
    elif kind is PolynomialFailureKind.UNSUPPORTED_EQUATION:
        code = ErrorCode.UNSUPPORTED_EQUATION
        user_message = "当前不支持该方程形式。"
    elif kind is PolynomialFailureKind.RESOURCE_LIMIT_EXCEEDED:
        code = ErrorCode.RESOURCE_LIMIT_EXCEEDED
        user_message = "方程精确计算超过当前安全上限，请简化后重试。"
    else:
        return _internal_error(item_id, "unknown equation polynomial failure kind")

    technical_message = f"equation polynomial normalization failed ({kind.value})"
    if kind is PolynomialFailureKind.RESOURCE_LIMIT_EXCEEDED:
        technical_message = (
            "equation polynomial normalization failed "
            f"({kind.value}: {error.exact_limit_component.value}, "
            f"limit={error.exact_limit})"
        )
    return ErrorInfo(
        code=code,
        user_message=user_message,
        technical_message=technical_message,
        item_id=item_id,
        field_name="input_text",
        source_location=error.source_span,
        recoverable=True,
    )


def _equation_geometry_error(
    error: EquationGeometryError,
    item_id: str,
    source_location: SourceSpan,
) -> ErrorInfo:
    kind = error.kind
    if kind is EquationGeometryFailureKind.ROTATED_CONIC_NOT_SUPPORTED:
        code = ErrorCode.ROTATED_CONIC_NOT_SUPPORTED
        user_message = "当前不支持含旋转项的圆锥曲线。"
    elif kind is EquationGeometryFailureKind.DEGENERATE_CONIC:
        code = ErrorCode.DEGENERATE_CONIC
        user_message = "该方程表示退化圆锥曲线，暂不支持绘制。"
    elif kind is EquationGeometryFailureKind.CONIC_HAS_NO_REAL_POINTS:
        code = ErrorCode.CONIC_HAS_NO_REAL_POINTS
        user_message = "该圆锥曲线没有实数点。"
    elif kind is EquationGeometryFailureKind.RESOURCE_LIMIT_EXCEEDED:
        code = ErrorCode.RESOURCE_LIMIT_EXCEEDED
        user_message = "方程几何计算超过当前安全上限，请简化后重试。"
    else:
        return _internal_error(item_id, "unknown equation geometry failure kind")

    technical_message = f"equation geometry classification failed ({kind.value})"
    if kind is EquationGeometryFailureKind.RESOURCE_LIMIT_EXCEEDED:
        technical_message = (
            "equation geometry classification failed "
            f"({kind.value}: {error.exact_limit_component.value}, "
            f"limit={error.exact_limit})"
        )
    return ErrorInfo(
        code=code,
        user_message=user_message,
        technical_message=technical_message,
        item_id=item_id,
        field_name="input_text",
        source_location=source_location,
        recoverable=True,
    )


def _validated_source_span(
    validated: object,
    fallback: SourceSpan,
) -> SourceSpan:
    if type(validated) is ValidatedEquationInput:
        provenance = getattr(validated, "provenance", None)
        if provenance is not None:
            source_span = getattr(provenance, "source_span", None)
            if type(source_span) is SourceSpan:
                return source_span
    return fallback


def _requested_kind_error(item_id: str) -> ErrorInfo:
    return ErrorInfo(
        code=ErrorCode.INVALID_REQUEST,
        user_message="请求的绘图类型与已验证的公式类型不一致。",
        technical_message="requested plot kind is incompatible with classified route",
        item_id=item_id,
        field_name="requested_plot_kind",
        source_location=None,
        recoverable=True,
    )


def _invalid_request(
    item_id: str | None,
    user_message: str,
    technical_message: str,
    field_name: str,
) -> ErrorInfo:
    return ErrorInfo(
        code=ErrorCode.INVALID_REQUEST,
        user_message=user_message,
        technical_message=technical_message,
        item_id=item_id,
        field_name=field_name,
        source_location=None,
        recoverable=True,
    )


def _internal_error(
    item_id: str,
    technical_message: str,
    *,
    field_name: str = "input_text",
) -> ErrorInfo:
    return ErrorInfo(
        code=ErrorCode.INTERNAL_ERROR,
        user_message="公式分析内部契约无效，请重新提交。",
        technical_message=technical_message,
        item_id=item_id,
        field_name=field_name,
        source_location=None,
        recoverable=False,
    )


__all__ = ["analyze_plot_item"]
