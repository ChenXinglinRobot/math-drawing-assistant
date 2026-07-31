"""Stage 10D evidence for the real formal Engine -> sampler -> Agg actor path.

The executor in this module is deliberately test-only.  It composes only the
published Engine/model APIs and lets the production RenderActor provide the
thread, mailbox, cancellation, relay, and shutdown boundaries.
"""

from __future__ import annotations

from collections import defaultdict
import gc
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import Event, Lock, get_ident
from typing import Callable
import weakref

from matplotlib._pylab_helpers import Gcf
import pytest
from PySide6.QtCore import (
    QEventLoop,
    QObject,
    QThread,
    QTimer,
    Qt,
    Signal,
    Slot,
)
from PySide6.QtWidgets import QApplication

from math_drawing_assistant.engine import (
    RenderCancelled,
    RenderPlanBuilder,
    SampledExplicitFunction,
    SamplingCancelled,
    analyze_explicit_function,
    build_explicit_scene_spec,
    render_explicit_png,
    resolve_single_explicit_viewport,
    sample_explicit_function,
)
from math_drawing_assistant.engine import renderer
from math_drawing_assistant.models import (
    ErrorCode,
    ErrorInfo,
    InputSource,
    PlotItemRequest,
    PlotKind,
    PlotSceneRequest,
    PlotSceneResult,
    RenderPlan,
    ViewportMode,
    ViewportRequest,
)
from math_drawing_assistant.workers import CancellationToken
from math_drawing_assistant.workers.render_actor import RenderActor


_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_GUARD_TIMEOUT_MS = 10_000
_STAGES = ("analyzer", "spec", "viewport", "plan", "sampler", "renderer")


def _request(
    request_id: int,
    text: str = "y=x^2",
    *,
    revision: int | None = None,
    image_width: int = 320,
    image_height: int = 240,
    viewport: ViewportRequest | None = None,
) -> PlotSceneRequest:
    return PlotSceneRequest(
        request_id=request_id,
        scene_revision=request_id if revision is None else revision,
        items=(
            PlotItemRequest(
                item_id=f"item-{request_id}",
                input_text=text,
                input_source=InputSource.MANUAL,
                requested_plot_kind=PlotKind.EXPLICIT_FUNCTION,
                display_order=0,
            ),
        ),
        viewport=viewport
        or ViewportRequest(
            mode=ViewportMode.MANUAL,
            x_min=-5,
            x_max=5,
            y_min=-5,
            y_max=25,
        ),
        image_width=image_width,
        image_height=image_height,
        dpi=96,
        show_grid=True,
        show_legend=False,
    )


def _negative_log_request(request_id: int) -> PlotSceneRequest:
    return _request(
        request_id,
        "log(x)",
        viewport=ViewportRequest(
            mode=ViewportMode.MANUAL,
            x_min=-10,
            x_max=-1,
            y_min=-10,
            y_max=10,
        ),
    )


def _failed(request: PlotSceneRequest, error: ErrorInfo) -> PlotSceneResult:
    return PlotSceneResult(
        request_id=request.request_id,
        scene_revision=request.scene_revision,
        success=False,
        error=error,
    )


def _cancelled(request: PlotSceneRequest) -> PlotSceneResult:
    """Return an error-code-free sentinel that the Actor's token gate suppresses."""

    return PlotSceneResult(
        request_id=request.request_id,
        scene_revision=request.scene_revision,
        success=False,
    )


