"""CPS6 bounded composition candidates in a physical typography contract.

This plans a display projection.  It never changes source ownership, creates a
bus, expands an unspecified instance, or optimizes completeness into a figure.
"""
from collections import defaultdict
import copy
import math

from . import publication_render
from . import structure_scene


WIDTH = 1800


def _box(x, y, width, height):
    return {"x": x, "y": y, "width": width, "height": height}


def _normal(box, height):
    return {key: round(value / (WIDTH if key in {"x", "width"} else height), 6)
            for key, value in box.items()}


def _rect(box):
    return box["x"], box["y"], box["x"] + box["width"], box["y"] + box["height"]


def _union(boxes, padding=24):
    left = min(b["x"] for b in boxes) - padding
    top = min(b["y"] for b in boxes) - padding
    right = max(b["x"] + b["width"] for b in boxes) + padding
    bottom = max(b["y"] + b["height"] for b in boxes) + padding
    return _box(left, top, right - left, bottom - top)


def _overlap(a, b):
    return a["x"] < b["x"] + b["width"] and b["x"] < a["x"] + a["width"] and a["y"] < b["y"] + b["height"] and b["y"] < a["y"] + a["height"]


def _source_projection(spec, figure):
    """Accept editorial macros or construct an exact control annex projection."""
    if figure.get("macro_nodes") is not None:
        nodes, edges = copy.deepcopy(figure["macro_nodes"]), copy.deepcopy(figure.get("macro_edges", []))
    else:
        source = {n["id"]: n for n in spec["nodes"]}
        nodes = [{"id": nid, "label": source[nid]["label"], "kind": source[nid]["kind"],
                  "members": [nid], "original_group": source[nid].get("group", ""), "children": []}
                 for nid in figure.get("node_ids", [])]
        edges = [{**copy.deepcopy(spec["edges"][index]), "members": [index], "id": "e" + str(index)}
                 for index in figure.get("edge_indices", [])]
    ids = {n["id"] for n in nodes}
    if len(ids) != len(nodes):
        raise ValueError("Duplicate display node IDs")
    source_nodes = {n["id"]: n for n in spec["nodes"]}
    source_groups = {g["id"]: g for g in spec.get("groups", [])}
    required = [*spec.get("verbatim_labels", []), *figure.get("required_verbatim_labels", [])]
    for node in nodes:
        if not node.get("members") or any(nid not in source_nodes for nid in node["members"]):
            raise ValueError("Display nodes require real source members")
        if len(node["members"]) == 1 and node["id"] in source_nodes:
            original = source_nodes[node["id"]]
            if node.get("original_group", "") != original.get("group", ""):
                raise ValueError("Projected source owner differs from source")
            if node["label"] != original["label"] or node["kind"] != original["kind"]:
                raise ValueError("Projected resource label/type differs from source")
            detail = publication_render.required_detail(original, spec, required)
            if detail:
                node["required_detail"] = detail
            else:
                node.pop("required_detail", None)
        elif node.get("source_group"):
            group = source_groups.get(node["source_group"])
            if group is None or node.get("original_group", "") != group.get("parent", ""):
                raise ValueError("Collapsed group parent differs from source owner")
            for member in node["members"]:
                owner = source_nodes[member].get("group", "")
                ancestors = set()
                while owner and owner not in ancestors:
                    ancestors.add(owner)
                    owner = source_groups.get(owner, {}).get("parent", "")
                if node["source_group"] not in ancestors:
                    raise ValueError("Collapsed group contains a resource outside its source owner")
        for child in node.get("children", []):
            if child["id"] not in node["members"] or child["id"] not in source_nodes:
                raise ValueError("A displayed child must belong to this real source projection")
            original = source_nodes[child["id"]]
            if any(child[key] != original[key] for key in ["label", "kind"]):
                raise ValueError("Displayed child text/type differs from source")
            detail = publication_render.required_detail(original, spec, required)
            if detail:
                child["required_detail"] = detail
            else:
                child.pop("required_detail", None)
    for edge in edges:
        if edge["source"] not in ids or edge["target"] not in ids:
            raise ValueError("Display relationship endpoints are missing")
        if not edge.get("members") or any(not isinstance(index, int) or index < 0 or index >= len(spec["edges"]) for index in edge["members"]):
            raise ValueError("Display relationships require valid source edge indices")
        for index in edge["members"]:
            original = spec["edges"][index]
            forward = original["source"] in next(n["members"] for n in nodes if n["id"] == edge["source"]) and original["target"] in next(n["members"] for n in nodes if n["id"] == edge["target"])
            reverse = original["source"] in next(n["members"] for n in nodes if n["id"] == edge["target"]) and original["target"] in next(n["members"] for n in nodes if n["id"] == edge["source"])
            if not forward and not (edge.get("bidirectional") and reverse):
                raise ValueError("Projected direction does not match its source evidence")
            if edge["kind"] != original["kind"]:
                raise ValueError("Projected relationship kind differs from source")
            text = original.get("label", "")
            important = publication_render.mandatory_text(text) or any(literal and literal in text for literal in required)
            if important and text not in edge.get("label", ""):
                raise ValueError("Projected relationship omits or changes a mandatory source condition or literal")
            if len(edge["members"]) == 1 and edge.get("label", "") != text:
                raise ValueError("Exact relationship label differs from its source evidence")
    mapped = [index for edge in edges for index in edge["members"]]
    if len(mapped) != len(set(mapped)):
        raise ValueError("Duplicate source edge evidence in display projection")
    declared = figure.get("source_edge_indices", figure.get("edge_indices", []))
    internal = figure.get("projection", {}).get("internal_edges", [])
    for index in internal:
        if not isinstance(index, int) or not 0 <= index < len(spec["edges"]):
            raise ValueError("Invalid internal source relationship index")
        original = spec["edges"][index]
        if not any(original["source"] in node["members"] and original["target"] in node["members"] for node in nodes):
            raise ValueError("An internal source relationship crosses display owners")
    if set(mapped) & set(internal):
        raise ValueError("Internal relationship is also claimed as a display arrow")
    if set(mapped) != set(declared) and set(mapped) | set(internal) != set(declared):
        raise ValueError("Display edge evidence does not match the declared source scope")
    for node in nodes:
        if len(node.get("children", [])) >= 2:
            node["entry_sources"] = publication_render.entry_sources(node["id"], edges)
            if node.get("logical_group"):
                node["boundary_port_count"] = sum(node["id"] in {e["source"], e["target"]} for e in edges)
    return nodes, edges


def _owner_scope_entries(raw, nodes, typography):
    """Every inventory boundary endpoint enters the same white scope strip."""
    objects = {n["id"]: n for n in nodes}
    boxes, metrics = raw["boxes"], raw["metrics"]
    endpoints = defaultdict(list)
    for index, edge in enumerate(raw["edges"]):
        for which, other in [("source", "target"), ("target", "source")]:
            nid, other_id = edge[which], edge[other]
            node = objects[nid]
            if not node.get("logical_group") or not node.get("children"):
                continue
            b, o = boxes[nid], boxes[other_id]
            routing = edge.setdefault("routing", {})
            side = routing.get(which + "_side")
            if side not in {"left", "right"}:
                center = b["x"] + b["width"] / 2
                other_center = o["x"] + o["width"] / 2
                side = "right" if other_center > center + 10 else "left" if other_center < center - 10 else "right" if center < WIDTH / 2 else "left"
            routing[which + "_side"] = side
            endpoints[(nid, side)].append((index, which, o["y"], {"data": 0, "relation": 1}.get(edge["kind"], 2)))
    for (nid, side), entries in endpoints.items():
        m, b = metrics[nid], boxes[nid]
        # Incoming interactions end above outgoing interactions on one side.
        # Otherwise a vertical input trunk can meet an output's short stub.
        # Matching side entries have the same geometric order at both
        # endpoints. Sorting input ahead of output reverses a reciprocal
        # pair and forces an avoidable crossover or whole-page return.
        if raw["orientation"] == "existing-owned-join":
            entries.sort(key=lambda item: (raw["edges"][item[0]].get("routing", {}).get(item[1] + "_entry_order", item[2]),
                                          item[3], item[0]))
        else:
            entries.sort(key=lambda item: (item[1] == "source",
                                          raw["edges"][item[0]].get("routing", {}).get(item[1] + "_entry_order", item[2]),
                                          item[3], item[0]))
        midpoint = m["header_height"] + m["entry_gutter_height"] / 2
        spacing = math.ceil(typography["body_px"] * 1.5)
        for order, (index, which, _, _) in enumerate(entries):
            y = midpoint + (order - (len(entries) - 1) / 2) * spacing
            if not m["header_height"] + typography["body_px"] / 2 <= y <= m["header_height"] + m["entry_gutter_height"] - typography["body_px"] / 2:
                return "An owner scope strip cannot separate all incident relationship entries"
            raw["edges"][index]["routing"][which + "_fraction"] = y / b["height"]
    if raw["orientation"] == "existing-data-hub-with-owned-subsystems":
        # Align the actual hub with the projected scope strip on each neighbor.
        data_neighbors = defaultdict(set)
        for edge in raw["edges"]:
            if edge["kind"] == "data":
                data_neighbors[edge["source"]].add(edge["target"])
                data_neighbors[edge["target"]].add(edge["source"])
        hubs = {nid for nid in objects if not objects[nid].get("children") and len(data_neighbors[nid]) >= 3}
        for edge in raw["edges"]:
            for which, other in [("source", "target"), ("target", "source")]:
                nid, other_id = edge[which], edge[other]
                if nid not in hubs or not objects[other_id].get("logical_group"):
                    continue
                b, o = boxes[nid], boxes[other_id]
                r = edge["routing"]
                y = o["y"] + o["height"] * r[other + "_fraction"]
                r[which + "_fraction"] = (y - b["y"]) / b["height"]
    # Jointly choose facing lateral entries inside each measured white scope
    # strip. A straight connector is feasible only if the strips overlap and
    # every other independent entry keeps its required spacing.
    for index, edge in enumerate(raw["edges"]):
        if raw["orientation"] == "existing-data-hub-with-owned-subsystems":
            continue
        r = edge.get("routing", {})
        ss, ts = r.get("source_side"), r.get("target_side")
        if (ss, ts) not in {("right", "left"), ("left", "right")} or r.get("outer_route") or r.get("organization_track"):
            continue
        intervals, levels = [], []
        for which in ("source", "target"):
            nid = edge[which]; b = boxes[nid]; m = metrics[nid]
            if objects[nid].get("logical_group") and objects[nid].get("children"):
                intervals.append((b["y"] + m["header_height"] + typography["body_px"] / 2,
                                  b["y"] + m["header_height"] + m["entry_gutter_height"] - typography["body_px"] / 2))
            else:
                intervals.append((b["y"] + 18, b["y"] + b["height"] - 18))
            levels.append(b["y"] + b["height"] * r.get(which + "_fraction", .5))
        low, high = max(i[0] for i in intervals), min(i[1] for i in intervals)
        if low > high:
            continue
        choices = [min(high, max(low, sum(levels) / 2)), *levels, low, high]
        for y in choices:
            if not low <= y <= high:
                continue
            conflict = False
            for which, side in [("source", ss), ("target", ts)]:
                nid = edge[which]
                for other_index, other_which, _, _ in endpoints[(nid, side)]:
                    if other_index == index and other_which == which:
                        continue
                    other_r = raw["edges"][other_index]["routing"]
                    other_y = boxes[nid]["y"] + boxes[nid]["height"] * other_r[other_which + "_fraction"]
                    if abs(y - other_y) < typography["body_px"] * 1.2:
                        conflict = True
            if not conflict:
                for which in ("source", "target"):
                    b = boxes[edge[which]]; r[which + "_fraction"] = (y - b["y"]) / b["height"]
                break
    return None


def _organization_ranks(nodes, edges):
    """Preserve data order; add command flow without converting IRQ to data."""
    forward = defaultdict(set)
    returning = set()
    def reaches(start, goal):
        pending, seen = [start], set()
        while pending:
            current = pending.pop()
            if current == goal:
                return True
            if current not in seen:
                seen.add(current); pending.extend(forward[current])
        return False
    for index in sorted(range(len(edges)), key=lambda i: ({"data": 0, "relation": 1, "control": 2}.get(edges[i]["kind"], 3), i)):
        edge = edges[index]
        if edge["kind"] in {"clock", "feedback"} or reaches(edge["target"], edge["source"]):
            returning.add(index)
        else:
            forward[edge["source"]].add(edge["target"])
    indegree = {node["id"]: 0 for node in nodes}
    ranks = {node["id"]: 0 for node in nodes}
    for targets in forward.values():
        for target in targets:
            indegree[target] += 1
    pending = [node["id"] for node in nodes if not indegree[node["id"]]]
    while pending:
        current = pending.pop(0)
        for target in forward[current]:
            ranks[target] = max(ranks[target], ranks[current] + 1)
            indegree[target] -= 1
            if not indegree[target]:
                pending.append(target)
    return ranks, returning


