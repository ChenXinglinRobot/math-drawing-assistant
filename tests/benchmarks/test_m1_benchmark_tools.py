"""Small fake-batch tests for the frozen M1 benchmark tooling."""

from __future__ import annotations

import ast
import builtins
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from types import ModuleType, SimpleNamespace

import pytest
from PySide6.QtGui import QImage

from benchmarks import m1_gui_benchmark as benchmark
from benchmarks import m1_startup_probe as startup_probe


ROOT = Path(__file__).resolve().parents[2]


def _artifact_hashes() -> benchmark.FrozenArtifactHashes:
    return benchmark.FrozenArtifactHashes("1" * 64, "2" * 64, "3" * 64)


def _environment(*, project_commit: str = "a" * 40) -> dict[str, object]:
    return {
        "protocol_version": benchmark.PROTOCOL_VERSION,
        "project_commit": project_commit,
    }


def _minimal_fontlist_payload() -> dict[str, object]:
    return {
        "_version": 999,
        "ttflist": [
            {
                "fname": "fake-font.ttf",
                "name": "Fake Font",
                "style": "normal",
            },
        ],
    }


def _write_fake_fontlist(cache: Path, name: str = "fontlist-v999.json") -> Path:
    path = cache / name
    path.write_bytes(benchmark._json_bytes(_minimal_fontlist_payload()))
    return path


def _font_manifest_entry(path: Path) -> dict[str, object]:
    contents = path.read_bytes()
    return {
        "basename": path.name,
        "size": len(contents),
        "sha256": hashlib.sha256(contents).hexdigest(),
    }


def _write_font_cache_marker(cache: Path, fontlists: list[Path]) -> Path:
    manifest = [_font_manifest_entry(path) for path in sorted(fontlists, key=lambda path: path.name)]
    marker = cache / benchmark.FONT_CACHE_READY_MARKER
    marker.write_bytes(
        benchmark._json_bytes(benchmark._font_cache_ready_payload(manifest)),
    )
    return marker


def _formal_argv(output: Path, mplconfigdir: Path, *, batch_id: str = "batch-2") -> list[str]:
    return [
        "--run",
        "--batch-id",
        batch_id,
        "--output-dir",
        str(output),
        "--mplconfigdir",
        str(mplconfigdir),
        "--expected-protocol-sha256",
        "1" * 64,
        "--expected-benchmark-sha256",
        "2" * 64,
        "--expected-startup-probe-sha256",
        "3" * 64,
    ]


class _FakeSignal:
    def __init__(self) -> None:
        self._callbacks: list[object] = []

    def connect(self, callback: object) -> None:
        self._callbacks.append(callback)

    def disconnect(self, callback: object) -> None:
        self._callbacks.remove(callback)

    def emit(self, value: object) -> None:
        for callback in tuple(self._callbacks):
            callback(value)  # type: ignore[operator]


class _FakeActor:

    def __init__(self, executor: object) -> None:
        self.result_ready = _FakeSignal()
        self._worker = SimpleNamespace(_executor=executor)
        self._mailbox = SimpleNamespace(
            _lock=threading.Lock(),
            pending=None,
            current_token=None,
        )
        self.is_running = False

    def start(self) -> None:
        self.is_running = True


class _FakeFormulaPanel:
    def __init__(self, *, error_text: str | None = None) -> None:
        self._text = ""
        self.error_text = error_text
        self.set_count = 0

    def set_text(self, text: str) -> None:
        self.set_count += 1
        if self.error_text is not None:
            raise RuntimeError(self.error_text)
        self._text = text

    def text(self) -> str:
        return self._text


def _image(colour: int) -> QImage:
    image = QImage(2, 2, QImage.Format.Format_ARGB32)
    image.fill(colour)
    return image


def _fake_hot_runtime(
    *,
    update_preview: bool = True,
    formula_error: str | None = None,
    single_shot: object | None = None,
) -> tuple[SimpleNamespace, SimpleNamespace]:
    executor = object()
    actor = _FakeActor(executor)
    formula_panel = _FakeFormulaPanel(error_text=formula_error)
    plot_preview = SimpleNamespace(_source_image=_image(0xFF000001))
    controller = SimpleNamespace(
        task_phase=SimpleNamespace(name="IDLE"),
        current_render_request_id=None,
        current_scene_revision=0,
        last_successful_result=None,
    )
    state = SimpleNamespace(submission_count=0, visible=False)

    def submit() -> None:
        state.submission_count += 1
        request_id = state.submission_count
        controller.current_render_request_id = request_id
        controller.current_scene_revision += 1
        scene_revision = controller.current_scene_revision
        controller.task_phase = SimpleNamespace(name="RENDERING")
        result = SimpleNamespace(
            request_id=request_id,
            scene_revision=scene_revision,
            success=True,
            error=None,
        )

        def deliver() -> None:
            controller.current_render_request_id = None
            controller.task_phase = SimpleNamespace(name="IDLE")
            controller.last_successful_result = result
            if update_preview:
                plot_preview._source_image = _image(0xFF000001 + request_id)
            actor.result_ready.emit(result)

        assert single_shot is not None
        single_shot(0, deliver)  # type: ignore[operator]

    def shutdown() -> None:
        actor.is_running = False

    def show() -> None:
        state.visible = True

    def close() -> None:
        state.visible = False

    window = SimpleNamespace(
        formula_panel=formula_panel,
        plot_preview=plot_preview,
        generate_button=SimpleNamespace(click=submit),
        show=show,
        close=close,
        isVisible=lambda: state.visible,
        windowHandle=lambda: object() if state.visible else None,
    )
    controller._render_submitter = actor
    controller.shutdown = shutdown
    window._controller = controller
    runtime = SimpleNamespace(
        executor=executor,
        actor=actor,
        controller=controller,
        window=window,
        clipboard_service=SimpleNamespace(write_history=()),
    )
    return runtime, state


