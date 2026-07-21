"""Tests for strict, ownership-safe PNG-to-QImage decoding."""

from __future__ import annotations

import base64
import gc

import pytest

from math_drawing_assistant.ui.qt_image import PngDecodeError, qimage_from_png_bytes


# Hand-authored 3x2 RGBA PNG: six opaque red pixels.  Keeping this tiny,
# fixed Base64 fixture avoids runtime image generation and external inputs.
PNG_3X2 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAMAAAACCAYAAACddGYaAAAAEUlEQVR4nGP4z8DwH4YZ"
    "kDkAm34L9XKwuTwAAAAASUVORK5CYII="
)

# Hand-authored valid 2x1 24-bit BMP; it must be rejected despite decoding
# successfully as a BMP in a general-purpose image loader.
BMP_2X1 = base64.b64decode(
    "Qk0+AAAAAAAAADYAAAAoAAAAAgAAAAEAAAABABgAAAAAAAgAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAD/AAD/AAA="
)


def test_fixed_png_decodes_with_expected_dimensions() -> None:
    image = qimage_from_png_bytes(PNG_3X2)

    assert image.isNull() is False
    assert (image.width(), image.height()) == (3, 2)


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"not an image",
        BMP_2X1,
        PNG_3X2[:16],
    ],
)
def test_invalid_or_incomplete_data_is_rejected(data: bytes) -> None:
    with pytest.raises(PngDecodeError):
        qimage_from_png_bytes(data)


def test_png_signature_with_truncated_body_is_rejected() -> None:
    with pytest.raises(PngDecodeError):
        qimage_from_png_bytes(b"\x89PNG\r\n\x1a\n\x00\x00")


def test_crc_corrupted_png_is_rejected() -> None:
    corrupted = bytearray(PNG_3X2)
    corrupted[45] ^= 0x01

    with pytest.raises(PngDecodeError):
        qimage_from_png_bytes(corrupted)


def test_returned_image_survives_temporary_input_collection() -> None:
    def decode_temporary_input():
        return qimage_from_png_bytes(bytes(PNG_3X2))

    image = decode_temporary_input()
    gc.collect()

    assert (image.width(), image.height()) == (3, 2)
    assert image.pixelColor(0, 0).red() == 255


def test_returned_image_is_isolated_from_mutable_input() -> None:
    mutable_data = bytearray(PNG_3X2)
    image = qimage_from_png_bytes(mutable_data)
    mutable_data[:] = b"\x00" * len(mutable_data)

    assert (image.width(), image.height()) == (3, 2)
    assert image.pixelColor(0, 0).red() == 255


def test_decoder_module_stays_outside_later_layer_dependencies() -> None:
    import math_drawing_assistant.ui.qt_image as qt_image

    source = qt_image.__file__
    assert source is not None
    content = open(source, encoding="utf-8").read()
    for forbidden in ("engine", "QClipboard", "numpy", "sympy", "matplotlib"):
        assert forbidden.lower() not in content.lower()
