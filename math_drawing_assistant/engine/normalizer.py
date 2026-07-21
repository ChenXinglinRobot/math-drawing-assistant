"""Explicit, non-executing normalization for mathematical input text."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from math_drawing_assistant.config import ApplicationLimits, DEFAULT_LIMITS
from math_drawing_assistant.engine.source_map import SourceMap
from math_drawing_assistant.models.errors import ErrorCode, ErrorInfo, SourceSpan


_FULLWIDTH_DIGITS: Final[dict[str, str]] = {
    chr(codepoint): str(codepoint - 0xFF10)
    for codepoint in range(0xFF10, 0xFF1A)
}

CHARACTER_REPLACEMENTS: Final[dict[str, str]] = {
    **_FULLWIDTH_DIGITS,
    "（": "(",
    "）": ")",
    "＝": "=",
    "＋": "+",
    "－": "-",
    "＊": "*",
    "／": "/",
    "，": ",",
    "．": ".",
    "｜": "|",
    "−": "-",
    "×": "*",
    "·": "*",
    "÷": "/",
    "²": "^2",
    "³": "^3",
}

_PASSTHROUGH_ASCII: Final[frozenset[str]] = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789+-*/^(),|=.<>!",
)
_PASSTHROUGH_RELATIONS: Final[frozenset[str]] = frozenset("≤≥≠")


@dataclass(frozen=True, slots=True)
class NormalizedInput:
    """Normalized text paired with its immutable original-source mapping."""

    text: str
    source_map: SourceMap

    def __post_init__(self) -> None:
        if not isinstance(self.text, str):
            raise TypeError("NormalizedInput.text must be a string.")
        if not isinstance(self.source_map, SourceMap):
            raise TypeError("NormalizedInput.source_map must be a SourceMap.")
        if self.text != self.source_map.normalized_text:
            raise ValueError("NormalizedInput text must match its SourceMap.")


def normalize_input(
    original_text: str,
    *,
    limits: ApplicationLimits = DEFAULT_LIMITS,
) -> NormalizedInput | ErrorInfo:
    """Normalize one raw input without parsing or executing mathematics."""

    if not isinstance(original_text, str):
        raise TypeError("original_text must be a string.")
    if not isinstance(limits, ApplicationLimits):
        raise TypeError("limits must be an ApplicationLimits value.")

    if len(original_text) > limits.max_input_characters:
        return _error(
            ErrorCode.INPUT_TOO_LONG,
            "输入字符数超过当前安全上限，请缩短后重试。",
            "input character limit exceeded",
            SourceSpan(limits.max_input_characters, len(original_text)),
        )
    if not original_text:
        return _error(
            ErrorCode.EMPTY_INPUT,
            "请输入一个公式或方程。",
            "empty input",
            SourceSpan(0, 0),
        )

    normalized_characters: list[str] = []
    source_spans: list[SourceSpan] = []
    index = 0
    while index < len(original_text):
        character = original_text[index]

        if character == " ":
            space_end = index + 1
            while space_end < len(original_text) and original_text[space_end] == " ":
                space_end += 1
            if _space_would_merge_token(original_text, index, space_end):
                return _error(
                    ErrorCode.INVALID_INPUT,
                    "空格只能位于公式外围或明确的 token 边界。",
                    "controlled whitespace would merge one token",
                    SourceSpan(index, space_end),
                )
            index = space_end
            continue

        if original_text.startswith("**", index):
            normalized_characters.append("^")
            source_spans.append(SourceSpan(index, index + 2))
            index += 2
            continue

        replacement = CHARACTER_REPLACEMENTS.get(character)
        if replacement is not None:
            source_span = SourceSpan(index, index + 1)
            normalized_characters.extend(replacement)
            source_spans.extend(source_span for _ in replacement)
            index += 1
            continue

        if character in _PASSTHROUGH_ASCII or character in _PASSTHROUGH_RELATIONS:
            normalized_characters.append(character)
            source_spans.append(SourceSpan(index, index + 1))
            index += 1
            continue

        return _error(
            ErrorCode.UNKNOWN_CHARACTER,
            "输入中包含当前版本不支持的字符。",
            f"unsupported character category U+{ord(character):04X}",
            SourceSpan(index, index + 1),
        )

    if not normalized_characters:
        return _error(
            ErrorCode.EMPTY_INPUT,
            "请输入一个公式或方程。",
            "input contains only controlled spaces",
            SourceSpan(0, len(original_text)),
        )

    normalized_text = "".join(normalized_characters)
    source_map = SourceMap(
        original_text=original_text,
        normalized_text=normalized_text,
        character_spans=tuple(source_spans),
    )
    return NormalizedInput(text=normalized_text, source_map=source_map)


def _space_would_merge_token(text: str, start: int, end: int) -> bool:
    if start == 0 or end == len(text):
        return False
    left = CHARACTER_REPLACEMENTS.get(text[start - 1], text[start - 1])[-1]
    right = CHARACTER_REPLACEMENTS.get(text[end], text[end])[0]
    if left.isascii() and right.isascii() and left.isalpha() and right.isalpha():
        return True
    numeric_characters = frozenset("0123456789.")
    return left in numeric_characters and right in numeric_characters


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
