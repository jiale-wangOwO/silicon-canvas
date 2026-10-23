"""Catalog-backed colors shared by Image Gen briefs and reference renderers.

The selected setting is authoritative. Parsing a human-readable prompt is only
a compatibility path for older saved results that lack a style setting.
"""
from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path
import re


@lru_cache(maxsize=1)
def _palettes():
    catalog = json.loads(Path(__file__).with_name("catalog.json").read_text(encoding="utf-8"))
    return {style["id"]: style["palette"] for style in catalog["styles"]}


def palette(style_id="paper"):
    """Return independent catalog values, using paper for unknown selections."""
    styles = _palettes()
    return deepcopy(styles.get(style_id, styles["paper"]))


def result_palette(result):
    """Resolve current structured settings before considering legacy prose."""
    settings = result.get("settings") or {}
    if settings.get("style"):
        return palette(settings["style"])
    colors = palette()
    match = re.search(r"Palette:\s*([^\n]+)", result.get("style_prompt", ""))
    if match:
        colors.update(re.findall(r"(\w+)\s+(#[0-9a-fA-F]{6})\b", match.group(1)))
        # Older prompts had only the five original palette keys. Do not
        # silently add paper's colored control and boundary extras to them.
        for key in ("control", "outline", "container"):
            if not re.search(r"\b" + key + r"\s+#", match.group(1)):
                colors.pop(key, None)
    return colors


def role_fill(kind, colors):
    """Color semantic resources; interfaces and ownership bodies stay plain."""
    if kind == "memory":
        return colors["secondary"]
    if kind == "compute":
        return colors["primary"]
    if kind in {"control", "state"}:
        return colors.get("control", colors["background"])
    return colors["background"]


def _is_grayscale(colors):
    return all(value[1:3].lower() == value[3:5].lower() == value[5:7].lower()
               for value in colors.values())


def route_color(preferred, colors):
    """Cached route-family hues must not leak into a monochrome selection."""
    return colors["ink"] if not preferred or _is_grayscale(colors) else preferred


def boundary_color(colors, strong=False):
    """Honor explicit outlines, otherwise derive a quiet tone from the ink."""
    key = "outline" if strong else "container"
    if key in colors:
        return colors[key]
    weight = .55 if strong else .25
    channels = [round(int(colors["ink"][i:i + 2], 16) * weight
                      + int(colors["background"][i:i + 2], 16) * (1 - weight))
                for i in (1, 3, 5)]
    return "#" + "".join(f"{value:02X}" for value in channels)
