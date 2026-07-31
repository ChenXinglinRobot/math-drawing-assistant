"""Stage-10C shutdown, timeout, result-gate, and lifetime verification."""

from __future__ import annotations

import gc
import inspect
import weakref
from queue import Queue
from threading import Barrier, Event, Lock, Thread, get_ident
from typing import Callable

import pytest
from PySide6.QtCore import (
    QEventLoop,
    QObject,
    QTimer,
    Qt,
    Signal,
    Slot,
    qInstallMessageHandler,
)
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication

import math_drawing_assistant.workers.render_actor as actor_module
from math_drawing_assistant.app_controller import AppController
from math_drawing_assistant.models import (
    ErrorCode,
    InputSource,
    PlotItemRequest,
    PlotKind,
    PlotSceneRequest,
    PlotSceneResult,
    TaskPhase,
    ViewportRequest,
)
from math_drawing_assistant.workers.cancellation import CancellationToken
from math_drawing_assistant.workers.render_actor import (
    RenderActor,
    _drain_mailbox,
    _Lifecycle,
    _Mailbox,
    _RenderTask,
)


def _request(request_id: int, *, scene_revision: int | None = None) -> PlotSceneRequest:
    return PlotSceneRequest(
        request_id=request_id,
        scene_revision=request_id if scene_revision is None else scene_revision,
        items=(
            PlotItemRequest(
                item_id=f"item-{request_id}",
                input_text=f"y=x+{request_id}",
                input_source=InputSource.MANUAL,
                requested_plot_kind=PlotKind.AUTO,
                display_order=0,
            ),
        ),
        viewport=ViewportRequest(),
        image_width=640,
        image_height=480,
        dpi=100,
        show_grid=True,
        show_legend=False,
    )


def _success(request: PlotSceneRequest) -> PlotSceneResult:
    return PlotSceneResult(
        request_id=request.request_id,
        scene_revision=request.scene_revision,
        success=True,
        png_bytes=b"png",
    )


class _EventExecutor:
    """Executor whose selected calls deliberately ignore cancellation."""

    def __init__(self, *, blocked_ids: set[int] | None = None) -> None:
        self._blocked_ids = set() if blocked_ids is None else set(blocked_ids)
        self._release = {request_id: Event() for request_id in self._blocked_ids}
        self.entered: Queue[tuple[int, CancellationToken, int]] = Queue()
        self.entered_ids: list[int] = []
        self.thread_ids: list[int] = []
        self._lock = Lock()

    def execute(
        self,
        request: PlotSceneRequest,
        cancellation: CancellationToken,
    ) -> PlotSceneResult:
        with self._lock:
            self.entered_ids.append(request.request_id)
            self.thread_ids.append(get_ident())
        self.entered.put((request.request_id, cancellation, get_ident()))
        if request.request_id in self._blocked_ids:
            if not self._release[request.request_id].wait(5):
                raise RuntimeError("controlled executor release timed out")
        return _success(request)

    def release(self, request_id: int) -> None:
        self._release[request_id].set()

    def release_all(self) -> None:
        for release in self._release.values():
            release.set()


@pytest.fixture
def actor_factory(qapp: QApplication):
    resources: list[tuple[RenderActor, object]] = []

    def create(
        executor: object,
        *,
        shutdown_timeout_ms: int = 5_000,
    ) -> RenderActor:
        actor = RenderActor(
            executor,  # type: ignore[arg-type]
            shutdown_timeout_ms=shutdown_timeout_ms,
        )
        started = Event()
        finished = Event()
        actor._thread.started.connect(
            started.set,
            Qt.ConnectionType.DirectConnection,
        )
        actor._thread.finished.connect(
            finished.set,
            Qt.ConnectionType.DirectConnection,
        )
        resources.append((actor, executor))
        return actor

    yield create

    for actor, executor in reversed(resources):
        release_all = getattr(executor, "release_all", None)
        if release_all is not None:
            release_all()
        assert actor.shutdown(5_000) is True
        assert actor.is_running is False
    qapp.processEvents()
    gc.collect()
    assert actor_module._timed_out_keepalive_count() == 0


def _start_actor(actor: RenderActor) -> None:
    started = QSignalSpy(actor._thread.started)
    actor.start()
    if not actor.is_running:
        assert started.wait(3_000)
    assert actor.is_running is True
    assert actor._lifecycle is _Lifecycle.STARTED