class _FakeQtHarness:
    def __init__(self) -> None:
        self.callbacks: list[object] = []
        self.application = SimpleNamespace(processEvents=lambda: None)

    def single_shot(self, delay: int, callback: object) -> None:
        assert delay == 0
        self.callbacks.append(callback)

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = self

        class _EventLoop:
            def __init__(self) -> None:
                self.finished = False

            def exec(self) -> None:
                while not self.finished:
                    if not harness.callbacks:
                        raise RuntimeError("fake event loop stalled")
                    callback = harness.callbacks.pop(0)
                    callback()  # type: ignore[operator]

            def quit(self) -> None:
                self.finished = True

        class _Timer:
            def __init__(self) -> None:
                self.timeout = _FakeSignal()

            @staticmethod
            def singleShot(delay: int, callback: object) -> None:
                harness.single_shot(delay, callback)

            def setTimerType(self, _timer_type: object) -> None:
                pass

            def setInterval(self, _interval: int) -> None:
                pass

            def setSingleShot(self, _single_shot: bool) -> None:
                pass

            def start(self, _interval: int | None = None) -> None:
                pass

            def stop(self) -> None:
                pass

        core = ModuleType("PySide6.QtCore")
        core.QEventLoop = _EventLoop  # type: ignore[attr-defined]
        core.QTimer = _Timer  # type: ignore[attr-defined]
        core.Qt = SimpleNamespace(TimerType=SimpleNamespace(PreciseTimer=object()))  # type: ignore[attr-defined]
        widgets = ModuleType("PySide6.QtWidgets")
        widgets.QApplication = SimpleNamespace(  # type: ignore[attr-defined]
            instance=lambda: harness.application,
        )
        monkeypatch.setitem(sys.modules, "PySide6.QtCore", core)
        monkeypatch.setitem(sys.modules, "PySide6.QtWidgets", widgets)


def _render_record(
    *,
    formula_id: str = "identity",
    exact_input: str = "x",
    round_index: int = 0,
    duration_ms: float = 10.0,
    timer_gap_ms: float = 20.0,
    success: bool = True,
    invalid_reason: str | None = None,
) -> dict[str, object]:
    return {
        "protocol_version": benchmark.PROTOCOL_VERSION,
        "tool_version": benchmark.TOOL_VERSION,
        "project_commit": "a" * 40,
        "batch_id": "fake-batch",
        "round_index": round_index,
        "formula_id": formula_id,
        "exact_input": exact_input,
        "sample_kind": "measurement",
        "submission_monotonic": 1.0,
        "completion_monotonic": 1.0 + duration_ms / 1_000.0,
        "duration_ms": duration_ms,
        "timer_max_gap_ms": timer_gap_ms,
        "request_id": round_index + 1,
        "scene_revision": round_index,
        "success": success,
        "invalid_reason": invalid_reason,
        "error_code": None,
        "preview_updated": success,
    }


def _startup_record(index: int, duration_ms: float = 100.0) -> dict[str, object]:
    return {
        "protocol_version": benchmark.PROTOCOL_VERSION,
        "tool_version": benchmark.TOOL_VERSION,
        "project_commit": "a" * 40,
        "batch_id": "fake-batch",
        "sample_index": index,
        "start_monotonic": 1.0,
        "ready_monotonic": 1.0 + duration_ms / 1_000.0,
        "duration_ms": duration_ms,
        "ready_count": 1,
        "child_pid": 1000 + index,
        "exit_code": 0,
        "success": True,
        "invalid_reason": None,
        "error_code": None,
    }


def test_startup_parent_command_uses_project_python_without_uv() -> None:
    python = Path(r"D:\project\.venv\Scripts\python.exe")
    probe = Path(r"D:\project\benchmarks\m1_startup_probe.py")
    command = benchmark.startup_child_command(python, probe)
    assert command == (str(python), "-B", str(probe))
    assert all("uv" not in part.lower() for part in command)


def test_ready_emitter_writes_exactly_once() -> None:
    stream = io.StringIO()
    emitter = startup_probe.ReadyEmitter(stream)
    assert emitter.emit_once() is True
    assert emitter.emit_once() is False
    assert stream.getvalue() == "READY\n"


def test_startup_ready_occurs_after_show_and_an_event_loop_turn() -> None:
    events: list[str] = []

    class _Input:
        def isVisible(self) -> bool:
            return True

        def isEnabled(self) -> bool:
            return True

    class _Window:
        def __init__(self) -> None:
            self.visible = False
            self.formula_panel = SimpleNamespace(_input=_Input())

        def show(self) -> None:
            events.append("show")
            self.visible = True

        def isVisible(self) -> bool:
            return self.visible

        def close(self) -> bool:
            events.append("close")
            self.visible = False
            return True

    class _Actor:
        def start(self) -> None:
            events.append("actor-start")

    class _Application:
        def __init__(self) -> None:
            self.callbacks: list[object] = []
            self.turn = 0
            self.exit_code: int | None = None

        def single_shot(self, delay: int, callback: object) -> None:
            assert delay in {0, 50}
            self.callbacks.append(callback)

        def exec(self) -> int:
            while self.exit_code is None:
                callback = self.callbacks.pop(0)
                self.turn += 1
                callback()
            return self.exit_code

        def exit(self, code: int) -> None:
            self.exit_code = code

    class _TrackingStream(io.StringIO):
        def write(self, text: str) -> int:
            events.append(f"ready-turn-{application.turn}")
            return super().write(text)

    application = _Application()
    window = _Window()
    runtime = SimpleNamespace(actor=_Actor(), window=window)
    stream = _TrackingStream()
    lifecycle = startup_probe.StartupProbeLifecycle(
        application,
        runtime,
        single_shot=application.single_shot,
        ready_emitter=startup_probe.ReadyEmitter(stream),
    )

    assert lifecycle.start() == 0
    assert stream.getvalue() == "READY\n"
    assert events == ["actor-start", "show", "ready-turn-1", "close"]


