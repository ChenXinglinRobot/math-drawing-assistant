"""Deterministic stage-10B tests for the persistent render actor."""

from __future__ import annotations

import inspect
from collections import deque
from queue import Empty, Queue
from threading import Event, Lock, Thread, get_ident
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
from math_drawing_assistant.models import (
    ErrorCode,
    InputSource,
    PlotItemRequest,
    PlotKind,
    PlotSceneRequest,
    PlotSceneResult,
    ViewportRequest,
)
from math_drawing_assistant.workers.cancellation import CancellationToken
from math_drawing_assistant.workers.render_actor import (
    RenderActor,
    _drain_mailbox,
    _execute_task,
    _Lifecycle,
    _Mailbox,
    _RenderTask,
)


def _request(request_id: int, scene_revision: int | None = None) -> PlotSceneRequest:
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


def _wait_for_count(spy: QSignalSpy, count: int) -> None:
    if spy.count() >= count:
        return

    loop = QEventLoop()
    poll = QTimer()
    timeout = QTimer()
    timeout.setSingleShot(True)

    def check_count() -> None:
        if spy.count() >= count:
            loop.quit()

    poll.timeout.connect(check_count)
    timeout.timeout.connect(loop.quit)
    poll.start(1)
    timeout.start(3_000)
    loop.exec()
    poll.stop()
    timeout.stop()
    assert spy.count() >= count, f"timed out waiting for signal {count}"


def _start_actor(actor: RenderActor) -> None:
    started = QSignalSpy(actor._thread.started)
    actor.start()
    if not actor.is_running:
        assert started.wait(3_000)
    assert actor.is_running is True


class _ControlledExecutor:
    def __init__(
        self,
        *,
        blocked_ids: set[int] | None = None,
        outcomes: dict[int, object] | None = None,
    ) -> None:
        self.blocked_ids = set() if blocked_ids is None else set(blocked_ids)
        self.outcomes = {} if outcomes is None else dict(outcomes)
        self.entered: Queue[tuple[int, CancellationToken, int]] = Queue()
        self.entered_ids: list[int] = []
        self.thread_ids: list[int] = []
        self._release = {request_id: Event() for request_id in self.blocked_ids}
        self._lock = Lock()
        self._active = 0
        self.max_active = 0

    def execute(
        self,
        request: PlotSceneRequest,
        cancellation: CancellationToken,
    ) -> PlotSceneResult:
        thread_id = get_ident()
        with self._lock:
            self._active += 1
            self.max_active = max(self.max_active, self._active)
            self.entered_ids.append(request.request_id)
            self.thread_ids.append(thread_id)
        self.entered.put((request.request_id, cancellation, thread_id))
        try:
            if request.request_id in self.blocked_ids:
                if not self._release[request.request_id].wait(5):
                    raise RuntimeError("controlled executor release timed out")
            outcome = self.outcomes.get(request.request_id)
            if isinstance(outcome, BaseException):
                raise outcome
            if callable(outcome):
                return outcome(request)
            if outcome is not None:
                return outcome  # type: ignore[return-value]
            return _success(request)
        finally:
            with self._lock:
                self._active -= 1

    def release(self, request_id: int) -> None:
        self._release[request_id].set()

    def release_all(self) -> None:
        for release in self._release.values():
            release.set()


class _SequenceExecutor:
    def __init__(self, outcomes: tuple[object, ...]) -> None:
        self._outcomes = deque(outcomes)
        self.thread_ids: list[int] = []

    def execute(
        self,
        request: PlotSceneRequest,
        cancellation: CancellationToken,
    ) -> PlotSceneResult:
        self.thread_ids.append(get_ident())
        outcome = self._outcomes.popleft()
        if isinstance(outcome, BaseException):
            raise outcome
        if callable(outcome):
            return outcome(request)
        return outcome  # type: ignore[return-value]

    def release_all(self) -> None:
        pass


@pytest.fixture
def actor_factory(qapp: QApplication):
    actors: list[tuple[RenderActor, object]] = []

    def create(
        executor: object,
        actor_type: type[RenderActor] = RenderActor,
    ) -> RenderActor:
        actor = actor_type(executor)  # type: ignore[arg-type]
        actors.append((actor, executor))
        return actor

    yield create

    for actor, executor in reversed(actors):
        release_all = getattr(executor, "release_all", None)
        if release_all is not None:
            release_all()
        assert actor.shutdown(5_000) is True
        assert actor.is_running is False
    qapp.processEvents()