def _wait_for_count(spy: QSignalSpy, count: int) -> None:
    if spy.count() >= count:
        return

    loop = QEventLoop()
    check = QTimer()
    timeout = QTimer()
    timeout.setSingleShot(True)

    def stop_when_ready() -> None:
        if spy.count() >= count:
            loop.quit()

    check.timeout.connect(stop_when_ready)
    timeout.timeout.connect(loop.quit)
    check.start(1)
    timeout.start(3_000)
    loop.exec()
    check.stop()
    timeout.stop()
    assert spy.count() >= count, f"timed out waiting for signal {count}"


class _ControllerReceiver(QObject):
    processed = Signal()

    def __init__(self, controller: AppController) -> None:
        super().__init__()
        self._controller = controller
        self.thread_ids: list[int] = []
        self.accepted: list[bool] = []
        self.results: list[PlotSceneResult] = []

    @Slot(object)
    def receive(self, result: object) -> None:
        assert isinstance(result, PlotSceneResult)
        self.thread_ids.append(get_ident())
        self.results.append(result)
        self.accepted.append(self._controller.handle_render_result(result))
        self.processed.emit()


class _WorkerEmissionRecorder(QObject):
    def __init__(self) -> None:
        super().__init__()
        self.emitted: Queue[tuple[int, int]] = Queue()

    @Slot(object)
    def record(self, result: object) -> None:
        assert isinstance(result, PlotSceneResult)
        self.emitted.put((result.request_id, get_ident()))


def _start_controller_render(controller: AppController) -> PlotSceneRequest:
    return controller.start_render(
        items=_request(1).items,
        viewport=ViewportRequest(),
        image_width=640,
        image_height=480,
        dpi=100,
        show_grid=True,
        show_legend=False,
    )


def test_created_shutdown_freezes_stopped_state(actor_factory) -> None:
    actor = actor_factory(_EventExecutor())
    token = CancellationToken()

    assert actor._lifecycle is _Lifecycle.CREATED
    assert actor.is_running is False
    assert actor.submit(_request(1), token) is False

    assert actor.shutdown() is True
    assert actor._lifecycle is _Lifecycle.STOPPED
    assert actor.shutdown() is True
    assert actor.submit(_request(1), token) is False
    with pytest.raises(RuntimeError, match="only be called once"):
        actor.start()


def test_started_shutdown_exposes_shutting_down_before_wait(actor_factory) -> None:
    executor = _EventExecutor(blocked_ids={1})
    actor = actor_factory(executor)
    token = CancellationToken()
    observed: Queue[_Lifecycle] = Queue()
    release_finished = Event()
    _start_actor(actor)
    assert actor.submit(_request(1), token) is True
    assert executor.entered.get(timeout=3)[0] == 1

    def release_after_close() -> None:
        assert token._event.wait(3)
        observed.put(actor._lifecycle)
        executor.release(1)
        release_finished.set()

    releaser = Thread(target=release_after_close)
    releaser.start()
    try:
        assert actor.shutdown() is True
    finally:
        executor.release_all()
        releaser.join(timeout=3)

    assert release_finished.is_set()
    assert observed.get_nowait() is _Lifecycle.SHUTTING_DOWN
    assert actor._lifecycle is _Lifecycle.STOPPED
    assert actor.is_running is False


def test_timeout_retries_remain_owned_until_finalized(actor_factory) -> None:
    executor = _EventExecutor(blocked_ids={1})
    actor = actor_factory(executor)
    finished = Event()
    actor._thread.finished.connect(
        finished.set,
        Qt.ConnectionType.DirectConnection,
    )
    token = CancellationToken()
    _start_actor(actor)
    assert actor.submit(_request(1), token) is True
    assert executor.entered.get(timeout=3)[0] == 1

    try:
        assert actor.shutdown(0) is False
        assert actor._lifecycle is _Lifecycle.TIMED_OUT
        assert actor.is_running is True
        assert actor_module._timed_out_keepalive_count() == 1
        assert actor.submit(_request(2), CancellationToken()) is False
        with pytest.raises(RuntimeError, match="only be called once"):
            actor.start()

        assert actor.shutdown(0) is False
        assert actor._lifecycle is _Lifecycle.TIMED_OUT
        assert actor_module._timed_out_keepalive_count() == 1

        executor.release(1)
        assert finished.wait(3)
        assert actor.is_running is False
        assert actor._lifecycle is _Lifecycle.TIMED_OUT

        assert actor.shutdown(1_000) is True
        assert actor._lifecycle is _Lifecycle.STOPPED
        assert actor_module._timed_out_keepalive_count() == 0
        assert actor.shutdown() is True
    finally:
        executor.release_all()


