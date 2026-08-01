"""Focused tests for the GUI-thread-only clipboard write boundary."""

from __future__ import annotations

import base64
import gc
import hashlib
from threading import Thread, get_ident

import pytest
from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QImage

import math_drawing_assistant.services.clipboard_service as clipboard_module
from math_drawing_assistant.app_controller import CopyCandidate
from math_drawing_assistant.services.clipboard_service import (
    ClipboardService,
    ClipboardThreadViolationError,
    ClipboardWriteStatus,
    InternalWriteState,
    qimage_internal_fingerprint,
)


PNG_3X2 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAMAAAACCAYAAACddGYaAAAAEUlEQVR4nGP4z8DwH4YZ"
    "kDkAm34L9XKwuTwAAAAASUVORK5CYII="
)


@pytest.fixture(autouse=True)
def _fake_gui_thread_boundary(monkeypatch) -> None:
    gui_thread_id = get_ident()

    class _Application:
        @classmethod
        def instance(cls) -> _Application:
            return cls()

        def thread(self) -> int:
            return gui_thread_id

    class _Thread:
        @staticmethod
        def currentThread() -> int:
            return get_ident()

    monkeypatch.setattr(clipboard_module, "QApplication", _Application)
    monkeypatch.setattr(clipboard_module, "QThread", _Thread)


class _SignalProbe:
    def __init__(self) -> None:
        self.connect_calls = 0

    def connect(self, slot: object) -> None:
        self.connect_calls += 1


class _FakeClipboard:
    def __init__(self, *, failure: Exception | None = None) -> None:
        self.failure = failure
        self.images: list[QImage] = []
        self.dataChanged = _SignalProbe()
        self.service: ClipboardService | None = None
        self.state_seen_during_set: InternalWriteState | None = None

    def setImage(self, image: QImage) -> None:
        assert self.service is not None
        active = self.service.active_internal_write
        self.state_seen_during_set = None if active is None else active.state
        if self.failure is not None:
            raise self.failure
        self.images.append(image)


def _candidate(png_bytes: bytes = PNG_3X2) -> CopyCandidate:
    return CopyCandidate(
        png_bytes=png_bytes,
        request_id=7,
        scene_revision=3,
        is_stale=False,
    )


def _service(
    backend: _FakeClipboard,
    *,
    timestamp: float = 12.5,
) -> ClipboardService:
    service = ClipboardService(backend, clock=lambda: timestamp)
    backend.service = service
    return service


def _encode_png(*, metadata: str) -> bytes:
    image = QImage(3, 2, QImage.Format.Format_RGBA8888)
    image.fill(0x336699FF)
    image.setText("variant", metadata)
    encoded = QByteArray()
    buffer = QBuffer(encoded)
    assert buffer.open(QIODevice.OpenModeFlag.WriteOnly) is True
    try:
        assert image.save(buffer, "PNG") is True
    finally:
        buffer.close()
    return bytes(encoded)


def test_valid_png_registers_pending_then_completes_one_write(
) -> None:
    backend = _FakeClipboard()
    service = _service(backend)

    outcome = service.write_candidate(_candidate())

    assert outcome.status is ClipboardWriteStatus.WRITE_COMPLETED
    assert len(backend.images) == 1
    assert backend.state_seen_during_set is InternalWriteState.PENDING
    assert service.active_internal_write is None
    assert outcome.record is service.last_internal_write
    assert outcome.record is not None
    assert outcome.record.request_id == 7
    assert outcome.record.scene_revision == 3
    assert outcome.record.source_png_sha256 == hashlib.sha256(PNG_3X2).hexdigest()
    assert outcome.record.monotonic_timestamp == 12.5
    assert outcome.record.state is InternalWriteState.COMPLETED
    assert [record.state for record in service.write_history] == [
        InternalWriteState.PENDING,
        InternalWriteState.COMPLETED,
    ]
    assert backend.dataChanged.connect_calls == 0


