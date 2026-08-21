"""Stage 15-C proof of the exact production composition and render chain."""

from __future__ import annotations

import dataclasses
import gc
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import sys
from queue import Queue
from threading import Event, Lock, get_ident, local
from typing import Callable
import weakref

import pytest
from PySide6.QtCore import (
    QObject,
    QEventLoop,
    QThread,
    QTimer,
    Qt,
    Slot,
    qInstallMessageHandler,
)
from PySide6.QtWidgets import QApplication
from shiboken6 import delete as delete_qt_object

from math_drawing_assistant import app_controller as controller_module
from math_drawing_assistant import bootstrap
from math_drawing_assistant.app_controller import (
    AppController,
    RenderResultDisposition,
)
from math_drawing_assistant.engine import renderer
from math_drawing_assistant.engine import scene_executor as scene_executor_module
from math_drawing_assistant.engine.samplers import SamplingCancelled
from math_drawing_assistant.engine.scene_executor import SceneRenderExecutor
from math_drawing_assistant.models import (
    ConcretePlotType,
    ErrorCode,
    PlotSceneResult,
    TaskPhase,
)
from math_drawing_assistant.workers.cancellation import CancellationToken
from math_drawing_assistant.workers.render_actor import RenderActor
import math_drawing_assistant.workers.render_actor as actor_module


_GUARD_TIMEOUT_MS = 15_000
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _spin_until(
    predicate: Callable[[], bool],
    *,
    timeout_ms: int = _GUARD_TIMEOUT_MS,
) -> None:
    """Process Qt events until one guarded condition becomes true."""

    if predicate():
        return
    loop = QEventLoop()
    poll = QTimer()
    guard = QTimer()
    guard.setSingleShot(True)

    def stop_if_ready() -> None:
        if predicate():
            loop.quit()

    poll.timeout.connect(stop_if_ready)
    guard.timeout.connect(loop.quit)
    poll.start(1)
    guard.start(timeout_ms)
    loop.exec()
    poll.stop()
    guard.stop()
    assert predicate(), "Qt event-loop guard timeout"


def _submit(runtime: object, formula: str) -> tuple[object, CancellationToken]:
    controller = runtime.controller
    request = controller.create_m1_render_request(
        formula_text=formula,
        viewport_mode="auto",
        x_min=-10.0,
        x_max=10.0,
        y_min=-10.0,
        y_max=10.0,
        aspect_request="default",
        show_grid=True,
        image_width=400,
        image_height=300,
    )
    token = controller._current_render_token
    assert isinstance(token, CancellationToken)
    return request, token


def _collect_public_results(actor: RenderActor) -> list[PlotSceneResult]:
    results: list[PlotSceneResult] = []

    def collect(value: object) -> None:
        assert isinstance(value, PlotSceneResult)
        results.append(value)

    actor.result_ready.connect(collect, Qt.ConnectionType.DirectConnection)
    return results


@pytest.fixture
def stage15c_qapp() -> QApplication:
    """Own and deterministically destroy this module's QApplication."""

    existing = QApplication.instance()
    created_here = existing is None
    application = existing or QApplication(sys.argv)
    yield application
    if created_here:
        application.processEvents()
        application.quit()
        delete_qt_object(application)
        assert QApplication.instance() is None


@pytest.fixture
def runtime_factory(stage15c_qapp: QApplication):
    runtimes: list[object] = []

    def create() -> object:
        runtime = bootstrap.create_application_runtime(stage15c_qapp)
        started = Event()
        runtime.actor._thread.started.connect(
            started.set,
            Qt.ConnectionType.DirectConnection,
        )
        runtime.actor.start()
        assert started.wait(_GUARD_TIMEOUT_MS / 1_000)
        runtimes.append(runtime)
        return runtime

    yield create

    for runtime in reversed(runtimes):
        if runtime.actor.is_running:
            assert runtime.actor.shutdown(5_000) is True
        runtime.window.deleteLater()
    stage15c_qapp.processEvents()
    gc.collect()
    assert actor_module._timed_out_keepalive_count() == 0


