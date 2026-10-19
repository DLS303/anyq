import io

import cv2
import numpy as np
from PIL import Image
from PIL.TiffImagePlugin import IFDRational

from app.media import blur_regions, detect_faces, detect_plates, process_upload


def _jpeg_with_meta() -> bytes:
    img = Image.new("RGB", (96, 64), (20, 90, 180))
    exif = img.getexif()
    exif[270] = "SECRET-GPS-99"
    exif[36867] = "2026:10:19 08:30:00"
    gps = exif.get_ifd(34853)
    gps[1] = "N"
    gps[2] = (IFDRational(43, 1), IFDRational(15, 1), IFDRational(0, 1))
    gps[3] = "E"
    gps[4] = (IFDRational(76, 1), IFDRational(57, 1), IFDRational(0, 1))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    return buf.getvalue()


def synthetic_face() -> np.ndarray:
    """Frontal face the bundled Haar cascades accept. Drawing only, no photo of a person."""
    size = 400
    rng = np.random.default_rng(1)
    photo = np.full((size, size, 3), (180, 160, 140), np.uint8)
    cx, cy = size // 2, size // 2 + 10
    cv2.ellipse(photo, (cx, cy), (90, 120), 0, 0, 360, (60, 45, 40), -1)
    cv2.ellipse(photo, (cx, cy + 15), (80, 100), 0, 0, 360, (200, 180, 160), -1)
    for dx in (-36, 36):
        cv2.ellipse(photo, (cx + dx, cy - 10), (22, 14), 0, 0, 360, (80, 60, 50), -1)
        cv2.ellipse(photo, (cx + dx, cy - 8), (14, 8), 0, 0, 360, (250, 250, 245), -1)
        cv2.circle(photo, (cx + dx, cy - 8), 5, (30, 20, 15), -1)
    cv2.ellipse(photo, (cx, cy + 18), (10, 18), 0, 0, 360, (170, 140, 120), -1)
    cv2.ellipse(photo, (cx, cy + 55), (28, 12), 0, 10, 170, (90, 40, 50), -1)
    noise = rng.integers(-8, 8, photo.shape, dtype=np.int16)
    return np.clip(photo.astype(np.int16) + noise, 0, 255).astype(np.uint8)


def synthetic_plate() -> np.ndarray:
    img = np.full((280, 700, 3), (20, 20, 20), np.uint8)
    cv2.rectangle(img, (80, 90), (620, 190), (250, 250, 250), -1)
    cv2.rectangle(img, (80, 90), (620, 190), (0, 0, 0), 6)
    cv2.putText(img, "A777AA 02", (110, 160), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (0, 0, 0), 5, cv2.LINE_AA)
    return img


def test_public_copy_drops_exif_and_gps():
    raw = _jpeg_with_meta()
    assert b"SECRET-GPS-99" in raw
    processed = process_upload(raw)
    assert processed.taken_at == "2026-10-19T08:30:00"
    assert processed.has_people is False
    for blob in (processed.original, processed.public):
        image = Image.open(io.BytesIO(blob))
        assert len(image.getexif()) == 0
        assert b"SECRET-GPS-99" not in blob
    dumped = f"{processed.taken_at}"
    assert "43" not in dumped


def test_blur_changes_pixels_inside_a_detected_face():
    image = synthetic_face()
    faces = detect_faces(image)
    assert faces, "bundled face cascade did not see the synthetic face"
    x, y, w, h = faces[0]
    blurred = blur_regions(image, [faces[0]])
    before = image[y : y + h, x : x + w]
    after = blurred[y : y + h, x : x + w]
    assert before.shape == after.shape
    assert not np.array_equal(before, after)


def test_blur_changes_pixels_inside_a_detected_plate():
    image = synthetic_plate()
    plates = detect_plates(image)
    assert plates, "bundled plate cascade did not see the synthetic plate"
    x, y, w, h = plates[0]
    blurred = blur_regions(image, [plates[0]])
    assert not np.array_equal(image[y : y + h, x : x + w], blurred[y : y + h, x : x + w])
