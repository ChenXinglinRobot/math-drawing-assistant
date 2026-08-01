"""Frozen M1 native-Windows GUI benchmark harness.

Importing this module is intentionally side-effect free.  In particular it does
not import the production bootstrap (and therefore Matplotlib) until after the
caller has selected a shared external ``MPLCONFIGDIR`` and explicitly confirmed
that a formal run is intended.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import queue
import random
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Iterable, Mapping, Sequence


PROTOCOL_VERSION = "m1-performance-v1"
TOOL_VERSION = "m1-benchmark-tools-v1"
SCHEDULE_SEED = 20260801
WARMUP_ROUNDS = 5
MEASUREMENT_ROUNDS = 30
STARTUP_SAMPLE_COUNT = 20
GUI_TIMER_INTERVAL_MS = 20
RENDER_TIMEOUT_SECONDS = 30.0
STARTUP_TIMEOUT_SECONDS = 30.0
STARTUP_EXIT_TIMEOUT_SECONDS = 15.0
SLEEP_DETECTION_TOLERANCE_MS = 1_000.0

STARTUP_THRESHOLD_MS = 5_000.0
RENDER_THRESHOLD_MS = 1_000.0
GUI_GAP_THRESHOLD_MS = 200.0

FONT_CACHE_READY_MARKER = "m1-font-cache-ready.json"
FONT_CACHE_READY_SCHEMA = "m1-font-cache-ready"
FONT_CACHE_READY_SCHEMA_VERSION = 2
BATCH_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
FROZEN_STARTUP_COMMAND = "<project-python> -B <startup-probe>"

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = REPOSITORY_ROOT / "docs" / "benchmarks" / "m1-performance-v1.md"
BENCHMARK_PATH = Path(__file__).resolve()
STARTUP_PROBE_PATH = REPOSITORY_ROOT / "benchmarks" / "m1_startup_probe.py"


@dataclass(frozen=True, slots=True)
class FormulaScenario:
    """One immutable formula selected from the current M1 acceptance surface."""

    formula_id: str
    exact_input: str
    rationale: str
    coverage: str


FORMULA_SCENARIOS: tuple[FormulaScenario, ...] = (
    FormulaScenario(
        "identity",
        "x=y",
        "Documented direct-side-swap identity and linear baseline.",
        "equation split, direct y-side swap, auto viewport, continuous sampling",
    ),
    FormulaScenario(
        "quadratic",
        "x^2",
        "Canonical quadratic with a turning point.",
        "power AST, nonlinear auto viewport, direction-change sampling",
    ),
    FormulaScenario(
        "reciprocal",
        "1/x",
        "Representative reciprocal with a vertical asymptote.",
        "division, non-finite samples, discontinuity segmentation",
    ),
    FormulaScenario(
        "restricted_domain",
        "ln(x)",
        "Natural logarithm whose real domain excludes part of the viewport.",
        "log executor, partial-domain omission warning, visible segment filtering",
    ),
    FormulaScenario(
        "trigonometric",
        "sin(x)",
        "Ordinary periodic trigonometric function.",
        "trigonometric executor path and multiple monotone runs",
    ),
    FormulaScenario(
        "exponential",
        "exp(x)",
        "Approved exponential spelling with rapidly varying magnitude.",
        "function-call executor, finite/non-finite handling, steep continuous curve",
    ),
    FormulaScenario(
        "logarithmic",
        "log(x,10)",
        "Approved explicit-base logarithm exercises the two-argument path.",
        "log-base validation, two-argument executor, automatic viewport",
    ),
    FormulaScenario(
        "dense_oscillation",
        "sin(1000*x)",
        "Documented positive case for the dense-oscillation warning proxy.",
        "implicit complexity, formal sampling diagnostics, warning propagation",
    ),
)


class InvalidReason(str, Enum):
    """The closed protocol enumeration for invalid individual samples."""

    APPLICATION_PROCESS_EXIT = "application_process_exit"
    REQUEST_FAILED = "request_failed"
    REQUEST_CANCELLED = "request_cancelled"
    REQUEST_TIMEOUT = "request_timeout"
    REQUEST_ID_REVISION_MISMATCH = "request_id_revision_mismatch"
    MISSING_RESULT = "missing_result"
    DUPLICATE_RESULT = "duplicate_result"
    BENCHMARK_HARNESS_EXCEPTION = "benchmark_harness_exception"
    INCOMPLETE_MONOTONIC_RECORD = "incomplete_monotonic_record"
    PREVIEW_NOT_UPDATED = "preview_not_updated"


class InvalidBatchReason(str, Enum):
    """The closed protocol enumeration for invalid complete batches."""

    WINDOWS_SLEEP_OR_RESUME = "windows_sleep_or_resume"
    BENCHMARK_PROCESS_CRASH = "benchmark_process_crash"
    USER_CLOSED_WINDOW = "user_closed_window"
    ENVIRONMENT_CHANGED = "environment_changed"
    SCHEDULE_CORRUPTED = "schedule_corrupted"
    RESULT_INTEGRITY_FAILED = "result_integrity_failed"


RENDER_REQUIRED_FIELDS = frozenset(
    {
        "protocol_version",
        "tool_version",
        "project_commit",
        "batch_id",
        "round_index",
        "formula_id",
        "exact_input",
        "sample_kind",
        "submission_monotonic",
        "completion_monotonic",
        "duration_ms",
        "timer_max_gap_ms",
        "request_id",
        "scene_revision",
        "success",
        "invalid_reason",
        "error_code",
        "preview_updated",
    }
)

STARTUP_REQUIRED_FIELDS = frozenset(
    {
        "protocol_version",
        "tool_version",
        "project_commit",
        "batch_id",
        "sample_index",
        "start_monotonic",
        "ready_monotonic",
        "duration_ms",
        "ready_count",
        "child_pid",
        "exit_code",
        "success",
        "invalid_reason",
        "error_code",
    }
)

REQUIRED_RESULT_FILES = frozenset(
    {
        "manifest.json",
        "environment.json",
        "startup-samples.jsonl",
        "render-samples.jsonl",
        "summary.json",
        "protocol.sha256",
        "tools.sha256",
        "stdout.txt",
        "stderr.txt",
    }
)
MANIFEST_REQUIRED_FIELDS = frozenset(
    {
        "protocol_version",
        "tool_version",
        "batch_id",
        "retest_of",
        "formal_measurement",
        "invalid_batch",
        "invalid_batch_reasons",
        "artifact_hashes",
        "result_file_sha256",
        "startup_command",
        "render_schedule",
    }
)
FONT_CACHE_READY_REQUIRED_FIELDS = frozenset(
    {
        "schema",
        "schema_version",
        "tool_version",
        "matplotlib_version",
        "font_cache_manifest",
    }
)
FONT_CACHE_MANIFEST_ENTRY_FIELDS = frozenset({"basename", "size", "sha256"})


@dataclass(frozen=True, slots=True)
class ScheduledSample:
    sample_kind: str
    round_index: int
    formula_id: str
    exact_input: str


@dataclass(frozen=True, slots=True)
class FrozenArtifactHashes:
    protocol_sha256: str
    benchmark_sha256: str
    startup_probe_sha256: str


@dataclass(frozen=True, slots=True)
class StabilitySnapshot:
    displays: tuple[tuple[object, ...], ...]
    power_mode: str
    tick_count_ms: int
    unbiased_interrupt_ms: float


def _round_seed(seed: int, sample_kind: str, round_index: int) -> int:
    payload = f"{PROTOCOL_VERSION}:{seed}:{sample_kind}:{round_index}".encode("ascii")
    return int.from_bytes(hashlib.sha256(payload).digest(), "big")


def build_schedule(
    sample_kind: str,
    *,
    seed: int = SCHEDULE_SEED,
    rounds: int | None = None,
) -> tuple[ScheduledSample, ...]:
    """Build the deterministic per-round shuffled schedule."""

    if sample_kind not in {"warmup", "measurement"}:
        raise ValueError("sample_kind must be warmup or measurement.")
    expected_rounds = WARMUP_ROUNDS if sample_kind == "warmup" else MEASUREMENT_ROUNDS
    round_count = expected_rounds if rounds is None else rounds
    if isinstance(round_count, bool) or not isinstance(round_count, int):
        raise TypeError("rounds must be an integer.")
    if round_count < 1:
        raise ValueError("rounds must be positive.")

    schedule: list[ScheduledSample] = []
    for round_index in range(round_count):
        scenarios = list(FORMULA_SCENARIOS)
        random.Random(_round_seed(seed, sample_kind, round_index)).shuffle(scenarios)
        schedule.extend(
            ScheduledSample(
                sample_kind=sample_kind,
                round_index=round_index,
                formula_id=scenario.formula_id,
                exact_input=scenario.exact_input,
            )
            for scenario in scenarios
        )
    return tuple(schedule)


def full_render_schedule() -> tuple[ScheduledSample, ...]:
    return build_schedule("warmup") + build_schedule("measurement")


def nearest_rank(values: Iterable[float], percentile: float) -> float:
    """Return a nearest-rank percentile using one-based ``ceil(p * n)``."""

    ordered = sorted(float(value) for value in values)
    if not ordered:
        raise ValueError("nearest_rank requires at least one value.")
    if not 0.0 < percentile <= 1.0:
        raise ValueError("percentile must be in (0, 1].")
    if not all(math.isfinite(value) for value in ordered):
        raise ValueError("nearest_rank values must be finite.")
    return ordered[math.ceil(percentile * len(ordered)) - 1]


def max_gui_gap_ms(
    submission_monotonic: float,
    tick_monotonics: Sequence[float],
    completion_monotonic: float,
) -> float:
    """Include start, inter-tick, and final tick-to-completion gaps."""

    points = [float(submission_monotonic)]
    points.extend(float(value) for value in tick_monotonics)
    points.append(float(completion_monotonic))
    if not all(math.isfinite(value) for value in points):
        raise ValueError("GUI timer timestamps must be finite.")
    if any(later < earlier for earlier, later in zip(points, points[1:])):
        raise ValueError("GUI timer timestamps must be monotonic.")
    return max(
        (later - earlier) * 1_000.0
        for earlier, later in zip(points, points[1:])
    )


def threshold_status(value_ms: float | None, threshold_ms: float) -> str:
    """Classify one metric under the frozen strict 10% retest rule."""

    if value_ms is None:
        return "unavailable"
    if value_ms > threshold_ms:
        return "not_met"
    if 0.9 * threshold_ms < value_ms <= threshold_ms:
        return "retest_required"
    return "met"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def frozen_artifact_hashes() -> FrozenArtifactHashes:
    for path in (PROTOCOL_PATH, BENCHMARK_PATH, STARTUP_PROBE_PATH):
        if not path.is_file():
            raise FileNotFoundError(path)
    return FrozenArtifactHashes(
        protocol_sha256=sha256_file(PROTOCOL_PATH),
        benchmark_sha256=sha256_file(BENCHMARK_PATH),
        startup_probe_sha256=sha256_file(STARTUP_PROBE_PATH),
    )


def verify_frozen_artifacts(
    expected: FrozenArtifactHashes,
    actual: FrozenArtifactHashes | None = None,
) -> FrozenArtifactHashes:
    observed = frozen_artifact_hashes() if actual is None else actual
    if observed != expected:
        raise ValueError("Frozen protocol or tool SHA-256 does not match approval.")
    return observed


def startup_child_command(
    project_python: Path,
    startup_probe: Path = STARTUP_PROBE_PATH,
) -> tuple[str, ...]:
    """Return the exact timed child command; it deliberately contains no uv."""

    return (str(project_python), "-B", str(startup_probe))


def validate_external_directory(path: Path, *, purpose: str) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(REPOSITORY_ROOT.resolve())
    except ValueError:
        return resolved
    raise ValueError(f"{purpose} must be outside the repository.")


def preflight_output_directory(output_directory: Path) -> Path:
    """Resolve and reject an unsafe or already-published result directory."""

    resolved = validate_external_directory(output_directory, purpose="result directory")
    if resolved.exists():
        raise FileExistsError(resolved)
    return resolved


def validate_batch_identifiers(batch_id: str, retest_of: str | None = None) -> None:
    """Apply one frozen character rule to first-batch and retest identities."""

    if not isinstance(batch_id, str):
        raise ValueError("--batch-id must be a string.")
    if BATCH_ID_PATTERN.fullmatch(batch_id) is None:
        raise ValueError("--batch-id contains unsupported characters.")
    if retest_of is None:
        return
    if not isinstance(retest_of, str):
        raise ValueError("--retest-of must be a string or null.")
    if BATCH_ID_PATTERN.fullmatch(retest_of) is None:
        raise ValueError("--retest-of contains unsupported characters.")
    if batch_id == retest_of:
        raise ValueError("--retest-of must identify a different earlier batch.")


def validate_render_record(record: Mapping[str, object]) -> None:
    missing = RENDER_REQUIRED_FIELDS.difference(record)
    if missing:
        raise ValueError(f"Render record missing fields: {sorted(missing)}")
    reason = record["invalid_reason"]
    allowed = {member.value for member in InvalidReason}
    if reason is not None and reason not in allowed:
        raise ValueError("Render record has a non-protocol invalid reason.")
    if record["protocol_version"] != PROTOCOL_VERSION:
        raise ValueError("Render record protocol version mismatch.")


def validate_startup_record(record: Mapping[str, object]) -> None:
    missing = STARTUP_REQUIRED_FIELDS.difference(record)
    if missing:
        raise ValueError(f"Startup record missing fields: {sorted(missing)}")
    reason = record["invalid_reason"]
    allowed = {member.value for member in InvalidReason}
    if reason is not None and reason not in allowed:
        raise ValueError("Startup record has a non-protocol invalid reason.")
    if record["protocol_version"] != PROTOCOL_VERSION:
        raise ValueError("Startup record protocol version mismatch.")


def _successful_values(
    records: Sequence[Mapping[str, object]],
    field: str,
) -> list[float]:
    return [
        float(record[field])
        for record in records
        if record["success"] is True
        and record["invalid_reason"] is None
        and record[field] is not None
    ]


def compute_summary(
    render_records: Sequence[Mapping[str, object]],
    startup_records: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Compute frozen descriptive statistics without deleting slow samples."""

    for record in render_records:
        validate_render_record(record)
    for record in startup_records:
        validate_startup_record(record)

    measured = [record for record in render_records if record["sample_kind"] == "measurement"]
    per_formula: dict[str, dict[str, object]] = {}
    for scenario in FORMULA_SCENARIOS:
        records = [record for record in measured if record["formula_id"] == scenario.formula_id]
        durations = _successful_values(records, "duration_ms")
        gaps = _successful_values(records, "timer_max_gap_ms")
        complete = len(records) == MEASUREMENT_ROUNDS and len(durations) == MEASUREMENT_ROUNDS
        render_p95 = nearest_rank(durations, 0.95) if complete else None
        gap_p95 = nearest_rank(gaps, 0.95) if complete and len(gaps) == MEASUREMENT_ROUNDS else None
        per_formula[scenario.formula_id] = {
            "exact_input": scenario.exact_input,
            "sample_count": len(records),
            "valid_success_count": len(durations),
            "p50_ms": nearest_rank(durations, 0.50) if complete else None,
            "p95_ms": render_p95,
            "max_ms": max(durations) if complete else None,
            "timer_max_gap_p95_ms": gap_p95,
            "render_threshold_status": threshold_status(render_p95, RENDER_THRESHOLD_MS),
            "gui_gap_threshold_status": threshold_status(gap_p95, GUI_GAP_THRESHOLD_MS),
        }

    overall_durations = _successful_values(measured, "duration_ms")
    startup_durations = _successful_values(startup_records, "duration_ms")
    startup_complete = (
        len(startup_records) == STARTUP_SAMPLE_COUNT
        and len(startup_durations) == STARTUP_SAMPLE_COUNT
    )
    startup_p95 = nearest_rank(startup_durations, 0.95) if startup_complete else None

    statuses = [
        details["render_threshold_status"]
        for details in per_formula.values()
    ] + [
        details["gui_gap_threshold_status"]
        for details in per_formula.values()
    ] + [threshold_status(startup_p95, STARTUP_THRESHOLD_MS)]
    all_records = list(render_records) + list(startup_records)
    has_failed_or_invalid_sample = any(
        record["success"] is not True or record["invalid_reason"] is not None
        for record in all_records
    )
    threshold_conclusion = (
        "unavailable"
        if has_failed_or_invalid_sample
        else "not_met"
        if "not_met" in statuses
        else "retest_required"
        if "retest_required" in statuses
        else "met"
        if statuses and "unavailable" not in statuses
        else "unavailable"
    )

    return {
        "protocol_version": PROTOCOL_VERSION,
        "tool_version": TOOL_VERSION,
        "per_formula": per_formula,
        "overall_measurement": {
            "scheduled_count": len(measured),
            "valid_success_count": len(overall_durations),
            "p50_ms": (
                nearest_rank(overall_durations, 0.50)
                if len(overall_durations) == len(measured) == 240
                else None
            ),
            "p95_ms": (
                nearest_rank(overall_durations, 0.95)
                if len(overall_durations) == len(measured) == 240
                else None
            ),
            "max_ms": (
                max(overall_durations)
                if len(overall_durations) == len(measured) == 240
                else None
            ),
        },
        "startup": {
            "sample_count": len(startup_records),
            "valid_success_count": len(startup_durations),
            "p50_ms": nearest_rank(startup_durations, 0.50) if startup_complete else None,
            "p95_ms": startup_p95,
            "max_ms": max(startup_durations) if startup_complete else None,
            "threshold_status": threshold_status(startup_p95, STARTUP_THRESHOLD_MS),
        },
        "counts": {
            "failure": sum(record["success"] is not True for record in render_records)
            + sum(record["success"] is not True for record in startup_records),
            "invalid": sum(record["invalid_reason"] is not None for record in render_records)
            + sum(record["invalid_reason"] is not None for record in startup_records),
            "cancelled": sum(
                record["invalid_reason"] == InvalidReason.REQUEST_CANCELLED.value
                for record in render_records
            ),
            "timeout": sum(
                record["invalid_reason"] == InvalidReason.REQUEST_TIMEOUT.value
                for record in render_records
            )
            + sum(
                record["invalid_reason"] == InvalidReason.REQUEST_TIMEOUT.value
                for record in startup_records
            ),
        },
        "retest_required": (
            not has_failed_or_invalid_sample and "retest_required" in statuses
        ),
        "threshold_conclusion": threshold_conclusion,
    }


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _jsonl_bytes(records: Sequence[Mapping[str, object]]) -> bytes:
    return b"".join(
        (json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
        for record in records
    )


def _frozen_render_schedule_payload() -> dict[str, int]:
    return {
        "seed": SCHEDULE_SEED,
        "warmup_rounds": WARMUP_ROUNDS,
        "measurement_rounds": MEASUREMENT_ROUNDS,
        "warmup_samples": 40,
        "measurement_samples": 240,
    }


def write_result_bundle(
    output_directory: Path,
    *,
    batch_id: str,
    environment: Mapping[str, object],
    startup_records: Sequence[Mapping[str, object]],
    render_records: Sequence[Mapping[str, object]],
    artifact_hashes: FrozenArtifactHashes,
    invalid_batch_reasons: Sequence[str] = (),
    stdout_text: str = "",
    stderr_text: str = "",
    retest_of: str | None = None,
) -> Path:
    """Validate in a same-parent staging directory, then publish exactly once."""

    validate_batch_identifiers(batch_id, retest_of)
    for record in startup_records:
        validate_startup_record(record)
    for record in render_records:
        validate_render_record(record)
    allowed_batch_reasons = {member.value for member in InvalidBatchReason}
    if any(reason not in allowed_batch_reasons for reason in invalid_batch_reasons):
        raise ValueError("Result bundle has a non-protocol invalid batch reason.")

    resolved = preflight_output_directory(output_directory)
    summary = compute_summary(render_records, startup_records)
    if invalid_batch_reasons:
        summary["retest_required"] = False
        summary["threshold_conclusion"] = "invalid_batch"

    payloads: dict[str, bytes] = {
        "environment.json": _json_bytes(dict(environment)),
        "startup-samples.jsonl": _jsonl_bytes(startup_records),
        "render-samples.jsonl": _jsonl_bytes(render_records),
        "summary.json": _json_bytes(summary),
        "protocol.sha256": (
            f"{artifact_hashes.protocol_sha256}  docs/benchmarks/m1-performance-v1.md\n"
        ).encode("ascii"),
        "tools.sha256": (
            f"{artifact_hashes.benchmark_sha256}  benchmarks/m1_gui_benchmark.py\n"
            f"{artifact_hashes.startup_probe_sha256}  benchmarks/m1_startup_probe.py\n"
        ).encode("ascii"),
        "stdout.txt": stdout_text.encode("utf-8"),
        "stderr.txt": stderr_text.encode("utf-8"),
    }
    file_hashes = {
        name: hashlib.sha256(payload).hexdigest()
        for name, payload in payloads.items()
    }
    manifest = {
        "protocol_version": PROTOCOL_VERSION,
        "tool_version": TOOL_VERSION,
        "batch_id": batch_id,
        "retest_of": retest_of,
        "formal_measurement": True,
        "invalid_batch": bool(invalid_batch_reasons),
        "invalid_batch_reasons": list(invalid_batch_reasons),
        "artifact_hashes": asdict(artifact_hashes),
        "result_file_sha256": file_hashes,
        "startup_command": FROZEN_STARTUP_COMMAND,
        "render_schedule": _frozen_render_schedule_payload(),
    }
    payloads["manifest.json"] = _json_bytes(manifest)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{resolved.name}.staging-",
            dir=resolved.parent,
        ),
    )
    try:
        for name, payload in payloads.items():
            (staging / name).write_bytes(payload)
        validate_result_bundle(staging, expected_hashes=artifact_hashes)
        preflight_output_directory(resolved)
        staging.rename(resolved)
        staging = None
        return resolved
    finally:
        if staging is not None and staging.exists():
            shutil.rmtree(staging)