class _StageGateToken(CancellationToken):
    """A real token with a deterministic test gate inside one public stage."""

    def __init__(
        self,
        stage: str,
        *,
        pass_polls: int = 0,
        resume_on_cancel: bool = True,
    ) -> None:
        super().__init__()
        if stage not in {"sampler", "renderer"}:
            raise ValueError("stage gate must target sampler or renderer")
        self.stage = stage
        self.pass_polls = pass_polls
        self.resume_on_cancel = resume_on_cancel
        self.entered = Event()
        self.resumed = Event()
        self.observed_cancelled = Event()
        self._armed = False
        self._blocked = False
        self._lock = Lock()

    def arm(self, stage: str) -> None:
        if stage != self.stage:
            return
        with self._lock:
            self._armed = True

    def release(self) -> None:
        self.resumed.set()

    def cancel(self) -> None:
        super().cancel()
        if self.resume_on_cancel:
            self.resumed.set()

    def is_cancelled(self) -> bool:
        already_cancelled = super().is_cancelled()
        should_block = False
        with self._lock:
            if self._armed and not self._blocked and not already_cancelled:
                if self.pass_polls:
                    self.pass_polls -= 1
                else:
                    self._blocked = True
                    should_block = True
        if should_block:
            self.entered.set()
            assert self.resumed.wait(_GUARD_TIMEOUT_MS / 1_000), (
                f"{self.stage} gate guard timeout"
            )
        observed = super().is_cancelled()
        if should_block and observed:
            self.observed_cancelled.set()
        return observed


class _FormalAggExecutor:
    """Test-only composition of the published formal pipeline."""

    def __init__(self, *, raise_after_sampler_ids: set[int] | None = None) -> None:
        self.stage_threads: dict[int, dict[str, list[int]]] = defaultdict(
            lambda: defaultdict(list),
        )
        self.executed_ids: list[int] = []
        self.completed_ids: list[int] = []
        self.failure_ids: list[int] = []
        self.cancellation_outcomes: list[tuple[int, str]] = []
        self.sampled_array_refs: list[weakref.ReferenceType[object]] = []
        self.max_matplotlib_entries = 0
        self._matplotlib_entries = 0
        self._stats_lock = Lock()
        self._tokens: list[_StageGateToken] = []
        self._raise_after_sampler_ids = set(raise_after_sampler_ids or ())

    def _record(self, request_id: int, stage: str) -> None:
        self.stage_threads[request_id][stage].append(get_ident())

    def _failure(
        self,
        request: PlotSceneRequest,
        error: ErrorInfo,
    ) -> PlotSceneResult:
        self.failure_ids.append(request.request_id)
        return _failed(request, error)

    def _arm(self, cancellation: CancellationToken, stage: str) -> None:
        if isinstance(cancellation, _StageGateToken):
            cancellation.arm(stage)
            if cancellation not in self._tokens:
                self._tokens.append(cancellation)

    def _cancelled_at_boundary(
        self,
        request: PlotSceneRequest,
        cancellation: CancellationToken,
        completed_stage: str,
    ) -> PlotSceneResult | None:
        if not cancellation.is_cancelled():
            return None
        self.cancellation_outcomes.append(
            (request.request_id, f"{completed_stage}-boundary"),
        )
        return _cancelled(request)

    def execute(
        self,
        request: PlotSceneRequest,
        cancellation: CancellationToken,
    ) -> PlotSceneResult:
        self.executed_ids.append(request.request_id)
        if len(request.items) != 1:
            raise AssertionError("the stage-10 executor requires one formal item")
        item = request.items[0]

        self._record(request.request_id, "analyzer")
        validated = analyze_explicit_function(item.input_text)
        if isinstance(validated, ErrorInfo):
            return self._failure(request, validated)
        boundary_cancellation = self._cancelled_at_boundary(
            request,
            cancellation,
            "analyzer",
        )
        if boundary_cancellation is not None:
            return boundary_cancellation

        self._record(request.request_id, "spec")
        scene = build_explicit_scene_spec(item, validated)
        if isinstance(scene, ErrorInfo):
            return self._failure(request, scene)
        boundary_cancellation = self._cancelled_at_boundary(
            request,
            cancellation,
            "spec",
        )
        if boundary_cancellation is not None:
            return boundary_cancellation

        self._record(request.request_id, "viewport")
        viewport_resolution = resolve_single_explicit_viewport(
            scene,
            request.viewport,
        )
        if viewport_resolution.error is not None:
            return self._failure(request, viewport_resolution.error)
        resolved_viewport = viewport_resolution.viewport
        assert resolved_viewport is not None
        boundary_cancellation = self._cancelled_at_boundary(
            request,
            cancellation,
            "viewport",
        )
        if boundary_cancellation is not None:
            return boundary_cancellation

        self._record(request.request_id, "plan")
        plan_or_error = RenderPlanBuilder().build(
            scene,
            resolved_viewport,
            image_width=request.image_width,
            image_height=request.image_height,
            dpi=request.dpi,
            show_grid=request.show_grid,
            show_legend=request.show_legend,
        )
        if isinstance(plan_or_error, ErrorInfo):
            return self._failure(request, plan_or_error)
        assert isinstance(plan_or_error, RenderPlan)
        plan = plan_or_error
        boundary_cancellation = self._cancelled_at_boundary(
            request,
            cancellation,
            "plan",
        )
        if boundary_cancellation is not None:
            return boundary_cancellation

        self._record(request.request_id, "sampler")
        self._arm(cancellation, "sampler")
        sampling_outcome = sample_explicit_function(
            plan,
            cancellation_probe=cancellation,
        )
        if isinstance(sampling_outcome, SampledExplicitFunction):
            self.sampled_array_refs.extend(
                (
                    weakref.ref(sampling_outcome.x),
                    weakref.ref(sampling_outcome.y),
                    weakref.ref(sampling_outcome.segment_ranges),
                ),
            )
        if request.request_id in self._raise_after_sampler_ids:
            raise RuntimeError("stage-10 injected post-sampler failure")

        self._record(request.request_id, "renderer")
        self._arm(cancellation, "renderer")
        with self._stats_lock:
            self._matplotlib_entries += 1
            self.max_matplotlib_entries = max(
                self.max_matplotlib_entries,
                self._matplotlib_entries,
            )
        try:
            render_outcome = render_explicit_png(
                plan,
                sampling_outcome,
                cancellation_probe=cancellation,
            )
        finally:
            with self._stats_lock:
                self._matplotlib_entries -= 1

        if isinstance(sampling_outcome, SamplingCancelled):
            assert isinstance(render_outcome, RenderCancelled)
            self.cancellation_outcomes.append((request.request_id, "sampler"))
            return _cancelled(request)
        if isinstance(render_outcome, RenderCancelled):
            self.cancellation_outcomes.append((request.request_id, "renderer"))
            return _cancelled(request)
        if isinstance(render_outcome, ErrorInfo):
            return self._failure(request, render_outcome)
        assert isinstance(render_outcome, bytes)

        self.completed_ids.append(request.request_id)
        return PlotSceneResult(
            request_id=request.request_id,
            scene_revision=request.scene_revision,
            success=True,
            png_bytes=render_outcome,
            resolved_viewport=resolved_viewport,
        )

    def release_all(self) -> None:
        for token in self._tokens:
            token.release()
            token.cancel()


