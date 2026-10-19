"""Verify a built MCP executable through the real classic STDIO protocol."""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import importlib.util
import json
import math
import os
from pathlib import Path
import tempfile
import zipfile

import anyio
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import BlobResourceContents, ImageContent

from silicon_canvas import engine, layout_guide
from design_coverage import (REPRESENTATIVE_CASES as DESIGN_CASES, source as design_source,
                             assert_contract as assert_design_contract,
                             assert_bundle as assert_design_bundle, report_case as design_report_case)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/editorial_benchmark/fresh-soc-final-source.json"
TOOLS = {"silicon_prepare", "silicon_compile", "silicon_generate", "silicon_export", "silicon_prepare_review"}
ALGORITHM_FIXTURES = ("attention-dataflow", "online-attention-dataflow")


def bounded_hardware_fixture():
    """Reuse the wholly synthetic test source; no user design is distributed."""
    module_spec = importlib.util.spec_from_file_location("silicon_bounded_flow_fixture", ROOT / "tests" / "test_bounded_hardware_flow.py")
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    raw = module.source()
    raw["edges"][0]["label"] = "3x8 read selection"
    return {"spec": engine.normalize_spec(raw),
            "settings": {"scene": "flow", "representation": "diagram", "style": "paper", "aspect": "16:9"},
            "description": ""}


def assert_bounded_hardware_contract(source, result):
    spec = source["spec"]
    assert result["spec"] == spec and result["source_hash"] == canonical_digest(spec)
    figure = next(item for item in result["figures"] if item["id"] == result["selected_figure_id"])
    assert figure["primary"] and not figure["technical_annex"]
    assert "algorithm_flow_plan" not in figure
    assert figure["design_contract"]["grammar"] == "exact-flow"
    assert figure["layout_strategy"] == "publication-candidates" and figure["requires_layout_guide"]
    projection = figure["projection"]
    assert projection["abstraction_policy"] == "bounded-leaf-flow" and projection["ownership_unchanged"]
    assert projection["internal_edges"] == projection["deferred_edges"] == projection["folded_groups"] == []
    assert projection["source_node_to_macro"] == {node["id"]: node["id"] for node in spec["nodes"]}
    objects = {node["id"]: node for node in figure["macro_nodes"]}
    assert len(objects) == len(figure["macro_nodes"]) == len(spec["nodes"]) == 5
    for node in spec["nodes"]:
        projected = objects[node["id"]]
        assert projected["members"] == [node["id"]]
        assert projected["original_group"] == node["group"]
        assert all(projected[field] == node[field] for field in ("label", "kind", "detail"))
    assert objects["helper"]["original_group"] == "shared"
    assert all(objects[node_id]["original_group"] == "private" for node_id in ("bank", "input", "local", "output"))
    assert sum(node["label"] == "Register Bank" for node in figure["macro_nodes"]) == 1
    assert len(figure["macro_edges"]) == len(spec["edges"]) == 6
    assert [edge["members"] for edge in figure["macro_edges"]] == [[index] for index in range(6)]
    scene = figure["layout_scene"]
    assert scene["quality"]["routes_complete"] and scene["quality"]["typography_measured"]
    assert len(scene["routes"]) == 6
    assert sorted(index for route in scene["routes"] for index in route["members"]) == list(range(6))
    for edge in figure["macro_edges"] + scene["routes"]:
        assert len(edge["members"]) == 1 and not edge.get("bidirectional")
        original = spec["edges"][edge["members"][0]]
        assert all(edge[field] == original[field] for field in ("source", "target", "kind", "label"))
        assert edge["kind"] == "data"
    pairs = [(edge["source"], edge["target"]) for edge in scene["routes"]]
    assert [target for start, target in pairs if start == "input"] == ["local", "helper"]
    assert [start for start, target in pairs if target == "output"] == ["local", "helper"]
    assert ("output", "bank") in pairs and ("local", "helper") not in pairs and ("helper", "local") not in pairs
    assert next(route for route in scene["routes"] if route["members"] == [5])["family"] == "return"
    assert figure["design_contract"]["body_pt"] >= 9 and figure["design_contract"]["signal_pt"] >= 8.5
    typography = figure["structure_layout"]["typography"]
    assert typography["no_font_shrink"]
    metrics = figure["structure_layout"]["symbol_metrics"]
    for node in spec["nodes"]:
        assert " ".join(metrics[node["id"]]["lines"]) == node["label"]
        assert metrics[node["id"]]["font_px"] >= typography["body_px"]
    assert metrics["bank"]["detail_lines"] == ["4 banks; 32-B entry"]
    labels = [label["text"] for label in figure["label_layout"]["labels"]]
    assert "3x8 read selection" in labels and "writeback" in labels
    selection_label = next(label for label in figure["label_layout"]["labels"] if label["text"] == "3x8 read selection")
    assert selection_label["source_edge_indices"] == [0]
    assert "3x8 read selection" in figure["prompt"]
    assert figure["review_task"]["status"] == "not_reviewed"
    assert layout_guide.render(result, figure)
    return figure


def assert_bounded_hardware_bundle(pack, result, figure, guide):
    prefix = "figures/" + figure["id"] + "/"
    portable = json.loads(pack.read("result.json"))
    assert portable["spec"] == result["spec"] and portable["source_hash"] == result["source_hash"]
    projected = next(item for item in portable["figures"] if item["id"] == figure["id"])
    for field in ("projection", "macro_nodes", "macro_edges", "layout_scene", "structure_layout", "label_layout"):
        assert projected[field] == json.loads(json.dumps(figure[field]))
    assert pack.read(prefix + "layout-guide.png") == guide
    assert pack.read(prefix + "prompt.txt").decode("utf-8") == figure["prompt"]
    assert pack.read(prefix + "caption.txt").decode("utf-8") == figure["caption"]
    assert json.loads(pack.read(prefix + "review-manifest.json"))["status"] == "not_reviewed"
    assert prefix + "algorithm-flow-plan.json" not in pack.namelist()