def validate_result_bundle(
    result_directory: Path,
    *,
    expected_hashes: FrozenArtifactHashes,
) -> None:
    direct_entries = list(result_directory.iterdir())
    entries = {path.name for path in direct_entries}
    missing = REQUIRED_RESULT_FILES.difference(entries)
    if missing:
        raise ValueError(f"Result bundle missing files: {sorted(missing)}")
    extra = entries.difference(REQUIRED_RESULT_FILES)
    if extra:
        raise ValueError(f"Result bundle has unexpected entries: {sorted(extra)}")
    for path in direct_entries:
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Result bundle entry is not a regular file: {path.name}")

    manifest = json.loads((result_directory / "manifest.json").read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("Result bundle manifest must be a JSON object.")
    manifest_fields = set(manifest)
    missing_manifest_fields = MANIFEST_REQUIRED_FIELDS.difference(manifest_fields)
    if missing_manifest_fields:
        raise ValueError(
            f"Result bundle manifest missing fields: {sorted(missing_manifest_fields)}",
        )
    unexpected_manifest_fields = manifest_fields.difference(MANIFEST_REQUIRED_FIELDS)
    if unexpected_manifest_fields:
        raise ValueError(
            f"Result bundle manifest has unexpected fields: {sorted(unexpected_manifest_fields)}",
        )
    if manifest["protocol_version"] != PROTOCOL_VERSION:
        raise ValueError("Result bundle manifest protocol version mismatch.")
    if manifest["tool_version"] != TOOL_VERSION:
        raise ValueError("Result bundle manifest tool version mismatch.")
    try:
        validate_batch_identifiers(manifest["batch_id"], manifest["retest_of"])
    except ValueError as error:
        raise ValueError("Result bundle manifest batch identifiers are invalid.") from error
    if manifest["formal_measurement"] is not True:
        raise ValueError("Result bundle manifest is not a formal measurement.")
    if type(manifest["invalid_batch"]) is not bool:
        raise ValueError("Result bundle manifest invalid_batch must be boolean.")
    invalid_batch_reasons = manifest["invalid_batch_reasons"]
    allowed_batch_reasons = {member.value for member in InvalidBatchReason}
    if not isinstance(invalid_batch_reasons, list) or any(
        not isinstance(reason, str) or reason not in allowed_batch_reasons
        for reason in invalid_batch_reasons
    ):
        raise ValueError("Result bundle manifest has invalid batch reasons.")
    if manifest["invalid_batch"] != bool(invalid_batch_reasons):
        raise ValueError("Result bundle manifest invalid batch status is inconsistent.")
    if manifest["artifact_hashes"] != asdict(expected_hashes):
        raise ValueError("Result bundle frozen artifact hash mismatch.")
    if manifest["startup_command"] != FROZEN_STARTUP_COMMAND:
        raise ValueError("Result bundle manifest startup command mismatch.")
    expected_render_schedule = _frozen_render_schedule_payload()
    render_schedule = manifest["render_schedule"]
    if (
        not isinstance(render_schedule, dict)
        or set(render_schedule) != set(expected_render_schedule)
        or any(type(value) is not int for value in render_schedule.values())
        or render_schedule != expected_render_schedule
    ):
        raise ValueError("Result bundle manifest render schedule mismatch.")

    result_hashes = manifest["result_file_sha256"]
    expected_hashed_files = REQUIRED_RESULT_FILES.difference({"manifest.json"})
    if not isinstance(result_hashes, dict) or set(result_hashes) != expected_hashed_files:
        raise ValueError("Result bundle integrity index is incomplete.")
    for name, expected in result_hashes.items():
        if sha256_file(result_directory / name) != expected:
            raise ValueError(f"Result file integrity mismatch: {name}")

    environment = json.loads((result_directory / "environment.json").read_text(encoding="utf-8"))
    summary = json.loads((result_directory / "summary.json").read_text(encoding="utf-8"))
    if not isinstance(environment, dict):
        raise ValueError("Result bundle environment must be a JSON object.")
    if environment.get("protocol_version") != manifest["protocol_version"]:
        raise ValueError("Result bundle environment protocol version mismatch.")
    project_commit = environment.get("project_commit")
    if not isinstance(project_commit, str) or re.fullmatch(r"[0-9a-f]{40}", project_commit) is None:
        raise ValueError("Result bundle environment project commit is invalid.")
    if not isinstance(summary, dict):
        raise ValueError("Result bundle summary must be a JSON object.")
    if summary.get("protocol_version") != manifest["protocol_version"]:
        raise ValueError("Result bundle summary protocol version mismatch.")
    if summary.get("tool_version") != manifest["tool_version"]:
        raise ValueError("Result bundle summary tool version mismatch.")

    for line in (result_directory / "render-samples.jsonl").read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if not isinstance(record, dict):
            raise ValueError("Result bundle render record must be a JSON object.")
        validate_render_record(record)
        if record["tool_version"] != manifest["tool_version"]:
            raise ValueError("Result bundle render record tool version mismatch.")
        if record["batch_id"] != manifest["batch_id"]:
            raise ValueError("Result bundle render record batch ID mismatch.")
        if record["project_commit"] != project_commit:
            raise ValueError("Result bundle render record project commit mismatch.")
    for line in (result_directory / "startup-samples.jsonl").read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if not isinstance(record, dict):
            raise ValueError("Result bundle startup record must be a JSON object.")
        validate_startup_record(record)
        if record["tool_version"] != manifest["tool_version"]:
            raise ValueError("Result bundle startup record tool version mismatch.")
        if record["batch_id"] != manifest["batch_id"]:
            raise ValueError("Result bundle startup record batch ID mismatch.")
        if record["project_commit"] != project_commit:
            raise ValueError("Result bundle startup record project commit mismatch.")


def current_project_commit() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def require_clean_reviewed_repository() -> str:
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if status:
        raise RuntimeError("Formal measurement requires a clean worktree and index.")
    head = current_project_commit()
    origin = subprocess.run(
        ["git", "rev-parse", "origin/master"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if head != origin:
        raise RuntimeError("Formal measurement requires HEAD == origin/master.")
    return head


def assert_formal_runtime_identity(runtime: object) -> None:
    """Prove that the factory graph owns one shared production Actor/Executor."""

    actor = getattr(runtime, "actor")
    executor = getattr(runtime, "executor")
    controller = getattr(runtime, "controller")
    window = getattr(runtime, "window")
    worker = getattr(actor, "_worker")
    if getattr(worker, "_executor") is not executor:
        raise RuntimeError("Runtime Actor does not own the factory Executor.")
    if getattr(controller, "_render_submitter") is not actor:
        raise RuntimeError("Runtime Controller does not submit to the factory Actor.")
    if getattr(window, "_controller") is not controller:
        raise RuntimeError("Runtime MainWindow does not own the factory Controller.")


def assert_clipboard_untouched(runtime: object) -> None:
    history = getattr(getattr(runtime, "clipboard_service"), "write_history")
    if tuple(history):
        raise RuntimeError("Benchmark detected a ClipboardService write.")


def _mailbox_is_empty(actor: object) -> bool:
    mailbox = getattr(actor, "_mailbox")
    lock = getattr(mailbox, "_lock")
    with lock:
        return (
            getattr(mailbox, "pending") is None
            and getattr(mailbox, "current_token") is None
        )


def _result_error_code(result: object) -> str | None:
    error = getattr(result, "error", None)
    if error is None:
        return None
    code = getattr(error, "code", None)
    return str(getattr(code, "value", code)) if code is not None else None


def _retained_preview_cache_key(plot_preview: object) -> int | None:
    """Read the retained GUI-thread image identity without asking for a copy."""

    image = getattr(plot_preview, "_source_image")
    if image is None or image.isNull():
        return None
    return int(image.cacheKey())


def _invalid_hot_sample_record(
    scheduled: ScheduledSample,
    *,
    project_commit: str,
    batch_id: str,
    error_code: str,
    scene_revision: int | None = None,
) -> dict[str, object]:
    now = time.monotonic()
    return {
        "protocol_version": PROTOCOL_VERSION,
        "tool_version": TOOL_VERSION,
        "project_commit": project_commit,
        "batch_id": batch_id,
        "round_index": scheduled.round_index,
        "formula_id": scheduled.formula_id,
        "exact_input": scheduled.exact_input,
        "sample_kind": scheduled.sample_kind,
        "submission_monotonic": now,
        "completion_monotonic": now,
        "duration_ms": 0.0,
        "timer_max_gap_ms": 0.0,
        "request_id": None,
        "scene_revision": scene_revision,
        "success": False,
        "invalid_reason": InvalidReason.BENCHMARK_HARNESS_EXCEPTION.value,
        "error_code": error_code,
        "preview_updated": False,
    }


def _run_one_hot_sample(
    runtime: object,
    scheduled: ScheduledSample,
    *,
    project_commit: str,
    batch_id: str,
) -> dict[str, object]:
    """Preserve any ordinary harness failure as the current scheduled sample."""

    try:
        return _run_one_hot_sample_inner(
            runtime,
            scheduled,
            project_commit=project_commit,
            batch_id=batch_id,
        )
    except Exception:
        return _invalid_hot_sample_record(
            scheduled,
            project_commit=project_commit,
            batch_id=batch_id,
            error_code="hot_sample_exception",
        )


def _run_one_hot_sample_inner(
    runtime: object,
    scheduled: ScheduledSample,
    *,
    project_commit: str,
    batch_id: str,
) -> dict[str, object]:
    from PySide6.QtCore import QEventLoop, QTimer, Qt
    from PySide6.QtWidgets import QApplication

    controller = getattr(runtime, "controller")
    actor = getattr(runtime, "actor")
    window = getattr(runtime, "window")
    app = QApplication.instance()
    if app is None:
        raise RuntimeError("QApplication is unavailable.")

    window.formula_panel.set_text(scheduled.exact_input)
    app.processEvents()
    stable_revision = controller.current_scene_revision
    app.processEvents()
    preconditions = (
        controller.task_phase.name == "IDLE"
        and controller.current_render_request_id is None
        and _mailbox_is_empty(actor)
        and window.formula_panel.text() == scheduled.exact_input
        and controller.current_scene_revision == stable_revision
    )
    if not preconditions:
        return _invalid_hot_sample_record(
            scheduled,
            project_commit=project_commit,
            batch_id=batch_id,
            error_code="precondition_failed",
            scene_revision=stable_revision,
        )

    previous_cache_key = _retained_preview_cache_key(window.plot_preview)
    event_loop = QEventLoop()
    ticks: list[float] = []
    gap_timer = QTimer()
    gap_timer.setTimerType(Qt.TimerType.PreciseTimer)
    gap_timer.setInterval(GUI_TIMER_INTERVAL_MS)
    gap_timer.timeout.connect(lambda: ticks.append(time.monotonic()))
    timeout_timer = QTimer()
    timeout_timer.setSingleShot(True)

    state: dict[str, object] = {
        "matching_results": 0,
        "result": None,
        "invalid_reason": None,
        "error_code": None,
        "preview_updated": False,
        "completion": None,
    }
    request_id: int | None = None
    scene_revision: int | None = None

    def finish_after_event_turn() -> None:
        if state["completion"] is not None:
            return
        result = state["result"]
        if state["matching_results"] > 1:
            state["invalid_reason"] = InvalidReason.DUPLICATE_RESULT.value
        if result is not None and getattr(result, "success", False):
            current_cache_key = _retained_preview_cache_key(window.plot_preview)
            preview_updated = (
                state["matching_results"] == 1
                and getattr(result, "request_id", None) == request_id
                and getattr(result, "scene_revision", None) == scene_revision
                and controller.last_successful_result is result
                and controller.task_phase.name == "IDLE"
                and current_cache_key is not None
                and current_cache_key != previous_cache_key
            )
            state["preview_updated"] = preview_updated
            if not preview_updated and state["invalid_reason"] is None:
                state["invalid_reason"] = InvalidReason.PREVIEW_NOT_UPDATED.value
        state["completion"] = time.monotonic()
        gap_timer.stop()
        timeout_timer.stop()
        event_loop.quit()

    def receive_result(result: object) -> None:
        nonlocal request_id, scene_revision
        result_request_id = getattr(result, "request_id", None)
        result_revision = getattr(result, "scene_revision", None)
        if result_request_id != request_id or result_revision != scene_revision:
            state["invalid_reason"] = InvalidReason.REQUEST_ID_REVISION_MISMATCH.value
            state["result"] = result
            QTimer.singleShot(0, finish_after_event_turn)
            return
        state["matching_results"] = int(state["matching_results"]) + 1
        state["result"] = result
        if getattr(result, "success", False) is not True:
            state["error_code"] = _result_error_code(result)
            state["invalid_reason"] = (
                InvalidReason.REQUEST_CANCELLED.value
                if getattr(result, "error", None) is None
                else InvalidReason.REQUEST_FAILED.value
            )
        QTimer.singleShot(0, finish_after_event_turn)

    def timeout_request() -> None:
        if state["completion"] is not None:
            return
        state["invalid_reason"] = InvalidReason.REQUEST_TIMEOUT.value
        state["error_code"] = "render_timeout"
        state["completion"] = time.monotonic()
        gap_timer.stop()
        event_loop.quit()

    actor.result_ready.connect(receive_result)
    timeout_timer.timeout.connect(timeout_request)
    gap_timer.start()
    submission = time.monotonic()
    try:
        window.generate_button.click()
        request_id = controller.current_render_request_id
        scene_revision = controller.current_scene_revision
        if request_id is None:
            state["invalid_reason"] = InvalidReason.BENCHMARK_HARNESS_EXCEPTION.value
            state["error_code"] = "formal_ui_entry_did_not_submit"
            state["completion"] = time.monotonic()
        else:
            timeout_timer.start(round(RENDER_TIMEOUT_SECONDS * 1_000))
            event_loop.exec()
    except Exception:
        state["invalid_reason"] = InvalidReason.BENCHMARK_HARNESS_EXCEPTION.value
        state["error_code"] = "hot_sample_exception"
        state["completion"] = time.monotonic()
    finally:
        gap_timer.stop()
        timeout_timer.stop()
        try:
            actor.result_ready.disconnect(receive_result)
        except (RuntimeError, TypeError):
            pass

    completion = state["completion"]
    if not isinstance(completion, float):
        completion = time.monotonic()
        state["invalid_reason"] = InvalidReason.INCOMPLETE_MONOTONIC_RECORD.value
    try:
        timer_gap = max_gui_gap_ms(submission, ticks, completion)
    except ValueError:
        timer_gap = None
        state["invalid_reason"] = InvalidReason.INCOMPLETE_MONOTONIC_RECORD.value

    invalid_reason = state["invalid_reason"]
    success = (
        invalid_reason is None
        and state["matching_results"] == 1
        and state["preview_updated"] is True
    )
    return {
        "protocol_version": PROTOCOL_VERSION,
        "tool_version": TOOL_VERSION,
        "project_commit": project_commit,
        "batch_id": batch_id,
        "round_index": scheduled.round_index,
        "formula_id": scheduled.formula_id,
        "exact_input": scheduled.exact_input,
        "sample_kind": scheduled.sample_kind,
        "submission_monotonic": submission,
        "completion_monotonic": completion,
        "duration_ms": (completion - submission) * 1_000.0,
        "timer_max_gap_ms": timer_gap,
        "request_id": request_id,
        "scene_revision": scene_revision,
        "success": success,
        "invalid_reason": invalid_reason,
        "error_code": state["error_code"],
        "preview_updated": state["preview_updated"],
    }


def assert_native_windows_qt(platform_name: str) -> None:
    if sys.platform != "win32":
        raise RuntimeError("Formal GUI measurement requires native Windows.")
    if platform_name.lower() != "windows":
        raise RuntimeError("Formal GUI measurement forbids offscreen/minimal Qt platforms.")


def run_hot_samples(
    *,
    application: object,
    project_commit: str,
    batch_id: str,
) -> tuple[list[dict[str, object]], list[str]]:
    from PySide6.QtGui import QGuiApplication

    from math_drawing_assistant.bootstrap import create_application_runtime

    assert_native_windows_qt(QGuiApplication.platformName())
    runtime = create_application_runtime(application)
    application._math_drawing_assistant_runtime = runtime  # type: ignore[attr-defined]
    assert_formal_runtime_identity(runtime)
    assert_clipboard_untouched(runtime)
    runtime.actor.start()
    runtime.window.show()
    application.processEvents()
    if not runtime.window.isVisible() or runtime.window.windowHandle() is None:
        raise RuntimeError("Formal MainWindow is not visible on the native platform.")

    records: list[dict[str, object]] = []
    invalid_batch_reasons: list[str] = []
    try:
        for scheduled in full_render_schedule():
            if not runtime.window.isVisible():
                invalid_batch_reasons.append(InvalidBatchReason.USER_CLOSED_WINDOW.value)
                break
            record = _run_one_hot_sample(
                runtime,
                scheduled,
                project_commit=project_commit,
                batch_id=batch_id,
            )
            records.append(record)
            if record["invalid_reason"] in {
                InvalidReason.BENCHMARK_HARNESS_EXCEPTION.value,
                InvalidReason.REQUEST_TIMEOUT.value,
                InvalidReason.REQUEST_ID_REVISION_MISMATCH.value,
                InvalidReason.DUPLICATE_RESULT.value,
            }:
                break
        expected_schedule = full_render_schedule()
        observed_schedule = tuple(
            (
                record["sample_kind"],
                record["round_index"],
                record["formula_id"],
                record["exact_input"],
            )
            for record in records
        )
        expected_order = tuple(
            (
                sample.sample_kind,
                sample.round_index,
                sample.formula_id,
                sample.exact_input,
            )
            for sample in expected_schedule
        )
        if observed_schedule != expected_order:
            invalid_batch_reasons.append(InvalidBatchReason.SCHEDULE_CORRUPTED.value)
        assert_clipboard_untouched(runtime)
    finally:
        runtime.window.close()
        application.processEvents()
        shutdown_attempts = 0
        while runtime.actor.is_running and shutdown_attempts < 3:
            shutdown_attempts += 1
            runtime.controller.shutdown()
            application.processEvents()
        if runtime.actor.is_running:
            invalid_batch_reasons.append(
                InvalidBatchReason.BENCHMARK_PROCESS_CRASH.value,
            )
    return records, list(dict.fromkeys(invalid_batch_reasons))


def _redact_local_paths(text: str, replacements: Mapping[Path, str]) -> str:
    redacted = text
    ordered = sorted(
        replacements.items(),
        key=lambda item: len(str(item[0])),
        reverse=True,
    )
    flags = re.IGNORECASE if sys.platform == "win32" else 0
    for path, placeholder in ordered:
        raw = str(path).rstrip("\\/")
        if not raw:
            continue
        pieces = [piece for piece in re.split(r"[\\/]+", raw) if piece]
        if not pieces:
            continue
        prefix = r"[\\/]+" if raw.startswith(("\\", "/")) else ""
        pattern = prefix + r"[\\/]+".join(re.escape(piece) for piece in pieces)
        redacted = re.sub(pattern, lambda _match: placeholder, redacted, flags=flags)
    return redacted


def _local_path_replacements(
    *,
    mplconfigdir: Path,
    project_python: Path,
) -> dict[Path, str]:
    replacements = {
        REPOSITORY_ROOT: "<repository>",
        Path.home(): "<user-home>",
        mplconfigdir: "<external-mplconfigdir>",
        project_python: "<project-python>",
        Path(sys.prefix): "<sys-prefix>",
        Path(sys.base_prefix): "<sys-base-prefix>",
    }
    for variable in (
        "LOCALAPPDATA",
        "APPDATA",
        "TEMP",
        "TMP",
        "UV_CACHE_DIR",
        "XDG_CACHE_HOME",
    ):
        value = os.environ.get(variable)
        if value:
            replacements[Path(value)] = f"<{variable.lower()}>"
    return replacements


def run_startup_samples(
    *,
    project_python: Path,
    project_commit: str,
    batch_id: str,
    mplconfigdir: Path,
) -> tuple[list[dict[str, object]], str, str]:
    """Measure READY from direct project-Python children, never through uv."""

    records: list[dict[str, object]] = []
    stdout_log: list[str] = []
    stderr_log: list[str] = []
    command = startup_child_command(project_python)
    replacements = _local_path_replacements(
        mplconfigdir=mplconfigdir,
        project_python=project_python,
    )
    for sample_index in range(STARTUP_SAMPLE_COUNT):
        env = os.environ.copy()
        env["MPLCONFIGDIR"] = str(mplconfigdir)
        existing_pythonpath = env.get("PYTHONPATH")
        env["PYTHONPATH"] = str(REPOSITORY_ROOT) + (
            os.pathsep + existing_pythonpath if existing_pythonpath else ""
        )
        env.pop("QT_QPA_PLATFORM", None)
        start = time.monotonic()
        process = subprocess.Popen(
            command,
            cwd=REPOSITORY_ROOT,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        line_queue: queue.Queue[str | None] = queue.Queue()
        stdout_lines: list[str] = []

        def read_stdout() -> None:
            assert process.stdout is not None
            for line in process.stdout:
                stdout_lines.append(line)
                line_queue.put(line)
            line_queue.put(None)

        reader = threading.Thread(target=read_stdout, daemon=True)
        reader.start()
        ready_time: float | None = None
        ready_count = 0
        invalid_reason: str | None = None
        error_code: str | None = None
        deadline = start + STARTUP_TIMEOUT_SECONDS
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                invalid_reason = InvalidReason.REQUEST_TIMEOUT.value
                error_code = "startup_ready_timeout"
                break
            try:
                line = line_queue.get(timeout=remaining)
            except queue.Empty:
                invalid_reason = InvalidReason.REQUEST_TIMEOUT.value
                error_code = "startup_ready_timeout"
                break
            if line is None:
                invalid_reason = InvalidReason.APPLICATION_PROCESS_EXIT.value
                error_code = "child_exited_before_ready"
                break
            if line.rstrip("\r\n") == "READY":
                if ready_time is None:
                    ready_time = time.monotonic()
                    break

        if invalid_reason is not None and process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=STARTUP_EXIT_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            invalid_reason = InvalidReason.APPLICATION_PROCESS_EXIT.value
            error_code = "child_shutdown_timeout"
        reader.join(timeout=1.0)
        assert process.stderr is not None
        child_stderr = process.stderr.read()
        ready_count = sum(
            line.rstrip("\r\n") == "READY"
            for line in stdout_lines
        )
        for line in stdout_lines:
            stdout_log.append(f"startup[{sample_index}] {line.rstrip()}")
        if child_stderr:
            stderr_log.append(f"startup[{sample_index}] <child-stderr-redacted>")
        if ready_count > 1:
            invalid_reason = InvalidReason.DUPLICATE_RESULT.value
            error_code = "duplicate_ready"
        if process.returncode != 0 and invalid_reason is None:
            invalid_reason = InvalidReason.APPLICATION_PROCESS_EXIT.value
            error_code = "child_nonzero_exit"
        if ready_time is None:
            ready_time = time.monotonic()
        success = invalid_reason is None and ready_count == 1 and process.returncode == 0
        records.append(
            {
                "protocol_version": PROTOCOL_VERSION,
                "tool_version": TOOL_VERSION,
                "project_commit": project_commit,
                "batch_id": batch_id,
                "sample_index": sample_index,
                "start_monotonic": start,
                "ready_monotonic": ready_time,
                "duration_ms": (ready_time - start) * 1_000.0,
                "ready_count": ready_count,
                "child_pid": process.pid,
                "exit_code": process.returncode,
                "success": success,
                "invalid_reason": invalid_reason,
                "error_code": error_code,
            }
        )
    return (
        records,
        _redact_local_paths("\n".join(stdout_log) + "\n", replacements),
        _redact_local_paths("\n".join(stderr_log) + "\n", replacements),
    )


class _MemoryStatusEx(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def _total_memory_bytes() -> int | None:
    if sys.platform != "win32":
        return None
    status = _MemoryStatusEx()
    status.dwLength = ctypes.sizeof(status)
    if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)) == 0:
        return None
    return int(status.ullTotalPhys)


def _windows_version() -> dict[str, object]:
    data: dict[str, object] = {
        "edition": platform.win32_edition() if sys.platform == "win32" else platform.system(),
        "version": platform.version(),
        "build": platform.win32_ver()[1] if sys.platform == "win32" else platform.release(),
    }
    if sys.platform != "win32":
        return data
    try:
        import winreg

        key_path = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
            data["edition"] = winreg.QueryValueEx(key, "ProductName")[0]
            data["version"] = winreg.QueryValueEx(key, "DisplayVersion")[0]
            data["build"] = (
                f"{winreg.QueryValueEx(key, 'CurrentBuildNumber')[0]}."
                f"{winreg.QueryValueEx(key, 'UBR')[0]}"
            )
    except (FileNotFoundError, OSError):
        pass
    return data


def _power_mode() -> str:
    if sys.platform != "win32":
        return "unsupported-non-windows"
    completed = subprocess.run(
        ["powercfg", "/getactivescheme"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    line = completed.stdout.strip()
    return re.sub(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", "<guid>", line)


def _display_topology(application: object) -> tuple[tuple[object, ...], ...]:
    displays: list[tuple[object, ...]] = []
    for screen in application.screens():
        geometry = screen.geometry()
        displays.append(
            (
                screen.name(),
                geometry.x(),
                geometry.y(),
                geometry.width(),
                geometry.height(),
                round(screen.logicalDotsPerInch(), 4),
                round(screen.physicalDotsPerInch(), 4),
                round(screen.devicePixelRatio(), 4),
            )
        )
    return tuple(sorted(displays))


def _unbiased_interrupt_ms() -> float:
    if sys.platform != "win32":
        return time.monotonic() * 1_000.0
    value = ctypes.c_ulonglong()
    if ctypes.windll.kernel32.QueryUnbiasedInterruptTime(ctypes.byref(value)) == 0:
        raise OSError("QueryUnbiasedInterruptTime failed.")
    return value.value / 10_000.0


def capture_stability_snapshot(application: object) -> StabilitySnapshot:
    tick_count_ms = (
        int(ctypes.windll.kernel32.GetTickCount64())
        if sys.platform == "win32"
        else round(time.monotonic() * 1_000.0)
    )
    return StabilitySnapshot(
        displays=_display_topology(application),
        power_mode=_power_mode(),
        tick_count_ms=tick_count_ms,
        unbiased_interrupt_ms=_unbiased_interrupt_ms(),
    )


def compare_stability_snapshots(
    before: StabilitySnapshot,
    after: StabilitySnapshot,
) -> list[str]:
    reasons: list[str] = []
    if before.displays != after.displays or before.power_mode != after.power_mode:
        reasons.append(InvalidBatchReason.ENVIRONMENT_CHANGED.value)
    elapsed_tick = after.tick_count_ms - before.tick_count_ms
    elapsed_unbiased = after.unbiased_interrupt_ms - before.unbiased_interrupt_ms
    if elapsed_tick - elapsed_unbiased > SLEEP_DETECTION_TOLERANCE_MS:
        reasons.append(InvalidBatchReason.WINDOWS_SLEEP_OR_RESUME.value)
    return reasons


def collect_environment(application: object, *, project_commit: str) -> dict[str, object]:
    from PySide6.QtCore import QLibraryInfo, qVersion

    versions = {
        name: importlib.metadata.version(distribution)
        for name, distribution in {
            "PySide6": "PySide6",
            "NumPy": "numpy",
            "Matplotlib": "matplotlib",
            "SymPy": "sympy",
        }.items()
    }
    return {
        "protocol_version": PROTOCOL_VERSION,
        "windows": _windows_version(),
        "cpu": platform.processor() or os.environ.get("PROCESSOR_IDENTIFIER", "unknown"),
        "logical_processors": os.cpu_count(),
        "memory_bytes": _total_memory_bytes(),
        "python": platform.python_version(),
        "dependencies": versions,
        "qt": {
            "runtime": qVersion(),
            "library": QLibraryInfo.version().toString(),
        },
        "project_commit": project_commit,
        "display_topology": [list(display) for display in _display_topology(application)],
        "power_mode": _power_mode(),
        "mplconfigdir_policy": "shared-prepared-external-directory",
        "mplconfigdir": "<external-mplconfigdir>",
    }


def _font_cache_ready_payload(
    font_cache_manifest: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    return {
        "schema": FONT_CACHE_READY_SCHEMA,
        "schema_version": FONT_CACHE_READY_SCHEMA_VERSION,
        "tool_version": TOOL_VERSION,
        "matplotlib_version": importlib.metadata.version("matplotlib"),
        "font_cache_manifest": [dict(entry) for entry in font_cache_manifest],
    }


def _write_json_atomic(path: Path, value: Mapping[str, object]) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(_json_bytes(dict(value)))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _fontlist_files(mplconfigdir: Path) -> tuple[Path, ...]:
    matches = tuple(
        sorted(
            (
                entry
                for entry in mplconfigdir.iterdir()
                if entry.name.startswith("fontlist-v") and entry.name.endswith(".json")
            ),
            key=lambda entry: entry.name,
        ),
    )
    if not matches:
        raise ValueError("MPLCONFIGDIR has no prepared Matplotlib font cache.")
    for path in matches:
        if path.is_symlink() or not path.is_file():
            raise ValueError("MPLCONFIGDIR font cache entry is not a regular file.")
    return matches


def _validated_fontlist_bytes(path: Path) -> bytes:
    try:
        contents = path.read_bytes()
        payload = json.loads(contents.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("MPLCONFIGDIR font cache is not valid strict UTF-8 JSON.") from None
    if not isinstance(payload, dict):
        raise ValueError("MPLCONFIGDIR font cache must contain a JSON object.")
    ttflist = payload.get("ttflist")
    if (
        not isinstance(ttflist, list)
        or not ttflist
        or any(not isinstance(font_entry, dict) for font_entry in ttflist)
    ):
        raise ValueError("MPLCONFIGDIR font cache has no usable ttflist.")
    return contents


def _font_cache_manifest(mplconfigdir: Path) -> list[dict[str, object]]:
    manifest: list[dict[str, object]] = []
    for path in _fontlist_files(mplconfigdir):
        contents = _validated_fontlist_bytes(path)
        manifest.append(
            {
                "basename": path.name,
                "size": len(contents),
                "sha256": hashlib.sha256(contents).hexdigest(),
            },
        )
    return manifest


def _validate_recorded_font_cache_manifest(value: object) -> None:
    if not isinstance(value, list) or not value:
        raise ValueError("MPLCONFIGDIR cache-ready marker has no font cache manifest.")
    for entry in value:
        if not isinstance(entry, dict) or set(entry) != FONT_CACHE_MANIFEST_ENTRY_FIELDS:
            raise ValueError("MPLCONFIGDIR cache-ready marker font manifest is invalid.")
        basename = entry["basename"]
        if (
            not isinstance(basename, str)
            or "/" in basename
            or "\\" in basename
            or not basename.startswith("fontlist-v")
            or not basename.endswith(".json")
        ):
            raise ValueError("MPLCONFIGDIR cache-ready marker basename is invalid.")
        if type(entry["size"]) is not int or entry["size"] < 0:
            raise ValueError("MPLCONFIGDIR cache-ready marker size is invalid.")
        sha256 = entry["sha256"]
        if not isinstance(sha256, str) or re.fullmatch(r"[0-9a-f]{64}", sha256) is None:
            raise ValueError("MPLCONFIGDIR cache-ready marker SHA-256 is invalid.")


def validate_prepared_mplconfigdir(mplconfigdir: Path) -> Path:
    """Prove that the external Matplotlib cache matches this frozen tool."""

    resolved = validate_external_directory(mplconfigdir, purpose="MPLCONFIGDIR")
    if not resolved.is_dir():
        raise ValueError("MPLCONFIGDIR must be prepared before a formal run.")
    marker = resolved / FONT_CACHE_READY_MARKER
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("MPLCONFIGDIR cache-ready marker is missing or invalid.") from None
    if not isinstance(payload, dict) or set(payload) != FONT_CACHE_READY_REQUIRED_FIELDS:
        raise ValueError("MPLCONFIGDIR cache-ready marker does not match this tool.")
    for name, expected in {
        "schema": FONT_CACHE_READY_SCHEMA,
        "schema_version": FONT_CACHE_READY_SCHEMA_VERSION,
        "tool_version": TOOL_VERSION,
        "matplotlib_version": importlib.metadata.version("matplotlib"),
    }.items():
        if payload[name] != expected or type(payload[name]) is not type(expected):
            raise ValueError("MPLCONFIGDIR cache-ready marker does not match this tool.")
    recorded_manifest = payload["font_cache_manifest"]
    _validate_recorded_font_cache_manifest(recorded_manifest)
    actual_manifest = _font_cache_manifest(resolved)
    if recorded_manifest != actual_manifest:
        raise ValueError("MPLCONFIGDIR cache-ready marker does not match this tool.")
    return resolved


def _build_font_cache() -> None:
    from matplotlib import font_manager

    font_path = font_manager.findfont(
        font_manager.FontProperties(family=["sans-serif"]),
    )
    if not Path(font_path).is_file():
        raise RuntimeError("Matplotlib font lookup did not resolve an existing font.")


def prepare_font_cache(mplconfigdir: Path) -> None:
    resolved = validate_external_directory(mplconfigdir, purpose="MPLCONFIGDIR")
    resolved.mkdir(parents=True, exist_ok=True)
    marker = resolved / FONT_CACHE_READY_MARKER
    marker.unlink(missing_ok=True)
    os.environ["MPLCONFIGDIR"] = str(resolved)
    _build_font_cache()
    font_cache_manifest = _font_cache_manifest(resolved)
    try:
        _write_json_atomic(
            marker,
            _font_cache_ready_payload(font_cache_manifest),
        )
        print("MPLCONFIGDIR_READY", flush=True)
    except BaseException:
        marker.unlink(missing_ok=True)
        raise


def _expected_hashes_from_args(args: argparse.Namespace) -> FrozenArtifactHashes:
    return FrozenArtifactHashes(
        protocol_sha256=args.expected_protocol_sha256,
        benchmark_sha256=args.expected_benchmark_sha256,
        startup_probe_sha256=args.expected_startup_probe_sha256,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--run", action="store_true", help="Run one formal batch.")
    action.add_argument("--prepare-font-cache", action="store_true")
    action.add_argument("--print-hashes", action="store_true")
    parser.add_argument("--batch-id")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--mplconfigdir", type=Path)
    parser.add_argument("--project-python", type=Path, default=Path(sys.executable))
    parser.add_argument("--retest-of")
    parser.add_argument("--expected-protocol-sha256")
    parser.add_argument("--expected-benchmark-sha256")
    parser.add_argument("--expected-startup-probe-sha256")
    return parser


def result_bundle_status(batch_id: str) -> str:
    return f"RESULT_BUNDLE <external-result-directory> batch_id={batch_id}"


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.print_hashes:
        print(json.dumps(asdict(frozen_artifact_hashes()), indent=2, sort_keys=True))
        return 0
    if args.mplconfigdir is None:
        raise SystemExit("--mplconfigdir is required.")
    if args.prepare_font_cache:
        prepare_font_cache(args.mplconfigdir)
        return 0
    required = {
        "--batch-id": args.batch_id,
        "--output-dir": args.output_dir,
        "--expected-protocol-sha256": args.expected_protocol_sha256,
        "--expected-benchmark-sha256": args.expected_benchmark_sha256,
        "--expected-startup-probe-sha256": args.expected_startup_probe_sha256,
    }
    missing = [name for name, value in required.items() if value is None]
    if missing:
        raise SystemExit(f"Formal run missing required options: {', '.join(missing)}")
    try:
        validate_batch_identifiers(args.batch_id, args.retest_of)
    except ValueError as error:
        raise SystemExit(str(error)) from None
    output_directory = preflight_output_directory(args.output_dir)
    mplconfigdir = validate_prepared_mplconfigdir(args.mplconfigdir)
    os.environ["MPLCONFIGDIR"] = str(mplconfigdir)
    expected_hashes = _expected_hashes_from_args(args)
    verify_frozen_artifacts(expected_hashes)
    project_commit = require_clean_reviewed_repository()
    project_python = args.project_python.resolve()
    if project_python != Path(sys.executable).resolve():
        raise SystemExit("--project-python must be the active locked project interpreter.")

    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication

    if sys.platform != "win32":
        raise SystemExit("Formal measurement requires native Windows.")
    application = QApplication.instance() or QApplication(["m1-gui-benchmark"])
    try:
        assert_native_windows_qt(QGuiApplication.platformName())
    except RuntimeError as error:
        raise SystemExit(str(error)) from None
    stability_before = capture_stability_snapshot(application)

    startup_records, startup_stdout, startup_stderr = run_startup_samples(
        project_python=project_python,
        project_commit=project_commit,
        batch_id=args.batch_id,
        mplconfigdir=mplconfigdir,
    )
    render_records, invalid_batch_reasons = run_hot_samples(
        application=application,
        project_commit=project_commit,
        batch_id=args.batch_id,
    )
    stability_after = capture_stability_snapshot(application)
    invalid_batch_reasons.extend(
        compare_stability_snapshots(stability_before, stability_after),
    )
    if len(startup_records) != STARTUP_SAMPLE_COUNT:
        invalid_batch_reasons.append(InvalidBatchReason.SCHEDULE_CORRUPTED.value)
    invalid_batch_reasons = list(dict.fromkeys(invalid_batch_reasons))
    environment = collect_environment(application, project_commit=project_commit)
    result_path = write_result_bundle(
        output_directory,
        batch_id=args.batch_id,
        environment=environment,
        startup_records=startup_records,
        render_records=render_records,
        artifact_hashes=expected_hashes,
        invalid_batch_reasons=invalid_batch_reasons,
        stdout_text=startup_stdout,
        stderr_text=startup_stderr,
        retest_of=args.retest_of,
    )
    assert result_path == output_directory
    print(result_bundle_status(args.batch_id))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