def _ownership_candidate(nodes, edges, typography, orientation, columns):
    """True subsystem inventories, including a single supplied xN owner."""
    maximum = 420 if columns == 1 else 720
    metrics = {node["id"]: publication_render.measure_node(node, typography["body_px"],
                   maximum=maximum if node.get("children") else 380, symbol_profile=typography.get("symbol_profile", "plain"),
                   inventory_columns=columns, compact_inventory=True) for node in nodes}
    if any(value is None for value in metrics.values()):
        return None, "A source subsystem inventory does not fit fixed publication type"
    ranks, returns = _organization_ranks(nodes, edges)
    roots_above = {}
    if orientation == "left-to-right":
        # A scalar entry endpoint can sit above its actual first subsystem.
        # This compacts four-column inventory chains without creating a node.
        incoming = defaultdict(set); outgoing = defaultdict(set)
        for index, edge in enumerate(edges):
            if index not in returns:
                outgoing[edge["source"]].add(edge["target"])
                incoming[edge["target"]].add(edge["source"])
        for node in nodes:
            nid = node["id"]
            if not node.get("children") and not incoming[nid] and len(outgoing[nid]) == 1:
                target = next(iter(outgoing[nid]))
                if len(incoming[target]) == 1:
                    roots_above[nid] = target
    layers = defaultdict(list)
    for node in nodes:
        if node["id"] in roots_above:
            continue
        layers[ranks[node["id"]]].append(node["id"])
    boxes = {}
    gap = 130
    if orientation == "top-to-bottom":
        y = 100
        for rank in sorted(layers):
            layer = layers[rank]
            total = sum(metrics[nid]["width"] for nid in layer) + max(0, len(layer) - 1) * 90
            if total > WIDTH - 160:
                return None, "Parallel subsystem inventories exceed the fixed-font document width"
            x = (WIDTH - total) / 2
            for nid in layer:
                item = metrics[nid]
                boxes[nid] = _box(x, y, item["width"], item["height"])
                x += item["width"] + 90
            y += max(metrics[nid]["height"] for nid in layer) + gap
        height = math.ceil(y + 100 + len(returns) * 70)
    else:
        widths = {rank: max(metrics[nid]["width"] for nid in layer) for rank, layer in layers.items()}
        gaps = {rank: gap for rank in layers}
        face = publication_render.font(typography["signal_px"])
        for index, edge in enumerate(edges):
            if index not in returns and edge["source"] not in roots_above and publication_render.mandatory_text(edge.get("label", "")):
                gaps[ranks[edge["source"]]] = max(gap, min(480, math.ceil(face.getlength(edge["label"]) + 64)))
        ordered_ranks = sorted(layers)
        total = sum(widths.values()) + sum(gaps[rank] for rank in ordered_ranks[:-1]) + 140
        if total > WIDTH:
            return None, "Horizontal subsystem inventories exceed the fixed-font document width"
        x = (WIDTH - total + 140) / 2
        plot_height = max(sum(metrics[nid]["height"] for nid in layer) + max(0, len(layer) - 1) * 100 for layer in layers.values())
        entry_height = max((metrics[nid]["height"] + 130 for nid in roots_above), default=0)
        for rank in sorted(layers):
            y = 100 + entry_height
            for nid in layers[rank]:
                item = metrics[nid]
                boxes[nid] = _box(x + (widths[rank] - item["width"]) / 2, y, item["width"], item["height"])
                y += item["height"] + 100
            x += widths[rank] + gaps[rank]
        for nid, target in roots_above.items():
            target_box = boxes[target]
            item = metrics[nid]
            boxes[nid] = _box(target_box["x"] + (target_box["width"] - item["width"]) / 2, 100, item["width"], item["height"])
        height = math.ceil(plot_height + entry_height + 260 + len(returns) * 80)
    routed = copy.deepcopy(edges)
    for index, edge in enumerate(routed):
        edge.pop("routing", None)
        if index in returns:
            edge["family"] = "return"
            side = "left" if boxes[edge["source"]]["x"] + boxes[edge["source"]]["width"] / 2 < WIDTH / 2 else "right"
            edge["routing"] = {"source_side": side, "target_side": side} if orientation == "top-to-bottom" else {
                "source_side": "bottom", "target_side": "bottom", "outer_route": True,
                "waypoint_axis": "y", "waypoint_value": (height - 60 - list(sorted(returns)).index(index) * 60) / height}
        else:
            edge["family"] = "forward"
            edge["routing"] = {"source_side": "bottom" if orientation == "top-to-bottom" else "right",
                               "target_side": "top" if orientation == "top-to-bottom" else "left"}
            if edge["source"] in roots_above:
                # The scalar entry is above its true first owner.  Enter the
                # owner's left scope strip so an outgoing right-side command
                # cannot be mistaken for a continuation of the input trunk.
                edge["routing"] = {"source_side": "bottom", "target_side": "left"}
    return {"boxes": boxes, "height": height, "metrics": metrics, "edges": routed,
            "orientation": orientation, "ranks": ranks, "insets": []}, None


def _ownership_hub_candidate(nodes, edges, typography, columns):
    """An existing high-degree data resource organizes subsystem columns."""
    objects = {node["id"]: node for node in nodes}
    neighbors = defaultdict(set)
    for edge in edges:
        if edge["kind"] == "data":
            neighbors[edge["source"]].add(edge["target"])
            neighbors[edge["target"]].add(edge["source"])
    hubs = [node for node in nodes if not node.get("children") and len(neighbors[node["id"]]) >= 3]
    if len(hubs) != 1:
        return None, "No single existing data hub establishes this organization"
    hub = hubs[0]["id"]
    producers = {e["source"] for e in edges if e["target"] == hub and e["kind"] == "data"}
    consumers = {e["target"] for e in edges if e["source"] == hub and e["kind"] == "data"}
    if not producers or not consumers or producers & consumers:
        return None, "Hub endpoints do not form distinct existing producer/service scopes"
    left = [node["id"] for node in nodes if node["id"] in producers]
    right = [node["id"] for node in nodes if node["id"] in consumers]
    other = [node["id"] for node in nodes if node["id"] not in {hub, *left, *right}]
    for nid in other:
        targets = {e["target"] for e in edges if e["source"] == nid}
        sources = {e["source"] for e in edges if e["target"] == nid}
        if targets and targets <= set(left) and not sources:
            left.insert(0, nid)
        elif sources and sources <= set(right) and not targets:
            right.append(nid)
        else:
            return None, "A residual subsystem needs a separate source-derived context view"
    maximum = 420 if columns == 1 else 650
    # The hub grammar establishes lateral owner entries before measurement.
    # Each side has its own white strip capacity; unrelated opposite-side
    # endpoints do not require a taller common band.
    display_nodes = copy.deepcopy(nodes)
    side_counts = defaultdict(lambda: defaultdict(int))
    for edge in edges:
        source, target = edge["source"], edge["target"]
        if target == hub:
            sides = ("right" if source in left else "left", None)
        elif source == hub:
            sides = (None, "left" if target in right else "right")
        elif source in right and target in left:
            sides = ("left", "left")
        elif source in right and target in right and right.index(target) > right.index(source) + 1:
            sides = ("right", "right")
        else:
            sides = ("right" if source in left else "left", "right" if target in left else "left")
        for nid, side in zip((source, target), sides):
            if side:
                side_counts[nid][side] += 1
    for node in display_nodes:
        if node.get("logical_group"):
            node["scope_ports_by_side"] = True
            node["boundary_port_count"] = max(side_counts[node["id"]].values(), default=1)
    metrics = {node["id"]: publication_render.measure_node(node, typography["body_px"], maximum=maximum if node.get("children") else 340,
                symbol_profile=typography.get("symbol_profile", "plain"), inventory_columns=columns, compact_inventory=True) for node in display_nodes}
    if any(value is None for value in metrics.values()):
        return None, "Hub subsystem inventory cannot fit at the declared body font"
    left_width = max(metrics[nid]["width"] for nid in left)
    right_width = max(metrics[nid]["width"] for nid in right)
    hub_width = metrics[hub]["width"]
    gap = 60
    total = left_width + right_width + hub_width + 2 * gap
    if total > WIDTH - 100:
        return None, "Hub and subsystem columns exceed the fixed-font document width"
    origin = (WIDTH - total) / 2
    boxes = {}
    for ids, x, width in [(left, origin, left_width), (right, origin + left_width + 2 * gap + hub_width, right_width)]:
        y = 100
        for nid in ids:
            item = metrics[nid]
            boxes[nid] = _box(x + (width - item["width"]) / 2, y, item["width"], item["height"])
            y += item["height"] + 90
    adjacent = [boxes[nid] for nid in producers | consumers]
    top = min(b["y"] for b in adjacent)
    bottom = max(b["y"] + b["height"] for b in adjacent)
    boxes[hub] = _box(origin + left_width + gap, top, hub_width, max(bottom - top, metrics[hub]["height"]))
    height = math.ceil(max(b["y"] + b["height"] for b in boxes.values()) + 190)
    routed = copy.deepcopy(edges)
    def level(nid, fraction):
        return boxes[nid]["y"] + boxes[nid]["height"] * fraction
    def hub_fraction(y):
        return (y - boxes[hub]["y"]) / boxes[hub]["height"]
    for edge in routed:
        edge.pop("routing", None)
        source, target = edge["source"], edge["target"]
        edge["family"] = "forward"
        if target == hub:
            fraction = .65 if edge["kind"] in {"feedback", "control"} else .35
            y = level(source, fraction)
            side = "right" if source in left else "left"
            edge["routing"] = {"source_side": side, "target_side": "left" if source in left else "right",
                               "source_fraction": fraction, "target_fraction": hub_fraction(y)}
        elif source == hub:
            fraction = .35
            y = level(target, fraction)
            side = "left" if target in right else "right"
            edge["routing"] = {"source_side": "right" if target in right else "left", "target_side": side,
                               "source_fraction": hub_fraction(y), "target_fraction": fraction}
        elif source in right and target in left:
            edge["family"] = "return"
            # A secondary interaction exits below the service's incoming data
            # entry, then uses the gap beside the real hub and an outer return.
            edge["routing"] = {"source_side": "left", "source_fraction": .65, "target_side": "left", "outer_route": True,
                               "waypoint_axis": "y", "waypoint_value": (height - 65) / height}
        elif source in right and target in right and right.index(target) > right.index(source) + 1:
            # A side chain that skips a service cannot descend through its
            # hub link. Reserve a separate outside track; this is geometry,
            # never an inferred shared bus or a changed source endpoint.
            edge["routing"] = {"source_side": "right", "source_fraction": .35,
                               "target_side": "right", "target_fraction": .25,
                               "organization_track": "outside-service-column"}
        else:
            edge["routing"] = {"source_side": "bottom", "target_side": "top"}
    return {"boxes": boxes, "height": height, "metrics": metrics, "edges": routed,
            "orientation": "existing-data-hub-with-owned-subsystems", "ranks": {}, "insets": [], "display_nodes": display_nodes}, None


def _owned_join_candidate(nodes, edges, typography, columns):
    """A real owning subsystem can join independent producer scopes."""
    objects = {node["id"]: node for node in nodes}
    incoming, outgoing = defaultdict(set), defaultdict(set)
    for edge in edges:
        if edge["kind"] == "data":
            incoming[edge["target"]].add(edge["source"])
            outgoing[edge["source"]].add(edge["target"])
    joins = [node for node in nodes if node.get("logical_group") and node.get("children")
             and len(incoming[node["id"]]) >= 2 and outgoing[node["id"]]]
    if len(joins) != 1:
        return None, "No single source-owned join establishes this hierarchy"
    join = joins[0]["id"]
    left = [node["id"] for node in nodes if node["id"] in incoming[join]]
    right = [node["id"] for node in nodes if node["id"] in outgoing[join]]
    if set(left) & set(right) or {node["id"] for node in nodes} != {join, *left, *right}:
        return None, "The owning join does not cover the supplied context scopes"
    display_nodes = copy.deepcopy(nodes)
    port_counts = defaultdict(lambda: defaultdict(int))
    for edge in edges:
        source, target = edge["source"], edge["target"]
        if target == join and source in left:
            sides = ("right", "left")
        elif source == join and target in right:
            sides = ("right", "left")
        elif source in right and target == join and edge["kind"] in {"control", "feedback", "clock"}:
            sides = ("left", "right")
        else:
            return None, "A relation outside the source-owned join needs another hierarchy view"
        for nid, side in zip((source, target), sides):
            port_counts[nid][side] += 1
    for node in display_nodes:
        if node.get("logical_group"):
            node["scope_ports_by_side"] = True
            node["boundary_port_count"] = max(port_counts[node["id"]].values(), default=1)
    maximum = 430 if columns == 1 else 650
    metrics = {node["id"]: publication_render.measure_node(node, typography["body_px"], maximum=maximum,
                symbol_profile=typography.get("symbol_profile", "plain"), inventory_columns=columns,
                compact_inventory=True) for node in display_nodes}
    if any(item is None for item in metrics.values()):
        return None, "A supplied join inventory cannot fit at the declared font"
    # Source declaration permutation must not flip equivalent producer
    # columns. Their actual inventory labels provide a deterministic tie
    # breaker after geometry; no new role or technical equivalence is inferred.
    left.sort(key=lambda nid: (-metrics[nid]["height"], -metrics[nid]["width"],
                              tuple(sorted(child["label"] for child in objects[nid].get("children", [])))))
    widths = [max(metrics[nid]["width"] for nid in left), metrics[join]["width"],
              max(metrics[nid]["width"] for nid in right)]
    gap = 150
    total = sum(widths) + 2 * gap
    if total > WIDTH - 130:
        return None, "Source join inventories require another arrangement at fixed font"
    origin = (WIDTH - total) / 2
    boxes = {}
    for ids, x, width in [(left, origin, widths[0]), (right, origin + widths[0] + widths[1] + 2 * gap, widths[2])]:
        y = 100
        for nid in ids:
            measured = metrics[nid]
            boxes[nid] = _box(x + (width - measured["width"]) / 2, y, measured["width"], measured["height"])
            y += measured["height"] + 100
    boxes[join] = _box(origin + widths[0] + gap, 100, widths[1], metrics[join]["height"])
    height = math.ceil(max(box["y"] + box["height"] for box in boxes.values()) + 130)
    routed = copy.deepcopy(edges)
    for edge in routed:
        edge.pop("routing", None)
        edge["routing"] = {"source_side": "right", "target_side": "left"}
        if edge["source"] in right and edge["target"] == join:
            edge["routing"] = {"source_side": "left", "target_side": "right"}
    return {"boxes": boxes, "height": height, "metrics": metrics, "edges": routed,
            "orientation": "existing-owned-join", "ranks": {}, "insets": [], "display_nodes": display_nodes}, None


def _acyclic_ranks(nodes, edges):
    """Identify true directed cycle returns, preserving their original edges."""
    adjacency = defaultdict(list)
    incoming = defaultdict(list)
    for index, edge in enumerate(edges):
        if edge["kind"] in {"data", "relation"}:
            adjacency[edge["source"]].append((edge["target"], index))
            incoming[edge["target"]].append(edge["source"])
    color, returning, order = {}, set(), []
    def visit(nid):
        color[nid] = 1
        for target, index in adjacency[nid]:
            if color.get(target) == 1:
                returning.add(index)
            elif not color.get(target):
                visit(target)
        color[nid] = 2
        order.append(nid)
    # Real root/external producers first, then preserve source order.
    start = sorted(nodes, key=lambda n: (bool(incoming[n["id"]]), bool(n.get("original_group"))))
    for node in start:
        if not color.get(node["id"]):
            visit(node["id"])
    ranks = {n["id"]: 0 for n in nodes}
    for nid in reversed(order):
        for target, index in adjacency[nid]:
            if index not in returning:
                ranks[target] = max(ranks[target], ranks[nid] + 1)
    return ranks, returning


