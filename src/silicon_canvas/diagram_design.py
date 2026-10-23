"""Source-driven editorial decisions for diagrams, independent of model/style.

The plan describes the *actual* selected display, including nested inventories
and same-hardware expansions. Counts measure drawing burden, not aesthetic
quality. Acceptance always requires inspection of the generated bitmap.
"""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json
import re


POLICY_VERSION = "DGP1"
_EXACT = re.compile(r"\d|[=<>≤≥≠∑×÷]|\[[^\]]+\]|\b(?:if|when|unless|otherwise|until)\b|若|当|否则|条件", re.I)


def _hash(spec):
    return hashlib.sha256(json.dumps(spec, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _visible(spec, figure):
    source = {node["id"]: node for node in spec.get("nodes", [])}
    layout = figure.get("structure_layout", {})
    render = figure.get("render_brief", {}).get("visible_content")
    if isinstance(render, dict):
        nodes = []
        for region in render.get("regions", []) + render.get("context_objects", []):
            members = region.get("source_node_ids", [])
            nodes.append({"id": region["id"], "label": region["label"], "kind": region.get("role", "resource"),
                          "members": members, "children": [source[nid] for nid in members if nid in source] if len(members) > 1 else [],
                          "original_group": source.get(members[0], {}).get("group", "") if members else ""})
        edges = [{**relation, "kind": relation.get("kinds", ["relation"])[0], "label": " / ".join(relation.get("labels", [])),
                  "members": relation.get("source_edge_indices", [])} for relation in render.get("relationships", [])]
        return nodes, edges, "selected product explanation; logical region membership is illustrative, not a physical floorplan"
    if layout.get("type") in {"publication", "behavioral"} and "macro_nodes" in layout:
        return layout["macro_nodes"], layout.get("macro_edges", []), "compiled publication guide"
    if figure.get("abstract"):
        nodes = figure.get("macro_nodes", layout.get("macro_nodes", []))
        return nodes, figure.get("macro_edges", []), "selected display projection"
    nodes = [source[nid] for nid in figure.get("node_ids", source) if nid in source]
    edges = [{**spec["edges"][index], "members": [index]} for index in figure.get("edge_indices", range(len(spec.get("edges", []))))]
    return nodes, edges, "selected source scope"


def _owner_path(gid, groups):
    path, visited = [], set()
    while gid in groups and gid not in visited:
        visited.add(gid)
        path.append(gid)
        gid = groups[gid].get("parent", "")
    return list(reversed(path))


def _components(ids, edges):
    """Strongly connected components; the presence of a return is not latency."""
    adjacency = {nid: [] for nid in ids}
    for edge in edges:
        if edge["source"] in adjacency and edge["target"] in adjacency:
            adjacency[edge["source"]].append(edge["target"])
            if edge.get("bidirectional"):
                adjacency[edge["target"]].append(edge["source"])
    cursor, stack, on_stack, numbers, low, output = 0, [], set(), {}, {}, []
    def visit(nid):
        nonlocal cursor
        numbers[nid] = low[nid] = cursor
        cursor += 1
        stack.append(nid); on_stack.add(nid)
        for target in adjacency[nid]:
            if target not in numbers:
                visit(target); low[nid] = min(low[nid], low[target])
            elif target in on_stack:
                low[nid] = min(low[nid], numbers[target])
        if low[nid] == numbers[nid]:
            members = []
            while True:
                current = stack.pop(); on_stack.remove(current); members.append(current)
                if current == nid:
                    break
            if len(members) > 1 or nid in adjacency[nid]:
                output.append(sorted(members))
    for nid in ids:
        if nid not in numbers:
            visit(nid)
    return sorted(output)


def _reading(category, figure, ids, incoming, outgoing, cycles):
    grammar = figure.get("design_contract", {}).get("grammar", category)
    explanation = figure.get("render_brief", {}).get("explanation_plan", {})
    if explanation:
        kind = explanation.get("mode", "product-explanation")
        question = explanation.get("reading_question", "What should the supplied product illustration explain?")
        convention = "Use the selected explanatory scope and a coherent camera/composition; factual roles and membership remain source-backed while appearance and logical placement are conceptual."
    elif category == "timing":
        kind = "signal-time"
        question = "How do the supplied signal values and events relate on the same time axis?"
        convention = "Aligned signal rows share one supplied time/event axis; preserve edge instants, levels and intervals. Missing cycle information permits an illustrative event sequence, never invented waveforms or latency."
    elif category == "fsm":
        kind = "state-transition"
        question = "Which supplied condition takes the controller from one state to another?"
        convention = "States are distinct state symbols and conditions sit on their transition. Use a cyclic or clustered transition map when needed; do not turn states into a numbered linear pipeline or invent an initial/final state."
    elif figure.get("algorithm_flow_plan"):
        kind = "mathematical-dependency"
        question = "How do the supplied operands, operations and state updates produce the output?"
        convention = "Operands and operator results remain distinct; align independent inputs and branches. Equations, tensor shapes and reduction axes stay on the matching object/output. A merge alone is not a mathematical operator."
    elif category == "algorithm":
        kind = "procedure-branch-loop" if cycles or any(value > 1 for value in outgoing.values()) else "procedure-sequence"
        question = "What inputs, decisions, operations and stopping conditions define the supplied procedure?"
        convention = "Use process symbols for actions and decision symbols only for supplied decisions. Keep alternative branches and loop predicates visible; dependency order does not establish clock-cycle timing."
    elif category == "pipeline":
        kind = "stage-dependency"
        question = "What is transformed at each supplied stage and where do branches, stalls or returns occur?"
        convention = "Give comparable functional stages a stable progression, with branch lanes and return corridors when supplied. Stage order is distinct from cycle latency; draw registers or handshake interfaces only when given."
    elif grammar in {"resource-array", "repeated-resources"} or figure.get("repeat_families"):
        kind = "equivalent-resource-array"
        question = "Which actual instances own private resources and which supplied services do they share?"
        convention = "Align source-proven peers as peers, retain actual instance names/count, and distinguish private contents from common services. A detail expansion is the same hardware, not another copy."
    elif grammar == "control-band":
        kind = "control-distribution"
        question = "Which actual resources receive commands and which completion or recovery paths return?"
        convention = "Separate command distribution from completion/recovery lanes, with independently traceable drops. A visual distribution band cannot create a broadcast wire or common electrical junction."
    elif category in {"architecture", "memory"} or grammar == "ownership-flow":
        kind = "ownership-network"
        question = "Which resources belong together and how do their supplied interfaces cross those boundaries?"
        convention = "Organize real ownership levels and source-backed common services. Centrality follows adjacency, not name or visual prominence; functional alignment bands never create ownership or shared hardware."
    else:
        kind = "fork-join-return" if cycles or any(value > 1 for value in incoming.values()) or any(value > 1 for value in outgoing.values()) else "source-transform-sink"
        question = "How do the supplied inputs reach their transformations and leave through outputs or returns?"
        convention = "Keep independent producer paths and joins traceable and place supplied returns in a separate corridor. Preserve the same resource at both ends of a return instead of duplicating it for a tidy row."
    supplied = explanation.get("reading_question") or figure.get("design_contract", {}).get("question", "")
    generic = {"What behavior, dependency, or interaction should the reader understand?", "How do the selected source relationships operate?"}
    return {"kind": kind, "grammar": grammar, "reading_question": supplied if supplied and supplied not in generic else question,
            "convention": convention, "entry_nodes": [nid for nid in ids if not incoming[nid]],
            "exit_nodes": [nid for nid in ids if not outgoing[nid]], "cycle_components": cycles,
            "direction": figure.get("structure_layout", {}).get("canvas", {}).get("reading_direction", "chosen from dependencies and ownership; no fixed left-to-right rule")}


def build(spec, figure, settings=None):
    """Build honest drawing decisions; do not modify source, figure or settings."""
    settings = settings or {}
    sources = {node["id"]: node for node in spec.get("nodes", [])}
    groups = {group["id"]: group for group in spec.get("groups", [])}
    nodes, edges, basis = _visible(spec, figure)
    layout = figure.get("structure_layout", {})
    ids = [node["id"] for node in nodes]
    incoming, outgoing = defaultdict(int), defaultdict(int)
    for edge in edges:
        incoming[edge["target"]] += 1; outgoing[edge["source"]] += 1
        if edge.get("bidirectional"):
            incoming[edge["source"]] += 1; outgoing[edge["target"]] += 1
    strategy = _reading(spec.get("category", "architecture"), figure, ids, incoming, outgoing, _components(ids, edges))
    appearances, nested, root_leaves, repeated = [], [], [], []
    metrics = layout.get("symbol_metrics", {})
    def record(node, path, same_hardware=False):
        nid = node.get("id", "")
        original_id = nid if nid in sources else node.get("members", [""])[0] if len(node.get("members", [])) == 1 else ""
        source = sources.get(original_id, {})
        gid = source.get("group", node.get("original_group", node.get("group", "")))
        children = metrics.get(nid, {}).get("children", node.get("children", [])) if len(path) == 1 else node.get("children", [])
        measured = metrics.get(nid, {}) if len(path) == 1 else node
        printed = measured.get("lines")
        printed = [*(printed if isinstance(printed, list) else [node.get("label", "")]), *measured.get("detail_lines", [])]
        item = {"display_path": path, "source_node_id": original_id, "label": node.get("label", ""),
                "role": source.get("diagram_role") or source.get("kind", node.get("kind", "resource")),
                "source_owner_path": _owner_path(gid, groups), "same_hardware_expansion": same_hardware,
                "printed_lines": printed,
                "has_children": bool(children)}
        appearances.append(item)
        if len(path) > 1:
            nested.append(item)
        if not children:
            root_leaves.append(item)
        for child in children:
            if isinstance(child, str):
                child = sources.get(child, {"id": child, "label": child})
            record(child, [*path, child.get("id", child.get("label", ""))], same_hardware)
    for node in nodes:
        record(node, [node["id"]])
    for inset in layout.get("insets", []):
        # An inset is an additional visual occurrence, never extra hardware.
        parent = next((node for node in nodes if node["id"] == inset.get("source_object")), None)
        if parent:
            inset_node = {**parent, "children": inset.get("metrics", {}).get("children", parent.get("children", []))}
            record(inset_node, [inset.get("id", "detail"), parent["id"]], bool(inset.get("same_hardware")))
    inset_sources = {inset.get("source_object") for inset in layout.get("insets", []) if inset.get("same_hardware")}
    for node in nodes:
        equivalent = node.get("equivalent_to")
        if not equivalent:
            match = re.fullmatch(r"Same resources as\s+([A-Za-z_][A-Za-z_0-9]*)", node.get("detail", ""), re.I)
            equivalent = match.group(1) if match else ""
        if equivalent or node.get("inherited_visual_only") or node.get("inherited") or node["id"] in inset_sources:
            shown = any(item["display_path"][0] == node["id"] and len(item["display_path"]) > 1 for item in nested)
            repeated.append({"display_id": node["id"], "equivalent_to": equivalent,
                             "shown_inventory": "expanded-in-place" if shown else "representative-inset" if node["id"] in inset_sources else "compact-peer",
                             "source_assertion": "source-proven equivalence; no inferred extra instances",
                             "instruction": "Keep the shown private inventory in this peer; its separate appearance is private, never common storage." if shown else "Keep the peer compact as shown; its equivalent inventory is explained by the source-proven representative or same-hardware inset."})
    route_count = len(figure.get("layout_scene", {}).get("routes", edges))
    text_items = [line for item in appearances for line in item["printed_lines"] if line]
    drawn_sources = {item["source_node_id"] for item in appearances if item["source_node_id"]}
    for label in figure.get("label_layout", {}).get("labels", []):
        # Behavioral manifests repeat object names to associate placement with
        # source IDs. They are the same printed name, not another text instance.
        if label.get("role") == "object" and set(label.get("source_node_ids", [])) & drawn_sources:
            continue
        text_items.append(label.get("text", ""))
    text_items.extend(figure.get("behavior_plan", {}).get("axis", []))
    burden = {"top_level_objects": len(nodes), "nested_appearances": len(nested), "leaf_appearances": len(root_leaves),
              "unique_source_leaves": len({item["source_node_id"] for item in root_leaves if item["source_node_id"]}),
              "text_items": len(text_items), "text_characters": sum(len(text) for text in text_items),
              "visible_connections": route_count, "source_relationships_in_view": len({index for edge in edges for index in edge.get("members", [])}),
              "max_incoming": max(incoming.values(), default=0), "max_outgoing": max(outgoing.values(), default=0),
              "ownership_depth": max((len(item["source_owner_path"]) for item in appearances), default=0),
              "exact_or_conditional_relations": sum(bool(_EXACT.search(edge.get("label", ""))) for edge in edges),
              "counts_basis": basis + "; actual nested label occurrences and same-hardware expansions, not only macro boxes"}
    pressure = []
    if len(root_leaves) > 20:
        pressure.append("More than 20 visible leaf appearances; choose a narrower reader question or a representative expansion before shrinking type.")
    if route_count > 24:
        pressure.append("More than 24 visible connections; separate source-backed data/control or ownership perspectives if their reading tasks differ.")
    if max(burden["max_incoming"], burden["max_outgoing"]) >= 6:
        pressure.append("A six-or-more-path endpoint requires dedicated connector/label corridors; adjacency must not imply a shared electrical junction.")
    quality = figure.get("layout_scene", {}).get("quality", {})
    if quality.get("routes_complete") is False:
        pressure.append("The compiled guide has untraceable connections; redesign or use a different selected perspective before Image Gen.")
    if quality.get("document_fit", {}).get("status") == "limited":
        pressure.append("The fixed document type scale exceeds this page height; split the reader task or give this view a separate page.")
    perspectives = []
    for gid in groups:
        scope = [nid for nid, node in sources.items() if gid in _owner_path(node.get("group", ""), groups)]
        if 2 <= len(scope) <= 20 and set(scope) != set(sources):
            perspectives.append({"kind": "real-owner-detail", "source_group": gid, "source_node_ids": scope,
                                 "context_policy": "Original outside endpoints may be context; never reparent them."})
    if any(edge["kind"] == "data" for edge in spec.get("edges", [])) and any(edge["kind"] in {"control", "clock"} for edge in spec.get("edges", [])):
        for name, kinds in [("payload-path", {"data", "relation"}), ("control-interaction", {"control", "clock", "feedback"})]:
            perspectives.append({"kind": name, "source_edge_indices": [index for index, edge in enumerate(spec["edges"]) if edge["kind"] in kinds],
                                 "context_policy": "Return data semantics remain on the payload view; edge kind alone never changes their meaning."})
    mathematical_roles = {item["source_node_id"]: item["role"] for item in figure.get("algorithm_flow_plan", {}).get("objects", [])}
    roles = []
    for nid in dict.fromkeys(item["source_node_id"] for item in appearances if item["source_node_id"]):
        node = sources[nid]
        role = mathematical_roles.get(nid) or node.get("diagram_role") or node.get("kind", "resource")
        symbol = ("mathematical-object" if role in {"tensor", "index"} else
                  "named-mathematical-operator" if role in {"operator", "reduction"} else
                  "state-circle" if node.get("kind") == "state" or spec.get("category") == "fsm" and node.get("kind") in {"compute", "stage"} else
                  "predicate-diamond" if node.get("kind") == "decision" else
                  "signal-row" if spec.get("category") == "timing" else
                  "storage-glyph" if node.get("kind") == "memory" else "plain-functional-symbol")
        roles.append({"source_node_id": nid, "role": role, "symbol": symbol,
                      "basis": "supplied semantic role/type or source-backed mathematical interpretation; geometry adds no operation"})
    instructions = [strategy["convention"],
                    "Make the main question visually dominant; use consistent role silhouettes and stronger resource names, with subdued real ownership labels. Whitespace belongs to independent paths, labels and related clusters rather than equal padded cards.",
                    "Use consistent semantic role fills from the selected graphic language and neutral secondary marks. Emphasis follows the reading structure; meaning must remain clear through position, shape, line style and text in grayscale. Color never implies unsupplied semantics."]
    if repeated:
        instructions.append("Repetition follows the actual plate: preserve each shown expanded private inventory and each compact peer. A same-hardware inset is explanatory; its leader has no data arrowhead.")
    if figure.get("context_nodes"):
        instructions.append("Context objects retain their original owner and stay outside unrelated private/system boundaries; closeness does not imply containment.")
    return {"version": POLICY_VERSION, "source_hash": _hash(spec), "reading_question": strategy["reading_question"],
            "reading_strategy": strategy, "inventory": {"basis": basis, "appearances": appearances,
                "top_level_ids": ids, "same_hardware_expansions": sorted(inset_sources)}, "burden": burden,
            "ownership": {"source_group_parents": {gid: group.get("parent", "") for gid, group in groups.items()},
                "context_node_ids": list(figure.get("context_nodes", [])),
                "display_bands_are_not_owners": True, "boundary_rule": "Only actual source containment encloses resources; layout bands/roles never create hardware ownership."},
            "role_plan": roles, "repeated_instances": repeated,
            "connection_plan": {"primary_source_edges": list(figure.get("source_edge_indices", figure.get("edge_indices", []))),
                "fork_nodes": [nid for nid in ids if outgoing[nid] > 1], "join_nodes": [nid for nid in ids if incoming[nid] > 1],
                "source_kind_and_endpoint_lock": True, "junction_policy": "Crossings do not merge; only supplied logical junction/operator/resource permits a shared endpoint."},
            "typography": {"target_width_mm": figure.get("design_contract", {}).get("target_width_mm", 160),
                "body_pt": figure.get("design_contract", {}).get("body_pt", 9), "signal_pt": figure.get("design_contract", {}).get("signal_pt", 8.5),
                "hierarchy": "resource/operand names, then exact notation, then quiet ownership/context",
                "label_economy": "Name once on each visible object; preserve exact predicates, quantities and expressions. Optional explanations belong in caption; never replace mathematical meaning with a decorative icon.",
                "overflow_policy": "Wrap or recompose/split the reading task before reducing the established document type scale."},
            "composition_action": {"status": "recompose" if pressure else "planned" if figure.get("structure_layout") or figure.get("algorithm_flow_plan") or figure.get("render_brief") else "uncontrolled",
                "geometry_controlled": bool(figure.get("requires_layout_guide") and figure.get("structure_layout")),
                "typography_measured": bool(layout.get("typography") and layout.get("symbol_metrics")),
                "reasons": pressure, "source_backed_perspectives": perspectives,
                "not_aesthetic_certification": True}, "render_instructions": instructions,
            "acceptance_checks": ["The reader can answer the selected question by following the actual figure.",
                "Nested contents, private/common ownership, external boundary and real instance count agree with the selected source projection.",
                "Each path is traceable to its source endpoint, target and direction; independent branches never appear serial or accidentally merged.",
                "Names, essential expressions and predicates are readable at the intended document size; inspect that size separately from a full-resolution image.",
                "Visual hierarchy, whitespace and line encodings remain meaningful without color; no ornamental symbols or connections add facts."],
            "actual_image_status": "not_reviewed"}


def caption(plan):
    """Short reader-facing explanation; burden metadata stays in the project."""
    return "Reading task: " + plan["reading_question"] + "\nDisplay organization: " + plan["reading_strategy"]["convention"]


def reconcile_scope_metadata(spec, figure):
    """Reconcile decision records with the actual controlled fallback only.

    Earlier reader-task projections stay immutable and auditable. This updates
    derived diagnostics after composition, not source, geometry or image text.
    """
    import copy
    diagnostics = copy.deepcopy(figure.get("projection_diagnostics", {}))
    if not diagnostics:
        return diagnostics
    scene = figure.get("layout_scene", {})
    routes = scene.get("routes")
    if scene.get("quality", {}).get("routes_complete") is not True or not isinstance(routes, list) or any(not route.get("members") for route in routes):
        diagnostics["actual_scope"] = {"accounting_status": "not_checked",
                                        "limitations": ["No complete controlled route manifest is available to reconcile actual scope."]}
        return diagnostics
    shown = {index for route in routes for index in route["members"]}
    if any(not isinstance(index, int) or not 0 <= index < len(spec["edges"]) for index in shown):
        diagnostics["actual_scope"] = {"accounting_status": "not_checked",
                                        "limitations": ["Controlled routes contain an unrecognized source relationship index."]}
        return diagnostics
    declared = set(figure.get("source_edge_indices", figure.get("edge_indices", [])))
    deferred = {item["index"] for item in figure.get("projection", {}).get("deferred_edges", [])}
    burden = figure["diagram_design"]["burden"]
    actual = {"accounting_status": "reconciled-from-controlled-scene", "layout_method": figure.get("layout_strategy", ""),
              "visible_objects": burden["top_level_objects"], "nested_appearances": burden["nested_appearances"],
              "leaf_appearances": burden["leaf_appearances"], "visible_relationships": len(routes),
              "source_edge_indices": sorted(shown), "declared_source_edge_indices": sorted(declared),
              "additional_source_edge_indices": sorted(shown - declared),
              "declared_deferred_now_visible": sorted(shown & deferred), "limitations": []}
    if actual["additional_source_edge_indices"] or actual["declared_deferred_now_visible"]:
        actual["limitations"].append("The controlled fallback shows additional source relationships that the earlier reading projection deferred. Actual scope follows the controlled scene; the original projection is retained for traceability.")
    for candidate in diagnostics.get("candidates", []):
        if not candidate.get("selected"):
            continue
        candidate["attempted_scope"] = {key: candidate[key] for key in ("visible_objects", "visible_relationships", "deferred_primary_relationships") if key in candidate}
        candidate.update(visible_objects=actual["visible_objects"], visible_relationships=actual["visible_relationships"],
                         source_edge_indices=actual["source_edge_indices"], actual_layout_method=actual["layout_method"],
                         additional_source_edge_indices=actual["additional_source_edge_indices"])
    diagnostics["actual_scope"] = actual
    return diagnostics


def figure_strategy(spec, figure):
    """Expose the actual chosen reading task consistently in Web and MCP.

    This is a concise derived explanation of existing compiler decisions. It
    never supplies a second specification, selects geometry or certifies pixels.
    """
    design = figure["diagram_design"]
    contract = figure.get("design_contract", {})
    explanation = figure.get("render_brief", {}).get("explanation_plan", {})
    algorithm = figure.get("algorithm_flow_plan", {})
    semantic = figure.get("behavior_plan", {})
    purpose = explanation.get("reading_question") or design["reading_question"]
    how = design["reading_strategy"]["convention"]
    if explanation:
        scope_lines = explanation.get("visible_summary", [])
        how = "; ".join(scope_lines) or how
        how += ". " + explanation.get("semantic_role", "Source-backed conceptual explanation.")
    elif algorithm:
        how = algorithm.get("composition", {}).get("primary_reading_axis", how)
        how += ". Independent operands and branches stay separate; state updates and returns retain their original endpoints."
    elif semantic:
        how = semantic.get("reading_direction") or figure.get("structure_layout", {}).get("canvas", {}).get("reading_direction") or how
        how += ". " + design["reading_strategy"]["convention"]
    visible = figure.get("render_brief", {}).get("visible_content", {})
    if visible:
        shown_edges = {index for edge in visible.get("relationships", []) for index in edge.get("source_edge_indices", [])}
    elif algorithm:
        shown_edges = {edge["source_edge_index"] for edge in algorithm.get("relations", [])}
    else:
        routes = figure.get("layout_scene", {}).get("routes")
        edges = routes if isinstance(routes, list) else figure.get("macro_edges", [])
        shown_edges = {index for edge in edges for index in edge.get("members", [])}
        if not edges and not figure.get("abstract"):
            shown_edges = set(figure.get("edge_indices", []))
    # Sample rows encode values/events, not arbitrary graph arrows. If a timing
    # source additionally declares relationships, the current table compiler
    # has no per-relation visual carrier contract; do not call them rendered or
    # silently recategorize them as deferred engineering details.
    unchecked_edges = set()
    if semantic.get("grammar") == "sampled-timing" and spec["edges"]:
        shown_edges = set()
        unchecked_edges = set(range(len(spec["edges"])))
    actual_scope = figure.get("projection_diagnostics", {}).get("actual_scope", {})
    limits = [*design["composition_action"]["reasons"], *actual_scope.get("limitations", [])]
    if figure.get("design_limit"):
        limits.append(figure["design_limit"])
    if figure.get("layout_strategy") == "legacy-technical-annex":
        limits.append("This scope uses the historical layout and has not passed the current physical typography preflight.")
    projection = figure.get("projection", {})
    internal = projection.get("internal_edges", [])
    if internal:
        limits.append(str(len(internal)) + " selected source relationships are internal to summarized owners; inspect their exact technical companions for mechanism details.")
    quality = figure.get("layout_scene", {}).get("quality", {})
    if quality.get("routes_complete") is False:
        limits.append("At least one selected relationship has no complete controlled route.")
    document = quality.get("document_fit", {})
    if document.get("status") == "limited":
        limits.append("The selected document width produces a figure " + str(document.get("height_mm")) + " mm high; its reading scope still needs a separate page or decomposition.")
    controlled = bool(figure.get("structure_layout") and quality.get("routes_complete") is True)
    status = "limited" if limits or figure.get("layout_strategy") == "text-only" else "controlled" if controlled else "planned"
    return {"version": "FS1", "figure_id": figure["id"], "purpose": purpose,
            "representation": figure.get("representation", "diagram"),
            "grammar": explanation.get("mode") or semantic.get("grammar") or ("mathematical-dependency" if algorithm else contract.get("grammar", "")),
            "how_to_read": how, "planning_status": status,
            "scope": {"source_nodes": len(spec["nodes"]), "source_relationships": len(spec["edges"]),
                      "visible_objects": design["burden"]["top_level_objects"],
                      "top_level_objects": design["burden"]["top_level_objects"],
                      "nested_appearances": design["burden"]["nested_appearances"],
                      "leaf_appearances": design["burden"]["leaf_appearances"],
                      "visible_relationships": design["burden"]["visible_connections"],
                      "visible_source_relationships": sorted(shown_edges),
                      "deferred_relationships": None if unchecked_edges else len(set(range(len(spec["edges"]))) - shown_edges),
                      "relationship_accounting_status": "not_checked" if unchecked_edges else "source_mapped",
                      "not_checked_source_relationships": sorted(unchecked_edges),
                      "deferred_primary_relationships": len(internal)},
            "assumptions": {"statements": list(spec.get("assumptions", [])),
                            "assumed_nodes": sum(node.get("origin") == "assumed" for node in spec["nodes"]),
                            "assumed_relationships": sum(edge.get("origin") == "assumed" for edge in spec["edges"])},
            "limitations": list(dict.fromkeys(limits)),
            "alternatives": figure.get("projection_diagnostics", {}).get("candidates", []),
            "actual_scope_accounting_status": actual_scope.get("accounting_status", "not_checked" if unchecked_edges else "source_mapped"),
            "document_size_status": "not_checked",
            "guide_document_fit_status": document.get("status", "not_measured"),
            "actual_image_status": "not_reviewed", "not_aesthetic_certification": True}
