from __future__ import annotations

import hashlib
import math
import os
import random
from pathlib import Path
from typing import Optional


MOOD_PALETTES: dict[str, dict[str, tuple[tuple[int, int, int], tuple[int, int, int], str, str]]] = {
    "开心": {
        "grad": ((255, 183, 77), (255, 110, 64)),
        "emoji": "🌞",
        "decor": ["✨", "🌸", "🎈", "⭐"],
    },
    "难过": {
        "grad": ((83, 120, 149), (61, 64, 91)),
        "emoji": "🌧️",
        "decor": ["💧", "🌙", "☁️", "🌊"],
    },
    "平静": {
        "grad": ((127, 179, 213), (172, 224, 249)),
        "emoji": "🍃",
        "decor": ["🌿", "☁️", "🌾", "🪷"],
    },
    "思考": {
        "grad": ((147, 112, 219), (84, 160, 212)),
        "emoji": "💭",
        "decor": ["🌟", "🔮", "📚", "🌌"],
    },
    "温暖": {
        "grad": ((255, 154, 158), (250, 208, 196)),
        "emoji": "💛",
        "decor": ["🌸", "☕", "🧸", "🌻"],
    },
    "待机": {
        "grad": ((123, 143, 161), (169, 192, 208)),
        "emoji": "💤",
        "decor": ["🌙", "⭐", "☁️", "✨"],
    },
    "陪伴": {
        "grad": ((255, 175, 189), (255, 195, 160)),
        "emoji": "💕",
        "decor": ["🌸", "🎀", "💌", "🌷"],
    },
    "记挂": {
        "grad": ((255, 167, 196), (193, 200, 228)),
        "emoji": "💗",
        "decor": ["🌙", "⭐", "💫", "🌸"],
    },
    "日常": {
        "grad": ((180, 200, 220), (220, 230, 240)),
        "emoji": "📅",
        "decor": ["☀️", "🌿", "☕", "📖"],
    },
    "成长": {
        "grad": ((82, 183, 136), (147, 208, 148)),
        "emoji": "🌱",
        "decor": ["🌿", "🌳", "🍀", "🌻"],
    },
    "害羞": {
        "grad": ((255, 182, 193), (255, 218, 233)),
        "emoji": "🙈",
        "decor": ["💗", "🌸", "🎀", "💮"],
    },
    "焦虑": {
        "grad": ((200, 140, 180), (120, 100, 160)),
        "emoji": "🌀",
        "decor": ["🌙", "💫", "🔮", "⭐"],
    },
    "兴奋": {
        "grad": ((255, 107, 107), (255, 159, 67)),
        "emoji": "🎉",
        "decor": ["✨", "🎊", "🌟", "🎆"],
    },
}


def _get_palette(mood: str = "") -> dict:
    mood_key = (mood or "").strip()
    if mood_key in MOOD_PALETTES:
        return MOOD_PALETTES[mood_key]
    return random.choice(list(MOOD_PALETTES.values()))


def _hex_to_rgb(color: tuple[int, int, int]) -> tuple[int, int, int]:
    return color


def _make_gradient(size: tuple[int, int], color_top: tuple[int, int, int],
                    color_bottom: tuple[int, int, int]) -> "Image.Image":
    from PIL import Image
    w, h = size
    img = Image.new("RGB", (w, h), color_top)
    pixels = img.load()
    for y in range(h):
        ratio = y / max(h - 1, 1)
        r = int(color_top[0] + (color_bottom[0] - color_top[0]) * ratio)
        g = int(color_top[1] + (color_bottom[1] - color_top[1]) * ratio)
        b = int(color_top[2] + (color_bottom[2] - color_top[2]) * ratio)
        for x in range(w):
            pixels[x, y] = (r, g, b)
    return img


