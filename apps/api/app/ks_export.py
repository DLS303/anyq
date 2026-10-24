"""KS-2 and KS-3 files. Amounts are written in Russian. Signatory lines stay blank."""

from __future__ import annotations

import io
import re
from pathlib import Path

from openpyxl import Workbook
from PIL import Image, ImageDraw, ImageFont

_PHONE = re.compile(r"(?:\+\d|\d)[\d\s().-]{7,}\d")
_ONES = (
    "",
    "один",
    "два",
    "три",
    "четыре",
    "пять",
    "шесть",
    "семь",
    "восемь",
    "девять",
    "десять",
    "одиннадцать",
    "двенадцать",
    "тринадцать",
    "четырнадцать",
    "пятнадцать",
    "шестнадцать",
    "семнадцать",
    "восемнадцать",
    "девятнадцать",
)
_TENS = (
    "",
    "",
    "двадцать",
    "тридцать",
    "сорок",
    "пятьдесят",
    "шестьдесят",
    "семьдесят",
    "восемьдесят",
    "девяносто",
)
_HUNDREDS = (
    "",
    "сто",
    "двести",
    "триста",
    "четыреста",
    "пятьсот",
    "шестьсот",
    "семьсот",
    "восемьсот",
    "девятьсот",
)


def redact(value: str) -> str:
    return _PHONE.sub("***", value or "")


def _triplet(value: int, female: bool) -> str:
    words: list[str] = []
    hundreds, rest = divmod(value, 100)
    if hundreds:
        words.append(_HUNDREDS[hundreds])
    if rest < 20:
        if rest:
            if female and rest == 1:
                words.append("одна")
            elif female and rest == 2:
                words.append("две")
            else:
                words.append(_ONES[rest])
    else:
        tens, ones = divmod(rest, 10)
        words.append(_TENS[tens])
        if ones:
            if female and ones == 1:
                words.append("одна")
            elif female and ones == 2:
                words.append("две")
            else:
                words.append(_ONES[ones])
    return " ".join(part for part in words if part)


def _group(value: int, one: str, few: str, many: str, female: bool) -> str:
    if value == 0:
        return ""
    word = _triplet(value, female)
    tail = value % 100
    if 11 <= tail <= 14:
        form = many
    else:
        last = tail % 10
        form = one if last == 1 else few if last in (2, 3, 4) else many
    return f"{word} {form}".strip()


def int_words(value: int) -> str:
    number = abs(int(value))
    if number == 0:
        return "ноль"
    billions, rest = divmod(number, 1_000_000_000)
    millions, rest = divmod(rest, 1_000_000)
    thousands, ones = divmod(rest, 1000)
    parts = [
        _group(billions, "миллиард", "миллиарда", "миллиардов", False),
        _group(millions, "миллион", "миллиона", "миллионов", False),
        _group(thousands, "тысяча", "тысячи", "тысяч", True),
        _triplet(ones, False),
    ]
    return " ".join(part for part in parts if part)


def money_words(tiyn: int) -> str:
    tenge, rest = divmod(abs(int(tiyn)), 100)
    return f"{int_words(tenge)} тенге {int_words(rest)} тиын"


def xlsx_cell(value):
    if isinstance(value, str) and value[:1] in "=+-@":
        return "'" + value
    return value


def _font_path() -> str:
    here = Path(__file__).resolve().parent / "fonts" / "DejaVuSans.ttf"
    if here.is_file():
        return str(here)
    system = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    if system.is_file():
        return str(system)
    raise RuntimeError("font_missing")


def _pdf_from_jpeg(jpeg: bytes, width: int, height: int) -> bytes:
    stream = (
        f"<< /Type /XObject /Subtype /Image /Width {width} /Height {height} "
        f"/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length {len(jpeg)} >>\n"
        f"stream\n".encode("ascii")
        + jpeg
        + b"\nendstream\nendobj\n"
    )
    objects = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Count 1 /Kids [3 0 R] >>\nendobj\n",
        (
            f"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width} {height}] "
            f"/Contents 4 0 R /Resources << /XObject << /Im 5 0 R >> >> >>\nendobj\n"
        ).encode("ascii"),
        f"4 0 obj\n<< /Length 28 >>\nstream\nq {width} 0 0 {height} 0 0 cm /Im Do Q\nendstream\nendobj\n".encode(
            "ascii"
        ),
        b"5 0 obj\n" + stream,
    ]
    header = b"%PDF-1.4\n"
    body = b""
    offsets = [0]
    cursor = len(header)
    for obj in objects:
        offsets.append(cursor)
        body += obj
        cursor += len(obj)
    xref = [f"xref\n0 {len(offsets)}\n".encode("ascii"), b"0000000000 65535 f \n"]
    for offset in offsets[1:]:
        xref.append(f"{offset:010d} 00000 n \n".encode("ascii"))
    trailer = f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{cursor}\n%%EOF\n".encode("ascii")
    return header + body + b"".join(xref) + trailer


