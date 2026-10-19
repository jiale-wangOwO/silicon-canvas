"""Containment-led system overview geometry; never new hardware facts.

Coordinates are normalized to [0, 1]. A collapsed template is a visual
reference to supplied internals, not additional semantic nodes or edges.
The original ownership and every projected relation remain auditable.
"""
from collections import Counter, defaultdict
import copy
import json
import math
import re


STRUCTURE_CATEGORIES = {"architecture", "microarchitecture", "memory"}
_SAME = re.compile(r"same\s+(?:private\s+)?resources\s+(?:as|of)\s+([\w-]+)", re.I)
_EXTERNAL = re.compile(r"external|off[- ]chip|outside|片外|外部", re.I)
_PRIVATE = re.compile(r"private|\blocal\b|私有|本地", re.I)
_SHARED = re.compile(r"shared|共享|inter[- ](?:pe|core)|\bfabric\b", re.I)


def _box(x, y, width, height):
    return {"x": x, "y": y, "width": width, "height": height}


def _union(boxes, pad=0):
    x = min(b["x"] for b in boxes) - pad
    y = min(b["y"] for b in boxes) - pad
    right = max(b["x"] + b["width"] for b in boxes) + pad
    bottom = max(b["y"] + b["height"] for b in boxes) + pad
    return _box(x, y, right - x, bottom - y)


def _normal(box, width, height):
    return {"x": round(box["x"] / width, 6), "y": round(box["y"] / height, 6),
            "width": round(box["width"] / width, 6), "height": round(box["height"] / height, 6)}


def _ancestors(gid, groups):
    seen = set()
    while gid:
        if gid not in groups or gid in seen:
            raise ValueError("Invalid or cyclic source containment.")
        seen.add(gid)
        yield gid
        gid = groups[gid].get("parent", "")


def _template_slots(members, edges=()):
    """All template members, in role lanes; no arbitrary two-label captions."""
    roles = {"control": 0, "stage": 0, "compute": 1, "io": 1, "memory": 2}
    lanes = defaultdict(list)
    member_ids = {node["id"] for node in members}
    internal = [edge for edge in edges if edge["source"] in member_ids and edge["target"] in member_ids]
    incoming = Counter(edge["target"] for edge in internal)
    degree = Counter(endpoint for edge in internal for endpoint in (edge["source"], edge["target"]))
    for node in members:
        lanes[roles.get(node["kind"], 1)].append(node)
    entry = next((n for n in lanes[0] if not incoming[n["id"]] and degree[n["id"]]), None)
    local_store = max(lanes[2], key=lambda n: degree[n["id"]], default=None)
    if local_store and degree[local_store["id"]] < 3:
        local_store = None
    arranged = []
    if entry:
        arranged.append((0, [entry]))
    for role in sorted(lanes):
        rest = [n for n in lanes[role] if n is not entry and n is not local_store]
        arranged.extend((role, rest[i:i + 2]) for i in range(0, len(rest), 2))
    if local_store:
        arranged.append((2, [local_store]))
    rows = len(arranged)
    slots = []
    for row, (role, row_nodes) in enumerate(arranged):
        for index, node in enumerate(row_nodes):
            slots.append({"source_node_id": node["id"], "label": node["label"],
                          "kind": node["kind"], "source_group": node.get("group", ""),
                          "role_lane": ("control", "execution", "local_storage")[role],
                          "box": _box(.04 + index * .48, .14 + row * .83 / rows,
                                      .92 if len(row_nodes) == 1 else .44, .70 / rows)})
    return slots


def _reference_group(token, groups):
    for gid, group in groups.items():
        if gid.casefold() == token.casefold() or re.search(r"(?<!\w)" + re.escape(token) + r"(?!\w)", group["label"], re.I):
            return gid
    return None


def _instance_slots(slots, template, inherited):
    result = copy.deepcopy(slots)
    for slot in result:
        slot["source_label"] = slot["label"]
        slot["visual_reference_only"] = inherited
        # In a PE1 replica, "PE0 Local RF" is a template source reference,
        # not the name of another real PE0 resource inside PE1.
        slot["display_label"] = re.sub(r"(?<!\w)" + re.escape(template) + r"(?!\w)\s*", "", slot["label"], flags=re.I).strip() if inherited else slot["label"]
    return result


