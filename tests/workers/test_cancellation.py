"""Deterministic tests for the cooperative cancellation boundary."""

from __future__ import annotations

import inspect
from threading import Barrier, Thread

import math_drawing_assistant.workers.cancellation as cancellation_module
from math_drawing_assistant.engine.samplers import CancellationProbe
from math_drawing_assistant.workers.cancellation import CancellationToken


def _read_probe(probe: CancellationProbe) -> bool:
    return probe.is_cancelled()


def test_token_starts_active_and_cancel_is_idempotent() -> None:
    token = CancellationToken()

    assert token.is_cancelled() is False
    assert token.cancel() is None
    assert token.is_cancelled() is True
    assert token.cancel() is None
    assert token.is_cancelled() is True


def test_token_set_is_visible_to_multiple_threads() -> None:
    token = CancellationToken()
    thread_count = 4
    ready = Barrier(thread_count)
    cancelled = Barrier(thread_count)
    observations: list[bool] = []

    def set_token() -> None:
        ready.wait()
        token.cancel()
        cancelled.wait()

    def read_token() -> None:
        ready.wait()
        cancelled.wait()
        observations.append(token.is_cancelled())

    threads = [Thread(target=set_token)]
    threads.extend(Thread(target=read_token) for _ in range(thread_count - 1))

    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert all(not thread.is_alive() for thread in threads)
    assert observations == [True] * (thread_count - 1)


def test_token_structurally_satisfies_cancellation_probe() -> None:
    token = CancellationToken()

    assert _read_probe(token) is False
    token.cancel()
    assert _read_probe(token) is True


def test_cancellation_boundary_has_no_gui_or_heavy_rendering_dependencies() -> None:
    source = inspect.getsource(cancellation_module)
    forbidden_terms = ("PySide6", "matplotlib", "numpy", "QWidget", "QThread")

    assert all(term not in source for term in forbidden_terms)