def test_bootstrap_builds_the_exact_single_production_object_graph(
    runtime_factory,
) -> None:
    runtime = runtime_factory()

    assert type(runtime.executor) is SceneRenderExecutor
    assert type(runtime.actor) is RenderActor
    assert type(runtime.controller) is AppController
    assert runtime.actor._worker._executor is runtime.executor
    assert runtime.controller._render_submitter is runtime.actor
    assert runtime.window.controller is runtime.controller
    assert runtime.actor._worker.thread() is runtime.actor._thread
    qthreads = [value for value in vars(runtime.actor).values() if type(value) is QThread]
    assert qthreads == [runtime.actor._owner_thread, runtime.actor._thread]
    assert runtime.actor._owner_thread is QThread.currentThread()
    assert runtime.actor._thread is not runtime.actor._owner_thread

    assert runtime.controller.shutdown() is True
    assert runtime.actor.is_running is False
    assert runtime.controller.shutdown() is True


def test_fresh_bootstrap_import_does_not_load_legacy_root_entry_points() -> None:
    project_root = Path(__file__).resolve().parents[1]
    probe = """
import json
import sys

import math_drawing_assistant.bootstrap

print(json.dumps({
    "legacy_main_window_loaded": "main_window" in sys.modules,
    "legacy_plot_engine_loaded": "plot_engine" in sys.modules,
    "package_main_window_loaded": (
        "math_drawing_assistant.ui.main_window" in sys.modules
    ),
}))
"""
    environment = os.environ.copy()
    environment.setdefault("QT_QPA_PLATFORM", "offscreen")
    completed = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=project_root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "legacy_main_window_loaded": False,
        "legacy_plot_engine_loaded": False,
        "package_main_window_loaded": True,
    }


class _ResourceTracker:
    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.references: dict[str, list[weakref.ReferenceType[object]]] = {
            "figure": [],
            "canvas": [],
            "bytes_io": [],
        }
        self.thread_ids: dict[str, list[int]] = {
            "figure": [],
            "canvas": [],
            "bytes_io": [],
        }
        self.created_buffer_ids: list[int] = []
        self.closed_buffer_ids: set[int] = set()
        self._lock = Lock()
        figure_type = renderer.Figure
        canvas_type = renderer.FigureCanvasAgg
        tracker = self

        class TrackingFigure(figure_type):
            def __init__(self, *args: object, **kwargs: object) -> None:
                tracker.thread_ids["figure"].append(get_ident())
                super().__init__(*args, **kwargs)
                tracker.references["figure"].append(weakref.ref(self))

        class TrackingCanvas(canvas_type):
            def __init__(self, figure: object) -> None:
                tracker.thread_ids["canvas"].append(get_ident())
                super().__init__(figure)
                tracker.references["canvas"].append(weakref.ref(self))

        class TrackingBytesIO(BytesIO):
            def __init__(self) -> None:
                tracker.thread_ids["bytes_io"].append(get_ident())
                super().__init__()
                tracker.created_buffer_ids.append(id(self))
                tracker.references["bytes_io"].append(weakref.ref(self))

            def close(self) -> None:
                if not self.closed:
                    with tracker._lock:
                        tracker.closed_buffer_ids.add(id(self))
                super().close()

        monkeypatch.setattr(renderer, "Figure", TrackingFigure)
        monkeypatch.setattr(renderer, "FigureCanvasAgg", TrackingCanvas)
        monkeypatch.setattr(renderer, "BytesIO", TrackingBytesIO)

    def assert_released(self) -> None:
        gc.collect()
        assert set(self.created_buffer_ids) == self.closed_buffer_ids
        assert all(
            reference() is None
            for references in self.references.values()
            for reference in references
        )