def _flow_candidate(nodes, edges, typography, orientation, gap, leaf_maximum=400):
    metrics = {node["id"]: publication_render.measure_node(node, typography["body_px"], maximum=680 if node.get("children") else leaf_maximum,
                                                          symbol_profile=typography.get("symbol_profile", "plain"))
               for node in nodes}
    if any(value is None for value in metrics.values()):
        return None, "A module name cannot fit two lines at the physical body font"
    ranks, returns = _acyclic_ranks(nodes, edges)
    if orientation == "left-to-right":
        face = publication_render.font(typography["signal_px"])
        # Include both 18px port stubs, a text perimeter and grid snapping.
        needed = max((face.getlength(edge.get("label", "")) + 72 for index, edge in enumerate(edges)
                      if index not in returns and publication_render.mandatory_text(edge.get("label", ""))), default=gap)
        # This is bounded geometry, never a reason to shrink type.  Longer
        # predicates can use the vertical candidate's adjacent text region.
        gap = max(gap, min(480, math.ceil(needed)))
    layers = defaultdict(list)
    for node in nodes:
        layers[ranks[node["id"]]].append(node["id"])
    # Stable paired lanes; merging/splitting uses the same vertical stage rank.
    boxes = {}
    if orientation == "top-to-bottom":
        y = 100
        for rank in sorted(layers):
            layer = layers[rank]
            total_width = sum(metrics[nid]["width"] for nid in layer) + (len(layer) - 1) * 110
            if total_width > WIDTH - 240:
                return None, "A parallel stage is wider than the print canvas at fixed body type"
            x = (WIDTH - total_width) / 2
            layer_height = max(metrics[nid]["height"] for nid in layer)
            for nid in layer:
                measured = metrics[nid]
                boxes[nid] = _box(x, y + (layer_height - measured["height"]) / 2,
                                  measured["width"], measured["height"])
                x += measured["width"] + 110
            y += layer_height + gap
        height = math.ceil(y + 70 + len(returns) * 40)
    else:
        rank_widths = {rank: max(metrics[nid]["width"] for nid in layer) for rank, layer in layers.items()}
        total_width = sum(rank_widths.values()) + (len(layers) - 1) * gap + 240
        if total_width > WIDTH:
            return None, "The horizontal circuit would require smaller body type than the print contract"
        column_heights = {rank: sum(metrics[nid]["height"] for nid in layer) + (len(layer) - 1) * 90 for rank, layer in layers.items()}
        plot_height = max(column_heights.values())
        x = (WIDTH - (total_width - 240)) / 2
        for rank in sorted(layers):
            layer = layers[rank]
            y = 100 + (plot_height - column_heights[rank]) / 2
            for nid in layer:
                measured = metrics[nid]
                boxes[nid] = _box(x + (rank_widths[rank] - measured["width"]) / 2, y,
                                  measured["width"], measured["height"])
                y += measured["height"] + 90
            x += rank_widths[rank] + gap
        height = math.ceil(100 + plot_height + 160 + len(returns) * 64)
    routed = copy.deepcopy(edges)
    for index, edge in enumerate(routed):
        edge.pop("routing", None)
        returning = index in returns or edge["kind"] in {"feedback", "clock"}
        edge["family"] = "return" if returning else "forward"
        if returning:
            if orientation == "left-to-right":
                edge["routing"] = {"source_side": "bottom", "target_side": "bottom", "outer_route": True,
                                   "waypoint_axis": "y", "waypoint_value": (height - 65 - list(sorted(returns)).index(index) * 50) / height if index in returns else (height - 65) / height}
            else:
                edge["routing"] = {"source_side": "right", "target_side": "right"}
        else:
            edge["routing"] = {"source_side": "bottom" if orientation == "top-to-bottom" else "right",
                               "target_side": "top" if orientation == "top-to-bottom" else "left"}
    return {"boxes": boxes, "height": height, "metrics": metrics, "edges": routed,
            "orientation": orientation, "ranks": ranks, "insets": []}, None


def _owner_payload_candidate(nodes, edges, typography):
    """Real owner columns with visible payload resources, not inventory cards.

    Parallel supplied compute peers share a row; a common storage resource is
    a single band in its actual owner. Positions never imply new instances,
    wiring, shared buses or an execution schedule.
    """
    metrics = {node["id"]: publication_render.measure_node(
        node, typography["body_px"], maximum=520 if node.get("children") else 360,
        symbol_profile=typography.get("symbol_profile", "plain"), compact_inventory=True) for node in nodes}
    if any(value is None for value in metrics.values()):
        return None, "A payload resource name exceeds fixed-font owner-column capacity"
    # Only the already-selected real commands participate in reading order.
    # Their technical kind stays unchanged in the output and routing.
    ranked = [{**edge, "kind": "relation"} if edge["kind"] == "control" else edge for edge in edges]
    ranks, returns = _acyclic_ranks(nodes, ranked)
    owners = {node["id"]: node.get("source_group") if node.get("children") else node.get("original_group")
              for node in nodes}
    owners = {nid: owner or "@single:" + nid for nid, owner in owners.items()}
    incoming, outgoing = defaultdict(set), defaultdict(set)
    for edge in edges:
        outgoing[edge["source"]].add(edge["target"])
        incoming[edge["target"]].add(edge["source"])
    for node in nodes:
        nid = node["id"]
        if node.get("children") or node["kind"] not in {"io", "control"} or incoming[nid] or len(outgoing[nid]) != 1:
            continue
        if sum(owner == owners[nid] for owner in owners.values()) == 1:
            # A source endpoint can sit above its actual first target without
            # changing either object's original_group or drawing a new owner.
            owners[nid] = owners[next(iter(outgoing[nid]))]
    columns = defaultdict(list)
    for node in nodes:
        columns[owners[node["id"]]].append(node)
    order = sorted(columns, key=lambda owner: (min(ranks[node["id"]] for node in columns[owner]),
                                              min(node["id"] for node in columns[owner])))
    rows, widths = {}, {}
    for owner in order:
        grouped = defaultdict(list)
        for node in columns[owner]:
            display_rank = ranks[node["id"]]
            if node["kind"] == "memory":
                compute_peers = {edge["target"] if edge["source"] == node["id"] else edge["source"]
                                 for edge in edges if edge.get("bidirectional") and node["id"] in {edge["source"], edge["target"]}}
                compute_peers &= {peer["id"] for peer in columns[owner] if peer["kind"] == "compute"}
                if len(compute_peers) >= 2:
                    # This source-backed shared store is a common band under
                    # its peer consumers, never a pipeline stage or new bus.
                    display_rank = max(ranks[peer] for peer in compute_peers) + .5
            grouped[display_rank].append(node)
        rows[owner] = [grouped[rank] for rank in sorted(grouped)]
        widths[owner] = max(sum(metrics[node["id"]]["width"] for node in row) + (len(row) - 1) * 40 for row in rows[owner])
    gap = 140
    gaps = {owner: gap for owner in order}
    face = publication_render.font(typography["signal_px"])
    for edge in edges:
        a, b = owners[edge["source"]], owners[edge["target"]]
        if a != b and publication_render.mandatory_text(edge.get("label", "")):
            left = a if order.index(a) < order.index(b) else b
            gaps[left] = max(gaps[left], math.ceil(face.getlength(edge["label"]) + 96))
    total = sum(widths.values()) + sum(gaps[owner] for owner in order[:-1])
    if total > WIDTH - 80:
        return None, "Real owner columns exceed the fixed-font document width"
    boxes, owner_right = {}, {}
    x = (WIDTH - total) / 2
    for owner in order:
        y = 110
        for row in rows[owner]:
            height = max(metrics[node["id"]]["height"] for node in row)
            width = sum(metrics[node["id"]]["width"] for node in row) + (len(row) - 1) * 40
            xx = x + (widths[owner] - width) / 2
            for node in row:
                item = metrics[node["id"]]
                # Single shared/service resources occupy their owner's clear
                # band. This also keeps a cross-owner input from wandering
                # deep into a narrower child before it reaches its endpoint.
                band = len(row) == 1 and not node.get("children")
                boxes[node["id"]] = _box(x if band else xx, y + (height - item["height"]) / 2,
                                          widths[owner] if band else item["width"], item["height"])
                xx += item["width"] + 40
            y += height + 120
        owner_right[owner] = x + widths[owner]
        x += widths[owner] + gaps[owner]
    for owner in order:
        if len(columns[owner]) != 1:
            continue
        node = columns[owner][0]
        nid = node["id"]
        peers = incoming[nid] | outgoing[nid]
        if node.get("children") or len(peers) != 1:
            continue
        peer = boxes[next(iter(peers))]
        boxes[nid]["y"] = peer["y"] + (peer["height"] - boxes[nid]["height"]) / 2
    height = math.ceil(max(box["y"] + box["height"] for box in boxes.values()) + 150)
    routed = copy.deepcopy(edges)
    return_lanes = {}
    for index, edge in enumerate(routed):
        edge.pop("routing", None)
        a, b = edge["source"], edge["target"]
        same = owners[a] == owners[b]
        if same and boxes[b]["y"] > boxes[a]["y"]:
            routing = {"source_side": "bottom", "target_side": "top"}
        elif same:
            routing = {"source_side": "right", "target_side": "right"}
            return_lanes[edge["id"]] = (owner_right[owners[a]] + gaps[owners[a]] / 2) / WIDTH
        else:
            forward = boxes[a]["x"] < boxes[b]["x"]
            routing = {"source_side": "right" if forward else "left", "target_side": "left" if forward else "right"}
        edge.update(family="return" if index in returns else "forward", routing=routing)
    return {"boxes": boxes, "height": height, "metrics": metrics, "edges": routed,
            "orientation": "source-owner-payload-columns", "ranks": ranks, "insets": [],
            "owner_return_lanes": return_lanes}, None


def _folded_candidate(nodes, edges, typography, gap):
    """A source-derived converging pipeline followed by a short return row.

    Reading direction is deliberately explicit.  Folding stages changes page
    composition, not dependency order or the number of hardware instances.
    """
    ranks, returns = _acyclic_ranks(nodes, edges)
    incoming = defaultdict(set)
    outgoing = defaultdict(set)
    for index, edge in enumerate(edges):
        if index not in returns and edge["kind"] in {"data", "relation"}:
            incoming[edge["target"]].add(edge["source"])
            outgoing[edge["source"]].add(edge["target"])
    joins = [n["id"] for n in nodes if len(incoming[n["id"]]) >= 2]
    if len(joins) != 1:
        return None, "A folded input pipeline needs one actual converging compute group"
    join = joins[0]
    tail, current = [], join
    while outgoing[current]:
        if len(outgoing[current]) != 1:
            return None, "Multiple post-compute paths need a separate reading projection"
        current = next(iter(outgoing[current]))
        if len(incoming[current]) != 1 or current in tail:
            return None, "The post-compute output is not a simple source-derived chain"
        tail.append(current)
        if len(tail) > 3:
            return None, "This source output chain needs a longer dedicated view"
    if not tail:
        return None, "A folded return row needs a real output chain"
    before = [n for n in nodes if n["id"] not in tail]
    metrics = {node["id"]: publication_render.measure_node(node, typography["body_px"],
                maximum=400 if node.get("children") else 280 if ranks[node["id"]] == 0 else 320,
                symbol_profile=typography.get("symbol_profile", "plain"))
               for node in nodes}
    if any(value is None for value in metrics.values()):
        return None, "A folded stage cannot fit two lines at the fixed physical body font"
    layers = defaultdict(list)
    for node in before:
        layers[ranks[node["id"]]].append(node["id"])
    widths = {rank: max(metrics[nid]["width"] for nid in layer) for rank, layer in layers.items()}
    total_width = sum(widths.values()) + max(0, len(layers) - 1) * gap + 160
    if total_width > WIDTH:
        return None, "The folded input section would exceed the fixed-font print canvas"
    heights = {rank: sum(metrics[nid]["height"] for nid in layer) + (len(layer) - 1) * 100 for rank, layer in layers.items()}
    plot_height = max(heights.values())
    boxes, columns = {}, {}
    x = (WIDTH - total_width + 160) / 2
    for rank in sorted(layers):
        columns[rank] = x + widths[rank] / 2
        for lane, nid in enumerate(layers[rank]):
            measured = metrics[nid]
            y = 100 + plot_height * (lane + .5) / len(layers[rank]) - measured["height"] / 2
            boxes[nid] = _box(x + (widths[rank] - measured["width"]) / 2, y,
                              measured["width"], measured["height"])
        x += widths[rank] + gap
    lower_y = 100 + plot_height + 140
    lower_height = max(metrics[nid]["height"] for nid in tail)
    # Output reads from right to left under the same real transfer pipeline.
    for index, nid in enumerate(tail):
        center = columns[max(layers) - index]
        measured = metrics[nid]
        boxes[nid] = _box(center - measured["width"] / 2, lower_y + (lower_height - measured["height"]) / 2,
                          measured["width"], measured["height"])
    height = math.ceil(lower_y + lower_height + 170)
    routed = copy.deepcopy(edges)
    for index, edge in enumerate(routed):
        edge.pop("routing", None)
        edge["family"] = "return" if index in returns else "forward"
        if index in returns:
            edge["routing"] = {"source_side": "bottom", "target_side": "bottom", "outer_route": True,
                               "waypoint_axis": "y", "waypoint_value": (height - 70 - list(sorted(returns)).index(index) * 45) / height}
        elif edge["source"] == join and edge["target"] == tail[0]:
            edge["routing"] = {"source_side": "bottom", "target_side": "top"}
        elif edge["source"] in tail:
            edge["routing"] = {"source_side": "left", "target_side": "right"}
        else:
            edge["routing"] = {"source_side": "right", "target_side": "left"}
            if edge["target"] == join and edge["source"] in incoming[join]:
                # Inputs enter the folded owner's header, not opposite an
                # individual child symbol that could imply a false endpoint.
                sources = sorted(incoming[join], key=lambda nid: boxes[nid]["y"])
                measured = metrics[join]
                if len(sources) >= 2 and measured.get("entry_gutter_height", 0):
                    first_center = boxes[sources[0]]["y"] + boxes[sources[0]]["height"] / 2 - boxes[join]["y"]
                    first = max(measured["header_height"] + typography["body_px"] * .5, first_center)
                    entry_y = first + sources.index(edge["source"]) * measured["entry_port_spacing_px"]
                    if entry_y > measured["header_height"] + measured["entry_gutter_height"] - typography["body_px"] * .5:
                        return None, "Common inputs need more white entry space at fixed trace separation"
                else:
                    entry_y = 24 + sources.index(edge["source"]) * 22
                edge["routing"]["target_fraction"] = entry_y / boxes[join]["height"]
    return {"boxes": boxes, "height": height, "metrics": metrics, "edges": routed,
            "orientation": "left-to-right-inputs-then-right-to-left-results", "ranks": ranks, "insets": []}, None


