"""Structured, display-safe error information."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ErrorInfo:
    """A small, serializable error notice without exception or stack data."""

    code: str
    user_message: str
    technical_message: str | None = None
    item_id: str | None = None
    field_name: str | None = None
    source_location: str | None = None
    recoverable: bool = True

    def __post_init__(self) -> None:
        if not self.code:
            raise ValueError("ErrorInfo.code must not be empty.")
        if not self.user_message:
            raise ValueError("ErrorInfo.user_message must not be empty.")