class _ResultReceiver(QObject):
    received = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.results: list[PlotSceneResult] = []
        self.thread_ids: list[int] = []

    @Slot(object)
    def receive(self, value: object) -> None:
        assert isinstance(value, PlotSceneResult)
        self.results.append(value)
        self.thread_ids.append(get_ident())
        self.received.emit()


def _spin_until(
    predicate: Callable[[], bool],
    *,
    timeout_ms: int = _GUARD_TIMEOUT_MS,
) -> None:
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


@pytest.fixture
def actor_factory(qapp: QApplication):
    resources: list[tuple[RenderActor, _FormalAggExecutor]] = []

    def create(
        executor: _FormalAggExecutor,
        *,
        shutdown_timeout_ms: int = 5_000,
    ) -> RenderActor:
        actor = RenderActor(
            executor,
            shutdown_timeout_ms=shutdown_timeout_ms,
        )
        started = Event()
        actor._thread.started.connect(
            started.set,
            Qt.ConnectionType.DirectConnection,
        )
        actor.start()
        assert started.wait(_GUARD_TIMEOUT_MS / 1_000)
        resources.append((actor, executor))
        return actor

    yield create

    for actor, executor in reversed(resources):
        executor.release_all()
        assert actor.shutdown(5_000) is True
        assert actor.is_running is False
    qapp.processEvents()
    gc.collect()