def test_lifecycle_before_start_and_shutdown_is_repeatable(actor_factory) -> None:
    executor = _ControlledExecutor()
    actor = actor_factory(executor)
    token = CancellationToken()
    request = _request(1)

    assert actor.is_running is False
    assert actor._thread.parent() is None
    assert actor._worker.parent() is None
    assert actor.submit(request, token) is False
    assert token.is_cancelled() is False
    assert actor._mailbox.pending is None

    assert actor.shutdown() is True
    assert actor.shutdown() is True
    assert actor.submit(request, token) is False
    assert token.is_cancelled() is False
    with pytest.raises(RuntimeError, match="only be called once"):
        actor.start()


def test_start_once_normal_shutdown_and_stopped_submission(actor_factory) -> None:
    executor = _ControlledExecutor()
    actor = actor_factory(executor)

    _start_actor(actor)
    with pytest.raises(RuntimeError, match="only be called once"):
        actor.start()

    assert actor.shutdown() is True
    assert actor.is_running is False
    stopped_token = CancellationToken()
    assert actor.submit(_request(1), stopped_token) is False
    assert stopped_token.is_cancelled() is False
    assert actor.shutdown() is True


@pytest.mark.parametrize("operation", ("start", "submit", "shutdown"))
def test_public_mutations_reject_the_wrong_thread(
    actor_factory,
    operation: str,
) -> None:
    executor = _ControlledExecutor()
    actor = actor_factory(executor)
    if operation != "start":
        _start_actor(actor)

    token = CancellationToken()
    failures: Queue[BaseException] = Queue()

    def call_from_wrong_thread() -> None:
        try:
            if operation == "start":
                actor.start()
            elif operation == "submit":
                actor.submit(_request(1), token)
            else:
                actor.shutdown()
        except BaseException as error:
            failures.put(error)

    caller = Thread(target=call_from_wrong_thread)
    caller.start()
    caller.join(timeout=3)

    assert caller.is_alive() is False
    error = failures.get_nowait()
    assert isinstance(error, RuntimeError)
    assert "owner thread" in str(error)
    assert token.is_cancelled() is False
    assert actor._mailbox.pending is None

    if operation == "start":
        _start_actor(actor)


def test_three_task_latest_wins_is_serial_and_thread_is_fixed(actor_factory) -> None:
    executor = _ControlledExecutor(blocked_ids={1, 3})
    actor = actor_factory(executor)
    results = QSignalSpy(actor.result_ready)
    _start_actor(actor)

    tokens = [CancellationToken() for _ in range(3)]
    assert actor.submit(_request(1), tokens[0]) is True
    assert executor.entered.get(timeout=3)[0] == 1

    assert actor.submit(_request(2), tokens[1]) is True
    assert tokens[0].is_cancelled() is True
    assert actor.submit(_request(3), tokens[2]) is True
    assert tokens[1].is_cancelled() is True
    with actor._mailbox._lock:
        assert actor._mailbox.pending is not None
        assert actor._mailbox.pending.request.request_id == 3

    executor.release(1)
    assert executor.entered.get(timeout=3)[0] == 3
    executor.release(3)
    _wait_for_count(results, 1)

    payload = results.at(0)[0]
    assert isinstance(payload, PlotSceneResult)
    assert payload.request_id == 3
    assert executor.entered_ids == [1, 3]
    assert 2 not in executor.entered_ids
    assert executor.max_active == 1
    assert len(set(executor.thread_ids)) == 1
    assert executor.thread_ids[0] != get_ident()


class _ThreadGate(QObject):
    enter_requested = Signal()
    marker_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.entered = Event()
        self.release = Event()
        self.marked = Event()
        self.enter_requested.connect(
            self._block,
            Qt.ConnectionType.QueuedConnection,
        )
        self.marker_requested.connect(
            self._mark,
            Qt.ConnectionType.QueuedConnection,
        )

    @Slot()
    def _block(self) -> None:
        self.entered.set()
        if not self.release.wait(5):
            raise RuntimeError("test gate release timed out")

    @Slot()
    def _mark(self) -> None:
        self.marked.set()


def _block_actor_thread(actor: RenderActor) -> _ThreadGate:
    gate = _ThreadGate()
    gate.moveToThread(actor._thread)
    actor._thread.finished.connect(gate.deleteLater)
    gate.enter_requested.emit()
    assert gate.entered.wait(3)
    return gate