def _control_candidate(nodes, edges, typography, gap):
    outgoing = defaultdict(list)
    for edge in edges:
        if edge["kind"] == "control":
            outgoing[edge["source"]].append(edge["target"])
    controllers = [node for node in nodes if node["kind"] == "control" and len(set(outgoing[node["id"]])) >= 2]
    if len(controllers) != 1:
        return None, "A control band needs one real dominant issue controller"
    controller = controllers[0]
    targets = set(outgoing[controller["id"]])
    # True sibling subresources stay adjacent, without flattening their owner.
    peers = sorted([n for n in nodes if n["id"] in targets], key=lambda n: n.get("original_group", ""))
    others = [n for n in nodes if n["id"] != controller["id"] and n["id"] not in targets]
    if len(peers) > 7 or len(others) > 3:
        return None, "The control interaction needs a narrower source scope before layout"
    available = WIDTH - 200 - max(0, len(peers) - 1) * gap
    per_peer = available / max(1, len(peers))
    # Unequal functional labels get measured widths.  Reserving an equal slot
    # before measuring would reject one long word even when the row fits.
    metrics = {n["id"]: publication_render.measure_node(n, typography["body_px"], maximum=320 if n["id"] in targets else 600,
                                                       symbol_profile=typography.get("symbol_profile", "plain")) for n in nodes}
    if any(value is None for value in metrics.values()):
        return None, "A control target cannot fit two lines at fixed body type"
    total = sum(metrics[n["id"]]["width"] for n in peers) + max(0, len(peers) - 1) * gap
    if total > WIDTH - 200:
        return None, "The control targets do not fit the body font in one clear issue row"
    left = (WIDTH - total) / 2
    boxes = {controller["id"]: _box(left, 95, total, metrics[controller["id"]]["height"])}
    control_bottom = boxes[controller["id"]]["y"] + boxes[controller["id"]]["height"]
    y = control_bottom + 160
    max_peer_height = max(metrics[n["id"]]["height"] for n in peers)
    x = left
    for node in peers:
        item = metrics[node["id"]]
        boxes[node["id"]] = _box(x, y, item["width"], max_peer_height)
        x += item["width"] + gap
    lower_y = y + max_peer_height + 180
    total_other = sum(metrics[n["id"]]["width"] for n in others) + max(0, len(others) - 1) * 100
    x = (WIDTH - total_other) / 2
    for node in others:
        item = metrics[node["id"]]
        boxes[node["id"]] = _box(x, lower_y, item["width"], item["height"])
        x += item["width"] + 100
    height = math.ceil(max(b["y"] + b["height"] for b in boxes.values()) + 240)
    routed = copy.deepcopy(edges)
    feedback_index = 0
    feedback_order = sorted([e for e in routed if e["kind"] in {"feedback", "clock"}],
                            key=lambda e: boxes[e["source"]]["x"] + boxes[e["source"]]["width"] / 2)
    feedback_ranks = {tuple(e["members"]): index for index, e in enumerate(feedback_order)}
    for edge in routed:
        edge.pop("routing", None)
        if edge["kind"] == "control" and edge["source"] == controller["id"]:
            target = boxes[edge["target"]]
            center = target["x"] + target["width"] / 2
            edge["family"] = "instruction"
            edge["routing"] = {"source_side": "bottom", "target_side": "top",
                               "source_fraction": (center - left) / total, "target_fraction": .5}
        elif edge["kind"] in {"feedback", "clock"}:
            rank = feedback_ranks[tuple(edge["members"])]
            side = "left" if rank < math.ceil(len(feedback_order) / 2) else "right"
            edge["family"] = "return"
            edge["routing"] = {"source_side": "bottom", "target_side": side,
                               "target_fraction": .35 if side == "left" else .65,
                               "outer_route": True, "waypoint_axis": "y",
                               "waypoint_value": (height - 70 - feedback_index * 70) / height}
            feedback_index += 1
        else:
            edge["family"] = "other"
    return {"boxes": boxes, "height": height, "metrics": metrics, "edges": routed,
            "orientation": "controller-band", "ranks": {}, "insets": []}, None


def _dispatcher_resource_candidate(nodes, edges, figure, typography):
    families = figure.get("repeat_families", [])
    if len(families) != 1:
        return None, "Resource-array grammar needs one source-proven equivalent family"
    family = families[0]
    instances = [family["template_group"], *family["instances"]]
    objects = {n["id"]: n for n in nodes}
    if not all(nid in objects for nid in instances) or len(instances) > 4:
        return None, "This publication array supports up to four actual source instances"
    template = objects[family["template_group"]]
    display_nodes = copy.deepcopy(nodes)
    for node in display_nodes:
        if node["id"] == template["id"]:
            node["children"] = []
    metrics = {n["id"]: publication_render.measure_node(n, typography["body_px"], maximum=380 if n["id"] not in instances else 370,
                                                       symbol_profile=typography.get("symbol_profile", "plain")) for n in display_nodes}
    # A common dispatcher is a real node, permitted a wider physical glyph.
    # Equivalent peer declarations in older hierarchy records list source IDs
    # under source_group, while the representative macro may retain an alias.
    fanout = [n for n in nodes if n["id"] not in instances and n["kind"] == "control"
              and set(instances) <= {e["target"] for e in edges if e["source"] == n["id"] and e["kind"] == "control"}]
    if len(fanout) != 1:
        return None, "The resource array needs one actual dispatcher connected to all shown instances"
    dispatcher = fanout[0]
    metrics[dispatcher["id"]] = publication_render.measure_node(dispatcher, typography["body_px"], maximum=1500)
    if any(value is None for value in metrics.values()):
        return None, "A resource label does not fit the fixed publication font"
    boxes = {}
    array_width = 1660
    unit_width = (array_width - (len(instances) - 1) * 45) / len(instances)
    unit_height = max(metrics[nid]["height"] for nid in instances)
    array_y = 430
    for index, nid in enumerate(instances):
        if metrics[nid]["width"] > unit_width:
            return None, "Actual instance labels require more horizontal space at body type"
        boxes[nid] = _box((WIDTH - array_width) / 2 + index * (unit_width + 45), array_y, unit_width, unit_height)
    boxes[dispatcher["id"]] = _box((WIDTH - array_width) / 2, 250, array_width, metrics[dispatcher["id"]]["height"])
    # The shared backbone is justified by actual adjacency, not its name.
    adjacent_units = {n["id"]: {e["target"] if e["source"] == n["id"] else e["source"] for e in edges
                                if e["kind"] == "data" and n["id"] in {e["source"], e["target"]}} & set(instances) for n in nodes}
    common = [n for n in nodes if n["kind"] == "memory" and n["id"] not in instances and adjacent_units[n["id"]]]
    if not common:
        return None, "No source-proven storage service connects a shown instance"
    common_node = max(common, key=lambda n: (n.get("zone") == "memory", len(adjacent_units[n["id"]]), not n.get("original_group")))
    storage_y = array_y + unit_height + 175
    if adjacent_units[common_node["id"]] == set(instances):
        boxes[common_node["id"]] = _box((WIDTH - array_width) / 2, storage_y, array_width, metrics[common_node["id"]]["height"])
    else:
        # A partial source connection does not establish an array-wide memory
        # band, nor access paths for the remaining equivalent instances.
        centers = [boxes[nid]["x"] + boxes[nid]["width"] / 2 for nid in adjacent_units[common_node["id"]]]
        measured = metrics[common_node["id"]]
        boxes[common_node["id"]] = _box(sum(centers) / len(centers) - measured["width"] / 2,
                                        storage_y, measured["width"], measured["height"])
    assigned = set(boxes)
    # Trace the real command entry chain backwards from the dispatcher.
    entry = []
    current = dispatcher["id"]
    while True:
        parents = [e["source"] for e in edges if e["target"] == current and e["source"] not in assigned]
        if len(set(parents)) != 1:
            break
        current = parents[0]
        if current in entry:
            break
        entry.append(current); assigned.add(current)
    entry.reverse()
    if entry:
        total = sum(metrics[nid]["width"] for nid in entry) + (len(entry) - 1) * 85
        if total > WIDTH - 150:
            return None, "The command-entry chain is too wide at body type"
        x = (WIDTH - total) / 2
        for nid in entry:
            item = metrics[nid]
            boxes[nid] = _box(x, 100, item["width"], item["height"])
            x += item["width"] + 85
    remaining = [n for n in nodes if n["id"] not in assigned]
    if len(remaining) > 6:
        return None, "Additional common services need a dedicated resource projection"
    bottom_y = boxes[common_node["id"]]["y"] + boxes[common_node["id"]]["height"] + 150
    service_bottom = bottom_y
    for row_start in range(0, len(remaining), 3):
        row = remaining[row_start:row_start + 3]
        total = sum(metrics[n["id"]]["width"] for n in row) + max(0, len(row) - 1) * 85
        if total > WIDTH - 200:
            return None, "The service row is wider than the print canvas at fixed body type"
        x = WIDTH - 100 - total
        row_height = max(metrics[n["id"]]["height"] for n in row)
        for node in row:
            item = metrics[node["id"]]
            boxes[node["id"]] = _box(x, service_bottom, item["width"], item["height"])
            x += item["width"] + 85
        service_bottom += row_height + 120
    inset_node = {**template, "label": objects[template["id"]]["label"]}
    # Expansion leaders are not data inputs to a second hardware instance.
    inset_node["entry_sources"] = []
    inset_metrics = publication_render.measure_node(inset_node, typography["body_px"], maximum=720,
                                                   symbol_profile=typography.get("symbol_profile", "plain"))
    if inset_metrics is None:
        return None, "The actual representative inventory does not fit its inset"
    inset = {"id": "representative-expansion", "source_object": template["id"],
             "label": template["label"], "same_hardware": True,
             "box": _box(130, bottom_y, inset_metrics["width"], inset_metrics["height"]), "metrics": inset_metrics}
    if remaining and inset["box"]["x"] + inset["box"]["width"] + 80 > min(boxes[n["id"]]["x"] for n in remaining):
        inset["box"]["y"] = service_bottom + 30
    height = math.ceil(max(inset["box"]["y"] + inset["box"]["height"], max(b["y"] + b["height"] for b in boxes.values())) + 90)
    routed = copy.deepcopy(edges)
    for edge in routed:
        edge.pop("routing", None)
        if edge["source"] == dispatcher["id"] and edge["target"] in instances:
            edge["family"] = "instruction"
            edge["routing"] = {"source_side": "bottom", "target_side": "top"}
        elif edge["source"] in instances and edge["target"] == common_node["id"]:
            edge["routing"] = {"source_side": "bottom", "target_side": "top"}
        elif edge["target"] in instances and edge["source"] == common_node["id"]:
            edge["routing"] = {"source_side": "top", "target_side": "bottom"}
    template_box = boxes[template["id"]]
    inset["leader_pixels"] = [[template_box["x"], template_box["y"] + template_box["height"] / 2],
                               [30, template_box["y"] + template_box["height"] / 2],
                               [30, inset["box"]["y"] + inset["box"]["height"] / 2],
                               [inset["box"]["x"], inset["box"]["y"] + inset["box"]["height"] / 2]]
    return {"boxes": boxes, "height": height, "metrics": metrics, "edges": routed,
            "orientation": "resource-array-with-source-expansion", "ranks": {}, "insets": [inset],
            "display_nodes": display_nodes}, None


