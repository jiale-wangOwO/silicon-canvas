"""Measured publication-size geometry carrier, never the final Image Gen image.

The renderer keeps a physical typography contract.  Labels which cannot fit are
reported; their font is never shrunk to conceal an overfull display projection.
"""
from functools import lru_cache
import io
import math
from pathlib import Path
import re

from .visual_style import boundary_color, result_palette, role_fill, route_color


@lru_cache(maxsize=1)
def font_path():
    path = Path(__file__).resolve().parent / "fonts" / "NotoSansCJKsc-Regular.otf"
    return str(path) if path.is_file() else None


@lru_cache(maxsize=32)
def font(size):
    from PIL import ImageFont
    path = font_path()
    if not path:
        raise RuntimeError("A sans-serif font is required for measured layout")
    return ImageFont.truetype(path, max(1, round(size)), layout_engine=ImageFont.Layout.BASIC)


def pixels_for_points(points, width=1800, target_width_mm=160):
    return points * width / (target_width_mm * 72 / 25.4)


def mandatory_text(text):
    """Numbers, predicates and explicit timing conditions stay visible."""
    text = str(text)
    if re.search(r"\d|[<>=≤≥≠!]|&&|\|\||\b(?:if|when|unless|otherwise|until)\b|若|当|否则|条件", text, re.I):
        return True
    # A complete compact operator expression is technical text.  Natural
    # descriptions such as a multiword phrase joined by '&' are not equations.
    expression = re.fullmatch(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*[&|^]\s*([A-Za-z_][A-Za-z0-9_]*)\s*", text)
    if not expression:
        return False
    operands = expression.groups()
    # Sentence capitalization on a long ordinary word signals prose; actual
    # code identifiers, short variables, acronym names and dense operators stay.
    prose = any(len(word) > 3 and word[0].isupper() and word[1:].islower() for word in operands)
    return not prose


def required_detail(node, spec, literals=()):
    """Distinguish source-reference metadata from actual numeric parameters."""
    detail = node.get("detail", "")
    if any(literal and literal in detail for literal in literals):
        return detail
    reference = re.fullmatch(r"\s*Same\s+(?:private\s+)?resources\s+as\s+([A-Za-z_][\w.-]*)\s*", detail, re.I)
    source_ids = {g["id"] for g in spec.get("groups", [])} | {n["id"] for n in spec.get("nodes", [])}
    if reference and reference.group(1) in source_ids:
        # g_cluster0 is a semantic reference key, not the quantity 0.  The
        # equivalence evidence stays in JSON; it is never image furniture.
        return ""
    # Instance names are identity, not parameters. Remove only this node's
    # full label and its real ancestors' full labels for the *decision*;
    # retain the exact original text whenever a real parameter remains.
    labels = {node.get("label", "")}
    groups = {group["id"]: group for group in spec.get("groups", [])}
    owner, seen = node.get("group", ""), set()
    while owner in groups and owner not in seen:
        seen.add(owner)
        labels.add(groups[owner]["label"])
        owner = groups[owner].get("parent", "")
    remainder = detail
    for label in sorted(filter(None, labels), key=len, reverse=True):
        pattern = r"(?<!\w)" + r"\s*".join(re.escape(part) for part in label.split()) + r"(?!\w)"
        remainder = re.sub(pattern, " ", remainder, flags=re.I)
    return detail if mandatory_text(remainder) else ""


def entry_sources(nid, edges):
    """Logical producers from real projected data evidence, never new ports."""
    sources = set()
    for edge in edges:
        if edge["kind"] not in {"data", "relation"}:
            continue
        if edge["target"] == nid and edge["source"] != nid:
            sources.add(edge["source"])
        if edge.get("bidirectional") and edge["source"] == nid and edge["target"] != nid:
            sources.add(edge["target"])
    return sorted(sources)


def common_gutter_height(body_px, base_height, header_height, count):
    """Readable separate entries: at least 3F and 1.5F between producers."""
    if count < 2:
        return 0
    spacing, margin = math.ceil(body_px * 1.5), math.ceil(body_px * .5)
    # Include the parallel lane's first producer center as the symbol grows.
    # This keeps its arrow level or slightly below, so the next input trunk
    # stops below the first horizontal path rather than hugging its elbow.
    aligned = (base_height / (2 * count) + (count - 1) * spacing + margin - header_height) / (1 - 1 / (2 * count))
    return max(math.ceil(body_px * 3.5), (count - 1) * spacing + 2 * margin, math.ceil(aligned))


def scope_gutter_height(node, body_px, base_height, header_height, ink_header):
    """A projected owner's arrows address its common scope, never a child."""
    count = len(node.get("entry_sources", []))
    gutter = common_gutter_height(body_px, base_height, header_height, count) if count >= 2 else (math.ceil(body_px * 1.4) if ink_header else 0)
    if node.get("logical_group") and node.get("children"):
        ports = max(1, int(node.get("boundary_port_count", 1)))
        gutter = max(gutter, math.ceil(body_px * 1.5), (ports - 1) * math.ceil(body_px * 1.5) + body_px)
    return gutter


def wrap_text(text, face, maximum, max_lines=2):
    """Use exact font advances, with balanced wrapping and no smaller type."""
    text = str(text).strip()
    if not text:
        return [""]
    if face.getlength(text) <= maximum:
        return [text]
    words = text.split()
    candidates = []
    if len(words) > 1:
        for cut in range(1, len(words)):
            lines = [" ".join(words[:cut]), " ".join(words[cut:])]
            widths = [face.getlength(line) for line in lines]
            if max(widths) <= maximum:
                candidates.append((max(widths), abs(widths[0] - widths[1]), lines))
    elif any(ord(char) > 127 for char in text):
        for cut in range(1, len(text)):
            lines = [text[:cut], text[cut:]]
            widths = [face.getlength(line) for line in lines]
            if max(widths) <= maximum:
                candidates.append((max(widths), abs(widths[0] - widths[1]), lines))
    if max_lines >= 2 and candidates:
        return min(candidates)[2]
    if max_lines > 2:
        # Measured multiline labels preserve the entire supplied text and
        # grow the glyph; punctuation is a legitimate typographic break.
        remaining, output = text.strip(), []
        while remaining and len(output) < max_lines:
            if face.getlength(remaining) <= maximum:
                output.append(remaining)
                remaining = ""
                break
            cuts = [i + (0 if char.isspace() else 1) for i, char in enumerate(remaining)
                    if char.isspace() or char in "-_/" or ord(char) > 127]
            valid = [cut for cut in cuts if cut > 0 and face.getlength(remaining[:cut].strip()) <= maximum]
            if not valid:
                return None
            cut = max(valid)
            output.append(remaining[:cut].strip())
            remaining = remaining[cut:].strip()
        if not remaining:
            return output
    return None


def measure_node(node, body_px, maximum=380, child_px=None, symbol_profile="plain", inventory_columns=None, compact_inventory=False):
    """Return a symbol sized to real labels, or an explicit typography failure."""
    face = font(body_px)
    padding = max(22, body_px * .6)
    lines = wrap_text(node["label"], face, maximum - 2 * padding, max_lines=4)
    if lines is None:
        return None
    line_height = math.ceil(body_px * 1.22)
    width = max(120, max(face.getlength(line) for line in lines) + 2 * padding)
    height = len(lines) * line_height + max(22, body_px * .65)
    detail_lines = []
    if node.get("required_detail"):
        detail_lines = wrap_text(node["required_detail"], face, maximum - 2 * padding, max_lines=4)
        if detail_lines is None:
            return None
        width = max(width, max(face.getlength(line) for line in detail_lines) + 2 * padding)
        height += len(detail_lines) * line_height + 10
    children = node.get("children", [])
    child_layout = []
    ink_header = symbol_profile == "ink-header" and node["kind"] == "compute" and len(children) >= 2
    header_height = (len(lines) + len(detail_lines)) * line_height + 22
    entry_gutter_height = math.ceil(body_px * 1.4) if ink_header else 0
    if children:
        child_px = child_px or body_px
        child_face = font(child_px)
        # These children are supplied real resources, not inferred contents.
        columns = min(2, len(children)) if maximum >= 540 else 1
        if inventory_columns is not None:
            columns = min(len(children), inventory_columns)
        child_width = max(200, min(300, (maximum - 3 * padding) / columns))
        for child in children:
            child_lines = wrap_text(child["label"], child_face, child_width - 22, max_lines=4)
            if child_lines is None:
                return None
            if child.get("required_detail"):
                parameter_lines = wrap_text(child["required_detail"], child_face, child_width - 22, max_lines=4)
                if parameter_lines is None:
                    return None
                child_lines += parameter_lines
            child_layout.append({"id": child["id"], "label": child["label"],
                                 "kind": child["kind"], "lines": child_lines})
        rows = math.ceil(len(children) / columns)
        child_height = max(len(c["lines"]) for c in child_layout) * math.ceil(child_px * 1.22) + 24
        row_heights = [max(len(c["lines"]) for c in child_layout[start:start + columns]) * math.ceil(child_px * 1.22) + 24
                       for start in range(0, len(children), columns)] if compact_inventory else [child_height] * rows
        width = max(width, columns * child_width + (columns + 1) * 18)
        height += sum(h + 16 for h in row_heights) + 16
        height = math.ceil(height)
        entry_gutter_height = scope_gutter_height(node, body_px, height, header_height, ink_header)
        height += entry_gutter_height
        for index, item in enumerate(child_layout):
            item["box_px"] = {"x": 18 + index % columns * (child_width + 18),
                              "y": header_height + entry_gutter_height + 10 + sum(h + 16 for h in row_heights[:index // columns]),
                              "width": child_width, "height": row_heights[index // columns]}
    return {"width": math.ceil(width), "height": math.ceil(height), "lines": lines,
            "detail_lines": detail_lines,
            "ink_header": ink_header, "header_height": header_height, "entry_gutter_height": entry_gutter_height,
            "entry_port_spacing_px": math.ceil(body_px * 1.5) if len(node.get("entry_sources", [])) >= 2 else 0,
            "font_px": round(body_px), "line_height": line_height, "children": child_layout}


def _rect(box, width, height):
    return (box["x"] * width, box["y"] * height,
            (box["x"] + box["width"]) * width, (box["y"] + box["height"]) * height)


def _overlap(a, b, margin=0):
    return a[0] < b[2] + margin and b[0] < a[2] + margin and a[1] < b[3] + margin and b[1] < a[3] + margin


def _wire_crosses_rect(a, b, box, margin=0):
    x0, y0, x1, y1 = box
    x0 -= margin; y0 -= margin; x1 += margin; y1 += margin
    if abs(a[0] - b[0]) < .1:
        return x0 < a[0] < x1 and max(min(a[1], b[1]), y0) < min(max(a[1], b[1]), y1)
    if abs(a[1] - b[1]) < .1:
        return y0 < a[1] < y1 and max(min(a[0], b[0]), x0) < min(max(a[0], b[0]), x1)
    return True


def _palette(result):
    return result_palette(result)


def _role_fill(kind, palette):
    return role_fill(kind, palette)


def _symbols_match_source(plan, spec, figure):
    """Validate measured text as well as source mappings in imported caches."""
    source = {node["id"]: node for node in spec["nodes"]}
    required = [*spec.get("verbatim_labels", []), *figure.get("required_verbatim_labels", [])]
    typography = plan["typography"]
    strip = lambda text: re.sub(r"\s", "", text)
    def parameters(node):
        detail = required_detail(node, spec, required)
        if plan.get("scene_id") == "concept" and not any(literal and literal in detail for literal in required):
            # Product views defer implementation parameters to the complete
            # source/caption. Explicitly required text still cannot be hidden.
            return ""
        return detail
    def child_matches(child):
        original = source.get(child["id"])
        return original is not None and original["label"] == child["label"] and original["kind"] == child["kind"] and strip("".join(child["lines"])) == strip(original["label"] + parameters(original))
    for node in plan["macro_nodes"]:
        measured = plan["symbol_metrics"][node["id"]]
        if measured["font_px"] != typography["body_px"] or measured["line_height"] != math.ceil(typography["body_px"] * 1.22):
            return False
        if strip("".join(measured["lines"])) != strip(node["label"]):
            return False
        expected_header = typography.get("symbol_profile", "plain") == "ink-header" and node["kind"] == "compute" and len(measured.get("children", [])) >= 2
        sources = entry_sources(node["id"], plan["macro_edges"]) if len(measured.get("children", [])) >= 2 else []
        current_node = {**node, "entry_sources": sources}
        if node.get("logical_group"):
            if node.get("scope_ports_by_side"):
                counts = {}
                for edge in plan["macro_edges"]:
                    for which in ["source", "target"]:
                        if edge[which] == node["id"]:
                            side = edge.get("routing", {}).get(which + "_side")
                            counts[side] = counts.get(side, 0) + 1
                current_node["boundary_port_count"] = max(counts.values(), default=1)
            else:
                current_node["boundary_port_count"] = sum(node["id"] in {e["source"], e["target"]} for e in plan["macro_edges"])
        expected_gutter = scope_gutter_height(current_node, typography["body_px"], measured["height"] - measured.get("entry_gutter_height", 0),
                                             measured.get("header_height", (len(measured["lines"]) + len(measured.get("detail_lines", []))) * measured["line_height"] + 22), expected_header)
        if bool(measured.get("ink_header")) != expected_header or measured.get("entry_gutter_height", 0) != expected_gutter:
            return False
        if len(node["members"]) == 1 and node["id"] in source:
            if strip("".join(measured.get("detail_lines", []))) != strip(parameters(source[node["id"]])):
                return False
        if any(not child_matches(child) or child["id"] not in node["members"] for child in measured.get("children", [])):
            return False
    objects = {node["id"]: node for node in plan["macro_nodes"]}
    for inset in plan.get("insets", []):
        parent = objects.get(inset["source_object"])
        if parent is None or inset["label"] != parent["label"] or not inset.get("same_hardware"):
            return False
        measured = inset["metrics"]
        if strip("".join(measured["lines"])) != strip(inset["label"]):
            return False
        expected_header = typography.get("symbol_profile", "plain") == "ink-header" and parent["kind"] == "compute" and len(measured["children"]) >= 2
        if bool(measured.get("ink_header")) != expected_header:
            return False
        if any(not child_matches(child) or child["id"] not in parent["members"] for child in measured["children"]):
            return False
    return True


def render(result, figure, labels_only=False):
    """Render a CPS6 guide, validating endpoint, path and typography facts.

    Optional relation labels may be deferred to the caption.  Required literal
    labels fail the guide if no free text region exists.  No text masks wires.
    """
    plan = figure.get("structure_layout")
    if not plan or plan.get("type") != "publication":
        return None
    scene = figure.get("layout_scene") or plan.get("layout_scene")
    if not scene or not scene.get("quality", {}).get("routes_complete"):
        return None
    current_spec = result.get("spec", {})
    if plan.get("source_ownership") != {n["id"]: n.get("group", "") for n in current_spec.get("nodes", [])}:
        return None
    if plan.get("source_group_parents") != {g["id"]: g.get("parent", "") for g in current_spec.get("groups", [])}:
        return None
    if plan.get("source_group_labels") != {g["id"]: g["label"] for g in current_spec.get("groups", [])}:
        return None
    try:
        # Recheck semi-trusted cached projects against their current source.
        from . import publication_layout
        from . import structure_scene
        publication_layout._source_projection(current_spec, {"macro_nodes": plan["macro_nodes"], "macro_edges": plan["macro_edges"],
                "source_edge_indices": plan["source_edge_indices"], "projection": plan.get("projection", {}),
                "required_verbatim_labels": figure.get("required_verbatim_labels", [])})
        expected = {tuple(sorted(edge["members"])): edge for edge in structure_scene._pair(plan["macro_edges"], False)}
        if len(scene["routes"]) != len(expected):
            return None
        for route in scene["routes"]:
            canonical = expected.get(tuple(sorted(route["members"])))
            if canonical is None or any(route.get(key) != canonical.get(key) for key in ["source", "target", "kind", "label", "bidirectional"]):
                return None
        if not _symbols_match_source(plan, current_spec, figure):
            return None
        if not publication_layout.input_trace_quality(plan, scene)["clear"]:
            return None
        if not publication_layout.owner_scope_quality(plan, scene)["clear"]:
            return None
        if not publication_layout.organization_trace_quality(plan, scene)["clear"]:
            return None
    except (KeyError, TypeError, ValueError, IndexError, ZeroDivisionError):
        return None
    try:
        from PIL import Image, ImageDraw
        width, height = scene["width"], scene["height"]
        typography = plan["typography"]
        if not 40 <= typography["target_width_mm"] <= 400 or min(typography["body_pt"], typography["signal_pt"]) < 6:
            return None
        if typography.get("symbol_profile", "plain") not in {"plain", "ink-header"}:
            return None
        if typography["body_px"] < math.ceil(pixels_for_points(typography["body_pt"], width, typography["target_width_mm"])) or typography["signal_px"] < math.ceil(pixels_for_points(typography["signal_pt"], width, typography["target_width_mm"])):
            return None
        main_face, signal_face = font(typography["body_px"]), font(typography["signal_px"])
    except (ImportError, OSError, RuntimeError, KeyError):
        return None
    boxes = {nid: _rect(box, width, height) for nid, box in plan["boxes"].items()}
    paths = []
    for route in scene["routes"]:
        if route["source"] not in boxes or route["target"] not in boxes:
            return None
        if not isinstance(route.get("points"), list) or len(route["points"]) < 2 or any(not isinstance(point, (list, tuple)) or len(point) != 2
                or any(not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1 for value in point)
                for point in route["points"]):
            return None
        points = [(x * width, y * height) for x, y in route["points"]]
        for point, nid in [(points[0], route["source"]), (points[-1], route["target"])]:
            x0, y0, x1, y1 = boxes[nid]
            if not (x0 - .02 <= point[0] <= x1 + .02 and y0 - .02 <= point[1] <= y1 + .02
                    and min(abs(point[0] - x0), abs(point[0] - x1), abs(point[1] - y0), abs(point[1] - y1)) < .02):
                return None
        for a, b in zip(points, points[1:]):
            if abs(a[0] - b[0]) > .02 and abs(a[1] - b[1]) > .02:
                return None
            if any(_wire_crosses_rect(a, b, box, -.05) for box in boxes.values()):
                return None
        paths.append(points)
    palette = _palette(result)
    image = Image.new("RGB", (width, height), palette["background"])
    draw = ImageDraw.Draw(image)
    reserved = list(boxes.values())
    annotation_tasks = []
    for inset in plan.get("insets", []):
        inset_box = _rect(inset["box"], width, height)
        if any(_overlap(inset_box, _rect(container["box"], width, height), 1)
               for container in plan.get("containers", []) if container.get("render_boundary") is not False):
            return None
        if any(_wire_crosses_rect(a, b, inset_box, 6) for path in paths for a, b in zip(path, path[1:])):
            return None
        reserved.append(inset_box)
        annotation = inset.get("annotation_text", "")
        if annotation:
            if annotation not in {"Same hardware detail", "同一硬件细节"} or inset.get("annotation_role") != "same-hardware-view":
                return None
            text_width, text_height = signal_face.getlength(annotation), typography["signal_px"] * 1.22
            marker = (inset_box[0], inset_box[1] - text_height - 14, inset_box[0] + text_width, inset_box[1] - 14)
            if marker[0] < 12 or marker[1] < 12 or marker[2] > inset_box[2] or any(_overlap(marker, other, 8) for other in reserved):
                return None
            if any(_wire_crosses_rect(a, b, marker, 8) for path in paths for a, b in zip(path, path[1:])):
                return None
            reserved.append(marker)
            annotation_tasks.append({"text": annotation, "box_pixels": marker, "color": boundary_color(palette, strong=True),
                                     "source_edge_indices": [], "source_object": inset["source_object"], "role": "same-hardware-view"})
        leader = [(x * width, y * height) for x, y in inset.get("leader", [])]
        leader_regions = [(min(a[0], b[0]) - 8, min(a[1], b[1]) - 8,
                           max(a[0], b[0]) + 8, max(a[1], b[1]) + 8) for a, b in zip(leader, leader[1:])]
        if any(_wire_crosses_rect(a, b, region, 8) for path in paths for a, b in zip(path, path[1:]) for region in leader_regions):
            # Exact matching owner names plus the same-hardware marker are a
            # valid view reference when no free graphical leader exists.
            # Never draw a leader through technical paths to imply a junction.
            inset["leader"] = []
            inset["leader_pixels"] = []
            inset["leader_mode"] = "matched owner name and same-hardware marker"
        else:
            reserved.extend(leader_regions)
            inset["leader_mode"] = "dedicated annotation corridor without arrowhead"
    title_tasks = []
    product_frame = plan.get("presentation_frame")
    product_title = None
    if product_frame:
        source_group = product_frame.get("source_group", "")
        groups = {g["id"]: g for g in current_spec.get("groups", [])}
        expected_label = groups[source_group]["label"] if source_group in groups else current_spec.get("title", "")
        if product_frame.get("label") != expected_label or any(nid not in boxes for nid in product_frame.get("member_ids", [])):
            return None
        fx0, fy0, fx1, fy1 = _rect(product_frame["box"], width, height)
        label = product_frame.get("label", "")
        if label:
            title_width = main_face.getlength(label)
            product_title = (fx0 + 28, fy0 + 22, fx0 + 28 + title_width,
                             fy0 + 22 + typography["body_px"] * 1.3)
            if title_width > fx1 - fx0 - 56 or any(_wire_crosses_rect(a, b, product_title, 8) for path in paths for a, b in zip(path, path[1:])):
                return None
            reserved.append(product_title)
    deferred_scopes = [{"source_group": c["source_group"], "label": c["label"]}
                       for c in plan.get("containers", []) if c.get("render_boundary") is False]
    for container in plan.get("containers", []):
        if container.get("render_boundary") is False:
            continue
        x0, y0, x1, y1 = _rect(container["box"], width, height)
        title = container["label"]
        title_width = main_face.getlength(title)
        title_box = (x0 + 14, y0 - typography["body_px"] * 1.2, x0 + 14 + title_width, y0)
        if container.get("heading_box"):
            proposed = _rect(container["heading_box"], width, height)
            # The title remains above or immediately beside its actual scope;
            # cached geometry cannot move the label onto another resource.
            adjacent = (x0 + 8 <= proposed[0] and proposed[2] <= x1 - 8
                        or abs(proposed[0] - x1 - 14) < .02
                        or abs(proposed[2] - x0 + 14) < .02)
            if (not adjacent or proposed[0] < 8 or proposed[2] > width - 8
                    or abs(proposed[1] - title_box[1]) > .02 or abs(proposed[3] - y0) > .02
                    or abs(proposed[2] - proposed[0] - title_width) > .02):
                return None
            title_box = proposed
        if title_width > x1 - x0 - 30 or any(_wire_crosses_rect(a, b, title_box, 6) for path in paths for a, b in zip(path, path[1:])):
            if any(literal and literal in title for literal in [*current_spec.get("verbatim_labels", []), *figure.get("required_verbatim_labels", [])]):
                return None
            # Logical collections may span external context.  Their source
            # ownership stays in JSON; an impossible label does not justify
            # erasing a wire or pretending this is a physical enclosure.
            container["render_boundary"] = False
            container["boundary_reason"] = "No unobstructed scope heading at publication body size"
            deferred_scopes.append({"source_group": container["source_group"], "label": title})
            continue
        reserved.append(title_box)
        title_tasks.append((container, title_box))
        # Text must not erase an ownership outline. A true interface wire may
        # cross it, but a relationship label earns a wholly clear text region.
        reserved.extend([(x0 - 2, y0, x0 + 2, y1), (x1 - 2, y0, x1 + 2, y1),
                         (x0, y0 - 2, x1, y0 + 2), (x0, y1 - 2, x1, y1 + 2)])
    label_tasks, deferred = [], []
    required = set([*current_spec.get("verbatim_labels", []), *figure.get("required_verbatim_labels", [])])
    for route, points in zip(scene["routes"], paths):
        text = route.get("label", "")
        if not text:
            continue
        # Long technical prose belongs to the caption unless explicitly literal.
        text_width = signal_face.getlength(text)
        text_height = typography["signal_px"] * 1.22
        found = None
        segments = sorted(zip(points, points[1:]), key=lambda p: math.dist(*p), reverse=True)
        for a, b in segments:
            horizontal = abs(a[1] - b[1]) < .1
            # Signal text stays horizontal.  A vertical track needs enough
            # height for the text, not enough length for its horizontal width.
            if math.dist(a, b) < (text_width if horizontal else text_height) + 20:
                continue
            for fraction in [.5, .25, .75]:
                center_x = a[0] + (b[0] - a[0]) * fraction
                center_y = a[1] + (b[1] - a[1]) * fraction
                candidates = [(center_x - text_width / 2, center_y - text_height - 12),
                              (center_x - text_width / 2, center_y + 12)] if horizontal else [
                                  (center_x + 12, center_y - text_height / 2),
                                  (center_x - text_width - 12, center_y - text_height / 2)]
                for x, y in candidates:
                    box = (x, y, x + text_width, y + text_height)
                    if x < 12 or y < 12 or box[2] > width - 12 or box[3] > height - 12:
                        continue
                    if any(_overlap(box, other, 8) for other in reserved):
                        continue
                    if any(_wire_crosses_rect(p, q, box, 6) for path in paths for p, q in zip(path, path[1:])):
                        continue
                    found = box
                    break
                if found:
                    break
            if found:
                break
        if found:
            reserved.append(found)
            label_tasks.append({"text": text, "box_pixels": found, "color": route_color(route.get("line_color"), palette),
                                "route_id": route.get("id"), "source_edge_indices": route.get("members", [])})
        else:
            deferred.append({"text": text, "source_edge_indices": route.get("members", []), "reason": "No unobstructed region at signal font size"})
            product_view = figure.get("design_contract", {}).get("grammar") == "product-concept"
            if any(literal and literal in text for literal in required) or (mandatory_text(text) and not product_view):
                return None
    scene["quality"]["labels_placed"] = len(label_tasks)
    scene["quality"]["deferred_labels"] = deferred
    scene["quality"]["typography_measured"] = True
    scene["quality"]["deferred_scope_titles"] = deferred_scopes
    if labels_only:
        product_labels = [{"text": product_frame["label"], "box": {
            "x": round(product_title[0] / width, 6), "y": round(product_title[1] / height, 6),
            "width": round((product_title[2] - product_title[0]) / width, 6),
            "height": round((product_title[3] - product_title[1]) / height, 6)},
            "color": palette["ink"], "source_edge_indices": []}] if product_title else []
        return {"width": width, "height": height, "body_font_px": typography["body_px"],
                "signal_font_px": typography["signal_px"], "target_width_mm": typography["target_width_mm"],
                "labels": [{"text": item["text"], "box": {"x": round(item["box_pixels"][0] / width, 6),
                                                              "y": round(item["box_pixels"][1] / height, 6),
                                                              "width": round((item["box_pixels"][2] - item["box_pixels"][0]) / width, 6),
                                                              "height": round((item["box_pixels"][3] - item["box_pixels"][1]) / height, 6)},
                            "color": item["color"], "source_edge_indices": item["source_edge_indices"]} for item in label_tasks] + product_labels + [
                    {"text": item["text"], "box": {"x": round(item["box_pixels"][0] / width, 6), "y": round(item["box_pixels"][1] / height, 6),
                                                     "width": round((item["box_pixels"][2] - item["box_pixels"][0]) / width, 6),
                                                     "height": round((item["box_pixels"][3] - item["box_pixels"][1]) / height, 6)},
                     "color": item["color"], "source_edge_indices": [], "source_object": item["source_object"], "role": item["role"]}
                    for item in annotation_tasks],
                "deferred_labels": deferred}

    def arrow(a, b, color):
        length = math.dist(a, b)
        if length < 1:
            return
        dx, dy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
        size = max(10, typography["body_px"] * .35)
        draw.polygon([b, (b[0] - size * dx + size * .35 * dy, b[1] - size * dy - size * .35 * dx),
                      (b[0] - size * dx - size * .35 * dy, b[1] - size * dy + size * .35 * dx)], fill=color)

    scene_id = plan.get("scene_id", "")
    outline = boundary_color(palette, strong=True)
    if product_frame:
        frame_box = _rect(product_frame["box"], width, height)
        draw.rounded_rectangle(frame_box, radius=26, fill=palette["muted"], outline=outline, width=3)
        if product_title:
            draw.text((product_title[0], product_title[1]), product_frame["label"], font=main_face, fill=palette["ink"], anchor="lt")
    for container, _ in title_tasks:
        draw.rectangle(_rect(container["box"], width, height), outline=boundary_color(palette), width=2)
    for route, points in zip(scene["routes"], paths):
        color = route_color(route.get("line_color"), palette)
        dashed = route.get("stroke_style", "dashed" if route["kind"] in {"control", "feedback", "clock"} else "solid") == "dashed"
        for a, b in zip(points, points[1:]):
            length = math.dist(a, b)
            if dashed:
                steps = max(1, math.ceil(length / 20))
                for index in range(steps):
                    t0, t1 = index / steps, min(1, (index + .56) / steps)
                    draw.line([(a[0] + (b[0] - a[0]) * t0, a[1] + (b[1] - a[1]) * t0),
                               (a[0] + (b[0] - a[0]) * t1, a[1] + (b[1] - a[1]) * t1)], fill=color, width=2)
            else:
                draw.line([a, b], fill=color, width=5 if scene_id == "flow" else 3)
        arrow(points[-2], points[-1], color)
        if route.get("bidirectional"):
            arrow(points[1], points[0], color)

    def centered_lines(lines, box, face, line_height, fill):
        x0, y0, x1, y1 = box
        if len(lines) * line_height > y1 - y0 - 12 or any(face.getlength(line) > x1 - x0 - 12 for line in lines):
            return False
        y = (y0 + y1 - len(lines) * line_height) / 2
        for line in lines:
            text_width = face.getlength(line)
            # Anchor at actual glyph top, independent of font ascent defaults.
            draw.text(((x0 + x1 - text_width) / 2, y), line, font=face, fill=fill, anchor="lt")
            y += line_height
        return True

    for node in plan["macro_nodes"]:
        box = boxes[node["id"]]
        measured = plan["symbol_metrics"][node["id"]]
        if re.sub(r"\s", "", "".join(measured["lines"])) != re.sub(r"\s", "", node["label"]):
            return None
        children = measured.get("children", [])
        fill = palette["background"] if children else _role_fill(node["kind"], palette)
        if scene_id in {"concept", "flow"}:
            draw.rounded_rectangle(box, radius=16 if scene_id == "concept" else 9, fill=fill, outline=outline, width=2)
        else:
            draw.rectangle(box, fill=fill, outline=outline, width=2)
        header_height = measured.get("header_height", (len(measured["lines"]) + len(measured.get("detail_lines", []))) * measured["line_height"] + 22)
        header = box if not children else (box[0], box[1], box[2], box[1] + header_height)
        if children:
            draw.rectangle(header, fill=palette["muted"])
        if measured.get("entry_gutter_height", 0):
            draw.rectangle((box[0] + 2, header[3], box[2] - 2, header[3] + measured["entry_gutter_height"]), fill=palette["background"])
        displayed_lines = measured["lines"] + measured.get("detail_lines", [])
        if not centered_lines(displayed_lines, header, main_face, measured["line_height"], palette["ink"]):
            return None
        for child in children:
            source_child = next((n for n in current_spec["nodes"] if n["id"] == child["id"]), None)
            if source_child is None or source_child["label"] != child["label"] or source_child["kind"] != child["kind"]:
                return None
            child_box = child["box_px"]
            cb = (box[0] + child_box["x"], box[1] + child_box["y"],
                  box[0] + child_box["x"] + child_box["width"], box[1] + child_box["y"] + child_box["height"])
            child_fill = _role_fill(child["kind"], palette)
            draw.rectangle(cb, fill=child_fill, outline=outline, width=2)
            if not centered_lines(child["lines"], cb, main_face, math.ceil(typography["body_px"] * 1.22), palette["ink"]):
                return None
    for inset in plan.get("insets", []):
        inset_box = _rect(inset["box"], width, height)
        measured = inset["metrics"]
        # A same-hardware expansion is an explanatory view of an existing
        # owner.  Its leader has no arrowhead and no source-edge member index.
        leader = [(x * width, y * height) for x, y in inset["leader"]]
        for a, b in zip(leader, leader[1:]):
            length = math.dist(a, b)
            steps = max(1, math.ceil(length / 12))
            for index in range(steps):
                t0, t1 = index / steps, min(1, (index + .18) / steps)
                draw.line([(a[0] + (b[0] - a[0]) * t0, a[1] + (b[1] - a[1]) * t0),
                           (a[0] + (b[0] - a[0]) * t1, a[1] + (b[1] - a[1]) * t1)], fill=boundary_color(palette), width=2)
        draw.rectangle(inset_box, fill=palette["background"], outline=outline, width=2)
        header_height = measured.get("header_height", len(measured["lines"]) * measured["line_height"] + 22)
        header_box = (inset_box[0], inset_box[1], inset_box[2], inset_box[1] + header_height)
        draw.rectangle(header_box, fill=palette["muted"])
        if not centered_lines(measured["lines"], (inset_box[0], inset_box[1], inset_box[2], inset_box[1] + header_height),
                              main_face, measured["line_height"], palette["ink"]):
            return None
        for child in measured["children"]:
            source_child = next((n for n in current_spec["nodes"] if n["id"] == child["id"]), None)
            if source_child is None or source_child["label"] != child["label"] or source_child["kind"] != child["kind"]:
                return None
            cb = child["box_px"]
            child_box = (inset_box[0] + cb["x"], inset_box[1] + cb["y"],
                         inset_box[0] + cb["x"] + cb["width"], inset_box[1] + cb["y"] + cb["height"])
            child_fill = _role_fill(child["kind"], palette)
            draw.rectangle(child_box, fill=child_fill, outline=outline, width=2)
            if not centered_lines(child["lines"], child_box, main_face, math.ceil(typography["body_px"] * 1.22), palette["ink"]):
                return None
    for container, box in title_tasks:
        draw.text((box[0], box[1]), container["label"], font=main_face, fill=palette["ink"], anchor="lt")
    for item in label_tasks:
        draw.text(item["box_pixels"][:2], item["text"], font=signal_face, fill=item["color"], anchor="lt")
    for item in annotation_tasks:
        draw.text(item["box_pixels"][:2], item["text"], font=signal_face, fill=item["color"], anchor="lt")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
