"""Central, immutable application configuration contracts."""

from math_drawing_assistant.config.limits import (
    DEFAULT_LIMITS,
    LIMITS_VERSION,
    ApplicationLimits,
    LimitStatus,
)

__all__ = [
    "ApplicationLimits",
    "DEFAULT_LIMITS",
    "LIMITS_VERSION",
    "LimitStatus",
]
