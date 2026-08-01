"""Stage 11B composition-root ownership and single-Actor tests."""

from __future__ import annotations

from types import SimpleNamespace

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
    created_executors: list[_Executor] = []
    created_clipboard_services: list[_ClipboardService] = []

    class _Executor:
        def __init__(self) -> None:
            created_executors.append(self)

    class _ClipboardService:
        def __init__(self, backend: object) -> None:
            self.backend = backend
            created_clipboard_services.append(self)

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
        def __init__(
            self,
            *,
            controller: object,
            clipboard_service: object,
        ) -> None:
            self.controller = controller
            self.clipboard_service = clipboard_service
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
            self.clipboard_backend = object()
            _Application.current = self

        @classmethod
        def instance(cls) -> _Application | None:
            return cls.current

        def applicationName(self) -> str:
            return self.name

        def setApplicationName(self, name: str) -> None:
            self.name = name

        def clipboard(self) -> object:
            return self.clipboard_backend

        def exec(self) -> int:
            runtime = self._math_drawing_assistant_runtime
            assert runtime.executor is created_actors[0].executor
            assert runtime.actor is created_actors[0]
            assert runtime.controller is runtime.window.controller
            assert runtime.clipboard_service is runtime.window.clipboard_service
            assert runtime.clipboard_service.backend is self.clipboard_backend
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
    monkeypatch.setattr(bootstrap, "ClipboardService", _ClipboardService)
    monkeypatch.setattr(bootstrap, "MainWindow", _Window)

    assert bootstrap.run(["mda-test"]) == 37
    assert len(created_actors) == 1
    app = _Application.current
    assert app is not None
    runtime = app._math_drawing_assistant_runtime
    assert runtime.actor is created_actors[0]
    assert runtime.executor is created_executors[0]
    assert runtime.clipboard_service is created_clipboard_services[0]
    assert len(created_executors) == 1
    assert len(created_clipboard_services) == 1
    assert runtime.actor.shutdown_calls == 1


def test_run_delegates_to_the_formal_runtime_factory(monkeypatch) -> None:
    factory_applications: list[object] = []

    class _Actor:
        def __init__(self) -> None:
            self.started = False
            self.running = False

        @property
        def is_running(self) -> bool:
            return self.running

        def start(self) -> None:
            self.started = True
            self.running = True

    class _Controller:
        def __init__(self, actor: _Actor) -> None:
            self.actor = actor
            self.shutdown_calls = 0

        def shutdown(self) -> bool:
            self.shutdown_calls += 1
            self.actor.running = False
            return True

    class _Window:
        def __init__(self) -> None:
            self.shown = False

        def show(self) -> None:
            self.shown = True

    actor = _Actor()
    controller = _Controller(actor)
    window = _Window()
    runtime = SimpleNamespace(
        executor=object(),
        actor=actor,
        controller=controller,
        clipboard_service=object(),
        window=window,
    )

    class _Application:
        current: _Application | None = None

        def __init__(self, argv: list[str]) -> None:
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
            assert self._math_drawing_assistant_runtime is runtime
            return 19

    def create_runtime(application: object) -> object:
        factory_applications.append(application)
        return runtime

    monkeypatch.setattr(bootstrap, "QApplication", _Application)
    monkeypatch.setattr(bootstrap, "create_application_runtime", create_runtime)

    assert bootstrap.run(["mda-factory-test"]) == 19
    assert factory_applications == [_Application.current]
    assert actor.started is True
    assert window.shown is True
    assert controller.shutdown_calls == 1