def test_gui_gap_includes_final_tick_to_completion_tail() -> None:
    assert benchmark.max_gui_gap_ms(10.0, [10.020, 10.040], 10.125) == pytest.approx(85.0)
    assert benchmark.max_gui_gap_ms(10.0, [], 10.125) == pytest.approx(125.0)


def test_retained_preview_identity_changes_only_when_retained_image_is_replaced() -> None:
    class _CopyingPreview:
        def __init__(self) -> None:
            self._source_image = _image(0xFF000001)

        @property
        def source_image(self) -> QImage:
            return self._source_image.copy()

    preview = _CopyingPreview()
    retained_key = benchmark._retained_preview_cache_key(preview)
    assert benchmark._retained_preview_cache_key(preview) == retained_key
    assert preview.source_image.cacheKey() != preview.source_image.cacheKey()

    preview._source_image = _image(0xFF000002)
    assert benchmark._retained_preview_cache_key(preview) != retained_key


def test_same_formula_in_consecutive_samples_requires_two_retained_updates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    qt = _FakeQtHarness()
    qt.install(monkeypatch)
    runtime, state = _fake_hot_runtime(single_shot=qt.single_shot)
    scheduled = benchmark.ScheduledSample("measurement", 0, "identity", "x=y")

    first = benchmark._run_one_hot_sample(
        runtime,
        scheduled,
        project_commit="a" * 40,
        batch_id="fake-batch",
    )
    second = benchmark._run_one_hot_sample(
        runtime,
        scheduled,
        project_commit="a" * 40,
        batch_id="fake-batch",
    )

    assert state.submission_count == 2
    assert first["success"] is True and first["preview_updated"] is True
    assert second["success"] is True and second["preview_updated"] is True
    assert first["request_id"] != second["request_id"]


def test_accepted_result_without_retained_preview_replacement_is_invalid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    qt = _FakeQtHarness()
    qt.install(monkeypatch)
    runtime, _state = _fake_hot_runtime(
        update_preview=False,
        single_shot=qt.single_shot,
    )
    record = benchmark._run_one_hot_sample(
        runtime,
        benchmark.ScheduledSample("measurement", 0, "identity", "x=y"),
        project_commit="a" * 40,
        batch_id="fake-batch",
    )

    assert runtime.controller.last_successful_result is not None
    assert record["success"] is False
    assert record["preview_updated"] is False
    assert record["invalid_reason"] == benchmark.InvalidReason.PREVIEW_NOT_UPDATED.value


