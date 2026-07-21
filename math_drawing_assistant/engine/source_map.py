"""Immutable source mapping for the stage 6 input front end."""

from __future__ import annotations

from dataclasses import dataclass

from math_drawing_assistant.models.errors import SourceSpan


@dataclass(frozen=True, slots=True)
class SourceMap:
    """Map normalized half-open ranges back to contributing source ranges.

    ``character_spans[index]`` is the non-empty original range that produced
    ``normalized_text[index]``.  A one-to-many expansion repeats a source
    span, while a many-to-one replacement stores the complete source span.

    A zero-length normalized range maps to a zero-length original range.  At
    a boundary before a character, it uses that character's source start; the
    final boundary uses the last character's source end.  An empty map uses
    original offset zero.
    """

    original_text: str
    normalized_text: str
    character_spans: tuple[SourceSpan, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.original_text, str):
            raise TypeError("SourceMap.original_text must be a string.")
        if not isinstance(self.normalized_text, str):
            raise TypeError("SourceMap.normalized_text must be a string.")
        if not isinstance(self.character_spans, tuple):
            raise TypeError("SourceMap.character_spans must be a tuple.")
        if len(self.character_spans) != len(self.normalized_text):
            raise ValueError(
                "SourceMap must contain one source span per normalized character.",
            )
        if self.normalized_text and not self.original_text:
            raise ValueError("A non-empty normalized text needs a non-empty source.")

        previous: SourceSpan | None = None
        for span in self.character_spans:
            if not isinstance(span, SourceSpan):
                raise TypeError("SourceMap entries must be SourceSpan values.")
            if span.start == span.end:
                raise ValueError("Every normalized character needs a non-empty span.")
            if span.end > len(self.original_text):
                raise ValueError("A source span extends beyond the original text.")
            if previous is not None and (
                span.start < previous.start or span.end < previous.end
            ):
                raise ValueError("SourceMap character spans must be monotonic.")
            previous = span

    def source_span_for_character(self, index: int) -> SourceSpan:
        """Return the original non-empty span for one normalized character."""

        self._validate_integer(index, "index")
        if not 0 <= index < len(self.normalized_text):
            raise IndexError("Normalized character index is out of range.")
        return self.character_spans[index]

    def map_offset(self, offset: int) -> SourceSpan:
        """Map a normalized boundary offset to a zero-length original span."""

        self._validate_integer(offset, "offset")
        if not 0 <= offset <= len(self.normalized_text):
            raise IndexError("Normalized offset is out of range.")
        if not self.character_spans:
            return SourceSpan(0, 0)
        if offset == len(self.normalized_text):
            original_offset = self.character_spans[-1].end
        else:
            original_offset = self.character_spans[offset].start
        return SourceSpan(original_offset, original_offset)

    def map_normalized_span(self, span: SourceSpan) -> SourceSpan:
        """Map one normalized half-open range to its original source range."""

        if not isinstance(span, SourceSpan):
            raise TypeError("span must be a SourceSpan.")
        if span.end > len(self.normalized_text):
            raise IndexError("Normalized span is out of range.")
        if span.start == span.end:
            return self.map_offset(span.start)
        return SourceSpan(
            self.character_spans[span.start].start,
            self.character_spans[span.end - 1].end,
        )

    def map_token_span(self, span: SourceSpan) -> SourceSpan:
        """Map a normalized token range using the same half-open semantics."""

        return self.map_normalized_span(span)

    @staticmethod
    def _validate_integer(value: int, name: str) -> None:
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{name} must be an integer.")