@pytest.mark.parametrize(
    "lifecycle",
    (
        _Lifecycle.SHUTTING_DOWN,
        _Lifecycle.TIMED_OUT,
        _Lifecycle.STOPPED,
    ),
)
def test_non_started_lifecycle_rejects_submission(
    actor_factory,
    lifecycle: _Lifecycle,
) -> None:
    actor = actor_factory(_EventExecutor())
    token = CancellationToken()
    actor._lifecycle = lifecycle

    assert actor.submit(_request(1), token) is False
    assert token.is_cancelled() is False
    assert actor._mailbox.pending is None

    actor._lifecycle = _Lifecycle.CREATED


def test_shutdown_atomically_cancels_current_and_pending(actor_factory) -> None:
    executor = _EventExecutor(blocked_ids={1})
    actor = actor_factory(executor)
    results = QSignalSpy(actor.result_ready)
    current_token = CancellationToken()
    pending_token = CancellationToken()
    cancellation_seen = Event()
    _start_actor(actor)
    assert actor.submit(_request(1), current_token) is True
    assert executor.entered.get(timeout=3)[0] == 1
    assert actor.submit(_request(2), pending_token) is True

    def release_when_both_are_cancelled() -> None:
        assert current_token._event.wait(3)
        assert pending_token._event.wait(3)
        cancellation_seen.set()
        executor.release(1)

    releaser = Thread(target=release_when_both_are_cancelled)
    releaser.start()
    try:
        assert actor.shutdown() is True
    finally:
        executor.release_all()
        releaser.join(timeout=3)

    assert cancellation_seen.is_set()
    assert current_token.is_cancelled() is True
    assert pending_token.is_cancelled() is True
    assert executor.entered_ids == [1]
    assert results.count() == 0
    with actor._mailbox._lock:
        assert actor._mailbox.pending is None
        assert actor._mailbox.current_token is None
        assert actor._mailbox.stop_requested is True
        assert actor._mailbox.result_gate_closed is True


class _BlockingExecutor:
    def __init__(self, entered: Barrier, release: Event) -> None:
        self._entered = entered
        self._release = release

    def execute(
        self,
        request: PlotSceneRequest,
        cancellation: CancellationToken,
    ) -> PlotSceneResult:
        self._entered.wait(timeout=3)
        if not self._release.wait(3):
            raise RuntimeError("decision test release timed out")
        return _success(request)


class _DecisionPauseMailbox(_Mailbox):
    def __init__(self, decision_made: Barrier, release: Event) -> None:
        super().__init__()
        self._decision_made = decision_made
        self._release = release
        self.allowed: bool | None = None

    def complete(
        self,
        token: CancellationToken,
        *,
        has_result: bool,
    ) -> bool:
        allowed = super().complete(token, has_result=has_result)
        self.allowed = allowed
        self._decision_made.wait(timeout=3)
        if not self._release.wait(3):
            raise RuntimeError("publish release timed out")
        return allowed


def _run_and_capture(error_queue: Queue[BaseException], action: Callable[[], None]) -> None:
    try:
        action()
    except BaseException as error:
        error_queue.put(error)


def test_close_before_completion_decision_blocks_worker_emit() -> None:
    executor_entered = Barrier(2)
    executor_release = Event()
    executor = _BlockingExecutor(executor_entered, executor_release)
    mailbox = _Mailbox()
    token = CancellationToken()
    published: list[PlotSceneResult] = []
    failures: Queue[BaseException] = Queue()
    assert mailbox.submit(_RenderTask(_request(1), token)) is True
    worker = Thread(
        target=_run_and_capture,
        args=(
            failures,
            lambda: _drain_mailbox(mailbox, executor, published.append),
        ),
    )
    worker.start()

    executor_entered.wait(timeout=3)
    mailbox.close()
    executor_release.set()
    worker.join(timeout=3)

    assert worker.is_alive() is False
    assert failures.empty()
    assert token.is_cancelled() is True
    assert published == []


