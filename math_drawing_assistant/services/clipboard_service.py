"""GUI-thread-only writes of accepted plot PNGs to an injected clipboard."""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass, replace
from enum import Enum, auto
from time import monotonic
from typing import Callable, Final, Protocol

from PySide6.QtCore import QThread
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from math_drawing_assistant.app_controller import CopyCandidate
from math_drawing_assistant.ui.qt_image import PngDecodeError, qimage_from_png_bytes


QIMAGE_FINGERPRINT_ALGORITHM: Final[str] = "qimage-rgba8888-v1"


class ClipboardBackend(Protocol):
    """Small injectable subset of QClipboard used by this service."""

    def setImage(self, image: QImage) -> None:
        """Write one image to the backend."""


class ClipboardThreadViolationError(RuntimeError):
    """Raised before clipboard work is attempted outside the GUI thread."""


class ClipboardWriteStatus(Enum):
    """Typed outcome of one clipboard write attempt."""

    WRITE_COMPLETED = auto()
    INVALID_IMAGE = auto()
    WRITE_EXCEPTION = auto()


class InternalWriteState(Enum):
    """Lifecycle state of one internal clipboard write context."""

    PENDING = auto()
    COMPLETED = auto()
    FAILED = auto()


@dataclass(frozen=True, slots=True)
class InternalClipboardWrite:
    """Traceable immutable state for one internal clipboard write."""

    request_id: int
    scene_revision: int
    source_png_sha256: str
    internal_image_fingerprint: str
    monotonic_timestamp: float
    state: InternalWriteState


@dataclass(frozen=True, slots=True)
class ClipboardWriteResult:
    """Typed service result without claiming target-application verification."""

    status: ClipboardWriteStatus
    record: InternalClipboardWrite | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, ClipboardWriteStatus):
            raise TypeError("status must be a ClipboardWriteStatus.")
        if self.status is ClipboardWriteStatus.INVALID_IMAGE:
            if self.record is not None:
                raise ValueError("INVALID_IMAGE cannot contain a write record.")
        elif not isinstance(self.record, InternalClipboardWrite):
            raise ValueError("A clipboard write attempt requires a write record.")


def qimage_internal_fingerprint(image: QImage) -> str:
    """Hash canonical RGBA8888 pixels while excluding per-row padding."""

    if not isinstance(image, QImage):
        raise TypeError("image must be a QImage.")
    if image.isNull() or image.width() <= 0 or image.height() <= 0:
        raise ValueError("image must have positive dimensions.")

    canonical = image.convertToFormat(QImage.Format.Format_RGBA8888)
    if canonical.isNull():
        raise ValueError("image could not be converted to RGBA8888.")

    width = canonical.width()
    height = canonical.height()
    row_bytes = width * 4
    bytes_per_line = canonical.bytesPerLine()
    if bytes_per_line < row_bytes:
        raise ValueError("QImage row storage is shorter than its RGBA pixels.")

    pixels = canonical.constBits()
    required_size = bytes_per_line * height
    if pixels.nbytes < required_size:
        raise ValueError("QImage pixel storage is incomplete.")

    digest = hashlib.sha256()
    digest.update(QIMAGE_FINGERPRINT_ALGORITHM.encode("ascii"))
    digest.update(b"\0")
    digest.update(struct.pack(">II", width, height))
    for row in range(height):
        offset = row * bytes_per_line
        digest.update(pixels[offset : offset + row_bytes])
    return digest.hexdigest()


class ClipboardService:
    """Decode and write accepted PNG snapshots on the Qt GUI thread only."""

    def __init__(
        self,
        clipboard_backend: ClipboardBackend,
        *,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if not callable(getattr(clipboard_backend, "setImage", None)):
            raise TypeError("clipboard_backend must provide setImage().")
        if not callable(clock):
            raise TypeError("clock must be callable.")
        self._clipboard_backend = clipboard_backend
        self._clock = clock
        self._active_internal_write: InternalClipboardWrite | None = None
        self._last_internal_write: InternalClipboardWrite | None = None
        self._write_history: list[InternalClipboardWrite] = []

    def write_candidate(self, candidate: CopyCandidate) -> ClipboardWriteResult:
        """Decode, fingerprint, register, and write one copy candidate."""

        self._require_gui_thread()
        if not isinstance(candidate, CopyCandidate):
            raise TypeError("candidate must be a CopyCandidate.")

        try:
            image = qimage_from_png_bytes(candidate.png_bytes)
            source_png_sha256 = hashlib.sha256(candidate.png_bytes).hexdigest()
            internal_fingerprint = qimage_internal_fingerprint(image)
            backend_image = image.copy()
            if backend_image.isNull():
                raise ValueError("decoded image could not be detached.")
        except (PngDecodeError, TypeError, ValueError):
            return ClipboardWriteResult(ClipboardWriteStatus.INVALID_IMAGE)

        pending = InternalClipboardWrite(
            request_id=candidate.request_id,
            scene_revision=candidate.scene_revision,
            source_png_sha256=source_png_sha256,
            internal_image_fingerprint=internal_fingerprint,
            monotonic_timestamp=float(self._clock()),
            state=InternalWriteState.PENDING,
        )
        self._active_internal_write = pending
        self._write_history.append(pending)

        try:
            self._clipboard_backend.setImage(backend_image)
        except Exception:
            failed = replace(pending, state=InternalWriteState.FAILED)
            self._active_internal_write = None
            self._last_internal_write = failed
            self._write_history.append(failed)
            return ClipboardWriteResult(
                ClipboardWriteStatus.WRITE_EXCEPTION,
                failed,
            )

        completed = replace(pending, state=InternalWriteState.COMPLETED)
        self._active_internal_write = None
        self._last_internal_write = completed
        self._write_history.append(completed)
        return ClipboardWriteResult(
            ClipboardWriteStatus.WRITE_COMPLETED,
            completed,
        )

    @property
    def active_internal_write(self) -> InternalClipboardWrite | None:
        """Return the pending write visible during a synchronous backend call."""

        return self._active_internal_write

    @property
    def last_internal_write(self) -> InternalClipboardWrite | None:
        """Return the most recent completed or failed write state."""

        return self._last_internal_write

    @property
    def write_history(self) -> tuple[InternalClipboardWrite, ...]:
        """Return an immutable snapshot of internal write state transitions."""

        return tuple(self._write_history)

    @staticmethod
    def _require_gui_thread() -> None:
        app = QApplication.instance()
        if app is None or QThread.currentThread() != app.thread():
            raise ClipboardThreadViolationError(
                "ClipboardService may only be called on the GUI thread.",
            )
