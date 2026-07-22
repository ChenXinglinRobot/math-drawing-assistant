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


def test_existing_error_code_values_remain_stable() -> None:
    assert ErrorCode.INVALID_INPUT.value == "invalid_input"
    assert ErrorCode.RENDER_FAILED.value == "render_failed"


def test_all_error_code_values_are_unique() -> None:
    values = [code.value for code in ErrorCode]
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
