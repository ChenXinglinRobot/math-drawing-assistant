"""Phase 5 tests for stable typed error information."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path
import re

import pytest

from math_drawing_assistant.models import ErrorCode, ErrorInfo, SourceSpan
from math_drawing_assistant.models.errors import (
    ViewportWarning,
    ViewportWarningCode,
)
from math_drawing_assistant.engine import SamplingWarningCode


LEGACY_ERROR_CODE_VALUES = {
    "INVALID_INPUT": "invalid_input",
    "RENDER_FAILED": "render_failed",
    "INVALID_REQUEST": "invalid_request",
    "RESOURCE_LIMIT_EXCEEDED": "resource_limit_exceeded",
    "INTERNAL_ERROR": "internal_error",
    "EMPTY_INPUT": "empty_input",
    "INPUT_TOO_LONG": "input_too_long",
    "UNKNOWN_CHARACTER": "unknown_character",
    "UNKNOWN_IDENTIFIER": "unknown_identifier",
    "UNSUPPORTED_RELATION": "unsupported_relation",
    "TOKEN_LIMIT_EXCEEDED": "token_limit_exceeded",
    "NUMBER_TOO_LONG": "number_too_long",
    "NESTING_TOO_DEEP": "nesting_too_deep",
    "DELIMITER_MISMATCH": "delimiter_mismatch",
    "ILLEGAL_TRAILING": "illegal_trailing",
    "MULTIPLE_EQUALS": "multiple_equals",
    "EQUATION_LEFT_EMPTY": "equation_left_empty",
    "EQUATION_RIGHT_EMPTY": "equation_right_empty",
    "PARSER_SYNTAX_ERROR": "parser_syntax_error",
    "FUNCTION_CALL_REQUIRED": "function_call_required",
    "FUNCTION_ARGUMENT_ERROR": "function_argument_error",
    "LOG_REQUIRES_BASE": "log_requires_base",
    "INVALID_LOG_BASE": "invalid_log_base",
    "IMPLICIT_MULTIPLICATION_NOT_ALLOWED": (
        "implicit_multiplication_not_allowed"
    ),
    "NESTED_ABSOLUTE_VALUE": "nested_absolute_value",
    "AST_NODE_LIMIT_EXCEEDED": "ast_node_limit_exceeded",
    "AST_DEPTH_LIMIT_EXCEEDED": "ast_depth_limit_exceeded",
    "RATIONAL_LITERAL_TOO_LONG": "rational_literal_too_long",
    "EXPONENT_OUT_OF_RANGE": "exponent_out_of_range",
    "UNSUPPORTED_EXPONENT": "unsupported_exponent",
    "INVALID_AST": "invalid_ast",
    "EXPLICIT_FUNCTION_Y_NOT_ALLOWED": "explicit_function_y_not_allowed",
    "UNSUPPORTED_EQUATION": "unsupported_equation",
    "INVALID_VIEWPORT": "invalid_viewport",
    "VIEWPORT_PROBE_BUDGET_EXCEEDED": "viewport_probe_budget_exceeded",
    "NO_VISIBLE_CURVE": "no_visible_curve",
}

STAGE_13_ERROR_CODE_VALUES = {
    "EQUATION_NON_RATIONAL_COEFFICIENT": (
        "equation_non_rational_coefficient"
    ),
    "EQUATION_NON_POLYNOMIAL": "equation_non_polynomial",
    "EQUATION_VARIABLE_DENOMINATOR": "equation_variable_denominator",
    "EQUATION_ZERO_DENOMINATOR": "equation_zero_denominator",
    "EQUATION_DEGREE_EXCEEDED": "equation_degree_exceeded",
    "ROTATED_CONIC_NOT_SUPPORTED": "rotated_conic_not_supported",
    "DEGENERATE_CONIC": "degenerate_conic",
    "CONIC_HAS_NO_REAL_POINTS": "conic_has_no_real_points",
}


def test_existing_error_code_values_remain_stable() -> None:
    assert {
        name: ErrorCode[name].value for name in LEGACY_ERROR_CODE_VALUES
    } == LEGACY_ERROR_CODE_VALUES


def test_stage_13_error_code_values_are_registered() -> None:
    assert {
        name: ErrorCode[name].value for name in STAGE_13_ERROR_CODE_VALUES
    } == STAGE_13_ERROR_CODE_VALUES


def test_stage_13_does_not_register_unapproved_error_codes() -> None:
    values = {code.value for code in ErrorCode}

    assert "equation_normalization_limit_exceeded" not in values
    assert "variable_zero_exponent" not in values
    assert ErrorCode.RESOURCE_LIMIT_EXCEEDED.value in values
    assert ErrorCode.UNSUPPORTED_EQUATION.value in values


def test_all_error_code_values_are_unique() -> None:
    values = [code.value for code in ErrorCode]
    assert len(values) == len(set(values))


def test_sampling_warning_code_values_are_unique_and_stable() -> None:
    assert SamplingWarningCode.PARTIAL_DOMAIN_OMITTED.value == (
        "partial_domain_omitted"
    )
    assert SamplingWarningCode.DENSE_OSCILLATION_SUSPECTED.value == (
        "dense_oscillation_suspected"
    )
    values = [code.value for code in SamplingWarningCode]
    assert len(values) == len(set(values))


def test_viewport_warnings_use_a_small_registered_typed_contract() -> None:
    warning = ViewportWarning(
        code="auto_viewport_fallback",
        user_message="A fallback is used.",
        item_id="item-1",
    )

    assert warning.code is ViewportWarningCode.AUTO_VIEWPORT_FALLBACK
    assert warning.item_id == "item-1"
    with pytest.raises(ValueError, match="registered"):
        ViewportWarning(code="future_warning", user_message="No.")


def test_error_info_is_frozen_and_normalizes_registered_strings() -> None:
    error = ErrorInfo(
        code="invalid_input",
        user_message="输入无效，请检查后重试。",
    )

    assert error.code is ErrorCode.INVALID_INPUT
    assert error.technical_message is None
    assert error.item_id is None
    assert error.source_location is None

    with pytest.raises(FrozenInstanceError):
        error.recoverable = False  # type: ignore[misc]  # frozen contract probe


def test_user_and_technical_messages_are_independent_fields() -> None:
    error = ErrorInfo(
        code=ErrorCode.INTERNAL_ERROR,
        user_message="暂时无法完成操作，请重试。",
        technical_message="sanitized exception category: RuntimeError",
        recoverable=True,
    )

    assert error.user_message != error.technical_message
    assert error.user_message == "暂时无法完成操作，请重试。"
    assert error.technical_message == "sanitized exception category: RuntimeError"


def test_optional_item_and_typed_source_span_are_supported() -> None:
    span = SourceSpan(start=3, end=8)
    error = ErrorInfo(
        code=ErrorCode.RESOURCE_LIMIT_EXCEEDED,
        user_message="输入超过当前安全限制。",
        item_id="item-2",
        field_name="input_text",
        source_location=span,
    )

    assert error.item_id == "item-2"
    assert error.field_name == "input_text"
    assert error.source_location is span
    assert "__dict__" not in SourceSpan.__dict__


@pytest.mark.parametrize(
    ("start", "end", "exception"),
    [
        (-1, 0, ValueError),
        (2, 1, ValueError),
        (True, 1, TypeError),
        (0, False, TypeError),
    ],
)
def test_invalid_source_spans_are_rejected(
    start: int,
    end: int,
    exception: type[Exception],
) -> None:
    with pytest.raises(exception):
        SourceSpan(start=start, end=end)


def test_unregistered_or_empty_error_content_is_rejected() -> None:
    with pytest.raises(ValueError, match="registered"):
        ErrorInfo(code="future_parser_error", user_message="尚未发布。")
    with pytest.raises(ValueError, match="user_message"):
        ErrorInfo(code=ErrorCode.INVALID_REQUEST, user_message="  ")
    with pytest.raises(TypeError, match="SourceSpan"):
        ErrorInfo(
            code=ErrorCode.INVALID_REQUEST,
            user_message="请求无效。",
            source_location="3:8",  # type: ignore[arg-type]  # invalid boundary probe
        )


def test_supported_formulas_error_registry_tracks_enum() -> None:
    document = (
        Path(__file__).parents[1] / "docs" / "supported-formulas.md"
    ).read_text(encoding="utf-8")
    section = document.split("<!-- ERROR_CODE_REGISTRY_START -->", 1)[1].split(
        "<!-- ERROR_CODE_REGISTRY_END -->",
        1,
    )[0]
    documented = set(re.findall(r"^\| `([^`]+)` \|", section, re.MULTILINE))

    assert documented == {code.value for code in ErrorCode}
