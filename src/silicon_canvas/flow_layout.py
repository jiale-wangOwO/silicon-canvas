"""Exact graph-led datapath geometry for Image Gen layout references.

The graph, kinds and source containment determine placement. Names size labels
but never select hardware roles. Every visible source object appears once and
every edge keeps its original index, including parallel and returning streams.
This module supplies geometry only; it does not draw the final diagram.
"""
from collections import Counter, defaultdict


SUPPORTED = {"architecture", "dataflow", "microarchitecture", "pipeline", "memory"}
PERIPHERAL_KINDS = {"control", "feedback", "clock"}


def _box(x, y, width, height):
    return {"x": x, "y": y, "width": width, "height": height}


def _union(boxes, pad=.7, heading=1.3):
    left = min(b["x"] for b in boxes) - pad
    top = min(b["y"] for b in boxes) - pad - heading
    right = max(b["x"] + b["width"] for b in boxes) + pad
    bottom = max(b["y"] + b["height"] for b in boxes) + pad
    return _box(left, top, right - left, bottom - top)


def _overlaps(a, b):
    return (a["x"] < b["x"] + b["width"] and b["x"] < a["x"] + a["width"]
            and a["y"] < b["y"] + b["height"] and b["y"] < a["y"] + a["height"])


def _normalize(box, width, height):
    return {key: round(value / (width if key in {"x", "width"} else height), 6)
            for key, value in box.items()}


def _ancestors(gid, groups):
    path = []
    while gid:
        if gid not in groups or gid in path:
            raise ValueError("Invalid or cyclic source containment.")
        path.append(gid)
        gid = groups[gid].get("parent", "")
    return path


def _dimensions(node):
    # Broad visual families, not a brand/name lookup or invented memory banks.
    units = sum(1 if ord(char) > 255 else .56 for char in node["label"])
    width = max(4.5, units + 1.7)
    kind = node["kind"]
    if kind == "memory":
        return max(6.8, width), 1.9, "storage-bar"
    if kind in {"control", "signal", "event"}:
        return width, 2.1, "control-block"
    if kind == "io":
        return width, 2.3, "interface-block"
    return width, 2.6, "functional-block"


def _forward_order(ids, edges, source_order):
    """Stable dependency order; cut only cycle-closing dependencies for layout.

    A cut changes no edge semantics: it simply reserves an outer return lane.
    The source ordering resolves a fully cyclic component, never label sorting.
    """
    incoming, outgoing = defaultdict(set), defaultdict(set)
    for index, edge in edges:
        a, b = edge["source"], edge["target"]
        if a != b:
            outgoing[a].add(b)
            incoming[b].add(a)
    remaining, ordered = set(ids), []
    while remaining:
        ready = [nid for nid in ids if nid in remaining and not (incoming[nid] & remaining)]
        if not ready:
            ready = [min(remaining, key=source_order.get)]
        for nid in ready:
            remaining.remove(nid)
            ordered.append(nid)
    position = {nid: index for index, nid in enumerate(ordered)}
    forward = [(index, edge) for index, edge in edges
               if position[edge["source"]] < position[edge["target"]]]
    ranks = {nid: 0 for nid in ids}
    next_nodes = defaultdict(list)
    for _, edge in forward:
        next_nodes[edge["source"]].append(edge["target"])
    for nid in ordered:
        for target in next_nodes[nid]:
            ranks[target] = max(ranks[target], ranks[nid] + 1)
    return ordered, ranks, forward


def _compact(nodes, preferred, dimensions, gap=1.8, before=None):
    """Least-squares nonoverlapping placement in a fixed branch order."""
    offsets, cursor = {}, 0
    previous = None
    for nid in nodes:
        if previous is not None:
            cursor += (dimensions[previous][1] + dimensions[nid][1]) / 2 + gap + (before or {}).get(nid, 0)
        offsets[nid] = cursor
        previous = nid
    pools = []
    for nid in nodes:
        pools.append(([nid], preferred[nid] - offsets[nid]))
        while len(pools) > 1 and pools[-2][1] > pools[-1][1]:
            right, rv = pools.pop()
            left, lv = pools.pop()
            pools.append((left + right, (lv * len(left) + rv * len(right)) / (len(left) + len(right))))
    return {nid: mean + offsets[nid] for members, mean in pools for nid in members}


