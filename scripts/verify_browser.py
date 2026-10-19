"""Real Chromium/Worker checks under a Pages-style subpath; no key by default."""
from __future__ import annotations

import argparse
import base64
from functools import partial
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import threading
import zipfile

from PIL import Image
from playwright.sync_api import sync_playwright
from silicon_canvas.browser_bridge import dispatch
from silicon_canvas import engine, layout_guide
from verify_workbench import verify_workbench
from design_coverage import (REPRESENTATIVE_CASES as DESIGN_CASES, source as design_source,
                             assert_contract as assert_design_contract,
                             assert_bundle as assert_design_bundle, report_case as design_report_case)
from verify_mcp_executable import (ALGORITHM_FIXTURES, assert_algorithm_bundle, assert_algorithm_contract,
                                   bounded_hardware_fixture, assert_bounded_hardware_contract, assert_bounded_hardware_bundle)

ROOT = Path(__file__).resolve().parent.parent


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass


def digest(data):
    return hashlib.sha256(data).hexdigest()


def first_difference(a, b, path="root"):
    if type(a) is not type(b):
        return f"{path}: {type(a).__name__} vs {type(b).__name__}"
    if isinstance(a, dict):
        if set(a) != set(b):
            return f"{path}: dictionary keys differ"
        for key in a:
            if a[key] != b[key]:
                return first_difference(a[key], b[key], path + "." + key)
    elif isinstance(a, list):
        if len(a) != len(b):
            return f"{path}: length {len(a)} vs {len(b)}"
        for index in range(len(a)):
            if a[index] != b[index]:
                return first_difference(a[index], b[index], path + f"[{index}]")
    return f"{path}: {str(a)[:120]!r} vs {str(b)[:120]!r}"


