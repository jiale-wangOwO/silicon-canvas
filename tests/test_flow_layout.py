import copy
import json
from pathlib import Path
import unittest

from silicon_canvas import flow_layout
from silicon_canvas import structure_scene


def contains(outer, inner):
    return (outer["x"] <= inner["x"] + .000002 and outer["y"] <= inner["y"] + .000002
            and outer["x"] + outer["width"] >= inner["x"] + inner["width"] - .000002
            and outer["y"] + outer["height"] >= inner["y"] + inner["height"] - .000002)


def node(nid, label, kind="compute", group=""):
    return {"id": nid, "label": label, "kind": kind, "group": group, "detail": ""}


def edge(a, b, kind="data", label=""):
    return {"source": a, "target": b, "kind": kind, "label": label}


def fixture():
    spec = {"title": "Dual operand datapath", "category": "dataflow",
            "groups": [{"id": "unit", "label": "Execution Unit", "parent": ""},
                       {"id": "fpu_scope", "label": "FPU", "parent": "unit"}],
            "nodes": [node("in_a", "Input A", "io", "unit"), node("in_b", "Input B", "io", "unit"),
                      node("unpack_a", "Unpack A", group="unit"), node("unpack_b", "Unpack B", group="unit"),
                      node("src_a", "Source Reg A", "memory", "unit"), node("src_b", "Source Reg B", "memory", "unit"),
                      node("fpu", "FPU Core", group="fpu_scope"), node("special", "Special FPU", group="fpu_scope"),
                      node("dst", "Destination Reg", "memory", "unit"), node("pack", "Packer", group="unit"),
                      node("memory", "Output Memory", "memory"), node("control", "Controller", "control", "unit")],
            "edges": [edge("in_a", "unpack_a"), edge("in_b", "unpack_b"),
                      edge("unpack_a", "src_a"), edge("unpack_b", "src_b"),
                      edge("src_a", "fpu"), edge("src_b", "fpu"), edge("fpu", "dst"),
                      edge("dst", "pack"), edge("pack", "memory"), edge("control", "fpu", "control", "enable")]}
    figure = {"title": spec["title"], "abstract": False,
              "node_ids": [n["id"] for n in reversed(spec["nodes"])],
              "edge_indices": list(reversed(range(len(spec["edges"]))))}
    return spec, figure