def test_cancelled_before_pending_take_never_enters_executor(actor_factory) -> None:
    executor = _ControlledExecutor()
    actor = actor_factory(executor)
    _start_actor(actor)
    gate = _block_actor_thread(actor)

    token = CancellationToken()
    assert actor.submit(_request(1), token) is True
    token.cancel()
    gate.marker_requested.emit()
    gate.release.set()
    assert gate.marked.wait(3)

    with pytest.raises(Empty):
        executor.entered.get_nowait()
    assert executor.entered_ids == []
    with actor._mailbox._lock:
        assert actor._mailbox.pending is None
        assert actor._mailbox.current_token is None


def test_submit_before_pending_take_replaces_atomically(actor_factory) -> None:
    executor = _ControlledExecutor()
    actor = actor_factory(executor)
    results = QSignalSpy(actor.result_ready)
    _start_actor(actor)
    gate = _block_actor_thread(actor)

    old_token = CancellationToken()
    new_token = CancellationToken()
    assert actor.submit(_request(1), old_token) is True
    assert actor.submit(_request(2), new_token) is True
    assert old_token.is_cancelled() is True
    with actor._mailbox._lock:
        assert actor._mailbox.pending is not None
        assert actor._mailbox.pending.request.request_id == 2

    gate.release.set()
    _wait_for_count(results, 1)
    assert results.at(0)[0].request_id == 2
    assert executor.entered_ids == [2]


def test_submit_after_pending_take_cancels_current_and_runs_next(
    actor_factory,
) -> None:
    executor = _ControlledExecutor(blocked_ids={1, 2})
    actor = actor_factory(executor)
    results = QSignalSpy(actor.result_ready)
    _start_actor(actor)
    current_token = CancellationToken()
    next_token = CancellationToken()

    assert actor.submit(_request(1), current_token) is True
    assert executor.entered.get(timeout=3)[0] == 1
    with actor._mailbox._lock:
        assert actor._mailbox.pending is None
        assert actor._mailbox.current_token is current_token

    assert actor.submit(_request(2), next_token) is True
    assert current_token.is_cancelled() is True
    executor.release(1)
    assert executor.entered.get(timeout=3)[0] == 2
    executor.release(2)
    _wait_for_count(results, 1)

    assert [results.at(index)[0].request_id for index in range(results.count())] == [2]


def test_complete_before_submit_may_relay_both_results(actor_factory) -> None:
    executor = _ControlledExecutor()
    actor = actor_factory(executor)
    results = QSignalSpy(actor.result_ready)
    _start_actor(actor)

    assert actor.submit(_request(1), CancellationToken()) is True
    _wait_for_count(results, 1)
    assert actor.submit(_request(2), CancellationToken()) is True
    _wait_for_count(results, 2)

    assert [results.at(index)[0].request_id for index in range(2)] == [1, 2]


@pytest.mark.parametrize(
    "outcome_factory",
    (
        lambda request: object(),
        lambda request: PlotSceneResult(
            request_id=request.request_id + 100,
            scene_revision=request.scene_revision,
            success=True,
        ),
        lambda request: PlotSceneResult(
            request_id=request.request_id,
            scene_revision=request.scene_revision + 100,
            success=True,
        ),
        lambda request: _invalid_result(request),
    ),
    ids=("wrong-type", "wrong-request-id", "wrong-revision", "invalid-model"),
)
def test_executor_contract_violations_map_to_sanitized_input_identity(
    actor_factory,
    outcome_factory: Callable[[PlotSceneRequest], object],
) -> None:
    executor = _SequenceExecutor((outcome_factory,))
    actor = actor_factory(executor)
    results = QSignalSpy(actor.result_ready)
    request = _request(7, scene_revision=11)
    _start_actor(actor)

    assert actor.submit(request, CancellationToken()) is True
    _wait_for_count(results, 1)

    payload = results.at(0)[0]
    assert type(payload) is PlotSceneResult
    assert payload.request_id == request.request_id
    assert payload.scene_revision == request.scene_revision
    assert payload.success is False
    assert payload.png_bytes is None
    assert payload.error is not None
    assert payload.error.code is ErrorCode.INTERNAL_ERROR
    assert payload.error.recoverable is False
    assert payload.error.technical_message is None