def assert_algorithm_source(name, source, result):
    """Check supplied algorithm facts, independently of bitmap aesthetics."""
    spec = source["spec"]
    assert result["spec"] == spec, "Algorithm input metadata or source facts changed during normalization"
    assert result["source_hash"] == canonical_digest(spec)
    nodes = {node["id"]: node for node in spec["nodes"]}
    endpoints = {(edge["source"], edge["target"], edge["kind"]) for edge in spec["edges"]}
    assert len(endpoints) == len(spec["edges"])
    assert all(node["evidence"] in source["description"] for node in nodes.values())
    assert all(edge["evidence"] in source["description"] for edge in spec["edges"])
    if name == "attention-dataflow":
        assert nodes["q"]["tensor_shape"] == nodes["k"]["tensor_shape"] == "N × d_k"
        assert nodes["v"]["tensor_shape"] == nodes["output"]["tensor_shape"] == "N × d_v"
        assert nodes["softmax"]["diagram_role"] == "reduction"
        assert endpoints == {
            ("q", "scores", "data"), ("k", "scores", "data"), ("scores", "scale_mask", "data"),
            ("mask", "scale_mask", "data"), ("scale_mask", "softmax", "data"),
            ("softmax", "weighted", "data"), ("v", "weighted", "data"), ("weighted", "output", "data"),
        }
        assert "sqrt(d_k)" in nodes["scale_mask"]["detail"]
        assert "j <= i" in nodes["mask"]["detail"] and "-inf" in nodes["mask"]["detail"]
    else:
        assert name == "online-attention-dataflow"
        assert nodes["state"]["diagram_role"] == "state"
        assert nodes["online"]["diagram_role"] == "reduction"
        assert nodes["q_tile"]["tensor_shape"] == "B_r × d_k"
        assert nodes["k_tile"]["tensor_shape"] == "B_c × d_k"
        assert nodes["v_tile"]["tensor_shape"] == "B_c × d_v"
        assert nodes["output"]["tensor_shape"] == "B_r × d_v"
        assert {(a, b) for a, b, kind in endpoints if kind == "feedback"} == {
            ("state", "online"), ("state", "accumulate"), ("accumulate", "state"),
        }
        assert ("v_tile", "accumulate", "data") in endpoints
        assert ("state", "normalize", "data") in endpoints
        assert "after all KV tiles" in next(edge["label"] for edge in spec["edges"] if edge["target"] == "normalize")
        assert "diag(alpha)A + P_j V_j" in nodes["accumulate"]["detail"]
        assert "diag(l)^(-1)A" in nodes["normalize"]["detail"]
        assert_online_recurrence()


def assert_online_recurrence():
    """Two rows, uneven tiles and changing maxima exercise the stated update."""
    query = [[1.0, 2.0], [-1.0, 0.5]]
    keys = [[0.2, 0.3], [2.0, -0.5], [-0.4, 1.7]]
    values = [[1.0, -2.0], [0.1, 0.5], [3.0, 1.0]]
    for q in query:
        scores = [sum(a * b for a, b in zip(q, k)) / math.sqrt(len(q)) for k in keys]
        full_weights = [math.exp(score - max(scores)) for score in scores]
        expected = [sum(weight * value[column] for weight, value in zip(full_weights, values)) / sum(full_weights) for column in range(2)]
        maximum, total, accumulator = -math.inf, 0.0, [0.0, 0.0]
        for start, stop in ((0, 1), (1, 3)):
            new_maximum = max(maximum, max(scores[start:stop]))
            alpha = math.exp(maximum - new_maximum)
            tile_weights = [math.exp(score - new_maximum) for score in scores[start:stop]]
            total = alpha * total + sum(tile_weights)
            accumulator = [alpha * accumulator[column] + sum(weight * value[column] for weight, value in zip(tile_weights, values[start:stop])) for column in range(2)]
            maximum = new_maximum
        assert all(math.isclose(actual / total, target, rel_tol=1e-12, abs_tol=1e-12) for actual, target in zip(accumulator, expected)), "Online accumulator fixture is mathematically inconsistent"