def test_prelinearized_emit_decision_remains_in_flight_after_close() -> None:
    decision_made = Barrier(2)
    publish_release = Event()
    mailbox = _DecisionPauseMailbox(decision_made, publish_release)
    token = CancellationToken()
    published: list[PlotSceneResult] = []
    failures: Queue[BaseException] = Queue()
    assert mailbox.submit(_RenderTask(_request(1), token)) is True
    worker = Thread(
        target=_run_and_capture,
        args=(
            failures,
            lambda: _drain_mailbox(
                mailbox,
                _EventExecutor(),
                published.append,
            ),
        ),
    )
    worker.start()

    decision_made.wait(timeout=3)
    assert mailbox.allowed is True
    mailbox.close()
    publish_release.set()
    worker.join(timeout=3)

    assert worker.is_alive() is False
    assert failures.empty()
    assert len(published) == 1
    assert published[0].request_id == 1
    assert mailbox.result_gate_closed is True


def test_real_actor_success_is_accepted_only_on_gui_thread(actor_factory) -> None:
    gui_thread_id = get_ident()
    executor = _EventExecutor()
    actor = actor_factory(executor)
    controller = AppController(render_submitter=actor)
    receiver = _ControllerReceiver(controller)
    actor.result_ready.connect(
        receiver.receive,
        Qt.ConnectionType.DirectConnection,
    )
    processed = QSignalSpy(receiver.processed)
    _start_actor(actor)

    request = _start_controller_render(controller)
    _wait_for_count(processed, 1)

    assert executor.entered_ids == [request.request_id]
    assert len(executor.thread_ids) == 1
    assert executor.thread_ids[0] != gui_thread_id
    assert receiver.thread_ids == [gui_thread_id]
    assert receiver.accepted == [True]
    assert controller.last_successful_result is receiver.results[0]
    assert controller.task_phase is TaskPhase.IDLE


def test_real_actor_superseded_in_flight_result_is_rejected(actor_factory) -> None:
    executor = _EventExecutor(blocked_ids={2})
    actor = actor_factory(executor)
    controller = AppController(render_submitter=actor)
    receiver = _ControllerReceiver(controller)
    emission_recorder = _WorkerEmissionRecorder()
    actor._worker._result_ready.connect(
        emission_recorder.record,
        Qt.ConnectionType.DirectConnection,
    )
    actor.result_ready.connect(
        receiver.receive,
        Qt.ConnectionType.DirectConnection,
    )
    processed = QSignalSpy(receiver.processed)
    _start_actor(actor)

    first = _start_controller_render(controller)
    first_token = controller._current_render_token
    emitted_request_id, worker_thread_id = emission_recorder.emitted.get(timeout=3)
    assert emitted_request_id == first.request_id
    assert worker_thread_id != get_ident()

    controller.mark_scene_edited()
    second = _start_controller_render(controller)
    assert first_token is not None
    assert first_token.is_cancelled() is True
    assert second.request_id == first.request_id + 1
    _wait_for_count(processed, 1)
    assert receiver.accepted == [False]
    assert controller.current_render_request_id == second.request_id

    assert executor.entered.get(timeout=3)[0] == first.request_id
    assert executor.entered.get(timeout=3)[0] == second.request_id
    executor.release(second.request_id)
    _wait_for_count(processed, 2)

    assert receiver.accepted == [False, True]
    assert [result.request_id for result in receiver.results] == [
        first.request_id,
        second.request_id,
    ]
    assert executor.entered_ids == [first.request_id, second.request_id]


def test_shutdown_allows_prelinearized_worker_signal_but_controller_rejects_it(
    actor_factory,
) -> None:
    executor = _EventExecutor()
    actor = actor_factory(executor)
    controller = AppController(render_submitter=actor)
    receiver = _ControllerReceiver(controller)
    emission_recorder = _WorkerEmissionRecorder()
    actor._worker._result_ready.connect(
        emission_recorder.record,
        Qt.ConnectionType.DirectConnection,
    )
    actor.result_ready.connect(
        receiver.receive,
        Qt.ConnectionType.DirectConnection,
    )
    processed = QSignalSpy(receiver.processed)
    _start_actor(actor)

    request = _start_controller_render(controller)
    emitted_request_id, _ = emission_recorder.emitted.get(timeout=3)
    assert emitted_request_id == request.request_id
    assert controller.task_phase is TaskPhase.RENDERING

    assert controller.shutdown() is True
    assert controller.task_phase is TaskPhase.SHUTTING_DOWN
    assert controller.current_render_request_id is None
    assert actor._lifecycle is _Lifecycle.STOPPED
    _wait_for_count(processed, 1)

    assert [result.request_id for result in receiver.results] == [request.request_id]
    assert receiver.accepted == [False]
    assert controller.last_successful_result is None


