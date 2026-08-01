"""Stage 11B composition-root ownership and single-Actor tests."""

from __future__ import annotations

from math_drawing_assistant import bootstrap


class _Signal:
    def __init__(self) -> None:
        self.connections: list[object] = []

    def connect(self, slot: object) -> None:
        self.connections.append(slot)


def test_run_builds_one_formal_runtime_and_holds_it_during_exec(
    monkeypatch,
) -> None:
    created_actors: list[_Actor] = []

    class _Executor:
        pass

    class _Actor:
        def __init__(self, executor: object) -> None:
            self.executor = executor
            self.result_ready = _Signal()
            self.started = False
            self.running = False
            self.shutdown_calls = 0
            created_actors.append(self)

        @property
        def is_running(self) -> bool:
            return self.running

        def start(self) -> None:
            self.started = True
            self.running = True

        def submit(self, request: object, token: object) -> bool:
            return self.running

        def shutdown(self) -> bool:
            self.shutdown_calls += 1
            self.running = False
            return True

    class _Window:
        def __init__(self, *, controller: object) -> None:
            self.controller = controller
            self.shown = False

        def handle_render_result(self, result: object) -> None:
            pass

        def show(self) -> None:
            self.shown = True

    class _Application:
        current: _Application | None = None

        def __init__(self, argv: list[str]) -> None:
            self.argv = argv
            self.name = ""
            _Application.current = self

        @classmethod
        def instance(cls) -> _Application | None:
            return cls.current

        def applicationName(self) -> str:
            return self.name

        def setApplicationName(self, name: str) -> None:
            self.name = name

        def exec(self) -> int:
            runtime = self._math_drawing_assistant_runtime
            assert runtime.executor is created_actors[0].executor
            assert runtime.actor is created_actors[0]
            assert runtime.controller is runtime.window.controller
            assert runtime.window.shown is True
            assert runtime.actor.started is True
            assert runtime.actor.result_ready.connections == [
                runtime.window.handle_render_result,
            ]
            assert runtime.controller.shutdown() is True
            return 37

    monkeypatch.setattr(bootstrap, "QApplication", _Application)
    monkeypatch.setattr(bootstrap, "SceneRenderExecutor", _Executor)
    monkeypatch.setattr(bootstrap, "RenderActor", _Actor)
    monkeypatch.setattr(bootstrap, "MainWindow", _Window)

    assert bootstrap.run(["mda-test"]) == 37
    assert len(created_actors) == 1
    app = _Application.current
    assert app is not None
    runtime = app._math_drawing_assistant_runtime
    assert runtime.actor is created_actors[0]
    assert runtime.actor.shutdown_calls == 1

