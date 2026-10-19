"""Reading-led display projections, separate from the immutable engineering ledger.

Source facts never change. A main illustration is allowed to summarize real
containment and defer secondary relationships to its caption and technical annex.
No product names, source IDs, or provider brands select an illustration grammar.
"""
from __future__ import annotations

import copy
from collections import defaultdict
import hashlib
import json
import re

from . import scene_profiles
from . import edge_semantics
from . import render_brief
from . import algorithm_flow

POLICY_VERSION = "CPS6"


def source_hash(spec):
    return hashlib.sha256(json.dumps(spec, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _inside(gid, ancestor, groups):
    while gid:
        if gid == ancestor:
            return True
        gid = groups[gid]["parent"]
    return False


def _contract(grammar, question, claim, scope="display projection"):
    return {"grammar": grammar, "question": question, "claim": claim, "scope": scope,
            "target_width_mm": 160, "body_pt": 9, "signal_pt": 8.5,
            "source_invariants": ["source ownership", "directed source relations", "explicit quantities and conditions", "required verbatim text"],
            "editorial_decisions": ["projection", "positions", "line bends", "which optional prose stays in caption"],
            "generation_inputs": "one reviewed target plate; source reference figures are learning material",
            "regeneration_policy": "For technical or structural failure, regenerate from the canonical source and a clean redesigned plate. Local edits are for isolated wording or minor appearance only."}


def _nodes(spec, ids):
    return [{"id": n["id"], "label": n["label"], "kind": n["kind"], "members": [n["id"]],
             "original_group": n["group"], "children": [], "detail": n.get("detail", "")}
            for n in spec["nodes"] if n["id"] in ids]


def _project_edges(spec, indices, owner):
    grouped = {}
    internal = []
    for i in indices:
        e = spec["edges"][i]
        a, b = owner[e["source"]], owner[e["target"]]
        if a == b:
            internal.append(i)
            continue
        # Exact parallel predicates remain distinct. Only a true source-group
        # projection may summarize several leaf relationships at one boundary.
        key = (a, b, e["kind"], e.get("label", "") if a == e["source"] and b == e["target"] else "")
        if key not in grouped:
            grouped[key] = {"source": a, "target": b, "kind": e["kind"], "label": e.get("label", ""), "members": [], "source_labels": []}
        item = grouped[key]
        item["members"].append(i)
        if e.get("label"):
            item["source_labels"].append(e["label"])
    links = []
    for item in grouped.values():
        labels = list(dict.fromkeys(item.pop("source_labels")))
        item["label"] = labels[0] if len(labels) == 1 else ""
        item["meanings_in_caption"] = labels if len(labels) > 1 else []
        links.append(item)
    paired, used = [], set()
    for i, e in enumerate(links):
        if i in used:
            continue
        item = copy.deepcopy(e)
        used.add(i)
        reverse = next((j for j, r in enumerate(links)
                        if j not in used and e["kind"] == "data" and r["kind"] == "data"
                        and r["source"] == e["target"] and r["target"] == e["source"]), None)
        if reverse is not None:
            r = links[reverse]
            used.add(reverse)
            item["bidirectional"] = True
            item["members"] += r["members"]
            item["directional_labels"] = [{"source": e["source"], "target": e["target"], "label": e["label"]},
                                          {"source": r["source"], "target": r["target"], "label": r["label"]}]
            item["label"] = " / ".join(dict.fromkeys(x for x in [e["label"], r["label"]] if x))
        item["id"] = "p" + str(len(paired) + 1)
        paired.append(item)
    return paired, internal


def _execution_main(spec, language):
    indices = [i for i, e in enumerate(spec["edges"]) if e["kind"] in {"data", "relation"}]
    if len(indices) < 4:
        return None
    visible = {x for i in indices for x in (spec["edges"][i]["source"], spec["edges"][i]["target"])}
    groups = {g["id"]: g for g in spec["groups"]}
    owner = {nid: nid for nid in visible}
    objects = _nodes(spec, visible)
    folded = []
    # A real nested compute owner may summarize its leaf resources. A root
    # engine, memory hierarchy, or invented visual collection is never folded.
    for g in sorted(spec["groups"], key=lambda x: x["id"]):
        members = [n for n in spec["nodes"] if n["id"] in visible and _inside(n["group"], g["id"], groups)]
        direct = [n for n in members if n["group"] == g["id"]]
        if not g["parent"] or not 2 <= len(members) <= 6 or len(direct) != len(members) or any(n["kind"] != "compute" for n in members):
            continue
        if any(owner[n["id"]] != n["id"] for n in members):
            continue
        member_ids = {n["id"] for n in members}
        if any(e["source"] in member_ids and e["target"] in member_ids for e in spec["edges"]):
            continue  # An explicit internal operation order is a primary fact.
        boundary_labels = defaultdict(list)
        for i in indices:
            e = spec["edges"][i]
            if (e["source"] in member_ids) != (e["target"] in member_ids):
                incoming = e["target"] in member_ids
                outside = e["source"] if incoming else e["target"]
                boundary_labels[(outside, incoming, e["kind"])].append(e.get("label", ""))
        if any(len(set(values)) > 1 and any(any(c.isdigit() or c in "=<>[]" for c in label) for label in values)
               for values in boundary_labels.values()):
            continue  # Different widths/predicates need separate leaf carriers.
        for n in members:
            owner[n["id"]] = g["id"]
        folded.append({"id": g["id"], "label": g["label"], "kind": "compute",
                       "members": [n["id"] for n in members], "original_group": g["parent"],
                       "source_group": g["id"], "expanded": True,
                       "children": [{"id": n["id"], "label": n["label"], "kind": n["kind"]} for n in members]})
    objects = [o for o in objects if owner[o["id"]] == o["id"]] + folded
    links, internal = _project_edges(spec, indices, owner)
    deferred = [{"index": i, "reason": "Secondary control/interaction is retained in the caption and technical annex."}
                for i in range(len(spec["edges"])) if i not in indices]
    if not folded and not deferred:
        return None
    suffix = "执行总览" if language == "zh" else "execution overview"
    return {"id": "execution", "kind": "overview", "abstract": True, "primary": True,
            "title": spec["title"] + " — " + suffix, "summary": "先读主要数据闭环；真实运算分组概括内部资源，控制细节在图注和附图保留。",
            "view_role": "datapath-overview", "view_type": "publication-execution",
            "node_ids": [], "edge_indices": [], "context_nodes": [],
            "macro_nodes": objects, "macro_edges": links, "source_edge_indices": indices,
            "projection": {"source_node_to_macro": owner, "internal_edges": internal, "deferred_edges": deferred,
                           "folded_groups": [o["id"] for o in folded], "ownership_unchanged": True,
                           "meaning": "Macro arrows summarize existing logical source relations. They do not declare a new physical bus, port, selector, or serialized operation."},
            "design_contract": _contract("folded-flow", "How does data reach computation and leave through the specified outputs or returns?",
                                          "The supplied input paths reach real computation resources and preserve the original output and return relationships.")}


def _organization_main(spec, old, language, preserve_payload=False):
    if not old or not old.get("abstract") or not old.get("structure_layout", {}).get("repeat_families"):
        return _ownership_main(spec, language, preserve_payload=preserve_payload)
    p = old["structure_layout"]
    out = {k: copy.deepcopy(v) for k, v in old.items() if k not in {"structure_layout", "layout_scene", "positions", "dimensions", "glyphs", "attachment_points", "label_layout"}}
    out["primary"] = True
    out["source_edge_indices"] = sorted({i for e in p["projected_links"] for i in e.get("members", [])})
    out["macro_edges"] = copy.deepcopy(p["projected_links"])
    out["repeat_families"] = copy.deepcopy(p["repeat_families"])
    for family in out["repeat_families"]:
        representative = family["template_group"]
        members = {node["id"] for node in spec["nodes"]
                   if _inside(node["group"], representative, {group["id"]: group for group in spec["groups"]})}
        family["source_internal_edge_indices"] = [index for index, edge in enumerate(spec["edges"])
                                                   if edge["source"] in members and edge["target"] in members]
        family["source_internal_relations"] = [{**copy.deepcopy(spec["edges"][index]), "source_edge_index": index}
                                                for index in family["source_internal_edge_indices"]]
    representative_of = {instance: family["template_group"]
                         for family in out["repeat_families"] for instance in family["instances"]}
    source_nodes = {node["id"]: node for node in spec["nodes"]}
    out["macro_nodes"] = []
    for original in p["macro_nodes"]:
        o = {k: copy.deepcopy(v) for k, v in original.items() if k not in {"box", "template_slots", "header_fraction", "children_labels"}}
        o["original_group"] = original.get("source_owner", "")
        o["children"] = [{"id": x["source_node_id"], "label": x["label"], "kind": x["kind"],
                          "detail": source_nodes[x["source_node_id"]].get("detail", "")}
                         for x in original.get("template_slots", []) if not x.get("visual_reference_only")]
        if original["id"] in representative_of or original.get("inherited_visual_only"):
            o["equivalent_to"] = representative_of.get(original["id"], original["template_id"])
            o["children"] = []
        child_ids = {child["id"] for child in o["children"]}
        internal_data = [edge for edge in spec["edges"] if edge["kind"] == "data"
                         and edge["source"] in child_ids and edge["target"] in child_ids]
        if len(child_ids) >= 2 and len(internal_data) == len(child_ids) - 1:
            forward, incoming = defaultdict(list), defaultdict(int)
            for edge in internal_data:
                forward[edge["source"]].append(edge["target"]); incoming[edge["target"]] += 1
            starts = [child["id"] for child in o["children"] if not incoming[child["id"]]]
            if len(starts) == 1 and max(map(len, forward.values()), default=0) <= 1 and max(incoming.values(), default=0) <= 1:
                order, current = [], starts[0]
                while current not in order:
                    order.append(current)
                    if not forward[current]:
                        break
                    current = forward[current][0]
                if set(order) == child_ids:
                    children = {child["id"]: child for child in o["children"]}
                    o["children"] = [children[nid] for nid in order]
                    o["inventory_reading_basis"] = "supplied linear internal dependency"
        out["macro_nodes"].append(o)
    # A sibling with different supplied internals remains its own inventory,
    # rather than disappearing into the proven equivalent family or losing its
    # visible owner among ungrouped leaf symbols.
    from . import structure_layout
    groups = {group["id"]: group for group in spec["groups"]}
    sibling_keys = {(groups[family["template_group"]]["parent"], structure_layout._instance_name(groups[family["template_group"]])[0].casefold())
                    for family in out["repeat_families"] if structure_layout._instance_name(groups[family["template_group"]])}
    owner = copy.deepcopy(p["node_to_macro"])
    for group in spec["groups"]:
        identity = structure_layout._instance_name(group)
        if not identity or (group["parent"], identity[0].casefold()) not in sibling_keys or any(node["id"] == group["id"] for node in out["macro_nodes"]):
            continue
        members = [node for node in spec["nodes"] if _inside(node["group"], group["id"], groups)]
        if len(members) < 2 or any(owner[node["id"]] != node["id"] for node in members):
            continue
        ids = {node["id"] for node in members}
        boundary = defaultdict(list)
        for edge in spec["edges"]:
            if (edge["source"] in ids) != (edge["target"] in ids):
                boundary[(edge["source"] if edge["source"] not in ids else edge["target"], edge["target"] in ids, edge["kind"])].append(edge.get("label", ""))
        if any(len(set(labels)) > 1 and any(any(char.isdigit() or char in "=<>[]" for char in label) for label in labels)
               for labels in boundary.values()):
            continue
        out["macro_nodes"] = [node for node in out["macro_nodes"] if node["id"] not in ids]
        out["macro_nodes"].append({"id": group["id"], "label": group["label"], "kind": "compute",
                                  "members": [node["id"] for node in members], "source_group": group["id"],
                                  "source_owner": group["parent"], "original_group": group["parent"], "zone": "units",
                                  "logical_group": True, "expanded": True,
                                  "distinct_inventory_from": next(family["template_group"] for family in out["repeat_families"]
                                       if groups[family["template_group"]]["parent"] == group["parent"]
                                       and structure_layout._instance_name(groups[family["template_group"]])[0].casefold() == identity[0].casefold()),
                                  "source_internal_relations": [{**copy.deepcopy(edge), "source_edge_index": index}
                                       for index, edge in enumerate(spec["edges"]) if edge["source"] in ids and edge["target"] in ids],
                                  "children": [{"id": node["id"], "label": node["label"], "kind": node["kind"], "detail": node.get("detail", "")} for node in members]})
        for node in members:
            owner[node["id"]] = group["id"]
    if owner != p["node_to_macro"]:
        out["macro_edges"], _ = _project_edges(spec, list(range(len(spec["edges"]))), owner)
    internal = [i for i, edge in enumerate(spec["edges"]) if owner[edge["source"]] == owner[edge["target"]]]
    mapped = {index for edge in out["macro_edges"] for index in edge["members"]}
    out["source_edge_indices"] = sorted(mapped | set(internal))
    out["projection"] = {"source_node_to_macro": owner,
                         "internal_edges": internal,
                         "deferred_edges": [{"index": i, "reason": "Complete incident relationships belong in the technical annex."}
                                            for i in range(len(spec["edges"])) if i not in mapped and i not in internal],
                         "ownership_unchanged": True,
                         "meaning": "Resource organization with a representative expansion of the same source owner. Expansion leaders are explanatory marks without arrowheads, never data edges."}
    out["design_contract"] = _contract("resource-array", "Which resources are private to each instance, and which services are shared?",
                                       "Actual owners retain matching supplied private resource patterns; one real representative per family explains the internals. State, physical identity, behavior and external connections remain independent source facts.")
    out["summary"] = "用紧凑实例阵列和代表展开解释私有/共享层级；完整关系保存在源结构与技术附图。"
    return out


def _ownership_main(spec, language, preserve_payload=False):
    """Organize a true inventory without requiring explicit repeated instances."""
    indices = [i for i, e in enumerate(spec["edges"]) if e["kind"] != "clock"]
    owner = {n["id"]: n["id"] for n in spec["nodes"]}
    nodes = {n["id"]: n for n in spec["nodes"]}
    groups = {group["id"]: group for group in spec["groups"]}
    # A subsystem's inventory is not a substitute for its supplied payload
    # path. Keep real resources visible when their owner contains data edges;
    # this covers computation/storage and cache hierarchies without a product
    # vocabulary or inventing a common fabric to connect them.
    retained = {}
    secondary = set()
    for group in spec["groups"] if preserve_payload else ():
        if any(child["parent"] == group["id"] for child in spec["groups"]):
            continue
        members = {n["id"] for n in spec["nodes"] if n["group"] == group["id"]}
        payload = [i for i in indices if spec["edges"][i]["kind"] == "data"
                   and spec["edges"][i]["source"] in members and spec["edges"][i]["target"] in members]
        if not payload:
            continue
        computes = {nid for nid in members if nodes[nid]["kind"] == "compute"}
        local_pool = (len(computes) > 1 and any(nodes[nid]["kind"] == "memory" for nid in members)
                      and all({nodes[spec["edges"][i]["source"]]["kind"], nodes[spec["edges"][i]["target"]]["kind"]} == {"compute", "memory"}
                              for i in payload))
        if local_pool:
            # A real functional owner with parallel execution resources and
            # local storage stays one subsystem in a system overview. Its
            # external cache/memory path remains visible; expanding its local
            # ports is the detail view's question, not an implied new array.
            continue
        retained[group["id"]] = payload
        payload_nodes = {nid for i in payload for nid in (spec["edges"][i]["source"], spec["edges"][i]["target"])}
        for i in indices:
            edge = spec["edges"][i]
            if edge["source"] not in members or edge["target"] not in members or edge["kind"] == "data":
                continue
            # A direct command into the actual payload consumer can explain
            # the main path; secondary status/recovery stays in exact views.
            principal_command = (edge["kind"] == "control" and edge["target"] in payload_nodes
                                 and nodes[edge["target"]]["kind"] in {"compute", "stage"}
                                 and nodes[edge["source"]]["kind"] in {"control", "io"})
            if not principal_command:
                secondary.add(i)
    indices = [i for i in indices if i not in secondary]
    visible = {nid for i in indices for nid in (spec["edges"][i]["source"], spec["edges"][i]["target"])}
    folded = []
    for g in spec["groups"]:
        if g["id"] in retained:
            continue
        children = [n for n in spec["nodes"] if n["group"] == g["id"]]
        if not any(n["id"] in visible for n in children):
            continue
        if not 2 <= len(children) <= 6 or any(other["parent"] == g["id"] for other in spec["groups"]):
            continue
        ids = {n["id"] for n in children}
        boundary = defaultdict(list)
        for i in indices:
            e = spec["edges"][i]
            if (e["source"] in ids) != (e["target"] in ids):
                incoming = e["target"] in ids
                boundary[(e["source"] if incoming else e["target"], incoming, e["kind"])].append(e.get("label", ""))
        if any(len(set(labels)) > 1 and any(any(c.isdigit() or c in "=<>[]" for c in label) for label in labels)
               for labels in boundary.values()):
            continue
        kinds = {n["kind"] for n in children}
        kind = "compute" if "compute" in kinds else "memory" if kinds == {"memory"} else "io"
        folded.append({"id": g["id"], "label": g["label"], "kind": kind,
                       "members": [n["id"] for n in children], "original_group": g["parent"],
                       "source_group": g["id"], "expanded": True, "logical_group": True,
                       "zone": "external" if all(_external_node(node, groups) for node in children) else "owned-subsystem",
                       "children": [{"id": n["id"], "label": n["label"], "kind": n["kind"]} for n in children]})
        for nid in ids:
            owner[nid] = g["id"]
    if len(folded) < 2 and not retained:
        return None
    objects = [o for o in _nodes(spec, visible) if owner[o["id"]] == o["id"]] + folded
    links, internal = _project_edges(spec, indices, owner)
    mapped = [i for e in links for i in e["members"]]
    deferred = [{"index": i, "reason": "Secondary control, global clock or folded inventory detail remains in the caption and exact annex."}
                for i in range(len(spec["edges"])) if i not in mapped]
    return {"id": "organization", "kind": "overview", "abstract": True, "primary": True,
            "technical_annex": False, "title": spec["title"],
            "summary": ("按真实子系统归属组织主图，保留已给定的主要数据路径；次要控制及资源清单细节在精确附图中保留。" if retained else
                        "按真实子系统归属组织主图，展开必要资源清单；内部接线与全局控制在图注及精确附图中保留。"),
            "macro_nodes": objects, "macro_edges": links, "edge_indices": [], "node_ids": [],
            "source_edge_indices": indices, "view_role": "organization", "steps": [], "annotations": [],
            "projection": {"source_node_to_macro": owner, "internal_edges": internal,
                           "deferred_edges": deferred, "folded_groups": [g["id"] for g in folded],
                           "retained_payload_groups": list(retained),
                           "retained_payload_edge_indices": sorted({i for values in retained.values() for i in values}),
                           "ownership_unchanged": True,
                           "meaning": "True group boundaries summarize only their source inventory and external relationships. A supplied xN group denotes that inventory's original multiplicity; no new instances or internal wiring are invented."},
            "design_contract": _contract("exact-flow" if retained else "ownership-flow",
                                          "Which real subsystems own these resources, and how does the supplied main payload path cross computation, storage and external interfaces?" if retained else "Which real subsystems own these resources, and how do those subsystems interact?",
                                          "Source ownership and principal payload dependencies remain visible; secondary control and folded inventory details have exact companion views." if retained else "Source ownership and the main inter-subsystem relationships are explicit; internal operation is a separate technical view.")}


def _external_node(node, groups):
    """Separate a resource's location from its interface's destination.

    'External memory interface' and 'connects to external DRAM' describe a
    controller's function, not an off-chip controller. A logical group may
    contain both that on-chip endpoint and an explicitly external memory.
    """
    marker = re.compile(r"\boff[ -]?chip\b|\bexternal\b|片外|芯片外", re.I)
    label, detail = node.get("label", ""), node.get("detail", "")
    interface_role = bool(re.search(r"\b(?:controller|controllers|interface|interfaces|bridge|port|ports|phy)\b|控制器|接口|桥接|端口", label, re.I))
    onchip = re.compile(r"\bon[ -]?chip\b|片上|芯片内部", re.I)
    relation = re.compile(r"\b(?:connects?|links?|access(?:es)?|to|for|towards?|drives?|controls?)\b|连接|访问|面向|用于|通往|控制", re.I)
    # A literal position statement is stronger than a functional interface name.
    position = re.compile(r"\b(?:located|situated|placed|resides?)\b[^.;]{0,30}\b(?:outside|off[ -]?chip)\b|\b(?:is|are)\s+(?:physically\s+)?(?:outside\s+(?:the\s+)?(?:chip|die|soc)|off[ -]?chip)\b|(?:位于|放置在|位置为|处于)(?:芯片|SoC|soc|裸片)?(?:边界)?(?:之外|外部|外面)|(?:本模块|该模块|自身)(?:位于|是)?片外", re.I)
    if position.search(detail):
        return True
    if onchip.search(label):
        return False
    if marker.search(label) and not interface_role and not relation.search(label):
        return True
    if re.fullmatch(r"(?:Host|Host PC|Host Processor|Host Device|主机)", label.strip(), re.I):
        return True
    # A supplied equipment/domain owner is stronger evidence than an
    # interface-shaped name. "External interfaces" alone remains ambiguous.
    gid = node.get("group", "")
    while gid:
        group = groups[gid]
        if marker.search(group["label"]) and not re.search(r"\b(?:interfaces?|controllers?|bridges?|ports?)\b|接口|控制器|端口", group["label"], re.I):
            return True
        gid = group["parent"]
    # An explicitly off-chip controller is possible; ordinary 'external memory
    # controller' remains an ambiguous interface name and is kept on chip.
    if interface_role:
        return bool(re.match(r"^(?:Off[ -]?Chip|片外|芯片外)\s*", label, re.I))
    if marker.search(detail) and not relation.search(detail) and not re.search(r"\binterface\b|接口", detail, re.I):
        return True
    gid = node.get("group", "")
    while gid:
        group = groups[gid]
        if marker.search(group["label"]):
            if re.search(r"\b(?:interface|interfaces|controller|controllers|bridge|ports?)\b|接口|控制器|端口", group["label"], re.I) and node.get("kind") not in {"memory", "io"}:
                return False
            return True
        gid = group["parent"]
    return False


def _concept_main(spec, language):
    """A complete functional product projection, not a trimmed local schematic."""
    groups = {g["id"]: g for g in spec["groups"]}
    external = {n["id"] for n in spec["nodes"] if _external_node(n, groups)}
    internal = {n["id"] for n in spec["nodes"]} - external
    roots = [g for g in spec["groups"] if not g["parent"] and internal
             and all(_inside(n["group"], g["id"], groups) for n in spec["nodes"] if n["id"] in internal)]
    root = roots[0] if len(roots) == 1 else None
    physical = bool(root and re.search(r"\b(?:soc|chip|die)\b|片上系统|芯片", root["label"], re.I))
    # Skip a whole-device parent. Its genuine child owners remain visible.
    whole_root = root["id"] if root else ""
    owner = {n["id"]: n["id"] for n in spec["nodes"]}
    folded = []
    def depth(group):
        result, gid = 0, group["parent"]
        while gid:
            result += 1
            gid = groups[gid]["parent"]
        return result
    for group in sorted(spec["groups"], key=lambda g: (depth(g), g["id"])):
        if group["id"] == whole_root:
            continue
        members = [n for n in spec["nodes"] if n["id"] not in external
                   and _inside(n["group"], group["id"], groups) and owner[n["id"]] == n["id"]]
        if len(members) < 2:
            continue
        kinds = {n["kind"] for n in members}
        kind = "compute" if "compute" in kinds else "memory" if "memory" in kinds else "control" if kinds == {"control"} else "io"
        folded.append({"id": group["id"], "label": group["label"], "kind": kind,
                       "members": [n["id"] for n in members], "original_group": group["parent"],
                       "source_group": group["id"], "children": [], "logical_group": True,
                       "collapsed_member_labels": [n["label"] for n in members],
                       "concept_role": "functional-region", "external": False})
        for node in members:
            owner[node["id"]] = group["id"]
    objects = [node for node in _nodes(spec, set(owner)) if owner[node["id"]] == node["id"]] + folded
    for node in objects:
        node["external"] = bool(set(node["members"]) <= external)
        node.setdefault("concept_role", "external-resource" if node["external"] else "functional-region")
        # Leaf implementation prose remains in the source ledger and captions.
        node["detail"] = ""
    indices = [i for i, edge in enumerate(spec["edges"]) if edge["kind"] in {"data", "relation", "control"}
               and owner[edge["source"]] != owner[edge["target"]]]
    links, _ = _project_edges(spec, indices, owner)
    # Several leaf connections may project to one interface. Never erase exact
    # numeric/conditional text merely because that boundary was collapsed.
    for edge in links:
        labels = list(dict.fromkeys(spec["edges"][i]["label"] for i in edge["members"] if spec["edges"][i]["label"]))
        if any(re.search(r"\d|[=<>\[\]]", label) for label in labels):
            edge["label"] = " / ".join(labels)
            edge["meanings_in_caption"] = []
    priority = {"data": 0, "relation": 1, "control": 2}
    # A bounded concept has few interfaces; all unshown edges stay explicit in
    # the source mapping and exact companions, including internal dependencies.
    object_map = {node["id"]: node for node in objects}
    external_links = [edge for edge in links if object_map[edge["source"]]["external"] != object_map[edge["target"]]["external"]]
    internal_links = [edge for edge in links if edge not in external_links]
    internal_links.sort(key=lambda edge: (priority[edge["kind"]], edge["source"], edge["target"], edge["label"]))
    # This is an inventory-led product image: retain genuine external interfaces
    # and only a short internal backbone, never a miniature full wiring graph.
    links = external_links + internal_links[:3]
    mapped = sorted({i for edge in links for i in edge["members"]})
    inner = [i for i, edge in enumerate(spec["edges"]) if owner[edge["source"]] == owner[edge["target"]]]
    frame = {"label": root["label"] if root else spec["title"], "source_group": whole_root,
             "member_ids": [node["id"] for node in objects if not node["external"]],
             "external_ids": [node["id"] for node in objects if node["external"]],
             "physical_boundary": physical,
             "meaning": "Illustrative logical chip boundary from a real source owner; proportions and placement are not a physical floorplan." if physical else "Illustrative logical system enclosure; this does not claim a physical chip boundary or floorplan."}
    return {"id": "concept", "kind": "overview", "abstract": True, "primary": True,
            "technical_annex": False, "title": spec["title"], "summary": "先展示完整产品的功能分区与主要接口；内部资源与精确接线保存在源结构、图注和可选附图。",
            "view_role": "product-concept", "view_type": "product-concept", "node_ids": [], "edge_indices": [],
            "context_nodes": [], "steps": [], "annotations": [], "macro_nodes": objects, "macro_edges": links,
            "source_edge_indices": mapped, "concept_frame": frame,
            "projection": {"source_node_to_macro": owner, "internal_edges": inner,
                           "deferred_edges": [{"index": i, "reason": "Implementation or secondary relationship retained in the source ledger, caption and exact companion."}
                                              for i in range(len(spec["edges"])) if i not in mapped],
                           "folded_groups": [node["id"] for node in folded], "ownership_unchanged": True,
                           "meaning": "Complete functional concept of the same source system. Regions summarize only real source owners; omitted internal wiring is not absent hardware. The outline is illustrative, not a measured physical floorplan."},
            "design_contract": _contract("product-concept", scene_profiles.PROFILES["concept"]["question"],
                                          "Every source resource is represented by its real functional region or exact leaf; visible interfaces have original source evidence.")}


def _scene_flow_main(spec, language, fold_owners=False):
    """Use the payload lifecycle even when the source category is architecture."""
    selected = [i for i, edge in enumerate(spec["edges"]) if edge["kind"] in {"data", "relation"}
                or (edge["kind"] == "feedback" and edge_semantics.stroke(edge) == "solid")]
    if not selected:
        selected = [i for i, edge in enumerate(spec["edges"]) if edge["kind"] == "control"]
    if not selected:
        return None
    visible = {endpoint for i in selected for endpoint in (spec["edges"][i]["source"], spec["edges"][i]["target"])}
    groups = {group["id"]: group for group in spec["groups"]}
    external = {node["id"] for node in spec["nodes"] if _external_node(node, groups)}
    owner = {nid: nid for nid in visible}
    folded = []
    # First retain the reader's actual mechanism, independently of global
    # inventory size. An unrelated management node must not collapse a payload
    # path; conversely, a small but dense graph is not automatically legible.
    # A real-owner summary is only an alternative after measured exact-scope
    # layouts fail, not a count-based replacement made before composition.
    bounded = not fold_owners
    for group in (sorted(spec["groups"], key=lambda value: value["id"]) if fold_owners else []):
        members = [node for node in spec["nodes"] if node["id"] in visible and node["id"] not in external
                   and node["group"] == group["id"] and owner[node["id"]] == node["id"]]
        if len(members) < 2 or any(child["parent"] == group["id"] for child in spec["groups"]):
            continue
        # A stage may be a real functional owner. Its source internal operation
        # remains exact in the companion rather than being asserted as a wire
        # inside this macro lifecycle view.
        kinds = {node["kind"] for node in members}
        kind = "compute" if "compute" in kinds else "memory" if "memory" in kinds else "io"
        folded.append({"id": group["id"], "label": group["label"], "kind": kind,
                       "members": [node["id"] for node in members], "original_group": group["parent"],
                       "source_group": group["id"], "children": [], "logical_group": True,
                       "collapsed_member_labels": [node["label"] for node in members]})
        for node in members:
            owner[node["id"]] = group["id"]
    objects = [node for node in _nodes(spec, visible) if owner[node["id"]] == node["id"]] + folded
    if bounded:
        # Even opposite directions between the same leaf pair remain distinct
        # source relations: read, response and writeback are not a new duplex
        # interface. Each connector retains one exact predicate and direction.
        links = [{**copy.deepcopy(spec["edges"][index]), "id": "p" + str(order + 1), "members": [index]}
                 for order, index in enumerate(selected)]
        internal = []
    else:
        links, internal = _project_edges(spec, selected, owner)
    for edge in links:
        labels = list(dict.fromkeys(spec["edges"][index]["label"] for index in edge["members"] if spec["edges"][index]["label"]))
        if any(re.search(r"\d|[=<>\[\]]", label) for label in labels):
            edge["label"] = " / ".join(labels)
            edge["meanings_in_caption"] = []
    return {"id": "lifecycle", "kind": "overview", "abstract": True, "primary": True,
            "technical_annex": False, "title": spec["title"], "summary": "保留可读范围内的实际资源，解释收集、并行计算、汇合及同一资源的返回路径；控制及其它关系保存在精确附图。" if bounded else "沿真实输入、缓冲、计算和输出讲解数据生命周期；控制及其它关系保存在精确附图。",
            "view_role": "data-lifecycle", "view_type": "publication-exact-flow", "node_ids": [], "edge_indices": [], "context_nodes": [],
            "macro_nodes": objects, "macro_edges": links, "source_edge_indices": selected,
            "projection": {"source_node_to_macro": owner, "internal_edges": internal,
                           "deferred_edges": [{"index": i, "reason": "Source-owner internal operation or secondary interaction remains in the complete source and exact companion."}
                                              for i in range(len(spec["edges"])) if i not in selected or i in internal],
                           "folded_groups": [node["id"] for node in folded], "ownership_unchanged": True,
                           "abstraction_policy": "bounded-leaf-flow" if bounded else "functional-owner-lifecycle",
                           "selection_basis": "Exact source leaves are attempted first; measured layout feasibility, never global resource count, may permit a declared real-owner summary.",
                           "meaning": "Readable source-leaf mechanism: ownership does not replace individual buffers/computation with a stage. Each selected source relation remains a separate directed connector, including branches, joins and same-resource returns. Spatial order is not a cycle schedule." if bounded else "Real functional owners form macro lifecycle stages; their internal source relationships remain in the exact companions. The original payload or dependency relationships determine reading order. Spatial order does not assert serialized execution or a cycle schedule."},
            "design_contract": _contract("exact-flow", scene_profiles.PROFILES["flow"]["question"],
                                          "The actual lifecycle, forks, returns and merge endpoints are preserved; secondary controls are a separate exact view.")}


def flow_owner_alternative(spec, figure, language):
    """Offer one source-backed scope alternative without silently changing it.

    This is deliberately narrower than a generic simplify-graph operation.
    Only the data-lifecycle main view may use the original owner projection;
    behavioral, mathematical, detail, product and system views keep their own
    grammars. A summary must still expose a genuine lifecycle relationship.
    """
    if figure.get("view_role") != "data-lifecycle" or figure.get("projection", {}).get("abstraction_policy") != "bounded-leaf-flow":
        return None, "This reading task does not admit an owner lifecycle alternative."
    alternative = _scene_flow_main(spec, language, fold_owners=True)
    if not alternative or not alternative["projection"]["folded_groups"]:
        return None, "No real source owner provides a different supported scope."
    if not alternative["macro_edges"]:
        return None, "Collapsing these owners would hide every selected relationship and no longer explain the requested data journey."
    if not alternative["projection"]["internal_edges"]:
        return None, "Owner folding would not relieve relationship burden; retain the exact mechanism."
    # A mandatory source object cannot disappear inside a coarse region.
    # Mandatory edge carriers are separately verified by publication preflight.
    required = figure.get("required_verbatim_labels", [])
    hidden = {node["id"] for node in spec["nodes"]
              if alternative["projection"]["source_node_to_macro"].get(node["id"], node["id"]) != node["id"]}
    mandatory = [literal for literal in required if literal and any(literal in node["label"] or literal in node.get("detail", "")
                 for node in spec["nodes"] if node["id"] in hidden)]
    if mandatory:
        return None, "Owner folding would hide required object text: " + "; ".join(mandatory)
    combined = copy.deepcopy(figure)
    combined.update(alternative)
    combined["design_contract"] = {**figure.get("design_contract", {}),
                                    "grammar": "exact-flow",
                                    "question": "How do the real functional owners exchange the supplied data?",
                                    "claim": "This measured scope alternative summarizes real owners; internal operation is deferred to the exact technical companions."}
    return combined, None


def _payload_focus(description):
    """An organizational inventory and an explicit main-path question differ.

    This is a reader-intent cue, independent of device names or graph size.
    Missing intent preserves legacy organizational views; it does not request
    every internal mechanism merely because the source contains data edges.
    """
    pattern = (r"\b(?:main|primary|principal|critical)\s+(?:data|payload|memory|compute|cache)[^.;\n]{0,28}\b(?:path|flow|route|traffic)\b"
               r"|主要通路|主通路|数据路径|访存路径|(?:计算|运算)[^。；\n]{0,24}(?:缓存|存储|显存)[^。；\n]{0,24}(?:关系|通路|路径|流向)")
    return scene_profiles.visual_cue(description, pattern)[0]


def build(spec, settings, legacy_plan, description=""):
    """Plan primary illustrations before physical composition; keep exact annex."""
    language = settings.get("language", "en")
    old = copy.deepcopy(legacy_plan)
    figures = old["figures"]
    primary = None
    resolved = scene_profiles.resolve(settings, spec=spec)
    scene = settings.get("resolved_scene") or (resolved["id"] if resolved else None)
    profile = scene_profiles.PROFILES.get(scene)
    behavioral = spec["category"] in {"algorithm", "fsm", "timing", "pipeline"}
    representation = settings.get("resolved_representation") or scene_profiles.resolve_representation(settings, spec=spec)["id"]
    if representation == "diagram" and spec["category"] in {"fsm", "timing", "memory", "pipeline"}:
        # Specialized behavior grammars are independent of palette or product
        # scene. The module is loaded only for its applicable content families.
        from . import behavior_guide
        primary = behavior_guide.primary(spec, language)
    if representation == "diagram" and algorithm_flow.applicable(spec):
        primary = algorithm_flow.primary(spec, language)
    elif primary is not None:
        pass
    elif representation in {"product_render", "system_illustration"} and not behavioral:
        primary = render_brief.primary(spec, representation, scene or "", language)
    elif scene == "concept" and not behavioral:
        primary = _concept_main(spec, language)
    elif scene == "detail":
        from . import presentation
        # Implementation review starts at a legible real ownership scope. The
        # exact planner retains complete coverage over all the other companions.
        old = presentation.build_plan(spec, "low", language)
        figures = old["figures"]
        figures = [figure for figure in figures if not figure.get("abstract")]
        source_nodes = {node["id"]: node for node in spec["nodes"]}
        source_groups = {group["id"]: group for group in spec["groups"]}
        def review_scope(figure):
            gid = figure.get("main_group", "")
            members = [source_nodes[nid] for nid in figure["node_ids"]
                       if (gid in source_groups and _inside(source_nodes[nid]["group"], gid, source_groups))
                       or (not gid and nid not in figure.get("context_nodes", []))]
            compute = sum(node["kind"] == "compute" for node in members)
            return (bool(compute), len(members), len(figure["edge_indices"]))
        selected_scope = max(figures, key=review_scope)
        figures = [selected_scope] + [figure for figure in figures if figure is not selected_scope]
    elif scene == "flow" and not behavioral:
        primary = _scene_flow_main(spec, language)
    elif spec["category"] in {"architecture", "memory"}:
        primary = _organization_main(spec, figures[0] if figures else None, language,
                                     preserve_payload=scene == "system" and _payload_focus(description))
    elif spec["category"] in {"microarchitecture", "dataflow"}:
        primary = _execution_main(spec, language)
    if primary:
        companions = [f for f in figures if not f.get("abstract")]
        if primary.get("semantic_grammar"):
            # The semantic main view already carries the exact full scope.
            # A duplicate legacy overview adds no reader question and can
            # discard self-loops in its historical group projection.
            companions = [f for f in companions if set(f.get("node_ids", [])) != set(primary["node_ids"])
                          or set(f.get("edge_indices", [])) != set(primary["edge_indices"])]
        figures = [primary] + companions
    for f in figures:
        if f is primary:
            continue
        f["representation"] = "diagram"
        f["primary"] = primary is None and f is figures[0]
        f["technical_annex"] = not f["primary"]
        role = f.get("view_role", "")
        scoped_edges = [spec["edges"][i] for i in f.get("edge_indices", [])]
        control_only = (bool(scoped_edges) and all(e["kind"] in {"control", "feedback", "clock"} for e in scoped_edges)
                        and any(n["kind"] == "control" for n in spec["nodes"] if n["id"] in f.get("node_ids", [])))
        if role == "control" or (control_only and spec["category"] not in {"fsm", "timing", "algorithm"}):
            grammar, question = "control-band", "Which actual resources receive control and which completion signals return?"
        elif spec["category"] in {"fsm", "timing", "pipeline", "algorithm"}:
            grammar, question = spec["category"], "What behavior, dependency, or interaction should the reader understand?"
        else:
            grammar, question = "exact-flow", "How do the selected source relationships operate?"
        f["design_contract"] = _contract(grammar, question, "Exact technical annex; only this selected source scope is drawn.", "exact source scope")
        if "macro_nodes" not in f:
            f["macro_nodes"] = _nodes(spec, set(f["node_ids"]))
            f["macro_edges"], _ = _project_edges(spec, f["edge_indices"], {n["id"]: n["id"] for n in spec["nodes"]})
            f["source_edge_indices"] = list(f["edge_indices"])
    if profile:
        for figure in figures:
            contract = figure["design_contract"]
            drawing_scene = scene if figure["primary"] else "detail"
            if behavioral and drawing_scene == "concept":
                drawing_scene = "detail" if spec["category"] in {"fsm", "timing"} else "flow"
            contract.update(scene=scene, scene_id=drawing_scene, scene_name=profile["name"], reader_purpose=profile["question"],
                            granularity=profile["granularity"], visual_language=profile["visual_language"],
                            annex_policy=profile["annex_policy"])
            if figure["primary"]:
                contract.update(target_width_mm=profile["target_width_mm"], body_pt=profile["body_pt"], signal_pt=profile["signal_pt"])
                if scene == "flow":
                    contract["preferred_reading_direction"] = "left-to-right"
                if scene == "detail":
                    contract["question"] = profile["question"]
                    contract["claim"] = "Exact implementation view of this selected original source scope; no product-level folding."
            figure["scene"] = scene
            if figure.get("representation") in {"product_render", "system_illustration"}:
                contract.update(visual_language=scene_profiles.REPRESENTATIONS[representation]["visual_language"],
                                granularity="whole product; selective context and exact technical companions",
                                annex_policy="Engineering internals are retained in separate technical diagrams; a product surface is not a logical graph.")
    if settings.get("style", "paper") in {"paper", "monochrome"}:
        for f in figures:
            f["design_contract"]["symbol_profile"] = "ink-header" if settings.get("style") == "monochrome" else "plain"
    exact = [i for f in figures if not f["abstract"] for i in f["edge_indices"]]
    if sorted(set(exact)) != list(range(len(spec["edges"]))):
        raise ValueError("Technical annex lost a source relationship.")
    old.update(policy_version="SCENE1" if profile else POLICY_VERSION, figures=figures, strategy="atlas" if len(figures)>1 else "single",
               reading_plan={"source_hash": source_hash(spec), "primary_figure_ids": [f["id"] for f in figures if f["primary"]],
                             "target_width_mm": 160, "body_pt": 9, "signal_pt": 8.5,
                             "selection_basis": "reader question, true containment and source relationships; not a provider aesthetic or fixed product template",
                             "full_source_retained": True},
               summary="主图先解释阅读重点；完整技术关系保存在源结构、图注和精确附图中。")
    if profile:
        old["reading_plan"].update(scene=scene, scene_name=profile["name"], reader_purpose=profile["question"],
                                   granularity=profile["granularity"], annex_policy=profile["annex_policy"],
                                   target_width_mm=profile["target_width_mm"], body_pt=profile["body_pt"], signal_pt=profile["signal_pt"],
                                   selection_basis="reader-purpose scene selects abstraction, grammar and reading order; palette and provider do not select the scene")
    old["reading_plan"].update(representation=representation,
                               representation_basis="Appearance representation is independent of reader purpose, semantic source and palette.")
    return old