def test_harness_exception_is_preserved_stops_schedule_and_writes_invalid_bundle(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    secret = r"secret failure at C:\Users\Alice\private"
    qt = _FakeQtHarness()
    runtime, state = _fake_hot_runtime(
        formula_error=secret,
        single_shot=qt.single_shot,
    )
    schedule = (
        benchmark.ScheduledSample("measurement", 0, "identity", "x=y"),
        benchmark.ScheduledSample("measurement", 0, "quadratic", "x^2"),
    )
    from math_drawing_assistant import bootstrap

    qt.install(monkeypatch)
    monkeypatch.setattr(benchmark, "assert_native_windows_qt", lambda _name: None)
    monkeypatch.setattr(bootstrap, "create_application_runtime", lambda _app: runtime)
    monkeypatch.setattr(benchmark, "full_render_schedule", lambda: schedule)

    records, invalid_batch_reasons = benchmark.run_hot_samples(
        application=qt.application,
        project_commit="a" * 40,
        batch_id="fake-batch",
    )

    assert len(records) == 1
    assert state.submission_count == 0
    assert runtime.window.formula_panel.set_count == 1
    assert records[0]["invalid_reason"] == (
        benchmark.InvalidReason.BENCHMARK_HARNESS_EXCEPTION.value
    )
    assert records[0]["error_code"] == "hot_sample_exception"
    assert secret not in json.dumps(records[0])
    assert invalid_batch_reasons == [benchmark.InvalidBatchReason.SCHEDULE_CORRUPTED.value]

    result = benchmark.write_result_bundle(
        tmp_path / "invalid-batch",
        batch_id="fake-batch",
        environment=_environment(),
        startup_records=[],
        render_records=records,
        artifact_hashes=_artifact_hashes(),
        invalid_batch_reasons=invalid_batch_reasons,
    )
    manifest = json.loads((result / "manifest.json").read_text(encoding="utf-8"))
    summary = json.loads((result / "summary.json").read_text(encoding="utf-8"))
    assert manifest["invalid_batch"] is True
    assert summary["threshold_conclusion"] == "invalid_batch"


def test_schema_validation_rejects_missing_fields_and_unknown_reason() -> None:
    missing = _render_record()
    del missing["preview_updated"]
    with pytest.raises(ValueError, match="missing fields"):
        benchmark.validate_render_record(missing)

    unknown = _render_record(invalid_reason="computer_felt_slow")
    with pytest.raises(ValueError, match="non-protocol"):
        benchmark.validate_render_record(unknown)


def test_slow_success_is_retained_in_statistics() -> None:
    records: list[dict[str, object]] = []
    for scenario in benchmark.FORMULA_SCENARIOS:
        for round_index in range(benchmark.MEASUREMENT_ROUNDS):
            duration = 5_000.0 if scenario.formula_id == "identity" and round_index == 0 else 10.0
            records.append(
                _render_record(
                    formula_id=scenario.formula_id,
                    exact_input=scenario.exact_input,
                    round_index=round_index,
                    duration_ms=duration,
                )
            )
    summary = benchmark.compute_summary(
        records,
        [_startup_record(index) for index in range(benchmark.STARTUP_SAMPLE_COUNT)],
    )
    identity = summary["per_formula"]["identity"]
    assert identity["valid_success_count"] == 30
    assert identity["max_ms"] == 5_000.0
    assert summary["overall_measurement"]["valid_success_count"] == 240


def test_failed_or_invalid_sample_makes_formal_percentiles_unavailable() -> None:
    records = [
        _render_record(
            formula_id=scenario.formula_id,
            exact_input=scenario.exact_input,
            round_index=round_index,
        )
        for scenario in benchmark.FORMULA_SCENARIOS
        for round_index in range(benchmark.MEASUREMENT_ROUNDS)
    ]
    failed = records[0]
    failed["success"] = False
    failed["invalid_reason"] = benchmark.InvalidReason.REQUEST_FAILED.value
    failed["preview_updated"] = False

    summary = benchmark.compute_summary(
        records,
        [_startup_record(index) for index in range(benchmark.STARTUP_SAMPLE_COUNT)],
    )

    assert summary["per_formula"][failed["formula_id"]]["p95_ms"] is None
    assert summary["overall_measurement"]["p50_ms"] is None
    assert summary["overall_measurement"]["p95_ms"] is None
    assert summary["threshold_conclusion"] == "unavailable"
    assert summary["retest_required"] is False


def test_hash_mismatch_rejects_formal_artifacts() -> None:
    expected = benchmark.FrozenArtifactHashes("1" * 64, "2" * 64, "3" * 64)
    actual = benchmark.FrozenArtifactHashes("1" * 64, "2" * 64, "4" * 64)
    with pytest.raises(ValueError, match="SHA-256"):
        benchmark.verify_frozen_artifacts(expected, actual)


def test_result_bundle_is_staged_complete_validated_and_not_overwritten(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "fake-batch"
    hashes = _artifact_hashes()
    validate = benchmark.validate_result_bundle

    def inspect_staging(
        staging: Path,
        *,
        expected_hashes: benchmark.FrozenArtifactHashes,
    ) -> None:
        assert staging != output
        assert staging.parent == output.parent
        assert output.exists() is False
        assert {path.name for path in staging.iterdir()} == benchmark.REQUIRED_RESULT_FILES
        validate(staging, expected_hashes=expected_hashes)

    monkeypatch.setattr(benchmark, "validate_result_bundle", inspect_staging)
    result = benchmark.write_result_bundle(
        output,
        batch_id="fake-batch",
        environment=_environment(),
        startup_records=[],
        render_records=[],
        artifact_hashes=hashes,
        retest_of="first-batch",
    )
    assert {path.name for path in result.iterdir()} == benchmark.REQUIRED_RESULT_FILES
    validate(result, expected_hashes=hashes)
    manifest = json.loads((result / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["retest_of"] == "first-batch"
    assert set(manifest) == benchmark.MANIFEST_REQUIRED_FIELDS
    assert set(manifest["result_file_sha256"]) == (
        benchmark.REQUIRED_RESULT_FILES.difference({"manifest.json"})
    )
    assert "manifest.json" not in manifest["result_file_sha256"]
    with pytest.raises(FileExistsError):
        benchmark.write_result_bundle(
            output,
            batch_id="fake-batch",
            environment=_environment(),
            startup_records=[],
            render_records=[],
            artifact_hashes=hashes,
        )


@pytest.mark.parametrize("extra_kind", ["file", "directory"])
def test_result_bundle_validation_rejects_any_extra_direct_entry(
    tmp_path: Path,
    extra_kind: str,
) -> None:
    hashes = _artifact_hashes()
    result = benchmark.write_result_bundle(
        tmp_path / "bundle",
        batch_id="fake-batch",
        environment=_environment(),
        startup_records=[],
        render_records=[],
        artifact_hashes=hashes,
    )
    extra = result / "unexpected"
    if extra_kind == "file":
        extra.write_text("unexpected\n", encoding="utf-8")
    else:
        extra.mkdir()

    with pytest.raises(ValueError, match="unexpected entries"):
        benchmark.validate_result_bundle(result, expected_hashes=hashes)


def test_result_bundle_validation_rejects_required_name_that_is_not_regular_file(
    tmp_path: Path,
) -> None:
    hashes = _artifact_hashes()
    result = benchmark.write_result_bundle(
        tmp_path / "bundle",
        batch_id="fake-batch",
        environment=_environment(),
        startup_records=[],
        render_records=[],
        artifact_hashes=hashes,
    )
    stdout = result / "stdout.txt"
    stdout.unlink()
    stdout.mkdir()

    with pytest.raises(ValueError, match="not a regular file"):
        benchmark.validate_result_bundle(result, expected_hashes=hashes)


def test_result_bundle_validation_rejects_missing_required_file(tmp_path: Path) -> None:
    hashes = _artifact_hashes()
    result = benchmark.write_result_bundle(
        tmp_path / "bundle",
        batch_id="fake-batch",
        environment=_environment(),
        startup_records=[],
        render_records=[],
        artifact_hashes=hashes,
    )
    (result / "stdout.txt").unlink()

    with pytest.raises(ValueError, match="missing files"):
        benchmark.validate_result_bundle(result, expected_hashes=hashes)


@pytest.mark.parametrize("missing_field", sorted(benchmark.MANIFEST_REQUIRED_FIELDS))
def test_result_bundle_validation_rejects_each_missing_manifest_field(
    tmp_path: Path,
    missing_field: str,
) -> None:
    hashes = _artifact_hashes()
    result = benchmark.write_result_bundle(
        tmp_path / missing_field,
        batch_id="fake-batch",
        environment=_environment(),
        startup_records=[],
        render_records=[],
        artifact_hashes=hashes,
    )
    manifest_path = result / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    del manifest[missing_field]
    manifest_path.write_bytes(benchmark._json_bytes(manifest))

    with pytest.raises(ValueError, match="manifest missing fields"):
        benchmark.validate_result_bundle(result, expected_hashes=hashes)


@pytest.mark.parametrize(
    ("field", "wrong_value", "message"),
    [
        ("protocol_version", "wrong-protocol", "protocol version"),
        ("tool_version", "wrong-tool", "tool version"),
        ("formal_measurement", False, "formal measurement"),
        ("startup_command", "python probe.py", "startup command"),
    ],
)
def test_result_bundle_validation_rejects_frozen_manifest_value_mismatches(
    tmp_path: Path,
    field: str,
    wrong_value: object,
    message: str,
) -> None:
    hashes = _artifact_hashes()
    result = benchmark.write_result_bundle(
        tmp_path / field,
        batch_id="fake-batch",
        environment=_environment(),
        startup_records=[],
        render_records=[],
        artifact_hashes=hashes,
    )
    manifest_path = result / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest[field] = wrong_value
    manifest_path.write_bytes(benchmark._json_bytes(manifest))

    with pytest.raises(ValueError, match=message):
        benchmark.validate_result_bundle(result, expected_hashes=hashes)


def test_result_bundle_validation_rejects_artifact_hash_or_integrity_index_schema_change(
    tmp_path: Path,
) -> None:
    hashes = _artifact_hashes()
    for change in ("artifact-hash", "self-hash"):
        result = benchmark.write_result_bundle(
            tmp_path / change,
            batch_id="fake-batch",
            environment=_environment(),
            startup_records=[],
            render_records=[],
            artifact_hashes=hashes,
        )
        manifest_path = result / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if change == "artifact-hash":
            manifest["artifact_hashes"]["protocol_sha256"] = "0" * 64
            message = "frozen artifact hash"
        else:
            manifest["result_file_sha256"]["manifest.json"] = "0" * 64
            message = "integrity index"
        manifest_path.write_bytes(benchmark._json_bytes(manifest))

        with pytest.raises(ValueError, match=message):
            benchmark.validate_result_bundle(result, expected_hashes=hashes)


@pytest.mark.parametrize(
    ("batch_id", "retest_of"),
    [("not valid/id", None), ("same-batch", "same-batch")],
)
def test_result_bundle_validation_rejects_invalid_or_self_retest_manifest_ids(
    tmp_path: Path,
    batch_id: str,
    retest_of: str | None,
) -> None:
    hashes = _artifact_hashes()
    result = benchmark.write_result_bundle(
        tmp_path / "bundle",
        batch_id="fake-batch",
        environment=_environment(),
        startup_records=[],
        render_records=[],
        artifact_hashes=hashes,
    )
    manifest_path = result / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["batch_id"] = batch_id
    manifest["retest_of"] = retest_of
    manifest_path.write_bytes(benchmark._json_bytes(manifest))

    with pytest.raises(ValueError, match="batch identifiers"):
        benchmark.validate_result_bundle(result, expected_hashes=hashes)


@pytest.mark.parametrize(
    ("invalid_batch", "reasons"),
    [
        (True, []),
        (False, [benchmark.InvalidBatchReason.ENVIRONMENT_CHANGED.value]),
        (False, ["not-a-protocol-reason"]),
        ("false", []),
    ],
)
def test_result_bundle_validation_rejects_invalid_batch_reason_inconsistency(
    tmp_path: Path,
    invalid_batch: object,
    reasons: list[str],
) -> None:
    hashes = _artifact_hashes()
    result = benchmark.write_result_bundle(
        tmp_path / "bundle",
        batch_id="fake-batch",
        environment=_environment(),
        startup_records=[],
        render_records=[],
        artifact_hashes=hashes,
    )
    manifest_path = result / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["invalid_batch"] = invalid_batch
    manifest["invalid_batch_reasons"] = reasons
    manifest_path.write_bytes(benchmark._json_bytes(manifest))

    with pytest.raises(ValueError, match="invalid.batch|invalid batch"):
        benchmark.validate_result_bundle(result, expected_hashes=hashes)


def test_result_bundle_validation_rejects_render_schedule_tampering(tmp_path: Path) -> None:
    hashes = _artifact_hashes()
    result = benchmark.write_result_bundle(
        tmp_path / "bundle",
        batch_id="fake-batch",
        environment=_environment(),
        startup_records=[],
        render_records=[],
        artifact_hashes=hashes,
    )
    manifest_path = result / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["render_schedule"]["measurement_samples"] = 239
    manifest_path.write_bytes(benchmark._json_bytes(manifest))

    with pytest.raises(ValueError, match="render schedule"):
        benchmark.validate_result_bundle(result, expected_hashes=hashes)


@pytest.mark.parametrize(
    ("record_kind", "field", "wrong_value", "message"),
    [
        ("render", "batch_id", "other-batch", "render record batch ID"),
        ("render", "tool_version", "wrong-tool", "render record tool version"),
        ("startup", "batch_id", "other-batch", "startup record batch ID"),
        ("startup", "tool_version", "wrong-tool", "startup record tool version"),
    ],
)
def test_result_bundle_validation_rejects_record_manifest_identifier_mismatch(
    tmp_path: Path,
    record_kind: str,
    field: str,
    wrong_value: str,
    message: str,
) -> None:
    render_records = [_render_record()] if record_kind == "render" else []
    startup_records = [_startup_record(0)] if record_kind == "startup" else []
    records = render_records or startup_records
    records[0][field] = wrong_value
    output = tmp_path / "bundle"

    with pytest.raises(ValueError, match=message):
        benchmark.write_result_bundle(
            output,
            batch_id="fake-batch",
            environment=_environment(),
            startup_records=startup_records,
            render_records=render_records,
            artifact_hashes=_artifact_hashes(),
        )
    assert output.exists() is False


@pytest.mark.parametrize("summary_field", ["protocol_version", "tool_version"])
def test_result_bundle_validation_rejects_summary_manifest_identifier_mismatch(
    tmp_path: Path,
    summary_field: str,
) -> None:
    hashes = _artifact_hashes()
    result = benchmark.write_result_bundle(
        tmp_path / "bundle",
        batch_id="fake-batch",
        environment=_environment(),
        startup_records=[],
        render_records=[],
        artifact_hashes=hashes,
    )
    summary_path = result / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary[summary_field] = "wrong-version"
    summary_path.write_bytes(benchmark._json_bytes(summary))
    manifest_path = result / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["result_file_sha256"]["summary.json"] = benchmark.sha256_file(summary_path)
    manifest_path.write_bytes(benchmark._json_bytes(manifest))

    with pytest.raises(ValueError, match=f"summary {summary_field.split('_')[0]} version"):
        benchmark.validate_result_bundle(result, expected_hashes=hashes)


def test_result_bundle_validation_rejects_environment_record_commit_mismatch(
    tmp_path: Path,
) -> None:
    output = tmp_path / "bundle"
    record = _render_record()
    record["project_commit"] = "b" * 40

    with pytest.raises(ValueError, match="render record project commit"):
        benchmark.write_result_bundle(
            output,
            batch_id="fake-batch",
            environment=_environment(),
            startup_records=[],
            render_records=[record],
            artifact_hashes=_artifact_hashes(),
        )
    assert output.exists() is False


@pytest.mark.parametrize("failure_stage", ["write", "validate"])
def test_result_bundle_failure_never_publishes_final_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_stage: str,
) -> None:
    output = tmp_path / "failed-batch"
    if failure_stage == "write":
        write_bytes = Path.write_bytes

        def fail_during_write(path: Path, data: bytes) -> int:
            if path.name == "render-samples.jsonl":
                raise OSError("injected write failure")
            return write_bytes(path, data)

        monkeypatch.setattr(Path, "write_bytes", fail_during_write)
    else:
        monkeypatch.setattr(
            benchmark,
            "validate_result_bundle",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("injected validation")),
        )

    with pytest.raises((OSError, ValueError)):
        benchmark.write_result_bundle(
            output,
            batch_id="failed-batch",
            environment=_environment(),
            startup_records=[],
            render_records=[],
            artifact_hashes=_artifact_hashes(),
        )

    assert output.exists() is False
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "tampered_name",
    sorted(benchmark.REQUIRED_RESULT_FILES.difference({"manifest.json"})),
)
def test_integrity_validation_detects_tampering_of_every_hashed_result_file(
    tmp_path: Path,
    tampered_name: str,
) -> None:
    hashes = _artifact_hashes()
    result = benchmark.write_result_bundle(
        tmp_path / tampered_name,
        batch_id="tamper-test",
        environment=_environment(),
        startup_records=[],
        render_records=[],
        artifact_hashes=hashes,
    )
    (result / tampered_name).write_bytes(b"tampered\n")
    with pytest.raises(ValueError, match="integrity mismatch"):
        benchmark.validate_result_bundle(result, expected_hashes=hashes)


@pytest.mark.parametrize("inside_repository", [True, False])
def test_output_preflight_rejects_before_any_measurement_function(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    inside_repository: bool,
) -> None:
    output = ROOT / "forbidden-result" if inside_repository else tmp_path / "existing"
    if not inside_repository:
        output.mkdir()
    calls: list[str] = []
    monkeypatch.setattr(
        benchmark,
        "run_startup_samples",
        lambda **_kwargs: calls.append("startup"),
    )
    monkeypatch.setattr(
        benchmark,
        "run_hot_samples",
        lambda **_kwargs: calls.append("hot"),
    )

    with pytest.raises((ValueError, FileExistsError)):
        benchmark.main(_formal_argv(output, tmp_path / "unused-mpl"))

    assert calls == []


def test_font_cache_marker_validation_rejects_unprepared_and_mismatched_directories(
    tmp_path: Path,
) -> None:
    cache = tmp_path / "mpl-cache"
    cache.mkdir()
    with pytest.raises(ValueError, match="marker"):
        benchmark.validate_prepared_mplconfigdir(cache)

    marker = cache / benchmark.FONT_CACHE_READY_MARKER
    marker.write_text("{not-json", encoding="utf-8")
    with pytest.raises(ValueError, match="marker"):
        benchmark.validate_prepared_mplconfigdir(cache)

    fontlist = _write_fake_fontlist(cache)
    payload = benchmark._font_cache_ready_payload([_font_manifest_entry(fontlist)])
    for key, wrong_value in (
        ("schema", "wrong-schema"),
        ("schema_version", 999),
        ("tool_version", "wrong-tool"),
        ("matplotlib_version", "0.0"),
    ):
        mismatched = dict(payload)
        mismatched[key] = wrong_value
        marker.write_bytes(benchmark._json_bytes(mismatched))
        with pytest.raises(ValueError, match="does not match"):
            benchmark.validate_prepared_mplconfigdir(cache)

    fontlist.unlink()
    marker.write_bytes(
        benchmark._json_bytes(
            benchmark._font_cache_ready_payload(
                [
                    {
                        "basename": "fontlist-v999.json",
                        "size": 1,
                        "sha256": "0" * 64,
                    },
                ],
            ),
        ),
    )
    with pytest.raises(ValueError, match="no prepared"):
        benchmark.validate_prepared_mplconfigdir(cache)


@pytest.mark.parametrize(
    "contents",
    [
        b"",
        b"{not-json",
        b"{}\n",
        b'{"ttflist": []}\n',
    ],
    ids=["empty", "broken-json", "empty-object", "empty-ttflist"],
)
def test_font_cache_validation_rejects_structurally_invalid_fontlists(
    tmp_path: Path,
    contents: bytes,
) -> None:
    cache = tmp_path / "mpl-cache"
    cache.mkdir()
    fontlist = cache / "fontlist-v999.json"
    fontlist.write_bytes(contents)
    _write_font_cache_marker(cache, [fontlist])

    with pytest.raises(ValueError, match="font cache|ttflist"):
        benchmark.validate_prepared_mplconfigdir(cache)


@pytest.mark.parametrize("mismatch", ["size", "sha256"])
def test_font_cache_validation_rejects_marker_size_or_hash_mismatch(
    tmp_path: Path,
    mismatch: str,
) -> None:
    cache = tmp_path / "mpl-cache"
    cache.mkdir()
    fontlist = _write_fake_fontlist(cache)
    entry = _font_manifest_entry(fontlist)
    entry[mismatch] = entry[mismatch] + 1 if mismatch == "size" else "0" * 64
    marker = cache / benchmark.FONT_CACHE_READY_MARKER
    marker.write_bytes(
        benchmark._json_bytes(benchmark._font_cache_ready_payload([entry])),
    )

    with pytest.raises(ValueError, match="does not match"):
        benchmark.validate_prepared_mplconfigdir(cache)


@pytest.mark.parametrize("manifest_change", ["omitted", "extra"])
def test_font_cache_validation_rejects_manifest_file_set_mismatch(
    tmp_path: Path,
    manifest_change: str,
) -> None:
    cache = tmp_path / "mpl-cache"
    cache.mkdir()
    first = _write_fake_fontlist(cache, "fontlist-v1.json")
    second = _write_fake_fontlist(cache, "fontlist-v2.json")
    entries = [_font_manifest_entry(first), _font_manifest_entry(second)]
    if manifest_change == "omitted":
        entries.pop()
    else:
        entries.append(
            {
                "basename": "fontlist-v3.json",
                "size": 1,
                "sha256": "0" * 64,
            },
        )
    marker = cache / benchmark.FONT_CACHE_READY_MARKER
    marker.write_bytes(
        benchmark._json_bytes(benchmark._font_cache_ready_payload(entries)),
    )

    with pytest.raises(ValueError, match="does not match"):
        benchmark.validate_prepared_mplconfigdir(cache)


def test_valid_font_cache_manifest_is_sorted_path_free_and_accepted(tmp_path: Path) -> None:
    cache = tmp_path / "mpl-cache"
    cache.mkdir()
    second = _write_fake_fontlist(cache, "fontlist-v2.json")
    first = _write_fake_fontlist(cache, "fontlist-v1.json")
    marker = _write_font_cache_marker(cache, [second, first])

    assert benchmark.validate_prepared_mplconfigdir(cache) == cache.resolve()
    marker_payload = json.loads(marker.read_text(encoding="utf-8"))
    assert marker_payload["schema_version"] == 2
    assert [
        entry["basename"]
        for entry in marker_payload["font_cache_manifest"]
    ] == ["fontlist-v1.json", "fontlist-v2.json"]
    assert str(cache.resolve()) not in marker.read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="outside"):
        benchmark.validate_prepared_mplconfigdir(ROOT / "forbidden-mpl-cache")