def build(spec, figure, language="en"):
    """Return a scene-compatible exact flow plan, or None for another grammar.

    Input is the same normalized semantic spec and exact figure projection used
    by private_layout.build_detail. Nodes, labels, groups and directed edges are
    never inferred. Invalid source projections raise ValueError; unsupported
    categories and abstract views fall back. A control-only dependency graph
    is eligible only when the caller explicitly selects view_role="control".
    """
    if spec.get("category") not in SUPPORTED or figure.get("abstract"):
        return None
    source_nodes = spec.get("nodes", [])
    source = {node["id"]: node for node in source_nodes}
    groups = {group["id"]: group for group in spec.get("groups", [])}
    ids = list(figure.get("node_ids", []))
    indices = list(figure.get("edge_indices", []))
    if len(ids) != len(set(ids)) or any(nid not in source for nid in ids):
        raise ValueError("Flow view must reference unique supplied nodes.")
    if len(indices) != len(set(indices)) or any(not isinstance(i, int) or isinstance(i, bool) or not 0 <= i < len(spec.get("edges", [])) for i in indices):
        raise ValueError("Flow view edge indices are invalid.")
    edges = [(i, spec["edges"][i]) for i in indices]
    if any(edge["source"] not in ids or edge["target"] not in ids for _, edge in edges):
        raise ValueError("Flow edge endpoints must be visible in this view.")
    paths = {nid: _ancestors(source[nid].get("group", ""), groups) for nid in ids}
    for gid in groups:
        _ancestors(gid, groups)
    # A dependency relation supports ordering without claiming a data bus.
    dependencies = [(index, edge) for index, edge in edges if edge["kind"] in {"data", "relation"}]
    control_view = figure.get("view_role") == "control" and not dependencies
    if control_view:
        dependencies = [(index, edge) for index, edge in edges if edge["kind"] == "control"]
    connected = {nid for _, edge in dependencies for nid in (edge["source"], edge["target"])}
    if len(connected) < 2 or not any(edge["source"] != edge["target"] for _, edge in dependencies):
        return None
    source_order = {node["id"]: index for index, node in enumerate(source_nodes)}
    active = [node["id"] for node in source_nodes if node["id"] in connected]
    ordered, ranks, forward = _forward_order(active, dependencies, source_order)
    forward_indices = {index for index, _ in forward}
    predecessors = defaultdict(list)
    for _, edge in forward:
        if edge["source"] not in predecessors[edge["target"]]:
            predecessors[edge["target"]].append(edge["source"])
    feedback_sources = []
    if control_view:
        # Completion-only resources belong on the consumer side but are not
        # command targets. These are placement anchors, never added edges.
        for node in source_nodes:
            nid = node["id"]
            if nid not in ids or nid in connected:
                continue
            peers = [edge["target"] for _, edge in edges
                     if edge["source"] == nid and edge["kind"] == "feedback" and edge["target"] in ranks]
            if peers:
                ranks[nid] = max(ranks[peer] for peer in peers) + 1
                predecessors[nid] = list(dict.fromkeys(peers))
                feedback_sources.append(nid)
                connected.add(nid)
                active.append(nid)
                ordered.append(nid)
    dimensions = {nid: _dimensions(source[nid]) for nid in ids}
    if control_view:
        output_counts = Counter(edge["source"] for _, edge in forward)
        for nid, count in output_counts.items():
            width, height, role = dimensions[nid]
            dimensions[nid] = (width, max(height, (count + 1) * .5), role)
    layers = defaultdict(list)
    for nid in ordered:
        layers[ranks[nid]].append(nid)
    centers = {}
    root_nodes = layers[0]
    root_nodes.sort(key=source_order.get)
    root_pitch=4.7 if control_view else max(dimensions[nid][1] for nid in active)+2.6
    preferred = {nid: index * root_pitch for index, nid in enumerate(root_nodes)}
    lane_gap=1.8 if control_view else 2.6
    centers.update(_compact(root_nodes, preferred, dimensions,gap=lane_gap))
    layer_order = {}
    group_first = {gid: min(source_order[nid] for nid in ids if gid in paths[nid])
                   for gid in groups if any(gid in paths[nid] for nid in ids)}
    for rank in sorted(layers):
        current = layers[rank]
        targets = {nid: sum(centers[p] for p in predecessors[nid]) / len(predecessors[nid])
                   if predecessors[nid] else centers[nid] for nid in current}
        if control_view:
            current.sort(key=lambda nid: (targets[nid], nid in feedback_sources,
                                          tuple(group_first[gid] for gid in reversed(paths[nid])) + (source_order[nid],)))
        else:
            current.sort(key=lambda nid: (targets[nid], source_order[nid]))
        before = {}
        if control_view:
            # A newly entered real scope needs a title band above its first
            # resource. This is empty geometry, not an added control endpoint.
            for previous, nid in zip(current, current[1:]):
                entered = [gid for gid in paths[nid] if gid not in paths[previous]]
                if any(sum(gid in paths[peer] for peer in ids) > 1 or
                       groups[gid]["label"].strip() != source[nid]["label"].strip() for gid in entered):
                    before[nid] = 1.8
        centers.update(_compact(current, targets, dimensions,gap=lane_gap,before=before))
        layer_order[rank] = list(current)
    widths = {rank: max(dimensions[nid][0] for nid in nodes) for rank, nodes in layers.items()}
    rank_x, cursor = {}, 0
    for rank in sorted(layers):
        rank_x[rank] = cursor
        cursor += widths[rank] + 2.5
    boxes = {}
    for nid in active:
        width, height, _ = dimensions[nid]
        boxes[nid] = _box(rank_x[ranks[nid]] + (widths[ranks[nid]] - width) / 2,
                          centers[nid] - height / 2, width, height)
    # Non-data controls occupy an upper band. An unconnected nested resource
    # instead stays next to its actual group's datapath; lack of edges does not
    # turn a compute block into a controller or imply a new connection.
    top = min(box["y"] for box in boxes.values())
    peripheral = [node["id"] for node in source_nodes if node["id"] in ids and node["id"] not in connected]
    peer_map = defaultdict(set)
    for _, edge in edges:
        peer_map[edge["source"]].add(edge["target"])
        peer_map[edge["target"]].add(edge["source"])
    placed = []
    peripheral_controls, ancillary = [], []
    for nid in peripheral:
        incident = [edge for _, edge in edges if nid in {edge["source"], edge["target"]}]
        is_control = source[nid]["kind"] in {"control", "signal", "event"} or (incident and all(edge["kind"] in PERIPHERAL_KINDS for edge in incident))
        if not is_control:
            ancillary.append(nid)
            continue
        peripheral_controls.append(nid)
        peers = [peer for peer in peer_map[nid] if peer in ranks]
        rank = round(sum(ranks[peer] for peer in peers) / len(peers)) if peers else 0
        width, height, _ = dimensions[nid]
        x = rank_x[rank] + widths[rank] / 2 - width / 2
        row = 0
        while any(level == row and x < previous_x + previous_width + 2 and x + width + 2 > previous_x
                  for level, previous_x, previous_width in placed):
            row += 1
        placed.append((row, x, width))
        boxes[nid] = _box(x, top - 1.8 - row * 4.3 - height, width, height)
    # Wide control blocks must also clear unrelated ownership captions. Those
    # headings live above scope borders, outside the actual resource boxes;
    # ignoring them can hide a Host/Frontend title behind a scheduler block.
    for nid in peripheral_controls:
        for gid, group in groups.items():
            members = [peer for peer in active if gid in paths[peer]]
            if not members or gid in paths[nid]:
                continue
            full_members = [node["id"] for node in source_nodes if gid in _ancestors(node.get("group", ""), groups)]
            if len(full_members) == 1 and group["label"].strip() == source[full_members[0]]["label"].strip():
                continue
            depth = len(_ancestors(gid, groups))
            scope = _union([boxes[peer] for peer in members], .6 + .2 / depth, .9 + .3 / depth)
            heading = _box(scope["x"], scope["y"] - 1.2, scope["width"], 1.2)
            if _overlaps(boxes[nid], heading):
                boxes[nid]["y"] = heading["y"] - boxes[nid]["height"] - .6
        while any(_overlaps(_union([boxes[nid]], .3, 0), boxes[other]) for other in peripheral_controls if other != nid):
            boxes[nid]["y"] -= boxes[nid]["height"] + 1.6
    for nid in ancillary:
        peers = []
        for gid in paths[nid]:
            peers = [peer for peer in active if gid in paths[peer]]
            if peers:
                break
        width, height, _ = dimensions[nid]
        near = [boxes[peer] for peer in peers] or list(boxes.values())
        x = sum(box["x"] + box["width"] / 2 for box in near) / len(near) - width / 2
        y = max(box["y"] + box["height"] for box in near) + 1.6
        candidate = _box(x, y, width, height)
        while any(_overlaps(_union([candidate], .6, 0), box) for box in boxes.values()):
            candidate["y"] += height + 1.6
        boxes[nid] = candidate
    owner = figure.get("main_group")
    owner = owner if owner in groups else None
    owned = [nid for nid in ids if owner and owner in paths[nid]]
    context = [nid for nid in ids if owner and nid not in owned]
    # A context object can share a stage with an owned object but may never be
    # pulled inside the real owner boundary for geometric convenience.
    if owned:
        owner_bounds = _union([boxes[nid] for nid in owned], 1, 1.5)
        context_floor = owner_bounds["y"] - 3
        for nid in context:
            if _overlaps(owner_bounds, boxes[nid]):
                boxes[nid]["y"] = context_floor - boxes[nid]["height"]
                context_floor = boxes[nid]["y"] - 3
    else:
        owner = None
    # Source containers are rectangular where possible. A disconnected scope
    # is represented by explicit continuation segments rather than enclosing
    # somebody else's resources. Segments are display boundaries, never nodes.
    raw_containers = []
    warnings = []
    for gid, group in groups.items():
        members = [nid for nid in ids if gid in paths[nid]]
        if not members:
            continue
        full_members = [node["id"] for node in source_nodes if gid in _ancestors(node.get("group", ""), groups)]
        single_named_resource = (len(full_members) == 1 and full_members == members
                                 and group["label"].strip() == source[members[0]]["label"].strip())
        depth = len(_ancestors(gid, groups))
        bounds = _union([boxes[nid] for nid in members], .6 + .2 / depth, .9 + .3 / depth)
        outsiders = [boxes[nid] for nid in ids if nid not in members]
        chunks = [members]
        if any(_overlaps(bounds, box) for box in outsiders):
            # Keep successive same-rank members together only when the union
            # does not pass through an unrelated node's actual footprint.
            chunks = []
            for nid in sorted(members, key=lambda n: (boxes[n]["x"], boxes[n]["y"])):
                candidate = next((chunk for chunk in reversed(chunks)
                                  if abs(boxes[chunk[0]]["x"] - boxes[nid]["x"]) < .01
                                  and not any(_overlaps(_union([boxes[n] for n in [*chunk, nid]], .55, 1.1), other) for other in outsiders)), None)
                if candidate is None:
                    chunks.append([nid])
                else:
                    candidate.append(nid)
            warnings.append("Source scope " + gid + " uses continuation segments; source ownership is unchanged.")
        for part, chunk in enumerate(chunks):
            raw_containers.append({"id": gid if len(chunks) == 1 else "@scope:" + gid + ":" + str(part + 1),
                                   "label": group["label"], "parent": group.get("parent", ""),
                                   "source_group": gid, "source_members": chunk, "members": chunk,
                                   "scope_source_members": members, "ownership_unchanged": True,
                                   "replaces_region": gid if single_named_resource else None,
                                   "continuation_of": gid if len(chunks) > 1 else None,
                                   "box": bounds if len(chunks) == 1 else _union([boxes[nid] for nid in chunk], .55, 1.1)})
    roots = [gid for gid, group in groups.items() if not group.get("parent") and all(gid in paths[nid] for nid in ids)]
    boundary_owner = owner or (roots[0] if len(roots) == 1 else None)
    frame_nodes = owned if owner else ids
    # Leave separate room for the outer title and the first source scope's
    # heading; both are rendered by structure_scene at a fixed font size.
    frame_box = _union([boxes[nid] for nid in frame_nodes], 1.2, 3.8 if raw_containers else 2.1)
    if owner:
        # Owner geometry was already reserved before positioning its context.
        frame_box = owner_bounds
    frame = {"id": boundary_owner or "@flow", "label": groups[boundary_owner]["label"] if boundary_owner else figure.get("title", spec.get("title", "")),
             "box": frame_box, "source_group": boundary_owner, "display_only": boundary_owner is None,
             "not_an_added_hardware_node": True, "replaces_container": boundary_owner}
    for container in raw_containers:
        if container["source_group"] == boundary_owner:
            container["is_system_boundary"] = True
            container["box"] = dict(frame_box)
    # Reserve real clear margins for outer control/return routing. A corridor
    # is geometry metadata, not an implicit shared bus or an extra port.
    all_bounds = _union([*boxes.values(), frame_box, *(cap["box"] for cap in raw_containers)], 0, 0)
    margin = 1.5
    width = all_bounds["width"] + 2 * margin
    # Short chains otherwise scale every box to 4--5 label heights when the
    # shared renderer expands them to 1800 px. Compress only the vertical
    # coordinate system so short and long views retain similar label-sized
    # symbols; preserve horizontal label capacity and branch alignment.
    vertical_scale = min(1, width / 68)
    units_per_vertical_pixel = width / (1800 * vertical_scale)
    # Corridors run outside actual circuit symbols, not outside the complete
    # title/frame envelope. Track pitch is at least 13 px at the renderer's
    # reference width; many real control edges legitimately need more space.
    def route_family(index, edge):
        if control_view:
            if index in forward_indices:
                return "control-forward"
            if edge["kind"] in {"control", "feedback"}:
                return "return"
        if edge["kind"] in PERIPHERAL_KINDS:
            return "control"
        return "forward" if index in forward_indices else "return"

    families = {index: route_family(index, edge) for index, edge in edges}
    control_count = sum(family == "control" for family in families.values())
    return_count = sum(family == "return" for family in families.values())
    control_height = max(.7, control_count * 13 * units_per_vertical_pixel)
    return_height = max(.7, return_count * 13 * units_per_vertical_pixel)
    outer_top = min(box["y"] for box in boxes.values()) - 1 - control_height
    outer_bottom = all_bounds["y"] + all_bounds["height"] + 13 * units_per_vertical_pixel
    corridor_boxes = {
        "control-outer": _box(all_bounds["x"], outer_top, all_bounds["width"], control_height),
        "return-outer": _box(all_bounds["x"], outer_bottom, all_bounds["width"], return_height),
    }
    offset_x = margin - all_bounds["x"]
    offset_y = margin - min(all_bounds["y"], outer_top if control_count else all_bounds["y"])
    bottom = max(all_bounds["y"] + all_bounds["height"], outer_bottom + return_height if return_count else all_bounds["y"] + all_bounds["height"])
    height = bottom + offset_y + margin

    def normalized(box):
        return _normalize(_box(box["x"] + offset_x, box["y"] + offset_y, box["width"], box["height"]), width, height)

    normalized_boxes = {nid: normalized(boxes[nid]) for nid in ids}
    frame["box"] = normalized(frame["box"])
    containers = [{**container, "box": normalized(container["box"])} for container in raw_containers]
    macro_nodes = [{"id": nid, "label": source[nid]["label"], "kind": source[nid]["kind"], "type": "resource",
                    "detail": source[nid].get("detail", ""), "members": [nid], "source_node_index": source_order[nid],
                    "source_group": source[nid].get("group", ""), "source_owner": source[nid].get("group", ""),
                    "source_ancestry": paths[nid], "context": nid in context,
                    "box": normalized_boxes[nid], "slot_box": dict(normalized_boxes[nid]),
                    "zone": "context" if nid in context else "feedback-source" if nid in feedback_sources else "flow" if nid in connected else "control" if nid in peripheral_controls else "ancillary",
                    "visual_role": dimensions[nid][2], "stage_rank": ranks.get(nid),
                    "not_a_new_hardware_instance": True} for nid in ids]
    links, track_counts = [], Counter()
    for index, edge in edges:
        a, b = edge["source"], edge["target"]
        family = families[index]
        control = family == "control"
        returning = family == "return"
        corridor = "control-outer" if control else "return-outer" if returning else "forward-stage-" + str(ranks[a])
        side = "top" if control else "bottom" if returning else None
        link = {"id": "E" + str(index + 1), "source": a, "target": b,
                "kind": edge["kind"], "label": edge.get("label", ""), "members": [index], "source_edge_index": index,
                "source_nodes": [a], "target_nodes": [b], "family": family,
                "routing": {"corridor": corridor, "track": track_counts[corridor],
                            "source_side": side or "right", "target_side": side or "left",
                            "obstacle_aware_routing_required": True, "no_broadcast_bus_is_inferred": True,
                            "outer_route": control or returning}}
        if side:
            target_y = outer_top + control_height / 2 if control else outer_bottom + return_height / 2
            link["routing"]["waypoint_axis"] = "y"
            link["routing"]["waypoint_value"] = round((target_y + offset_y) / height, 6)
        track_counts[corridor] += 1
        links.append(link)
    for link in links:
        routing = link["routing"]
        routing["track_fraction"] = (routing["track"] + .5) / track_counts[routing["corridor"]]
        if routing["outer_route"]:
            corridor = corridor_boxes[routing["corridor"]]
            routing["waypoint_value"] = round((corridor["y"] + corridor["height"] * routing["track_fraction"] + offset_y) / height, 6)
    lanes = [{"id": "stage-" + str(rank), "role": "control-dependency" if control_view else "data-stage", "rank": rank,
              "members": layer_order[rank], "box": normalized(_union([boxes[nid] for nid in layer_order[rank]], .3, 0)),
              "display_only": True, "not_a_cycle_or_pipeline_stage_claim": True} for rank in sorted(layers)]
    if peripheral_controls:
        lanes.insert(0, {"id": "peripheral-control", "role": "peripheral-control", "members": peripheral_controls,
                         "box": normalized(_union([boxes[nid] for nid in peripheral_controls], .3, 0)), "display_only": True})
    if ancillary:
        lanes.append({"id": "nested-resources", "role": "nested-resource", "members": ancillary,
                      "box": normalized(_union([boxes[nid] for nid in ancillary], .3, 0)), "display_only": True})
    covered = [index for link in links for index in link["members"]]
    return {"type": "directed_flow", "view_type": "graph-led-control" if control_view else "graph-led-datapath", "abstract": False,
            "flow_basis": "control" if control_view else "data", "feedback_source_nodes": feedback_sources,
            "title": figure.get("title", spec.get("title", "")), "main_group": owner,
            "macro_nodes": macro_nodes, "macro_edges": links, "projected_links": links,
            "deferred_links": [], "internal_edges": [], "node_ids": ids, "edge_indices": indices,
            "boxes": normalized_boxes, "slot_boxes": {nid: dict(box) for nid, box in normalized_boxes.items()},
            "containers": containers, "system_frame": frame, "role_lanes": lanes,
            "region_slots": [], "component_lanes": [], "repeat_families": [],
            "source_ownership": {nid: source[nid].get("group", "") for nid in ids},
            "node_to_macro": {nid: nid for nid in ids}, "context_nodes": context,
            "source_nested_groups": [gid for gid in groups if owner and gid != owner and owner in _ancestors(gid, groups)],
            "scope_owner_nodes": [node["id"] for node in source_nodes if owner and owner in _ancestors(node.get("group", ""), groups)],
            "flow_ranks": ranks, "forward_edge_indices": [index for index, _ in forward],
            "return_edge_indices": [index for index in indices if families[index] == "return"],
            "routing_corridors": [{"id": cid, "box": normalized(box), "axis": "horizontal", "track_count": track_counts[cid],
                                   "routing_is_not_a_hardware_bus": True} for cid, box in corridor_boxes.items() if track_counts[cid]],
            "canvas": {"coordinate_system": "normalized", "natural_aspect": round(width / (height * vertical_scale), 3),
                       "label_unit_pixels": round(1800 / width, 6), "reading_direction": "left-to-right"},
            "coverage": {"source_nodes": len(ids), "source_edges": len(indices), "nodes_projected": len(ids),
                         "missing_nodes": [], "missing_edges": sorted(set(indices) - set(covered)),
                         "duplicate_edge_indices": sorted(index for index, count in Counter(covered).items() if count > 1)},
            "warnings": warnings + ["Dependency ranks are geometric positions, not clock cycles. Outer return routes retain their original kind and direction.",
                                     "Source containment and context ownership are unchanged; no node, bus, port, parameter or hardware copy is introduced."]}
