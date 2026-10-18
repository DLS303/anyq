import io

from PIL import Image, ImageOps

_FORMATS = {
    "JPEG": ("image/jpeg", ".jpg"),
    "PNG": ("image/png", ".png"),
    "WEBP": ("image/webp", ".webp"),
}


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
