"""Exact ownership-led detail geometry; no hardware facts or raster rendering.

An eligible owner contains actual control, execution and storage resources.
Every supplied view node remains its original ID; context never changes owner.
Normalized corridors are routing hints, not invented ports or interconnects.
"""
from collections import Counter, defaultdict
import copy
import math
import re


def _box(x, y, width, height):
    return {"x": x, "y": y, "width": width, "height": height}


def _normal(box, width, height):
    return {"x": round(box["x"] / width, 6), "y": round(box["y"] / height, 6),
            "width": round(box["width"] / width, 6), "height": round(box["height"] / height, 6)}


def _path(group, groups):
    seen = set()
    while group:
        if group not in groups or group in seen:
            raise ValueError("Invalid or cyclic source containment.")
        seen.add(group)
        yield group
        group = groups[group].get("parent", "")


def _role(node):
    if node["kind"] in {"control", "stage"}:
        return "control"
    if node["kind"] == "memory":
        return "storage"
    return "execution"


def _width(node):
    # Size is driven by the supplied name; no vendor/module-specific lookup.
    text = node["label"]
    unit = .85 if re.search(r"[\u4e00-\u9fff]", text) else .44
    return max(3.4, min(16 if unit == .85 else 11.8, unit * len(text) + 1.2))


def _context_role(node, groups, edges=()):
    owners = " ".join(groups[g]["label"] for g in _path(node.get("group", ""), groups))
    outgoing = [edge for edge in edges if edge["source"] == node["id"]]
    if outgoing and all(edge["kind"] in {"control", "feedback", "clock"} for edge in outgoing):
        return "control"
    if _role(node) == "control":
        return "control"
    if _role(node) == "storage" or re.search(r"\bL[123]\b|cache|memory interface|存储接口", node["label"] + " " + owners, re.I):
        return "storage"
    return "execution"


def _source_order(nodes, edges):
    """Stable source-edge dependency order with cycle-safe source leftovers."""
    ids = {n["id"] for n in nodes}
    forward, indegree = defaultdict(list), Counter()
    for edge in edges:
        a, b = edge["source"], edge["target"]
        if a in ids and b in ids and a != b and b not in forward[a]:
            forward[a].append(b)
            indegree[b] += 1
    ready = [n["id"] for n in nodes if not indegree[n["id"]]]
    ordered = []
    while ready:
        source = ready.pop(0)
        ordered.append(source)
        for target in forward[source]:
            indegree[target] -= 1
            if not indegree[target]:
                ready.append(target)
    ordered.extend(n["id"] for n in nodes if n["id"] not in ordered)
    by_id = {n["id"]: n for n in nodes}
    return [by_id[nid] for nid in ordered]