def test_gate_blocks_task_that_finishes_after_timeout(actor_factory) -> None:
    executor = _EventExecutor(blocked_ids={1})
    actor = actor_factory(executor, shutdown_timeout_ms=0)
    worker_emitted = _WorkerEmissionRecorder()
    actor._worker._result_ready.connect(
        worker_emitted.record,
        Qt.ConnectionType.DirectConnection,
    )
    relayed = QSignalSpy(actor.result_ready)
    finished = Event()
    actor._thread.finished.connect(
        finished.set,
        Qt.ConnectionType.DirectConnection,
    )
    token = CancellationToken()
    _start_actor(actor)
    assert actor.submit(_request(1), token) is True
    assert executor.entered.get(timeout=3)[0] == 1

    try:
        assert actor.shutdown() is False
        assert actor._lifecycle is _Lifecycle.TIMED_OUT
        executor.release(1)
        assert finished.wait(3)
        assert actor.is_running is False
        assert worker_emitted.emitted.empty()
        assert relayed.count() == 0
        assert actor.shutdown(1_000) is True
    finally:
        executor.release_all()


def test_controller_propagates_actor_timeout_and_retry_finalizes(
    actor_factory,
) -> None:
    executor = _EventExecutor(blocked_ids={1})
    actor = actor_factory(executor, shutdown_timeout_ms=50)
    controller = AppController(render_submitter=actor)
    finished = Event()
    actor._thread.finished.connect(
        finished.set,
        Qt.ConnectionType.DirectConnection,
    )
    _start_actor(actor)
    request = _start_controller_render(controller)
    active_token = controller._current_render_token
    assert active_token is not None
    assert executor.entered.get(timeout=3)[0] == request.request_id

    try:
        assert controller.shutdown() is False
        assert actor.is_running is True
        assert controller.task_phase is TaskPhase.SHUTTING_DOWN
        assert controller.current_render_request_id is None
        assert controller.current_recognition_request_id is None
        assert controller._current_render_token is None
        assert active_token.is_cancelled() is True
        assert controller.last_error_notice is not None
        assert controller.last_error_notice.code is ErrorCode.INTERNAL_ERROR
        assert (
            controller.last_error_notice.user_message
            == "Unable to shut down the render service."
        )
        assert controller.last_error_notice.technical_message is None
        assert controller.last_error_notice.recoverable is False

        executor.release_all()
        assert finished.wait(3)
        assert actor.is_running is False
        assert controller.shutdown() is True
        assert controller.task_phase is TaskPhase.SHUTTING_DOWN
    finally:
        executor.release_all()


def test_timed_out_registry_survives_actor_gc_then_cleans_without_qt_warning(
    qapp: QApplication,
) -> None:
    executor = _EventExecutor(blocked_ids={1})
    messages: list[str] = []
    messages_lock = Lock()

    def capture_message(message_type, context, message: str) -> None:
        del message_type, context
        with messages_lock:
            messages.append(message)

    previous_handler = qInstallMessageHandler(capture_message)
    actor: RenderActor | None = None
    try:
        actor = RenderActor(executor, shutdown_timeout_ms=0)
        finished = Event()
        actor._thread.finished.connect(
            finished.set,
            Qt.ConnectionType.DirectConnection,
        )
        _start_actor(actor)
        assert actor.submit(_request(1), CancellationToken()) is True
        assert executor.entered.get(timeout=3)[0] == 1
        assert actor.shutdown() is False
        assert actor_module._timed_out_keepalive_count() == 1

        actor_ref = weakref.ref(actor)
        actor = None
        gc.collect()
        assert actor_ref() is None
        with messages_lock:
            assert not any(
                "Destroyed while thread is still running" in message
                for message in messages
            )

        executor.release(1)
        assert finished.wait(3)
        qapp.processEvents()
        gc.collect()

        assert actor_module._timed_out_keepalive_count() == 0
        with messages_lock:
            assert not any(
                "QThread: Destroyed while thread is still running" in message
                for message in messages
            )
    finally:
        executor.release_all()
        if actor is not None:
            assert actor.shutdown(5_000) is True
        qapp.processEvents()
        qInstallMessageHandler(previous_handler)


