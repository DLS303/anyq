"""Placeholder icon: the letters Ан on the brand blue. Replace assets/logo.png to swap it."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
BRAND = (47, 91, 138, 255)
INK = (244, 247, 250, 255)
FONT = "/usr/share/fonts/truetype/macos/Inter-Bold.ttf"
TEXT = "Ан"


def canvas(size: int, background: tuple[int, int, int, int] | None) -> Image.Image:
    image = Image.new("RGBA", (size, size), background or (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(FONT, int(size * 0.34))
    box = draw.textbbox((0, 0), TEXT, font=font)
    x = (size - (box[2] - box[0])) / 2 - box[0]
    y = (size - (box[3] - box[1])) / 2 - box[1]
    draw.text((x, y), TEXT, font=font, fill=INK)
    return image


def main() -> None:
    logo = canvas(1024, None)
    assets = ROOT / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    logo.save(assets / "logo.png")

    web = ROOT.parent / "web" / "public" / "icons"
    web.mkdir(parents=True, exist_ok=True)
    for size, name in ((192, "icon-192.png"), (512, "icon-512.png"), (180, "apple-touch-icon.png")):
        canvas(size, BRAND).save(web / name)


if __name__ == "__main__":
    main()
