"""Whitelist tokenizer for normalized mathematical input."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final

from math_drawing_assistant.config import ApplicationLimits, DEFAULT_LIMITS
from math_drawing_assistant.engine.normalizer import NormalizedInput
from math_drawing_assistant.models.errors import ErrorCode, ErrorInfo, SourceSpan


class TokenKind(str, Enum):
    """Closed stage 6 token-kind set."""

    NUMBER = "number"
    VARIABLE = "variable"
    CONSTANT = "constant"
    FUNCTION = "function"
    PLUS = "plus"
    MINUS = "minus"
    STAR = "star"
    SLASH = "slash"
    POWER = "power"
    LEFT_PAREN = "left_paren"
    RIGHT_PAREN = "right_paren"
    COMMA = "comma"
    BAR = "bar"
    EQUAL = "equal"


@dataclass(frozen=True, slots=True)
class Token:
    """One immutable token with normalized and original half-open ranges."""

    kind: TokenKind
    lexeme: str
    normalized_span: SourceSpan
    source_span: SourceSpan

    def __post_init__(self) -> None:
        if not isinstance(self.kind, TokenKind):
            raise TypeError("Token.kind must be a TokenKind.")
        if not isinstance(self.lexeme, str):
            raise TypeError("Token.lexeme must be a string.")
        if not self.lexeme:
            raise ValueError("Token.lexeme must not be empty.")
        if not isinstance(self.normalized_span, SourceSpan):
            raise TypeError("Token.normalized_span must be a SourceSpan.")
        if not isinstance(self.source_span, SourceSpan):
            raise TypeError("Token.source_span must be a SourceSpan.")
        if self.normalized_span.start == self.normalized_span.end:
            raise ValueError("A token must consume normalized text.")
        if self.source_span.start == self.source_span.end:
            raise ValueError("A token must map to non-empty original text.")


APPROVED_FUNCTIONS: Final[frozenset[str]] = frozenset(
    {"sin", "cos", "tan", "sqrt", "abs", "exp", "log", "ln", "lg"},
)
APPROVED_CONSTANTS: Final[frozenset[str]] = frozenset({"pi", "E"})
APPROVED_VARIABLES: Final[frozenset[str]] = frozenset({"x", "y"})

_SINGLE_CHARACTER_KINDS: Final[dict[str, TokenKind]] = {
    "+": TokenKind.PLUS,
    "-": TokenKind.MINUS,
    "*": TokenKind.STAR,
    "/": TokenKind.SLASH,
    "^": TokenKind.POWER,
    "(": TokenKind.LEFT_PAREN,
    ")": TokenKind.RIGHT_PAREN,
    ",": TokenKind.COMMA,
    "|": TokenKind.BAR,
    "=": TokenKind.EQUAL,
}
_ILLEGAL_TRAILING_KINDS: Final[frozenset[TokenKind]] = frozenset(
    {
        TokenKind.PLUS,
        TokenKind.MINUS,
        TokenKind.STAR,
        TokenKind.SLASH,
        TokenKind.POWER,
        TokenKind.COMMA,
        TokenKind.LEFT_PAREN,
    },
)


def tokenize(
    normalized_input: NormalizedInput,
    *,
    limits: ApplicationLimits = DEFAULT_LIMITS,
) -> tuple[Token, ...] | ErrorInfo:
    """Fully consume normalized input into the closed stage 6 token set."""

    if not isinstance(normalized_input, NormalizedInput):
        raise TypeError("normalized_input must be a NormalizedInput.")
    if not isinstance(limits, ApplicationLimits):
        raise TypeError("limits must be an ApplicationLimits value.")

    text = normalized_input.text
    source_map = normalized_input.source_map
    tokens: list[Token] = []
    open_parentheses: list[Token] = []
    unmatched_bar: Token | None = None
    index = 0

    while index < len(text):
        character = text[index]

        relation_end = _relation_end(text, index)
        if relation_end is not None:
            normalized_span = SourceSpan(index, relation_end)
            return _error(
                ErrorCode.UNSUPPORTED_RELATION,
                "当前版本不支持不等式或其他关系符。",
                "unsupported relation operator",
                source_map.map_normalized_span(normalized_span),
            )

        if character.isascii() and (
            character.isdigit()
            or (character == "." and index + 1 < len(text) and text[index + 1].isdigit())
        ):
            scanned = _scan_number(normalized_input, index, limits)
            if isinstance(scanned, ErrorInfo):
                return scanned
            token, index = scanned
            overflow = _append_token(tokens, token, limits)
            if overflow is not None:
                return overflow
            continue

        if character.isascii() and character.isalpha():
            end = index + 1
            while end < len(text) and text[end].isascii() and text[end].isalpha():
                end += 1
            identifier = text[index:end]
            kind = _identifier_kind(identifier)
            normalized_span = SourceSpan(index, end)
            source_span = source_map.map_token_span(normalized_span)
            if kind is None:
                return _error(
                    ErrorCode.UNKNOWN_IDENTIFIER,
                    "输入中包含当前版本不支持的标识符。",
                    f"unknown identifier length={len(identifier)}",
                    source_span,
                )
            token = Token(kind, identifier, normalized_span, source_span)
            overflow = _append_token(tokens, token, limits)
            if overflow is not None:
                return overflow
            index = end
            continue

        kind = _SINGLE_CHARACTER_KINDS.get(character)
        if kind is None:
            normalized_span = SourceSpan(index, index + 1)
            return _error(
                ErrorCode.UNKNOWN_CHARACTER,
                "输入中包含当前版本不支持的字符。",
                f"unknown normalized character U+{ord(character):04X}",
                source_map.map_normalized_span(normalized_span),
            )

        normalized_span = SourceSpan(index, index + 1)
        token = Token(
            kind=kind,
            lexeme=character,
            normalized_span=normalized_span,
            source_span=source_map.map_token_span(normalized_span),
        )
        overflow = _append_token(tokens, token, limits)
        if overflow is not None:
            return overflow

        if kind is TokenKind.LEFT_PAREN:
            open_parentheses.append(token)
            if len(open_parentheses) > limits.max_nesting_depth:
                return _error(
                    ErrorCode.NESTING_TOO_DEEP,
                    "括号嵌套超过当前安全上限。",
                    "parenthesis nesting limit exceeded",
                    token.source_span,
                )
        elif kind is TokenKind.RIGHT_PAREN:
            if not open_parentheses:
                return _error(
                    ErrorCode.DELIMITER_MISMATCH,
                    "右括号没有对应的左括号。",
                    "unmatched right parenthesis",
                    token.source_span,
                )
            open_parentheses.pop()
        elif kind is TokenKind.BAR:
            unmatched_bar = token if unmatched_bar is None else None

        index += 1

    if open_parentheses:
        return _error(
            ErrorCode.DELIMITER_MISMATCH,
            "左括号没有对应的右括号。",
            "unclosed left parenthesis",
            open_parentheses[-1].source_span,
        )
    if unmatched_bar is not None:
        return _error(
            ErrorCode.DELIMITER_MISMATCH,
            "绝对值竖线必须成对出现。",
            "unpaired absolute-value bar",
            unmatched_bar.source_span,
        )
    if not tokens:
        return _error(
            ErrorCode.EMPTY_INPUT,
            "请输入一个公式或方程。",
            "tokenizer received empty normalized text",
            SourceSpan(0, 0),
        )

    final_token = tokens[-1]
    if final_token.kind is TokenKind.EQUAL:
        return _error(
            ErrorCode.EQUATION_RIGHT_EMPTY,
            "方程等号右侧不能为空。",
            "equation ends with equals token",
            SourceSpan(final_token.source_span.end, final_token.source_span.end),
        )
    if final_token.kind in _ILLEGAL_TRAILING_KINDS:
        return _error(
            ErrorCode.ILLEGAL_TRAILING,
            "公式末尾不完整，请补全后重试。",
            f"illegal trailing token kind={final_token.kind.value}",
            final_token.source_span,
        )

    return tuple(tokens)


def _scan_number(
    normalized_input: NormalizedInput,
    start: int,
    limits: ApplicationLimits,
) -> tuple[Token, int] | ErrorInfo:
    text = normalized_input.text
    source_map = normalized_input.source_map
    index = start
    numeric_digits = 0
    decimal_places = 0
    decimal_seen = False

    if text[index] == ".":
        decimal_seen = True
        index += 1

    while index < len(text):
        character = text[index]
        if character.isascii() and character.isdigit():
            numeric_digits += 1
            if decimal_seen:
                decimal_places += 1
            index += 1
            if (
                numeric_digits > limits.max_numeric_digits
                or decimal_places > limits.max_decimal_places
            ):
                normalized_span = SourceSpan(start, index)
                return _error(
                    ErrorCode.NUMBER_TOO_LONG,
                    "数字长度超过当前安全上限。",
                    (
                        "numeric token limit exceeded "
                        f"digits={numeric_digits} decimal_places={decimal_places}"
                    ),
                    source_map.map_normalized_span(normalized_span),
                )
            continue
        if character == "." and not decimal_seen:
            if index + 1 >= len(text) or not text[index + 1].isdigit():
                dot_span = SourceSpan(index, index + 1)
                return _error(
                    ErrorCode.ILLEGAL_TRAILING,
                    "小数点后必须包含数字。",
                    "incomplete decimal token",
                    source_map.map_normalized_span(dot_span),
                )
            decimal_seen = True
            index += 1
            continue
        break

    if index < len(text) and text[index] == ".":
        dot_span = SourceSpan(index, index + 1)
        return _error(
            ErrorCode.ILLEGAL_TRAILING,
            "一个数字中只能包含一个小数点。",
            "multiple decimal points in numeric token",
            source_map.map_normalized_span(dot_span),
        )

    normalized_span = SourceSpan(start, index)
    token = Token(
        kind=TokenKind.NUMBER,
        lexeme=text[start:index],
        normalized_span=normalized_span,
        source_span=source_map.map_token_span(normalized_span),
    )
    return token, index


def _identifier_kind(identifier: str) -> TokenKind | None:
    if identifier in APPROVED_VARIABLES:
        return TokenKind.VARIABLE
    if identifier in APPROVED_CONSTANTS:
        return TokenKind.CONSTANT
    if identifier in APPROVED_FUNCTIONS:
        return TokenKind.FUNCTION
    return None


def _relation_end(text: str, start: int) -> int | None:
    character = text[start]
    if character in "≤≥≠":
        return start + 1
    if character in "<>":
        if start + 1 < len(text) and text[start + 1] == "=":
            return start + 2
        return start + 1
    if character == "!" and start + 1 < len(text) and text[start + 1] == "=":
        return start + 2
    return None


def _append_token(
    tokens: list[Token],
    token: Token,
    limits: ApplicationLimits,
) -> ErrorInfo | None:
    if len(tokens) >= limits.max_tokens:
        return _error(
            ErrorCode.TOKEN_LIMIT_EXCEEDED,
            "token 数量超过当前安全上限。",
            "token limit exceeded while scanning",
            token.source_span,
        )
    tokens.append(token)
    return None


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