def build_detail(spec, figure, language="en"):
    """Return exact ownership_detail geometry, or None for other view grammars.

    The caller performs obstacle-aware routing and Image Gen rendering. This
    function retains all selected edges, including parallel and return edges.
    Parent-group membership is data, never inferred from fan-in or box proximity.
    """
    if spec.get("category") not in {"architecture", "microarchitecture"} or figure.get("abstract"):
        return None
    groups = {g["id"]: g for g in spec.get("groups", [])}
    owner = figure.get("main_group")
    if owner not in groups:
        return None
    owner_label = groups[owner]["label"]
    private_marker = r"\bprivate\b|\blocal\b|私有|本地"
    named_private = bool(re.search(private_marker, owner_label, re.I))
    direct = [node for node in spec["nodes"] if node.get("group", "") == owner]
    direct_kinds = {node["kind"] for node in direct}
    direct_private_memory = any(
        node["kind"] == "memory"
        and not re.search(r"\bshared\b|共享", node["label"], re.I)
        and (re.search(private_marker, node["label"], re.I)
             or re.search(r"^(?:private|local)\b|^(?:私有|本地)", node.get("detail", "").strip(), re.I))
        for node in direct
    )
    # Root-level representative clusters need not say "private" in their
    # scope label. Directly owned private storage plus actual local control
    # and execution establishes the detail scope. Descendant PE resources or
    # a parent evidence paragraph mentioning them cannot establish that claim.
    direct_private = bool(direct_private_memory and {"compute", "memory"} <= direct_kinds
                          and direct_kinds & {"control", "stage"})
    private_scope = named_private or direct_private
    if re.search(r"\bshared\b|共享", owner_label, re.I) and not named_private:
        return None
    if not groups[owner].get("parent") and not private_scope:
        return None
    source = {node["id"]: node for node in spec["nodes"]}
    ids = list(figure.get("node_ids", []))
    if len(ids) != len(set(ids)) or any(nid not in source for nid in ids):
        raise ValueError("Detail view must reference unique supplied nodes.")
    indices = list(figure.get("edge_indices", []))
    if len(indices) != len(set(indices)) or any(not isinstance(i, int) or isinstance(i, bool) or not 0 <= i < len(spec["edges"]) for i in indices):
        raise ValueError("Detail view edge indices are invalid.")
    edges = [spec["edges"][i] for i in indices]
    if any(edge["source"] not in ids or edge["target"] not in ids for edge in edges):
        raise ValueError("Detail edge endpoints must be visible in this view.")
    visible_ids = set(ids)
    full_owned = [node for node in spec["nodes"] if owner in set(_path(node.get("group", ""), groups))]
    owned = [node for node in spec["nodes"] if node["id"] in visible_ids and owner in set(_path(node.get("group", ""), groups))]
    context = [node for node in spec["nodes"] if node["id"] in visible_ids and node["id"] not in {item["id"] for item in owned}]
    full_kinds = {node["kind"] for node in full_owned}
    minimum_visible = 2 if figure.get("view_role") in {"control", "datapath"} else 4
    if len(ids) < minimum_visible or not owned or not (full_kinds & {"control", "stage"}) or not {"compute", "memory"} <= full_kinds:
        return None
    # A repeated-unit system scope needs the containment overview, not one
    # giant private detail with the other units folded into its local storage.
    if any(re.search(r"same\s+(?:private\s+)?resources\s+as", node.get("detail", ""), re.I) for node in full_owned):
        return None
    owned_ids = {node["id"] for node in owned}
    local_edges = [edge for edge in edges if edge["source"] in owned_ids and edge["target"] in owned_ids]
    roles = {role: _source_order([n for n in owned if _role(n) == role], local_edges) for role in ("control", "execution", "storage")}
    incoming = Counter(edge["target"] for edge in local_edges)
    entry = next((node for node in roles["control"] if not incoming[node["id"]]), None)
    degree = Counter(endpoint for edge in edges for endpoint in (edge["source"], edge["target"]))
    backbone = max(roles["storage"], key=lambda node: degree[node["id"]], default=None)
    if backbone and degree[backbone["id"]] < 3:
        backbone = None
    def adjacent(nid, candidate_ids):
        return any(edge["kind"] == "data" and ((edge["source"] == nid and edge["target"] in candidate_ids)
                                                or (edge["target"] == nid and edge["source"] in candidate_ids)) for edge in edges)
    context_io = {node["id"] for node in context if node["kind"] == "io"}
    owned_storage = {node["id"] for node in roles["storage"]}
    transfers = [node for node in roles["storage"] if node is not backbone
                 and adjacent(node["id"], context_io) and adjacent(node["id"], owned_storage - {node["id"]})]
    context_placement = {node["id"]: _context_role(node, groups, edges) for node in context}
    context_lanes = {role: [node for node in context if context_placement[node["id"]] == role] for role in ("control", "execution", "storage")}
    parallel_ids = {node["id"] for node in roles["execution"] + transfers}
    parallel = [node for node in owned if node["id"] in parallel_ids]
    columns = min(5, max(1, len(parallel)))
    cell_width = max(_width(node) for node in (parallel or owned))
    owner_width = max(40, columns * cell_width + (columns - 1) * 3 + 6)
    top_count = len(context_lanes["control"])
    top_rows = math.ceil(top_count / 3)
    owner_left, owner_top = 3, 3 + top_rows * 5.6 + (4 if top_count else 0)
    boxes, slots, lanes = {}, {}, []
    cursor = owner_top + 3

    def owned_row(nodes, role, height=2.6, full=False, fill_symbol=False):
        nonlocal cursor
        if not nodes:
            return
        count = 1 if full else min(5, len(nodes))
        rows = math.ceil(len(nodes) / count)
        available = owner_width - 6
        width = available if full else (available - (count - 1) * 3) / count
        for index, node in enumerate(nodes):
            slot = _box(owner_left + 3 + (index % count) * (width + 3), cursor + (index // count) * (height + 3), width, height)
            slots[node["id"]] = slot
            symbol_width = width if fill_symbol else min(width, _width(node))
            boxes[node["id"]] = _box(slot["x"] + (width - symbol_width) / 2, slot["y"], symbol_width, height)
        lanes.append({"id": "owned-" + role + "-" + str(len(lanes)), "role": role,
                      "members": [node["id"] for node in nodes],
                      "box": _box(owner_left + 2.4, cursor - .6, owner_width - 4.8, rows * (height + 3) - 3 + 1.2),
                      "source_owner": owner, "display_only": True})
        cursor += rows * (height + 3) + 1

    if entry:
        owned_row([entry], "control-entry", full=True)
    owned_row([node for node in roles["control"] if node is not entry], "control")
    owned_row(parallel, "execution")
    local_storage = [node for node in roles["storage"] if node is not backbone and node not in transfers]
    if local_storage:
        rows, placed = 1, []
        start_y = cursor
        for index, node in enumerate(local_storage):
            width = min(owner_width - 6, _width(node))
            neighbors = {other for edge in local_edges for endpoint, other in ((edge["source"], edge["target"]), (edge["target"], edge["source"]))
                         if endpoint == node["id"] and other in parallel_ids}
            center = sum(boxes[nid]["x"] + boxes[nid]["width"] / 2 for nid in neighbors) / len(neighbors) if neighbors else owner_left + 3 + (index + .5) * (owner_width - 6) / len(local_storage)
            x = max(owner_left + 3, min(center - width / 2, owner_left + owner_width - 3 - width))
            row = 0
            while any(other_row == row and x < other_x + other_width + 1 and x + width + 1 > other_x for other_row, other_x, other_width in placed):
                row += 1
            rows = max(rows, row + 1)
            placed.append((row, x, width))
            boxes[node["id"]] = _box(x, start_y + row * 5.6, width, 2.6)
            slots[node["id"]] = dict(boxes[node["id"]])
        lanes.append({"id": "owned-local-storage-" + str(len(lanes)), "role": "local-storage",
                      "members": [node["id"] for node in local_storage],
                      "box": _box(owner_left + 2.4, start_y - .6, owner_width - 4.8, rows * 5.6 - 3 + 1.2),
                      "source_owner": owner, "display_only": True})
        cursor += rows * 5.6 + 1
    if backbone:
        owned_row([backbone], "local-storage-backbone", height=3, full=True, fill_symbol=True)
    owner_box = _box(owner_left, owner_top, owner_width, cursor - owner_top + 1)
    for index, node in enumerate(context_lanes["control"]):
        count = min(3, top_count)
        width = (owner_width - (count - 1) * 3) / count
        slot = _box(owner_left + (index % count) * (width + 3), 3 + (index // count) * 5.6, width, 2.6)
        slots[node["id"]] = slot
        symbol_width = min(width, _width(node))
        boxes[node["id"]] = _box(slot["x"] + (width - symbol_width) / 2, slot["y"], symbol_width, 2.6)
    right_cursor = owner_top + 3
    for node in sorted(context_lanes["execution"], key=lambda n: min((boxes[other]["y"] for edge in edges for endpoint, other in ((edge["source"], edge["target"]), (edge["target"], edge["source"])) if endpoint == n["id"] and other in owned_ids), default=owner_top)):
        neighbors = [other for edge in edges for endpoint, other in ((edge["source"], edge["target"]), (edge["target"], edge["source"])) if endpoint == node["id"] and other in owned_ids]
        target_y = sum(boxes[nid]["y"] + boxes[nid]["height"] / 2 for nid in neighbors) / len(neighbors) - 1.3 if neighbors else right_cursor
        y = max(right_cursor, target_y)
        boxes[node["id"]] = _box(owner_left + owner_width + 6, y, _width(node), 2.6)
        slots[node["id"]] = dict(boxes[node["id"]])
        right_cursor = y + 5.6
    bottom_top = owner_box["y"] + owner_box["height"] + 6
    for index, node in enumerate(context_lanes["storage"]):
        count = min(3, len(context_lanes["storage"]))
        width = (owner_width - (count - 1) * 3) / count
        slot = _box(owner_left + (index % count) * (width + 3), bottom_top + (index // count) * 5.6, width, 2.6)
        slots[node["id"]] = slot
        symbol_width = min(width, _width(node))
        boxes[node["id"]] = _box(slot["x"] + (width - symbol_width) / 2, slot["y"], symbol_width, 2.6)
    width = max(box["x"] + box["width"] for box in boxes.values()) + 3
    height = max(owner_box["y"] + owner_box["height"], *(box["y"] + box["height"] for box in boxes.values())) + 3
    normalized = {nid: _normal(box, width, height) for nid, box in boxes.items()}
    normalized_slots = {nid: _normal(slot, width, height) for nid, slot in slots.items()}
    frame = {"id": owner, "label": groups[owner]["label"], "parent": groups[owner].get("parent", ""),
             "box": _normal(owner_box, width, height), "source_group": owner,
             "source_members": [node["id"] for node in owned], "members": [node["id"] for node in owned],
             "scope_source_members": [node["id"] for node in full_owned],
             "ownership_unchanged": True, "replaces_region": owner, "is_system_boundary": True}
    macro_nodes = [{"id": nid, "label": source[nid]["label"], "kind": source[nid]["kind"], "type": "resource",
                    "detail": source[nid].get("detail", ""), "members": [nid],
                    "source_group": source[nid].get("group", ""), "source_owner": source[nid].get("group", ""),
                    "context": nid not in owned_ids, "box": normalized[nid],
                    "slot_box": normalized_slots[nid],
                    "zone": "owned-" + _role(source[nid]) if nid in owned_ids else "context-" + context_placement[nid]} for nid in ids]
    for node in macro_nodes:
        if node["id"] in {item["id"] for item in transfers}:
            node["visual_lane"] = "execution-transfer"
        if backbone and node["id"] == backbone["id"]:
            node["visual_caption_policy"] = {"max_lines": 2, "numeric_only": True, "full_detail_stays_in_caption": True}
    for lane in lanes:
        lane["box"] = _normal(lane["box"], width, height)
    corridor_specs = {
        "top-control": _box(owner_left, owner_top - 3, owner_width, 2),
        "right-services": _box(owner_left + owner_width + 1, owner_top, 4, owner_box["height"]),
        "bottom-memory": _box(owner_left, owner_box["y"] + owner_box["height"] + 1, owner_width, 4),
        "local-left-return": _box(owner_left + .5, owner_top + 2, 1.2, owner_box["height"] - 3),
        "local-right-control": _box(owner_left + owner_width - 1.7, owner_top + 2, 1.2, owner_box["height"] - 3),
    }
    counts = Counter()
    projected = []
    for index, edge in zip(indices, edges):
        a, b = edge["source"], edge["target"]
        external = [nid for nid in (a, b) if nid not in owned_ids]
        if external:
            context_roles = {context_placement[nid] for nid in external}
            corridor = "top-control" if "control" in context_roles else "bottom-memory" if "storage" in context_roles else "right-services"
        else:
            corridor = "local-right-control" if edge["kind"] in {"control", "feedback", "clock"} else "local-left-return"
        source_box, target_box = normalized[a], normalized[b]
        if source_box["y"] + source_box["height"] <= target_box["y"]:
            source_side, target_side = "bottom", "top"
        elif target_box["y"] + target_box["height"] <= source_box["y"]:
            source_side, target_side = "top", "bottom"
        else:
            source_side, target_side = ("right", "left") if source_box["x"] < target_box["x"] else ("left", "right")
        projected.append({"id": "E" + str(index + 1), "source": a, "target": b,
                          "kind": edge["kind"], "label": edge.get("label", ""), "members": [index],
                          "source_nodes": [a], "target_nodes": [b],
                          "routing": {"corridor": corridor, "track": counts[corridor],
                                      "source_side": source_side, "target_side": target_side,
                                      "obstacle_aware_routing_required": True, "no_broadcast_bus_is_inferred": True}})
        counts[corridor] += 1
    for edge in projected:
        edge["routing"]["track_fraction"] = (edge["routing"]["track"] + .5) / counts[edge["routing"]["corridor"]]
    return {"type": "ownership_detail", "view_type": "ownership-led-private-detail", "abstract": False,
            "title": figure.get("title", groups[owner]["label"]), "main_group": owner,
            "macro_nodes": macro_nodes, "macro_edges": projected, "projected_links": projected,
            "deferred_links": [], "internal_edges": [], "edge_indices": indices,
            "node_ids": ids, "boxes": normalized, "containers": [frame],
            "slot_boxes": normalized_slots, "transfer_nodes": [node["id"] for node in transfers],
            "system_frame": {**frame, "display_only": False, "not_an_added_hardware_node": True, "replaces_container": owner},
            "role_lanes": lanes, "context_nodes": [node["id"] for node in context],
            "region_slots": [], "component_lanes": [], "repeat_families": [],
            "source_ownership": {nid: source[nid].get("group", "") for nid in ids},
            "scope_owner_nodes": [node["id"] for node in full_owned],
            "node_to_macro": {nid: nid for nid in ids}, "local_storage_backbone": backbone["id"] if backbone else None,
            "routing_corridors": [{"id": cid, "box": _normal(bounds, width, height),
                                   "track_count": counts[cid], "routing_is_not_a_hardware_bus": True}
                                  for cid, bounds in corridor_specs.items() if counts[cid]],
            "canvas": {"coordinate_system": "normalized", "natural_aspect": round(width / height, 3)},
            "coverage": {"source_nodes": len(ids), "source_edges": len(indices), "nodes_projected": len(ids),
                         "missing_nodes": [], "missing_edges": [], "duplicate_edge_indices": []},
            "source_nested_groups": [g for g in groups if g != owner and owner in set(_path(g, groups))],
            "warnings": ["Role lanes and context placement are visual only. The owner boundary follows source ancestry; context retains its actual source group.",
                         "Nested source owners remain in metadata; omitted child outlines never move nodes into another subsystem."]}
