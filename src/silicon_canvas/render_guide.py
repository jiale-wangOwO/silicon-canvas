"""Optional art-direction thumbnail; it carries no electrical/CAD geometry."""
import io


def render(result, figure):
    if figure.get("representation") not in {"product_render", "system_illustration"}:
        return None
    try:
        from PIL import Image, ImageDraw
        from .publication_render import font
    except ImportError:
        return None
    brief = figure.get("render_brief", {})
    aspect = brief.get("art_direction", {}).get("canvas", result.get("settings", {}).get("aspect", "auto"))
    width, height = {"A4": (1131, 1600), "1:1": (1200, 1200), "4:3": (1600, 1200)}.get(aspect, (1600, 900))
    image = Image.new("RGB", (width, height), "#F7F8FA")
    draw = ImageDraw.Draw(image)
    scale = min(width, height) / 900
    title_font, body_font = font(round(29 * scale)), font(round(21 * scale))
    plan = brief.get("composition_plan", {})
    geometry = plan.get("geometry", "product_identity")
    detail = plan.get("detail_view", {}).get("requested", False)

    def label(x, y, text):
        draw.text((round(x * width), round(y * height)), text, font=body_font, fill="#687789")

    def zone(bounds, text):
        x1, y1, x2, y2 = bounds
        draw.rounded_rectangle((round(x1 * width), round(y1 * height), round(x2 * width), round(y2 * height)),
                               radius=round(22 * scale), fill="#E4E8ED", outline="#B8C1CC", width=max(2, round(2 * scale)))
        label(x1 + .025, y1 + .035, text)

    draw.text((round(.055 * width), round(.045 * height)), "COMPOSITION REFERENCE", font=title_font, fill="#465467")
    label(.055, .105, "Optional framing only - not physical geometry or final artwork")
    if detail:
        zone((.08, .24, .65, .78), "WHOLE SUBJECT")
        zone((.72, .33, .95, .62), "DETAIL")
        label(.72, .66, "Same source object")
    elif geometry == "assembled_section":
        zone((.13, .23, .88, .79), "ONE ASSEMBLED SUBJECT")
        draw.rectangle((round(.53 * width), round(.40 * height), round(.76 * width), round(.65 * height)),
                       outline="#9AA7B5", width=max(2, round(2 * scale)))
        label(.55, .68, "Local section opening")
    elif geometry in {"coherent_assembly", "exploded_assembly"}:
        zone((.12, .22, .88, .80), "WHOLE ASSEMBLY")
        label(.15, .68, "Object arrangement comes from the source")
    elif geometry == "whole_with_context":
        zone((.25, .23, .77, .79), "PRODUCT ANCHOR")
        label(.055, .20, "Annotation space")
    elif geometry == "logical_function_plane":
        zone((.15, .23, .85, .79), "ONE LOGICAL FUNCTION PLANE")
    else:
        zone((.18, .23, .83, .79), "WHOLE PRODUCT")
    footer = "Create the illustration from the source brief. These zones do not specify component count, wiring or placement. Do not draw the guide marks."
    line, lines = "", []
    for word in footer.split():
        proposed = (line + " " + word).strip()
        if draw.textlength(proposed, font=body_font) > width * .89 and line:
            lines.append(line)
            line = word
        else:
            line = proposed
    lines.append(line)
    draw.multiline_text((round(.055 * width), round(.88 * height)), "\n".join(lines), font=body_font, fill="#687789", spacing=round(8 * scale))
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()