def _hierarchy_resource_candidate(nodes, edges, figure, typography, gap=110, data_spine=False):
    """Measured rows of actual peers with one real expansion per family.

    Common dispatchers, buses and storage are optional source objects, never
    prerequisites or inferred connections. Separate families retain their own
    representative and exact identities; a long inventory earns more space.
    """
    objects = {node["id"]: node for node in nodes}
    families = figure.get("repeat_families", [])
    if not families:
        return None, "A resource hierarchy needs source-proven repeated owners"
    family_ids, representatives = set(), []
    for family in families:
        ids = [family["template_group"], *family["instances"]]
        if len(set(ids)) != len(ids) or not set(ids) <= objects.keys() or family_ids & set(ids):
            return None, "Repeated families must be distinct actual source owners"
        family_ids.update(ids)
        representatives.append(objects[family["template_group"]])
    variants = [node for node in nodes if node.get("distinct_inventory_from") in {family["template_group"] for family in families}]
    representatives.extend(variants)
    representative_records = [*families, *[{"source_internal_relations": node.get("source_internal_relations", []),
                                             "source_internal_edge_indices": [relation["source_edge_index"] for relation in node.get("source_internal_relations", [])]}
                                            for node in variants]]
    array_ids = family_ids | {node["id"] for node in variants}
    display_nodes = copy.deepcopy(nodes)
    for node in display_nodes:
        if node["id"] in array_ids:
            node["children"] = []
    metrics = {node["id"]: publication_render.measure_node(node, typography["body_px"], maximum=640,
               symbol_profile=typography.get("symbol_profile", "plain")) for node in display_nodes}
    if any(item is None for item in metrics.values()):
        return None, "An actual resource label cannot fit without reducing publication type"
    external = [node for node in nodes if node.get("zone") == "external"]
    external_width = max((metrics[node["id"]]["width"] for node in external), default=0)
    left, content_width = 80, WIDTH - 160 - (external_width + gap if external else 0)
    if content_width < 600:
        return None, "Source external context leaves insufficient readable internal area"
    boxes, y = {}, 100
    # Source graph reachability distinguishes a real upstream command path
    # from downstream services; this does not create a broadcast dispatcher.
    forward = defaultdict(set)
    for edge in edges:
        if edge["kind"] not in {"feedback", "clock"}:
            forward[edge["source"]].add(edge["target"])
    def reaches(start, targets):
        pending, seen = list(forward[start]), set()
        while pending:
            current = pending.pop()
            if current in targets:
                return True
            if current not in seen:
                seen.add(current); pending.extend(forward[current])
        return False
    downstream = {node["id"] for node in nodes if any(reaches(instance, {node["id"]}) for instance in array_ids)}
    upstream = [node for node in nodes if node["id"] not in array_ids and node not in external
                and node["id"] not in downstream and reaches(node["id"], array_ids)]
    def pack_rows(items, start, width, origin, row_gap, item_gap=60, equal_height=False):
        rows, row, used = [], [], 0
        for node in items:
            measured = metrics[node["id"]]
            if measured["width"] > width:
                return None
            if row and used + item_gap + measured["width"] > width:
                rows.append(row); row, used = [], 0
            used += (item_gap if row else 0) + measured["width"]
            row.append(node)
        if row:
            rows.append(row)
        cursor = start
        for row in rows:
            total = sum(metrics[node["id"]]["width"] for node in row) + item_gap * (len(row) - 1)
            x = origin + (width - total) / 2
            row_height = max(metrics[node["id"]]["height"] for node in row)
            for node in row:
                measured = metrics[node["id"]]
                boxes[node["id"]] = _box(x, cursor, measured["width"], row_height if equal_height else measured["height"])
                x += measured["width"] + item_gap
            cursor += row_height + row_gap
        return cursor
    if upstream:
        ranks, _ = _organization_ranks(upstream, [edge for edge in edges if edge["source"] in {n["id"] for n in upstream} and edge["target"] in {n["id"] for n in upstream}])
        for rank in sorted(set(ranks.values())):
            y = pack_rows([node for node in upstream if ranks[node["id"]] == rank], y, content_width, left, gap)
            if y is None:
                return None, "A source upstream row exceeds readable document width"
    for family in families:
        peers = [objects[nid] for nid in [family["template_group"], *family["instances"]]]
        peers.extend(node for node in variants if node["distinct_inventory_from"] == family["template_group"])
        columns = max(1, min(len(peers), math.floor(content_width / 220)))
        while columns:
            maximum = min(370, (content_width - 45 * (columns - 1)) / columns)
            compact = {node["id"]: publication_render.measure_node({**node, "children": []}, typography["body_px"],
                         maximum=maximum, symbol_profile=typography.get("symbol_profile", "plain")) for node in peers}
            if all(value is not None for value in compact.values()):
                metrics.update(compact)
                break
            columns -= 1
        if not columns:
            return None, "Peer identities do not fit the measured document width"
        y = pack_rows(peers, y, content_width, left, gap + 35, item_gap=45, equal_height=True)
        if y is None:
            return None, "Actual peer labels require a wider document or separate family view"
    array_bottom = y
    inset_nodes, inset_metrics = [], []
    remaining = [node for node in nodes if node["id"] not in boxes and node not in external]
    for representative in representatives:
        expanded = {**copy.deepcopy(representative), "entry_sources": []}
        maximum = min(720, content_width / 2 - 25) if remaining else min(720, content_width)
        measured = publication_render.measure_node(expanded, typography["body_px"], maximum=maximum,
                    symbol_profile=typography.get("symbol_profile", "plain"), compact_inventory=True)
        if measured is None:
            measured = publication_render.measure_node(expanded, typography["body_px"], maximum=min(720, content_width),
                        symbol_profile=typography.get("symbol_profile", "plain"), compact_inventory=True)
        if measured is None:
            return None, "A representative's supplied internals exceed the readable inset budget"
        inset_nodes.append(expanded); inset_metrics.append(measured)
    inset_width = max(item["width"] for item in inset_metrics)
    # Use separate columns when source text actually fits; otherwise keep a
    # sequential arrangement with unchanged font and full source coverage.
    service_width = content_width - inset_width - 85
    side_by_side = not data_spine and bool(remaining) and service_width >= max(metrics[node["id"]]["width"] for node in remaining)
    service_origin = left + inset_width + 85 if side_by_side else left
    service_width = service_width if side_by_side else content_width
    cursor = array_bottom
    if remaining and data_spine:
        remaining_ids = {node["id"] for node in remaining}
        data_next = defaultdict(list)
        for edge in edges:
            if edge["kind"] == "data" and {edge["source"], edge["target"]} <= remaining_ids:
                data_next[edge["source"]].append(edge["target"])
        entries = {edge["target"] for edge in edges if edge["source"] in array_ids and edge["target"] in remaining_ids and edge["kind"] == "data"}
        if len(entries) != 1:
            return None, "A primary service spine needs one actual repeated-resource receiver"
        spine, current = [], next(iter(entries))
        while current not in spine:
            spine.append(current)
            following = list(dict.fromkeys(data_next[current]))
            if not following:
                break
            if len(following) != 1:
                return None, "A branching common data path needs another source-derived arrangement"
            current = following[0]
        support = [node for node in remaining if node["id"] not in spine]
        if len(spine) < 2 or not support:
            return None, "A service spine candidate needs an actual chain and separate side resources"
        main_width = max(metrics[nid]["width"] for nid in spine)
        side_width = max(metrics[node["id"]]["width"] for node in support)
        total = main_width + side_width + 110
        if total > content_width:
            return None, "Primary data and side resources do not fit beside each other at fixed publication type"
        origin = left + (content_width - total) / 2
        # A side resource aligns with its real data consumer. Its control-only
        # predecessors sit above it; they never occupy the main data corridor.
        side_rank = {}
        for node in support:
            targets = [spine.index(edge["target"]) for edge in edges if edge["source"] == node["id"] and edge["target"] in spine and edge["kind"] == "data"]
            if targets:
                side_rank[node["id"]] = min(targets)
        for _ in support:
            for edge in edges:
                if edge["source"] in {n["id"] for n in support} and edge["target"] in side_rank and edge["source"] not in side_rank:
                    side_rank[edge["source"]] = max(0, side_rank[edge["target"]] - 1)
        if len(side_rank) != len(support):
            return None, "Unattached common resources need another source-derived arrangement"
        # The existing many-input receiver spans the real peer endpoints.
        # This spends width on actual fan-in ports, without merging inputs or
        # adding a bus. Later services retain their measured symbol widths.
        receiver = spine[0]
        array_left = min(boxes[nid]["x"] for nid in array_ids)
        array_right = max(boxes[nid]["x"] + boxes[nid]["width"] for nid in array_ids)
        boxes[receiver] = _box(array_left, cursor, max(array_right - array_left, metrics[receiver]["width"]), metrics[receiver]["height"])
        cursor += metrics[receiver]["height"] + gap
        early_support = [node for node in support if side_rank[node["id"]] == 0]
        if early_support:
            for node in early_support:
                item = metrics[node["id"]]
                boxes[node["id"]] = _box(origin + main_width + 110 + (side_width - item["width"]) / 2, cursor, item["width"], item["height"])
                cursor += item["height"] + max(70, gap * .65)
        for rank, nid in enumerate(spine[1:], 1):
            peers = [node for node in support if side_rank[node["id"]] == rank]
            row_height = max(metrics[nid]["height"], sum(metrics[n["id"]]["height"] for n in peers) + 70 * max(0, len(peers) - 1))
            item = metrics[nid]
            boxes[nid] = _box(origin + (main_width - item["width"]) / 2, cursor + (row_height - item["height"]) / 2, item["width"], item["height"])
            side_y = cursor
            for node in peers:
                item = metrics[node["id"]]
                boxes[node["id"]] = _box(origin + main_width + 110 + (side_width - item["width"]) / 2, side_y, item["width"], item["height"])
                side_y += item["height"] + 70
            cursor += row_height + gap
    elif remaining:
        remaining_ids = {node["id"] for node in remaining}
        ranks, _ = _organization_ranks(remaining, [edge for edge in edges if {edge["source"], edge["target"]} <= remaining_ids])
        for rank in sorted(set(ranks.values())):
            cursor = pack_rows([node for node in remaining if ranks[node["id"]] == rank], cursor, service_width, service_origin, gap)
            if cursor is None:
                return None, "A service row exceeds the measured publication area"
    insets, inset_y = [], array_bottom if side_by_side else cursor
    for index, (representative, measured) in enumerate(zip(inset_nodes, inset_metrics)):
        b = boxes[representative["id"]]
        inset_box = _box(left, inset_y, measured["width"], measured["height"])
        internal = list(representative_records[index].get("source_internal_edge_indices", []))
        insets.append({"id": "representative-expansion" + ("-" + str(index + 1) if len(representatives) > 1 else ""),
                       "source_object": representative["id"], "label": representative["label"], "same_hardware": True,
                       "box": inset_box, "metrics": measured,
                       "source_members": list(representative["members"]),
                       "source_internal_edge_indices": internal,
                       "source_internal_relations": copy.deepcopy(representative_records[index].get("source_internal_relations", [])),
                       "annotation_text": "Same hardware detail", "annotation_role": "same-hardware-view",
                       "leader_pixels": [[b["x"], b["y"] + b["height"] / 2], [24 + index * 10, b["y"] + b["height"] / 2],
                                         [24 + index * 10, inset_y + measured["height"] / 2], [left, inset_y + measured["height"] / 2]]})
        if representative.get("distinct_inventory_from"):
            # Its exact owner label identifies this second source scope.
            # A leader across the peer row would cross unrelated resources.
            insets[-1]["leader_pixels"] = []
            insets[-1]["distinct_inventory_from"] = representative["distinct_inventory_from"]
        inset_y += measured["height"] + gap
    # External objects have a separate column outside the enclosing owners.
    external_y = 100
    for node in external:
        neighbors = [edge["target"] if edge["source"] == node["id"] else edge["source"] for edge in edges
                     if node["id"] in {edge["source"], edge["target"]}]
        measured = metrics[node["id"]]
        neighbor_y = [boxes[nid]["y"] + (boxes[nid]["height"] - measured["height"]) / 2
                      for nid in neighbors if nid in boxes]
        external_y = max(external_y, min(neighbor_y, default=100))
        boxes[node["id"]] = _box(left + content_width + gap, external_y, measured["width"], measured["height"])
        external_y += measured["height"] + gap
    height = math.ceil(max(inset_y - gap, external_y - gap, cursor - gap,
                           max(box["y"] + box["height"] for box in boxes.values())) + 90)
    routed = copy.deepcopy(edges)
    for edge in routed:
        edge.pop("routing", None)
    # Distinct fan-in operands get monotone ports and staggered bend levels.
    # The tracks are graphical geometry, never a common bus or extra edge.
    incoming = defaultdict(list)
    for edge in routed:
        if edge["source"] in array_ids and edge["target"] not in array_ids:
            if boxes[edge["source"]]["y"] + boxes[edge["source"]]["height"] < boxes[edge["target"]]["y"]:
                incoming[edge["target"]].append(edge)
    for target, relations in incoming.items():
        relations.sort(key=lambda edge: (boxes[edge["source"]]["x"], boxes[edge["source"]]["y"]))
        low = max(boxes[edge["source"]]["y"] + boxes[edge["source"]]["height"] for edge in relations) + 28
        high = boxes[target]["y"] - 28
        for index, edge in enumerate(relations):
            fraction = (index + 1) / (len(relations) + 1)
            source_x = boxes[edge["source"]]["x"] + boxes[edge["source"]]["width"] / 2
            if data_spine and boxes[target]["x"] + 18 <= source_x <= boxes[target]["x"] + boxes[target]["width"] - 18:
                edge["routing"] = {"source_side": "bottom", "target_side": "top", "source_fraction": .5,
                                   "target_fraction": (source_x - boxes[target]["x"]) / boxes[target]["width"]}
                continue
            bend_y = high - fraction * max(0, high - low)
            edge["routing"] = {"source_side": "bottom", "target_side": "top", "source_fraction": .5,
                               "target_fraction": fraction, "outer_route": True, "waypoint_axis": "y",
                               "waypoint_value": bend_y / height}
    return {"boxes": boxes, "height": height, "metrics": metrics, "edges": routed,
            "orientation": "source-hierarchy-with-representative-expansions", "ranks": {}, "insets": insets,
            "display_nodes": display_nodes}, None


def _resource_candidate(nodes, edges, figure, typography, gap=110, data_spine=False):
    if data_spine:
        return _hierarchy_resource_candidate(nodes, edges, figure, typography, gap, True)
    raw, _ = _dispatcher_resource_candidate(nodes, edges, figure, typography)
    if raw is not None:
        return raw, None
    return _hierarchy_resource_candidate(nodes, edges, figure, typography, gap)


def _containers(spec, nodes, boxes, body_px):
    """Only real, contiguous ownership scopes; context is never reparented."""
    groups = {g["id"]: g for g in spec.get("groups", [])}
    source = {n["id"]: n for n in spec["nodes"]}
    represented = {n.get("source_group") for n in nodes if n.get("children")}
    output = []
    for gid, group in groups.items():
        if gid in represented:
            continue
        def inside(nid):
            owner = source[nid].get("group", "")
            while owner:
                if owner == gid:
                    return True
                owner = groups.get(owner, {}).get("parent", "")
            return False
        members = [n["id"] for n in nodes if all(inside(nid) for nid in n["members"])]
        if len(members) < 2:
            continue
        box = None
        # Leave a genuine gap to neighboring hardware; a touching boundary can
        # look as though that neighbor is also contained in the owner.
        for padding in [24, 16, 10]:
            candidate = _union([boxes[nid] for nid in members], padding)
            if not any(_overlap(_box(other["x"] - 8, other["y"] - 8, other["width"] + 16, other["height"] + 16), candidate)
                       for nid, other in boxes.items() if nid not in members):
                box = candidate
                break
        if box is None:
            continue
        title_width = publication_render.font(body_px).getlength(group["label"])
        if title_width > box["width"] - 30:
            continue
        output.append({"id": gid, "source_group": gid, "label": group["label"], "members": members, "box": box})
    return output