@pytest.mark.parametrize("png_bytes", [b"", b"not a png"])
def test_empty_or_invalid_png_is_rejected_without_backend_write(
    png_bytes: bytes,
) -> None:
    backend = _FakeClipboard()
    service = _service(backend)

    outcome = service.write_candidate(_candidate(png_bytes))

    assert outcome.status is ClipboardWriteStatus.INVALID_IMAGE
    assert outcome.record is None
    assert backend.images == []
    assert service.active_internal_write is None
    assert service.last_internal_write is None
    assert service.write_history == ()


def test_backend_exception_transitions_pending_to_failed_not_completed(
) -> None:
    backend = _FakeClipboard(failure=RuntimeError("backend unavailable"))
    service = _service(backend)

    outcome = service.write_candidate(_candidate())

    assert outcome.status is ClipboardWriteStatus.WRITE_EXCEPTION
    assert backend.state_seen_during_set is InternalWriteState.PENDING
    assert service.active_internal_write is None
    assert outcome.record is service.last_internal_write
    assert outcome.record is not None
    assert outcome.record.state is InternalWriteState.FAILED
    assert [record.state for record in service.write_history] == [
        InternalWriteState.PENDING,
        InternalWriteState.FAILED,
    ]
    assert all(
        record.state is not InternalWriteState.COMPLETED
        for record in service.write_history
    )


def test_non_gui_thread_call_is_rejected_before_backend_access(
) -> None:
    backend = _FakeClipboard()
    service = _service(backend)
    errors: list[BaseException] = []

    def call_from_thread() -> None:
        try:
            service.write_candidate(_candidate())
        except BaseException as exc:
            errors.append(exc)

    thread = Thread(target=call_from_thread)
    thread.start()
    thread.join(timeout=3)

    assert thread.is_alive() is False
    assert len(errors) == 1
    assert isinstance(errors[0], ClipboardThreadViolationError)
    assert backend.images == []
    assert service.write_history == ()


def test_same_pixels_with_different_png_encoding_share_internal_fingerprint(
) -> None:
    first_png = _encode_png(metadata="first")
    second_png = _encode_png(metadata="second")
    assert first_png != second_png
    backend = _FakeClipboard()
    service = _service(backend)

    first = service.write_candidate(_candidate(first_png))
    second = service.write_candidate(_candidate(second_png))

    assert first.record is not None
    assert second.record is not None
    assert first.record.source_png_sha256 != second.record.source_png_sha256
    assert (
        first.record.internal_image_fingerprint
        == second.record.internal_image_fingerprint
    )
    assert len(backend.images) == 2


def test_internal_fingerprint_ignores_qimage_row_padding() -> None:
    first_storage = bytearray(
        b"\x11\x22\x33\xff" + b"AAAA" + b"\x44\x55\x66\xff" + b"BBBB"
    )
    second_storage = bytearray(
        b"\x11\x22\x33\xff" + b"xxxx" + b"\x44\x55\x66\xff" + b"yyyy"
    )
    first = QImage(
        first_storage,
        1,
        2,
        8,
        QImage.Format.Format_RGBA8888,
    )
    second = QImage(
        second_storage,
        1,
        2,
        8,
        QImage.Format.Format_RGBA8888,
    )

    assert first.bytesPerLine() == second.bytesPerLine() == 8
    assert qimage_internal_fingerprint(first) == qimage_internal_fingerprint(second)


def test_backend_image_owns_pixels_after_candidate_and_decode_temporaries_die(
) -> None:
    backend = _FakeClipboard()
    service = _service(backend)
    candidate = _candidate(bytes(PNG_3X2))

    assert service.write_candidate(candidate).status is (
        ClipboardWriteStatus.WRITE_COMPLETED
    )
    del candidate
    gc.collect()

    retained = backend.images[0]
    assert retained.isNull() is False
    assert (retained.width(), retained.height()) == (3, 2)
    assert retained.constBits().nbytes >= retained.sizeInBytes()
