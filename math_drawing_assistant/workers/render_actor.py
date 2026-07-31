"""Single-threaded, latest-wins execution for immutable render requests."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from threading import Lock
from typing import Callable, Final, Protocol

from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot

from math_drawing_assistant.models.errors import ErrorCode, ErrorInfo
from math_drawing_assistant.models.requests import PlotSceneRequest
from math_drawing_assistant.models.results import PlotSceneResult
from math_drawing_assistant.workers.cancellation import CancellationToken


_INTERNAL_ERROR = ErrorInfo(
    code=ErrorCode.INTERNAL_ERROR,
    user_message="绘图服务发生内部错误，请重试。",
    recoverable=False,
)
_RESOURCE_ERROR = ErrorInfo(
    code=ErrorCode.RESOURCE_LIMIT_EXCEEDED,
    user_message="绘图资源不足，请缩小输出规模后重试。",
    recoverable=True,
)
_DEFAULT_SHUTDOWN_TIMEOUT_MS: Final[int] = 5_000
_MAX_SHUTDOWN_TIMEOUT_MS: Final[int] = 60_000


class RenderTaskExecutor(Protocol):
    """Injected synchronous render boundary used only by the actor thread."""

    def execute(
        self,
        request: PlotSceneRequest,
        cancellation: CancellationToken,
    ) -> PlotSceneResult:
        """Execute one immutable request cooperatively."""


@dataclass(frozen=True, slots=True)
class _RenderTask:
    request: PlotSceneRequest
    token: CancellationToken


class _Mailbox:
    """Thread-safe single-slot handoff shared by facade and worker."""

    def __init__(self) -> None:
        self._lock = Lock()
        self.pending: _RenderTask | None = None
        self.current_token: CancellationToken | None = None
        self.stop_requested = False
        self.result_gate_closed = False

    def submit(self, task: _RenderTask) -> bool:
        """Atomically replace pending work and cancel all superseded work."""

        with self._lock:
            if self.stop_requested:
                return False

            replaced = self.pending
            self.pending = task
            if replaced is not None:
                replaced.token.cancel()
            if self.current_token is not None:
                self.current_token.cancel()
            return True

    def take_pending(self) -> _RenderTask | None:
        """Move one active pending task to current at a single linearization point."""

        with self._lock:
            if self.stop_requested:
                return None

            task = self.pending
            self.pending = None
            if task is None or task.token.is_cancelled():
                return None
            if self.current_token is not None:
                raise RuntimeError("Render mailbox already has a current task.")
            self.current_token = task.token
            return task

    def complete(
        self,
        token: CancellationToken,
        *,
        has_result: bool,
    ) -> bool:
        """Clear current work and decide result delivery under the mailbox lock."""

        with self._lock:
            owns_current = self.current_token is token
            emit_allowed = (
                owns_current
                and has_result
                and not self.result_gate_closed
                and not token.is_cancelled()
            )
            if owns_current:
                self.current_token = None
            return emit_allowed

    def close(self) -> None:
        """Close submission and result gates while cancelling retained work."""

        with self._lock:
            self.stop_requested = True
            self.result_gate_closed = True
            if self.pending is not None:
                self.pending.token.cancel()
                self.pending = None
            if self.current_token is not None:
                self.current_token.cancel()


def _internal_failure(request: PlotSceneRequest) -> PlotSceneResult:
    return PlotSceneResult(
        request_id=request.request_id,
        scene_revision=request.scene_revision,
        success=False,
        error=_INTERNAL_ERROR,
    )


def _resource_failure(request: PlotSceneRequest) -> PlotSceneResult:
    return PlotSceneResult(
        request_id=request.request_id,
        scene_revision=request.scene_revision,
        success=False,
        error=_RESOURCE_ERROR,
    )


def _validated_executor_result(
    request: PlotSceneRequest,
    result: object,
) -> PlotSceneResult:
    if not isinstance(result, PlotSceneResult):
        return _internal_failure(request)

    try:
        PlotSceneResult.__post_init__(result)
    except Exception:
        return _internal_failure(request)

    if (
        result.request_id != request.request_id
        or result.scene_revision != request.scene_revision
    ):
        return _internal_failure(request)
    return result


def _execute_task(
    executor: RenderTaskExecutor,
    task: _RenderTask,
) -> PlotSceneResult:
    try:
        result = executor.execute(task.request, task.token)
    except MemoryError:
        return _resource_failure(task.request)
    except Exception:
        return _internal_failure(task.request)
    return _validated_executor_result(task.request, result)


def _drain_mailbox(
    mailbox: _Mailbox,
    executor: RenderTaskExecutor,
    publish: Callable[[PlotSceneResult], None],
) -> None:
    """Drain serially, containing non-business BaseException per task."""

    while True:
        task = mailbox.take_pending()
        if task is None:
            return

        result: PlotSceneResult | None = None
        try:
            if task.token.is_cancelled():
                continue
            result = _execute_task(executor, task)
        except BaseException:
            # SystemExit, KeyboardInterrupt, GeneratorExit, and other
            # non-Exception failures end only this task. They are not
            # business results and their text must never cross the Qt boundary.
            pass
        finally:
            emit_allowed = mailbox.complete(
                task.token,
                has_result=result is not None,
            )

        if emit_allowed:
            publish(result)


class _RenderWorker(QObject):
    """QObject that remains affine to the dedicated actor thread."""

    _result_ready = Signal(object)

    def __init__(
        self,
        mailbox: _Mailbox,
        executor: RenderTaskExecutor,
    ) -> None:
        super().__init__()
        self._mailbox = mailbox
        self._executor = executor

    @Slot()
    def _wake(self) -> None:
        _drain_mailbox(
            self._mailbox,
            self._executor,
            self._result_ready.emit,
        )


class _Lifecycle(Enum):
    CREATED = auto()
    STARTED = auto()
    SHUTTING_DOWN = auto()
    TIMED_OUT = auto()
    STOPPED = auto()


class _ThreadFinishObserver(QObject):
    """Release a timed-out keepalive from the actor's owner thread."""

    def __init__(self, registry_key: object) -> None:
        super().__init__()
        self._registry_key = registry_key

    @Slot()
    def _release_keepalive(self) -> None:
        _unregister_timed_out_thread(self._registry_key)