def _invalid_result(request: PlotSceneRequest) -> PlotSceneResult:
    result = _success(request)
    object.__setattr__(result, "success", "invalid")
    return result


@pytest.mark.parametrize(
    ("error", "expected_code", "recoverable"),
    (
        (
            RuntimeError(r"secret y=x C:\private\plot.png [1, 2] seal"),
            ErrorCode.INTERNAL_ERROR,
            False,
        ),
        (
            MemoryError(r"secret y=x C:\private\plot.png [1, 2] seal"),
            ErrorCode.RESOURCE_LIMIT_EXCEEDED,
            True,
        ),
    ),
)
def test_executor_exceptions_are_fixed_and_redacted(
    actor_factory,
    error: Exception,
    expected_code: ErrorCode,
    recoverable: bool,
) -> None:
    executor = _SequenceExecutor((error,))
    actor = actor_factory(executor)
    results = QSignalSpy(actor.result_ready)
    _start_actor(actor)

    assert actor.submit(_request(1), CancellationToken()) is True
    _wait_for_count(results, 1)

    payload = results.at(0)[0]
    assert type(payload) is PlotSceneResult
    assert payload.error is not None
    assert payload.error.code is expected_code
    assert payload.error.recoverable is recoverable
    exposed = repr(payload)
    for secret in ("secret", "y=x", "private", "[1, 2]", "seal", "traceback"):
        assert secret not in exposed


def test_regular_exception_does_not_poison_the_long_lived_actor(actor_factory) -> None:
    executor = _SequenceExecutor(
        (
            RuntimeError("sensitive first failure"),
            lambda request: _success(request),
        ),
    )
    actor = actor_factory(executor)
    results = QSignalSpy(actor.result_ready)
    _start_actor(actor)

    assert actor.submit(_request(1), CancellationToken()) is True
    _wait_for_count(results, 1)
    assert actor.submit(_request(2), CancellationToken()) is True
    _wait_for_count(results, 2)

    first = results.at(0)[0]
    second = results.at(1)[0]
    assert first.success is False
    assert first.error is not None
    assert first.error.code is ErrorCode.INTERNAL_ERROR
    assert second.success is True
    assert second.request_id == 2
    assert len(set(executor.thread_ids)) == 1


class _BaseExceptionExecutor:
    def execute(
        self,
        request: PlotSceneRequest,
        cancellation: CancellationToken,
    ) -> PlotSceneResult:
        raise SystemExit("must propagate")


def test_execute_task_base_exception_remains_unmapped() -> None:
    token = CancellationToken()
    task = _RenderTask(_request(1), token)

    with pytest.raises(SystemExit, match="must propagate"):
        _execute_task(_BaseExceptionExecutor(), task)

    assert token.is_cancelled() is False


@pytest.mark.parametrize(
    "error_type",
    (SystemExit, KeyboardInterrupt),
)
def test_real_actor_contains_base_exception_and_drains_latest_pending(
    actor_factory,
    qapp: QApplication,
    error_type: type[BaseException],
) -> None:
    secret = r"secret y=x C:\private\plot.png [1, 2] traceback"
    executor = _ControlledExecutor(
        blocked_ids={1},
        outcomes={1: error_type(secret)},
    )
    actor = actor_factory(executor)
    results = QSignalSpy(actor.result_ready)
    messages: list[str] = []
    messages_lock = Lock()

    def capture_message(message_type, context, message: str) -> None:
        del message_type, context
        with messages_lock:
            messages.append(message)

    previous_handler = qInstallMessageHandler(capture_message)
    try:
        _start_actor(actor)
        first_token = CancellationToken()
        second_token = CancellationToken()
        assert actor.submit(_request(1), first_token) is True
        first_entry = executor.entered.get(timeout=3)
        assert first_entry[0] == 1
        assert actor.submit(_request(2), second_token) is True
        with actor._mailbox._lock:
            assert actor._mailbox.pending is not None
            assert actor._mailbox.pending.request.request_id == 2
            assert actor._mailbox.current_token is first_token

        executor.release(1)
        second_entry = executor.entered.get(timeout=3)
        assert second_entry[0] == 2
        _wait_for_count(results, 1)

        assert results.count() == 1
        payload = results.at(0)[0]
        assert type(payload) is PlotSceneResult
        assert payload.success is True
        assert payload.request_id == 2
        assert first_entry[2] == second_entry[2]
        assert executor.thread_ids == [first_entry[2], second_entry[2]]
        assert actor._worker.thread() is actor._thread
        with actor._mailbox._lock:
            assert actor._mailbox.pending is None
            assert actor._mailbox.current_token is None
            assert actor._mailbox.stop_requested is False
            assert actor._mailbox.result_gate_closed is False

        assert actor.shutdown(5_000) is True
        assert actor._lifecycle is _Lifecycle.STOPPED
        assert actor.is_running is False
        assert actor_module._timed_out_keepalive_count() == 0
        qapp.processEvents()
        with messages_lock:
            exposed_messages = "\n".join(messages)
        assert secret not in exposed_messages
        assert "QThread: Destroyed while thread is still running" not in exposed_messages
    finally:
        executor.release_all()
        if actor.is_running:
            assert actor.shutdown(5_000) is True
        qapp.processEvents()
        qInstallMessageHandler(previous_handler)


