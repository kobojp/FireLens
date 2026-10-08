from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "packaging" / "assets"
PNG_PATH = ASSET_DIR / "firelens.png"
ICO_PATH = ASSET_DIR / "firelens.ico"


def _scaled(points: list[tuple[float, float]], scale: int) -> list[tuple[int, int]]:
    return [(round(x * scale), round(y * scale)) for x, y in points]


def draw_icon(size: int = 512) -> Image.Image:
    scale = 4
    canvas = Image.new("RGBA", (size * scale, size * scale), (0, 0, 0, 0))
    d = ImageDraw.Draw(canvas)

    def box(x0: float, y0: float, x1: float, y1: float) -> tuple[int, int, int, int]:
        return tuple(round(v * scale) for v in (x0, y0, x1, y1))  # type: ignore[return-value]

    d.ellipse(box(45, 45, 430, 430), fill=(32, 36, 43, 255))
    d.ellipse(box(67, 67, 408, 408), fill=(59, 66, 78, 255))
    d.ellipse(box(87, 87, 388, 388), fill=(21, 24, 30, 255))

    center = (238.0, 238.0)
    for i in range(8):
        a0 = -112 + i * 45
        p1 = (
            center[0] + math.cos(math.radians(a0)) * 148,
            center[1] + math.sin(math.radians(a0)) * 148,
        )
        p2 = (
            center[0] + math.cos(math.radians(a0 + 35)) * 148,
            center[1] + math.sin(math.radians(a0 + 35)) * 148,
        )
        p3 = (
            center[0] + math.cos(math.radians(a0 + 19)) * 55,
            center[1] + math.sin(math.radians(a0 + 19)) * 55,
        )
        palette = [(218, 45, 38, 255), (239, 67, 34, 255), (245, 102, 30, 255), (230, 52, 36, 255)]
        d.polygon(_scaled([center, p1, p2, p3], scale), fill=palette[i % len(palette)])

    d.ellipse(box(171, 171, 305, 305), fill=(8, 11, 16, 255))
    d.ellipse(box(184, 184, 292, 292), fill=(22, 31, 43, 255))
    d.ellipse(box(198, 198, 278, 278), fill=(14, 19, 27, 255))
    d.ellipse(box(214, 211, 243, 240), fill=(255, 255, 255, 90))

    d.rounded_rectangle(box(305, 176, 399, 403), radius=30 * scale, fill=(183, 20, 27, 255))
    d.rounded_rectangle(box(318, 188, 347, 389), radius=12 * scale, fill=(242, 60, 50, 160))
    d.rectangle(box(298, 190, 407, 218), fill=(36, 39, 45, 255))
    d.rounded_rectangle(box(318, 137, 380, 193), radius=14 * scale, fill=(48, 51, 58, 255))
    d.rounded_rectangle(box(355, 119, 406, 151), radius=12 * scale, fill=(50, 53, 60, 255))
    d.ellipse(
        box(367, 132, 416, 181),
        fill=(224, 228, 232, 255),
        outline=(77, 81, 88, 255),
        width=5 * scale,
    )
    d.line(_scaled([(391, 157), (403, 148)], scale), fill=(193, 24, 31, 255), width=4 * scale)

    hose = _scaled([(401, 201), (438, 235), (438, 295), (414, 321)], scale)
    d.line(hose, fill=(27, 29, 34, 255), width=14 * scale, joint="curve")

    flame_outer = [
        (274, 389),
        (301, 343),
        (319, 362),
        (342, 319),
        (365, 355),
        (397, 322),
        (392, 376),
        (424, 369),
        (390, 420),
        (338, 439),
        (291, 427),
    ]
    d.polygon(_scaled(flame_outer, scale), fill=(245, 72, 27, 255))
    flame_inner = [(319, 411), (336, 374), (349, 393), (367, 367), (373, 405), (352, 422)]
    d.polygon(_scaled(flame_inner, scale), fill=(255, 180, 26, 255))
    d.arc(box(55, 55, 420, 420), start=205, end=318, fill=(126, 136, 150, 180), width=5 * scale)
    d.arc(box(73, 73, 402, 402), start=20, end=118, fill=(90, 98, 110, 150), width=3 * scale)

    return canvas.resize((size, size), Image.Resampling.LANCZOS)


def main() -> None:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    image = draw_icon()
    image.save(PNG_PATH, optimize=True)
    image.save(
        ICO_PATH,
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print(f"Generated: {PNG_PATH}")
    print(f"Generated: {ICO_PATH}")


if __name__ == "__main__":
    main()
