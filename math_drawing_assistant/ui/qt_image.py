"""Qt image decoding helpers used by the UI layer.

This module deliberately deals only with ``QImage``.  Converting to
``QPixmap`` and updating widgets remains the GUI-thread-only responsibility
of the preview widget.
"""

from __future__ import annotations

import struct
import zlib

from PySide6.QtGui import QImage


_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class PngDecodeError(ValueError):
    """Raised when bytes are not a complete, decodable PNG image."""


def _validate_png_container(data: bytes) -> None:
    """Reject truncated or CRC-corrupted PNG containers before Qt decodes it."""
    if not data.startswith(_PNG_SIGNATURE):
        raise PngDecodeError("图像数据不是 PNG")

    offset = len(_PNG_SIGNATURE)
    saw_ihdr = False
    saw_idat = False

    while offset < len(data):
        if len(data) - offset < 12:
            raise PngDecodeError("PNG 数据不完整")

        length = struct.unpack(">I", data[offset : offset + 4])[0]
        chunk_type = data[offset + 4 : offset + 8]
        chunk_end = offset + 12 + length
        if chunk_end > len(data):
            raise PngDecodeError("PNG 数据不完整")

        payload = data[offset + 8 : offset + 8 + length]
        expected_crc = struct.unpack(">I", data[offset + 8 + length : chunk_end])[0]
        actual_crc = zlib.crc32(chunk_type + payload) & 0xFFFFFFFF
        if actual_crc != expected_crc:
            raise PngDecodeError("PNG 数据已损坏")

        if not saw_ihdr:
            if chunk_type != b"IHDR" or length != 13:
                raise PngDecodeError("PNG 缺少有效的 IHDR")
            saw_ihdr = True
        elif chunk_type == b"IDAT":
            saw_idat = True
        elif chunk_type == b"IEND":
            if length != 0 or not saw_idat or chunk_end != len(data):
                raise PngDecodeError("PNG 数据不完整")
            return

        offset = chunk_end

    raise PngDecodeError("PNG 缺少结束块")


def qimage_from_png_bytes(data: bytes | bytearray | memoryview) -> QImage:
    """Decode complete PNG bytes into a QImage with independently owned data.

    The defensive ``bytes`` conversion isolates the decoder from a mutable
    caller buffer.  ``QImage.copy()`` then detaches returned pixel storage from
    the temporary decoding buffer and Qt decoder internals.
    """
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise PngDecodeError("PNG 数据必须是字节序列")

    try:
        owned_data = bytes(data)
    except (TypeError, ValueError) as exc:
        raise PngDecodeError("PNG 数据无法读取") from exc

    if not owned_data:
        raise PngDecodeError("PNG 数据为空")

    _validate_png_container(owned_data)

    image = QImage()
    if not image.loadFromData(owned_data, "PNG"):
        raise PngDecodeError("PNG 无法由 Qt 完整解码")
    if image.isNull() or image.width() <= 0 or image.height() <= 0:
        raise PngDecodeError("PNG 解码后没有有效尺寸")

    detached_image = image.copy()
    if (
        detached_image.isNull()
        or detached_image.width() <= 0
        or detached_image.height() <= 0
    ):
        raise PngDecodeError("PNG 图像数据无法独立保存")
    return detached_image
