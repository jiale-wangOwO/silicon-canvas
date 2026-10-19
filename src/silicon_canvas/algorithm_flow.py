"""Source-backed algorithm figures, independent of model and hardware layout.

This grammar explains mathematical objects and dependencies.  It never turns
fan-in into a reduction, mathematical tensors into SRAM, or display columns into
an execution schedule.  Source groups and every selected leaf remain intact.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from collections import defaultdict
from . import edge_semantics

POLICY_VERSION = "ALGO1"
ROLES = {"tensor", "operator", "reduction", "state", "storage", "index", "decision"}
_TENSOR = re.compile(r"tensor|matrix|vector|feature\s*map|embedding|张量|矩阵|向量|特征图|\[[^\]]*[,×][^\]]*\]|[A-Za-z0-9_{}]+\s*[×]\s*[A-Za-z0-9_{}]+|∈", re.I)
_OPERATOR = re.compile(r"matmul|multiply|multiplication|convol|softmax|normalize|normalization|transpose|reshape|attention|gather|scatter|projection|reduce|reduction|elementwise|dot\s*product|exp\(|乘|卷积|归一化|规约|转置|重排|加权|点积|求和", re.I)
_REDUCTION = re.compile(r"\b(?:reduce|reduction|sum|max|min|argmax|argmin)\b|∑|Σ|规约|求和|最大值|最小值", re.I)
_STATE = re.compile(r"running|accumulat|previous\s+state|next\s+state|recurrent\s+state|hidden\s+state|状态|累加|累计", re.I)
_INDEX = re.compile(r"^(?:index|indices|position|offset|mask|索引|掩码)\b", re.I)
_MATH_LABEL = re.compile(r"^[A-Za-z](?:[_'][A-Za-z0-9{}]+|[₀-₉ᵢⱼₜ])*?$|^[A-Z]{1,3}$")
_AXIS = re.compile(r"contraction\s+over|reduc(?:tion|e)\s+(?:over|across|axis)|normalized\s+across|along\s+(?:axis|dimension)|按行|按列|规约轴|沿.*维", re.I)
_EQUATION = re.compile(r"=|≤|≥|<=|>=|∈")


def _text_plan(node, role):
    """Select mathematical lines from exact source substrings, not paraphrases."""
    equations, axes, prose = [], [], []
    shape = node.get("tensor_shape", "")
    for clause in re.split(r";\s*|,\s+(?=normalized\s+across)", node.get("detail", "")):
        clause = clause.strip()
        if not clause or clause == shape:
            continue
        if _EQUATION.search(clause):
            # Presentation prefixes may be omitted; equations remain verbatim.
            match = re.match(r"(?:Initialize\s+|After[^:]+:\s*)(.*)", clause, re.I)
            equations.append(match.group(1) if match else clause)
        elif _AXIS.search(clause):
            axes.append(clause)
        else:
            prose.append(clause)
    if node.get("reduction_axis"):
        axes = [node["reduction_axis"], *axes]
    return {"name": node["label"], "mathematical_lines": list(dict.fromkeys(equations)),
            "axis_lines": list(dict.fromkeys(axes)), "shape_once": shape,
            "shape_location": "at output path" if role in {"operator", "reduction"} else "beside the mathematical object",
            "caption_only_detail": prose,
            "policy": "Name once, expression once and shape once for each supplied object/output; repeated symbols inside actual equations are valid. Do not duplicate dimensions below silhouettes and inside labels."}


def _role(node):
    explicit = node.get("diagram_role")
    if explicit:
        return explicit, {"type": "supplied", "fields": ["diagram_role"], "text": explicit}
    label, detail = node.get("label", ""), node.get("detail", "")
    text = label + " " + detail
    kind = node.get("kind")
    if kind == "decision":
        role = "decision"
    elif kind in {"memory", "io", "signal"}:
        if _STATE.search(text):
            role = "state"
        elif _INDEX.search(label):
            role = "index"
        elif _TENSOR.search(text) or _MATH_LABEL.fullmatch(label.strip()):
            role = "tensor"
        else:
            role = "storage" if kind == "memory" else "tensor"
    elif _REDUCTION.search(text) and kind in {"compute", "stage"}:
        role = "reduction"
    elif kind == "state" or (_STATE.search(text) and kind == "control"):
        role = "state"
    else:
        role = "operator"
    return role, {"type": "graphical interpretation", "fields": ["kind", "label", "detail"], "text": text.strip()}


def applicable(spec):
    """Hardware dataflow keeps its existing grammar unless math is supplied."""
    if spec.get("category") == "algorithm":
        return True
    if spec.get("category") != "dataflow":
        return False
    nodes = spec.get("nodes", [])
    if any(node.get("diagram_role") in {"tensor", "operator", "reduction", "state", "index"} for node in nodes):
        return True
    tensor_count = sum(bool(_TENSOR.search(node.get("label", "") + " " + node.get("detail", "")))
                       for node in nodes if node.get("kind") in {"memory", "io", "signal"})
    return tensor_count >= 2 and any(_OPERATOR.search(node.get("label", "") + " " + node.get("detail", ""))
                                     for node in nodes if node.get("kind") in {"compute", "stage"})


def _topology(spec, objects):
    """Deterministic dependency layers; only supplied edges become connectors."""
    ids = [node["id"] for node in spec["nodes"]]
    order = {nid: i for i, nid in enumerate(ids)}
    edges = spec["edges"]
    graph = defaultdict(list)
    incoming = defaultdict(list)
    for index, edge in enumerate(edges):
        if edge["kind"] == "clock":
            continue
        graph[edge["source"]].append((edge["target"], index))
        incoming[edge["target"]].append((edge["source"], index))
    # A DFS back edge is a graphical return, not a newly inferred recurrence.
    colors, returns = {}, []
    def visit(nid):
        colors[nid] = 1
        for target, index in graph[nid]:
            if colors.get(target) == 1:
                returns.append(index)
            elif not colors.get(target):
                visit(target)
        colors[nid] = 2
    for nid in ids:
        if not colors.get(nid):
            visit(nid)
    return_set = set(returns)
    dag_in = {nid: [(source, i) for source, i in incoming[nid] if i not in return_set] for nid in ids}
    ranks = {}
    def rank(nid):
        if nid not in ranks:
            ranks[nid] = max((rank(source) + 1 for source, _ in dag_in[nid]), default=0)
        return ranks[nid]
    for nid in ids:
        rank(nid)
    layers = [{"rank": value, "node_ids": [nid for nid in ids if ranks[nid] == value]}
              for value in sorted(set(ranks.values()))]
    branches = [{"source_node_id": nid, "target_node_ids": list(dict.fromkeys(target for target, _ in graph[nid])),
                 "source_edge_indices": [i for _, i in graph[nid]]}
                for nid in ids if len(set(target for target, _ in graph[nid])) > 1]
    joins = [{"target_node_id": nid, "source_node_ids": list(dict.fromkeys(source for source, _ in incoming[nid])),
              "source_edge_indices": [i for _, i in incoming[nid]],
              "meaning": "separate supplied operands/dependencies; fan-in alone does not imply a reduction"}
             for nid in ids if len(set(source for source, _ in incoming[nid])) > 1]
    # Record strongly connected components for real source cycles.
    serial, stack, on_stack, index_map, low, components = 0, [], set(), {}, {}, []
    def strong(nid):
        nonlocal serial
        index_map[nid] = low[nid] = serial
        serial += 1
        stack.append(nid); on_stack.add(nid)
        for target, _ in graph[nid]:
            if target not in index_map:
                strong(target); low[nid] = min(low[nid], low[target])
            elif target in on_stack:
                low[nid] = min(low[nid], index_map[target])
        if low[nid] == index_map[nid]:
            members = []
            while True:
                member = stack.pop(); on_stack.remove(member); members.append(member)
                if member == nid:
                    break
            scope = set(members)
            inner = [i for i, edge in enumerate(edges) if edge["source"] in scope and edge["target"] in scope and edge["kind"] != "clock"]
            if len(members) > 1 or any(edges[i]["source"] == edges[i]["target"] for i in inner):
                components.append({"node_ids": sorted(members, key=order.get), "source_edge_indices": inner,
                                   "return_edge_indices": [i for i in returns if i in inner]})
    for nid in ids:
        if nid not in index_map:
            strong(nid)
    states = [o["source_node_id"] for o in objects if o["role"] == "state"]
    roles = {o["source_node_id"]: o["role"] for o in objects}
    columns = dict(ranks)
    nearby_operands = []
    for nid in ids:
        targets = list(dict.fromkeys(target for target, i in graph[nid] if i not in return_set))
        if not dag_in[nid] and roles[nid] in {"tensor", "index", "storage"} and len(targets) == 1:
            target = targets[0]
            columns[nid] = max(0, ranks[target] - 1)
            nearby_operands.append({"source_node_id": nid, "consumer_node_id": target, "column": columns[nid],
                                    "basis": "independent supplied operand placed beside its single consumer; dependency rank is unchanged"})
    display_columns = [{"column": value, "node_ids": [nid for nid in ids if columns[nid] == value]}
                       for value in sorted(set(columns.values()))]
    vertical = bool(re.search(r"top.to.bottom|vertical|从上到下|自上而下|纵向", spec.get("layout", ""), re.I))
    return {"dependency_layers": layers, "display_columns": display_columns, "matched_operand_placement": nearby_operands,
            "parallel_branches": branches, "joins": joins,
            "recurrence_components": components, "return_edge_indices": sorted(returns),
            "state_lane_node_ids": states, "primary_reading_axis": "top-to-bottom dependency order" if vertical else "left-to-right dependency order",
            "layer_meaning": "graphical dependency layers only; not cycles, latencies, pipeline stages or serialized execution"}


def build(spec):
    objects = []
    for node in spec["nodes"]:
        role, basis = _role(node)
        fields = {name: node[name] for name in ("label", "kind", "detail", "diagram_role", "tensor_shape", "reduction_axis", "residency") if name in node}
        objects.append({"source_node_id": node["id"], "label": node["label"], "role": role,
                        "source_group": node["group"], "source_fields": fields, "role_basis": basis,
                        "detail": node.get("detail", ""), "tensor_shape": node.get("tensor_shape", ""),
                        "reduction_axis": node.get("reduction_axis", ""), "residency": node.get("residency", ""),
                        "origin": node.get("origin", "given"), "evidence": node.get("evidence", "")})
    topology = _topology(spec, objects)
    recurrence_exits = []
    for component in topology["recurrence_components"]:
        scope = set(component["node_ids"])
        for index, edge in enumerate(spec["edges"]):
            if edge["source"] in scope and edge["target"] not in scope:
                recurrence_exits.append({"source_edge_index": index, "source_node_id": edge["source"], "target_node_id": edge["target"],
                                         "label": edge["label"], "component_node_ids": component["node_ids"],
                                         "kind": edge["kind"], "placement": "separate terminal branch originating at its exact source; outside the recurrent kernel"})
    adjacency = defaultdict(list)
    for index, edge in enumerate(spec["edges"]):
        adjacency[(edge["source"], edge["target"])].append(index)
    outputs = [{"source_node_id": obj["source_node_id"],
                "source_edge_indices": [index for index, edge in enumerate(spec["edges"]) if edge["source"] == obj["source_node_id"]],
                "allowed_target_node_ids": list(dict.fromkeys(edge["target"] for edge in spec["edges"] if edge["source"] == obj["source_node_id"]))}
               for obj in objects]
    residency_labels = defaultdict(list)
    for obj in objects:
        if obj["residency"]:
            residency_labels[(obj["source_group"], obj["residency"])].append(obj["source_node_id"])
    for obj, node in zip(objects, spec["nodes"]):
        obj["text_plan"] = _text_plan(node, obj["role"])
    grammar = "recurrent-tensor-flow" if topology["recurrence_components"] or topology["state_lane_node_ids"] else "branched-tensor-flow" if topology["joins"] or topology["parallel_branches"] else "operator-tensor-flow"
    by_id = {obj["source_node_id"]: obj for obj in objects}
    relations = []
    for index, edge in enumerate(spec["edges"]):
        state_operand = edge["kind"] == "feedback" and any(by_id[endpoint]["role"] == "state" for endpoint in (edge["source"], edge["target"]))
        data_return = edge["kind"] == "feedback" and edge_semantics.stroke(edge) == "solid"
        relations.append({"source_edge_index": index, **copy.deepcopy(edge),
                          "display_role": "state operand/update" if state_operand else "data return" if data_return else "control dependency" if edge["kind"] in {"control", "clock", "feedback"} else "data/dependency",
                          "display_stroke": "solid" if state_operand or data_return or edge["kind"] in {"data", "relation"} else "dashed"})
    return {"version": POLICY_VERSION,
            "source_hash": hashlib.sha256(json.dumps(spec, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
            "objects": objects,
            "relations": relations,
            "groups": [{**copy.deepcopy(group), "member_node_ids": [node["id"] for node in spec["nodes"] if node["group"] == group["id"]]} for group in spec["groups"]],
            "motifs": {key: topology[key] for key in ("parallel_branches", "joins", "recurrence_components")}
                      | {"reductions": [o["source_node_id"] for o in objects if o["role"] == "reduction"],
                         "recurrence_exits": recurrence_exits,
                         "data_residency": [{"source_node_id": o["source_node_id"], "residency": o["residency"]} for o in objects if o["residency"]],
                         "tensor_shapes": [{"source_node_id": o["source_node_id"], "shape": o["tensor_shape"]} for o in objects if o["tensor_shape"]]},
            "composition": {"grammar": grammar, **topology, "group_policy": "compact group headings or short open brackets over actual members; no large empty container frames",
                            "recurrence_exit_branches": recurrence_exits,
                            "residency_labels": [{"source_group": group, "text": text, "source_node_ids": ids} for (group, text), ids in residency_labels.items()],
                            "outgoing_contracts": outputs,
                            "connector_cardinality": [{"source_node_id": a, "target_node_id": b, "source_edge_indices": indices, "connector_count": len(indices)} for (a, b), indices in adjacency.items()],
                            "object_budget": "prefer 8–14 main objects per panel; if the complete source is larger, use aligned source-backed panels without dropping leaves or dependencies"},
            "semantic_policy": "Shapes, axes, tiles and residency are shown only when supplied. Separate operands remain separate. Visible source cycles retain exact direction. A graphical join is not a reduction, matrix multiply is not elementwise multiplication, and no tensor is silently a hardware memory."}


def primary(spec, language="en"):
    plan = build(spec)
    indices = list(range(len(spec["edges"])))
    nodes = [{"id": node["id"], "label": node["label"], "kind": node["kind"], "members": [node["id"]],
              "original_group": node["group"], "detail": node.get("detail", ""), "children": []} for node in spec["nodes"]]
    return {"id": "algorithm-flow", "kind": "overview", "abstract": True, "primary": True, "technical_annex": False,
            "title": spec["title"], "summary": "用张量、运算符、并行分支及源规格中的状态更新解释计算；保留每个运算和依赖，避免套用硬件流水线。",
            "representation": "diagram", "view_role": "algorithm-dataflow", "view_type": "algorithm-dataflow",
            "node_ids": [], "edge_indices": [], "context_nodes": [], "macro_nodes": nodes,
            "macro_edges": [{**copy.deepcopy(edge), "members": [i]} for i, edge in enumerate(spec["edges"])],
            "source_edge_indices": indices, "algorithm_flow_plan": plan, "requires_layout_guide": False,
            "projection": {"source_node_to_macro": {n["id"]: n["id"] for n in spec["nodes"]}, "internal_edges": [], "deferred_edges": [], "folded_groups": [], "ownership_unchanged": True,
                           "meaning": "Identity source projection: each tensor/operator/state and directed dependency is preserved. Phase groups organize reading without becoming collapsed stage cards or physical hardware."},
            "design_contract": {"grammar": plan["composition"]["grammar"], "scope": "complete source-backed algorithm dependency graph",
                                "question": "Which supplied operands feed each operation, where do branches join, and what source-backed state or residency explains reuse?",
                                "claim": "Every source object and dependency is retained; visual roles and layers explain supplied mathematics without adding schedule or hardware.",
                                "target_width_mm": 160, "body_pt": 9, "signal_pt": 8.5,
                                "generation_inputs": "text-only algorithm brief; no hardware target plate is required"}}


def compile_figure(figure, spec, settings, palette, required_labels=()):
    plan = figure["algorithm_flow_plan"]
    by_id = {o["source_node_id"]: o for o in plan["objects"]}
    name = lambda nid: json.dumps(by_id[nid]["label"], ensure_ascii=False)
    contract = figure.get("design_contract", {})
    width_mm, body_pt, signal_pt = (contract.get("target_width_mm", 160), contract.get("body_pt", 9), contract.get("signal_pt", 8.5))
    background, ink = palette.get("background", "#FFFFFF"), palette.get("ink", "#263238")
    lines = ["Generate one publication-quality ALGORITHM DATAFLOW figure with Image Gen from this complete source-backed brief. No input guide image is required.",
             "The figure explains mathematical data objects, operations and dependencies, with the clarity of an algorithm paper. It is not a chip floorplan, hardware block inventory, timing chart or numbered process dashboard.",
             "Use the selected background " + background + " and restrained thin strokes/text " + ink + ", generous open gaps and small consistent arrowheads. A few quiet semantic accent families are a starting point; each color has one stable role and grayscale position/shape/line cues must retain meaning. Avoid decorative gradients, bevels, glossy cards, heavy shadows and thick enclosing boxes that compete with the mathematics.",
             f"Use clear sans-serif names and clean mathematical typesetting. Fit legibly at {width_mm:g} mm document width: main labels about {body_pt:g} pt, edge labels about {signal_pt:g} pt; redesign spacing or panels rather than shrink text. Keep shapes subordinate to mathematics. Omit the large title/header; the document caption carries " + json.dumps(spec["title"], ensure_ascii=False) + ".",
             "Visual vocabulary: tensors are compact mathematical symbols with a pale silhouette when useful. A simple projected plane, meaningful stack or depth cue may explain a supplied tensor shape, axis or feature resolution; do not add an unsupplied tensor axis or imply counted cells, tiles or hardware copies. A symbolic dimension is never a fabricated grid-cell count. Operators use compact outlined symbols with their operation name and essential expression. Supplied reductions have their own operator and exact axis. State is an explicitly named accumulator/state strip next to its update path. Storage/residency is shown only as supplied. Diamonds belong only to an actual decision. Shapes differ by meaning rather than becoming identical rounded cards.",
             "Layout is a dependency graph, not a serial list of steps: keep independent inputs and parallel branches separately aligned. Put each operator's operands beside its actual input arrows, use distinct ingress attachments for separate operands, and place its output downstream along the selected reading orientation. An unlabeled arrow carries the supplied dependency only; never create intermediate tensors or duplicate an operator to fill the page."]
    lines.append("Concise text policy: print each supplied object name once, each essential equation once and each object/output shape once. Mathematical symbols may recur within actual equations. Put an output shape beside its outgoing value or once below its producing operator, never at both. Do not repeat Query/Key/Value/Output tensor prose, transient descriptions or long annotations in the artwork. The caption carries explanatory prose. Do not turn audit instructions into notes, legends or footers.")
    if settings.get("style") == "monochrome":
        lines.append("Selected monochrome style: white background, dark ink and pale neutral grayscale only. Distinguish tensors, operators and state by silhouette and line treatment, without colored accents.")
    else:
        selected = {key: value for key, value in palette.items() if isinstance(value, str) and value.startswith("#")}
        lines.append("Selected palette: " + "; ".join(key + " " + value for key, value in selected.items()) + ". Use its pale primary family for tensors and pale secondary family for operations; keep state quietly distinct by line treatment. A palette never changes the algorithm topology.")
    aspect = settings.get("aspect", "auto")
    if aspect != "auto":
        lines.append("Requested canvas proportions: " + aspect + ". Adapt open spacing and the source-backed branch lanes to this canvas.")
    axis = plan["composition"]["primary_reading_axis"]
    lines.append("Named spatial organization: " + axis + "; the following display columns are dependency-based reading bands, never a pipeline schedule. Independent single-consumer operands sit beside their actual consumer rather than at the far left. Never print column numbers.")
    for layer in plan["composition"]["display_columns"]:
        lines.append("Display band " + str(layer["column"] + 1) + ": " + ", ".join(name(nid) for nid in layer["node_ids"]) + ". Objects in a band occupy separate aligned branch lanes, not one combined object.")
    if spec.get("layout"):
        lines.append("Supplied source-specific organization intent: " + spec["layout"] + ". Follow its named operand/bypass/state/residency relationships; dependency bands may be transposed or spaced to support this intent without changing the graph.")
    for branch in plan["motifs"]["parallel_branches"]:
        lines.append("Branch " + name(branch["source_node_id"]) + " into separate lanes toward " + ", ".join(name(nid) for nid in branch["target_node_ids"]) + "; preserve each exact connector and shared source, without serialized arrows between those branches.")
    for join in plan["motifs"]["joins"]:
        lines.append("At " + name(join["target_node_id"]) + ", keep incoming operands from " + ", ".join(name(nid) for nid in join["source_node_ids"]) + " distinct. Align their arrowheads on separate attachments; their fan-in does not create a sum/reduction operation.")
    states = plan["composition"]["state_lane_node_ids"]
    if states:
        lines.append("Lower state lane: " + ", ".join(name(nid) for nid in states) + ". Position adjacent to the supplied update operator. Show only the supplied old/new-state dependencies; a state name alone does not authorize adding a feedback loop.")
    returns = set(plan["composition"]["return_edge_indices"])
    if returns:
        lines.append("Use a dedicated lower/outer return corridor for these actual source cycles: " + "; ".join(name(spec["edges"][i]["source"]) + " → " + name(spec["edges"][i]["target"]) for i in sorted(returns)) + ". Preserve their arrowhead direction and any supplied predicate; do not mix these returns into the forward lanes.")
    for exit in plan["motifs"]["recurrence_exits"]:
        source, target = exit["source_node_id"], exit["target_node_id"]
        lines.append("Separate recurrence-exit branch: place " + name(target) + " to the lower/right of " + name(source) + ", outside the recurrent kernel. This branch starts ONLY at " + name(source) + " and carries " + json.dumps(exit["label"], ensure_ascii=False) + ". Keep it spatially apart from the upper per-iteration computation spine; do not extend that spine straight into this exit target. Adjacent computation boxes do not authorize an extra shortcut arrow. The source predicate is exact; no new completion condition may be inferred.")
    if len(plan["objects"]) > 14:
        lines.append("This complete source exceeds one compact panel. Arrange aligned panels along the actual phase groups or dependency columns, with named source-backed continuation terminals when necessary. Keep every original object and dependency represented exactly once; no collapsed black-box stage may hide mathematics.")
    parent_map = {group["id"]: group["parent"] for group in plan["groups"]}
    def belongs(gid, ancestor):
        while gid:
            if gid == ancestor:
                return True
            gid = parent_map.get(gid, "")
        return False
    for group in plan["groups"]:
        members = group["member_node_ids"]
        if members:
            parent = next((g["label"] for g in plan["groups"] if g["id"] == group["parent"]), "")
            outside = [obj["source_node_id"] for obj in plan["objects"] if not belongs(obj["source_group"], group["id"])]
            lines.append("Supplied group " + json.dumps(group["label"], ensure_ascii=False) + " has exact members " + ", ".join(name(nid) for nid in members) + ("; parent " + json.dumps(parent, ensure_ascii=False) if parent else "") + ". Use a compact heading, open bracket or thin enclosure when it clarifies the real iteration, residency or phase scope. Keep operators visible and avoid empty padded frames. Every shown boundary must stop before nonmembers " + ", ".join(name(nid) for nid in outside) + ". Unowned outputs stay outside every source group; no group may expand merely to fill the canvas. A real source-group frame is meaningful scope, not a hardware package or an implied repeated-instance count.")
    lines.append("Required visible mathematical inventory:")
    for obj in plan["objects"]:
        line = name(obj["source_node_id"]) + " — " + obj["role"]
        shape_label = "supplied output shape" if obj["role"] in {"operator", "reduction"} else "supplied shape"
        text_plan = obj["text_plan"]
        if text_plan["mathematical_lines"]:
            line += "; essential exact equation(s) " + "; ".join(json.dumps(text, ensure_ascii=False) for text in text_plan["mathematical_lines"])
        if text_plan["axis_lines"]:
            line += "; essential supplied axis " + "; ".join(json.dumps(text, ensure_ascii=False) for text in text_plan["axis_lines"])
        if obj["tensor_shape"]:
            line += "; " + shape_label + " ONCE " + json.dumps(obj["tensor_shape"], ensure_ascii=False)
        lines.append(line + ". Keep this object compact. Do not repeat its label as both a nearby heading and inside a card.")
    if plan["composition"]["residency_labels"]:
        lines.append("Source-backed residency/reuse cues: show each following source phrase once beside its named group/members or source path; never repeat residency prose under every operator:")
        for item in plan["composition"]["residency_labels"]:
            lines.append(json.dumps(item["text"], ensure_ascii=False) + " applies to " + ", ".join(name(nid) for nid in item["source_node_ids"]) + ".")
    lines.append("Closed outgoing-connection contract: the targets listed below are the ONLY permissible arrow destinations for each object. Omit all other adjacency shortcuts; a visually adjacent successor is not automatically connected.")
    for item in plan["composition"]["outgoing_contracts"]:
        targets = item["allowed_target_node_ids"]
        lines.append(name(item["source_node_id"]) + ": " + (", ".join(name(nid) for nid in targets) if targets else "terminal sink; no outgoing arrows") + ".")
    lines.append("One listed source relation produces one connector. A comma-separated tuple carried by one edge is ONE arrow bearing that entire tuple; never split it into several update arrows. Parallel source relations only remain separate when separately listed.")
    lines.append("Exact connector cardinality between each ordered pair (audit constraint only; do not typeset these counts): " + "; ".join(name(item["source_node_id"]) + " → " + name(item["target_node_id"]) + ": " + str(item["connector_count"]) + " connector" + ("s" if item["connector_count"] != 1 else "") for item in plan["composition"]["connector_cardinality"]) + ".")
    lines.append("Exact directed connections (quoted names identify the objects; do not print provenance tags or source IDs):")
    for rel in plan["relations"]:
        line = name(rel["source"]) + " → " + name(rel["target"])
        if rel["label"]:
            line += "; supplied edge text " + json.dumps(rel["label"], ensure_ascii=False)
        if rel["display_role"] == "state operand/update":
            line += "; thin solid directed previous-state operand or new-state update, preserving the original recurrence"
        elif rel["display_role"] == "data return":
            line += "; thin solid directed return of the supplied data payload"
        elif rel["kind"] in {"control", "clock", "feedback"}:
            line += "; distinguish this supplied " + rel["kind"] + " dependency by a fine dashed stroke; it is not a tensor transfer"
        else:
            line += "; thin solid directed dependency"
        if rel["source_edge_index"] in returns:
            line += "; route on the outer return corridor"
        lines.append(line + ".")
    for edge in figure.get("macro_edges", []):
        index = edge["members"][0]
        edge["stroke_style"] = plan["relations"][index]["display_stroke"]
    if not plan["relations"]:
        lines.append("No connectors are supplied. Add no arrows.")
    expressions = [*spec.get("steps", []), *spec.get("annotations", [])]
    mathematical = [item for item in expressions if _EQUATION.search(item)]
    context = [item for item in expressions if item not in mathematical]
    if mathematical:
        lines.append("Additional supplied mathematical expressions: show only beside the matching operator if not already printed there:")
        lines.extend(json.dumps(item, ensure_ascii=False) for item in mathematical)
    if context:
        lines.append("Source context for interpretation ONLY; preserve its meaning through graph and equations, but DO NOT TYPESET this prose or add a footer:")
        lines.extend(json.dumps(item, ensure_ascii=False) for item in context)
    if required_labels:
        lines.append("Mandatory exact supplied text: " + "; ".join(json.dumps(label, ensure_ascii=False) for label in required_labels) + ". Put each on its matching object, never in a separate label list.")
    if settings.get("notes"):
        lines.append("Additional requested presentation constraints: " + settings["notes"])
    lines.append("Check the final bitmap: every arrow must have the listed source, target and direction; trace every separate operand and source cycle. Preserve shapes, axes, predicates and source grouping without inventing numerical dimensions, tile counts, extra normalization, hardware buffers or mathematical operators. A compact paper figure must still explain the computation at a glance.")
    return "\n".join(lines)
