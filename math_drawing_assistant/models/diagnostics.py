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


def _positive_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer.")
    if value <= 0:
        raise ValueError(f"{field_name} must be positive.")
    return value


@dataclass(frozen=True, slots=True)
class PlotItemDiagnostics:
    """Planned and completed sampling counts for one plot item."""

    planned_sample_point_count: int
    actual_sampled_point_count: int | None = None
    sampled_segment_count: int | None = None
    visible_segment_count: int | None = None

    def __post_init__(self) -> None:
        planned = _positive_int(
            self.planned_sample_point_count,
            "planned_sample_point_count",
        )
        completed = (
            self.actual_sampled_point_count,
            self.sampled_segment_count,
            self.visible_segment_count,
        )
        if all(value is None for value in completed):
            return
        if any(value is None for value in completed):
            raise ValueError("sampling diagnostic fields must be all present or all absent.")
        actual = _positive_int(
            self.actual_sampled_point_count,
            "actual_sampled_point_count",
        )
        sampled_segments = _positive_int(
            self.sampled_segment_count,
            "sampled_segment_count",
        )
        visible_segments = _positive_int(
            self.visible_segment_count,
            "visible_segment_count",
        )
        if actual != planned:
            raise ValueError("actual sampled point count must equal the planned count.")
        if visible_segments > sampled_segments:
            raise ValueError("visible segment count must not exceed sampled segments.")


@dataclass(frozen=True, slots=True)
class PlotSceneDiagnostics:
    """Approved scene resources and completed output sizes."""

    total_planned_sample_point_count: int
    total_actual_sampled_point_count: int | None
    approved_estimated_memory_bytes: int
    final_png_byte_count: int | None = None

    def __post_init__(self) -> None:
        planned = _positive_int(
            self.total_planned_sample_point_count,
            "total_planned_sample_point_count",
        )
        _positive_int(
            self.approved_estimated_memory_bytes,
            "approved_estimated_memory_bytes",
        )
        actual = self.total_actual_sampled_point_count
        if actual is not None:
            actual = _positive_int(actual, "total_actual_sampled_point_count")
            if actual != planned:
                raise ValueError("actual scene sample count must equal the planned count.")
        if self.final_png_byte_count is not None:
            if actual is None:
                raise ValueError("PNG byte count requires completed scene sampling.")
            _positive_int(self.final_png_byte_count, "final_png_byte_count")
