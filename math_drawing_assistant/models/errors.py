"""Stable, typed, display-safe error information."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ErrorCode(str, Enum):
    """Published error-code registry for implemented project boundaries."""

    INVALID_INPUT = "invalid_input"
    RENDER_FAILED = "render_failed"
    INVALID_REQUEST = "invalid_request"
    RESOURCE_LIMIT_EXCEEDED = "resource_limit_exceeded"
    INTERNAL_ERROR = "internal_error"
    EMPTY_INPUT = "empty_input"
    INPUT_TOO_LONG = "input_too_long"
    UNKNOWN_CHARACTER = "unknown_character"
    UNKNOWN_IDENTIFIER = "unknown_identifier"
    UNSUPPORTED_RELATION = "unsupported_relation"
    TOKEN_LIMIT_EXCEEDED = "token_limit_exceeded"
    NUMBER_TOO_LONG = "number_too_long"
    NESTING_TOO_DEEP = "nesting_too_deep"
    DELIMITER_MISMATCH = "delimiter_mismatch"
    ILLEGAL_TRAILING = "illegal_trailing"
    MULTIPLE_EQUALS = "multiple_equals"
    EQUATION_LEFT_EMPTY = "equation_left_empty"
    EQUATION_RIGHT_EMPTY = "equation_right_empty"
    PARSER_SYNTAX_ERROR = "parser_syntax_error"
    FUNCTION_CALL_REQUIRED = "function_call_required"
    FUNCTION_ARGUMENT_ERROR = "function_argument_error"
    LOG_REQUIRES_BASE = "log_requires_base"
    INVALID_LOG_BASE = "invalid_log_base"
    IMPLICIT_MULTIPLICATION_NOT_ALLOWED = "implicit_multiplication_not_allowed"
    NESTED_ABSOLUTE_VALUE = "nested_absolute_value"
    AST_NODE_LIMIT_EXCEEDED = "ast_node_limit_exceeded"
    AST_DEPTH_LIMIT_EXCEEDED = "ast_depth_limit_exceeded"
    RATIONAL_LITERAL_TOO_LONG = "rational_literal_too_long"
    EXPONENT_OUT_OF_RANGE = "exponent_out_of_range"
    UNSUPPORTED_EXPONENT = "unsupported_exponent"
    INVALID_AST = "invalid_ast"
    EXPLICIT_FUNCTION_Y_NOT_ALLOWED = "explicit_function_y_not_allowed"
    UNSUPPORTED_EQUATION = "unsupported_equation"


@dataclass(frozen=True, slots=True)
class SourceSpan:
    """A zero-based half-open location in one source string."""

    start: int
    end: int

    def __post_init__(self) -> None:
        for name, value in (("start", self.start), ("end", self.end)):
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"SourceSpan.{name} must be an integer.")
        if self.start < 0:
            raise ValueError("SourceSpan.start must not be negative.")
        if self.end < self.start:
            raise ValueError("SourceSpan.end must not precede start.")


@dataclass(frozen=True, slots=True, init=False)
class ErrorInfo:
    """A small, serializable error notice without exception or stack data."""

    code: ErrorCode
    user_message: str
    technical_message: str | None = None
    item_id: str | None = None
    field_name: str | None = None
    source_location: SourceSpan | None = None
    recoverable: bool = True

    def __init__(
        self,
        code: ErrorCode | str,
        user_message: str,
        technical_message: str | None = None,
        item_id: str | None = None,
        field_name: str | None = None,
        source_location: SourceSpan | None = None,
        recoverable: bool = True,
    ) -> None:
        """Build an error, accepting existing published strings at the boundary."""

        try:
            stable_code = ErrorCode(code)
        except (TypeError, ValueError) as exc:
            raise ValueError("ErrorInfo.code must be a registered error code.") from exc

        if not isinstance(user_message, str):
            raise TypeError("ErrorInfo.user_message must be a string.")
        if not user_message.strip():
            raise ValueError("ErrorInfo.user_message must not be empty.")
        self._validate_optional_text(technical_message, "technical_message")
        self._validate_optional_text(item_id, "item_id")
        self._validate_optional_text(field_name, "field_name")
        if source_location is not None and not isinstance(
            source_location,
            SourceSpan,
        ):
            raise TypeError("source_location must be a SourceSpan or None.")
        if not isinstance(recoverable, bool):
            raise TypeError("recoverable must be a bool.")

        object.__setattr__(self, "code", stable_code)
        object.__setattr__(self, "user_message", user_message)
        object.__setattr__(self, "technical_message", technical_message)
        object.__setattr__(self, "item_id", item_id)
        object.__setattr__(self, "field_name", field_name)
        object.__setattr__(self, "source_location", source_location)
        object.__setattr__(self, "recoverable", recoverable)

    @staticmethod
    def _validate_optional_text(value: str | None, name: str) -> None:
        if value is None:
            return
        if not isinstance(value, str):
            raise TypeError(f"ErrorInfo.{name} must be a string or None.")
        if not value.strip():
            raise ValueError(f"ErrorInfo.{name} must not be empty when supplied.")