class _EmitThreadRecorder(QObject):
    def __init__(self) -> None:
        super().__init__()
        self.thread_ids: Queue[int] = Queue()

    @Slot(object)
    def record(self, result: object) -> None:
        self.thread_ids.put(get_ident())


class _FinalReceiver(QObject):
    received = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.thread_ids: list[int] = []
        self.payloads: list[object] = []

    @Slot(object)
    def receive(self, result: object) -> None:
        self.thread_ids.append(get_ident())
        self.payloads.append(result)
        self.received.emit()


def test_emit_relay_and_receiver_have_explicit_thread_affinity(
    actor_factory,
) -> None:
    gui_thread_id = get_ident()
    executor = _ControlledExecutor()
    actor = actor_factory(executor)
    emit_recorder = _EmitThreadRecorder()
    relay_recorder = _FinalReceiver()
    receiver = _FinalReceiver()
    actor._worker._result_ready.connect(
        emit_recorder.record,
        Qt.ConnectionType.DirectConnection,
    )
    actor.result_ready.connect(
        relay_recorder.receive,
        Qt.ConnectionType.DirectConnection,
    )
    actor.result_ready.connect(
        receiver.receive,
        Qt.ConnectionType.QueuedConnection,
    )
    received = QSignalSpy(receiver.received)
    _start_actor(actor)

    assert actor.submit(_request(1), CancellationToken()) is True
    _wait_for_count(received, 1)

    executor_thread_id = executor.thread_ids[0]
    worker_emit_thread_id = emit_recorder.thread_ids.get(timeout=3)
    assert executor_thread_id == worker_emit_thread_id
    assert relay_recorder.thread_ids == [gui_thread_id]
    assert receiver.thread_ids == [gui_thread_id]
    assert executor_thread_id != gui_thread_id
    assert type(receiver.payloads[0]) is PlotSceneResult


def test_shutdown_cancels_current_closes_gate_and_releases_thread(
    actor_factory,
) -> None:
    executor = _ControlledExecutor(blocked_ids={1})
    actor = actor_factory(executor)
    results = QSignalSpy(actor.result_ready)
    _start_actor(actor)
    token = CancellationToken()

    assert actor.submit(_request(1), token) is True
    assert executor.entered.get(timeout=3)[0] == 1
    cancellation_seen = Event()

    def release_after_shutdown_cancels() -> None:
        assert token._event.wait(3)
        cancellation_seen.set()
        executor.release(1)

    releaser = Thread(target=release_after_shutdown_cancels)
    releaser.start()
    assert actor.shutdown() is True
    releaser.join(timeout=3)

    assert releaser.is_alive() is False
    assert cancellation_seen.is_set()
    assert token.is_cancelled() is True
    assert actor.is_running is False
    assert results.count() == 0
    with actor._mailbox._lock:
        assert actor._mailbox.pending is None
        assert actor._mailbox.current_token is None
        assert actor._mailbox.stop_requested is True
        assert actor._mailbox.result_gate_closed is True


def test_module_boundary_and_worker_slot_are_explicit() -> None:
    source = inspect.getsource(actor_module)
    lowered = source.lower()

    assert actor_module._RenderWorker.staticMetaObject.indexOfSlot("_wake()") >= 0
    assert actor_module.RenderActor.staticMetaObject.indexOfSlot(
        "_relay_result(PyObject)",
    ) >= 0
    assert "terminate" not in lowered
    assert "matplotlib" not in lowered
    assert "pyplot" not in lowered
    assert "math_drawing_assistant.ui" not in lowered