def test_repeated_start_shutdown_has_no_running_thread_destruction_warning(
    qapp: QApplication,
) -> None:
    messages: list[str] = []

    def capture_message(message_type, context, message: str) -> None:
        del message_type, context
        messages.append(message)

    previous_handler = qInstallMessageHandler(capture_message)
    actor: RenderActor | None = None
    try:
        for _ in range(20):
            actor = RenderActor(_EventExecutor())
            _start_actor(actor)
            assert actor.shutdown() is True
            assert actor.is_running is False
            actor = None
            gc.collect()
            qapp.processEvents()
    finally:
        if actor is not None:
            assert actor.shutdown(5_000) is True
        qapp.processEvents()
        qInstallMessageHandler(previous_handler)

    assert not any(
        "QThread: Destroyed while thread is still running" in message
        for message in messages
    )


@pytest.mark.parametrize("timeout_ms", (-1, True, 1.5, "10"))
def test_shutdown_timeout_must_be_in_the_safe_integer_domain(
    actor_factory,
    timeout_ms: object,
) -> None:
    actor = actor_factory(_EventExecutor())

    expected_error = TypeError if isinstance(timeout_ms, (bool, float, str)) else ValueError
    with pytest.raises(expected_error):
        actor.shutdown(timeout_ms)  # type: ignore[arg-type]

    assert actor._lifecycle is _Lifecycle.CREATED


@pytest.mark.parametrize(
    ("timeout_ms", "expected"),
    (
        (None, actor_module._DEFAULT_SHUTDOWN_TIMEOUT_MS),
        (0, 0),
        (actor_module._MAX_SHUTDOWN_TIMEOUT_MS, actor_module._MAX_SHUTDOWN_TIMEOUT_MS),
    ),
    ids=("default", "zero", "max"),
)
def test_constructor_accepts_shutdown_timeout_boundaries(
    actor_factory,
    timeout_ms: int | None,
    expected: int,
) -> None:
    if timeout_ms is None:
        actor = actor_factory(_EventExecutor())
    else:
        actor = actor_factory(_EventExecutor(), shutdown_timeout_ms=timeout_ms)

    assert actor._shutdown_timeout_ms == expected
    assert actor._lifecycle is _Lifecycle.CREATED
    assert actor.is_running is False


@pytest.mark.parametrize(
    ("timeout_ms", "expected_error"),
    (
        (-1, ValueError),
        (True, TypeError),
        (1.5, TypeError),
        ("10", TypeError),
        (actor_module._MAX_SHUTDOWN_TIMEOUT_MS + 1, ValueError),
        (2**32 - 1, ValueError),
        (2**64 - 1, ValueError),
    ),
    ids=(
        "negative",
        "bool",
        "float",
        "string",
        "max-plus-one",
        "ulong-max",
        "uint64-max",
    ),
)
def test_constructor_rejects_unsafe_timeout_before_qthread_creation(
    monkeypatch,
    timeout_ms: object,
    expected_error: type[Exception],
) -> None:
    class _QThreadCreationGuard:
        @classmethod
        def currentThread(cls):
            raise AssertionError("invalid construction reached QThread.currentThread")

        def __init__(self) -> None:
            raise AssertionError("invalid construction created a QThread")

    registry_count = actor_module._timed_out_keepalive_count()
    monkeypatch.setattr(actor_module, "QThread", _QThreadCreationGuard)

    with pytest.raises(expected_error):
        RenderActor(  # type: ignore[arg-type]
            _EventExecutor(),
            shutdown_timeout_ms=timeout_ms,  # type: ignore[arg-type]
        )

    assert actor_module._timed_out_keepalive_count() == registry_count


def test_shutdown_override_accepts_maximum(actor_factory) -> None:
    actor = actor_factory(_EventExecutor())
    _start_actor(actor)

    assert actor.shutdown(actor_module._MAX_SHUTDOWN_TIMEOUT_MS) is True
    assert actor._lifecycle is _Lifecycle.STOPPED
    assert actor.is_running is False