class _ResourceTracker:
    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.references: dict[str, list[weakref.ReferenceType[object]]] = {
            "figure": [],
            "canvas": [],
            "bytes_io": [],
        }
        self.buffer_close_count = 0
        self._lock = Lock()
        figure_type = renderer.Figure
        canvas_type = renderer.FigureCanvasAgg
        tracker = self

        class TrackingFigure(figure_type):
            def __init__(self, *args: object, **kwargs: object) -> None:
                super().__init__(*args, **kwargs)
                tracker.references["figure"].append(weakref.ref(self))

        class TrackingCanvas(canvas_type):
            def __init__(self, figure: object) -> None:
                super().__init__(figure)
                tracker.references["canvas"].append(weakref.ref(self))

        class TrackingBytesIO(BytesIO):
            def __init__(self) -> None:
                super().__init__()
                tracker.references["bytes_io"].append(weakref.ref(self))

            def close(self) -> None:
                if not self.closed:
                    with tracker._lock:
                        tracker.buffer_close_count += 1
                super().close()

        monkeypatch.setattr(renderer, "Figure", TrackingFigure)
        monkeypatch.setattr(renderer, "FigureCanvasAgg", TrackingCanvas)
        monkeypatch.setattr(renderer, "BytesIO", TrackingBytesIO)

    def assert_released(self, *, expected_buffers: int) -> None:
        gc.collect()
        assert self.buffer_close_count == expected_buffers
        assert all(
            reference() is None
            for references in self.references.values()
            for reference in references
        )


def _connect_receiver(actor: RenderActor) -> _ResultReceiver:
    receiver = _ResultReceiver()
    actor.result_ready.connect(
        receiver.receive,
        Qt.ConnectionType.DirectConnection,
    )
    return receiver


def _assert_png(result: PlotSceneResult, width: int, height: int) -> None:
    assert result.success is True
    assert result.png_bytes is not None
    assert result.png_bytes[:8] == _PNG_SIGNATURE
    assert result.png_bytes[12:16] == b"IHDR"
    assert int.from_bytes(result.png_bytes[16:20], "big") == width
    assert int.from_bytes(result.png_bytes[20:24], "big") == height


def test_real_actor_runs_full_formal_chain_on_one_worker_and_relays_to_gui(
    actor_factory,
) -> None:
    gui_thread_id = get_ident()
    gui_qthread = QThread.currentThread()
    executor = _FormalAggExecutor()
    actor = actor_factory(executor)
    receiver = _connect_receiver(actor)
    request = _request(101, revision=37, image_width=641, image_height=377)
    token = CancellationToken()

    assert actor.submit(request, token) is True
    _spin_until(lambda: len(receiver.results) == 1)

    result = receiver.results[0]
    assert result.request_id == request.request_id
    assert result.scene_revision == request.scene_revision
    _assert_png(result, 641, 377)
    stage_threads = executor.stage_threads[request.request_id]
    assert tuple(stage_threads) == _STAGES
    worker_ids = {
        thread_id
        for stage in _STAGES
        for thread_id in stage_threads[stage]
    }
    assert len(worker_ids) == 1
    assert gui_thread_id not in worker_ids
    assert receiver.thread_ids == [gui_thread_id]
    assert actor._owner_thread is gui_qthread
    assert actor._thread is not gui_qthread
    assert executor.max_matplotlib_entries == 1


def test_latest_wins_cancels_formal_sampler_skips_middle_and_recovers(
    actor_factory,
) -> None:
    executor = _FormalAggExecutor()
    actor = actor_factory(executor)
    receiver = _connect_receiver(actor)
    current = _StageGateToken("sampler", resume_on_cancel=False)
    middle = CancellationToken()
    latest = CancellationToken()

    assert actor.submit(_request(201), current) is True
    _spin_until(current.entered.is_set)
    assert actor.submit(_request(202), middle) is True
    assert actor.submit(_request(203), latest) is True
    current.release()
    _spin_until(lambda: len(receiver.results) == 1)

    assert current.observed_cancelled.is_set()
    assert middle.is_cancelled() is True
    assert latest.is_cancelled() is False
    assert executor.executed_ids == [201, 203]
    assert executor.cancellation_outcomes == [(201, "sampler")]
    assert [result.request_id for result in receiver.results] == [203]
    _assert_png(receiver.results[0], 320, 240)
    assert executor.max_matplotlib_entries == 1