@dataclass(frozen=True, slots=True)
class _TimedOutKeepalive:
    """Temporary ownership for Qt objects whose thread is still running."""

    thread: QThread
    worker: _RenderWorker
    finish_observer: _ThreadFinishObserver


_TIMED_OUT_KEEPALIVES_LOCK = Lock()
_TIMED_OUT_KEEPALIVES: dict[object, _TimedOutKeepalive] = {}


def _register_timed_out_thread(
    registry_key: object,
    *,
    thread: QThread,
    worker: _RenderWorker,
    finish_observer: _ThreadFinishObserver,
) -> None:
    """Prevent premature QObject destruction after a bounded wait expires.

    This registry is only a temporary in-process lifetime guard. A False
    shutdown result still requires the long-lived caller to retain or retry the
    actor and forbids final QApplication, module, or process shutdown.
    """

    keepalive = _TimedOutKeepalive(
        thread=thread,
        worker=worker,
        finish_observer=finish_observer,
    )
    with _TIMED_OUT_KEEPALIVES_LOCK:
        _TIMED_OUT_KEEPALIVES[registry_key] = keepalive


def _unregister_timed_out_thread(registry_key: object) -> None:
    """Drop a keepalive only after the QThread has finished or wait succeeded."""

    with _TIMED_OUT_KEEPALIVES_LOCK:
        _TIMED_OUT_KEEPALIVES.pop(registry_key, None)


def _timed_out_keepalive_count() -> int:
    """Return a synchronized registry size for lifecycle verification."""

    with _TIMED_OUT_KEEPALIVES_LOCK:
        return len(_TIMED_OUT_KEEPALIVES)


def _validate_shutdown_timeout(timeout_ms: object) -> int:
    if isinstance(timeout_ms, bool) or not isinstance(timeout_ms, int):
        raise TypeError("timeout_ms must be an integer.")
    if not 0 <= timeout_ms <= _MAX_SHUTDOWN_TIMEOUT_MS:
        raise ValueError("timeout_ms must be between 0 and 60000 milliseconds.")
    return timeout_ms