def _instance_name(group):
    """Recognize an instance suffix without prescribing a vendor vocabulary."""
    # A level, memory standard or arithmetic precision is a technical role,
    # not an instance identifier (L2 vs L3, FP32 vs FP64, and similar labels).
    if re.match(r"^(?:L\d+|DDR\d+|HBM\d+|(?:U?INT|FP|BF|TF)\d+)\b", group["label"], re.I):
        return None
    match = re.match(r"^(.*?\D)(\d+)(?=$|[\s_—–-])", group["label"])
    if match:
        return match.group(1).strip(" _-"), match.group(2), match.group(0).strip()
    # Named peers can use letters or Chinese ordinal identifiers. Only the
    # actual owner token is normalized; semantic child words are untouched.
    match = re.match(r"^(.*?)([甲乙丙丁戊己庚辛壬癸])(?=$|[\s_—–-])", group["label"])
    if not match:
        match = re.match(r"^(.+?)[ _-]([A-Zα-ω])(?=$|[\s_—–-])", group["label"])
    return (match.group(1).strip(" _-"), None, match.group(0).strip()) if match else None


def _inventory_signature(gid, groups, descendant_members, edges):
    """Prove equality of supplied internals, including quantities and topology.

    Source IDs and provenance may differ. Technical text may not: only the
    named instance token and a matching separated label suffix are normalized.
    Ambiguous duplicate resource identities do not establish equivalence.
    """
    identity = _instance_name(groups[gid])
    _, ordinal, token = identity if identity else ("", None, groups[gid]["label"])
    def text(value, identity_label=False):
        if identity_label:
            for prefix in [groups[gid]["label"], token, gid]:
                if value.startswith(prefix):
                    value = "<instance>" + value[len(prefix):]
                    break
        value = re.sub(r"(?<!\w)" + re.escape(token) + r"(?!\w)", "<instance>", value)
        value = re.sub(r"(?<!\w)" + re.escape(gid) + r"(?!\w)", "<instance>", value)
        return (re.sub(r"(?<=\s)" + re.escape(ordinal) + r"$", "<instance>", value)
                if ordinal is not None and identity_label else value).strip()
    def normalized(value, identity_label=False):
        if isinstance(value, str):
            return text(value, identity_label)
        if isinstance(value, list):
            return [normalized(item) for item in value]
        if isinstance(value, dict):
            return {key: normalized(item) for key, item in value.items()}
        return value
    ignored = {"id", "group", "parent", "evidence", "origin", "rationale"}
    def facts(item, identity_labels=False):
        return json.dumps({key: normalized(value, identity_labels and key == "label")
                           for key, value in item.items() if key not in ignored},
                          sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    identities = {}
    owned_scopes = []
    for owner_id in groups:
        path, owner, seen = [], owner_id, set()
        while owner and owner != gid:
            if owner in seen or owner not in groups:
                raise ValueError("Invalid or cyclic source containment.")
            seen.add(owner)
            path.append(facts(groups[owner], True))
            owner = groups[owner].get("parent", "")
        if owner == gid and owner_id != gid:
            owned_scopes.append(tuple(reversed(path)))
    for node in descendant_members[gid]:
        path, owner = [], node.get("group", "")
        while owner and owner != gid:
            path.append(facts(groups[owner], True))
            owner = groups[owner].get("parent", "")
        identities[node["id"]] = (tuple(reversed(path)), facts(node, True))
    if len(set(identities.values())) != len(identities):
        return None
    # Endpoints are source identity, not additional technical fields.
    internal = sorted((identities[edge["source"]], identities[edge["target"]],
                       facts({key: value for key, value in edge.items() if key not in {"source", "target"}}))
                      for edge in edges if edge["source"] in identities and edge["target"] in identities)
    return facts(groups[gid], True), tuple(sorted(owned_scopes)), tuple(sorted(identities.values())), tuple(internal)


def _families(nodes, groups, descendant_members, hints, edges=()):
    families, instances = {}, {}
    for node in nodes:
        match = _SAME.search(node.get("detail", ""))
        if not match:
            continue
        template = _reference_group(match.group(1), groups)
        if template and descendant_members[template]:
            families.setdefault(template, {"template_group": template, "instances": [],
                                             "evidence": []})
            families[template]["instances"].append(node["id"])
            families[template]["evidence"].append(node.get("detail", ""))
            instances[node["id"]] = template
    # Fully specified sibling unit groups can share appearance when the
    # supplied inventories actually match; a similar label alone is insufficient.
    indexed = defaultdict(list)
    for gid, group in groups.items():
        identity = _instance_name(group)
        members = descendant_members[gid]
        if identity and len(members) >= 2 and not _SHARED.search(group["label"]):
            fingerprint = _inventory_signature(gid, groups, descendant_members, edges)
            if fingerprint is not None:
                indexed[(group.get("parent", ""), identity[0].casefold(), fingerprint)].append(gid)
    claimed = {node["id"] for template in families for node in descendant_members[template]}
    for siblings in sorted(indexed.values(), key=lambda item: -len(descendant_members[item[0]])):
        if len(siblings) > 1:
            members = {node["id"] for gid in siblings for node in descendant_members[gid]}
            if members & claimed:
                continue  # A repeated owner already explains these internals.
            template = siblings[0]
            families.setdefault(template, {"template_group": template, "instances": [], "evidence": []})
            families[template]["instances"].extend(siblings[1:])
            families[template]["evidence"].append("Matching supplied private resource patterns and internal relations; owner identities, state and external connections remain independent")
            claimed.update(members)
    for item in hints.get("repeated_sets", []):
        template = item["template_group"]
        if template not in groups or not descendant_members[template]:
            raise ValueError("Repeated template must reference a nonempty source group.")
        valid = {n["id"] for n in nodes} | set(groups)
        if not set(item.get("instances", [])) <= valid:
            raise ValueError("Repeated instance is not a supplied object.")
        if not item.get("evidence"):
            raise ValueError("Repeated-set hints need explicit caller evidence.")
        for instance in item.get("instances", []):
            if instance in groups and descendant_members[instance]:
                if _inventory_signature(template, groups, descendant_members, edges) != _inventory_signature(instance, groups, descendant_members, edges):
                    raise ValueError("Repeated-set evidence conflicts with supplied technical internals.")
        families.setdefault(template, {"template_group": template, "instances": [], "evidence": []})
        families[template]["instances"].extend(item.get("instances", []))
        families[template]["evidence"].append(item["evidence"])
    for family in families.values():
        family["instances"] = list(dict.fromkeys(family["instances"]))
    return list(families.values()), instances


def _zone(node, owner_text):
    text = node["label"] + " " + node.get("detail", "") + " " + owner_text
    if _EXTERNAL.search(node['label']+' '+owner_text) or (node['kind']=='memory' and _EXTERNAL.search(node.get('detail',''))) or (node['kind']=='io' and re.search(r'(?:external|off[- ]chip).*(?:source|device|endpoint)',node.get('detail',''),re.I)):
        return "external"
    if re.search(r"I[- ]?Cache|instruction|指令", text, re.I):
        return "instruction"
    if re.search(r"L[23]\b|memory interface|GM interface|memory controller|存储接口", text, re.I):
        return "memory"
    if _SHARED.search(text) and not _PRIVATE.search(node["label"]):
        return "shared"
    if node['kind'] in {'control', 'stage'}:
        return "instruction"
    return "support"


def build_overview(spec, language="en", hints=None):
    """Return a hierarchy_overview plan, or None when no structure is supplied.

    Optional hints: system_label, repeated_sets (each with template_group,
    instances and evidence), main_family_limit (default 5). All input objects
    and edges are read-only. Boxes include units, common bands and external
    objects; source owners are never rewritten to match those visual bands.
    """
    if spec.get("category") not in STRUCTURE_CATEGORIES or not spec.get("groups"):
        return None
    hints = hints or {}
    nodes = spec["nodes"]
    node_by_id = {n["id"]: n for n in nodes}
    groups = {g["id"]: g for g in spec["groups"]}
    descendants = {gid: [] for gid in groups}
    for node in nodes:
        for gid in _ancestors(node.get("group", ""), groups):
            descendants[gid].append(node)
    families, _ = _families(nodes, groups, descendants, hints, spec["edges"])
    fold_groups = {f["template_group"] for f in families}
    fold_groups.update(i for f in families for i in f["instances"] if i in groups)
    if not families and not any(g.get("parent") for g in groups.values()):
        return None
    ownership = {n["id"]: n.get("group", "") for n in nodes}
    objects, node_to_macro, template_data = [], {}, {}
    for family in families:
        template = family["template_group"]
        template_data[template] = _template_slots(descendants[template], spec["edges"])
    family_by_group = {i: f["template_group"] for f in families for i in [f["template_group"], *f["instances"]]}
    for gid in groups:
        if gid not in fold_groups:
            continue
        members = descendants[gid]
        if any(n["id"] in node_to_macro for n in members):
            raise ValueError("Repeated regions must not overlap or nest.")
        template = family_by_group[gid]
        slots = _instance_slots(template_data[template], template, gid != template)
        objects.append({"id": gid, "label": groups[gid]["label"], "kind": "compute",
                        "type": "unit-region", "members": [n["id"] for n in members],
                        "source_group": gid, "source_owner": groups[gid].get("parent", ""),
                        "template_id": template, "template_slots": slots,
                        "children_labels": [n["label"] for n in descendants[template]],
                        "zone": "units", "display_only": True})
        for n in members:
            node_to_macro[n["id"]] = gid
    for node in nodes:
        if node["id"] in node_to_macro:
            continue
        template = family_by_group.get(node["id"])
        owner_text = " ".join(groups[g]["label"] for g in _ancestors(node.get("group", ""), groups))
        item = {"id": node["id"], "label": node["label"], "kind": node["kind"],
                "type": "collapsed-template" if template else "resource",
                "members": [node["id"]], "source_group": node.get("group", ""),
                "source_owner": node.get("group", ""), "detail": node.get("detail", ""),
                "zone": "units" if template else _zone(node, owner_text)}
        if not template and item['zone']=='support' and node['kind']=='io' and any(e['source']==node['id'] and node_by_id[e['target']]['kind']=='control' for e in spec['edges']):
            item['zone']='instruction'
        if template:
            slots = _instance_slots(template_data[template], template, True)
            item.update(template_id=template, template_slots=slots,
                        children_labels=[s["label"] for s in template_data[template]],
                        inheritance_evidence=node.get("detail", ""),
                        inherited_visual_only=True)
        objects.append(item)
        node_to_macro[node["id"]] = node["id"]
    by_id = {o["id"]: o for o in objects}
    units = [o for o in objects if o["zone"] == "units"]
    # Preserve a compact peer row for a small family; larger real inventories
    # use a balanced two-dimensional array rather than a long row plus a
    # nearly empty tail. This chooses positions, never a new instance count.
    columns = min(4, max(1, math.ceil(math.sqrt(len(units))) if len(units) > 4 else len(units)))
    template_rows = max((len({round(s['box']['y'], 6) for s in slots}) for slots in template_data.values()), default=6)
    long_unit_titles=any(sum(1.25 if ord(c)>255 else .62 for c in u['label'])>18 for u in units)
    unit_width, unit_height, gap, pad = (24 if long_unit_titles else 20), max(12, template_rows * 4 + (8 if long_unit_titles else 4)), 2, 2
    if long_unit_titles:
        for unit in units:
            unit['header_fraction']=.26
            for slot in unit['template_slots']:
                slot['box']['y']=.26+(slot['box']['y']-.14)*(.71/.83)
                slot['box']['height']*=.71/.83
    system_width = max(40, columns * unit_width + (columns - 1) * gap + 2 * pad)
    raw_boxes, lanes = {}, []
    component_lanes = []
    cursor = 5

    def band(zone, title):
        nonlocal cursor
        members = [o for o in objects if o["zone"] == zone]
        if not members:
            return
        if zone=='instruction' and units:
            unit_ids={u['id'] for u in units}
            fanout=[o for o in members if len({node_to_macro[e['target']] for e in spec['edges'] if node_to_macro[e['source']]==o['id']} & unit_ids)>=2]
            if fanout and len(members)>len(fanout):
                rest=[o for o in members if o not in fanout];count=min(4,len(rest));w=(system_width-2*pad-(count-1)*gap)/count
                x=2+pad
                for index,obj in enumerate(rest):
                    if index and index%count==0:x=2+pad
                    fitted=min(w,max(14,sum(1.25 if ord(c)>255 else .75 for c in obj['label'])+4))
                    raw_boxes[obj['id']]=_box(x,cursor+(index//count)*10,fitted,5);x+=fitted+5
                cursor+=math.ceil(len(rest)/count)*10
                for obj in fanout:raw_boxes[obj['id']]=_box(2+pad,cursor,system_width-2*pad,5);cursor+=10
                lanes.append({'id':zone,'label':title,'role':zone,'members':[o['id'] for o in members],'box':_union([raw_boxes[o['id']] for o in members],.6),'display_only':True})
                return
        if zone=='memory' and len(units)>=2:
            unit_ids={u['id'] for u in units}
            backbone=[o for o in members if o['kind']=='memory' and unit_ids<={node_to_macro[e['target']] if node_to_macro[e['source']]==o['id'] else node_to_macro[e['source']] for e in spec['edges'] if o['id'] in (node_to_macro[e['source']],node_to_macro[e['target']]) and e['kind']=='data'}]
            if len(backbone)==1:
                start=cursor;obj=backbone[0];raw_boxes[obj['id']]=_box(2+pad,cursor,system_width-2*pad,5);cursor+=10
                for obj in members:
                    if obj in backbone:continue
                    raw_boxes[obj['id']]=_box(2+system_width-pad-20,cursor,20,5);cursor+=10
                lanes.append({'id':zone,'label':title,'role':zone,'members':[o['id'] for o in members],'box':_union([raw_boxes[o['id']] for o in members],.6),'display_only':True})
                return
        # Roles, then source order; alphabetical labels are not a reading path.
        rank = {"control": 0, "stage": 0, "compute": 1, "io": 2, "memory": 3}
        if zone in {"shared", "support"}:
            members.sort(key=lambda o: rank.get(o["kind"], 2))
        if zone == "shared":
            member_ids = {o["id"] for o in members}
            adjacent = defaultdict(set)
            for edge in spec["edges"]:
                a, b = node_to_macro[edge["source"]], node_to_macro[edge["target"]]
                if a in member_ids and b in member_ids and a != b:
                    adjacent[a].add(b)
                    adjacent[b].add(a)
            components, remaining = [], set(member_ids)
            for member in members:
                if member["id"] not in remaining:
                    continue
                queue, component = [member["id"]], []
                remaining.remove(member["id"])
                while queue:
                    current = queue.pop(0)
                    component.append(current)
                    for candidate in members:
                        nid = candidate["id"]
                        if nid in remaining and nid in adjacent[current]:
                            remaining.remove(nid)
                            queue.append(nid)
                components.append(component)
            count = min(4, len(components))
            width = (system_width - 2 * pad - (count - 1) * gap) / count
            consumed = 0
            for offset in range(0, len(components), count):
                row_components = components[offset:offset + count]
                depth = max(map(len, row_components))
                for column, component in enumerate(row_components):
                    # Preserve a supplied directed operand/transfer chain inside
                    # the weak component; no synthetic shared hardware group.
                    order = {nid: index for index, nid in enumerate(component)}
                    indegree = Counter()
                    forward = defaultdict(list)
                    for edge in spec["edges"]:
                        a, b = node_to_macro[edge["source"]], node_to_macro[edge["target"]]
                        if a in order and b in order and a != b and b not in forward[a]:
                            forward[a].append(b)
                            indegree[b] += 1
                    ready = [nid for nid in component if not indegree[nid]]
                    arranged = []
                    while ready:
                        nid = ready.pop(0)
                        arranged.append(nid)
                        for target in forward[nid]:
                            indegree[target] -= 1
                            if not indegree[target]:
                                ready.append(target)
                    arranged.extend(nid for nid in component if nid not in arranged)
                    for local_row, nid in enumerate(arranged):
                        raw_boxes[nid] = _box(2 + pad + column * (width + gap), cursor + consumed + local_row * 9, width, 5)
                    component_lanes.append({"id": "shared-component-" + str(len(component_lanes) + 1),
                                            "members": arranged, "box": _union([raw_boxes[nid] for nid in arranged]),
                                            "display_only": True, "basis": "supplied weak connectivity"})
                consumed += depth * 9
            lane_box = _box(2 + pad - .6, cursor - .6, system_width - 2 * pad + 1.2, consumed - 4 + 1.2)
            lanes.append({"id": zone, "label": title, "role": zone, "members": [o["id"] for o in members], "box": lane_box, "display_only": True})
            cursor += consumed
            return
        count = min(4, len(members))
        width = (system_width - 2 * pad - (count - 1) * gap) / count
        rows = math.ceil(len(members) / count)
        for index, obj in enumerate(members):
            raw_boxes[obj["id"]] = _box(2 + pad + (index % count) * (width + gap), cursor + (index // count) * 7, width, 5)
        lane_box = _box(2 + pad - .6, cursor - .6, system_width - 2 * pad + 1.2, rows * 7 - 2 + 1.2)
        lanes.append({"id": zone, "label": title, "role": zone, "members": [o["id"] for o in members], "box": lane_box, "display_only": True})
        cursor += rows * 7 + 2

    band("instruction", "Instruction / control" if language == "en" else "指令与控制")
    if units:
        rows = math.ceil(len(units) / columns)
        for index, unit in enumerate(units):
            raw_boxes[unit["id"]] = _box(2 + pad + (index % columns) * (unit_width + gap), cursor + (index // columns) * (unit_height + gap), unit_width, unit_height)
        lanes.append({"id": "units", "label": "Repeated private units" if language == "en" else "同构私有单元",
                      "role": "repeated-array", "members": [o["id"] for o in units],
                      "box": _box(2 + pad - .6, cursor - .6, system_width - 2 * pad + 1.2, rows * (unit_height + gap) - gap + 1.2), "display_only": True})
        cursor += rows * (unit_height + gap) + 6
    band("shared", "Common services" if language == "en" else "共同服务")
    band("support", "Other supplied resources" if language == "en" else "其他给定资源")
    band("memory", "Shared memory / interface band" if language == "en" else "共享存储与接口带")
    system_box = _box(2, 2, system_width, cursor)
    external = [o for o in objects if o["zone"] == "external"]
    for index, obj in enumerate(external):
        neighbor_ids={node_to_macro[e['target']] if e['source'] in obj['members'] else node_to_macro[e['source']] for e in spec['edges'] if e['source'] in obj['members'] or e['target'] in obj['members']}
        neighbor_boxes=[raw_boxes[n] for n in neighbor_ids if n in raw_boxes]
        row=sum(b['y']+b['height']/2 for b in neighbor_boxes)/len(neighbor_boxes)-2.5 if neighbor_boxes else max(5,cursor-7)+index*7
        is_source=obj['kind']=='io' and not any(e['target'] in obj['members'] for e in spec['edges'])
        box=_box(system_box['x']-24 if is_source else system_box['x']+system_width+6,max(5,row),18,5)
        while any(not (box['y']+box['height']+2<=raw_boxes[o['id']]['y'] or raw_boxes[o['id']]['y']+raw_boxes[o['id']]['height']+2<=box['y']) for o in external[:index]):box['y']+=7
        raw_boxes[obj['id']]=box
    shift=max(0,2-min(b['x'] for b in raw_boxes.values()))
    if shift:
        for box in raw_boxes.values():box['x']+=shift
        system_box['x']+=shift
        for lane in lanes:lane['box']['x']+=shift
        for lane in component_lanes:lane['box']['x']+=shift
    scene_width = max(b["x"] + b["width"] for b in raw_boxes.values()) + 2
    scene_height = max(system_box["y"] + system_box["height"], *(b["y"] + b["height"] for b in raw_boxes.values())) + 2
    boxes = {key: _normal(box, scene_width, scene_height) for key, box in raw_boxes.items()}
    for obj in objects:
        obj["box"] = boxes[obj["id"]]
    for lane in lanes:
        lane["box"] = _normal(lane["box"], scene_width, scene_height)
    for component in component_lanes:
        component["box"] = _normal(component["box"], scene_width, scene_height)
    containers, warnings = [], []
    for gid, group in groups.items():
        visible = list(dict.fromkeys(node_to_macro[n["id"]] for n in descendants[gid]))
        if not visible:
            continue
        external_members = [i for i in visible if by_id[i]["zone"] == "external"]
        inside = [i for i in visible if i not in external_members]
        segments = []
        for region in (inside, external_members):
            if region:
                segments.append(_normal(_union([raw_boxes[i] for i in region], .6), scene_width, scene_height))
        containers.append({"id": gid, "label": group["label"], "parent": group.get("parent", ""),
                           "source_group": gid, "members": visible, "source_members": [n["id"] for n in descendants[gid]],
                           "box": segments[0], "segment_boxes": segments, "ownership_unchanged": True,
                           "replaces_region": gid if gid in fold_groups else None})
        if len(visible)==1 and by_id[visible[0]]['label'].strip().casefold()==group['label'].strip().casefold():containers[-1]['replaces_region']=visible[0]
        if external_members and inside:
            containers[-1]['render_boundary']=False
            warnings.append("Group " + gid + " spans supplied internal/external roles; separate segments preserve the source group without moving off-chip memory inside the system frame.")
    # This outer framing is physical only when it corresponds to one supplied
    # root group. A flat input gets a display-only system shell, not a new owner.
    inside_ids = {n["id"] for o in objects if o["zone"] != "external" for n in nodes if n["id"] in o["members"]}
    roots = [g for g in groups.values() if not g.get("parent")]
    system_group = next((g["id"] for g in roots if {n["id"] for n in descendants[g["id"]]} == inside_ids), None)
    frame = {"id": "@system", "label": hints.get("system_label") or (groups[system_group]["label"] if system_group else spec["title"]),
             "box": _normal(system_box, scene_width, scene_height), "source_group": system_group,
             "display_only": system_group is None, "not_an_added_hardware_node": True,
             "replaces_container": system_group}
    for container in containers:
        if container["id"] == system_group:
            container["box"] = frame["box"]
            container["is_system_boundary"] = True
    if system_group is None:
        warnings.append("The outer system shell is visual framing only; flat functional groups do not establish an additional physical ownership domain.")
    projected, index_by_key, internal = [], {}, defaultdict(list)
    for index, edge in enumerate(spec["edges"]):
        source, target = node_to_macro[edge["source"]], node_to_macro[edge["target"]]
        if source == target:
            internal[source].append(index)
            continue
        key = (source, target, edge["kind"])
        if key not in index_by_key:
            index_by_key[key] = len(projected)
            projected.append({"id": "P" + str(len(projected) + 1), "source": source, "target": target,
                              "kind": edge["kind"], "label": "", "labels": [], "members": [], "source_nodes": [], "target_nodes": []})
        link = projected[index_by_key[key]]
        link["members"].append(index)
        for field, value in (("labels", edge.get("label", "")), ("source_nodes", edge["source"]), ("target_nodes", edge["target"])):
            if value and value not in link[field]:
                link[field].append(value)
    family_members = defaultdict(list)
    priority = {"instruction": 0, "external": 1, "memory": 2, "service": 3, "exchange": 4, "coordination": 5, "other": 6}
    for link in projected:
        s, t = by_id[link["source"]], by_id[link["target"]]
        labels = " ".join(link["labels"])
        if re.search(r"instructions?", labels, re.I) or (s['zone']=='instruction' and t['zone']=='units' and link['kind']=='control'):
            family = "instruction"
        elif "external" in (s["zone"], t["zone"]):
            family = "external"
        elif re.search(r"inter[- ](?:pe|core)|exchange|fabric", s["label"] + " " + t["label"], re.I):
            family = "exchange"
        elif "memory" in (s["zone"], t["zone"]):
            family = "memory"
        elif link["kind"] == "control":
            family = "coordination"
        elif "shared" in (s["zone"], t["zone"]):
            family = "service"
        else:
            family = "other"
        link["family"] = family
        link["label"] = link["labels"][0] if len(link["labels"]) == 1 else ""
        family_members[family].append(link["id"])
    ordered_families = sorted(family_members, key=lambda f: priority[f])
    limit = hints.get("main_family_limit", 5)
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0:
        raise ValueError("main_family_limit must be a nonnegative integer.")
    selected = set(ordered_families[:limit])
    main, deferred = [], []
    corridor_counts = Counter()
    lane_by_id = {lane["id"]: lane for lane in lanes}
    def corridor_geometry(family):
        frame_box = frame["box"]
        if family == "external":
            return _normal(_box(system_box["x"] + system_width + 1, 3, 4, cursor - 1), scene_width, scene_height), "vertical"
        if family == "memory":
            return _normal(_box(system_box["x"] + .4, 3, 1.0, cursor - 1), scene_width, scene_height), "vertical"
        if family == "instruction" and "instruction" in lane_by_id and "units" in lane_by_id:
            a, b = lane_by_id["instruction"]["box"], lane_by_id["units"]["box"]
            return _box(a["x"], a["y"] + a["height"], a["width"], max(.002, b["y"] - a["y"] - a["height"])), "horizontal"
        if family in {"service", "exchange", "coordination"} and "units" in lane_by_id:
            a = lane_by_id["units"]["box"]
            below = [lane["box"] for lane in lanes if lane["box"]["y"] > a["y"]]
            end = min((b["y"] for b in below), default=frame_box["y"] + frame_box["height"])
            return _box(a["x"], a["y"] + a["height"], a["width"], max(.002, end - a["y"] - a["height"])), "horizontal"
        return _normal(_box(system_box["x"] + system_width - 1.4, 3, 1, cursor - 1), scene_width, scene_height), "vertical"
    for link in projected:
        source, target = boxes[link["source"]], boxes[link["target"]]
        if by_id[link["target"]]["zone"] == "external":
            source_side, target_side = ("right", "left") if source['x']<target['x'] else ("left", "right")
        elif by_id[link["source"]]["zone"] == "external":
            source_side, target_side = ("right", "left") if source['x']<target['x'] else ("left", "right")
        elif source["y"] + source["height"] <= target["y"]:
            source_side, target_side = "bottom", "top"
        elif target["y"] + target["height"] <= source["y"]:
            source_side, target_side = "top", "bottom"
        else:
            source_side, target_side = ("right", "left") if source["x"] < target["x"] else ("left", "right")
        corridor = link["family"] + ":" + ("control" if link["kind"] in {"control", "feedback", "clock"} else "data")
        track = corridor_counts[corridor]
        corridor_counts[corridor] += 1
        link["routing"] = {"corridor": corridor, "track": track, "source_side": source_side,
                           "target_side": target_side, "obstacle_aware_routing_required": True,
                           "no_broadcast_bus_is_inferred": True}
        if link["family"] in selected:
            main.append(link)
        else:
            deferred.append({**link, "reason": "Deferred relation family; exact source edges remain in detail views and full specification."})
    covered_edges = [i for link in projected for i in link["members"]] + [i for indices in internal.values() for i in indices]
    routing_corridors = []
    for cid, count in corridor_counts.items():
        bounds, axis = corridor_geometry(cid.split(":", 1)[0])
        routing_corridors.append({"id": cid, "track_count": count, "box": bounds,
                                  "axis": axis, "routing_is_not_a_hardware_bus": True})
    for link in projected:
        link["routing"]["track_fraction"] = (link["routing"]["track"] + .5) / corridor_counts[link["routing"]["corridor"]]
    return {"type": "hierarchy_overview", "view_type": "containment-led-system", "abstract": True,
            "title": spec["title"], "macro_nodes": objects, "macro_edges": main,
            "projected_links": projected, "deferred_links": deferred,
            "internal_edges": [{"region": region, "members": indices} for region, indices in internal.items()],
            "containers": containers, "system_frame": frame, "role_lanes": lanes, "boxes": boxes,
            "component_lanes": component_lanes,
            "region_slots": [{"id": u["id"], "box": u["box"], "template_id": u["template_id"],
                              "source_members": u["members"], "template_slots": u["template_slots"]} for u in units],
            "repeat_families": families, "source_ownership": ownership, "node_to_macro": node_to_macro,
            "link_families": [{"id": f, "link_ids": family_members[f], "shown": f in selected} for f in ordered_families],
            "routing_corridors": routing_corridors,
            "canvas": {"coordinate_system": "normalized", "natural_aspect": round(scene_width / scene_height, 3)},
            "coverage": {"source_nodes": len(nodes), "source_edges": len(spec["edges"]),
                         "nodes_projected": len(node_to_macro), "missing_nodes": sorted(set(node_by_id) - set(node_to_macro)),
                         "missing_edges": sorted(set(range(len(spec["edges"]))) - set(covered_edges)),
                         "duplicate_edge_indices": sorted(i for i, count in Counter(covered_edges).items() if count > 1)},
            "warnings": warnings}