def assert_algorithm_contract(name, source, result):
    assert_algorithm_source(name, source, result)
    figure = next(item for item in result["figures"] if item["id"] == result["selected_figure_id"])
    plan, spec = figure["algorithm_flow_plan"], source["spec"]
    assert plan["version"] == "ALGO1" and plan["source_hash"] == result["source_hash"]
    assert figure["layout_strategy"] == "algorithm-dependency-plan"
    assert figure["primary"] and not figure["technical_annex"]
    assert not figure["requires_layout_guide"] and not figure["generation_inputs"]
    assert "structure_layout" not in figure and "layout_scene" not in figure
    assert layout_guide.render(result, figure) is None
    assert figure["source_edge_indices"] == list(range(len(spec["edges"])))
    assert figure["projection"]["source_node_to_macro"] == {node["id"]: node["id"] for node in spec["nodes"]}
    assert figure["projection"]["deferred_edges"] == []
    assert len(plan["objects"]) == len(spec["nodes"])
    nodes = {node["id"]: node for node in spec["nodes"]}
    objects = {item["source_node_id"]: item for item in plan["objects"]}
    assert set(objects) == set(nodes)
    for node_id, item in objects.items():
        node = nodes[node_id]
        assert item["label"] == node["label"] and item["source_group"] == node["group"]
        assert item["role"] == node["diagram_role"]
        assert item["evidence"] == node["evidence"] and item["origin"] == node["origin"]
        assert item["source_fields"] == {field: node[field] for field in ("label", "kind", "detail", "diagram_role", "tensor_shape", "reduction_axis", "residency") if field in node}
        text = item["text_plan"]
        assert text["name"] == node["label"] and text["shape_once"] == node.get("tensor_shape", "")
        assert all(line in node["detail"] for line in text["mathematical_lines"])
        assert all(line in node["detail"] or line == node.get("reduction_axis") for line in text["axis_lines"])
        assert len(text["mathematical_lines"]) == len(set(text["mathematical_lines"]))
    expected_outputs = [{"source_node_id": node["id"],
                         "source_edge_indices": [index for index, edge in enumerate(spec["edges"]) if edge["source"] == node["id"]],
                         "allowed_target_node_ids": list(dict.fromkeys(edge["target"] for edge in spec["edges"] if edge["source"] == node["id"]))} for node in spec["nodes"]]
    assert plan["composition"]["outgoing_contracts"] == expected_outputs
    endpoint_pairs = list(dict.fromkeys((edge["source"], edge["target"]) for edge in spec["edges"]))
    assert plan["composition"]["connector_cardinality"] == [{"source_node_id": start, "target_node_id": end, "source_edge_indices": [index for index, edge in enumerate(spec["edges"]) if (edge["source"], edge["target"]) == (start, end)], "connector_count": sum((edge["source"], edge["target"]) == (start, end) for edge in spec["edges"])} for start, end in endpoint_pairs]
    assert len(plan["relations"]) == len(spec["edges"])
    for index, (relation, edge) in enumerate(zip(plan["relations"], spec["edges"])):
        assert relation["source_edge_index"] == index
        assert {key: relation[key] for key in edge} == edge
        if edge["kind"] == "feedback":
            assert relation["display_role"] == "state operand/update" and relation["display_stroke"] == "solid"
    assert plan["groups"] == [{**group, "member_node_ids": [node["id"] for node in spec["nodes"] if node["group"] == group["id"]]} for group in spec["groups"]]
    assert plan["motifs"]["tensor_shapes"] == [{"source_node_id": node["id"], "shape": node["tensor_shape"]} for node in spec["nodes"] if node.get("tensor_shape")]
    assert plan["motifs"]["data_residency"] == [{"source_node_id": node["id"], "residency": node["residency"]} for node in spec["nodes"] if node.get("residency")]
    assert plan["motifs"]["reductions"] == [node["id"] for node in spec["nodes"] if node["diagram_role"] == "reduction"]
    ranks = {node_id: layer["rank"] for layer in plan["composition"]["dependency_layers"] for node_id in layer["node_ids"]}
    assert set(ranks) == set(nodes)
    returns = set(plan["composition"]["return_edge_indices"])
    assert all(ranks[edge["source"]] < ranks[edge["target"]] for index, edge in enumerate(spec["edges"]) if index not in returns)
    joins = {item["target_node_id"]: item for item in plan["motifs"]["joins"]}
    for target, join in joins.items():
        incoming = [(index, edge) for index, edge in enumerate(spec["edges"]) if edge["target"] == target]
        assert join["source_node_ids"] == list(dict.fromkeys(edge["source"] for _, edge in incoming))
        assert join["source_edge_indices"] == [index for index, _ in incoming]
    if name == "attention-dataflow":
        assert ranks["q"] == ranks["k"] == ranks["v"]
        assert joins["scores"]["source_node_ids"] == ["q", "k"]
        assert joins["weighted"]["source_node_ids"] == ["softmax", "v"]
        assert not returns and not plan["motifs"]["recurrence_components"]
        assert not plan["motifs"]["recurrence_exits"]
        assert plan["composition"]["grammar"] == "branched-tensor-flow"
    else:
        assert plan["composition"]["state_lane_node_ids"] == ["state"]
        assert plan["composition"]["grammar"] == "recurrent-tensor-flow"
        assert len(plan["motifs"]["recurrence_components"]) == 1
        component = plan["motifs"]["recurrence_components"][0]
        assert set(component["node_ids"]) == {"online", "accumulate", "state"}
        assert component["source_edge_indices"] == [3, 4, 6, 7]
        assert returns and returns <= set(component["source_edge_indices"])
        exits = plan["motifs"]["recurrence_exits"]
        assert len(exits) == 1 and exits == plan["composition"]["recurrence_exit_branches"]
        assert exits[0]["source_edge_index"] == 8 and exits[0]["source_node_id"] == "state" and exits[0]["target_node_id"] == "normalize"
        assert exits[0]["label"] == spec["edges"][8]["label"] and exits[0]["kind"] == "data"
        assert set(exits[0]["component_node_ids"]) == set(component["node_ids"])
        assert objects["normalize"]["text_plan"]["mathematical_lines"] == ["O_i = diag(l)^(-1)A"]
        assert "m = -inf, l = 0, A = 0" in objects["state"]["text_plan"]["mathematical_lines"]
        assert joins["accumulate"]["source_node_ids"] == ["online", "v_tile", "state"]
        branches = {item["source_node_id"]: item for item in plan["motifs"]["parallel_branches"]}
        assert branches["state"]["target_node_ids"] == ["online", "accumulate", "normalize"]
    review = figure["review_task"]
    assert review["status"] == "not_reviewed" and not review["has_controlled_plate"]
    assert review["objects"] == plan["objects"] and review["expected_connections"] == plan["relations"]
    assert review["source_scope"] == figure["source_edge_indices"]
    assert "No input guide image is required" in figure["prompt"]
    return figure


