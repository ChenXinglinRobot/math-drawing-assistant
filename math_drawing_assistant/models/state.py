"""Small enums shared by immutable scene models and coordination code."""

from __future__ import annotations

from enum import Enum


class TaskPhase(str, Enum):
    """The single user-visible foreground activity."""

    IDLE = "idle"
    CAPTURING = "capturing"
    RECOGNIZING = "recognizing"
    REVIEWING = "reviewing"
    RENDERING = "rendering"
    SHUTTING_DOWN = "shutting_down"


class PlotKind(str, Enum):
    """The requested or classified plot category."""

    AUTO = "auto"
    EXPLICIT_FUNCTION = "explicit_function"
    LINE_EQUATION = "line_equation"
    CONIC_EQUATION = "conic_equation"


class InputSource(str, Enum):
    """How the user-facing input text entered the application."""

    MANUAL = "manual"
    OCR = "ocr"


class ViewportMode(str, Enum):
    """Whether viewport bounds are user-specified or to be resolved later."""

    AUTO = "auto"
    MANUAL = "manual"


class AspectRequest(str, Enum):
    """The coordinate aspect requested by the user."""

    AUTO = "auto"
    EQUAL = "equal"


class ViewportSource(str, Enum):
    """Where a resolved viewport range came from."""

    MANUAL = "manual"
    AUTO_PROBE = "auto_probe"
    AUTO_FALLBACK = "auto_fallback"
