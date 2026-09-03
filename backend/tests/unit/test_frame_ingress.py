import cv2
import numpy as np
import pytest

from app.errors import AppError, ErrorCode
from app.frame_ingress import decode_jpeg, jpeg_dimensions


def encoded_image(width: int, height: int, extension: str = ".jpg") -> bytes:
    image = np.zeros((height, width, 3), dtype=np.uint8)
    success, encoded = cv2.imencode(extension, image)
    assert success
    return encoded.tobytes()


def test_reads_jpeg_dimensions_without_decoding_pixels() -> None:
    assert jpeg_dimensions(encoded_image(24, 16)) == (24, 16)


@pytest.mark.parametrize("rotation, expected", [(0, (24, 16)), (90, (16, 24)), (180, (24, 16)), (270, (16, 24))])
def test_decode_returns_orientation_corrected_dimensions(
    rotation: int, expected: tuple[int, int]
) -> None:
    result = decode_jpeg(
        encoded_image(24, 16),
        rotation_degrees=rotation,
        max_image_width=100,
        max_image_pixels=10_000,
    )
    assert (result.width, result.height) == expected
    assert result.image.shape[:2] == (expected[1], expected[0])


@pytest.mark.parametrize("payload", [b"", b"not-an-image", b"\xff\xd8\xffbroken"])
def test_malformed_image_is_rejected(payload: bytes) -> None:
    with pytest.raises(AppError) as exc_info:
        decode_jpeg(
            payload,
            rotation_degrees=0,
            max_image_width=100,
            max_image_pixels=10_000,
        )
    assert exc_info.value.code == ErrorCode.IMAGE_DECODE_FAILED


def test_non_jpeg_bytes_are_rejected_even_if_opencv_can_decode_them() -> None:
    with pytest.raises(AppError) as exc_info:
        decode_jpeg(
            encoded_image(24, 16, ".png"),
            rotation_degrees=0,
            max_image_width=100,
            max_image_pixels=10_000,
        )
    assert exc_info.value.code == ErrorCode.IMAGE_DECODE_FAILED


def test_oversized_dimensions_are_rejected_before_opencv_decode(monkeypatch) -> None:
    called = False

    def fail_if_called(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("OpenCV decode should not run")

    monkeypatch.setattr(cv2, "imdecode", fail_if_called)
    with pytest.raises(AppError) as exc_info:
        decode_jpeg(
            encoded_image(100, 100),
            rotation_degrees=0,
            max_image_width=100,
            max_image_pixels=9_999,
        )
    assert exc_info.value.code == ErrorCode.IMAGE_TOO_LARGE
    assert called is False