def assert_algorithm_bundle(pack, result, figure):
    prefix = "figures/" + figure["id"] + "/"
    portable = json.loads(pack.read("result.json"))
    assert portable["spec"] == result["spec"] and portable["source_hash"] == result["source_hash"]
    assert json.loads(pack.read(prefix + "algorithm-flow-plan.json")) == figure["algorithm_flow_plan"]
    assert pack.read(prefix + "prompt.txt").decode("utf-8") == figure["prompt"]
    assert pack.read(prefix + "caption.txt").decode("utf-8") == figure["caption"]
    assert prefix + "layout-guide.png" not in pack.namelist() and prefix + "composition-guide.png" not in pack.namelist()
    assert json.loads(pack.read(prefix + "review-manifest.json"))["status"] == "not_reviewed"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_digest(spec: dict) -> str:
    return digest(json.dumps(spec, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def checked(result):
    if result.is_error:
        raise RuntimeError("MCP tool failed: " + " ".join(getattr(item, "text", "") for item in result.content))
    if not isinstance(result.structured_content, dict):
        raise AssertionError("Expected structured MCP output.")
    return result.structured_content


def assert_visible_projection(spec, brief):
    """Check the explanatory projection without calling it physical layout."""
    assert brief["version"] == "RENDER3"
    plan, visible = brief["explanation_plan"], brief["visible_content"]
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
    shown_nodes = set()
    for item in regions + context:
        ids = item["source_node_ids"]
        assert ids and len(set(ids)) == len(ids) and set(ids) <= set(nodes)
        assert not shown_nodes.intersection(ids)
        shown_nodes.update(ids)
        assert item["label"] and item["portrayal"]
    for region in regions:
        group_ids = region["source_group_ids"]
        assert set(group_ids) <= set(groups)
        if group_ids:
            assert region["members"] == [nodes[node_id]["label"] for node_id in region["source_node_ids"]]
            assert all(nodes[node_id]["group"] in group_ids for node_id in region["source_node_ids"])
            assert region["label"] in {groups[group_id]["label"] for group_id in group_ids}
        else:
            assert len(region["source_node_ids"]) == 1
            assert region["label"] == nodes[region["source_node_ids"][0]]["label"]
        for detail in region["member_details"]:
            node_id = detail["source_node_id"]
            assert node_id in region["source_node_ids"]
            assert detail["label"] == nodes[node_id]["label"] and detail["detail"] == nodes[node_id]["detail"]
    for item in context:
        assert len(item["source_node_ids"]) == 1
        node = nodes[item["source_node_ids"][0]]
        assert item["label"] == node["label"] and item["origin"] == node.get("origin", "given")
    shown_edges = set()
    for relation in visible["relationships"]:
        assert relation["source"] in objects and relation["target"] in objects
        start, end = objects[relation["source"]], objects[relation["target"]]
        assert relation["source_label"] == start["label"] and relation["target_label"] == end["label"]
        indices = relation["source_edge_indices"]
        assert indices and len(set(indices)) == len(indices) and not shown_edges.intersection(indices)
        assert all(isinstance(index, int) and 0 <= index < len(spec["edges"]) for index in indices)
        shown_edges.update(indices)
        edges = [spec["edges"][index] for index in indices]
        assert relation["source_node_pairs"] == [[edge["source"], edge["target"]] for edge in edges]
        assert all(edge["source"] in start["source_node_ids"] and edge["target"] in end["source_node_ids"] for edge in edges)
        assert relation["labels"] == list(dict.fromkeys(edge["label"] for edge in edges if edge.get("label")))
        assert relation["kinds"] == list(dict.fromkeys(edge["kind"] for edge in edges))
        assert relation["origin"] == ("assumed" if any(edge.get("origin", "given") == "assumed" for edge in edges) else "given")
        if plan["mode"] == "annotated_context":
            assert start in context or end in context
    for symbol in visible.get("interface_symbols", []):
        assert len(symbol["source_node_ids"]) == 1 and set(symbol["source_node_ids"]) <= set(nodes)
        node = nodes[symbol["source_node_ids"][0]]
        assert node["kind"] == "io" and symbol["source_label"] == node["label"]
        assert symbol["origin"] == node.get("origin", "given")
        assert symbol["label"] and all(protocol.strip().lower() in node.get("detail", "").lower() for protocol in symbol["label"].split("/"))
    assert visible["deferred_node_ids"] == [node["id"] for node in spec["nodes"] if node["id"] not in shown_nodes]
    assert visible["deferred_edge_indices"] == [index for index in range(len(spec["edges"])) if index not in shown_edges]
    if plan["mode"] == "hero":
        assert not regions and not context and not visible["relationships"] and not visible["interface_symbols"]
    return shown_nodes, shown_edges


async def verify_design_cases(client, directory):
    cases = []
    for name in DESIGN_CASES:
        payload = design_source(name)
        native = engine.compile_manual(payload)
        native_json = json.loads(json.dumps(native, ensure_ascii=False))
        native_figure = assert_design_contract(name, payload, native)
        native_guide = layout_guide.render(native, native_figure)
        output = await client.call_tool("silicon_compile", payload)
        data = checked(output)
        complete = json.loads((await client.read_resource(data["result_uri"])).contents[0].text)
        assert complete == native_json, name + ": frozen compiler differs from current native result"
        figure = assert_design_contract(name, payload, complete)
        meta = next(item for item in data["figures"] if item["id"] == figure["id"])
        brief = json.loads((await client.read_resource(meta["brief_uri"])).contents[0].text)
        assert brief["prompt"] == data["prompt"] == figure["prompt"]
        assert brief["diagram_design"] == figure["diagram_design"]
        images = [item for item in output.content if isinstance(item, ImageContent)]
        if native_guide:
            assert len(images) == 1
            guide = base64.b64decode(images[0].data, validate=True)
            assert guide == native_guide, name + ": frozen guide differs from current native pixels"
            guide_path = Path(data["guide_path"]).resolve()
            assert guide_path.is_relative_to(directory / "artifacts")
            assert guide_path.read_bytes() == guide
            guide_resource = (await client.read_resource(data["guide_uri"])).contents[0]
            assert isinstance(guide_resource, BlobResourceContents)
            assert base64.b64decode(guide_resource.blob, validate=True) == guide
        else:
            assert not native_figure.get("requires_layout_guide"), name + ": required guide missing"
            assert not images and data["guide_uri"] is None and data["guide_path"] is None
            guide = None
        exported = checked(await client.call_tool("silicon_export", {"artifact_id": data["artifact_id"]}))
        export_path = Path(exported["path"]).resolve()
        assert export_path.is_relative_to(directory / "artifacts")
        resource = (await client.read_resource(exported["uri"])).contents[0]
        assert isinstance(resource, BlobResourceContents)
        pack = base64.b64decode(resource.blob, validate=True)
        assert pack == export_path.read_bytes()
        with zipfile.ZipFile(io.BytesIO(pack)) as archive:
            assert_design_bundle(archive, payload, complete, figure, guide)
        review = checked(await client.call_tool("silicon_prepare_review", {"artifact_id": data["artifact_id"]}))
        assert review["status"] == "not_reviewed" and review["review_task"] == figure["review_task"]
        cases.append({**design_report_case(name, payload, complete), "native_compiler_equal": True,
                      "guide_checked": bool(guide), "native_guide_equal": True if guide else None,
                      "brief_resource_and_export_equal": True})
    return cases


async def verify(command: Path, design_only: bool = False) -> dict:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    expected_source_hash = canonical_digest(fixture["spec"])
    native = engine.compile_manual({"spec": fixture["spec"], "settings": fixture.get("settings", {}), "description": fixture["description"]})
    # Match the JSON wire representation, including native tuple -> JSON array conversion.
    native_json = json.loads(json.dumps(native, ensure_ascii=False))
    native_selected = next(item for item in native["figures"] if item["id"] == native["selected_figure_id"])
    native_guide = layout_guide.render(native, native_selected)
    assert native_guide is not None
    with tempfile.TemporaryDirectory(prefix="silicon-frozen-mcp-") as temporary:
        directory = Path(temporary).resolve()
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        # No provider tools are called, and no API key is supplied to the process.
        for key in tuple(environment):
            if key.startswith("DEEPSEEK_"):
                environment.pop(key)
        environment["SILICON_CANVAS_OUTPUT_DIR"] = str(directory / "artifacts")
        environment["PYTHONUTF8"] = "1"
        parameters = StdioServerParameters(command=str(command), args=[], env=environment, cwd=directory)
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write, read_timeout_seconds=180) as client:
                initialized = await client.initialize()
                assert initialized.server_info.name == "Silicon Canvas"
                tools = (await client.list_tools()).tools
                assert {tool.name for tool in tools} == TOOLS
                if design_only:
                    return {"status": "pass", "executable": str(command),
                            "protocol_version": initialized.protocol_version, "tools": len(tools),
                            "provider_tools_called": False,
                            "design_cases": await verify_design_cases(client, directory)}
                calls = ["silicon_compile", "silicon_export", "silicon_prepare_review"]
                compiled = await client.call_tool("silicon_compile", {"spec": fixture["spec"], "settings": fixture.get("settings", {}), "description": fixture["description"]})
                data = checked(compiled)
                assert data["source_hash"] == expected_source_hash
                assert data["review_status"] == "not_reviewed"
                assert data["preflight"]["quality"]["routes_complete"] is True
                assert data["preflight"]["quality"]["document_fit"]["status"] == "pass"
                images = [item for item in compiled.content if isinstance(item, ImageContent)]
                assert len(images) == 1
                guide = base64.b64decode(images[0].data, validate=True)
                assert guide.startswith(b"\x89PNG\r\n\x1a\n")
                guide_path = Path(data["guide_path"]).resolve()
                assert guide_path.is_relative_to(directory / "artifacts")
                assert guide_path.read_bytes() == guide
                guide_resource = (await client.read_resource(data["guide_uri"])).contents[0]
                assert isinstance(guide_resource, BlobResourceContents)
                assert base64.b64decode(guide_resource.blob, validate=True) == guide
                complete = json.loads((await client.read_resource(data["result_uri"])).contents[0].text)
                assert complete["spec"] == fixture["spec"]
                assert canonical_digest(complete["spec"]) == expected_source_hash
                assert complete == native_json, "Frozen compiler result differs from current native source; rebuild the executable."
                assert guide == native_guide, "Frozen primary PNG differs from the current native compiler; rebuild the executable."
                selected_brief = next(item for item in data["figures"] if item["id"] == data["selected_figure_id"])
                brief = json.loads((await client.read_resource(selected_brief["brief_uri"])).contents[0].text)
                assert brief["prompt"] == data["prompt"]
                assert brief["caption"] == data["caption"]
                exported = checked(await client.call_tool("silicon_export", {"artifact_id": data["artifact_id"]}))
                exported_path = Path(exported["path"]).resolve()
                assert exported_path.is_relative_to(directory / "artifacts")
                zip_resource = (await client.read_resource(exported["uri"])).contents[0]
                assert isinstance(zip_resource, BlobResourceContents)
                pack = base64.b64decode(zip_resource.blob, validate=True)
                assert pack == exported_path.read_bytes()
                with zipfile.ZipFile(io.BytesIO(pack)) as archive:
                    zipped = json.loads(archive.read("result.json"))
                    assert zipped["spec"] == fixture["spec"]
                    prefix = "figures/" + data["selected_figure_id"] + "/"
                    assert archive.read(prefix + "layout-guide.png") == guide
                    assert archive.read(prefix + "prompt.txt").decode("utf-8") == data["prompt"]
                    assert archive.read(prefix + "caption.txt").decode("utf-8") == data["caption"]
                    assert json.loads(archive.read(prefix + "review-manifest.json"))["status"] == "not_reviewed"
                review = checked(await client.call_tool("silicon_prepare_review", {"artifact_id": data["artifact_id"]}))
                assert review["status"] == "not_reviewed"
                assert review["review_task"]["status"] == "not_reviewed"
                render_cases = []
                for representation, explanatory_mode, staged in (
                    ("product_render", "annotated_context", False),
                    ("system_illustration", "functional_cutaway", False),
                    ("product_render", "hero", False),
                    ("system_illustration", "functional_cutaway", True),
                ):
                    settings = {**fixture.get("settings", {}), "representation": representation, "scene": "system", "explanatory_mode": explanatory_mode}
                    if staged:
                        settings["notes"] = settings.get("notes", "") + "\n请分步生成：先生成完整解释画面，再编辑真实成图精修标签。"
                    payload = {"spec": fixture["spec"], "settings": settings, "description": fixture["description"]}
                    native_render = engine.compile_manual(payload)
                    native_render_json = json.loads(json.dumps(native_render, ensure_ascii=False))
                    native_figure = next(item for item in native_render["figures"] if item["id"] == native_render["selected_figure_id"])
                    expected_guide = layout_guide.render(native_render, native_figure)
                    assert expected_guide is not None
                    render_output = await client.call_tool("silicon_compile", payload)
                    rendered = checked(render_output)
                    assert rendered["source_hash"] == expected_source_hash
                    assert rendered["representation"] == representation
                    assert rendered["guide_role"] == "composition_reference" and rendered["guide_optional"]
                    assert rendered["review_status"] == "not_reviewed"
                    assert rendered["preflight"]["layout_strategy"] == "art-directed-render"
                    # Rendering must not pretend publication routing preflight was run.
                    assert rendered["preflight"]["quality"] == {}
                    render_result = json.loads((await client.read_resource(rendered["result_uri"])).contents[0].text)
                    assert render_result == native_render_json, f"Frozen {representation} result differs from current native source; rebuild the executable."
                    assert render_result["spec"] == fixture["spec"]
                    assert render_result["source_hash"] == expected_source_hash
                    render_figure = next(item for item in render_result["figures"] if item["id"] == rendered["selected_figure_id"])
                    assert "structure_layout" not in render_figure and "layout_scene" not in render_figure
                    assert render_figure["macro_nodes"] == [] and render_figure["macro_edges"] == []
                    assert not render_figure["requires_layout_guide"] and render_figure["composition_guide_optional"]
                    assert render_figure["render_contract"]["source_ledger_complete"]
                    assert render_figure["render_contract"]["version"] == "RENDER3"
                    assert render_figure["render_contract"]["layout_authority"] == "art_direction"
                    assert render_figure["render_contract"]["actual_image_status"] == "not_reviewed"
                    render_brief = render_figure["render_brief"]
                    assert rendered["render_brief"] == native_figure["render_brief"] == render_brief
                    shown_nodes, shown_edges = assert_visible_projection(fixture["spec"], render_brief)
                    assert render_brief["explanation_plan"]["mode"] == explanatory_mode
                    assert rendered["explanation_plan"] == render_brief["explanation_plan"]
                    assert render_figure["render_contract"]["explanatory_mode"] == explanatory_mode
                    assert set(render_figure["render_contract"]["visible_source_node_ids"]) == shown_nodes
                    assert set(render_figure["render_contract"]["visible_source_edge_indices"]) == shown_edges
                    visible = render_brief["visible_content"]
                    if explanatory_mode != "hero":
                        assert len(visible["regions"]) >= 2 and visible["context_objects"] and visible["relationships"]
                    if explanatory_mode == "functional_cutaway":
                        assert any(not relation["source"].startswith("context:") and not relation["target"].startswith("context:") for relation in visible["relationships"])
                    assert rendered["generation_steps"] == render_figure["generation_steps"] == render_brief["workflow"]["steps"]
                    steps = {step["id"]: step for step in render_figure["generation_steps"]}
                    assert steps["complete"]["operation"] == "generate" and steps["complete"]["input_role"] is None
                    assert steps["complete"]["prompt"] == render_figure["prompt"]
                    assert render_brief["workflow"]["recommended"] == staged
                    if staged:
                        assert render_brief["workflow"]["mode"] == "staged" and set(steps) == {"complete", "refine"}
                        assert steps["refine"]["operation"] == "edit" and steps["refine"]["optional"]
                        assert steps["refine"]["input_role"] == "edit_target" and steps["refine"]["input_from"] == "complete"
                    else:
                        assert render_brief["workflow"]["mode"] == "single_pass" and set(steps) == {"complete"}
                    semantic = render_brief["semantic_contract"]
                    assert render_brief["source_hash"] == semantic["source_hash"] == expected_source_hash
                    facts = semantic["known_facts"] + semantic["assumed_facts"]
                    facts_by_id = {fact["id"]: fact for fact in facts}
                    assert len(facts) == len(facts_by_id) == len(fixture["spec"]["nodes"])
                    assert set(facts_by_id) == {node["id"] for node in fixture["spec"]["nodes"]}
                    for node in fixture["spec"]["nodes"]:
                        for field, value in facts_by_id[node["id"]].items():
                            assert node.get(field, "") == value
                    assert len(semantic["source_relations"]) == len(fixture["spec"]["edges"])
                    for index, (relation, edge) in enumerate(zip(semantic["source_relations"], fixture["spec"]["edges"])):
                        assert relation["index"] == index and relation["visible_requirement"] == (index in shown_edges)
                        assert {field: relation[field] for field in edge} == edge
                    owners = {owner["id"]: owner for owner in semantic["ownership"]}
                    assert set(owners) == {group["id"] for group in fixture["spec"]["groups"]}
                    for group in fixture["spec"]["groups"]:
                        owner = owners[group["id"]]
                        assert owner["label"] == group["label"] and owner["parent"] == group["parent"]
                        assert owner["members"] == [node["id"] for node in fixture["spec"]["nodes"] if node["group"] == group["id"]]
                    assert render_brief["composition_guide"]["optional"]
                    assert render_brief["composition_guide"]["role"] == "composition_reference"
                    assert render_brief["composition_guide"]["authority"] == "framing only"
                    assert all(item["role"] == "composition_reference" and item["optional"] for item in render_figure["generation_inputs"])
                    render_images = [item for item in render_output.content if isinstance(item, ImageContent)]
                    assert len(render_images) == 1
                    render_guide = base64.b64decode(render_images[0].data, validate=True)
                    assert render_guide == expected_guide, f"Frozen {representation} PNG differs from current native compiler; rebuild the executable."
                    render_guide_path = Path(rendered["guide_path"]).resolve()
                    assert render_guide_path.is_relative_to(directory / "artifacts")
                    assert render_guide_path.read_bytes() == render_guide
                    render_guide_resource = (await client.read_resource(rendered["guide_uri"])).contents[0]
                    assert isinstance(render_guide_resource, BlobResourceContents)
                    assert base64.b64decode(render_guide_resource.blob, validate=True) == render_guide
                    selected_render_brief = next(item for item in rendered["figures"] if item["id"] == rendered["selected_figure_id"])
                    render_resource = json.loads((await client.read_resource(selected_render_brief["brief_uri"])).contents[0].text)
                    assert render_resource["render_brief"] == render_brief
                    assert render_resource["representation"] == representation
                    assert render_resource["guide_role"] == "composition_reference" and render_resource["guide_optional"]
                    assert render_resource["prompt"] == rendered["prompt"] == native_figure["prompt"]
                    assert render_resource["caption"] == rendered["caption"] == native_figure["caption"]
                    assert render_resource["generation_steps"] == render_figure["generation_steps"]
                    assert render_resource["review_status"] == "not_reviewed"
                    render_export = checked(await client.call_tool("silicon_export", {"artifact_id": rendered["artifact_id"]}))
                    render_export_path = Path(render_export["path"]).resolve()
                    assert render_export_path.is_relative_to(directory / "artifacts")
                    render_zip_resource = (await client.read_resource(render_export["uri"])).contents[0]
                    assert isinstance(render_zip_resource, BlobResourceContents)
                    render_pack = base64.b64decode(render_zip_resource.blob, validate=True)
                    assert render_pack == render_export_path.read_bytes()
                    with zipfile.ZipFile(io.BytesIO(render_pack)) as archive:
                        render_zipped = json.loads(archive.read("result.json"))
                        assert render_zipped["spec"] == fixture["spec"]
                        assert render_zipped["source_hash"] == expected_source_hash
                        prefix = "figures/" + rendered["selected_figure_id"] + "/"
                        assert archive.read(prefix + "composition-guide.png") == render_guide
                        assert prefix + "layout-guide.png" not in archive.namelist()
                        assert json.loads(archive.read(prefix + "render-brief.json")) == render_brief
                        assert archive.read(prefix + "prompt.txt").decode("utf-8") == rendered["prompt"]
                        assert archive.read(prefix + "caption.txt").decode("utf-8") == rendered["caption"]
                        for step in render_figure["generation_steps"]:
                            assert archive.read(prefix + step["id"] + "-prompt.txt").decode("utf-8") == step["prompt"]
                        assert json.loads(archive.read(prefix + "review-manifest.json"))["status"] == "not_reviewed"
                        zipped_figure = next(item for item in render_zipped["figures"] if item["id"] == rendered["selected_figure_id"])
                        assert zipped_figure["render_brief"] == render_brief
                        assert all(item["role"] == "composition_reference" and item["optional"] and item["source"] == prefix + "composition-guide.png" for item in zipped_figure["generation_inputs"])
                    render_review = checked(await client.call_tool("silicon_prepare_review", {"artifact_id": rendered["artifact_id"]}))
                    assert render_review["status"] == render_review["review_task"]["status"] == "not_reviewed"
                    assert render_review["review_task"]["representation"] == representation
                    assert render_review["review_task"]["semantic_contract"] == semantic
                    review_resource = json.loads((await client.read_resource(rendered["review_uri"])).contents[0].text)
                    assert review_resource == render_review["review_task"]
                    render_cases.append({
                        "representation": representation,
                        "explanatory_mode": explanatory_mode,
                        "explicit_edit": staged,
                        "workflow": render_brief["workflow"]["mode"],
                        "visible_regions": len(visible["regions"]),
                        "visible_relationships": len(visible["relationships"]),
                        "context_objects": len(visible["context_objects"]),
                        "visible_source_projection": "passed",
                        "source_hash": expected_source_hash,
                        "native_compiler_equal": True,
                        "native_primary_png_equal": True,
                        "source_ledger_complete": True,
                        "no_engineering_target_geometry": True,
                        "guide_role": rendered["guide_role"],
                        "guide_optional": rendered["guide_optional"],
                        "brief_resource_complete": True,
                        "bundle_render_brief_and_composition_guide": True,
                        "guide_sha256": digest(render_guide),
                        "guide_bytes": len(render_guide),
                        "export_bytes": len(render_pack),
                        "review_status": render_review["status"],
                    })
                bounded_source = bounded_hardware_fixture()
                native_bounded = engine.compile_manual(bounded_source)
                native_bounded_json = json.loads(json.dumps(native_bounded, ensure_ascii=False))
                native_bounded_figure = assert_bounded_hardware_contract(bounded_source, native_bounded)
                native_bounded_guide = layout_guide.render(native_bounded, native_bounded_figure)
                bounded_output = await client.call_tool("silicon_compile", bounded_source)
                bounded_data = checked(bounded_output)
                assert bounded_data["source_hash"] == native_bounded["source_hash"]
                assert bounded_data["guide_role"] == "target_structure" and not bounded_data["guide_optional"]
                assert bounded_data["preflight"]["layout_strategy"] == "publication-candidates"
                assert bounded_data["preflight"]["quality"]["routes_complete"]
                assert bounded_data["preflight"]["quality"]["typography_measured"]
                bounded_result = json.loads((await client.read_resource(bounded_data["result_uri"])).contents[0].text)
                assert bounded_result == native_bounded_json, "Frozen bounded hardware flow differs from native compiler; rebuild the executable."
                bounded_figure = assert_bounded_hardware_contract(bounded_source, bounded_result)
                bounded_images = [item for item in bounded_output.content if isinstance(item, ImageContent)]
                assert len(bounded_images) == 1
                bounded_guide = base64.b64decode(bounded_images[0].data, validate=True)
                assert bounded_guide == native_bounded_guide, "Frozen bounded-flow guide differs from native compiler; rebuild the executable."
                bounded_guide_path = Path(bounded_data["guide_path"]).resolve()
                assert bounded_guide_path.is_relative_to(directory / "artifacts")
                assert bounded_guide_path.read_bytes() == bounded_guide
                bounded_resource = (await client.read_resource(bounded_data["guide_uri"])).contents[0]
                assert isinstance(bounded_resource, BlobResourceContents)
                assert base64.b64decode(bounded_resource.blob, validate=True) == bounded_guide
                bounded_brief_meta = next(item for item in bounded_data["figures"] if item["id"] == bounded_data["selected_figure_id"])
                bounded_brief = json.loads((await client.read_resource(bounded_brief_meta["brief_uri"])).contents[0].text)
                assert bounded_brief["prompt"] == bounded_data["prompt"] == bounded_figure["prompt"]
                bounded_export = checked(await client.call_tool("silicon_export", {"artifact_id": bounded_data["artifact_id"]}))
                bounded_export_path = Path(bounded_export["path"]).resolve()
                assert bounded_export_path.is_relative_to(directory / "artifacts")
                bounded_zip = (await client.read_resource(bounded_export["uri"])).contents[0]
                assert isinstance(bounded_zip, BlobResourceContents)
                bounded_pack = base64.b64decode(bounded_zip.blob, validate=True)
                assert bounded_pack == bounded_export_path.read_bytes()
                with zipfile.ZipFile(io.BytesIO(bounded_pack)) as archive:
                    assert_bounded_hardware_bundle(archive, bounded_result, bounded_figure, bounded_guide)
                bounded_review = checked(await client.call_tool("silicon_prepare_review", {"artifact_id": bounded_data["artifact_id"]}))
                assert bounded_review["status"] == "not_reviewed" and bounded_review["review_task"] == bounded_figure["review_task"]
                hardware_flow_cases = [{"case": "bounded-hardware-flow", "source_hash": bounded_result["source_hash"], "nodes": 5, "edges": 6,
                                        "native_compiler_equal": True, "native_primary_png_equal": True,
                                        "source_leaf_ownership_preserved": True, "singleton_one_way_routes": 6,
                                        "parallel_branch_and_same_bank_return": True, "typography_measured": True,
                                        "guide_resource_and_bundle_equal": True, "review_status": "not_reviewed",
                                        "bitmap_quality": "not_certified_by_software"}]
                algorithm_cases = []
                for name in ALGORITHM_FIXTURES:
                    source = json.loads((ROOT / "examples" / (name + ".json")).read_text(encoding="utf-8"))
                    native_algorithm = engine.compile_manual(source)
                    native_algorithm_json = json.loads(json.dumps(native_algorithm, ensure_ascii=False))
                    native_algorithm_figure = assert_algorithm_contract(name, source, native_algorithm)
                    algorithm_output = await client.call_tool("silicon_compile", source)
                    algorithm_data = checked(algorithm_output)
                    assert algorithm_data["source_hash"] == native_algorithm["source_hash"]
                    assert algorithm_data["algorithm_flow_plan"] == native_algorithm_figure["algorithm_flow_plan"]
                    assert algorithm_data["guide_role"] is None and algorithm_data["guide_optional"]
                    assert algorithm_data["guide_uri"] is None and algorithm_data["guide_path"] is None
                    assert not any(isinstance(item, ImageContent) for item in algorithm_output.content)
                    assert algorithm_data["preflight"]["layout_strategy"] == "algorithm-dependency-plan"
                    assert algorithm_data["preflight"]["quality"] == {}
                    algorithm_result = json.loads((await client.read_resource(algorithm_data["result_uri"])).contents[0].text)
                    assert algorithm_result == native_algorithm_json, f"Frozen {name} result differs from native compiler; rebuild the executable."
                    algorithm_figure = assert_algorithm_contract(name, source, algorithm_result)
                    selected_algorithm = next(item for item in algorithm_data["figures"] if item["id"] == algorithm_data["selected_figure_id"])
                    algorithm_brief = json.loads((await client.read_resource(selected_algorithm["brief_uri"])).contents[0].text)
                    assert algorithm_brief["algorithm_flow_plan"] == algorithm_figure["algorithm_flow_plan"]
                    assert algorithm_brief["prompt"] == algorithm_data["prompt"] == algorithm_figure["prompt"]
                    algorithm_export = checked(await client.call_tool("silicon_export", {"artifact_id": algorithm_data["artifact_id"]}))
                    algorithm_export_path = Path(algorithm_export["path"]).resolve()
                    assert algorithm_export_path.is_relative_to(directory / "artifacts")
                    algorithm_zip = (await client.read_resource(algorithm_export["uri"])).contents[0]
                    assert isinstance(algorithm_zip, BlobResourceContents)
                    algorithm_pack = base64.b64decode(algorithm_zip.blob, validate=True)
                    assert algorithm_pack == algorithm_export_path.read_bytes()
                    with zipfile.ZipFile(io.BytesIO(algorithm_pack)) as archive:
                        assert_algorithm_bundle(archive, algorithm_result, algorithm_figure)
                    algorithm_review = checked(await client.call_tool("silicon_prepare_review", {"artifact_id": algorithm_data["artifact_id"]}))
                    assert algorithm_review["status"] == "not_reviewed"
                    assert algorithm_review["review_task"] == algorithm_figure["review_task"]
                    algorithm_cases.append({
                        "case": name, "source_hash": algorithm_result["source_hash"],
                        "nodes": len(source["spec"]["nodes"]), "edges": len(source["spec"]["edges"]),
                        "native_compiler_equal": True, "source_metadata_preserved": True,
                        "algorithm_plan_resource_and_bundle_equal": True,
                        "no_required_guide_or_image_content": True,
                        "source_branches_reductions_recurrence": "passed",
                        "review_status": "not_reviewed", "bitmap_quality": "not_certified_by_software",
                    })
                design_cases = await verify_design_cases(client, directory)
                return {
                    "status": "pass",
                    "executable": str(command),
                    "protocol_version": initialized.protocol_version,
                    "tools": len(tools),
                    "calls": calls,
                    "provider_tools_called": False,
                    "native_compiler_equal": True,
                    "native_primary_png_equal": True,
                    "source_hash": expected_source_hash,
                    "nodes": len(complete["spec"]["nodes"]),
                    "edges": len(complete["spec"]["edges"]),
                    "figures": len(data["figures"]),
                    "guide_sha256": digest(guide),
                    "guide_bytes": len(guide),
                    "export_bytes": len(pack),
                    "review_status": review["status"],
                    "render_cases": render_cases,
                    "algorithm_cases": algorithm_cases,
                    "hardware_flow_cases": hardware_flow_cases,
                    "design_cases": design_cases,
                    "verified": ["classic_initialize", "tool_list", "canonical_source", "real_preflight", "image_content_equals_file_resource_and_zip", "prompt_and_caption_equal_brief_and_zip", "review_handoff_not_acceptance", "independent_cwd_without_pythonpath", "complete_frozen_result_equals_current_native", "primary_frozen_png_equals_current_native", "product_render_and_system_illustration_over_same_source", "complete_render_brief_resource", "optional_composition_reference_not_target_geometry", "render_bundle_names_roles_and_review", "visible_roles_and_directional_links_backed_by_source", "purpose_specific_hero_and_explanatory_scope", "single_pass_complete_illustration", "explicit_edit_uses_actual_image", "complete_and_refine_prompts_equal_wire_resources_and_zip", "algorithm_tensor_shapes_roles_residency_and_source_provenance", "algorithm_fan_in_reductions_and_state_recurrence", "algorithm_text_only_mcp_resources_and_bundle", "online_accumulator_fixture_agrees_with_full_softmax"],
                }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", type=Path, help="Built MCP executable path")
    parser.add_argument("--output", type=Path, help="Optional JSON evidence file")
    parser.add_argument("--design-only", action="store_true", help="Verify only twelve original coverage sources through real MCP STDIO")
    arguments = parser.parse_args()
    command = arguments.command.expanduser().resolve(strict=True)
    if not command.is_file():
        parser.error("Command must be an executable file.")
    report = anyio.run(verify, command, arguments.design_only)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