def _get_font(size: int, bold: bool = False) -> "ImageFont.FreeTypeFont | ImageFont.ImageFont":
    from PIL import ImageFont
    font_paths = [
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\msyhbd.ttc" if bold else r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\simsun.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]
    for path in font_paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _wrap_text(text: str, font, max_width: int, draw) -> list[str]:
    lines: list[str] = []
    current = ""
    for ch in text:
        test = current + ch
        bbox = draw.textbbox((0, 0), test, font=font)
        w = bbox[2] - bbox[0]
        if w > max_width and current:
            lines.append(current)
            current = ch
        else:
            current = test
    if current:
        lines.append(current)
    return lines


def _add_decor(img: "Image.Image", decor_emojis: list[str], seed: str = "") -> None:
    from PIL import ImageDraw
    rng = random.Random(hashlib.md5(seed.encode("utf-8")).digest() if seed else None)
    draw = ImageDraw.Draw(img, "RGBA")
    w, h = img.size
    small_font = _get_font(28)
    for _ in range(12):
        emoji = rng.choice(decor_emojis)
        x = rng.randint(20, w - 60)
        y = rng.randint(20, h - 60)
        alpha = rng.randint(40, 90)
        try:
            draw.text((x, y), emoji, fill=(255, 255, 255, alpha), font=small_font)
        except Exception:
            pass


def generate_mood_card(
    text: str,
    mood: str = "",
    signature: str = "",
    width: int = 800,
    height: int = 1000,
    output_path: Optional[str | Path] = None,
    seed: str = "",
) -> str:
    from PIL import Image, ImageDraw

    palette = _get_palette(mood)
    color_top, color_bottom = palette["grad"]
    main_emoji = palette["emoji"]
    decor_emojis = palette["decor"]

    img = _make_gradient((width, height), color_top, color_bottom)
    _add_decor(img, decor_emojis, seed=seed or text)

    draw = ImageDraw.Draw(img, "RGBA")

    padding = 60
    content_width = width - padding * 2

    emoji_font = _get_font(72)
    emoji_bbox = draw.textbbox((0, 0), main_emoji, font=emoji_font)
    emoji_w = emoji_bbox[2] - emoji_bbox[0]
    draw.text(((width - emoji_w) / 2, 80), main_emoji, fill=(255, 255, 255, 230), font=emoji_font)

    title_font = _get_font(24, bold=False)
    mood_text = mood or "心情"
    title_bbox = draw.textbbox((0, 0), mood_text, font=title_font)
    title_w = title_bbox[2] - title_bbox[0]
    draw.text(((width - title_w) / 2, 170), mood_text, fill=(255, 255, 255, 200), font=title_font)

    body_font = _get_font(32)
    lines = _wrap_text(text, body_font, content_width, draw)
    line_height = 52
    total_text_height = len(lines) * line_height
    start_y = (height - total_text_height) / 2 - 30

    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=body_font)
        line_w = bbox[2] - bbox[0]
        x = (width - line_w) / 2
        y = start_y + i * line_height
        draw.text((x + 2, y + 2), line, fill=(0, 0, 0, 30), font=body_font)
        draw.text((x, y), line, fill=(255, 255, 255, 240), font=body_font)

    if signature:
        sig_font = _get_font(22)
        sig = f"—— {signature}"
        sig_bbox = draw.textbbox((0, 0), sig, font=sig_font)
        sig_w = sig_bbox[2] - sig_bbox[0]
        draw.text(((width - sig_w) / 2, height - 120), sig,
                  fill=(255, 255, 255, 180), font=sig_font)

    from datetime import datetime
    date_text = datetime.now().strftime("%Y.%m.%d")
    date_font = _get_font(18)
    date_bbox = draw.textbbox((0, 0), date_text, font=date_font)
    date_w = date_bbox[2] - date_bbox[0]
    draw.text(((width - date_w) / 2, height - 70), date_text,
              fill=(255, 255, 255, 140), font=date_font)

    if output_path is None:
        from app import DATA_DIR
        cards_dir = Path(DATA_DIR) / "mood_cards"
        cards_dir.mkdir(parents=True, exist_ok=True)
        card_id = hashlib.md5(f"{text}:{mood}:{datetime.now().isoformat()}".encode("utf-8")).hexdigest()[:12]
        output_path = cards_dir / f"{card_id}.png"

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_path), "PNG")
    return str(output_path)


def generate_abstract_wallpaper(
    style: str = "gradient",
    width: int = 1080,
    height: int = 1920,
    output_path: Optional[str | Path] = None,
    seed: Optional[str] = None,
) -> str:
    from PIL import Image, ImageDraw

    rng = random.Random(seed) if seed else random.Random()

    hue = rng.randint(0, 360)
    hue2 = (hue + rng.randint(30, 80)) % 360

    def hsl_to_rgb(h: float, s: float, l: float) -> tuple[int, int, int]:
        c = (1 - abs(2 * l - 1)) * s
        x = c * (1 - abs((h / 60) % 2 - 1))
        m = l - c / 2
        if h < 60:
            r, g, b = c, x, 0
        elif h < 120:
            r, g, b = x, c, 0
        elif h < 180:
            r, g, b = 0, c, x
        elif h < 240:
            r, g, b = 0, x, c
        elif h < 300:
            r, g, b = x, 0, c
        else:
            r, g, b = c, 0, x
        return (int((r + m) * 255), int((g + m) * 255), int((b + m) * 255))

    color_top = hsl_to_rgb(hue, 0.6, 0.7)
    color_bottom = hsl_to_rgb(hue2, 0.5, 0.5)

    img = _make_gradient((width, height), color_top, color_bottom)
    draw = ImageDraw.Draw(img, "RGBA")

    for _ in range(rng.randint(5, 15)):
        cx = rng.randint(0, width)
        cy = rng.randint(0, height)
        r = rng.randint(50, 300)
        alpha = rng.randint(20, 60)
        hue3 = (hue + rng.randint(-20, 20)) % 360
        cr, cg, cb = hsl_to_rgb(hue3, 0.7, 0.8)
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(cr, cg, cb, alpha))

    for _ in range(rng.randint(20, 60)):
        x = rng.randint(0, width)
        y = rng.randint(0, height)
        s = rng.randint(2, 8)
        alpha = rng.randint(50, 150)
        draw.ellipse((x - s, y - s, x + s, y + s), fill=(255, 255, 255, alpha))

    if output_path is None:
        from app import DATA_DIR
        wp_dir = Path(DATA_DIR) / "wallpapers"
        wp_dir.mkdir(parents=True, exist_ok=True)
        wp_id = hashlib.md5(f"{style}:{seed or rng.random()}".encode("utf-8")).hexdigest()[:12]
        output_path = wp_dir / f"{wp_id}.png"

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_path), "PNG")
    return str(output_path)
