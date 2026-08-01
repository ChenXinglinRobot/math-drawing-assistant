"""Child process for the frozen M1 process-cold startup protocol."""

from __future__ import annotations

import os
import sys
from typing import Callable, Sequence, TextIO


READY_LINE = "READY"


class ReadyEmitter:
    """Write the protocol marker at most once."""

    def __init__(self, stream: TextIO) -> None:
        self._stream = stream
        self._emitted = False

    @property
    def emitted(self) -> bool:
        return self._emitted

    def emit_once(self) -> bool:
        if self._emitted:
            return False
        self._stream.write(f"{READY_LINE}\n")
        self._stream.flush()
        self._emitted = True
        return True


def formula_input_is_ready(window: object) -> bool:
    """Check the actual formal formula input control, not only its container."""

    panel = getattr(window, "formula_panel")
    input_control = getattr(panel, "_input")
    return bool(
        getattr(window, "isVisible")()
        and getattr(input_control, "isVisible")()
        and getattr(input_control, "isEnabled")()
    )


class StartupProbeLifecycle:
    """Show one formal runtime, emit READY after a turn, then close formally."""

    def __init__(
        self,
        application: object,
        runtime: object,
        *,
        single_shot: Callable[[int, Callable[[], None]], None],
        ready_emitter: ReadyEmitter,
    ) -> None:
        self._application = application
        self._runtime = runtime
        self._single_shot = single_shot
        self._ready_emitter = ready_emitter
        self._exit_code = 0

    def start(self) -> int:
        self._runtime.actor.start()
        self._runtime.window.show()
        # This callback cannot run until the event loop has completed a turn.
        self._single_shot(0, self._after_first_event_loop_turn)
        return int(self._application.exec())

    def _after_first_event_loop_turn(self) -> None:
        if not formula_input_is_ready(self._runtime.window):
            print("startup probe input control is not ready", file=sys.stderr, flush=True)
            self._exit_code = 2
            self._single_shot(0, self._close_formally)
            return
        if not self._ready_emitter.emit_once():
            print("startup probe attempted duplicate READY", file=sys.stderr, flush=True)
            self._exit_code = 3
        self._single_shot(0, self._close_formally)

    def _close_formally(self) -> None:
        closed = bool(self._runtime.window.close())
        if not closed:
            # MainWindow.closeEvent owns the bounded shutdown policy.  A failed
            # close keeps the runtime alive and is retried from the event loop.
            self._single_shot(50, self._close_formally)
            return
        self._application.exit(self._exit_code)


def main(argv: Sequence[str] | None = None) -> int:
    del argv
    if sys.platform != "win32":
        print("startup probe requires native Windows", file=sys.stderr, flush=True)
        return 2
    if not os.environ.get("MPLCONFIGDIR"):
        print("startup probe requires shared MPLCONFIGDIR", file=sys.stderr, flush=True)
        return 2
    platform_override = os.environ.get("QT_QPA_PLATFORM", "").lower()
    if platform_override in {"offscreen", "minimal", "minimalegl"}:
        print("startup probe forbids non-native Qt platforms", file=sys.stderr, flush=True)
        return 2

    # Imported only after MPLCONFIGDIR and native-platform guards are fixed.
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication

    from math_drawing_assistant.bootstrap import create_application_runtime

    application = QApplication.instance() or QApplication(["m1-startup-probe"])
    if QGuiApplication.platformName().lower() != "windows":
        print("startup probe did not load the Windows Qt platform", file=sys.stderr, flush=True)
        return 2
    runtime = create_application_runtime(application)
    application._math_drawing_assistant_runtime = runtime  # type: ignore[attr-defined]
    lifecycle = StartupProbeLifecycle(
        application,
        runtime,
        single_shot=QTimer.singleShot,
        ready_emitter=ReadyEmitter(sys.stdout),
    )
    return lifecycle.start()


if __name__ == "__main__":
    raise SystemExit(main())