def test_font_cache_preflight_does_not_import_matplotlib(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache = tmp_path / "mpl-cache"
    cache.mkdir()
    fontlist = _write_fake_fontlist(cache)
    _write_font_cache_marker(cache, [fontlist])
    original_import = builtins.__import__

    def guarded_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "matplotlib" or name.startswith("matplotlib."):
            raise AssertionError("font cache preflight imported Matplotlib")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    assert benchmark.validate_prepared_mplconfigdir(cache) == cache.resolve()


def test_font_cache_validation_rejects_matching_directory_entry(tmp_path: Path) -> None:
    cache = tmp_path / "mpl-cache"
    cache.mkdir()
    (cache / "fontlist-v999.json").mkdir()
    marker = cache / benchmark.FONT_CACHE_READY_MARKER
    marker.write_bytes(
        benchmark._json_bytes(
            benchmark._font_cache_ready_payload(
                [
                    {
                        "basename": "fontlist-v999.json",
                        "size": 1,
                        "sha256": "0" * 64,
                    },
                ],
            ),
        ),
    )

    with pytest.raises(ValueError, match="regular file"):
        benchmark.validate_prepared_mplconfigdir(cache)


def test_prepare_font_cache_marks_only_a_completed_cache_and_has_one_stdout_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cache = tmp_path / "completed-cache"

    def build_cache() -> None:
        _write_fake_fontlist(cache)

    monkeypatch.setattr(benchmark, "_build_font_cache", build_cache)
    benchmark.prepare_font_cache(cache)
    assert capsys.readouterr().out == "MPLCONFIGDIR_READY\n"
    assert benchmark.validate_prepared_mplconfigdir(cache) == cache.resolve()

    prepared_fontlist = cache / "fontlist-v999.json"
    prepared_fontlist.write_bytes(
        benchmark._json_bytes(
            {
                "_version": 999,
                "ttflist": [{"fname": "changed.ttf", "name": "Changed"}],
            },
        ),
    )
    with pytest.raises(ValueError, match="does not match"):
        benchmark.validate_prepared_mplconfigdir(cache)

    failed_cache = tmp_path / "failed-cache"
    failed_cache.mkdir()
    failed_marker = failed_cache / benchmark.FONT_CACHE_READY_MARKER
    failed_marker.write_text("stale\n", encoding="utf-8")

    def fail_cache() -> None:
        raise RuntimeError("font lookup failed")

    monkeypatch.setattr(benchmark, "_build_font_cache", fail_cache)
    with pytest.raises(RuntimeError, match="font lookup"):
        benchmark.prepare_font_cache(failed_cache)
    assert capsys.readouterr().out == ""
    assert failed_marker.exists() is False


def test_prepare_font_cache_atomic_marker_failure_preserves_fontlist_and_prints_no_ready(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cache = tmp_path / "failed-marker-cache"

    def build_cache() -> None:
        _write_fake_fontlist(cache)

    def fail_replace(_source: object, _destination: object) -> None:
        raise OSError("injected marker replace failure")

    monkeypatch.setattr(benchmark, "_build_font_cache", build_cache)
    monkeypatch.setattr(benchmark.os, "replace", fail_replace)
    with pytest.raises(OSError, match="replace failure"):
        benchmark.prepare_font_cache(cache)

    assert capsys.readouterr().out == ""
    assert (cache / benchmark.FONT_CACHE_READY_MARKER).exists() is False
    assert (cache / "fontlist-v999.json").is_file()
    assert not list(cache.glob(f".{benchmark.FONT_CACHE_READY_MARKER}.*.tmp"))


def test_retest_identifiers_use_one_rule_and_reject_self_retest() -> None:
    benchmark.validate_batch_identifiers("batch-2", "batch-1")
    with pytest.raises(ValueError, match="different earlier batch"):
        benchmark.validate_batch_identifiers("same", "same")
    with pytest.raises(ValueError, match="--retest-of"):
        benchmark.validate_batch_identifiers("batch-2", "not valid/id")
    with pytest.raises(SystemExit, match="different earlier batch"):
        benchmark.main(
            _formal_argv(Path(r"C:\external\new"), Path(r"C:\external\mpl"), batch_id="same")
            + ["--retest-of", "same"],
        )


def test_local_path_redaction_covers_windows_case_and_separator_variants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    replacements = {
        Path(r"C:\Users\Alice\repo"): "<repository>",
        Path(r"C:\Users\Alice"): "<user-home>",
        Path(r"C:\Project\.venv\Scripts\python.exe"): "<project-python>",
        Path(r"C:\Project\.venv"): "<sys-prefix>",
        Path(r"C:\Cache\mpl"): "<external-mplconfigdir>",
        Path(r"C:\Cache\uv"): "<uv-cache-dir>",
    }
    text = (
        r"repo=C:/USERS/alice/REPO/file.py "
        r"home=c:\users\ALICE\note.txt "
        r"python=c:/project/.VENV/scripts/PYTHON.EXE "
        r"prefix=C:\PROJECT\.venv\Lib "
        r"mpl=c:/CACHE/MPL/fontlist-v1.json "
        r"cache=C:\cache\UV\archive ordinary=unchanged"
    )

    redacted = benchmark._redact_local_paths(text, replacements)

    assert "C:/USERS/alice/REPO" not in redacted
    assert r"c:\users\ALICE" not in redacted
    for placeholder in replacements.values():
        assert placeholder in redacted
    assert "ordinary=unchanged" in redacted
    assert "<repository>/file.py" in redacted


def test_path_replacement_set_and_result_status_never_expose_result_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache = tmp_path / "cache"
    python = tmp_path / "venv" / "python.exe"
    monkeypatch.setenv("UV_CACHE_DIR", str(tmp_path / "uv-cache"))
    replacements = benchmark._local_path_replacements(
        mplconfigdir=cache,
        project_python=python,
    )
    assert benchmark.REPOSITORY_ROOT in replacements
    assert Path.home() in replacements
    assert cache in replacements
    assert python in replacements
    assert Path(sys.prefix) in replacements
    assert Path(sys.base_prefix) in replacements
    assert Path(os.environ["UV_CACHE_DIR"]) in replacements

    output = tmp_path / "sensitive-result"
    status = benchmark.result_bundle_status("batch-2")
    assert status == "RESULT_BUNDLE <external-result-directory> batch_id=batch-2"
    assert str(output) not in status


def test_dirty_git_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def dirty_status(command: list[str], **_kwargs: object) -> SimpleNamespace:
        calls.append(command)
        return SimpleNamespace(stdout="?? local-change\n")

    monkeypatch.setattr(subprocess, "run", dirty_status)
    with pytest.raises(RuntimeError, match="clean worktree"):
        benchmark.require_clean_reviewed_repository()
    assert calls == [["git", "status", "--porcelain"]]


def test_cli_without_run_never_calls_formal_measurement_functions(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(benchmark, "frozen_artifact_hashes", _artifact_hashes)

    def forbidden(**_kwargs: object) -> None:
        raise AssertionError("formal measurement function was called")

    monkeypatch.setattr(benchmark, "run_startup_samples", forbidden)
    monkeypatch.setattr(benchmark, "run_hot_samples", forbidden)
    assert benchmark.main(["--print-hashes"]) == 0
    assert json.loads(capsys.readouterr().out)["benchmark_sha256"] == "2" * 64


def test_non_native_qt_rejection_needs_no_real_gui(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    with pytest.raises(RuntimeError, match="native Windows"):
        benchmark.assert_native_windows_qt("windows")
    monkeypatch.setattr(sys, "platform", "win32")
    with pytest.raises(RuntimeError, match="offscreen/minimal"):
        benchmark.assert_native_windows_qt("offscreen")


def test_runtime_identity_requires_the_factory_actor_and_executor() -> None:
    executor = object()
    actor = SimpleNamespace(_worker=SimpleNamespace(_executor=executor))
    controller = SimpleNamespace(_render_submitter=actor)
    window = SimpleNamespace(_controller=controller)
    runtime = SimpleNamespace(
        executor=executor,
        actor=actor,
        controller=controller,
        window=window,
    )
    benchmark.assert_formal_runtime_identity(runtime)
    actor._worker._executor = object()
    with pytest.raises(RuntimeError, match="factory Executor"):
        benchmark.assert_formal_runtime_identity(runtime)


def test_benchmark_source_has_no_clipboard_or_copy_invocation() -> None:
    source = (ROOT / "benchmarks" / "m1_gui_benchmark.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_calls = {"write_candidate", "setImage", "image", "mimeData", "clear"}
    called_attributes = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    loaded_names = {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
    }
    assert called_attributes.isdisjoint(forbidden_calls)
    assert "copy_requested" not in loaded_names


def test_hot_tool_only_calls_the_shared_runtime_factory() -> None:
    source = (ROOT / "benchmarks" / "m1_gui_benchmark.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    called_names = [
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]
    assert called_names.count("create_application_runtime") == 1
    assert "RenderActor" not in called_names
    assert "SceneRenderExecutor" not in called_names


def test_tools_delay_production_imports_until_after_mplconfigdir_guards() -> None:
    benchmark_source = (ROOT / "benchmarks" / "m1_gui_benchmark.py").read_text(encoding="utf-8")
    probe_source = (ROOT / "benchmarks" / "m1_startup_probe.py").read_text(encoding="utf-8")
    assert "from math_drawing_assistant.bootstrap" not in benchmark_source.split(
        "def run_hot_samples", 1
    )[0]
    assert probe_source.index('os.environ.get("MPLCONFIGDIR")') < probe_source.index(
        "from math_drawing_assistant.bootstrap import create_application_runtime"
    )
