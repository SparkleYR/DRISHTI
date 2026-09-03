from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from app.errors import AppError, ErrorCode


JPEG_CONTENT_TYPE = "image/jpeg"
JPEG_START = b"\xff\xd8\xff"
START_OF_FRAME_MARKERS = {
    0xC0,
    0xC1,
    0xC2,
    0xC3,
    0xC5,
    0xC6,
    0xC7,
    0xC9,
    0xCA,
    0xCB,
    0xCD,
    0xCE,
    0xCF,
}


@dataclass(frozen=True)
class DecodedFrame:
    width: int
    height: int
    image: np.ndarray


def jpeg_dimensions(data: bytes) -> tuple[int, int]:
    if not data.startswith(JPEG_START):
        raise _decode_error()

    cursor = 2
    while cursor < len(data):
        while cursor < len(data) and data[cursor] != 0xFF:
            cursor += 1
        while cursor < len(data) and data[cursor] == 0xFF:
            cursor += 1
        if cursor >= len(data):
            break

        marker = data[cursor]
        cursor += 1
        if marker in {0x01, *range(0xD0, 0xDA)}:
            continue
        if cursor + 2 > len(data):
            break

        segment_length = int.from_bytes(data[cursor : cursor + 2], "big")
        if segment_length < 2 or cursor + segment_length > len(data):
            break
        if marker in START_OF_FRAME_MARKERS:
            if segment_length < 7:
                break
            height = int.from_bytes(data[cursor + 3 : cursor + 5], "big")
            width = int.from_bytes(data[cursor + 5 : cursor + 7], "big")
            if width <= 0 or height <= 0:
                break
            return width, height
        if marker == 0xDA:
            break
        cursor += segment_length

    raise _decode_error()


def decode_jpeg(
    data: bytes,
    *,
    rotation_degrees: int,
    max_image_width: int,
    max_image_pixels: int,
) -> DecodedFrame:
    encoded_width, encoded_height = jpeg_dimensions(data)
    if encoded_width * encoded_height > max_image_pixels:
        raise AppError(
            ErrorCode.IMAGE_TOO_LARGE,
            "The JPEG dimensions exceed the local processing limit.",
            status_code=413,
        )

    encoded = np.frombuffer(data, dtype=np.uint8)
    image = cv2.imdecode(encoded, cv2.IMREAD_COLOR | cv2.IMREAD_IGNORE_ORIENTATION)
    if image is None or image.ndim != 3 or image.shape[2] != 3:
        raise _decode_error()

    if rotation_degrees == 90:
        image = cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
    elif rotation_degrees == 180:
        image = cv2.rotate(image, cv2.ROTATE_180)
    elif rotation_degrees == 270:
        image = cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)

    height, width = image.shape[:2]
    if width > max_image_width:
        raise AppError(
            ErrorCode.IMAGE_TOO_LARGE,
            "The oriented JPEG width exceeds the session limit.",
            status_code=413,
            details={"max_image_width": max_image_width},
        )
    return DecodedFrame(width=width, height=height, image=image)


def _decode_error() -> AppError:
    return AppError(
        ErrorCode.IMAGE_DECODE_FAILED,
        "The uploaded file is not a decodable JPEG image.",
        status_code=422,
    )