def _separate_detail_views(raw, nodes, containers, typography, language="en"):
    """Keep an annotation outside hardware scopes without moving its sources.

    Side space is preferred; otherwise the same-hardware view gets a separate
    lower region. Its measured type and inventory remain intact. Context which
    occupies that annotation column is shifted vertically, not reparented.
    """
    if not raw.get("insets"):
        return
    old_height = raw["height"]
    gap = max(54, typography["body_px"] * 1.5)
    owner_boxes = [c["box"] for c in containers if c.get("render_boundary") is not False]
    main_boxes = [raw["boxes"][node["id"]] for node in nodes if node.get("zone") != "external"]
    owner = _union(owner_boxes or main_boxes, 0) if owner_boxes or main_boxes else None
    if owner is None:
        return
    occupied_details = []
    for index, inset in enumerate(raw["insets"]):
        box = inset["box"]
        if any(_overlap(box, scope) for scope in owner_boxes):
            right = owner["x"] + owner["width"] + gap
            left = owner["x"] - gap - box["width"]
            if right + box["width"] <= WIDTH - 12:
                box["x"] = right
            elif left >= 12:
                box["x"] = left
            else:
                box["y"] = owner["y"] + owner["height"] + gap + typography["signal_px"] * 1.3
        for previous in occupied_details:
            if _overlap(_box(box["x"], box["y"] - gap, box["width"], box["height"] + 2 * gap), previous):
                box["y"] = previous["y"] + previous["height"] + gap + typography["signal_px"] * 1.3
        occupied_details.append(copy.deepcopy(box))
        inset["annotation_text"] = "同一硬件细节" if language == "zh" else "Same hardware detail"
        inset["annotation_role"] = "same-hardware-view"
        inset["outside_source_owner"] = True
        # A leader uses an outer annotation lane and enters the header, away
        # from operand/control entry points. It is never a source relation.
        source = raw["boxes"][inset["source_object"]]
        anchor_y = source["y"] + min(source["height"] * .2, typography["body_px"] * .4)
        attach_y = box["y"] + min(inset["metrics"].get("header_height", box["height"]) / 2, typography["body_px"] * .6)
        if not inset.get("distinct_inventory_from"):
            if box["x"] > owner["x"] + owner["width"]:
                lane_x = (owner["x"] + owner["width"] + box["x"]) / 2
                inset["leader_pixels"] = [[source["x"], anchor_y], [12, anchor_y], [12, 12 + index * 6],
                                           [lane_x, 12 + index * 6], [lane_x, attach_y], [box["x"], attach_y]]
            else:
                lane_x = max(12, min(owner["x"], box["x"]) - gap)
                inset["leader_pixels"] = [[source["x"], anchor_y], [lane_x, anchor_y],
                                           [lane_x, attach_y], [box["x"], attach_y]]
        inset["leader_role"] = "explanatory view leader, without arrowhead or source-edge membership"
    for node in nodes:
        if node.get("zone") != "external":
            continue
        box = raw["boxes"][node["id"]]
        for inset in raw["insets"]:
            detail = inset["box"]
            expanded = _box(detail["x"] - gap, detail["y"] - gap, detail["width"] + 2 * gap, detail["height"] + 2 * gap)
            if _overlap(box, expanded):
                box["y"] = detail["y"] + detail["height"] + gap
        # Context which shares a detail column enters from its facing side.
        # A vertically nearest top port would drag its path through the inset.
        if box["x"] > owner["x"] + owner["width"]:
            for edge in raw["edges"]:
                if edge["source"] == node["id"]:
                    edge["routing"] = {"source_side": "left", "target_side": "right"}
                elif edge["target"] == node["id"]:
                    edge["routing"] = {"source_side": "right", "target_side": "left"}
        elif box["x"] + box["width"] < owner["x"]:
            for edge in raw["edges"]:
                if edge["source"] == node["id"]:
                    edge["routing"] = {"source_side": "right", "target_side": "left"}
                elif edge["target"] == node["id"]:
                    edge["routing"] = {"source_side": "left", "target_side": "right"}
    raw["height"] = math.ceil(max([b["y"] + b["height"] for b in raw["boxes"].values()]
                                  + [i["box"]["y"] + i["box"]["height"] for i in raw["insets"]]) + 90)
    if raw["height"] != old_height:
        for edge in raw["edges"]:
            routing = edge.get("routing", {})
            if routing.get("waypoint_axis") == "y":
                routing["waypoint_value"] *= old_height / raw["height"]


def _detail_context_scene(scene, plan):
    """Take a context path around, rather than through, an outside inset."""
    if not plan.get("insets"):
        return
    width, height = scene["width"], scene["height"]
    objects = {node["id"]: node for node in plan["macro_nodes"]}
    boxes = {nid: _box(box["x"] * width, box["y"] * height,
                       box["width"] * width, box["height"] * height) for nid, box in plan["boxes"].items()}
    internal = [box for nid, box in boxes.items() if objects[nid].get("zone") != "external"]
    if not internal:
        return
    owner = _union(internal, 24)
    details = [publication_render._rect(inset["box"], width, height) for inset in plan["insets"]]
    for route in scene["routes"]:
        external = route["source"] if objects[route["source"]].get("zone") == "external" else route["target"] if objects[route["target"]].get("zone") == "external" else ""
        if not external:
            continue
        points = [(x * width, y * height) for x, y in route["points"]]
        if not any(publication_render._wire_crosses_rect(a, b, detail, 8) for a, b in zip(points, points[1:]) for detail in details):
            continue
        context = boxes[external]
        right_details = [detail for detail in details if detail[0] > owner["x"] + owner["width"]]
        left_details = [detail for detail in details if detail[2] < owner["x"]]
        if context["x"] > owner["x"] + owner["width"] and right_details:
            corridor_x = (owner["x"] + owner["width"] + min(detail[0] for detail in right_details)) / 2
        elif context["x"] + context["width"] < owner["x"] and left_details:
            corridor_x = (owner["x"] + max(detail[2] for detail in left_details)) / 2
        else:
            continue
        start, end = points[0], points[-1]
        candidate = [start, (corridor_x, start[1]), (corridor_x, end[1]), end]
        if any(publication_render._wire_crosses_rect(a, b, detail, 8) for a, b in zip(candidate, candidate[1:]) for detail in details):
            continue
        route["points"] = [[round(x / width, 6), round(y / height, 6)] for x, y in candidate]
        route["annotation_detour"] = "existing context relationship kept outside the same-hardware view"


def _route_metrics(scene):
    lengths, bends, segments = [], 0, []
    width, height = scene["width"], scene["height"]
    for route in scene["routes"]:
        points = [(x * width, y * height) for x, y in route["points"]]
        bends += max(0, len(points) - 2)
        lengths.append(sum(math.dist(a, b) for a, b in zip(points, points[1:])))
        segments.extend((a, b, route.get("id")) for a, b in zip(points, points[1:]))
    crossings = 0
    for index, (a, b, rid) in enumerate(segments):
        for c, d, other in segments[index + 1:]:
            if rid == other:
                continue
            if abs(a[0] - b[0]) < .1 and abs(c[1] - d[1]) < .1:
                crosses = min(c[0], d[0]) + 1 < a[0] < max(c[0], d[0]) - 1 and min(a[1], b[1]) + 1 < c[1] < max(a[1], b[1]) - 1
            elif abs(a[1] - b[1]) < .1 and abs(c[0] - d[0]) < .1:
                crosses = min(a[0], b[0]) + 1 < c[0] < max(a[0], b[0]) - 1 and min(c[1], d[1]) + 1 < a[1] < max(c[1], d[1]) - 1
            else:
                crosses = False
            crossings += bool(crosses)
    return {"crossings": crossings, "bends": bends, "longest_route_px": round(max(lengths, default=0), 1),
            "total_route_px": round(sum(lengths), 1)}


def _boundary_conflicts(scene, containers, clearance):
    """Crossing a logical scope is valid; tracking its outline is ambiguous."""
    width, height = scene["width"], scene["height"]
    conflicts = []
    for container in containers:
        if container.get("render_boundary") is False:
            continue
        b = container["box"]
        left, right = b["x"] * width, (b["x"] + b["width"]) * width
        top, bottom = b["y"] * height, (b["y"] + b["height"]) * height
        for route in scene["routes"]:
            points = [(x * width, y * height) for x, y in route["points"]]
            for a, b in zip(points, points[1:]):
                if abs(a[1] - b[1]) < .1:
                    near = min(abs(a[1] - top), abs(a[1] - bottom)) < clearance
                    span = min(max(a[0], b[0]), right) - max(min(a[0], b[0]), left)
                else:
                    near = min(abs(a[0] - left), abs(a[0] - right)) < clearance
                    span = min(max(a[1], b[1]), bottom) - max(min(a[1], b[1]), top)
                if near and span > 44:
                    conflicts.append({"source_group": container["source_group"], "route_id": route.get("id"), "parallel_span_px": round(span, 1)})
    return conflicts


def _segment_distance(a, b, c, d):
    """Orthogonal segment distance; zero includes overlap and endpoint touch."""
    epsilon = .05
    horizontal_ab = abs(a[1] - b[1]) < epsilon
    horizontal_cd = abs(c[1] - d[1]) < epsilon
    if horizontal_ab and horizontal_cd:
        contact = abs(a[1] - c[1]) < epsilon and min(max(a[0], b[0]), max(c[0], d[0])) >= max(min(a[0], b[0]), min(c[0], d[0])) - epsilon
    elif not horizontal_ab and not horizontal_cd:
        contact = abs(a[0] - c[0]) < epsilon and min(max(a[1], b[1]), max(c[1], d[1])) >= max(min(a[1], b[1]), min(c[1], d[1])) - epsilon
    else:
        h0, h1, v0, v1 = (a, b, c, d) if horizontal_ab else (c, d, a, b)
        contact = min(h0[0], h1[0]) - epsilon <= v0[0] <= max(h0[0], h1[0]) + epsilon and min(v0[1], v1[1]) - epsilon <= h0[1] <= max(v0[1], v1[1]) + epsilon
    if contact:
        return 0.0
    def point_distance(point, start, end):
        dx, dy = end[0] - start[0], end[1] - start[1]
        length_squared = dx * dx + dy * dy
        if not length_squared:
            return math.dist(point, start)
        t = max(0, min(1, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length_squared))
        return math.dist(point, (start[0] + t * dx, start[1] + t * dy))
    return min(point_distance(a, c, d), point_distance(b, c, d), point_distance(c, a, b), point_distance(d, a, b))


def input_trace_quality(plan, scene):
    """Print-scale logical input separation, independently of source IDs."""
    width, height = scene["width"], scene["height"]
    body_px = plan["typography"]["body_px"]
    required_port_gap = math.ceil(body_px * 1.5)
    reports, failures = [], []
    for node in plan["macro_nodes"]:
        if len(node.get("children", [])) < 2:
            continue
        incoming = []
        for route in scene["routes"]:
            if route["kind"] not in {"data", "relation"}:
                continue
            if route["target"] == node["id"]:
                incoming.append((route["source"], [(x * width, y * height) for x, y in route["points"]]))
            elif route.get("bidirectional") and route["source"] == node["id"]:
                incoming.append((route["target"], [(x * width, y * height) for x, y in reversed(route["points"])]))
        if len({source for source, _ in incoming}) < 2:
            continue
        pairs = [(a, b) for index, a in enumerate(incoming) for b in incoming[index + 1:] if a[0] != b[0]]
        port_gap = min(math.dist(a[1][-1], b[1][-1]) for a, b in pairs)
        trace_gap = min(_segment_distance(p, q, r, s) for a, b in pairs
                        for p, q in zip(a[1], a[1][1:]) for r, s in zip(b[1], b[1][1:]))
        report = {"owner": node["id"], "producer_count": len({source for source, _ in incoming}),
                  "minimum_port_gap_px": round(port_gap, 3), "required_port_gap_px": required_port_gap,
                  "minimum_path_clearance_px": round(trace_gap, 3), "paths_touch_or_share": trace_gap < .05,
                  "target_width_mm": plan["typography"]["target_width_mm"],
                  "geometry_is_not_new_hardware_ports": True}
        reports.append(report)
        if port_gap + .1 < required_port_gap:
            failures.append({"owner": node["id"], "reason": "Logical input entries are closer than 1.5 body-font units"})
        if trace_gap < body_px * .75:
            failures.append({"owner": node["id"], "reason": "Different producer paths touch, share a segment, or lack a clear print-scale channel"})
    return {"clear": not failures, "owners": reports, "failures": failures}


def _control_feedback_scene(scene, plan):
    """Use reserved outer tracks rather than a shortest path along a boundary."""
    width, height = scene["width"], scene["height"]
    objects = {n["id"]: n for n in plan["macro_nodes"]}
    for route in scene["routes"]:
        if route["kind"] not in {"feedback", "clock"} or objects[route["target"]]["kind"] != "control":
            continue
        routing = route.get("routing", {})
        if not routing.get("outer_route"):
            continue
        original_points = route["points"]
        start, end = original_points[0], original_points[-1]
        target = plan["boxes"][route["target"]]
        left = target["x"] * width
        right = (target["x"] + target["width"]) * width
        outside = left - 75 if abs(end[0] * width - left) < 1 else right + 75
        y = routing["waypoint_value"]
        # Keep the original obstacle-aware source leg: its vertical descent
        # may need to pass beside a result/status resource in the lower row.
        index = next((i for i, point in enumerate(original_points) if abs(point[1] * height - y * height) <= 4), None)
        prefix = original_points[:index + 1] if index is not None else [start, [start[0], y]]
        y = prefix[-1][1]
        route["points"] = [*prefix, [outside / width, y], [outside / width, end[1]], end]