def test_running_actor_rejects_unsafe_timeout_before_any_state_change(
    actor_factory,
    monkeypatch,
) -> None:
    executor = _EventExecutor(blocked_ids={1})
    actor = actor_factory(executor)
    results = QSignalSpy(actor.result_ready)
    token = CancellationToken()
    _start_actor(actor)
    assert actor.submit(_request(1), token) is True
    assert executor.entered.get(timeout=3)[0] == 1

    with actor._mailbox._lock:
        mailbox_before = (
            actor._mailbox.pending,
            actor._mailbox.current_token,
            actor._mailbox.stop_requested,
            actor._mailbox.result_gate_closed,
        )
    lifecycle_before = actor._lifecycle
    registry_before = actor_module._timed_out_keepalive_count()
    wait_calls: list[int] = []
    quit_calls: list[None] = []
    original_wait = actor._thread.wait
    original_quit = actor._thread.quit

    def wait_spy(timeout_ms: int) -> bool:
        wait_calls.append(timeout_ms)
        return original_wait(timeout_ms)

    def quit_spy() -> None:
        quit_calls.append(None)
        original_quit()

    try:
        with monkeypatch.context() as context:
            context.setattr(actor._thread, "wait", wait_spy)
            context.setattr(actor._thread, "quit", quit_spy)
            for timeout_ms in (
                actor_module._MAX_SHUTDOWN_TIMEOUT_MS + 1,
                2**32 - 1,
                2**64 - 1,
            ):
                with pytest.raises(ValueError, match="between 0 and 60000"):
                    actor.shutdown(timeout_ms)

                assert actor._lifecycle is lifecycle_before
                assert token.is_cancelled() is False
                with actor._mailbox._lock:
                    assert (
                        actor._mailbox.pending,
                        actor._mailbox.current_token,
                        actor._mailbox.stop_requested,
                        actor._mailbox.result_gate_closed,
                    ) == mailbox_before
                assert actor_module._timed_out_keepalive_count() == registry_before

            pending_token = CancellationToken()
            assert actor.submit(_request(2), pending_token) is True
            assert token.is_cancelled() is True
            assert pending_token.is_cancelled() is False
            with actor._mailbox._lock:
                pending_mailbox_before = (
                    actor._mailbox.pending,
                    actor._mailbox.current_token,
                    actor._mailbox.stop_requested,
                    actor._mailbox.result_gate_closed,
                )

            with pytest.raises(ValueError, match="between 0 and 60000"):
                actor.shutdown(actor_module._MAX_SHUTDOWN_TIMEOUT_MS + 1)

            with actor._mailbox._lock:
                assert (
                    actor._mailbox.pending,
                    actor._mailbox.current_token,
                    actor._mailbox.stop_requested,
                    actor._mailbox.result_gate_closed,
                ) == pending_mailbox_before
            assert pending_token.is_cancelled() is False
            assert actor_module._timed_out_keepalive_count() == registry_before
            assert wait_calls == []
            assert quit_calls == []

        executor.release(1)
        _wait_for_count(results, 1)
        assert results.at(0)[0].request_id == 2
        assert actor.submit(_request(3), CancellationToken()) is True
        _wait_for_count(results, 2)
        assert results.at(1)[0].request_id == 3
        assert actor.shutdown(5_000) is True
        assert actor._lifecycle is _Lifecycle.STOPPED
        assert actor.is_running is False
        assert actor_module._timed_out_keepalive_count() == 0
    finally:
        executor.release_all()


def test_shutdown_module_boundary_is_static_and_bounded() -> None:
    source = inspect.getsource(actor_module)
    shutdown_source = inspect.getsource(actor_module.RenderActor.shutdown)
    lowered = source.lower()

    assert actor_module._MAX_SHUTDOWN_TIMEOUT_MS == 60_000
    assert ".terminate(" not in lowered
    assert "__del__" not in lowered
    assert "self._thread.wait()" not in source
    assert "self._thread.wait(wait_timeout_ms)" in source
    assert shutdown_source.index("_validate_shutdown_timeout(timeout_ms)") < (
        shutdown_source.index("self._lifecycle is _Lifecycle.STOPPED")
    )
    assert "matplotlib" not in lowered
    assert "pyplot" not in lowered
    assert "math_drawing_assistant.ui" not in lowered
    assert "math_drawing_assistant.engine" not in lowered
    assert "forbids final qapplication, module, or process shutdown" in lowered
