"""Model-neutral handoff for auditing an actual generated bitmap."""
from __future__ import annotations
import json
from . import publication_brief


def build(spec, figure, source_hash):
    if figure.get("behavior_plan"):
        semantic=figure["behavior_plan"]
        actual_scope=figure.get("projection_diagnostics",{}).get("actual_scope",{})
        manifest={"figure_id":figure["id"],"source_hash":source_hash,"status":"not_reviewed",
                  "representation":"diagram","scope":"source-backed semantic guide",
                  "semantic_plan":semantic,"source_scope":actual_scope.get("source_edge_indices",figure.get("source_edge_indices",[])),
                  "declared_source_scope":figure.get("source_edge_indices",[]),
                  "actual_scope_accounting_status":actual_scope.get("accounting_status","not_checked" if semantic["grammar"]=="sampled-timing" and spec["edges"] else "source_mapped"),
                  "source_objects":[{"id":n["id"],"label":n["label"],"owner":n["group"],"detail":n["detail"]} for n in spec["nodes"]],
                  "source_groups":spec["groups"],"source_conventions":spec["annotations"],
                  "record_fields":["technical_verdict","reading_verdict","visual_verdict","text_verdict","document_size_verdict","failed_relations","evidence","limits"],
                  "decision":"Inspect actual pixels. Source identity, layout metadata and entry-point parity do not certify an image."}
        specific={
            "state-machine":"Trace every source state transition INCLUDING self-loops and exact competing predicates. State transitions are solid arrows, not dashed hardware control. Initial/reset markers may summarize explicitly supplied global entry/reset behavior and are not extra transition states. Check state outputs, priority, retry actions and unconditional exits.",
            "sampled-timing":"Compare EACH named sample value and signal row against the semantic plan. Check stalled-data stability and actual events at their supplied columns. Rising sample markers are not payload arrows. Between-edge timing and duty cycle are unspecified; do not certify fabricated continuous waveforms.",
            "logical-topology":"Trace every original directed link, attached endpoint and request/response meaning. Check logical mesh adjacency and absent diagonal/shortcut links. Drawing embeddings convey topology, not physical placement, area or latency. Preserve real source ownership and external boundaries.",
            "directed-process":"Trace forward payload, independent operands, branch/merge and same-resource return. Check each numerical capacity/selection parameter and reverse ready/control path. Source stages express function, not unsupplied clock latency. Distinguish actual private/shared resources and do not invent buses or a join operation."}[semantic["grammar"]]
        prompt="\n".join(["Inspect the actual Image Gen bitmap against this semantic source manifest. Do not edit or redraw it.",specific,
                           "Separately judge hierarchy, meaningful grouping, path continuity, label economy and appearance. A layout that preserves names but makes the task hard to follow is insufficient.",
                           "Document-size legibility is not_checked without a rendering at the actual intended width. Technical errors reject the image; do not excuse them as style.",
                           json.dumps(manifest,ensure_ascii=False,indent=2)])
        return {**manifest,"prompt":prompt}
    if figure.get("algorithm_flow_plan"):
        plan = figure["algorithm_flow_plan"]
        manifest = {"figure_id": figure["id"], "source_hash": source_hash, "status": "not_reviewed",
                    "scope": "complete source-backed algorithm dependency graph", "has_controlled_plate": False,
                    "objects": plan["objects"], "expected_connections": plan["relations"],
                    "source_scope": figure["source_edge_indices"], "groups": plan["groups"],
                    "motifs": plan["motifs"], "composition": plan["composition"],
                    "required_verbatim_labels": figure.get("required_verbatim_labels", []),
                    "record_fields": ["technical_verdict", "reading_verdict", "visual_verdict", "text_verdict", "document_size_verdict", "failed_relations", "evidence", "limits"],
                    "decision": "Judge the actual algorithm figure, not source counts or compiler confidence. Mathematical, dependency or state-update errors reject the bitmap."}
        prompt = "\n".join([
            "Inspect the actual attached Image Gen algorithm/dataflow bitmap against the scoped manifest below; do not redraw it.",
            "Trace every named operand, operator output, parallel branch, join and source cycle. Check exact directed endpoints and arrowheads; reject accidental serial Q/K/V-like inputs, bypasses entering the wrong operator, missing state dependencies, extra operators or unexplained merges. A fan-in does not imply a reduction unless its supplied operator says so.",
            "Check supplied tensor shapes, contraction/reduction axes, equations, masks and predicates. A reduction may produce a tensor; do not require a scalar result. Where shapes belong to an operator they describe its output, not physical dimensions. Long non-mathematical explanation may stay in the caption, but essential expressions and assigned shape labels must be readable on their matching object/path.",
            "Check state initialization and previous/new-state direction, and distinguish a loop exit predicate from a recurrence. Check supplied residency and reuse without fabricating SRAM capacities, tensor grid counts, full intermediates, repeated hardware copies or a pipeline schedule. Source feedback marked as a mathematical state operand may use a solid return arrow.",
            "Assess mathematical reading order, independent branch spacing, distinct tensor/operator/state silhouettes, restrained palette, legibility and path ambiguity. Group brackets/bands organize real members and cannot replace their mathematics with a collapsed stage card. Mathematical role inference is a graphical interpretation, not permission to invent an operation.",
            "Return the record_fields with pass/partial/fail/not_checked and observed visual evidence. Physical document-width readability is not_checked without an actual width rendering. A valid source graph, prompt or plan does not certify the bitmap.",
            json.dumps(manifest, ensure_ascii=False, indent=2)])
        return {**manifest, "prompt": prompt}
    if figure.get("representation") in {"product_render", "system_illustration"}:
        brief = figure.get("render_brief", {})
        explanation = brief.get("explanation_plan", {})
        manifest = {"figure_id": figure["id"], "source_hash": source_hash, "status": "not_reviewed",
                    "representation": figure["representation"], "scope": "product render or spatial illustration",
                    "subject": brief.get("subject", {}), "art_direction": brief.get("art_direction", {}),
                    "visible_content": brief.get("visible_content", {}),
                    "explanation_plan": explanation,
                    "appearance": brief.get("appearance", {}), "semantic_contract": brief.get("semantic_contract", {}),
                    "framing_reference_is_optional": True, "no_cad_or_die_layout_certification": True,
                    "record_fields": ["technical_verdict", "representation_verdict", "visual_verdict", "text_verdict", "evidence", "limits"],
                    "decision": "Review the selected explanatory scope and art direction. A hero may defer internals; a functional illustration must communicate its planned regions, ownership and selected relationships. Conceptual placement is not measured manufacturing geometry."}
        prompt = "\n".join([
            "Inspect the actual Image Gen image against its selected explanatory mode and reader question. Evaluate what a viewer can understand, as well as the product rendering.",
            "Check the subject, coherent camera and scale, materials, light, purposeful regional hierarchy, readable labels and meaningful relationships. Functional regions on an illustrative chip plane and source-backed schematic context are valid visual methods. Judge their organization and clarity rather than rejecting them merely for being logical overlays.",
            "Check each planned logical region, its source membership and ownership. Trace selected relationships to source indices and their directionality. A source-directed data/control/feedback/clock relationship needs a discreet target direction mark at its actual endpoint; opposite flows remain separately traceable. Only an association/interface relationship may be an unheaded link. A quiet hero with no selected links needs no arrows. Do not require deferred engineering details in the image.",
            "Preserve explicit visible facts, quantities and exact text. Symbolic devices, interface glyphs and generic connector appearances may explain known functions; they must not silently become additional source instances, a pin count, measured floorplan, actual package stack or certified bill of materials. Reject fabricated performance and unsupplied brand claims.",
            "Treat declared conceptual geometry as visual explanation. A hero may hide internals; a functional view must show its chosen structure. Facts not visually verifiable remain not_checked, rather than being invented or falsely certified.",
            "Check that supplied physical assembly information is respected when given. Do not demand detailed electrical arrows for a product hero image, or enforce the optional framing sketch as exact object geometry.",
            "Return the record_fields with pass/partial/fail/not_checked and observed visual evidence. A good render does not validate the chip architecture or the whole system.",
            json.dumps(manifest, ensure_ascii=False, indent=2)
        ])
        return {**manifest, "prompt": prompt}
    nodes = {n["id"]: n for n in spec["nodes"]}
    groups = {g["id"]: g["label"] for g in spec["groups"]}
    parents = {g["id"]: g["parent"] for g in spec["groups"]}
    objects = figure.get("macro_nodes", []) if figure.get("abstract") else [nodes[nid] for nid in figure["node_ids"]]
    displayed = {o["id"]: o["label"] for o in objects}
    relations = []
    routes = figure.get("layout_scene", {}).get("routes")
    basis = "planned display routes" if isinstance(routes, list) else "source-backed relationships; geometry unplanned"
    if not isinstance(routes, list):
        routes = figure.get("macro_edges") if figure.get("abstract") else [{**spec["edges"][i], "members": [i]} for i in figure.get("edge_indices", [])]
    for e in routes or []:
        relations.append({"source": displayed.get(e["source"], e["source"]),
                          "target": displayed.get(e["target"], e["target"]),
                          "bidirectional": bool(e.get("bidirectional")),
                          "kind": e["kind"], "stroke_style": e.get("stroke_style"), "meaning": e.get("label", ""), "source_edge_indices": e.get("members", [])})
    objects_manifest = []
    for o in objects:
        members = o.get("members", [o["id"]])
        gid = o.get("original_group", o.get("group", ""))
        ancestors = []
        while gid in groups:
            ancestors.append(groups[gid])
            gid = parents[gid]
        facts = [{"label": nodes[nid]["label"], "owner": groups.get(nodes[nid]["group"], ""),
                  "detail": nodes[nid].get("detail", "")} for nid in members if nid in nodes]
        objects_manifest.append({"label": o["label"], "source_members": members,
                                 "original_owner_path": ancestors,
                                 "children": [c["label"] for c in o.get("children", [])],
                                 "source_facts": facts,
                                 "same_hardware_as": displayed.get(o.get("equivalent_to"), o.get("equivalent_to", ""))})
    manifest = {"figure_id": figure["id"], "source_hash": source_hash, "status": "not_reviewed",
                "scene": figure.get("design_contract", {}).get("scene_id", "legacy"),
                "reader_purpose": figure.get("design_contract", {}).get("reader_purpose", ""),
                "concept_frame": figure.get("concept_frame"),
                "scope": figure.get("design_contract", {}).get("scope"),
                "target_width_mm": figure.get("design_contract", {}).get("target_width_mm",160),
                "objects": objects_manifest,
                "required_verbatim_labels": figure.get("required_verbatim_labels", []),
                "planned_labels": [{"text": l["text"], "source_edge_indices": l.get("source_edge_indices", [])} for l in figure.get("label_layout", {}).get("labels", [])],
                "has_controlled_plate": bool(figure.get("requires_layout_guide")),
                "expected_connections": relations, "connection_basis": basis, "counts": publication_brief.connection_contract(figure),
                "source_scope": figure.get("source_edge_indices",figure.get("edge_indices",[])),
                "record_fields": ["technical_verdict","reading_verdict","visual_verdict","document_size_verdict","failed_relations","evidence","limits"],
                "decision": "Technical failure rejects this bitmap. Recompose/regenerate from clean source; never certify from source coverage or prompt confidence."}
    prompt = "\n".join([
        "Inspect the actual attached Image Gen bitmap, using the scoped manifest below. Do not redraw or edit it.",
        "Review the bitmap itself: trace every source/target, direction, arrowhead, required text and original ownership. Identify extra connectors, reverse heads, missing paths, mixed independent inputs, or unintended hardware duplication.",
        "A scope projection may summarize only its recorded source members. A same-hardware detail inset is not another instance. Its explanatory leader must have no data arrowhead.",
        "Source_facts describe the immutable engineering ledger. Optional prose may remain in the caption; require the planned labels, verbatim labels, quantities and predicates assigned to this figure. Do not require deferred caption prose to become image text.",
        "Separately assess reading order, hierarchy, typography, meaningful whitespace and path ambiguity. Assess document-size readability only if a true physical-width rendering is attached; otherwise mark it not_checked.",
        "Judge the requested purpose: a product concept must explain the whole stated system and its functional regions without implementation clutter; an architecture view must explain real ownership and interfaces; a data journey must make source-backed paths readable; a detail view must cover its selected implementation scope. A chip-shaped enclosure is illustrative unless explicitly grounded; never certify its placement as a physical floorplan.",
        "Do not infer acceptance from valid JSON, source counts, the guide, a compiler quality field or a nicer appearance. An image is not automatically passed because all names appear.",
        "Return JSON with the record_fields in the manifest. technical_verdict, reading_verdict and visual_verdict are pass/partial/fail/not_checked. Quote observed visual evidence and list material limits. No numerical beauty score.",
        "Manifest (IDs and counts are audit data, never new image text):",
        json.dumps(manifest,ensure_ascii=False,indent=2)
    ])
    return {**manifest,"prompt":prompt}