def _ownership_hub_scene(scene, plan):
    """Route true side chains and reverse interactions on distinct tracks."""
    width, height = scene["width"], scene["height"]
    boxes = plan["boxes"]
    data_neighbors = defaultdict(set)
    for edge in plan["macro_edges"]:
        if edge["kind"] == "data":
            data_neighbors[edge["source"]].add(edge["target"])
            data_neighbors[edge["target"]].add(edge["source"])
    hubs = [nid for nid, b in boxes.items()
            if any(e["source"] == nid for e in plan["macro_edges"] if e["kind"] == "data")
            and any(e["target"] == nid for e in plan["macro_edges"] if e["kind"] == "data")
            and len(data_neighbors[nid]) >= 3
            and not next(n for n in plan["macro_nodes"] if n["id"] == nid).get("children")]
    if len(hubs) != 1:
        return
    hub = boxes[hubs[0]]
    hub_right = (hub["x"] + hub["width"]) * width
    services = [b for b in boxes.values() if b["x"] * width > hub_right]
    if not services:
        return
    inside_track = (hub_right + min(b["x"] * width for b in services)) / 2
    outside_track = max((b["x"] + b["width"]) * width for b in services) + plan["typography"]["body_px"] * .75
    for route in scene["routes"]:
        routing = route.get("routing", {})
        start, end = route["points"][0], route["points"][-1]
        if routing.get("organization_track") == "outside-service-column":
            route["points"] = [start, [outside_track / width, start[1]],
                               [outside_track / width, end[1]], end]
        elif route.get("family") == "return" and routing.get("source_side") == "left" and routing.get("target_side") == "left":
            y = routing["waypoint_value"]
            target = boxes[route["target"]]
            outside_left = target["x"] * width - plan["typography"]["body_px"] * .75
            route["points"] = [start, [inside_track / width, start[1]],
                               [inside_track / width, y], [outside_left / width, y],
                               [outside_left / width, end[1]], end]


def _owned_join_scene(scene, plan):
    """Separate true producer operands from an outer control return."""
    width, height = scene["width"], scene["height"]
    boxes = plan["boxes"]
    incoming = defaultdict(list)
    for route in scene["routes"]:
        if route["kind"] == "data":
            incoming[route["target"]].append(route)
    joins = [nid for nid, routes in incoming.items() if len(routes) >= 2]
    if len(joins) != 1:
        return
    join = joins[0]
    left_edge = boxes[join]["x"] * width
    producers = sorted(incoming[join], key=lambda route: route["points"][0][1])
    for index, route in enumerate(producers):
        start, end = route["points"][0], route["points"][-1]
        track = left_edge - (len(producers) - index + 1) * 36
        route["points"] = [start, [track / width, start[1]], [track / width, end[1]], end]
    for route in scene["routes"]:
        if route.get("routing", {}).get("organization_track") != "owned-join-outer-control":
            continue
        start, end = route["points"][0], route["points"][-1]
        external = boxes[route["source"]]
        outside = (external["x"] + external["width"]) * width + 30
        returning = left_edge - 36
        bottom = height - 65
        route["points"] = [start, [outside / width, start[1]], [outside / width, bottom / height],
                           [returning / width, bottom / height], [returning / width, end[1]], end]


def owner_scope_quality(plan, scene):
    """Projected ownership arrows cannot visually select an inventory child."""
    if plan.get("view_type") != "publication-ownership-flow":
        return {"clear": True, "failures": []}
    objects = {n["id"]: n for n in plan["macro_nodes"]}
    failures = []
    height = scene["height"]
    for route in scene["routes"]:
        for nid, point in [(route["source"], route["points"][0]), (route["target"], route["points"][-1])]:
            node = objects[nid]
            if not node.get("source_group") or not node.get("children"):
                continue
            measured = plan["symbol_metrics"][nid]
            box = plan["boxes"][nid]
            local_y = (point[1] - box["y"]) * height
            if not measured["header_height"] + 8 <= local_y <= measured["header_height"] + measured["entry_gutter_height"] - 8:
                failures.append({"owner": nid, "route_id": route.get("id"),
                                 "reason": "A scope endpoint selects a title or child row instead of the common strip"})
    return {"clear": not failures, "failures": failures,
            "meaning": "Boundary entry is scope-level, not a fabricated child-to-child mapping."}


def organization_trace_quality(plan, scene):
    """Include elbow contact and shared segments, not only strict crossings."""
    if plan.get("view_type") != "publication-ownership-flow":
        return {"clear": True, "contacts": []}
    width, height = scene["width"], scene["height"]
    paths = [[(x * width, y * height) for x, y in route["points"]] for route in scene["routes"]]
    contacts = []
    for index, path in enumerate(paths):
        for other in range(index + 1, len(paths)):
            distance = min(_segment_distance(a, b, c, d) for a, b in zip(path, path[1:])
                           for c, d in zip(paths[other], paths[other][1:]))
            if distance < .1:
                contacts.append({"routes": [scene["routes"][index].get("id"), scene["routes"][other].get("id")],
                                 "reason": "Independent paths touch, cross, or share a segment"})
    return {"clear": not contacts, "contacts": contacts,
            "geometry_is_not_new_junctions": True}


def _product_candidate(nodes, edges, figure, typography, linear=False, hub=False):
    """A whole-system hero and its context, with source-backed functional tiles.

    The frame is a logical product symbol, never a silicon floorplan. Its
    members come from the semantic projection rather than name heuristics.
    """
    frame = figure.get("concept_frame", {})
    internal_ids = set(frame.get("member_ids", [n["id"] for n in nodes]))
    inside = [n for n in nodes if n["id"] in internal_ids]
    outside = [n for n in nodes if n["id"] not in internal_ids]
    if not inside:
        return None, "A product view needs a real system inventory"
    if hub:
        raw, failure = _ownership_hub_candidate(nodes, edges, typography, 1)
        if failure:
            return raw, failure
        for node in inside:
            box = raw["boxes"][node["id"]]
            box["x"] = max(400, min(box["x"], 1400 - box["width"]))
        left = [n for n in outside if n["kind"] != "memory"]
        right = [n for n in outside if n["kind"] == "memory"]
        for side, peers in [("left", left), ("right", right)]:
            for index, node in enumerate(peers):
                box = raw["boxes"][node["id"]]
                box["x"] = 30 if side == "left" else WIDTH - box["width"] - 30
                box["y"] = raw["height"] * (index + 1) / (len(peers) + 1) - box["height"] / 2
        hero = _union([raw["boxes"][n["id"]] for n in inside], 30)
        hero["y"] -= 75; hero["height"] += 75
        if hero["y"] < 50:
            delta = 50 - hero["y"]
            for box in raw["boxes"].values():box["y"] += delta
            hero["y"] += delta; raw["height"] += delta
        if any(_overlap(hero, raw["boxes"][n["id"]]) for n in outside):
            return None, "Product boundary would contain an external resource"
        raw["height"] = max(1012, raw["height"], math.ceil(hero["y"] + hero["height"] + 50))
        raw["presentation_frame"] = {**frame, "box": hero}
        return raw, None
    if linear:
        raw, failure = _flow_candidate(nodes, edges, typography, "left-to-right", 125)
        if failure:
            return raw, failure
        hero = _union([raw["boxes"][n["id"]] for n in inside], 32)
        hero["y"] -= 68
        hero["height"] += 68
        # A frame may not falsely enclose an explicitly external resource.
        if any(_overlap(hero, raw["boxes"][n["id"]]) for n in outside):
            return None, "Product boundary would contain an external resource"
        raw["height"] = max(raw["height"], hero["y"] + hero["height"] + 48)
        raw["presentation_frame"] = {**frame, "box": hero}
        raw["orientation"] = "product-system-and-context"
        return raw, None
    columns = 2 if len(inside) <= 6 else 3
    left = [n for n in outside if n["kind"] != "memory"]
    right = [n for n in outside if n["kind"] == "memory"]
    # Keep external resources out of the chip silhouette even in unusual input.
    if len(left) > 3:
        right.extend(left[3:]); left = left[:3]
    x0 = 420 if left else 110
    x1 = 1380 if right else 1690
    hero_width = x1 - x0
    gap = 48
    tile_max = (hero_width - 100 - (columns - 1) * gap) / columns
    metrics = {}
    for node in nodes:
        maximum = tile_max if node in inside else 295
        measured = publication_render.measure_node(node, typography["body_px"], maximum=maximum,
                                                      symbol_profile=typography.get("symbol_profile", "plain"))
        if measured is None:
            return None, "Product label exceeds its measured tile; use a wider source projection"
        metrics[node["id"]] = measured
    row_height = max(132, max(metrics[n["id"]]["height"] for n in inside))
    rows = math.ceil(len(inside) / columns)
    hero_height = 120 + rows * row_height + (rows - 1) * gap + 60
    height = max(1012, math.ceil(hero_height + 180),
                 160 + max(len(left), len(right), 1) * 220)
    y0 = (height - hero_height) / 2
    boxes = {}
    role_order = {"compute": 0, "control": 1, "memory": 2, "io": 3}
    ordered = sorted(inside, key=lambda n: (role_order.get(n["kind"], 4), n["id"]))
    for index, node in enumerate(ordered):
        column, row = index % columns, index // columns
        width = tile_max
        boxes[node["id"]] = _box(x0 + 50 + column * (width + gap), y0 + 120 + row * (row_height + gap), width, row_height)
    for side, peers in [("left", left), ("right", right)]:
        for index, node in enumerate(peers):
            m = metrics[node["id"]]
            y = height * (index + 1) / (len(peers) + 1) - m["height"] / 2
            boxes[node["id"]] = _box(55 if side == "left" else 1450, y, 295, m["height"])
    projected = copy.deepcopy(edges)
    for edge in projected:
        a, b = boxes[edge["source"]], boxes[edge["target"]]
        if abs((a["y"] + a["height"] / 2) - (b["y"] + b["height"] / 2)) < 10:
            direction = a["x"] < b["x"]
            edge["routing"] = {"source_side": "right" if direction else "left", "target_side": "left" if direction else "right"}
    return {"boxes": boxes, "metrics": metrics, "edges": projected, "height": height,
            "orientation": "product-hero-with-functional-regions", "ranks": {}, "insets": [],
            "presentation_frame": {**frame, "box": _box(x0, y0, hero_width, hero_height)}}, None