def assert_result_equal(native, wasm, output, case):
    if wasm != native:
        for name, result in [("native", native), ("wasm", wasm)]:
            (output / f"{case}-{name}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        raise AssertionError(f"{case}: browser/native result differs: " + first_difference(native, wasm))


def assert_guide_equal(native, wasm, case):
    for field in ("mime", "filename", "role", "optional"):
        assert native.get(field) == wasm.get(field), f"{case}: guide {field} differs"
    a = Image.open(io.BytesIO(base64.b64decode(native["base64"]))).convert("RGB")
    b = Image.open(io.BytesIO(base64.b64decode(wasm["base64"]))).convert("RGB")
    assert a.size == b.size and a.tobytes() == b.tobytes(), f"{case}: browser/native guide pixels differ"
    return a


def assert_visible_projection(spec, brief):
    """Visible explanation must project real source roles and directed links."""
    plan, visible = brief["explanation_plan"], brief["visible_content"]
    assert brief["version"] == "RENDER3"
    assert plan["mode"] in {"hero", "annotated_context", "functional_cutaway", "assembly"}
    assert plan["reading_question"] and plan["visible_scope"]
    assert plan["geometry"] == brief["composition_plan"]["geometry"]
    assert brief["artwork_language"] in {"en", "zh"}
    subject = brief["subject"]
    assert subject["source_node_ids"] == [node["id"] for node in spec["nodes"]]
    assert subject["source_group_ids"] == [group["id"] for group in spec["groups"]]
    assert subject["plan"]["scale"] in {"chip", "package", "die", "wafer", "board", "server", "rack", "system"}
    assert subject["plan"]["instruction"] and subject["plan"]["basis"]
    assert subject["plan"]["source_ownership"] == [
        {"id": group["id"], "label": group["label"], "parent": group["parent"],
         "members": [node["id"] for node in spec["nodes"] if node["group"] == group["id"]]}
        for group in spec["groups"]
    ]
    nodes = {node["id"]: node for node in spec["nodes"]}
    groups = {group["id"]: group for group in spec["groups"]}
    regions, context = visible["regions"], visible["context_objects"]
    objects = {item["id"]: item for item in regions + context}
    assert len(objects) == len(regions) + len(context)
    displayed_nodes = set()
    for item in regions + context:
        member_ids = item["source_node_ids"]
        assert member_ids and len(set(member_ids)) == len(member_ids)
        assert set(member_ids) <= set(nodes)
        assert not displayed_nodes.intersection(member_ids), "Visible source ownership must not be duplicated"
        displayed_nodes.update(member_ids)
        assert item["label"] and item["portrayal"]
    for region in regions:
        source_groups = region["source_group_ids"]
        assert set(source_groups) <= set(groups)
        if source_groups:
            assert region["members"] == [nodes[node_id]["label"] for node_id in region["source_node_ids"]]
            assert all(nodes[node_id]["group"] in source_groups for node_id in region["source_node_ids"])
            assert region["label"] in {groups[group_id]["label"] for group_id in source_groups}
        else:
            assert len(region["source_node_ids"]) == 1
            assert region["label"] == nodes[region["source_node_ids"][0]]["label"]
        for detail in region["member_details"]:
            node_id = detail["source_node_id"]
            assert node_id in region["source_node_ids"]
            assert detail["label"] == nodes[node_id]["label"] and detail["detail"] == nodes[node_id]["detail"]
    for item in context:
        assert len(item["source_node_ids"]) == 1
        source = nodes[item["source_node_ids"][0]]
        assert item["label"] == source["label"] and item["origin"] == source.get("origin", "given")
    shown_edges = set()
    for relation in visible["relationships"]:
        assert relation["source"] in objects and relation["target"] in objects
        start, end = objects[relation["source"]], objects[relation["target"]]
        assert relation["source_label"] == start["label"] and relation["target_label"] == end["label"]
        indices = relation["source_edge_indices"]
        assert indices and len(set(indices)) == len(indices)
        assert all(isinstance(index, int) and 0 <= index < len(spec["edges"]) for index in indices)
        assert not shown_edges.intersection(indices), "A source relation must have one visible projection"
        shown_edges.update(indices)
        source_edges = [spec["edges"][index] for index in indices]
        assert relation["source_node_pairs"] == [[edge["source"], edge["target"]] for edge in source_edges]
        assert all(edge["source"] in start["source_node_ids"] and edge["target"] in end["source_node_ids"] for edge in source_edges)
        assert relation["labels"] == list(dict.fromkeys(edge["label"] for edge in source_edges if edge.get("label")))
        assert relation["kinds"] == list(dict.fromkeys(edge["kind"] for edge in source_edges))
        assert relation["origin"] == ("assumed" if any(edge.get("origin", "given") == "assumed" for edge in source_edges) else "given")
        if plan["mode"] == "annotated_context":
            assert start in context or end in context, "Exterior annotations should explain selected external links"
    for symbol in visible.get("interface_symbols", []):
        assert len(symbol["source_node_ids"]) == 1 and set(symbol["source_node_ids"]) <= set(nodes)
        source = nodes[symbol["source_node_ids"][0]]
        assert source["kind"] == "io" and symbol["source_label"] == source["label"]
        assert symbol["origin"] == source.get("origin", "given")
        assert symbol["label"] and all(protocol.strip().lower() in source.get("detail", "").lower() for protocol in symbol["label"].split("/"))
    assert visible["deferred_node_ids"] == [node["id"] for node in spec["nodes"] if node["id"] not in displayed_nodes]
    assert visible["deferred_edge_indices"] == [index for index in range(len(spec["edges"])) if index not in shown_edges]
    if plan["mode"] == "hero":
        assert not regions and not context and not visible["relationships"] and not visible["interface_symbols"]
    return displayed_nodes, shown_edges


def assert_render_contract(result, figure, representation):
    spec, brief = result["spec"], figure["render_brief"]
    contract = brief["semantic_contract"]
    assert figure["render_contract"]["version"] == "RENDER3"
    assert figure["representation"] == brief["representation"] == representation
    assert brief["source_hash"] == contract["source_hash"] == result["source_hash"]
    assert figure["layout_strategy"] == "art-directed-render"
    assert not figure["requires_layout_guide"] and figure["composition_guide_optional"]
    assert "structure_layout" not in figure and "layout_scene" not in figure
    assert figure["macro_nodes"] == [] and figure["macro_edges"] == []
    assert figure["render_contract"]["layout_authority"] == "art_direction"
    assert figure["render_contract"]["source_ledger_complete"]
    assert figure["render_contract"]["actual_image_status"] == figure["review_task"]["status"] == "not_reviewed"
    shown_nodes, shown_edges = assert_visible_projection(spec, brief)
    assert figure["render_contract"]["explanatory_mode"] == brief["explanation_plan"]["mode"]
    assert set(figure["render_contract"]["visible_source_node_ids"]) == shown_nodes
    assert set(figure["render_contract"]["visible_source_edge_indices"]) == shown_edges
    facts = contract["known_facts"] + contract["assumed_facts"]
    facts_by_id = {fact["id"]: fact for fact in facts}
    assert len(facts) == len(facts_by_id) == len(spec["nodes"])
    assert set(facts_by_id) == {node["id"] for node in spec["nodes"]}
    for node in spec["nodes"]:
        for field, value in facts_by_id[node["id"]].items():
            assert node.get(field, "") == value, f"Source node {node['id']} lost {field} in render ledger"
    assert len(contract["source_relations"]) == len(spec["edges"])
    for index, (relation, edge) in enumerate(zip(contract["source_relations"], spec["edges"])):
        assert relation["index"] == index and relation["visible_requirement"] == (index in shown_edges)
        assert {field: relation[field] for field in edge} == edge
    owners = {owner["id"]: owner for owner in contract["ownership"]}
    assert set(owners) == {group["id"] for group in spec["groups"]}
    for group in spec["groups"]:
        owner = owners[group["id"]]
        assert owner["label"] == group["label"] and owner["parent"] == group["parent"]
        assert owner["members"] == [node["id"] for node in spec["nodes"] if node["group"] == group["id"]]
    assert set(brief["subject"]["source_node_ids"]) == set(facts_by_id)
    assert brief["composition_guide"]["optional"]
    assert brief["composition_guide"]["role"] == "composition_reference"
    assert brief["composition_guide"]["authority"] == "framing only"
    assert figure["generation_inputs"] and all(item["role"] == "composition_reference" and item["optional"] for item in figure["generation_inputs"])
    assert all(annex["representation"] == "diagram" for annex in result["figures"][1:])
    workflow = brief.get("workflow")
    if workflow:
        assert figure["generation_steps"] == workflow["steps"]
        steps = {step["id"]: step for step in figure["generation_steps"]}
        assert steps["complete"]["operation"] == "generate" and steps["complete"]["input_role"] is None
        assert steps["complete"]["prompt"] == figure["prompt"]
        if brief["explanation_plan"]["workflow"] == "single_pass":
            assert workflow["mode"] == "single_pass" and not workflow["recommended"]
            assert set(steps) == {"complete"}
        else:
            assert brief["explanation_plan"]["workflow"] == "optional_edit"
            assert workflow["mode"] == "staged" and workflow["recommended"]
            assert set(steps) == {"complete", "refine"}
            assert steps["refine"]["operation"] == "edit" and steps["refine"]["optional"]
            assert steps["refine"]["input_role"] == "edit_target" and steps["refine"]["input_from"] == "complete"


def assert_bundle_steps(pack, folder, figure):
    """ZIP preserves the complete image and any explicitly requested edit prompt."""
    for step in figure.get("generation_steps", []):
        assert pack.read(folder + step["id"] + "-prompt.txt").decode("utf-8") == step["prompt"]


def verify_design_cases(call, output, report):
    """Original unfamiliar domains use the same actual Worker and bundle path."""
    for name in DESIGN_CASES:
        payload = design_source(name)
        native = dispatch("compile", payload)
        wasm = call("compile", payload)
        assert_result_equal(native, wasm, output, "design-" + name)
        figure = assert_design_contract(name, payload, wasm)
        native_figure = next(item for item in native["figures"] if item["id"] == figure["id"])
        guide_bytes = layout_guide.render(native, native_figure)
        guide_checked = False
        if guide_bytes:
            native_guide = dispatch("guide", {"result": native, "figure_id": figure["id"]})
            wasm_guide = call("guide", {"result": wasm, "figure_id": figure["id"]})
            image = assert_guide_equal(native_guide, wasm_guide, "design-" + name)
            direct = Image.open(io.BytesIO(guide_bytes)).convert("RGB")
            assert direct.size == image.size and direct.tobytes() == image.tobytes(), name + ": direct and bridge guide pixels differ"
            # PNG encoders may produce different compression streams. The
            # assertion above compares every decoded RGB pixel exactly;
            # exported bytes must equal the same browser guide response.
            guide_bytes = base64.b64decode(wasm_guide["base64"])
            (output / ("design-" + name + "-guide.png")).write_bytes(guide_bytes)
            guide_checked = True
        else:
            assert not figure.get("requires_layout_guide"), name + ": required guide is missing"
        archive = call("bundle", {"result": wasm, "figure_id": figure["id"]})
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(archive["base64"]))) as pack:
            assert_design_bundle(pack, payload, wasm, figure, guide_bytes)
        assert call("review", {"result": wasm, "figure_id": figure["id"]}) == figure["review_task"]
        report["design_cases"].append({**design_report_case(name, payload, wasm),
                                      "result_equal": True, "guide_checked": guide_checked,
                                      "guide_rgb_equal": True if guide_checked else None,
                                      "bundle_source_design_and_prompt_equal": True})