def test_renderer_cancellation_releases_resources_and_next_task_succeeds(
    actor_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tracker = _ResourceTracker(monkeypatch)
    executor = _FormalAggExecutor()
    actor = actor_factory(executor)
    receiver = _connect_receiver(actor)
    current = _StageGateToken("renderer", pass_polls=1)

    assert actor.submit(_request(301), current) is True
    _spin_until(current.entered.is_set)
    assert len(tracker.references["figure"]) == 1
    assert len(tracker.references["canvas"]) == 1
    assert len(tracker.references["bytes_io"]) == 1
    assert actor.submit(_request(302), CancellationToken()) is True
    _spin_until(lambda: len(receiver.results) == 1)

    assert current.observed_cancelled.is_set()
    assert executor.cancellation_outcomes == [(301, "renderer")]
    assert [result.request_id for result in receiver.results] == [302]
    _assert_png(receiver.results[0], 320, 240)
    assert Gcf.get_all_fig_managers() == []
    tracker.assert_released(expected_buffers=2)


def test_formal_log_domain_failure_then_valid_task_succeeds(actor_factory) -> None:
    executor = _FormalAggExecutor()
    actor = actor_factory(executor)
    receiver = _connect_receiver(actor)

    assert actor.submit(_negative_log_request(401), CancellationToken()) is True
    _spin_until(lambda: len(receiver.results) == 1)
    failure = receiver.results[0]
    assert failure.request_id == 401
    assert failure.success is False
    assert failure.error is not None
    assert failure.error.code is ErrorCode.LOG_REQUIRES_BASE

    assert actor.submit(_request(402), CancellationToken()) is True
    _spin_until(lambda: len(receiver.results) == 2)
    assert [result.request_id for result in receiver.results] == [401, 402]
    _assert_png(receiver.results[1], 320, 240)
    assert executor.executed_ids == [401, 402]


def test_shutdown_during_real_renderer_is_bounded_cooperative_and_silent(
    actor_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tracker = _ResourceTracker(monkeypatch)
    executor = _FormalAggExecutor()
    actor = actor_factory(executor, shutdown_timeout_ms=5_000)
    receiver = _connect_receiver(actor)
    token = _StageGateToken("renderer", pass_polls=1)

    assert actor.submit(_request(501), token) is True
    _spin_until(token.entered.is_set)
    assert actor.shutdown() is True

    assert token.observed_cancelled.is_set()
    assert token.is_cancelled() is True
    assert actor.is_running is False
    assert receiver.results == []
    assert executor.cancellation_outcomes == [(501, "renderer")]
    assert Gcf.get_all_fig_managers() == []
    tracker.assert_released(expected_buffers=1)


def test_twenty_real_renders_release_figures_buffers_and_sample_arrays(
    actor_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tracker = _ResourceTracker(monkeypatch)
    executor = _FormalAggExecutor()
    actor = actor_factory(executor)
    receiver = _connect_receiver(actor)

    for request_id in range(601, 621):
        assert actor.submit(_request(request_id), CancellationToken()) is True
        expected_count = request_id - 600
        _spin_until(lambda: len(receiver.results) == expected_count)
        assert Gcf.get_all_fig_managers() == []

    assert len(receiver.results) == 20
    assert all(result.success for result in receiver.results)
    assert executor.executed_ids == list(range(601, 621))
    assert executor.completed_ids == list(range(601, 621))
    assert executor.max_matplotlib_entries == 1
    worker_ids = {
        thread_id
        for request_id in range(601, 621)
        for stage in _STAGES
        for thread_id in executor.stage_threads[request_id][stage]
    }
    assert len(worker_ids) == 1
    gc.collect()
    assert all(reference() is None for reference in executor.sampled_array_refs)
    tracker.assert_released(expected_buffers=20)


def test_fresh_process_actor_and_renderer_imports_keep_pyplot_and_gui_backends_out(
) -> None:
    project_root = Path(__file__).resolve().parents[2]
    probe = """
import json
import sys

import math_drawing_assistant.workers.render_actor

actor_loaded_matplotlib = any(
    name == "matplotlib" or name.startswith("matplotlib.")
    for name in sys.modules
)
import math_drawing_assistant.engine.renderer
import matplotlib

print(json.dumps({
    "actor_loaded_matplotlib": actor_loaded_matplotlib,
    "backend": matplotlib.get_backend(auto_select=False),
    "backend_agg_loaded": "matplotlib.backends.backend_agg" in sys.modules,
    "backend_qtagg_loaded": "matplotlib.backends.backend_qtagg" in sys.modules,
    "interactive": matplotlib.is_interactive(),
    "pyplot_loaded": "matplotlib.pyplot" in sys.modules,
    "pyside6_loaded": any(
        name == "PySide6" or name.startswith("PySide6.")
        for name in sys.modules
    ),
}))
"""
    environment = os.environ.copy()
    environment.pop("MPLBACKEND", None)
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
    evidence = json.loads(completed.stdout)
    assert evidence == {
        "actor_loaded_matplotlib": False,
        "backend": None,
        "backend_agg_loaded": True,
        "backend_qtagg_loaded": False,
        "interactive": False,
        "pyplot_loaded": False,
        "pyside6_loaded": True,
    }


def test_qapp_event_loop_processes_repeated_timers_during_real_actor_work(
    actor_factory,
) -> None:
    gui_thread_id = get_ident()
    executor = _FormalAggExecutor()
    actor = actor_factory(executor)
    receiver = _connect_receiver(actor)
    token = _StageGateToken("sampler")
    ticks: list[int] = []
    timer = QTimer()
    timer.setInterval(0)

    def observe_gui_tick() -> None:
        if not token.entered.is_set():
            return
        assert token.resumed.is_set() is False
        assert actor.is_running is True
        ticks.append(get_ident())
        if len(ticks) == 3:
            timer.stop()
            token.release()

    timer.timeout.connect(observe_gui_tick)
    timer.start()
    try:
        assert actor.submit(_request(701), token) is True
        _spin_until(lambda: len(receiver.results) == 1)
    finally:
        timer.stop()
        token.release()

    assert ticks == [gui_thread_id, gui_thread_id, gui_thread_id]
    assert token.is_cancelled() is False
    _assert_png(receiver.results[0], 320, 240)


def test_exception_after_formal_sampling_isolated_and_actor_continues(
    actor_factory,
) -> None:
    executor = _FormalAggExecutor(raise_after_sampler_ids={801})
    actor = actor_factory(executor)
    receiver = _connect_receiver(actor)

    assert actor.submit(_request(801), CancellationToken()) is True
    _spin_until(lambda: len(receiver.results) == 1)
    failure = receiver.results[0]
    assert failure.request_id == 801
    assert failure.success is False
    assert failure.error is not None
    assert failure.error.code is ErrorCode.INTERNAL_ERROR
    assert tuple(executor.stage_threads[801]) == _STAGES[:-1]

    assert actor.submit(_request(802), CancellationToken()) is True
    _spin_until(lambda: len(receiver.results) == 2)
    assert executor.executed_ids == [801, 802]
    _assert_png(receiver.results[1], 320, 240)
    gc.collect()
    assert all(reference() is None for reference in executor.sampled_array_refs)


def _run_visible_desktop_probe() -> int:
    """Launch the non-offscreen, human-observed stage-10D acceptance window."""

    from PySide6.QtCore import qInstallMessageHandler
    from PySide6.QtGui import QCloseEvent, QPixmap
    from PySide6.QtWidgets import (
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMainWindow,
        QPlainTextEdit,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )

    if os.environ.get("QT_QPA_PLATFORM", "").lower() == "offscreen":
        raise RuntimeError("manual acceptance refuses the offscreen Qt platform")

    application = QApplication.instance() or QApplication(sys.argv)
    application.setApplicationName("Math Drawing Assistant Stage 10D Desktop Probe")
    qt_messages: list[str] = []
    qt_messages_lock = Lock()

    def capture_qt_message(message_type, context, message: str) -> None:
        del message_type, context
        with qt_messages_lock:
            qt_messages.append(message)

    previous_handler = qInstallMessageHandler(capture_qt_message)

    class DesktopProbeWindow(QMainWindow):
        def __init__(self) -> None:
            super().__init__()
            self.setWindowTitle("Stage 10D — Real RenderActor Desktop Acceptance")
            self.resize(1_020, 760)
            self._request_id = 1_000
            self._executor = _FormalAggExecutor()
            self._actor = RenderActor(self._executor, shutdown_timeout_ms=5_000)
            self._actor.result_ready.connect(self._receive_result)
            self._actor.start()
            self._error_recovery_pending = False
            self._closing = False

            self._formula = QLineEdit("y=x^2")
            self._formula.setAccessibleName("Formula input")
            self._submit_button = QPushButton("Submit 800×600")
            self._rapid_button = QPushButton("Rapid latest-wins (heavy + 4)")
            self._error_button = QPushButton("Formal error → recovery")
            self._heavy_button = QPushButton("Start heavy 4096×4096")
            self._status = QLabel("Ready — real Actor thread is running")
            self._heartbeat = QLabel("GUI heartbeat: 0")
            self._warning_status = QLabel("QThread running-destruction warnings: 0")
            self._preview = QLabel("PNG preview appears here")
            self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._preview.setMinimumHeight(360)
            self._history = QPlainTextEdit()
            self._history.setReadOnly(True)
            self._history.setAccessibleName("Acceptance history")

            controls = QHBoxLayout()
            for button in (
                self._submit_button,
                self._rapid_button,
                self._error_button,
                self._heavy_button,
            ):
                controls.addWidget(button)
            layout = QVBoxLayout()
            layout.addWidget(
                QLabel(
                    "Visible Windows probe: formal Engine → sampler → Agg in one "
                    "persistent RenderActor QThread",
                ),
            )
            layout.addWidget(self._formula)
            layout.addLayout(controls)
            layout.addWidget(self._status)
            layout.addWidget(self._heartbeat)
            layout.addWidget(self._warning_status)
            layout.addWidget(self._preview, 1)
            layout.addWidget(self._history, 1)
            central = QWidget()
            central.setLayout(layout)
            self.setCentralWidget(central)

            self._submit_button.clicked.connect(self._submit_formula)
            self._formula.returnPressed.connect(self._submit_formula)
            self._rapid_button.clicked.connect(self._start_rapid_latest_wins)
            self._error_button.clicked.connect(self._start_error_recovery)
            self._heavy_button.clicked.connect(self._submit_heavy)

            self._heartbeat_count = 0
            self._heartbeat_timer = QTimer(self)
            self._heartbeat_timer.setInterval(100)
            self._heartbeat_timer.timeout.connect(self._tick)
            self._heartbeat_timer.start()
            self._append(
                f"START pid={os.getpid()} gui_tid={get_ident()} "
                f"platform={os.environ.get('QT_QPA_PLATFORM', '<default>')}",
            )

        def _append(self, message: str) -> None:
            self._history.appendPlainText(message)
            self._history.verticalScrollBar().setValue(
                self._history.verticalScrollBar().maximum(),
            )

        @Slot()
        def _tick(self) -> None:
            self._heartbeat_count += 1
            self._heartbeat.setText(f"GUI heartbeat: {self._heartbeat_count}")
            with qt_messages_lock:
                warning_count = sum(
                    "QThread: Destroyed while thread is still running" in message
                    for message in qt_messages
                )
            self._warning_status.setText(
                f"QThread running-destruction warnings: {warning_count}",
            )

        def _next_request(
            self,
            text: str,
            *,
            image_width: int,
            image_height: int,
        ) -> PlotSceneRequest:
            self._request_id += 1
            if text == "log(x)":
                return _negative_log_request(self._request_id)
            return _request(
                self._request_id,
                text,
                image_width=image_width,
                image_height=image_height,
            )

        def _submit(
            self,
            text: str,
            *,
            image_width: int,
            image_height: int,
        ) -> int:
            request = self._next_request(
                text,
                image_width=image_width,
                image_height=image_height,
            )
            accepted = self._actor.submit(request, CancellationToken())
            self._status.setText(
                f"Rendering request {request.request_id}: {text} "
                f"({image_width}×{image_height})",
            )
            self._append(
                f"SUBMIT id={request.request_id} accepted={accepted} "
                f"formula={text} size={image_width}x{image_height} "
                f"gui_tid={get_ident()}",
            )
            return request.request_id

        @Slot()
        def _submit_formula(self) -> None:
            text = self._formula.text().strip() or "y=x^2"
            self._submit(text, image_width=800, image_height=600)

        @Slot()
        def _submit_heavy(self) -> None:
            self._submit(
                "sin(1000*x)+cos(997*x)",
                image_width=4_096,
                image_height=4_096,
            )

        @Slot()
        def _start_rapid_latest_wins(self) -> None:
            first_id = self._submit(
                "sin(1000*x)+cos(997*x)",
                image_width=4_096,
                image_height=4_096,
            )

            def supersede() -> None:
                submitted = [
                    self._submit(text, image_width=800, image_height=600)
                    for text in ("y=x", "sin(x)", "cos(x)", "y=x^2+1")
                ]
                self._append(
                    f"RAPID current_candidate={first_id} "
                    f"intermediate={submitted[:-1]} latest={submitted[-1]}",
                )

            QTimer.singleShot(50, supersede)

        @Slot()
        def _start_error_recovery(self) -> None:
            self._error_recovery_pending = True
            self._submit("log(x)", image_width=800, image_height=600)

        @Slot(object)
        def _receive_result(self, value: object) -> None:
            assert isinstance(value, PlotSceneResult)
            worker_ids = sorted(
                {
                    thread_id
                    for stage_threads in self._executor.stage_threads[
                        value.request_id
                    ].values()
                    for thread_id in stage_threads
                },
            )
            if value.success:
                assert value.png_bytes is not None
                pixmap = QPixmap()
                assert pixmap.loadFromData(value.png_bytes, "PNG")
                self._preview.setPixmap(
                    pixmap.scaled(
                        self._preview.size(),
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    ),
                )
                self._status.setText(
                    f"Success request {value.request_id}; window remains responsive",
                )
                outcome = "success"
            else:
                code = value.error.code.value if value.error is not None else "none"
                self._status.setText(
                    f"Formal failure request {value.request_id}: {code}",
                )
                outcome = f"failure:{code}"
            self._append(
                f"RESULT id={value.request_id} outcome={outcome} "
                f"relay_gui_tid={get_ident()} worker_tids={worker_ids} "
                f"max_matplotlib_entries={self._executor.max_matplotlib_entries}",
            )
            if self._error_recovery_pending and not value.success:
                self._error_recovery_pending = False
                QTimer.singleShot(
                    0,
                    lambda: self._submit(
                        "y=x^2",
                        image_width=800,
                        image_height=600,
                    ),
                )

        def closeEvent(self, event: QCloseEvent) -> None:
            if self._closing:
                event.accept()
                return
            self._closing = True
            self._heartbeat_timer.stop()
            stopped = self._actor.shutdown()
            with qt_messages_lock:
                destruction_warnings = [
                    message
                    for message in qt_messages
                    if "QThread: Destroyed while thread is still running" in message
                ]
            self._append(
                f"CLOSE shutdown={stopped} actor_running={self._actor.is_running} "
                f"destruction_warnings={len(destruction_warnings)}",
            )
            if not stopped:
                self._status.setText(
                    "Shutdown timed out — close refused; retry after worker finishes",
                )
                self._closing = False
                self._heartbeat_timer.start()
                event.ignore()
                return
            event.accept()

    window = DesktopProbeWindow()
    window.show()
    exit_code = application.exec()
    qInstallMessageHandler(previous_handler)
    return int(exit_code)


if __name__ == "__main__":
    if "--manual" not in sys.argv:
        raise SystemExit("Use pytest, or pass --manual for visible desktop acceptance.")
    raise SystemExit(_run_visible_desktop_probe())