def _product_anchor_candidate(nodes, edges, figure, typography):
    """Lay out an existing high-degree resource, not a newly invented fabric."""
    frame = figure.get("concept_frame", {})
    internal = set(frame.get("member_ids", []))
    peers = {n["id"]: n for n in nodes}
    degree = {nid: sum(nid in {e["source"], e["target"]} for e in edges) for nid in internal}
    if not degree or max(degree.values()) < 3:
        return None, "This product has no source-backed multi-interface anchor"
    anchor = max(sorted(degree), key=degree.get)
    incoming, outgoing = [], []
    for edge in edges:
        other = edge["target"] if edge["source"] == anchor else edge["source"] if edge["target"] == anchor else None
        if other not in internal or other in incoming + outgoing:
            continue
        (incoming if edge["target"] == anchor and not edge.get("bidirectional") else outgoing).append(other)
    if len(incoming) > 3 or len(outgoing) > 3:
        return None, "Too many primary product interfaces for one hero"
    rest = sorted(internal - {anchor} - set(incoming + outgoing))
    if len(rest) > 6:
        return None, "Support inventory exceeds one concept canvas"
    metrics = {n["id"]: publication_render.measure_node(n, typography["body_px"], maximum=270,
                    symbol_profile=typography.get("symbol_profile", "plain")) for n in nodes}
    if any(value is None for value in metrics.values()):
        return None, "Product anchor text needs a wider semantic region"
    height = max(1012, 830 + math.ceil(len(rest) / 3) * 170)
    boxes = {anchor: _box(800, 390, 280, 150)}
    for side, ids in [("left", incoming), ("right", outgoing)]:
        for index, nid in enumerate(ids):
            boxes[nid] = _box(410 if side == "left" else 1190, 160 + 600 * (index + 1) / (len(ids) + 1), 270, 145)
    for index, nid in enumerate(rest):
        boxes[nid] = _box(410 + (index % 3) * 390, 770 + (index // 3) * 170, 270, 145)
    for node in nodes:
        nid = node["id"]
        if nid in internal:continue
        incident = [e for e in edges if nid in {e["source"], e["target"]}]
        related = next((e["source"] if e["target"] == nid else e["target"] for e in incident
                        if (e["source"] if e["target"] == nid else e["target"]) in boxes), None)
        left = bool(incident) and all(e["source"] == nid and not e.get("bidirectional") for e in incident)
        y = boxes[related]["y"] if related else 250
        boxes[nid] = _box(30 if left else 1530, y, 240, 145)
    routed = copy.deepcopy(edges)
    for edge in routed:
        a, b = boxes[edge["source"]], boxes[edge["target"]]
        forward = a["x"] < b["x"]
        edge["routing"] = {"source_side": "right" if forward else "left", "target_side": "left" if forward else "right"}
    return {"boxes": boxes, "metrics": metrics, "edges": routed, "height": height,
            "orientation": "product-functional-anchor-and-context", "ranks": {}, "insets": [],
            "presentation_frame": {**frame, "box": _box(350, 70, 1140, height - 125)}}, None


def build(spec, figure, settings):
    """Build and select a publication candidate, or return None with reasons.

    Only ``layout_scene``/``composition_diagnostics`` are written on the display
    figure.  The source spec and supplied display projection remain immutable.
    """
    contract = figure.get("design_contract", {})
    try:
        publication_render.font(12)
    except (ImportError, RuntimeError):
        figure["composition_diagnostics"] = {"candidates": [], "limitation": "A measured target plate requires optional Pillow and an available font."}
        return None
    grammar = contract.get("grammar")
    if grammar not in {"product-concept", "folded-flow", "control-band", "resource-array", "exact-flow", "ownership-flow"}:
        return None
    if grammar == "exact-flow" and spec.get("category") not in {"architecture", "microarchitecture", "dataflow", "pipeline", "memory"}:
        return None
    nodes, edges = _source_projection(spec, figure)
    if grammar == "product-concept":
        required = [*spec.get("verbatim_labels", []), *figure.get("required_verbatim_labels", [])]
        for node in nodes:
            if not any(literal and literal in node.get("required_detail", "") for literal in required):
                node.pop("required_detail", None)
    if not nodes:
        return None
    target_width = float(contract.get("target_width_mm", 160))
    if contract.get("scene_id") == "concept":
        target_width = max(240, target_width)
        contract["target_width_mm"] = target_width
    elif contract.get("scene_id") == "flow":
        target_width = max(200, target_width)
        contract["target_width_mm"] = target_width
    body_pt, signal_pt = float(contract.get("body_pt", 9)), float(contract.get("signal_pt", 8.5))
    if not 40 <= target_width <= 400 or min(body_pt, signal_pt) < 6:
        raise ValueError("Invalid publication typography contract")
    typography = {"target_width_mm": target_width, "body_pt": body_pt, "signal_pt": signal_pt,
                  "body_px": math.ceil(publication_render.pixels_for_points(body_pt, WIDTH, target_width)),
                  "signal_px": math.ceil(publication_render.pixels_for_points(signal_pt, WIDTH, target_width)),
                  "no_font_shrink": True,
                  "symbol_profile": contract.get("symbol_profile", "plain")}
    if typography["symbol_profile"] not in {"plain", "ink-header"}:
        raise ValueError("Unknown publication symbol profile")
    choices = [("folded-input-output", 70), ("folded-input-output", 95), ("top-to-bottom", 100), ("left-to-right", 80)] if grammar == "folded-flow" else [("top-to-bottom", 100), ("left-to-right", 80)] if grammar == "exact-flow" else [("ownership-hub", 2), ("ownership-hub", 1), ("ownership-join", 1), ("ownership-join", 2), ("top-to-bottom", 1), ("left-to-right", 1), ("top-to-bottom", 2), ("left-to-right", 2)] if grammar == "ownership-flow" else [("controller-band", 38), ("controller-band", 24)] if grammar == "control-band" else [("resource-array", 110), ("resource-array", 145)]
    if grammar == "product-concept":
        choices = [("product-hero", 0), ("product-anchor", 0), ("product-hub", 0), ("product-linear", 0)]
    elif contract.get("preferred_reading_direction") == "left-to-right" and grammar in {"folded-flow", "exact-flow"}:
        choices = [("left-to-right", 110), ("folded-input-output", 95), ("existing-flow-hub", 1)] if grammar == "folded-flow" else [("left-to-right", 110), ("left-to-right", 150), ("existing-flow-hub", 1), ("top-to-bottom", 100)]
    elif contract.get("scene_id") == "detail" and grammar == "exact-flow":
        choices = [("implementation-fanout", 80), *choices]
    if grammar == "resource-array":
        choices = [("resource-data-spine", 110), ("resource-data-spine", 145), *choices]
    if figure.get("projection", {}).get("retained_payload_groups"):
        choices = [("owner-payload", 0), *choices]
    candidates, diagnostics = [], []
    for orientation, gap in choices:
        if orientation == "owner-payload":
            raw, failure = _owner_payload_candidate(nodes, edges, typography)
        elif grammar == "product-concept":
            raw, failure = _product_anchor_candidate(nodes, edges, figure, typography) if orientation == "product-anchor" else _product_candidate(nodes, edges, figure, typography, orientation == "product-linear", orientation == "product-hub")
        elif grammar in {"folded-flow", "exact-flow"}:
            # A bounded leaf mechanism may spend width on exact resource names
            # and numeric organization, rather than folding them away or
            # shrinking the physical font. Larger lifecycle candidates keep
            # their existing per-symbol width budget.
            leaf_maximum = 640 if figure.get("projection", {}).get("abstraction_policy") == "bounded-leaf-flow" else 400
            raw, failure = _control_candidate(nodes, edges, typography, gap) if orientation == "implementation-fanout" else _ownership_hub_candidate(nodes, edges, typography, gap) if orientation == "existing-flow-hub" else _folded_candidate(nodes, edges, typography, gap) if orientation == "folded-input-output" else _flow_candidate(nodes, edges, typography, orientation, gap, leaf_maximum=leaf_maximum)
        elif grammar == "control-band":
            raw, failure = _control_candidate(nodes, edges, typography, gap)
        elif grammar == "ownership-flow":
            raw, failure = _ownership_hub_candidate(nodes, edges, typography, gap) if orientation == "ownership-hub" else _owned_join_candidate(nodes, edges, typography, gap) if orientation == "ownership-join" else _ownership_candidate(nodes, edges, typography, orientation, gap)
        else:
            raw, failure = _resource_candidate(nodes, edges, figure, typography, gap, orientation == "resource-data-spine")
        candidate_id = orientation + "-" + str(gap)
        if failure:
            diagnostics.append({"id": candidate_id, "accepted": False, "reasons": [failure]})
            continue
        if grammar == "ownership-flow":
            failure = _owner_scope_entries(raw, nodes, typography)
            if failure:
                diagnostics.append({"id": candidate_id, "accepted": False, "reasons": [failure]})
                continue
        height = raw["height"]
        containers = [] if grammar in {"ownership-flow", "product-concept"} or contract.get("scene_id") == "flow" else _containers(spec, nodes, raw["boxes"], typography["body_px"])
        if raw.get("insets"):
            _separate_detail_views(raw, nodes, containers, typography, settings.get("language", "en"))
            height = raw["height"]
            containers = _containers(spec, nodes, raw["boxes"], typography["body_px"])
        if contract.get("scene_id") == "detail" and len(containers) == 1:
            container = containers[0]
            owner = container["source_group"]
            required = [*spec.get("verbatim_labels", []), *figure.get("required_verbatim_labels", [])]
            if figure.get("main_group") == owner and all(n.get("original_group") == owner for n in nodes) and not any(literal and literal in container["label"] for literal in required):
                container["render_boundary"] = False
                container["boundary_reason"] = "All displayed resources belong to the named exact scope; caption carries its single owner and leaves feedback lanes unobstructed"
        if grammar == "control-band":
            # Legacy routing reserves 20px headings.  New publication headings
            # are larger and must be measured before short-drop corridors.
            face = publication_render.font(typography["body_px"])
            for container in containers:
                b = container["box"]
                title_box = (b["x"] + 14, b["y"] - typography["body_px"] * 1.2,
                             b["x"] + 14 + face.getlength(container["label"]), b["y"])
                for edge in raw["edges"]:
                    if edge["kind"] != "control":
                        continue
                    target = raw["boxes"][edge["target"]]
                    source = raw["boxes"][edge["source"]]
                    center = target["x"] + target["width"] / 2
                    if publication_render._wire_crosses_rect((center, source["y"] + source["height"]), (center, target["y"]), title_box, 6):
                        if any(literal and literal in container["label"] for literal in [*spec.get("verbatim_labels", []), *figure.get("required_verbatim_labels", [])]):
                            failure = "A required scope name conflicts with the control drop corridor"
                        else:
                            container["render_boundary"] = False
                            container["boundary_reason"] = "Scope heading is retained in caption to keep independent control drops readable"
            if failure:
                diagnostics.append({"id": candidate_id, "accepted": False, "reasons": [failure]})
                continue
        plan = {"type": "publication", "version": "CPS6", "abstract": True, "view_type": "publication-" + grammar,
                "view_role": figure.get("view_role"), "title": figure["title"],
                "macro_nodes": copy.deepcopy(raw.get("display_nodes", nodes)), "macro_edges": raw["edges"],
                "boxes": {nid: _normal(box, height) for nid, box in raw["boxes"].items()},
                "containers": [{**c, "box": _normal(c["box"], height)} for c in containers],
                "system_frame": {"box": _box(0, 0, 1, 1), "label": "", "display_only": True},
                "canvas": {"coordinate_system": "normalized", "natural_aspect": round(WIDTH / height, 6),
                           "reading_direction": raw["orientation"], "target_width_mm": target_width},
                "typography": typography, "symbol_metrics": raw["metrics"], "candidate_id": candidate_id,
                "source_ownership": {n["id"]: n.get("group", "") for n in spec["nodes"]},
                "source_group_parents": {g["id"]: g.get("parent", "") for g in spec.get("groups", [])},
                "source_group_labels": {g["id"]: g["label"] for g in spec.get("groups", [])},
                "node_to_macro": copy.deepcopy(figure.get("projection", {}).get("source_node_to_macro", {})),
                "source_edge_indices": list(figure.get("source_edge_indices", figure.get("edge_indices", []))),
                "projection": copy.deepcopy(figure.get("projection", {})),
                "insets": [{**inset, "box": _normal(inset["box"], height),
                            "leader": [[round(x / WIDTH, 6), round(y / height, 6)] for x, y in inset["leader_pixels"]]}
                           for inset in raw["insets"]]}
        scene = structure_scene.prepare(plan)
        _detail_context_scene(scene, plan)
        for route in scene["routes"]:
            lane = raw.get("owner_return_lanes", {}).get(route["id"])
            if lane is not None:
                start, end = route["points"][0], route["points"][-1]
                route["points"] = [start, [lane, start[1]], [lane, end[1]], end]
        plan["scene_id"] = contract.get("scene_id", "")
        if raw.get("presentation_frame"):
            plan["presentation_frame"] = {**raw["presentation_frame"], "box": _normal(raw["presentation_frame"]["box"], height)}
        if grammar == "control-band" or raw["orientation"] == "controller-band":
            _control_feedback_scene(scene, plan)
        elif raw["orientation"] == "existing-data-hub-with-owned-subsystems":
            _ownership_hub_scene(scene, plan)
        elif raw["orientation"] == "existing-owned-join":
            _owned_join_scene(scene, plan)
        for route in scene["routes"]:
            route["points"] = structure_scene.compact_path(route["points"], 1e-6)
        scope_quality = owner_scope_quality(plan, scene)
        scene["quality"]["owner_scope_entries"] = scope_quality
        if not scope_quality["clear"]:
            diagnostics.append({"id": candidate_id, "accepted": False, "reasons": ["A scope relationship visually selects an inventory child"],
                                "owner_scope_entries": scope_quality})
            continue
        trace_contacts = organization_trace_quality(plan, scene)
        scene["quality"]["organization_traces"] = trace_contacts
        if not trace_contacts["clear"]:
            diagnostics.append({"id": candidate_id, "accepted": False, "reasons": ["Independent organization relationships touch or cross"],
                                "organization_traces": trace_contacts})
            continue
        scene["quality"].update(body_font_pt=body_pt, signal_font_pt=signal_pt, target_width_mm=target_width,
                                publication_typography=True, geometry_is_not_raster_acceptance=True)
        if not scene["quality"]["routes_complete"]:
            diagnostics.append({"id": candidate_id, "accepted": False, "reasons": ["A canonical display relationship has no unobstructed route"], "failed_routes": scene["quality"]["failed_routes"]})
            continue
        trace_quality = input_trace_quality(plan, scene)
        scene["quality"]["input_traces"] = trace_quality
        if not trace_quality["clear"]:
            diagnostics.append({"id": candidate_id, "accepted": False,
                                "reasons": ["Common-owner input paths are ambiguous at the document target size"],
                                "input_traces": trace_quality})
            continue
        plan["layout_scene"] = scene
        provisional = {**figure, "structure_layout": plan, "layout_scene": scene}
        labels = publication_render.render({"spec": spec}, provisional, labels_only=True)
        if labels is None:
            diagnostics.append({"id": candidate_id, "accepted": False, "reasons": ["Endpoint, boundary title, or typography preflight failed"]})
            continue
        boundary_conflicts = _boundary_conflicts(scene, plan["containers"], max(20, typography["signal_px"] / 2))
        if boundary_conflicts:
            diagnostics.append({"id": candidate_id, "accepted": False, "reasons": ["A relationship tracks a scope boundary and could be mistaken for its outline"],
                                "boundary_conflicts": boundary_conflicts})
            continue
        metrics = _route_metrics(scene)
        metrics["routing_cost_px"] = round(metrics["total_route_px"] + 16 * metrics["bends"], 1)
        if metrics["crossings"]:
            diagnostics.append({"id": candidate_id, "accepted": False, "reasons": ["Independent routes cross without a declared crossover symbol"],
                                "geometry": metrics})
            continue
        diagnostics.append({"id": candidate_id, "accepted": True, "reasons": [], "geometry": metrics,
                            "deferred_label_count": len(labels["deferred_labels"]), "natural_aspect": plan["canvas"]["natural_aspect"],
                            "document_height_mm": round(target_width / plan["canvas"]["natural_aspect"], 1)})
        if grammar == "ownership-flow":
            candidates.append((metrics["crossings"], height, len(labels["deferred_labels"]), metrics["routing_cost_px"], metrics["bends"], metrics["longest_route_px"], plan, labels))
        else:
            candidates.append((metrics["crossings"], len(labels["deferred_labels"]), metrics["routing_cost_px"], metrics["bends"], metrics["longest_route_px"], height, plan, labels))
    figure["composition_diagnostics"] = {"grammar": grammar, "candidates": diagnostics,
                                           "selection_policy": "Hard route/typography/crossover/boundary gates, then document height before optional prose and length plus 16px per bend for subsystem organization; no beauty score" if grammar == "ownership-flow" else "Hard route/typography/crossover/boundary gates, then fewer deferred labels, total route length plus 16px per bend, fewer bends and shorter longest route; no beauty score"}
    if not candidates:
        return None
    selected = min(candidates, key=lambda row: row[:6])
    plan, labels = selected[-2:]
    if grammar in {"ownership-flow", "resource-array"}:
        document_height = target_width / plan["canvas"]["natural_aspect"]
        portrait = settings.get("aspect") in {"portrait", "3:4", "9:16", "A4"}
        plan["layout_scene"]["quality"]["document_fit"] = {"height_mm": round(document_height, 1), "default_limit_mm": 140,
                                                              "status": "pass" if portrait or document_height <= 140 else "limited",
                                                              "no_font_shrink": True,
                                                              "meaning": "Native source routing and typography do not certify a tall figure as publication-ready."}
    plan["composition_diagnostics"] = copy.deepcopy(figure["composition_diagnostics"])
    plan["composition_diagnostics"]["selected"] = plan["candidate_id"]
    figure["layout_scene"] = plan["layout_scene"]
    figure["label_layout"] = labels
    return plan