class RenderActor(QObject):
    """GUI-thread facade for one persistent serial render worker."""

    result_ready = Signal(object)
    _wake_requested = Signal()

    def __init__(
        self,
        executor: RenderTaskExecutor,
        *,
        shutdown_timeout_ms: int = _DEFAULT_SHUTDOWN_TIMEOUT_MS,
    ) -> None:
        validated_shutdown_timeout_ms = _validate_shutdown_timeout(
            shutdown_timeout_ms,
        )
        super().__init__()
        self._owner_thread = QThread.currentThread()
        self._shutdown_timeout_ms = validated_shutdown_timeout_ms
        self._lifecycle = _Lifecycle.CREATED
        self._mailbox = _Mailbox()
        self._thread = QThread()
        self._registry_key = object()
        self._worker = _RenderWorker(self._mailbox, executor)
        self._finish_observer = _ThreadFinishObserver(self._registry_key)
        self._worker.moveToThread(self._thread)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(
            self._finish_observer._release_keepalive,
            Qt.ConnectionType.QueuedConnection,
        )

        self._wake_requested.connect(
            self._worker._wake,
            Qt.ConnectionType.QueuedConnection,
        )
        self._worker._result_ready.connect(
            self._relay_result,
            Qt.ConnectionType.QueuedConnection,
        )

    @property
    def is_running(self) -> bool:
        """Return whether the dedicated QThread is currently running."""

        return self._thread.isRunning()

    def start(self) -> None:
        """Start the actor thread exactly once."""

        self._require_owner_thread("start")
        if self._lifecycle is not _Lifecycle.CREATED:
            raise RuntimeError("RenderActor.start() may only be called once.")
        self._lifecycle = _Lifecycle.STARTED
        self._thread.start()

    def submit(
        self,
        request: PlotSceneRequest,
        token: CancellationToken,
    ) -> bool:
        """Submit latest work directly into the shared single-slot mailbox."""

        self._require_owner_thread("submit")
        if self._lifecycle is not _Lifecycle.STARTED:
            return False
        if not isinstance(request, PlotSceneRequest):
            raise TypeError("request must be a PlotSceneRequest.")
        if not isinstance(token, CancellationToken):
            raise TypeError("token must be a CancellationToken.")

        accepted = self._mailbox.submit(_RenderTask(request, token))
        if accepted:
            self._wake_requested.emit()
        return accepted

    def shutdown(self, timeout_ms: int | None = None) -> bool:
        """Request cooperative stop and perform one bounded completion wait."""

        self._require_owner_thread("shutdown")
        wait_timeout_ms = (
            self._shutdown_timeout_ms
            if timeout_ms is None
            else _validate_shutdown_timeout(timeout_ms)
        )
        if self._lifecycle is _Lifecycle.STOPPED:
            return True

        if self._lifecycle is _Lifecycle.CREATED:
            self._mailbox.close()
            self._lifecycle = _Lifecycle.STOPPED
            return True

        self._lifecycle = _Lifecycle.SHUTTING_DOWN
        self._mailbox.close()
        self._thread.quit()
        stopped = self._thread.wait(wait_timeout_ms)
        if stopped:
            self._lifecycle = _Lifecycle.STOPPED
            _unregister_timed_out_thread(self._registry_key)
            return True

        self._lifecycle = _Lifecycle.TIMED_OUT
        _register_timed_out_thread(
            self._registry_key,
            thread=self._thread,
            worker=self._worker,
            finish_observer=self._finish_observer,
        )
        return stopped

    @Slot(object)
    def _relay_result(self, result: object) -> None:
        self.result_ready.emit(result)

    def _require_owner_thread(self, operation: str) -> None:
        if not self._owner_thread.isCurrentThread():
            raise RuntimeError(
                f"RenderActor.{operation}() must be called from its owner thread.",
            )


__all__ = ["RenderActor", "RenderTaskExecutor"]