def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Make one real configured DeepSeek request; credentials are never written to the report")
    parser.add_argument("--algorithm-only", action="store_true", help="Run the two mathematical sources and real mobile UI without repeating unchanged hardware/render cases")
    parser.add_argument("--bounded-flow-only", action="store_true", help="Run the generic five-resource hardware branch/return with native/Worker result and guide parity")
    parser.add_argument("--design-only", action="store_true", help="Run twelve original generalization sources through native/Worker and bundle parity")
    args = parser.parse_args()
    if sum((args.algorithm_only, args.bounded_flow_only, args.design_only)) > 1:
        parser.error("Choose only one focused verification mode")
    if (args.algorithm_only or args.bounded_flow_only or args.design_only) and args.live:
        parser.error("Focused checks do not make provider requests; omit --live")
    output = ROOT / ".local" / "verification"
    output.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(ROOT / "dist")))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}/web/"
    report = {"static_subpath": "/web/", "cases": [], "scene_cases": [], "representation_cases": [], "explanation_cases": [], "algorithm_cases": [], "hardware_flow_cases": [], "design_cases": [], "live": "not_requested"}
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_default_timeout(180000)
            errors = []
            requests = []
            page.on("pageerror", lambda error: errors.append(type(error).__name__))
            page.on("request", lambda request: requests.append(request.url.split("?")[0]))
            page.goto(base, wait_until="networkidle")
            assert page.title().startswith("Silicon Canvas")
            page.evaluate("""async () => {
                const {Compiler} = await import('./compiler.js');
                window.verificationCompiler = new Compiler();
            }""")
            def call(action, payload):
                return page.evaluate("async ({action,payload}) => await window.verificationCompiler.call(action,payload)", {"action": action, "payload": payload})
            if not args.algorithm_only and not args.bounded_flow_only:
                verify_design_cases(call, output, report)
            if args.design_only:
                report["ui"] = {"no_backend_requests": not any("/api/" in url for url in requests), "page_errors": errors}
                assert not errors and report["ui"]["no_backend_requests"]
                browser.close()
                (output / "design-coverage-browser-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                print(json.dumps(report, ensure_ascii=False))
                return
            for name in ([] if args.algorithm_only or args.bounded_flow_only else ["gpu", "soc"]):
                source = json.loads((ROOT / "examples" / (name + ".json")).read_text(encoding="utf-8"))
                native = dispatch("compile", source)
                wasm = call("compile", source)
                native_json = json.dumps(native, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
                # Exact source + projection + geometry + labels + prompt consistency.
                assert_result_equal(native, wasm, output, name)
                figure_id = wasm["selected_figure_id"]
                native_guide = dispatch("guide", {"result": native, "figure_id": figure_id})
                wasm_guide = call("guide", {"result": wasm, "figure_id": figure_id})
                a = assert_guide_equal(native_guide, wasm_guide, name)
                archive = call("bundle", {"result": wasm, "figure_id": figure_id})
                with zipfile.ZipFile(io.BytesIO(base64.b64decode(archive["base64"]))) as pack:
                    portable = json.loads(pack.read("result.json"))
                    assert portable["spec"] == native["spec"]
                    assert json.loads(pack.read(f"figures/{figure_id}/review-manifest.json"))["status"] == "not_reviewed"
                    assert pack.read(f"figures/{figure_id}/layout-guide.png") == base64.b64decode(wasm_guide["base64"])
                (output / (name + "-guide.png")).write_bytes(base64.b64decode(wasm_guide["base64"]))
                report["cases"].append({"case": name, "source_nodes": len(native["spec"]["nodes"]), "source_edges": len(native["spec"]["edges"]), "result_equal": True, "result_sha256": digest(native_json), "guide_size": a.size, "guide_rgb_equal": True, "bundle_full_source": True, "review_status": "not_reviewed"})
                # The same engineering source must produce different compositions by purpose.
                scene_sources = set()
                scene_prompts = set()
                scene_pixels = set()
                for scene in ["concept", "system", "flow", "detail"]:
                    payload = {**source, "settings": {**source["settings"], "scene": scene, "representation": "diagram"}}
                    native_scene = dispatch("compile", payload)
                    browser_scene = call("compile", payload)
                    assert_result_equal(native_scene, browser_scene, output, f"{name}-{scene}")
                    assert browser_scene["spec"] == native["spec"], f"{name}/{scene}: purpose changed canonical engineering facts"
                    assert browser_scene["settings"]["scene"] == scene
                    assert browser_scene["settings"]["resolved_scene"] == scene
                    assert browser_scene["scene_profile"]["id"] == scene
                    selected = browser_scene["selected_figure_id"]
                    local_guide = dispatch("guide", {"result": native_scene, "figure_id": selected})
                    browser_guide = call("guide", {"result": browser_scene, "figure_id": selected})
                    local_image = assert_guide_equal(local_guide, browser_guide, f"{name}/{scene}")
                    scene_sources.add(browser_scene["source_hash"])
                    scene_prompts.add(browser_scene["prompt"])
                    scene_pixels.add(digest(local_image.tobytes()))
                    (output / f"{name}-{scene}-guide.png").write_bytes(base64.b64decode(browser_guide["base64"]))
                    report["scene_cases"].append({"case": name, "scene": scene, "result_equal": True, "guide_rgb_equal": True, "canonical_facts_equal": True, "source_hash": browser_scene["source_hash"], "guide_size": local_image.size})
                assert len(scene_sources) == 1, f"{name}: scene selection changed the engineering source hash"
                assert len(scene_prompts) == 4, f"{name}: purposes must change the actual Image Gen brief"
                assert len(scene_pixels) == 4, f"{name}: purposes must change actual guide composition"
                # Representation changes art direction, never the source engineering ledger.
                representation_prompts = set()
                original_art = {}
                variants = [(representation, False) for representation in ["product_render", "system_illustration", "diagram"]]
                variants += [(representation, True) for representation in ["product_render", "system_illustration"]]
                for representation, alternate in variants:
                    variant = representation + ("-dark-overhead" if alternate else "")
                    notes = source["settings"].get("notes", "")
                    if alternate:
                        notes += "\n使用深色背景与俯视镜头；保持所有设计事实不变。"
                    payload = {**source, "settings": {**source["settings"], "representation": representation, "scene": "system", "notes": notes}}
                    native_render = dispatch("compile", payload)
                    browser_render = call("compile", payload)
                    assert_result_equal(native_render, browser_render, output, f"{name}-{variant}")
                    assert browser_render["spec"] == native["spec"]
                    assert browser_render["source_hash"] == native["source_hash"]
                    assert browser_render["settings"]["resolved_representation"] == representation
                    selected = browser_render["selected_figure_id"]
                    figure = next(item for item in browser_render["figures"] if item["id"] == selected)
                    assert figure["review_task"]["status"] == "not_reviewed"
                    local_guide = dispatch("guide", {"result": native_render, "figure_id": selected})
                    browser_guide = call("guide", {"result": browser_render, "figure_id": selected})
                    local_image = assert_guide_equal(local_guide, browser_guide, f"{name}/{variant}")
                    render = representation != "diagram"
                    guide_name = "composition-guide.png" if render else "layout-guide.png"
                    if render:
                        assert_render_contract(browser_render, figure, representation)
                        assert browser_guide["role"] == "composition_reference" and browser_guide["optional"]
                        art = figure["render_brief"]["art_direction"]
                        if alternate:
                            assert art["camera"] != original_art[representation]["camera"]
                            assert art["background"] != original_art[representation]["background"]
                            assert "top-down" in art["camera"] and "dark charcoal" in art["background"]
                        else:
                            original_art[representation] = art
                    else:
                        assert "render_brief" not in figure
                        assert figure["representation"] == "diagram" and figure.get("structure_layout")
                        assert browser_guide["role"] == "target_structure" and not browser_guide["optional"]
                    archive = call("bundle", {"result": browser_render, "figure_id": selected})
                    folder = f"figures/{selected}/"
                    with zipfile.ZipFile(io.BytesIO(base64.b64decode(archive["base64"]))) as pack:
                        portable = json.loads(pack.read("result.json"))
                        assert portable["spec"] == native["spec"] and portable["source_hash"] == native["source_hash"]
                        assert pack.read(folder + guide_name) == base64.b64decode(browser_guide["base64"])
                        assert json.loads(pack.read(folder + "review-manifest.json"))["status"] == "not_reviewed"
                        if render:
                            assert json.loads(pack.read(folder + "render-brief.json")) == figure["render_brief"]
                            assert_bundle_steps(pack, folder, figure)
                            image_input = portable["figures"][0]["generation_inputs"][0]
                            assert image_input["role"] == "composition_reference" and image_input["optional"]
                            assert image_input["source"] == folder + guide_name
                            assert folder + "layout-guide.png" not in pack.namelist()
                        else:
                            assert folder + "render-brief.json" not in pack.namelist()
                    review = call("review", {"result": browser_render, "figure_id": selected})
                    assert review["status"] == "not_reviewed" and review["source_hash"] == native["source_hash"]
                    representation_prompts.add(figure["prompt"])
                    (output / f"{name}-{variant}-guide.png").write_bytes(base64.b64decode(browser_guide["base64"]))
                    report["representation_cases"].append({"case": name, "representation": representation, "dark_overhead": alternate, "result_equal": True, "guide_rgb_equal": True, "guide_size": local_image.size, "source_hash": native["source_hash"], "canonical_facts_equal": True, "render_ledger_complete": render, "guide_role": browser_guide["role"], "guide_optional": browser_guide["optional"], "bundle_contract": "render-brief.json" if render else "engineering diagram", "review_status": "not_reviewed"})
                assert len(representation_prompts) == len(variants), f"{name}: expressions/camera requests must change the actual Image Gen brief"
                # Informative illustrations and optional editing have distinct,
                # source-backed contracts; neither is an empty-package mandate.
                for representation, mode, staged in [
                    ("product_render", "annotated_context", False),
                    ("system_illustration", "functional_cutaway", False),
                    ("system_illustration", "functional_cutaway", True),
                ]:
                    case = f"{name}-{mode}" + ("-explicit-edit" if staged else "-single-pass")
                    notes = source["settings"].get("notes", "")
                    if staged:
                        notes += "\n请分步生成：先生成完整解释画面，再编辑真实成图精修标签。"
                    payload = {**source, "settings": {**source["settings"], "scene": "system", "representation": representation, "explanatory_mode": mode, "notes": notes}}
                    native_explanation = dispatch("compile", payload)
                    browser_explanation = call("compile", payload)
                    assert_result_equal(native_explanation, browser_explanation, output, case)
                    assert browser_explanation["spec"] == native["spec"]
                    assert browser_explanation["source_hash"] == native["source_hash"]
                    selected = browser_explanation["selected_figure_id"]
                    figure = next(item for item in browser_explanation["figures"] if item["id"] == selected)
                    assert_render_contract(browser_explanation, figure, representation)
                    brief = figure["render_brief"]
                    visible = brief["visible_content"]
                    assert brief["explanation_plan"]["mode"] == mode
                    assert len(visible["regions"]) >= 2, f"{case}: informative source collapsed into an empty hero"
                    assert visible["context_objects"] and visible["relationships"], f"{case}: system explanation lost external context"
                    if mode == "functional_cutaway":
                        assert any(not relation["source"].startswith("context:") and not relation["target"].startswith("context:") for relation in visible["relationships"])
                    assert brief["workflow"]["recommended"] == staged
                    local_guide = dispatch("guide", {"result": native_explanation, "figure_id": selected})
                    browser_guide = call("guide", {"result": browser_explanation, "figure_id": selected})
                    guide_image = assert_guide_equal(local_guide, browser_guide, case)
                    archive = call("bundle", {"result": browser_explanation, "figure_id": selected})
                    with zipfile.ZipFile(io.BytesIO(base64.b64decode(archive["base64"]))) as pack:
                        folder = f"figures/{selected}/"
                        assert json.loads(pack.read("result.json"))["spec"] == native["spec"]
                        assert json.loads(pack.read(folder + "render-brief.json")) == brief
                        assert pack.read(folder + "composition-guide.png") == base64.b64decode(browser_guide["base64"])
                        assert_bundle_steps(pack, folder, figure)
                    report["explanation_cases"].append({"case": case, "representation": representation, "mode": mode, "explicit_edit": staged, "workflow": brief["workflow"]["mode"], "result_equal": True, "guide_rgb_equal": True, "guide_size": guide_image.size, "canonical_facts_equal": True, "source_hash": native["source_hash"], "visible_regions": len(visible["regions"]), "visible_relationships": len(visible["relationships"]), "context_objects": len(visible["context_objects"]), "visible_source_projection": "passed", "bundle_stage_prompts": "passed"})
            # A small hardware mechanism keeps source leaves and directed paths,
            # even when its ownership groups would fit a coarser lifecycle view.
            if not args.algorithm_only:
                bounded_source = bounded_hardware_fixture()
                native_bounded = dispatch("compile", bounded_source)
                browser_bounded = call("compile", bounded_source)
                assert_result_equal(native_bounded, browser_bounded, output, "bounded-hardware-flow")
                bounded_figure = assert_bounded_hardware_contract(bounded_source, browser_bounded)
                native_bounded_guide = dispatch("guide", {"result": native_bounded, "figure_id": bounded_figure["id"]})
                browser_bounded_guide = call("guide", {"result": browser_bounded, "figure_id": bounded_figure["id"]})
                bounded_image = assert_guide_equal(native_bounded_guide, browser_bounded_guide, "bounded-hardware-flow")
                assert browser_bounded_guide["role"] == "target_structure" and not browser_bounded_guide["optional"]
                archive = call("bundle", {"result": browser_bounded, "figure_id": bounded_figure["id"]})
                bounded_guide_bytes = base64.b64decode(browser_bounded_guide["base64"])
                with zipfile.ZipFile(io.BytesIO(base64.b64decode(archive["base64"]))) as pack:
                    assert_bounded_hardware_bundle(pack, browser_bounded, bounded_figure, bounded_guide_bytes)
                assert call("review", {"result": browser_bounded, "figure_id": bounded_figure["id"]}) == bounded_figure["review_task"]
                (output / "bounded-hardware-flow-guide.png").write_bytes(bounded_guide_bytes)
                report["hardware_flow_cases"].append({"case": "bounded-hardware-flow", "source_hash": browser_bounded["source_hash"], "source_nodes": 5, "source_edges": 6,
                                                     "result_equal": True, "guide_rgb_equal": True, "guide_size": bounded_image.size,
                                                     "source_leaf_ownership_preserved": True, "singleton_one_way_routes": 6,
                                                     "parallel_branch_and_same_bank_return": True, "typography_measured": True,
                                                     "bundle_source_and_guide_equal": True, "review_status": "not_reviewed",
                                                     "bitmap_quality": "not_certified_by_software"})
            if args.bounded_flow_only:
                report["ui"] = {"no_backend_requests": not any("/api/" in url for url in requests), "page_errors": errors}
                assert not errors and report["ui"]["no_backend_requests"]
                browser.close()
                (output / "bounded-flow-browser-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                print(json.dumps(report, ensure_ascii=False))
                return
            # Mathematical branches and recurrent state use their own grammar,
            # rather than a hardware target plate in the primary image.
            for name in ALGORITHM_FIXTURES:
                algorithm_source = json.loads((ROOT / "examples" / (name + ".json")).read_text(encoding="utf-8"))
                native_algorithm = dispatch("compile", algorithm_source)
                browser_algorithm = call("compile", algorithm_source)
                assert_result_equal(native_algorithm, browser_algorithm, output, name)
                algorithm_figure = assert_algorithm_contract(name, algorithm_source, browser_algorithm)
                archive = call("bundle", {"result": browser_algorithm, "figure_id": algorithm_figure["id"]})
                with zipfile.ZipFile(io.BytesIO(base64.b64decode(archive["base64"]))) as pack:
                    assert_algorithm_bundle(pack, browser_algorithm, algorithm_figure)
                review = call("review", {"result": browser_algorithm, "figure_id": algorithm_figure["id"]})
                assert review == algorithm_figure["review_task"]
                report["algorithm_cases"].append({"case": name, "source_hash": browser_algorithm["source_hash"], "source_nodes": len(algorithm_source["spec"]["nodes"]), "source_edges": len(algorithm_source["spec"]["edges"]), "result_equal": True, "canonical_optional_metadata_equal": True, "algorithm_bundle_equal": True, "source_branches_reductions_recurrence": "passed", "primary_guide_required": False, "review_status": "not_reviewed", "bitmap_quality": "not_certified_by_software"})
            if args.algorithm_only:
                verify_workbench(browser, base, output, report, provider_checks=False)
                report["ui"] = report["workbench"]
                assert not errors
                browser.close()
                (output / "algorithm-browser-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                print(json.dumps(report, ensure_ascii=False))
                return
            # The complete compiler/guide/export matrix above remains the
            # same; only obsolete form/tab checks are replaced by the actual
            # simplified workbench flows and its natural-language auto options.
            verify_workbench(browser, base, output, report)
            report["ui"] = report["workbench"]
            if args.live:
                from verify_workbench import verify_live_workbench
                report["live"] = verify_live_workbench(browser, base, output)
            assert not errors
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
    (output / "browser-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