class FlowLayoutTests(unittest.TestCase):
    def test_parallel_operand_lanes_align_then_merge_without_new_instances(self):
        spec, figure = fixture()
        original = copy.deepcopy((spec, figure))
        plan = flow_layout.build(spec, figure)
        self.assertEqual((spec, figure), original)
        self.assertEqual(plan["type"], "directed_flow")
        self.assertEqual(plan["node_ids"], figure["node_ids"])
        self.assertEqual(plan["node_to_macro"], {nid: nid for nid in figure["node_ids"]})
        for nid in figure["node_ids"]:
            item = next(n for n in plan["macro_nodes"] if n["id"] == nid)
            self.assertEqual(item["members"], [nid])
            source = next(n for n in spec["nodes"] if n["id"] == nid)
            self.assertEqual(spec["nodes"][item["source_node_index"]]["id"], nid)
            for key in ("label", "kind", "detail"):
                self.assertEqual(item[key], source[key])
        for a, b in (("in_a", "in_b"), ("unpack_a", "unpack_b"), ("src_a", "src_b")):
            self.assertEqual(plan["flow_ranks"][a], plan["flow_ranks"][b])
            self.assertAlmostEqual(plan["boxes"][a]["x"], plan["boxes"][b]["x"])
        centers = lambda nid: plan["boxes"][nid]["y"] + plan["boxes"][nid]["height"] / 2
        for side in ("a", "b"):
            self.assertAlmostEqual(centers("in_" + side), centers("unpack_" + side), places=5)
            self.assertAlmostEqual(centers("unpack_" + side), centers("src_" + side), places=5)
        for a, b in zip(("src_a", "fpu", "dst", "pack"), ("fpu", "dst", "pack", "memory")):
            self.assertLess(plan["boxes"][a]["x"] + plan["boxes"][a]["width"], plan["boxes"][b]["x"])
        self.assertLess(plan["boxes"]["src_a"]["height"], plan["boxes"]["fpu"]["height"])
        self.assertEqual(next(n for n in plan["macro_nodes"] if n["id"] == "src_a")["visual_role"], "storage-bar")

    def test_nested_unconnected_function_keeps_real_owner_without_fake_edges(self):
        spec, figure = fixture()
        plan = flow_layout.build(spec, figure)
        owner = next(c for c in plan["containers"] if c["source_group"] == "fpu_scope")
        self.assertEqual(set(owner["members"]), {"fpu", "special"})
        self.assertTrue(contains(owner["box"], plan["boxes"]["special"]))
        self.assertTrue(contains(owner["box"], plan["boxes"]["fpu"]))
        self.assertFalse(contains(owner["box"], plan["boxes"]["dst"]))
        self.assertEqual(plan["source_ownership"]["special"], "fpu_scope")
        self.assertFalse(any("special" in {e["source"], e["target"]} for e in plan["macro_edges"]))
        self.assertEqual(len(plan["macro_nodes"]), len(spec["nodes"]))

    def test_control_parallel_and_return_edges_keep_original_indices(self):
        spec, figure = fixture()
        spec["edges"].extend([edge("memory", "in_a", "data", "return stream"),
                              edge("src_a", "fpu", "data", "second operand channel"),
                              edge("fpu", "fpu", "feedback", "retry")])
        figure["edge_indices"] = [12, 10, 11, *figure["edge_indices"]]
        plan = flow_layout.build(spec, figure)
        self.assertEqual(plan["edge_indices"], figure["edge_indices"])
        for actual, index in zip(plan["macro_edges"], figure["edge_indices"]):
            self.assertEqual(actual["members"], [index])
            self.assertEqual(actual["source_edge_index"], index)
            for key in ("source", "target", "kind", "label"):
                self.assertEqual(actual[key], spec["edges"][index][key])
            self.assertFalse(actual.get("bidirectional"))
        returning = next(e for e in plan["macro_edges"] if e["members"] == [10])
        self.assertEqual(returning["routing"]["corridor"], "return-outer")
        self.assertEqual(returning["kind"], "data")
        control = next(e for e in plan["macro_edges"] if e["members"] == [9])
        self.assertEqual(control["routing"]["corridor"], "control-outer")
        self.assertLess(control["routing"]["waypoint_value"], min(box["y"] for box in plan["boxes"].values()))
        self.assertGreater(returning["routing"]["waypoint_value"], max(box["y"] + box["height"] for box in plan["boxes"].values()))
        self.assertEqual(plan["coverage"]["missing_edges"], [])
        self.assertEqual(plan["coverage"]["duplicate_edge_indices"], [])

    def test_private_memory_and_external_shared_context_retain_ownership(self):
        spec = {"title": "Memory hierarchy", "category": "memory",
                "groups": [{"id": "system", "label": "System", "parent": ""},
                           {"id": "a", "label": "Private A", "parent": "system"},
                           {"id": "b", "label": "Private B", "parent": "system"},
                           {"id": "shared", "label": "Shared", "parent": "system"}],
                "nodes": [node("cpu_a", "Core A", group="a"), node("cpu_b", "Core B", group="b"),
                          node("local_a", "Local A", "memory", "a"), node("local_b", "Local B", "memory", "b"),
                          node("common", "Shared Memory", "memory", "shared"), node("external", "External Memory", "memory")],
                "edges": [edge("cpu_a", "local_a"), edge("cpu_b", "local_b"),
                          edge("local_a", "common"), edge("local_b", "common"), edge("common", "external"),
                          edge("common", "local_a", label="response")]}
        figure = {"abstract": False, "main_group": "a", "node_ids": [n["id"] for n in spec["nodes"]], "edge_indices": list(range(6))}
        plan = flow_layout.build(spec, figure)
        self.assertEqual(plan["system_frame"]["source_group"], "a")
        self.assertTrue(contains(plan["system_frame"]["box"], plan["boxes"]["local_a"]))
        for nid in ("cpu_b", "local_b", "common", "external"):
            self.assertIn(nid, plan["context_nodes"])
            self.assertFalse(contains(plan["system_frame"]["box"], plan["boxes"][nid]))
        for source in spec["nodes"]:
            self.assertEqual(plan["source_ownership"][source["id"]], source["group"])
        self.assertEqual(plan["node_to_macro"]["common"], "common")

    def test_branching_is_name_independent_and_unsupported_views_fall_back(self):
        spec, figure = fixture()
        baseline = flow_layout.build(spec, figure)
        renamed = copy.deepcopy(spec)
        for item in renamed["nodes"]:
            item["label"] = "Q" * len(item["label"])
        changed = flow_layout.build(renamed, figure)
        self.assertEqual(changed["flow_ranks"], baseline["flow_ranks"])
        self.assertEqual(changed["source_ownership"], baseline["source_ownership"])
        for category in ("fsm", "algorithm", "timing"):
            with self.subTest(category=category):
                self.assertIsNone(flow_layout.build({**spec, "category": category}, figure))
        self.assertIsNone(flow_layout.build(spec, {**figure, "abstract": True}))
        control_only = copy.deepcopy(spec)
        for item in control_only["edges"]:
            item["kind"] = "control"
        self.assertIsNone(flow_layout.build(control_only, figure))

    def test_bad_projection_rejected_and_scene_routes_preserve_source_coverage(self):
        spec, figure = fixture()
        with self.assertRaisesRegex(ValueError, "endpoints"):
            flow_layout.build(spec, {**figure, "node_ids": [n for n in figure["node_ids"] if n != "src_a"]})
        with self.assertRaisesRegex(ValueError, "indices"):
            flow_layout.build(spec, {**figure, "edge_indices": [*figure["edge_indices"], 0]})
        plan = flow_layout.build(spec, figure)
        scene = structure_scene.prepare(plan)
        self.assertTrue(scene["quality"]["routes_complete"], scene["quality"])
        self.assertCountEqual([i for route in scene["routes"] for i in route["members"]], figure["edge_indices"])
        for box in [*plan["boxes"].values(), *[c["box"] for c in plan["containers"]], *[c["box"] for c in plan["routing_corridors"]], plan["system_frame"]["box"]]:
            self.assertGreaterEqual(box["x"], 0)
            self.assertGreaterEqual(box["y"], 0)
            self.assertLessEqual(box["x"] + box["width"], 1.000002)
            self.assertLessEqual(box["y"] + box["height"], 1.000002)

    def test_outer_tracks_stay_distinct_and_frame_does_not_pad_control_routing(self):
        spec, figure = fixture()
        spec["edges"].extend(edge("control", target, "control", "select " + str(index))
                             for index, target in enumerate(("unpack_a", "unpack_b", "src_a", "src_b")))
        figure["edge_indices"] = list(range(len(spec["edges"])))
        plan = flow_layout.build(spec, figure)
        render_height = round(1800 / plan["canvas"]["natural_aspect"])
        positions = sorted(e["routing"]["waypoint_value"] for e in plan["macro_edges"] if e["routing"]["corridor"] == "control-outer")
        self.assertGreaterEqual(min(b - a for a, b in zip(positions, positions[1:])) * render_height, 12)
        control_top = plan["boxes"]["control"]["y"]
        self.assertLess((control_top - positions[-1]) * render_height, 45)
        # The outer control track belongs to a useful routing band above the
        # symbols, rather than another full title-height detour above the frame.
        self.assertGreater(positions[-1], plan["system_frame"]["box"]["y"])

    def test_shared_dma_memory_round_trip_keeps_compact_symbols_and_clear_return_tracks(self):
        spec = {"title": "Transfer loop", "category": "dataflow", "groups": [],
                "nodes": [node("memory", "Memory", "memory"), node("dma", "DMA"),
                          node("input", "Input Buffer", "memory"), node("compute", "Compute"),
                          node("output", "Output Buffer", "memory"), node("control", "Controller", "control")],
                "edges": [edge("memory", "dma"), edge("dma", "input"), edge("input", "compute"),
                          edge("compute", "output"), edge("output", "dma"), edge("dma", "memory"),
                          edge("control", "dma", "control"), edge("control", "compute", "control")]}
        figure = {"abstract": False, "node_ids": [n["id"] for n in spec["nodes"]], "edge_indices": list(range(8))}
        plan = flow_layout.build(spec, figure)
        self.assertEqual(plan["return_edge_indices"], [4, 5])
        self.assertEqual(len([n for n in plan["macro_nodes"] if n["id"] == "dma"]), 1)
        render_height = round(1800 / plan["canvas"]["natural_aspect"])
        self.assertLess(plan["boxes"]["compute"]["height"] * render_height, 72)
        bottom = plan["system_frame"]["box"]["y"] + plan["system_frame"]["box"]["height"]
        tracks = sorted(e["routing"]["waypoint_value"] for e in plan["macro_edges"] if e["routing"]["corridor"] == "return-outer")
        self.assertGreater((tracks[0] - bottom) * render_height, 12)
        self.assertGreater((tracks[1] - tracks[0]) * render_height, 12)
        scene = structure_scene.prepare(plan)
        self.assertTrue(scene["quality"]["routes_complete"], scene["quality"])
        self.assertCountEqual([i for route in scene["routes"] for i in route["members"]], list(range(8)))

    def test_saved_model_two_input_design_routes_all_twenty_two_original_edges(self):
        path = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "publication_benchmark" / "two-input-semantic-v2-result.json"
        saved = json.loads(path.read_text(encoding="utf-8"))
        spec, figure = saved["spec"], saved["figures"][0]
        original = copy.deepcopy(spec)
        plan = flow_layout.build(spec, figure)
        self.assertEqual(spec, original)
        self.assertEqual(len(plan["macro_nodes"]), 11)
        self.assertEqual(len(plan["macro_edges"]), 22)
        for gid, nid in (("g_srcA", "n_srcA"), ("g_srcB", "n_srcB"), ("g_result", "n_result")):
            container = next(c for c in plan["containers"] if c["source_group"] == gid)
            self.assertEqual(container["replaces_region"], gid)
            self.assertEqual(container["source_members"], [nid])
            self.assertEqual(plan["source_ownership"][nid], gid)
        fpu = next(c for c in plan["containers"] if c["source_group"] == "g_fpu")
        self.assertFalse(fpu["replaces_region"])
        self.assertCountEqual(fpu["members"], ["n_alu", "n_sfu"])
        scene = structure_scene.prepare(plan)
        self.assertTrue(scene["quality"]["routes_complete"], scene["quality"])
        self.assertEqual(scene["quality"]["route_count"], 22)
        self.assertCountEqual([i for route in scene["routes"] for i in route["members"]], list(range(22)))
        issue = next(route for route in scene["routes"] if route["members"] == [14])
        self.assertEqual((issue["source"], issue["target"]), ("n_ctrl", "n_dma"))
        self.assertTrue(issue["points"])

    def test_gpu_architecture_exact_support_preserves_remaining_sixteen_edges(self):
        path = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "publication_benchmark" / "gpu-baseline-result.json"
        spec = json.loads(path.read_text(encoding="utf-8"))["spec"]
        original = copy.deepcopy(spec)
        owned = {node["id"] for node in spec["nodes"] if node["group"] == "g_cluster0"}
        detail = [index for index, edge in enumerate(spec["edges"]) if owned & {edge["source"], edge["target"]}]
        indices = [index for index in range(len(spec["edges"])) if index not in detail]
        endpoints = {nid for index in indices for nid in (spec["edges"][index]["source"], spec["edges"][index]["target"])}
        figure = {"title": "Shared support", "abstract": False,
                  "node_ids": [node["id"] for node in spec["nodes"] if node["id"] in endpoints], "edge_indices": indices}
        plan = flow_layout.build(spec, figure)
        self.assertEqual(len(detail), 7)
        self.assertEqual(len(indices), 16)
        self.assertCountEqual(detail + indices, list(range(23)))
        self.assertEqual(len(plan["macro_nodes"]), len(endpoints))
        host_scope = [container for container in plan["containers"] if container["source_group"] == "g_host"]
        self.assertEqual(len(host_scope), 1)
        height = round(1800 / plan["canvas"]["natural_aspect"])
        scheduler_bottom = plan["boxes"]["n_sched"]["y"] + plan["boxes"]["n_sched"]["height"]
        self.assertLess(scheduler_bottom * height, host_scope[0]["box"]["y"] * height - 20)
        for item in plan["macro_nodes"]:
            self.assertEqual(item["members"], [item["id"]])
            self.assertFalse(item.get("template_slots"))
            self.assertEqual(item["source_owner"], spec["nodes"][item["source_node_index"]]["group"])
        self.assertCountEqual([i for link in plan["macro_edges"] for i in link["members"]], indices)
        scene = structure_scene.prepare(plan)
        self.assertTrue(scene["quality"]["routes_complete"], scene["quality"])
        self.assertEqual(scene["quality"]["route_count"], 16)
        self.assertCountEqual([i for route in scene["routes"] for i in route["members"]], indices)
        self.assertEqual(spec, original)
        self.assertIsNone(flow_layout.build(spec, {**figure, "abstract": True}))

    def test_saved_control_view_has_six_command_targets_and_two_completion_returns(self):
        path = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "publication_benchmark" / "two-input-semantic-v2-result.json"
        spec = json.loads(path.read_text(encoding="utf-8"))["spec"]
        indices = [index for index, item in enumerate(spec["edges"]) if item["kind"] in {"control", "feedback"}]
        endpoints = {nid for index in indices for nid in (spec["edges"][index]["source"], spec["edges"][index]["target"])}
        figure = {"abstract": False, "view_role": "control", "title": "Control and completion",
                  "node_ids": [item["id"] for item in spec["nodes"] if item["id"] in endpoints], "edge_indices": indices}
        original = copy.deepcopy((spec, figure))
        plan = flow_layout.build(spec, figure)
        self.assertEqual((spec, figure), original)
        self.assertEqual(plan["flow_basis"], "control")
        self.assertEqual(plan["view_type"], "graph-led-control")
        self.assertEqual(plan["forward_edge_indices"], list(range(14, 20)))
        self.assertEqual(plan["return_edge_indices"], [20, 21])
        self.assertEqual(plan["feedback_source_nodes"], ["n_result"])
        self.assertEqual(len(plan["macro_nodes"]), 8)
        commands = [item for item in plan["macro_edges"] if item["kind"] == "control"]
        completions = [item for item in plan["macro_edges"] if item["kind"] == "feedback"]
        self.assertCountEqual([item["target"] for item in commands],
                              ["n_dma", "n_unpackA", "n_unpackB", "n_alu", "n_sfu", "n_packer"])
        self.assertCountEqual([(item["source"], item["target"]) for item in completions],
                              [("n_result", "n_ctrl"), ("n_dma", "n_ctrl")])
        for item in commands:
            self.assertEqual(item["source"], "n_ctrl")
            self.assertEqual(item["family"], "control-forward")
            self.assertEqual((item["routing"]["source_side"], item["routing"]["target_side"]), ("right", "left"))
            self.assertFalse(item["routing"]["outer_route"])
            self.assertLess(plan["boxes"]["n_ctrl"]["x"] + plan["boxes"]["n_ctrl"]["width"], plan["boxes"][item["target"]]["x"])
        for item in completions:
            self.assertEqual(item["routing"]["corridor"], "return-outer")
            self.assertTrue(item["routing"]["outer_route"])
        for item, index in zip(plan["macro_edges"], indices):
            self.assertEqual(item["members"], [index])
            self.assertEqual(item["source_edge_index"], index)
            self.assertFalse(item.get("bidirectional"))
            for key in ("source", "target", "kind", "label"):
                self.assertEqual(item[key], spec["edges"][index][key])
        fpu = next(item for item in plan["containers"] if item["source_group"] == "g_fpu")
        self.assertCountEqual(fpu["members"], ["n_alu", "n_sfu"])
        for nid in ("n_unpackA", "n_unpackB"):
            self.assertEqual(plan["source_ownership"][nid], "g_engine")
            self.assertFalse(contains(fpu["box"], plan["boxes"][nid]))
        self.assertAlmostEqual(plan["boxes"]["n_unpackA"]["x"], plan["boxes"]["n_unpackB"]["x"])
        # Real nested scope headings have a clear band below the previous row.
        height = round(1800 / plan["canvas"]["natural_aspect"])
        unpack_bottom = plan["boxes"]["n_unpackB"]["y"] + plan["boxes"]["n_unpackB"]["height"]
        self.assertGreater((fpu["box"]["y"] - unpack_bottom) * height, 30)
        scene = structure_scene.prepare(plan)
        self.assertTrue(scene["quality"]["routes_complete"], scene["quality"])
        self.assertEqual(scene["quality"]["route_count"], 8)
        self.assertCountEqual([i for route in scene["routes"] for i in route["members"]], indices)
        self.assertFalse(any(route["target"] == "n_result" for route in scene["routes"]))
        for item in plan["macro_nodes"]:
            self.assertEqual(item["members"], [item["id"]])
            self.assertEqual(spec["nodes"][item["source_node_index"]]["id"], item["id"])

    def test_control_scope_placement_uses_source_ownership_without_name_rules(self):
        spec = {"title": "Control", "category": "microarchitecture",
                "groups": [{"id": "owner", "label": "Unit", "parent": ""},
                           {"id": "part", "label": "Subunit", "parent": "owner"}],
                "nodes": [node("root", "Dispatch", "control", "owner"), node("a", "Alpha", group="part"),
                          node("b", "Beta", group="owner"), node("c", "Gamma", group="part")],
                "edges": [edge("root", "a", "control"), edge("root", "b", "control"), edge("root", "c", "control")]}
        figure = {"abstract": False, "view_role": "control", "node_ids": [item["id"] for item in spec["nodes"]], "edge_indices": [0, 1, 2]}
        baseline = flow_layout.build(spec, figure)
        changed = copy.deepcopy(spec)
        for item in changed["nodes"] + changed["groups"]:
            item["label"] = "Q" * len(item["label"])
        renamed = flow_layout.build(changed, figure)
        self.assertEqual(baseline["boxes"], renamed["boxes"])
        self.assertEqual(baseline["flow_ranks"], renamed["flow_ranks"])
        scope = next(item for item in baseline["containers"] if item["source_group"] == "part")
        self.assertCountEqual(scope["members"], ["a", "c"])
        self.assertFalse(contains(scope["box"], baseline["boxes"]["b"]))
        self.assertTrue(contains(scope["box"], baseline["boxes"]["a"]))
        self.assertTrue(contains(scope["box"], baseline["boxes"]["c"]))

    def test_label_scale_distinguishes_short_control_view_from_normal_datapath(self):
        path = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "publication_benchmark" / "two-input-semantic-v2-result.json"
        spec = json.loads(path.read_text(encoding="utf-8"))["spec"]
        fonts = {}
        for role, kinds in (("datapath", {"data"}), ("control", {"control", "feedback"})):
            indices = [index for index, item in enumerate(spec["edges"]) if item["kind"] in kinds]
            endpoints = {nid for index in indices for nid in (spec["edges"][index]["source"], spec["edges"][index]["target"])}
            figure = {"abstract": False, "view_role": role,
                      "node_ids": [item["id"] for item in spec["nodes"] if item["id"] in endpoints], "edge_indices": indices}
            plan = flow_layout.build(spec, figure)
            unit = plan["canvas"]["label_unit_pixels"]
            # An interface block with a short label has a 4.5-unit footprint;
            # consumers can use this scale without reconstructing raw layout.
            self.assertAlmostEqual(plan["boxes"]["n_dma"]["width"] * 1800 / 4.5, unit, places=3)
            fonts[role] = min(32, max(20, round(unit)))
        self.assertEqual(fonts, {"datapath": 22, "control": 32})

    def test_control_cycle_keeps_original_kind_and_needs_explicit_control_role(self):
        spec = {"title": "Control dependency", "category": "pipeline", "groups": [],
                "nodes": [node("a", "Issuer", "control"), node("b", "Consumer")],
                "edges": [edge("a", "b", "control"), edge("b", "a", "control")]}
        figure = {"abstract": False, "view_role": "control", "node_ids": ["a", "b"], "edge_indices": [0, 1]}
        plan = flow_layout.build(spec, figure)
        self.assertEqual(plan["forward_edge_indices"], [0])
        self.assertEqual(plan["return_edge_indices"], [1])
        self.assertEqual([item["kind"] for item in plan["macro_edges"]], ["control", "control"])
        self.assertTrue(plan["macro_edges"][1]["routing"]["outer_route"])
        self.assertIsNone(flow_layout.build(spec, {**figure, "view_role": "detail"}))
        self.assertIsNone(flow_layout.build(spec, {**figure, "abstract": True}))
        feedback = copy.deepcopy(spec)
        for item in feedback["edges"]:
            item["kind"] = "feedback"
        self.assertIsNone(flow_layout.build(feedback, figure))
        mixed = copy.deepcopy(spec)
        mixed["edges"][0]["kind"] = "data"
        data_plan = flow_layout.build(mixed, figure)
        self.assertEqual(data_plan["flow_basis"], "data")
        self.assertEqual(data_plan["macro_edges"][1]["routing"]["corridor"], "control-outer")


if __name__ == "__main__":
    unittest.main()