def render_pdf(lines: list[str]) -> bytes:
    font = ImageFont.truetype(_font_path(), 18)
    width = 1400
    height = max(700, 48 + 28 * max(len(lines), 1))
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    y = 24
    for line in lines:
        draw.text((24, y), redact(line)[:180], fill="black", font=font)
        y += 28
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=85)
    return _pdf_from_jpeg(out.getvalue(), width, height)


def render_xlsx(rows: list[list]) -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.title = "KS"
    for row in rows:
        sheet.append([xlsx_cell(cell) for cell in row])
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def ks2_lines(act: dict) -> list[str]:
    lines = [
        "KS-2 Акт о приемке выполненных работ",
        f"Номер {act['number']}",
        f"{act['period_from']} - {act['period_to']}",
        f"{act['act_date']}",
        redact(str(act.get("contract_ref") or "")),
    ]
    for line in act.get("lines") or []:
        lines.append(
            " | ".join(
                [
                    str(line["line_no"]),
                    redact(str(line["name"])),
                    str(line["unit"]),
                    str(line["qty_contract"]),
                    str(line["qty_prev"]),
                    str(line["qty_period"]),
                    str(line["unit_price_tiyn"]),
                    str(line["amount_tiyn"]),
                ]
            )
        )
    lines.append(money_words(int(act["total_with_vat_tiyn"])))
    lines.append(f"vat_bp {act['vat_rate_bp']}")
    lines.append("Сдал ____________________")
    lines.append("Принял ____________________")
    return lines


def ks2_rows(act: dict) -> list[list]:
    rows = [
        ["KS-2", act["number"]],
        ["period", act["period_from"], act["period_to"]],
        ["contract", redact(str(act.get("contract_ref") or ""))],
        ["N", "Наименование", "Ед.", "По договору", "С начала", "За период", "Цена", "Сумма"],
    ]
    for line in act.get("lines") or []:
        rows.append(
            [
                line["line_no"],
                redact(str(line["name"])),
                line["unit"],
                line["qty_contract"],
                line["qty_prev"],
                line["qty_period"],
                line["unit_price_tiyn"],
                line["amount_tiyn"],
            ]
        )
    rows.append(["total_tiyn", act["total_tiyn"]])
    rows.append(["vat_tiyn", act["vat_tiyn"]])
    rows.append(["total_with_vat_tiyn", act["total_with_vat_tiyn"]])
    rows.append(["words", money_words(int(act["total_with_vat_tiyn"]))])
    rows.append(["Сдал", ""])
    rows.append(["Принял", ""])
    return rows


def ks3_lines(report: dict) -> list[str]:
    return [
        "KS-3",
        f"{report['period_from']} - {report['period_to']}",
        f"period {report['period_tiyn']}",
        f"year {report['year_tiyn']}",
        f"start {report['start_tiyn']}",
        money_words(int(report["period_with_vat_tiyn"])),
        "Сдал ____________________",
        "Принял ____________________",
    ]


def ks3_rows(report: dict) -> list[list]:
    return [
        ["KS-3", report["period_from"], report["period_to"]],
        ["period_tiyn", report["period_tiyn"]],
        ["year_tiyn", report["year_tiyn"]],
        ["start_tiyn", report["start_tiyn"]],
        ["period_vat_tiyn", report["period_vat_tiyn"]],
        ["period_with_vat_tiyn", report["period_with_vat_tiyn"]],
        ["words", money_words(int(report["period_with_vat_tiyn"]))],
        ["Сдал", ""],
        ["Принял", ""],
    ]