def test_explicit_and_geometry_use_one_actor_thread_and_release_agg_resources(
    runtime_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gui_thread_id = get_ident()
    tracker = _ResourceTracker(monkeypatch)
    executor_calls: list[tuple[int, CancellationToken, int]] = []
    renderer_calls: list[tuple[int, CancellationToken, int, int]] = []
    renderer_active = 0
    renderer_max_active = 0
    stats_lock = Lock()
    render_context = local()
    real_execute = SceneRenderExecutor.execute
    real_renderer = scene_executor_module.render_sampled_curve_png

    def observe_execute(
        self: SceneRenderExecutor,
        request: object,
        cancellation: CancellationToken,
    ) -> PlotSceneResult:
        executor_calls.append((request.request_id, cancellation, get_ident()))
        render_context.request_id = request.request_id
        render_context.token = cancellation
        try:
            return real_execute(self, request, cancellation)
        finally:
            del render_context.request_id
            del render_context.token

    def observe_renderer(*args: object, **kwargs: object):
        nonlocal renderer_active, renderer_max_active
        request_thread = get_ident()
        request_id = render_context.request_id
        cancellation = kwargs["cancellation_probe"]
        assert cancellation is render_context.token
        with stats_lock:
            renderer_active += 1
            renderer_max_active = max(renderer_max_active, renderer_active)
        try:
            outcome = real_renderer(*args, **kwargs)
            assert type(outcome) is bytes
            renderer_calls.append(
                (request_id, cancellation, request_thread, len(outcome)),
            )
            return outcome
        finally:
            with stats_lock:
                renderer_active -= 1

    monkeypatch.setattr(SceneRenderExecutor, "execute", observe_execute)
    monkeypatch.setattr(
        scene_executor_module,
        "render_sampled_curve_png",
        observe_renderer,
    )
    runtime = runtime_factory()
    public_results = _collect_public_results(runtime.actor)

    requests_and_tokens: list[tuple[object, CancellationToken]] = []
    for formula in ("y=x^2", "x^2+y^2=4"):
        requests_and_tokens.append(_submit(runtime, formula))
        expected_count = len(requests_and_tokens)
        _spin_until(lambda: len(public_results) == expected_count)

    results = public_results[:2]
    assert [result.item_results[0].concrete_plot_type for result in results] == [
        ConcretePlotType.EXPLICIT_FUNCTION,
        ConcretePlotType.CIRCLE,
    ]
    assert all(result.success for result in results)
    assert all(result.png_bytes and result.png_bytes.startswith(_PNG_SIGNATURE) for result in results)
    assert [call[0] for call in executor_calls] == [
        request.request_id for request, _ in requests_and_tokens
    ]
    assert [call[1] for call in executor_calls] == [
        token for _, token in requests_and_tokens
    ]

    worker_thread_ids = {call[2] for call in executor_calls}
    assert len(worker_thread_ids) == 1
    worker_thread_id = next(iter(worker_thread_ids))
    assert worker_thread_id != gui_thread_id
    assert [call[0] for call in renderer_calls] == [
        request.request_id for request, _ in requests_and_tokens
    ]
    assert [call[1] for call in renderer_calls] == [
        token for _, token in requests_and_tokens
    ]
    assert {call[2] for call in renderer_calls} == {worker_thread_id}
    assert renderer_max_active == 1
    assert all(
        thread_id == worker_thread_id
        for thread_ids in tracker.thread_ids.values()
        for thread_id in thread_ids
    )
    tracker.assert_released()

    continuation, continuation_token = _submit(runtime, "y=x+1")
    _spin_until(lambda: len(public_results) == 3)
    assert public_results[-1].request_id == continuation.request_id
    assert public_results[-1].success is True
    assert executor_calls[-1][1] is continuation_token
    tracker.assert_released()


def test_production_latest_wins_skips_middle_and_publishes_only_final(
    runtime_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_entered = Event()
    release_first = Event()
    entered_ids: list[int] = []
    calls: list[tuple[int, CancellationToken, PlotSceneResult]] = []
    active = 0
    max_active = 0
    stats_lock = Lock()
    real_execute = SceneRenderExecutor.execute

    def blocked_execute(
        self: SceneRenderExecutor,
        request: object,
        cancellation: CancellationToken,
    ) -> PlotSceneResult:
        nonlocal active, max_active
        entered_ids.append(request.request_id)
        with stats_lock:
            active += 1
            max_active = max(max_active, active)
        try:
            if len(entered_ids) == 1:
                first_entered.set()
                assert release_first.wait(_GUARD_TIMEOUT_MS / 1_000)
            result = real_execute(self, request, cancellation)
            calls.append((request.request_id, cancellation, result))
            return result
        finally:
            with stats_lock:
                active -= 1

    monkeypatch.setattr(SceneRenderExecutor, "execute", blocked_execute)
    runtime = runtime_factory()
    public_results = _collect_public_results(runtime.actor)

    first, first_token = _submit(runtime, "y=x^2")
    assert first_entered.wait(_GUARD_TIMEOUT_MS / 1_000)
    second, second_token = _submit(runtime, "x^2+y^2=4")
    final, final_token = _submit(runtime, "y=x+3")
    release_first.set()
    _spin_until(lambda: len(public_results) == 1)

    assert first_token.is_cancelled() is True
    assert second_token.is_cancelled() is True
    assert final_token.is_cancelled() is False
    assert entered_ids == [first.request_id, final.request_id]
    assert second.request_id not in entered_ids
    assert max_active == 1
    assert len(calls) == 2
    first_result = calls[0][2]
    assert first_result.request_id == first.request_id
    assert first_result.success is False
    assert first_result.error is None
    assert first_result.png_bytes is None
    assert first_result.item_results == ()
    assert [result.request_id for result in public_results] == [final.request_id]
    assert runtime.controller.last_successful_result is public_results[0]
    assert runtime.controller.current_render_request_id is None
    assert runtime.controller.task_phase is TaskPhase.IDLE


@dataclasses.dataclass(frozen=True)
class _DispositionRecord:
    result: PlotSceneResult
    disposition: RenderResultDisposition
    retained_before: PlotSceneResult | None
    retained_after: PlotSceneResult | None


def _observe_controller_dispositions(
    monkeypatch: pytest.MonkeyPatch,
) -> list[_DispositionRecord]:
    records: list[_DispositionRecord] = []
    original = AppController.handle_render_result

    def observe(
        self: AppController,
        result: PlotSceneResult,
    ) -> RenderResultDisposition:
        before = self.last_successful_result
        disposition = original(self, result)
        records.append(
            _DispositionRecord(
                result=result,
                disposition=disposition,
                retained_before=before,
                retained_after=self.last_successful_result,
            ),
        )
        return disposition

    monkeypatch.setattr(AppController, "handle_render_result", observe)
    return records


class _WorkerResultRecorder(QObject):
    def __init__(self) -> None:
        super().__init__()
        self.results: Queue[tuple[PlotSceneResult, int]] = Queue()

    @Slot(object)
    def record(self, value: object) -> None:
        assert isinstance(value, PlotSceneResult)
        self.results.put((value, get_ident()))


@pytest.mark.parametrize("obsolete_gate", ("request_id", "scene_revision"))
def test_prelinearized_real_result_is_rejected_by_each_controller_gate(
    runtime_factory,
    monkeypatch: pytest.MonkeyPatch,
    obsolete_gate: str,
) -> None:
    dispositions = _observe_controller_dispositions(monkeypatch)
    runtime = runtime_factory()
    public_results = _collect_public_results(runtime.actor)

    baseline_request, _ = _submit(runtime, "y=x^2")
    _spin_until(lambda: len(public_results) == 1)
    baseline = runtime.controller.last_successful_result
    assert baseline is public_results[0]
    assert baseline.request_id == baseline_request.request_id
    dispositions.clear()

    worker_recorder = _WorkerResultRecorder()
    runtime.actor._worker._result_ready.connect(
        worker_recorder.record,
        Qt.ConnectionType.DirectConnection,
    )
    obsolete_request, _ = _submit(runtime, "x^2+y^2=4")
    worker_result, worker_thread_id = worker_recorder.results.get(
        timeout=_GUARD_TIMEOUT_MS / 1_000,
    )
    assert worker_result.request_id == obsolete_request.request_id
    assert worker_thread_id != get_ident()
    assert runtime.actor._mailbox.current_token is None

    if obsolete_gate == "request_id":
        current_request, _ = _submit(runtime, "y=x+5")
        _spin_until(lambda: len(dispositions) == 2)
        assert dispositions[0].result is worker_result
        assert dispositions[0].disposition is RenderResultDisposition.IGNORED_OBSOLETE
        assert dispositions[0].retained_before is baseline
        assert dispositions[0].retained_after is baseline
        assert dispositions[1].result.request_id == current_request.request_id
        assert dispositions[1].disposition is RenderResultDisposition.ACCEPTED_SUCCESS
    else:
        previous_revision = runtime.controller.current_scene_revision
        runtime.controller.mark_scene_edited()
        assert runtime.controller.current_scene_revision == previous_revision + 1
        _spin_until(lambda: len(dispositions) == 1)
        assert dispositions[0].result is worker_result
        assert dispositions[0].disposition is RenderResultDisposition.IGNORED_OBSOLETE
        assert dispositions[0].retained_before is baseline
        assert dispositions[0].retained_after is baseline
        assert runtime.controller.last_successful_result is baseline


def test_current_failures_are_redacted_preserve_baseline_and_recover(
    runtime_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dispositions = _observe_controller_dispositions(monkeypatch)
    injected_formula = "y=123456789*x+987654321"
    secret = "STAGE15C-DO-NOT-LEAK-4f29"
    private_path = r"C:\private\teacher-formula.txt"
    real_execute = SceneRenderExecutor.execute
    executed: list[tuple[int, SceneRenderExecutor]] = []

    def inject_once(
        self: SceneRenderExecutor,
        request: object,
        cancellation: CancellationToken,
    ) -> PlotSceneResult:
        executed.append((request.request_id, self))
        if request.items[0].input_text == injected_formula:
            raise RuntimeError(
                f"Traceback: {secret}; {private_path}; {injected_formula}",
            )
        return real_execute(self, request, cancellation)

    monkeypatch.setattr(SceneRenderExecutor, "execute", inject_once)
    runtime = runtime_factory()
    public_results = _collect_public_results(runtime.actor)

    baseline_request, _ = _submit(runtime, "y=x^2")
    _spin_until(lambda: len(public_results) == 1)
    baseline = public_results[0]
    assert runtime.controller.last_successful_result is baseline

    typed_request, _ = _submit(runtime, "log(x)")
    _spin_until(lambda: len(public_results) == 2)
    typed_failure = public_results[1]
    assert typed_failure.request_id == typed_request.request_id
    assert typed_failure.error is not None
    assert typed_failure.error.code is ErrorCode.LOG_REQUIRES_BASE
    assert dispositions[-1].disposition is RenderResultDisposition.HANDLED_CURRENT_FAILURE
    assert runtime.controller.last_successful_result is baseline

    injected_request, _ = _submit(runtime, injected_formula)
    _spin_until(lambda: len(public_results) == 3)
    internal_failure = public_results[2]
    notice = runtime.controller.last_error_notice
    assert internal_failure.request_id == injected_request.request_id
    assert internal_failure.error is not None
    assert internal_failure.error.code is ErrorCode.INTERNAL_ERROR
    assert dispositions[-1].disposition is RenderResultDisposition.HANDLED_CURRENT_FAILURE
    assert runtime.controller.last_successful_result is baseline
    assert notice is internal_failure.error
    public_text = "\n".join(
        (repr(internal_failure), repr(internal_failure.error), repr(notice)),
    )
    for forbidden in (secret, private_path, injected_formula, "Traceback"):
        assert forbidden not in public_text

    recovery_request, _ = _submit(runtime, "x^2+y^2=4")
    _spin_until(lambda: len(public_results) == 4)
    recovery = public_results[3]
    assert recovery.request_id == recovery_request.request_id
    assert recovery.success is True
    assert runtime.controller.last_successful_result is recovery
    assert dispositions[-1].disposition is RenderResultDisposition.ACCEPTED_SUCCESS
    assert all(executor is runtime.executor for _, executor in executed)
    assert runtime.actor._worker._executor is runtime.executor
    assert [request_id for request_id, _ in executed] == [
        baseline_request.request_id,
        typed_request.request_id,
        injected_request.request_id,
        recovery_request.request_id,
    ]


def test_production_shutdown_timeout_closes_gates_and_suppresses_late_result(
    stage15c_qapp: QApplication,
    runtime_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_entered = Event()
    release_current = Event()
    thread_finished = Event()
    entered_ids: list[int] = []
    real_execute = SceneRenderExecutor.execute

    def block_current(
        self: SceneRenderExecutor,
        request: object,
        cancellation: CancellationToken,
    ) -> PlotSceneResult:
        entered_ids.append(request.request_id)
        if request.items[0].input_text == "y=x^3":
            current_entered.set()
            assert release_current.wait(_GUARD_TIMEOUT_MS / 1_000)
        return real_execute(self, request, cancellation)

    monkeypatch.setattr(SceneRenderExecutor, "execute", block_current)
    messages: list[str] = []
    messages_lock = Lock()

    def capture_message(message_type, context, message: str) -> None:
        del message_type, context
        with messages_lock:
            messages.append(message)

    previous_handler = qInstallMessageHandler(capture_message)
    runtime = runtime_factory()
    runtime.actor._thread.finished.connect(
        thread_finished.set,
        Qt.ConnectionType.DirectConnection,
    )
    public_results = _collect_public_results(runtime.actor)
    try:
        baseline_request, _ = _submit(runtime, "y=x^2")
        _spin_until(lambda: len(public_results) == 1)
        baseline = public_results[0]
        assert baseline.request_id == baseline_request.request_id

        current_request, current_token = _submit(runtime, "y=x^3")
        assert current_entered.wait(_GUARD_TIMEOUT_MS / 1_000)
        pending_request, pending_token = _submit(runtime, "x^2+y^2=4")
        runtime.actor._shutdown_timeout_ms = 0

        assert runtime.controller.shutdown() is False
        assert current_token.is_cancelled() is True
        assert pending_token.is_cancelled() is True
        assert entered_ids == [baseline_request.request_id, current_request.request_id]
        assert pending_request.request_id not in entered_ids
        assert runtime.controller.task_phase is TaskPhase.SHUTTING_DOWN
        assert runtime.controller.current_render_request_id is None
        assert runtime.controller.current_recognition_request_id is None
        assert runtime.controller._current_render_token is None
        assert runtime.actor._mailbox.stop_requested is True
        assert runtime.actor._mailbox.result_gate_closed is True
        assert runtime.actor.submit(pending_request, CancellationToken()) is False
        with pytest.raises(RuntimeError, match="shutting down"):
            _submit(runtime, "y=x+9")
        assert actor_module._timed_out_keepalive_count() == 1

        release_current.set()
        assert thread_finished.wait(_GUARD_TIMEOUT_MS / 1_000)
        _spin_until(lambda: actor_module._timed_out_keepalive_count() == 0)
        stage15c_qapp.processEvents()
        assert runtime.actor.is_running is False
        assert public_results == [baseline]
        assert runtime.controller.last_successful_result is baseline
        assert runtime.controller.shutdown() is True
        assert runtime.controller.shutdown() is True
        with messages_lock:
            assert not any(
                "QThread: Destroyed while thread is still running" in message
                for message in messages
            )
    finally:
        release_current.set()
        qInstallMessageHandler(previous_handler)


class _SamplerGateToken(CancellationToken):
    """Real token subclass paused at the first production sampler poll."""

    def __init__(self) -> None:
        super().__init__()
        self.entered = Event()
        self.released = Event()
        self.observed_cancelled = Event()
        self._armed = False
        self._blocked = False
        self._lock = Lock()

    def arm(self) -> None:
        with self._lock:
            self._armed = True

    def release(self) -> None:
        self.released.set()

    def is_cancelled(self) -> bool:
        already_cancelled = super().is_cancelled()
        should_block = False
        with self._lock:
            if self._armed and not self._blocked and not already_cancelled:
                self._blocked = True
                should_block = True
        if should_block:
            self.entered.set()
            assert self.released.wait(_GUARD_TIMEOUT_MS / 1_000)
        observed = super().is_cancelled()
        if should_block and observed:
            self.observed_cancelled.set()
        return observed


@pytest.mark.parametrize(
    "formula",
    (
        "x^2/9+y^2/4=1",
        "x^2/9-y^2/4=1",
        "x^2=4*y",
    ),
    ids=("oval", "hyperbola", "parabola"),
)
def test_real_geometry_cancellation_keeps_one_token_and_no_partial_result(
    runtime_factory,
    monkeypatch: pytest.MonkeyPatch,
    formula: str,
) -> None:
    runtime = runtime_factory()
    public_results = _collect_public_results(runtime.actor)
    baseline_request, _ = _submit(runtime, "y=x^2")
    _spin_until(lambda: len(public_results) == 1)
    baseline = public_results[0]
    assert baseline.request_id == baseline_request.request_id

    created_tokens: list[_SamplerGateToken] = []

    class ControllerSamplerGateToken(_SamplerGateToken):
        def __init__(self) -> None:
            super().__init__()
            created_tokens.append(self)

    sampler_records: list[tuple[object, CancellationToken, object]] = []
    executor_records: list[tuple[object, CancellationToken, PlotSceneResult]] = []
    executor_finished = Event()
    real_sampler = scene_executor_module._sample_geometry_curve_for_scene
    real_execute = SceneRenderExecutor.execute

    def observe_sampler(
        plan: object,
        *,
        cancellation_probe: CancellationToken | None = None,
    ):
        assert isinstance(cancellation_probe, _SamplerGateToken)
        cancellation_probe.arm()
        outcome = real_sampler(
            plan,
            cancellation_probe=cancellation_probe,
        )
        sampler_records.append((plan, cancellation_probe, outcome))
        return outcome

    def observe_execute(
        self: SceneRenderExecutor,
        request: object,
        cancellation: CancellationToken,
    ) -> PlotSceneResult:
        result = real_execute(self, request, cancellation)
        executor_records.append((request, cancellation, result))
        executor_finished.set()
        return result

    monkeypatch.setattr(
        controller_module,
        "CancellationToken",
        ControllerSamplerGateToken,
    )
    monkeypatch.setattr(
        scene_executor_module,
        "_sample_geometry_curve_for_scene",
        observe_sampler,
    )
    monkeypatch.setattr(SceneRenderExecutor, "execute", observe_execute)

    request, token = _submit(runtime, formula)
    assert created_tokens == [token]
    assert type(token) is ControllerSamplerGateToken
    assert token.entered.wait(_GUARD_TIMEOUT_MS / 1_000)
    assert runtime.controller._current_render_token is token
    assert runtime.actor._mailbox.current_token is token
    try:
        assert runtime.controller.cancel_active_task() is True
        assert token.is_cancelled() is True
        token.release()
        assert executor_finished.wait(_GUARD_TIMEOUT_MS / 1_000)
        _spin_until(lambda: runtime.actor._mailbox.current_token is None)
    finally:
        token.release()

    assert token.observed_cancelled.is_set()
    assert len(sampler_records) == 1
    plan, sampler_token, sampler_outcome = sampler_records[0]
    del plan
    assert sampler_token is token
    assert type(sampler_outcome) is SamplingCancelled
    assert sampler_outcome.item_id == request.items[0].item_id
    assert [field.name for field in dataclasses.fields(sampler_outcome)] == ["item_id"]
    for forbidden in ("x", "y", "ranges", "warnings", "diagnostics"):
        assert not hasattr(sampler_outcome, forbidden)

    assert len(executor_records) == 1
    executor_request, executor_token, executor_outcome = executor_records[0]
    assert executor_request is request
    assert executor_token is token
    assert executor_outcome.request_id == request.request_id
    assert executor_outcome.scene_revision == request.scene_revision
    assert executor_outcome.success is False
    assert executor_outcome.error is None
    assert executor_outcome.png_bytes is None
    assert executor_outcome.item_results == ()
    assert executor_outcome.resolved_viewport is None
    assert executor_outcome.warnings == ()
    assert executor_outcome.diagnostics is None
    assert executor_outcome.elapsed_ms == ()
    assert public_results == [baseline]
    assert runtime.controller.last_successful_result is baseline
    assert runtime.controller.current_render_request_id is None
    assert runtime.controller.task_phase is TaskPhase.IDLE
