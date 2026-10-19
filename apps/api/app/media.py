"""Image cleanup for uploads.

Originals are re-saved without EXIF. Public copies are resized and blurred
where a bundled OpenCV cascade finds a face or a licence plate. Models ship
inside opencv-python-headless; nothing is downloaded at runtime.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

_FORMATS = {
    "JPEG": ("image/jpeg", ".jpg"),
    "PNG": ("image/png", ".png"),
    "WEBP": ("image/webp", ".webp"),
}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
_PUBLIC_LONG_SIDE = 1600
_DETECT_LONG_SIDE = 1280

_FACE_CASCADES = (
    "haarcascade_frontalface_default.xml",
    "haarcascade_frontalface_alt2.xml",
)
_PLATE_CASCADE = "haarcascade_russian_plate_number.xml"


_PDF_INFO_KEYS = (b"/Author", b"/Creator", b"/Producer")


def _skip_pdf_literal(raw: bytes, start: int) -> int:
    i = start + 1
    while i < len(raw):
        if raw[i] == 0x5C:
            i += 2
            continue
        if raw[i] == 0x28:
            i = _skip_pdf_literal(raw, i)
            continue
        if raw[i] == 0x29:
            return i + 1
        i += 1
    return len(raw)


def _blank_pdf_key(raw: bytes, key: bytes) -> bytes:
    out = bytearray()
    start = 0
    while True:
        pos = raw.find(key, start)
        if pos < 0:
            out.extend(raw[start:])
            return bytes(out)
        after = pos + len(key)
        boundary = after >= len(raw) or raw[after : after + 1] in (b" ", b"\t", b"\r", b"\n", b"/", b">", b"(", b"<")
        if not boundary:
            out.extend(raw[start : pos + 1])
            start = pos + 1
            continue
        cursor = after
        while cursor < len(raw) and raw[cursor] in b" \t\r\n":
            cursor += 1
        out.extend(raw[start:pos])
        out.extend(key)
        if cursor < len(raw) and raw[cursor] == 0x28:
            out.extend(b" ()")
            start = _skip_pdf_literal(raw, cursor)
            continue
        if cursor < len(raw) and raw[cursor] == 0x3C and not raw.startswith(b"<<", cursor):
            end = raw.find(b">", cursor)
            if end < 0:
                out.extend(raw[pos:])
                return bytes(out)
            out.extend(b" <>")
            start = end + 1
            continue
        out.extend(raw[pos:after])
        start = after


def strip_pdf_author(raw: bytes) -> bytes:
    """Return PDF bytes with author, creator, and producer metadata cleared."""
    if not raw or not raw.startswith(b"%PDF"):
        raise ValueError("Нужен PDF")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise ValueError("Файл больше 10 МБ")
    cleaned = raw
    for key in _PDF_INFO_KEYS:
        cleaned = _blank_pdf_key(cleaned, key)
    cleaned = re.sub(br"<dc:creator>.*?</dc:creator>", b"<dc:creator></dc:creator>", cleaned, flags=re.DOTALL)
    cleaned = re.sub(br"pdf:Author=\"[^\"]*\"", b'pdf:Author=""', cleaned)
    return cleaned


def strip_image(raw: bytes) -> tuple[bytes, str, str]:
    """Return image bytes without embedded metadata, plus content type and suffix."""
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except Exception as exc:
        raise ValueError("Файл не является изображением") from exc
    fmt = (img.format or "").upper()
    if fmt not in _FORMATS:
        raise ValueError("Только jpg, png, webp")
    turned = ImageOps.exif_transpose(img)
    if turned is not None:
        img = turned
    if fmt == "JPEG" and img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    clean = Image.frombytes(img.mode, img.size, img.tobytes())
    out = io.BytesIO()
    if fmt == "JPEG":
        clean.save(out, format="JPEG", quality=90)
    elif fmt == "PNG":
        clean.save(out, format="PNG")
    else:
        clean.save(out, format="WEBP", quality=90)
    content_type, suffix = _FORMATS[fmt]
    return out.getvalue(), content_type, suffix


@dataclass(frozen=True)
class ProcessedUpload:
    original: bytes
    public: bytes
    has_people: bool
    has_plates: bool
    taken_at: str | None
    content_type: str = "image/jpeg"


def _cascade(name: str) -> cv2.CascadeClassifier:
    path = Path(cv2.data.haarcascades) / name
    if not path.is_file():
        raise RuntimeError(f"В пакете OpenCV нет модели {name}")
    cascade = cv2.CascadeClassifier(str(path))
    if cascade.empty():
        raise RuntimeError(f"Не удалось открыть модель {name}")
    return cascade


def _faces() -> list[cv2.CascadeClassifier]:
    return [_cascade(name) for name in _FACE_CASCADES]


def _plates() -> cv2.CascadeClassifier:
    return _cascade(_PLATE_CASCADE)


def _scale_down(bgr: np.ndarray) -> tuple[np.ndarray, float]:
    height, width = bgr.shape[:2]
    longest = max(height, width)
    if longest <= _DETECT_LONG_SIDE:
        return bgr, 1.0
    ratio = _DETECT_LONG_SIDE / longest
    resized = cv2.resize(bgr, (max(1, int(width * ratio)), max(1, int(height * ratio))), interpolation=cv2.INTER_AREA)
    return resized, ratio


def _boxes(found: np.ndarray | tuple) -> list[tuple[int, int, int, int]]:
    if found is None or len(found) == 0:
        return []
    return [(int(x), int(y), int(w), int(h)) for x, y, w, h in found]


def _unmap(rects: list[tuple[int, int, int, int]], ratio: float) -> list[tuple[int, int, int, int]]:
    if ratio == 1.0:
        return rects
    inv = 1 / ratio
    return [(int(x * inv), int(y * inv), max(1, int(w * inv)), max(1, int(h * inv))) for x, y, w, h in rects]


def detect_faces(bgr: np.ndarray) -> list[tuple[int, int, int, int]]:
    work, ratio = _scale_down(bgr)
    gray = cv2.equalizeHist(cv2.cvtColor(work, cv2.COLOR_BGR2GRAY))
    found: list[tuple[int, int, int, int]] = []
    for cascade in _faces():
        found.extend(
            _boxes(cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30)))
        )
    return _unmap(found, ratio)


def detect_plates(bgr: np.ndarray) -> list[tuple[int, int, int, int]]:
    work, ratio = _scale_down(bgr)
    gray = cv2.cvtColor(work, cv2.COLOR_BGR2GRAY)
    found = _boxes(_plates().detectMultiScale(gray, scaleFactor=1.05, minNeighbors=4, minSize=(50, 15)))
    return _unmap(found, ratio)


def blur_regions(
    bgr: np.ndarray,
    rects: list[tuple[int, int, int, int]],
    pad: float = 0.15,
) -> np.ndarray:
    """Strong Gaussian blur on each rectangle, expanded by `pad` on every side."""
    out = bgr.copy()
    height, width = out.shape[:2]
    for x, y, w, h in rects:
        if w < 2 or h < 2:
            continue
        px = round(w * pad)
        py = round(h * pad)
        x0 = max(0, int(x) - px)
        y0 = max(0, int(y) - py)
        x1 = min(width, int(x) + int(w) + px)
        y1 = min(height, int(y) + int(h) + py)
        if x1 - x0 < 3 or y1 - y0 < 3:
            continue
        roi = out[y0:y1, x0:x1]
        side = min(roi.shape[0], roi.shape[1])
        kernel = max(31, (side // 2) | 1)
        kernel = min(kernel, side if side % 2 == 1 else side - 1)
        if kernel < 3:
            continue
        out[y0:y1, x0:x1] = cv2.GaussianBlur(roi, (kernel, kernel), 0)
    return out


def _taken_at(img: Image.Image) -> str | None:
    raw = img.getexif().get(36867) or img.getexif().get(306)
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if len(text) < 19 or text[4] != ":" or text[7] != ":" or text[10] != " ":
        return None
    return f"{text[0:4]}-{text[5:7]}-{text[8:10]}T{text[11:19]}"


def _jpeg(img: Image.Image, quality: int) -> bytes:
    out = io.BytesIO()
    rgb = img if img.mode == "RGB" else img.convert("RGB")
    rgb.save(out, format="JPEG", quality=quality)
    return out.getvalue()


def _limit_long_side(img: Image.Image, limit: int) -> Image.Image:
    width, height = img.size
    longest = max(width, height)
    if longest <= limit:
        return img
    ratio = limit / longest
    size = (max(1, int(width * ratio)), max(1, int(height * ratio)))
    return img.resize(size, Image.Resampling.LANCZOS)


def _open_image(raw: bytes) -> Image.Image:
    if not raw:
        raise ValueError("Пустой файл")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise ValueError("Файл больше 10 МБ")
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except Exception as exc:
        raise ValueError("Файл не является изображением") from exc
    if (img.format or "").upper() not in _FORMATS:
        raise ValueError("Только jpg, png, webp")
    return img


def process_upload(raw: bytes) -> ProcessedUpload:
    """Strip metadata, keep an unblurred original, and build a public JPEG.

    GPS and other EXIF tags are not returned and are not written into either copy.
    `taken_at` comes only from the camera date, when the file has one.
    """
    img = _open_image(raw)
    taken = _taken_at(img)
    turned = ImageOps.exif_transpose(img)
    if turned is not None:
        img = turned
    if img.mode != "RGB":
        img = img.convert("RGB")
    clean = Image.frombytes("RGB", img.size, img.tobytes())
    bgr = cv2.cvtColor(np.asarray(clean), cv2.COLOR_RGB2BGR)
    faces = detect_faces(bgr)
    plates = detect_plates(bgr)
    blurred = blur_regions(bgr, [*faces, *plates])
    public_img = Image.fromarray(cv2.cvtColor(blurred, cv2.COLOR_BGR2RGB))
    public_img = _limit_long_side(public_img, _PUBLIC_LONG_SIDE)
    return ProcessedUpload(
        original=_jpeg(clean, 90),
        public=_jpeg(public_img, 80),
        has_people=bool(faces),
        has_plates=bool(plates),
        taken_at=taken,
    )
