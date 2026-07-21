"""Small immutable diagnostics that do not collect or invent measurements."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True, slots=True)
class StageTiming:
    """Elapsed milliseconds for one named processing stage."""

    stage: str
    elapsed_ms: float

    def __post_init__(self) -> None:
        if not isinstance(self.stage, str):
            raise TypeError("stage must be a string.")
        if not self.stage.strip():
            raise ValueError("stage must not be empty.")
        if isinstance(self.elapsed_ms, bool) or not isinstance(
            self.elapsed_ms,
            (int, float),
        ):
            raise TypeError("elapsed_ms must be a real number.")

        elapsed_ms = float(self.elapsed_ms)
        if not isfinite(elapsed_ms):
            raise ValueError("elapsed_ms must be finite.")
        if elapsed_ms < 0:
            raise ValueError("elapsed_ms must not be negative.")
        object.__setattr__(self, "elapsed_ms", elapsed_ms)
