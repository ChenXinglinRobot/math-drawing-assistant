"""Lexical expression/equation boundary splitting without algebra."""

from __future__ import annotations

from dataclasses import dataclass

from math_drawing_assistant.engine.tokenizer import Token, TokenKind
from math_drawing_assistant.models.errors import ErrorCode, ErrorInfo, SourceSpan


@dataclass(frozen=True, slots=True)
class ExpressionInput:
    """A token sequence containing no equals token."""

    tokens: tuple[Token, ...]
    normalized_span: SourceSpan
    source_span: SourceSpan


@dataclass(frozen=True, slots=True)
class EquationInput:
    """Two non-empty token sequences separated by exactly one equals token."""

    left_tokens: tuple[Token, ...]
    right_tokens: tuple[Token, ...]
    left_normalized_span: SourceSpan
    right_normalized_span: SourceSpan
    left_source_span: SourceSpan
    right_source_span: SourceSpan


def split_equation(
    tokens: tuple[Token, ...],
) -> ExpressionInput | EquationInput | ErrorInfo:
    """Split a complete token tuple without parsing or transforming either side."""

    if not isinstance(tokens, tuple):
        raise TypeError("tokens must be a tuple.")
    for token in tokens:
        if not isinstance(token, Token):
            raise TypeError("tokens must contain only Token values.")

    if not tokens:
        return _error(
            ErrorCode.EMPTY_INPUT,
            "请输入一个公式或方程。",
            "equation splitter received an empty token tuple",
            SourceSpan(0, 0),
        )

    equals_indexes = tuple(
        index for index, token in enumerate(tokens) if token.kind is TokenKind.EQUAL
    )
    if not equals_indexes:
        return ExpressionInput(
            tokens=tokens,
            normalized_span=_normalized_extent(tokens),
            source_span=_source_extent(tokens),
        )
    if len(equals_indexes) > 1:
        second_equals = tokens[equals_indexes[1]]
        return _error(
            ErrorCode.MULTIPLE_EQUALS,
            "一个输入中只能包含一个等号。",
            f"multiple equals tokens count={len(equals_indexes)}",
            second_equals.source_span,
        )

    equals_index = equals_indexes[0]
    equals_token = tokens[equals_index]
    left_tokens = tokens[:equals_index]
    right_tokens = tokens[equals_index + 1 :]
    if not left_tokens:
        offset = equals_token.source_span.start
        return _error(
            ErrorCode.EQUATION_LEFT_EMPTY,
            "方程等号左侧不能为空。",
            "equation has no tokens before equals",
            SourceSpan(offset, offset),
        )
    if not right_tokens:
        offset = equals_token.source_span.end
        return _error(
            ErrorCode.EQUATION_RIGHT_EMPTY,
            "方程等号右侧不能为空。",
            "equation has no tokens after equals",
            SourceSpan(offset, offset),
        )

    return EquationInput(
        left_tokens=left_tokens,
        right_tokens=right_tokens,
        left_normalized_span=_normalized_extent(left_tokens),
        right_normalized_span=_normalized_extent(right_tokens),
        left_source_span=_source_extent(left_tokens),
        right_source_span=_source_extent(right_tokens),
    )


def _normalized_extent(tokens: tuple[Token, ...]) -> SourceSpan:
    return SourceSpan(
        tokens[0].normalized_span.start,
        tokens[-1].normalized_span.end,
    )


def _source_extent(tokens: tuple[Token, ...]) -> SourceSpan:
    return SourceSpan(tokens[0].source_span.start, tokens[-1].source_span.end)


def _error(
    code: ErrorCode,
    user_message: str,
    technical_message: str,
    source_location: SourceSpan,
) -> ErrorInfo:
    return ErrorInfo(
        code=code,
        user_message=user_message,
        technical_message=technical_message,
        field_name="input_text",
        source_location=source_location,
        recoverable=True,
    )
