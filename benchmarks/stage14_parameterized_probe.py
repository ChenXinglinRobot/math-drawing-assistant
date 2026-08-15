"""Direct Stage 14 parameterized-sampler prototype measurements.

This tool intentionally stops before renderer, Actor, PNG, GUI, preview, and
clipboard integration.  It records raw development-machine evidence only.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, fields
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import subprocess
import sys
from time import perf_counter_ns
from typing import Mapping, Sequence

import numpy as np

from math_drawing_assistant.engine import (
    RenderPlanBuilder,
    SampledParameterizedCurve,
    SamplingCancelled,
    analyze_plot_item,
    resolve_single_item_viewport,
    sample_parameterized_curve,
)
from math_drawing_assistant.models import (
    ErrorInfo,
    GeometryRenderItemPlan,
    InputSource,
    ParameterizedRenderMemoryBudget,
    PlotItemRequest,
    PlotKind,
    PlotSceneSpec,
    RenderPlan,
    ViewportMode,
    ViewportRequest,
)


PROTOCOL_VERSION = "stage14-parameterized-prototype-v1"
WARMUP_RUNS = 1
MEASUREMENT_RUNS = 5
DEVELOPMENT_SCREENING_TARGET_NS = 2_000_000_000
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESULTS_ROOT = REPOSITORY_ROOT / "benchmarks" / "results"
RESULT_FILENAMES = (
    "manifest.json",
    "environment.json",
    "records.jsonl",
    "summary.json",
)
MEMORY_BUDGET_KEYS = frozenset(
    {
        *(field.name for field in fields(ParameterizedRenderMemoryBudget)),
        "fixed_bytes",
        "batch_bytes",
        "total_bytes",
    },
)

BOUNDARY_STATEMENTS = (
    "Only the direct analyzer/resolver/RenderPlanBuilder/parameterized-sampler chain is measured.",
    "Actor, renderer, PNG, GUI, preview, and copy are excluded.",
    "Results from this machine are development references only.",
    "A result below two seconds is only necessary Stage 15 screening evidence, not M1.5 performance acceptance.",
    "No formal P50 or P95 is calculated or claimed by this prototype.",
)

RECORD_FIELDS = frozenset(
    {
        "protocol_version",
        "scenario_name",
        "scenario_index",
        "measurement_index",
        "formula",
        "item_id",
        "success",
        "status",
        "failure_stage",
        "error_code",
        "analyze_elapsed_ns",
        "resolve_elapsed_ns",
        "build_elapsed_ns",
        "sample_elapsed_ns",
        "total_elapsed_ns",
        "spec_type",
        "resolved_aspect",
        "viewport_source",
        "mathematical_branch_count",
        "planned_segment_count",
        "actual_segment_count",
        "max_segment_count",
        "sample_count",
        "batch_size",
        "memory_budget",
        "actual_x_bytes",
        "actual_y_bytes",
        "actual_segment_range_bytes",
        "warning_codes",
        "cancellation_probe_calls",
        "cancellation_elapsed_ns",
        "cancellation_neutral",
    },
)


@dataclass(frozen=True, slots=True)
class PrototypeScenario:
    name: str
    formula: str
    viewport_request: ViewportRequest = ViewportRequest()


SCENARIOS = (
    PrototypeScenario("line-vertical", "x=2"),
    PrototypeScenario("line-general", "2*x-y+3=0"),
    PrototypeScenario("circle-origin", "x^2+y^2=25"),
    PrototypeScenario("circle-translated", "(x-2)^2+(y+1)^2=9"),
    PrototypeScenario("ellipse-origin", "x^2/9+y^2/4=1"),
    PrototypeScenario("ellipse-translated", "(x-1)^2/9+(y+2)^2/4=1"),
    PrototypeScenario("hyperbola-horizontal", "x^2/9-y^2/4=1"),
    PrototypeScenario("hyperbola-vertical", "y^2/4-x^2/9=1"),
    PrototypeScenario(
        "hyperbola-one-branch-split",
        "x^2/9-y^2/4=1",
        ViewportRequest(
            mode=ViewportMode.MANUAL,
            x_min=5.0,
            x_max=10.0,
            y_min=-8.0,
            y_max=8.0,
        ),
    ),
    PrototypeScenario("parabola-up", "x^2=4*y"),
    PrototypeScenario("parabola-down", "x^2=-4*y"),
    PrototypeScenario("parabola-right", "y^2=4*x"),
    PrototypeScenario("parabola-left", "y^2=-4*x"),
    PrototypeScenario(
        "parabola-vertex-excluded-two-segments",
        "x^2=4*y",
        ViewportRequest(
            mode=ViewportMode.MANUAL,
            x_min=-10.0,
            x_max=10.0,
            y_min=1.0,
            y_max=4.0,
        ),
    ),
)


class _ImmediateCancellationProbe:
    def __init__(self) -> None:
        self.calls = 0

    def is_cancelled(self) -> bool:
        self.calls += 1
        return True


def _validate_scenarios(scenarios: Sequence[PrototypeScenario]) -> None:
    if not scenarios:
        raise ValueError("at least one prototype scenario is required")
    names = tuple(scenario.name for scenario in scenarios)
    if len(names) != len(set(names)):
        raise ValueError("prototype scenario names must be unique")
    for scenario in scenarios:
        if type(scenario) is not PrototypeScenario:
            raise TypeError("scenarios must contain exact PrototypeScenario values")


def _base_record(
    scenario: PrototypeScenario,
    *,
    scenario_index: int,
    measurement_index: int,
) -> dict[str, object]:
    return {
        "protocol_version": PROTOCOL_VERSION,
        "scenario_name": scenario.name,
        "scenario_index": scenario_index,
        "measurement_index": measurement_index,
        "formula": scenario.formula,
        "item_id": f"stage14-probe-{scenario_index:02d}",
        "success": False,
        "status": "typed_failure",
        "failure_stage": None,
        "error_code": None,
        "analyze_elapsed_ns": None,
        "resolve_elapsed_ns": None,
        "build_elapsed_ns": None,
        "sample_elapsed_ns": None,
        "total_elapsed_ns": None,
        "spec_type": None,
        "resolved_aspect": None,
        "viewport_source": None,
        "mathematical_branch_count": None,
        "planned_segment_count": None,
        "actual_segment_count": None,
        "max_segment_count": None,
        "sample_count": None,
        "batch_size": None,
        "memory_budget": None,
        "actual_x_bytes": None,
        "actual_y_bytes": None,
        "actual_segment_range_bytes": None,
        "warning_codes": [],
        "cancellation_probe_calls": None,
        "cancellation_elapsed_ns": None,
        "cancellation_neutral": None,
    }


def _typed_failure(
    record: dict[str, object],
    *,
    stage: str,
    error: ErrorInfo,
    total_start_ns: int,
) -> dict[str, object]:
    record["failure_stage"] = stage
    record["error_code"] = error.code.value
    record["total_elapsed_ns"] = perf_counter_ns() - total_start_ns
    return record


def _memory_payload(budget: ParameterizedRenderMemoryBudget) -> dict[str, int]:
    payload = {
        field.name: int(getattr(budget, field.name))
        for field in fields(ParameterizedRenderMemoryBudget)
    }
    payload.update(
        {
            "fixed_bytes": budget.fixed_bytes,
            "batch_bytes": budget.batch_bytes,
            "total_bytes": budget.total_bytes,
        },
    )
    if set(payload) != MEMORY_BUDGET_KEYS:
        raise RuntimeError("parameterized memory budget schema drifted")
    return payload


def _execute_once(
    scenario: PrototypeScenario,
    *,
    scenario_index: int,
    measurement_index: int,
) -> dict[str, object]:
    record = _base_record(
        scenario,
        scenario_index=scenario_index,
        measurement_index=measurement_index,
    )
    total_start = perf_counter_ns()
    request = PlotItemRequest(
        item_id=str(record["item_id"]),
        input_text=scenario.formula,
        input_source=InputSource.MANUAL,
        requested_plot_kind=PlotKind.AUTO,
        display_order=0,
    )

    stage_start = perf_counter_ns()
    spec = analyze_plot_item(request)
    record["analyze_elapsed_ns"] = perf_counter_ns() - stage_start
    if isinstance(spec, ErrorInfo):
        return _typed_failure(
            record,
            stage="analyze",
            error=spec,
            total_start_ns=total_start,
        )
    record["spec_type"] = type(spec).__name__
    scene = PlotSceneSpec(items=(spec,))

    stage_start = perf_counter_ns()
    resolution = resolve_single_item_viewport(scene, scenario.viewport_request)
    record["resolve_elapsed_ns"] = perf_counter_ns() - stage_start
    if resolution.error is not None:
        return _typed_failure(
            record,
            stage="resolve",
            error=resolution.error,
            total_start_ns=total_start,
        )
    if resolution.viewport is None:
        raise RuntimeError("successful viewport resolution returned no viewport")
    viewport = resolution.viewport
    record["resolved_aspect"] = viewport.aspect.value
    record["viewport_source"] = viewport.source.value

    stage_start = perf_counter_ns()
    plan = RenderPlanBuilder().build(
        scene,
        viewport,
        image_width=800,
        image_height=600,
        dpi=96,
        show_grid=True,
        show_legend=False,
    )
    record["build_elapsed_ns"] = perf_counter_ns() - stage_start
    if isinstance(plan, ErrorInfo):
        return _typed_failure(
            record,
            stage="build",
            error=plan,
            total_start_ns=total_start,
        )
    if type(plan) is not RenderPlan:
        raise RuntimeError("builder returned an unknown outcome")

    stage_start = perf_counter_ns()
    sampled = sample_parameterized_curve(plan)
    record["sample_elapsed_ns"] = perf_counter_ns() - stage_start
    record["total_elapsed_ns"] = perf_counter_ns() - total_start
    if isinstance(sampled, ErrorInfo):
        return _typed_failure(
            record,
            stage="sample",
            error=sampled,
            total_start_ns=total_start,
        )
    if type(sampled) is not SampledParameterizedCurve:
        raise RuntimeError("parameterized sampler returned an unknown outcome")
    if type(plan.item_plan) is not GeometryRenderItemPlan:
        raise RuntimeError("parameterized prototype received a non-geometry plan")
    if type(plan.memory_budget) is not ParameterizedRenderMemoryBudget:
        raise RuntimeError("parameterized prototype received the wrong memory budget")

    probe = _ImmediateCancellationProbe()
    cancellation_start = perf_counter_ns()
    cancellation = sample_parameterized_curve(plan, cancellation_probe=probe)
    cancellation_elapsed = perf_counter_ns() - cancellation_start

    record.update(
        {
            "success": True,
            "status": "success",
            "failure_stage": None,
            "error_code": None,
            "mathematical_branch_count": plan.item_plan.mathematical_branch_count,
            "planned_segment_count": len(plan.item_plan.segments),
            "actual_segment_count": sampled.visible_segment_count,
            "max_segment_count": plan.item_plan.max_segment_count,
            "sample_count": plan.item_plan.sample_count,
            "batch_size": plan.item_plan.batch_size,
            "memory_budget": _memory_payload(plan.memory_budget),
            "actual_x_bytes": int(sampled.x.nbytes),
            "actual_y_bytes": int(sampled.y.nbytes),
            "actual_segment_range_bytes": int(sampled.segment_ranges.nbytes),
            "warning_codes": [warning.code.value for warning in sampled.warnings],
            "cancellation_probe_calls": probe.calls,
            "cancellation_elapsed_ns": cancellation_elapsed,
            "cancellation_neutral": type(cancellation) is SamplingCancelled,
        },
    )
    if set(record) != RECORD_FIELDS:
        raise RuntimeError("prototype record schema drifted")
    return record


def run_scenario(
    scenario: PrototypeScenario,
    *,
    scenario_index: int = 0,
    warmup_runs: int = WARMUP_RUNS,
    measurement_runs: int = MEASUREMENT_RUNS,
) -> tuple[dict[str, object], ...]:
    """Warm one fixed scenario, then retain each raw measurement record."""

    if type(scenario) is not PrototypeScenario:
        raise TypeError("scenario must be an exact PrototypeScenario")
    if isinstance(warmup_runs, bool) or not isinstance(warmup_runs, int) or warmup_runs < 0:
        raise ValueError("warmup_runs must be a nonnegative integer")
    if (
        isinstance(measurement_runs, bool)
        or not isinstance(measurement_runs, int)
        or measurement_runs <= 0
    ):
        raise ValueError("measurement_runs must be a positive integer")
    for warmup_index in range(warmup_runs):
        _execute_once(
            scenario,
            scenario_index=scenario_index,
            measurement_index=-(warmup_index + 1),
        )
    return tuple(
        _execute_once(
            scenario,
            scenario_index=scenario_index,
            measurement_index=measurement_index,
        )
        for measurement_index in range(measurement_runs)
    )


def _project_commit() -> str:
    completed = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        check=False,
        text=True,
        timeout=10,
    )
    value = completed.stdout.strip()
    return value if completed.returncode == 0 and len(value) == 40 else "unknown"


def collect_environment(*, generated_at_utc: str) -> dict[str, object]:
    """Collect reproducibility fields without paths or environment variables."""

    return {
        "protocol_version": PROTOCOL_VERSION,
        "generated_at_utc": generated_at_utc,
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "os": platform.system(),
        "os_release": platform.release(),
        "os_version": platform.version(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "platform": platform.platform(),
        "numpy_version": np.__version__,
        "git_commit": _project_commit(),
    }


def _duration_summary(records: Sequence[Mapping[str, object]]) -> dict[str, object]:
    successful = [record for record in records if record["success"] is True]
    raw_total_ns = [int(record["total_elapsed_ns"]) for record in successful]
    return {
        "measurement_count": len(records),
        "success_count": len(successful),
        "typed_failure_count": len(records) - len(successful),
        "raw_total_elapsed_ns": raw_total_ns,
        "minimum_total_elapsed_ns": min(raw_total_ns) if raw_total_ns else None,
        "maximum_total_elapsed_ns": max(raw_total_ns) if raw_total_ns else None,
        "below_two_second_development_screen": (
            bool(raw_total_ns)
            and len(raw_total_ns) == len(records)
            and max(raw_total_ns) < DEVELOPMENT_SCREENING_TARGET_NS
        ),
    }


def _summary(
    records: Sequence[Mapping[str, object]],
    scenarios: Sequence[PrototypeScenario],
) -> dict[str, object]:
    by_scenario = []
    for scenario in scenarios:
        selected = [
            record for record in records if record["scenario_name"] == scenario.name
        ]
        by_scenario.append(
            {"scenario_name": scenario.name, **_duration_summary(selected)},
        )
    return {
        "protocol_version": PROTOCOL_VERSION,
        "formal_percentiles_computed": False,
        "boundary_statements": list(BOUNDARY_STATEMENTS),
        "overall": _duration_summary(records),
        "scenarios": by_scenario,
    }


def run_probe(
    scenarios: Sequence[PrototypeScenario] = SCENARIOS,
    *,
    warmup_runs: int = WARMUP_RUNS,
    measurement_runs: int = MEASUREMENT_RUNS,
) -> dict[str, object]:
    """Run the fixed direct prototype without invoking any application layer."""

    _validate_scenarios(scenarios)
    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    records = tuple(
        record
        for scenario_index, scenario in enumerate(scenarios)
        for record in run_scenario(
            scenario,
            scenario_index=scenario_index,
            warmup_runs=warmup_runs,
            measurement_runs=measurement_runs,
        )
    )
    return {
        "protocol_version": PROTOCOL_VERSION,
        "generated_at_utc": generated_at,
        "warmup_runs": warmup_runs,
        "measurement_runs": measurement_runs,
        "scenario_order": [scenario.name for scenario in scenarios],
        "environment": collect_environment(generated_at_utc=generated_at),
        "records": list(records),
        "summary": _summary(records, scenarios),
    }


def _json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write_result_bundle(
    run: Mapping[str, object],
    *,
    output_root: Path = DEFAULT_RESULTS_ROOT,
) -> Path:
    """Write the four-file Stage 14 prototype result bundle."""

    if run.get("protocol_version") != PROTOCOL_VERSION:
        raise ValueError("run protocol version does not match the active prototype")
    timestamp = str(run["generated_at_utc"])
    parsed_timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    compact_timestamp = parsed_timestamp.astimezone(timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ",
    )
    directory = output_root / f"{compact_timestamp}-{PROTOCOL_VERSION}"
    directory.mkdir(parents=True, exist_ok=False)

    records = run["records"]
    if not isinstance(records, list):
        raise TypeError("run records must be a list")
    manifest = {
        "protocol_version": PROTOCOL_VERSION,
        "generated_at_utc": run["generated_at_utc"],
        "warmup_runs": run["warmup_runs"],
        "measurement_runs": run["measurement_runs"],
        "scenario_order": run["scenario_order"],
        "record_count": len(records),
        "result_files": list(RESULT_FILENAMES),
        "boundary_statements": list(BOUNDARY_STATEMENTS),
    }
    (directory / "manifest.json").write_text(
        _json_text(manifest),
        encoding="utf-8",
    )
    (directory / "environment.json").write_text(
        _json_text(run["environment"]),
        encoding="utf-8",
    )
    records_text = "".join(
        json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
        for record in records
    )
    (directory / "records.jsonl").write_text(records_text, encoding="utf-8")
    (directory / "summary.json").write_text(
        _json_text(run["summary"]),
        encoding="utf-8",
    )
    return directory


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_RESULTS_ROOT,
        help="Directory under which the timestamped result bundle is created.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    run = run_probe()
    directory = write_result_bundle(run, output_root=args.output_root)
    overall = run["summary"]["overall"]  # type: ignore[index]
    print(directory)
    print(
        f"records={overall['measurement_count']} "  # type: ignore[index]
        f"success={overall['success_count']} "  # type: ignore[index]
        f"typed_failure={overall['typed_failure_count']}",  # type: ignore[index]
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
