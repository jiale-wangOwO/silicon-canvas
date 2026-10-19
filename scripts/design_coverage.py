"""Independent, original coverage sources and cross-entry-point invariants.

This module is verification tooling, not a production planner. A passed
contract is deliberately not an aesthetic or technical acceptance of pixels.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "design_coverage"
CASES = ("repeated-ingress", "heterogeneous-instrument", "branched-tile-return",
         "residual-projection", "retry-controller", "ready-valid-trace",
         "elastic-pipeline", "mesh-memory", "commercial-context",
         "commercial-cutaway", "commercial-hero", "sparse-acquisition")
REPRESENTATIVE_CASES = ("repeated-ingress", "retry-controller", "ready-valid-trace",
                        "elastic-pipeline", "mesh-memory", "residual-projection",
                        "commercial-context", "commercial-cutaway", "commercial-hero",
                        "sparse-acquisition", "heterogeneous-instrument", "branched-tile-return")


def source(name):
    if name not in CASES:
        raise ValueError("Unknown coverage case")
    return json.loads((FIXTURES / (name + ".json")).read_text(encoding="utf-8"))


def canonical_digest(spec):
    return hashlib.sha256(json.dumps(spec, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def selected(result):
    return next(figure for figure in result["figures"] if figure["id"] == result["selected_figure_id"])


def owner_path(node, groups):
    path, current = [], node["group"]
    while current:
        path.append(current)
        current = groups[current]["parent"]
    return list(reversed(path))


def assert_case_semantics(name, payload, figure):
    """Case-specific correctness gates are shared by native, Worker and MCP."""
    spec = payload["spec"]
    if name in {"retry-controller", "mesh-memory", "elastic-pipeline", "branched-tile-return"}:
        assert {node["id"] for node in figure["macro_nodes"]} == {node["id"] for node in spec["nodes"]}, name + ": lost actual resources"
        assert len(figure["macro_edges"]) == len(spec["edges"]), name + ": lost or merged directed relations"
        assert sorted(index for edge in figure["macro_edges"] for index in edge["members"]) == list(range(len(spec["edges"])))
        for edge in figure["macro_edges"]:
            assert len(edge["members"]) == 1 and not edge.get("bidirectional"), name + ": distinct senses merged"
            original = spec["edges"][edge["members"][0]]
            assert all(edge[field] == original[field] for field in ("source", "target", "kind", "label")), name + ": directed meaning changed"
    if name == "ready-valid-trace":
        timing = figure["structure_layout"]
        assert timing["axis"] == [f"c{i}" for i in range(8)]
        rows = {item["id"]: item for item in timing["rows"]}
        assert rows["clk"]["kind"] == "sample-markers" and rows["clk"]["values"] == []
        for node in spec["nodes"]:
            if node["id"] != "clk":
                assert rows[node["id"]]["values"] == node["detail"].split(": ", 1)[1].split()
    if name == "residual-projection":
        plan = figure["algorithm_flow_plan"]
        assert len(plan["objects"]) == len(spec["nodes"])
        assert len(plan["relations"]) == len(spec["edges"])
        for index, relation in enumerate(plan["relations"]):
            assert relation["source_edge_index"] == index
            assert all(relation[field] == value for field, value in spec["edges"][index].items())
    if name == "repeated-ingress":
        mapping = figure["projection"]["source_node_to_macro"]
        assert set(mapping) == {node["id"] for node in spec["nodes"]}
        objects = {item["id"]: item for item in figure["macro_nodes"]}
        for i in range(4):
            gid = f"lane{i}"
            members = [node["id"] for node in spec["nodes"] if node["group"] == gid]
            assert gid in objects and objects[gid]["label"] == f"Ingress Lane {i}"
            assert set(objects[gid]["members"]) == set(members)
            assert all(mapping[node_id] == gid for node_id in members)
        shown = [index for edge in figure["macro_edges"] for index in edge["members"]]
        internal = figure["projection"]["internal_edges"]
        assert sorted(shown + internal) == list(range(len(spec["edges"])))
    if name.startswith("commercial-"):
        mode = {"commercial-context": "annotated_context", "commercial-cutaway": "functional_cutaway", "commercial-hero": "hero"}[name]
        assert figure["render_brief"]["explanation_plan"]["mode"] == mode
    if name == "sparse-acquisition":
        assert all(item["origin"] == "assumed" and not item["evidence"] for item in spec["nodes"] + spec["edges"])
        if figure.get("render_brief"):
            assert figure["render_brief"]["explanation_plan"]["mode"] != "hero"
    if not figure.get("algorithm_flow_plan") and not figure.get("render_brief"):
        assert figure.get("structure_layout"), name + ": engineering drawing has no controlled layout"
        assert figure["layout_strategy"] not in {"text-only", "legacy-technical-annex"}, name + ": unmanaged layout fallback"


def assert_contract(name, payload, result):
    """Check canonical facts and independently recompute display accounting."""
    spec = payload["spec"]
    assert result["spec"] == spec, name + ": source facts or metadata changed"
    assert result["source_hash"] == canonical_digest(spec)
    nodes = {node["id"]: node for node in spec["nodes"]}
    groups = {group["id"]: group for group in spec["groups"]}
    for figure in result["figures"]:
        plan = figure["diagram_design"]
        assert plan["version"] == "DGP1"
        assert plan["source_hash"] == result["source_hash"]
        assert plan["actual_image_status"] == figure["review_task"]["status"] == "not_reviewed"
        assert plan["reading_question"] and plan["reading_strategy"]["kind"]
        appearances = plan["inventory"]["appearances"]
        paths = [tuple(item["display_path"]) for item in appearances]
        assert len(paths) == len(set(paths)), name + ": duplicated visual appearance identity"
        for item in appearances:
            if item["source_node_id"]:
                node = nodes[item["source_node_id"]]
                assert item["source_owner_path"] == owner_path(node, groups), name + ": invented ownership"
                assert item["label"] == node["label"], name + ": source-backed appearance label changed"
        burden = plan["burden"]
        leaves = [item for item in appearances if not item["has_children"]]
        assert burden["top_level_objects"] == len(plan["inventory"]["top_level_ids"])
        assert burden["nested_appearances"] == sum(len(item["display_path"]) > 1 for item in appearances)
        assert burden["leaf_appearances"] == len(leaves)
        assert burden["unique_source_leaves"] == len({item["source_node_id"] for item in leaves if item["source_node_id"]})
        assert burden["text_characters"] >= sum(len(line) for item in appearances for line in item["printed_lines"])
        assert burden["ownership_depth"] == max((len(item["source_owner_path"]) for item in appearances), default=0)
        assert plan["composition_action"]["status"] in {"planned", "recompose", "uncontrolled"}
        assert all(item["source_node_ids"] for item in plan["composition_action"].get("source_backed_perspectives", []) if "source_node_ids" in item)
        layout = figure.get("structure_layout", {})
        # Recompute a floor from the actual glyph plan, not DGP's own inventory.
        # Required numeric details printed under a name are drawing work too.
        def printed_glyphs(metrics):
            texts = [*metrics.get("lines", []), *metrics.get("detail_lines", [])]
            for child in metrics.get("children", []):
                if isinstance(child, dict):
                    texts.extend(printed_glyphs(child))
            return texts
        metric_text = [line for metrics in layout.get("symbol_metrics", {}).values() for line in printed_glyphs(metrics)]
        for inset in layout.get("insets", []):
            metric_text.extend(printed_glyphs(inset.get("metrics", {})))
        assert burden["text_characters"] >= sum(len(line) for line in metric_text), name + ": printed details missing from burden"
        typography = layout.get("typography", {})
        if typography:
            assert typography.get("no_font_shrink"), name + ": layout shrinks body text"
            body_px = typography.get("body_px", 0)
            for metrics in layout.get("symbol_metrics", {}).values():
                if "font_px" in metrics:
                    assert metrics["font_px"] >= body_px
    figure = selected(result)
    assert figure.get("primary") and not figure.get("technical_annex", False), name + ": primary fell back to an annex"
    assert_case_semantics(name, payload, figure)
    return figure


def assert_bundle(pack, payload, result, figure, guide=None):
    portable = json.loads(pack.read("result.json"))
    assert portable["spec"] == payload["spec"]
    assert portable["source_hash"] == result["source_hash"]
    zipped = next(item for item in portable["figures"] if item["id"] == figure["id"])
    assert zipped["diagram_design"] == figure["diagram_design"]
    prefix = "figures/" + figure["id"] + "/"
    assert pack.read(prefix + "prompt.txt").decode("utf-8") == figure["prompt"]
    assert pack.read(prefix + "caption.txt").decode("utf-8") == figure["caption"]
    assert json.loads(pack.read(prefix + "review-manifest.json"))["status"] == "not_reviewed"
    if guide is not None:
        filename = "composition-guide.png" if figure.get("render_brief") else "layout-guide.png"
        assert pack.read(prefix + filename) == guide


def report_case(name, payload, result):
    figure = selected(result)
    plan = figure["diagram_design"]
    return {"case": name, "source_hash": result["source_hash"],
            "source_nodes": len(payload["spec"]["nodes"]), "source_edges": len(payload["spec"]["edges"]),
            "representation": figure.get("representation"), "reading_kind": plan["reading_strategy"]["kind"],
            "display_burden": plan["burden"], "composition_action": plan["composition_action"]["status"],
            "source_and_actual_display_accounting": "passed", "review_status": "not_reviewed",
            "bitmap_quality": "not_certified_by_software"}
