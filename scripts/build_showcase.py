"""Build lightweight homepage images and its two curated rows.

Edit web/assets/showcase.json, then run: python scripts/build_showcase.py
Full-resolution sources stay untouched and are loaded only by the image viewer.
"""
from html import escape
from pathlib import Path
import json

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
START = "<!-- showcase:generated:start -->"
END = "<!-- showcase:generated:end -->"


def build():
    rows = json.loads((WEB / "assets/showcase.json").read_text(encoding="utf-8"))["rows"]
    destination = WEB / "assets/showcase-thumbs"
    destination.mkdir(exist_ok=True)
    markup = [START]
    original_bytes = thumbnail_bytes = 0
    for row_index, entries in enumerate(rows):
        row_id = "artworkStrip" if row_index == 0 else "artworkStripSecondary"
        markup.append(f'      <div id="{row_id}" class="wb-artwork-strip" tabindex="0" aria-label="作品第{row_index + 1}行，两行同步切换，点击查看图片与介绍">')
        for entry in entries:
            source = WEB / entry["source"]
            name = Path(entry["source"].removeprefix("assets/").replace("/", "--")).with_suffix(".webp").name
            thumbnail = destination / name
            with Image.open(source) as image:
                rgba = ImageOps.exif_transpose(image).convert("RGBA")
                original_width, original_height = rgba.size
                preview = Image.new("RGB", rgba.size, "white")
                preview.paste(rgba, mask=rgba.getchannel("A"))
                preview.thumbnail((1120, 440), Image.Resampling.LANCZOS)
                preview.save(thumbnail, "WEBP", quality=84, method=6)
                width, height = preview.size
            original_bytes += source.stat().st_size
            thumbnail_bytes += thumbnail.stat().st_size
            shape = entry.get("shape", "landscape")
            dark = " wb-dark-picture" if entry.get("dark") else ""
            title = escape(entry["title"], quote=True)
            alt = escape(entry["alt"], quote=True)
            href = escape(entry["source"], quote=True)
            origin = escape(entry.get("origin", "imagegen"), quote=True)
            description = escape(entry.get("description", entry["alt"]), quote=True)
            category = escape(entry.get("category", "Silicon Canvas"), quote=True)
            markup.append(f'        <article class="wb-artwork wb-artwork-{shape}" data-original-artwork data-origin="{origin}"><a class="wb-artwork-picture{dark}" href="./{href}" aria-haspopup="dialog" aria-controls="artworkViewer" aria-label="查看作品：{title}" title="{title}" data-title="{title}" data-category="{category}" data-description="{description}" data-origin="{origin}" data-dimensions="{original_width} × {original_height}"><img src="./assets/showcase-thumbs/{name}" width="{width}" height="{height}" alt="{alt}" loading="lazy" decoding="async"></a></article>')
        markup.append("      </div>")
    markup.append("      " + END)
    page = WEB / "index.html"
    html = page.read_text(encoding="utf-8")
    before, rest = html.split(START, 1)
    _, after = rest.split(END, 1)
    page.write_text(before + "\n".join(markup) + after, encoding="utf-8")
    return {"images": sum(map(len, rows)), "original_bytes": original_bytes,
            "thumbnail_bytes": thumbnail_bytes, "saved_percent": round(100 * (1 - thumbnail_bytes / original_bytes), 1)}


if __name__ == "__main__":
    print(json.dumps(build()))
