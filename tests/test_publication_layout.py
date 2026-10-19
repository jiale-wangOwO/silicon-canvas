import copy
import importlib.util
import io
import json
from pathlib import Path
import unittest

from silicon_canvas import publication_layout
from silicon_canvas import publication_render


def fixture():
    groups = [{"id": "owner", "label": "Processing Unit", "parent": ""},
              {"id": "paths", "label": "Compute Paths", "parent": "owner"}]
    labels = [("external", "External Store", "memory", ""),
              ("transfer", "Transfer", "io", "owner"),
              ("first", "Input Transform A", "compute", "owner"),
              ("second", "Input Transform B", "compute", "owner"),
              ("bank_a", "Operand Bank A", "memory", "owner"),
              ("bank_b", "Operand Bank B", "memory", "owner"),
              ("normal", "Regular Unit", "compute", "paths"),
              ("special", "Special Unit", "compute", "paths"),
              ("destination", "Result Bank", "memory", "owner"),
              ("encode", "Encoder", "compute", "owner"),
              ("issue", "Issue Controller", "control", "owner")]
    nodes = [{"id": nid, "label": label, "kind": kind, "group": owner, "detail": ""}
             for nid, label, kind, owner in labels]
    pairs = [("external", "transfer", "read"), ("transfer", "first", "A"), ("transfer", "second", "B"),
             ("first", "bank_a", ""), ("second", "bank_b", ""),
             ("bank_a", "normal", "operand A"), ("bank_b", "normal", "operand B"),
             ("bank_a", "special", "operand A"), ("bank_b", "special", "operand B"),
             ("normal", "destination", ""), ("special", "destination", ""),
             ("destination", "encode", ""), ("encode", "transfer", "encoded result"),
             ("transfer", "external", "write")]
    edges = [{"source": s, "target": t, "kind": "data", "label": label} for s, t, label in pairs]
    edges += [{"source": "issue", "target": target, "kind": "control", "label": "issue command"}
              for target in ["transfer", "first", "second", "normal", "special", "encode"]]
    edges += [{"source": "destination", "target": "issue", "kind": "feedback", "label": "compute done"},
              {"source": "transfer", "target": "issue", "kind": "feedback", "label": "transfer done"}]
    spec = {"title": "Processing Unit", "category": "microarchitecture", "groups": groups,
            "nodes": nodes, "edges": edges, "verbatim_labels": []}
    mapping = {n["id"]: "paths" if n["group"] == "paths" else n["id"] for n in nodes if n["id"] != "issue"}
    macros = [{"id": n["id"], "label": n["label"], "kind": n["kind"], "original_group": n["group"],
               "members": [n["id"]], "children": []} for n in nodes if n["id"] not in {"issue", "normal", "special"}]
    macros.append({"id": "paths", "label": "Compute Paths", "kind": "compute", "original_group": "owner",
                   "source_group": "paths", "members": ["normal", "special"],
                   "children": [{"id": n["id"], "label": n["label"], "kind": n["kind"]} for n in nodes if n["group"] == "paths"]})
    projected = []
    for source, target, indices, label in [("external", "transfer", [0, 13], "read / write"),
            ("transfer", "first", [1], "A"), ("transfer", "second", [2], "B"),
            ("first", "bank_a", [3], ""), ("second", "bank_b", [4], ""),
            ("bank_a", "paths", [5, 7], "operand A"), ("bank_b", "paths", [6, 8], "operand B"),
            ("paths", "destination", [9, 10], ""), ("destination", "encode", [11], ""),
            ("encode", "transfer", [12], "encoded result")]:
        projected.append({"id": "r" + str(len(projected)), "source": source, "target": target, "kind": "data",
                          "label": label, "members": indices, "bidirectional": len(indices) == 2 and source == "external"})
    contract = {"grammar": "folded-flow", "question": "How do operands reach compute and return?",
                "target_width_mm": 160, "body_pt": 9, "signal_pt": 8.5}
    figure = {"id": "primary", "title": spec["title"], "abstract": True, "view_role": "datapath-overview",
              "macro_nodes": macros, "macro_edges": projected, "source_edge_indices": list(range(14)),
              "projection": {"source_node_to_macro": mapping}, "design_contract": contract}
    return spec, figure


@unittest.skipUnless(importlib.util.find_spec("PIL") and publication_render.font_path(), "Guide requires Pillow and a font")
class PublicationLayoutTests(unittest.TestCase):
    def test_folded_projection_keeps_source_and_owner_with_fixed_print_type(self):
        spec, figure = fixture()
        original = copy.deepcopy(spec)
        projection = copy.deepcopy((figure["macro_nodes"], figure["macro_edges"]))
        plan = publication_layout.build(spec, figure, {"language": "en"})
        self.assertIsNotNone(plan, figure.get("composition_diagnostics"))
        self.assertEqual(spec, original)
        self.assertEqual((figure["macro_nodes"], figure["macro_edges"]), projection)
        self.assertEqual(plan["type"], "publication")
        self.assertEqual(plan["typography"]["body_px"], 36)
        self.assertGreaterEqual(plan["typography"]["body_px"] * 160 / 1800 * 72 / 25.4, 9)
        self.assertTrue(plan["typography"]["no_font_shrink"])
        self.assertEqual(plan["source_ownership"], {n["id"]: n["group"] for n in spec["nodes"]})
        self.assertCountEqual([i for edge in plan["layout_scene"]["routes"] for i in edge["members"]], range(14))
        selected = next(c for c in plan["composition_diagnostics"]["candidates"] if c["id"] == plan["candidate_id"])
        self.assertEqual(selected["geometry"]["crossings"], 0)

    def test_folding_inputs_enter_parent_header_not_individual_child(self):
        spec, figure = fixture()
        plan = publication_layout.build(spec, figure, {})
        self.assertTrue(plan["candidate_id"].startswith("folded-input-output"))
        group = plan["boxes"]["paths"]
        children = plan["symbol_metrics"]["paths"]["children"]
        first_child_y = min(c["box_px"]["y"] for c in children)
        incoming = [r for r in plan["layout_scene"]["routes"] if r["target"] == "paths"]
        for route in incoming:
            endpoint_y_px = (route["points"][-1][1] - group["y"]) * plan["layout_scene"]["height"]
            self.assertLess(endpoint_y_px, first_child_y)

    def test_control_uses_real_controller_and_six_independent_drops(self):
        spec, _ = fixture()
        ids = {end for e in spec["edges"][14:] for end in [e["source"], e["target"]]}
        figure = {"id": "control", "title": "Control Interactions", "abstract": False, "view_role": "control",
                  "node_ids": sorted(ids), "edge_indices": list(range(14, 22)),
                  "design_contract": {"grammar": "control-band", "target_width_mm": 160, "body_pt": 9, "signal_pt": 8.5}}
        plan = publication_layout.build(spec, figure, {})
        self.assertIsNotNone(plan, figure.get("composition_diagnostics"))
        routes = plan["layout_scene"]["routes"]
        commands = [r for r in routes if r["kind"] == "control"]
        self.assertEqual(len(commands), 6)
        self.assertEqual(len({tuple(r["points"][0]) for r in commands}), 6)
        self.assertEqual({r["source"] for r in commands}, {"issue"})
        self.assertEqual(len([r for r in routes if r["kind"] == "feedback"]), 2)
        self.assertCountEqual([i for r in routes for i in r["members"]], range(14, 22))

    def test_owner_changes_and_false_group_members_are_rejected(self):
        spec, figure = fixture()
        figure["macro_nodes"][0]["original_group"] = "owner"
        with self.assertRaisesRegex(ValueError, "owner"):
            publication_layout.build(spec, figure, {})
        spec, figure = fixture()
        group = next(n for n in figure["macro_nodes"] if n["id"] == "paths")
        group["members"].append("external")
        with self.assertRaisesRegex(ValueError, "outside"):
            publication_layout.build(spec, figure, {})

    def test_stale_child_label_and_edge_direction_are_rejected(self):
        spec, figure = fixture()
        figure["macro_nodes"][-1]["children"][0]["label"] = "Invented Unit"
        with self.assertRaisesRegex(ValueError, "text/type"):
            publication_layout.build(spec, figure, {})
        spec, figure = fixture()
        figure["macro_edges"][1]["source"], figure["macro_edges"][1]["target"] = "first", "transfer"
        with self.assertRaisesRegex(ValueError, "direction"):
            publication_layout.build(spec, figure, {})

    def test_missing_or_duplicate_source_scope_evidence_is_rejected(self):
        spec, figure = fixture()
        figure["source_edge_indices"].remove(4)
        with self.assertRaisesRegex(ValueError, "scope"):
            publication_layout.build(spec, figure, {})
        spec, figure = fixture()
        figure["macro_edges"][1]["members"].append(1)
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            publication_layout.build(spec, figure, {})

    def test_overfull_typography_returns_failure_without_smaller_type(self):
        spec, figure = fixture()
        long_label = "UNBREAKABLE" * 30
        spec["nodes"][0]["label"] = long_label
        figure["macro_nodes"][0]["label"] = long_label
        self.assertIsNone(publication_layout.build(spec, figure, {}))
        self.assertTrue(figure["composition_diagnostics"]["candidates"])
        self.assertTrue(all(not c["accepted"] for c in figure["composition_diagnostics"]["candidates"]))

    def test_source_numeric_parameters_are_measured_and_rendered(self):
        spec, figure = fixture()
        next(n for n in spec["nodes"] if n["id"] == "bank_a")["detail"] = "64 B"
        plan = publication_layout.build(spec, figure, {})
        self.assertIsNotNone(plan, figure.get("composition_diagnostics"))
        self.assertIn("64 B", plan["symbol_metrics"]["bank_a"]["detail_lines"])
        figure["structure_layout"] = plan
        self.assertTrue(publication_render.render({"spec": spec}, figure))

    def test_numeric_edge_text_is_not_silently_deferred(self):
        spec, figure = fixture()
        label = "128 elements when count >= 64 " * 12
        spec["edges"][1]["label"] = label
        figure["macro_edges"][1]["label"] = label
        self.assertIsNone(publication_layout.build(spec, figure, {}))

    def test_source_reference_id_digits_are_not_image_parameters(self):
        spec, figure = fixture()
        spec["groups"].append({"id": "template_7", "label": "Representative", "parent": ""})
        node = next(n for n in spec["nodes"] if n["id"] == "external")
        node["detail"] = "Same resources as template_7"
        self.assertEqual(publication_render.required_detail(node, spec), "")
        plan = publication_layout.build(spec, figure, {})
        self.assertIsNotNone(plan, figure.get("composition_diagnostics"))
        self.assertEqual(plan["symbol_metrics"]["external"]["detail_lines"], [])
        node["detail"] = "Capacity 7 KiB"
        self.assertEqual(publication_render.required_detail(node, spec), "Capacity 7 KiB")

    def test_prose_conjunction_does_not_masquerade_as_a_bitwise_parameter(self):
        spec, _ = fixture()
        for description in ["Warp issue & scoreboard", "Decode & dispatch", "Scheduling & arbitration"]:
            with self.subTest(description=description):
                self.assertFalse(publication_render.mandatory_text(description))
                self.assertEqual(publication_render.required_detail({"detail": description}, spec), "")
                self.assertEqual(publication_render.required_detail({"detail": description}, spec, [description]), description)
        for expression in ["req & gnt", "mask & flags", "a|b", "valid && ready", "count >= 4", "when ready", "64 KiB"]:
            with self.subTest(expression=expression):
                self.assertTrue(publication_render.mandatory_text(expression))

    def test_settings_literal_is_not_silently_deferred(self):
        spec, figure = fixture()
        figure["required_verbatim_labels"] = ["read / write"]
        self.assertIsNone(publication_layout.build(spec, figure, {}))

    def test_cached_parameter_or_group_parent_change_is_rejected(self):
        spec, figure = fixture()
        next(n for n in spec["nodes"] if n["id"] == "bank_a")["detail"] = "64 B"
        figure["structure_layout"] = publication_layout.build(spec, figure, {})
        self.assertTrue(publication_render.render({"spec": spec}, figure, labels_only=True))
        changed = copy.deepcopy(spec)
        next(n for n in changed["nodes"] if n["id"] == "bank_a")["detail"] = "128 B"
        self.assertIsNone(publication_render.render({"spec": changed}, figure, labels_only=True))
        changed = copy.deepcopy(spec)
        changed["groups"][1]["parent"] = ""
        self.assertIsNone(publication_render.render({"spec": changed}, figure, labels_only=True))

    def test_cached_font_cannot_claim_nine_points_with_smaller_pixels(self):
        spec, figure = fixture()
        figure["structure_layout"] = publication_layout.build(spec, figure, {})
        figure["structure_layout"]["typography"]["body_px"] = 18
        self.assertIsNone(publication_render.render({"spec": spec}, figure, labels_only=True))

    def test_cached_relation_literal_or_condition_change_is_rejected(self):
        spec, figure = fixture()
        figure["structure_layout"] = publication_layout.build(spec, figure, {})
        changed = copy.deepcopy(spec)
        changed["edges"][1]["label"] = "C"
        self.assertIsNone(publication_render.render({"spec": changed}, figure, labels_only=True))
        changed = copy.deepcopy(spec)
        changed["edges"][5]["label"] = "valid && ready"
        self.assertIsNone(publication_render.render({"spec": changed}, figure, labels_only=True))

    def test_optional_ink_header_has_white_common_entry_gutter(self):
        from PIL import Image
        spec, figure = fixture()
        original = copy.deepcopy(spec)
        figure["design_contract"]["symbol_profile"] = "ink-header"
        plan = publication_layout.build(spec, figure, {})
        self.assertIsNotNone(plan, figure.get("composition_diagnostics"))
        figure["structure_layout"] = plan
        self.assertEqual(spec, original)
        measured = plan["symbol_metrics"]["paths"]
        self.assertTrue(measured["ink_header"])
        self.assertGreater(measured["entry_gutter_height"], 0)
        height = plan["layout_scene"]["height"]
        group = plan["boxes"]["paths"]
        incoming = [r for r in plan["layout_scene"]["routes"] if r["target"] == "paths"]
        for route in incoming:
            entry_y = (route["points"][-1][1] - group["y"]) * height
            self.assertGreater(entry_y, measured["header_height"])
            self.assertLess(entry_y, measured["header_height"] + measured["entry_gutter_height"])
            self.assertLess(entry_y, min(c["box_px"]["y"] for c in measured["children"]))
        image = Image.open(io.BytesIO(publication_render.render({"spec": spec}, figure)))
        x, y = group["x"] * 1800, group["y"] * height
        self.assertEqual(image.getpixel((round(x + 6), round(y + 6))), (38, 50, 56))
        self.assertEqual(image.getpixel((round(x + 50), round(y + measured["header_height"] + measured["entry_gutter_height"] / 2))), (255, 255, 255))
        self.assertCountEqual([i for route in plan["layout_scene"]["routes"] for i in route["members"]], range(14))

    def test_common_owner_entries_are_separate_at_document_scale_for_both_profiles(self):
        for profile in ["plain", "ink-header"]:
            with self.subTest(profile=profile):
                spec, figure = fixture()
                original = copy.deepcopy(spec)
                figure["design_contract"]["symbol_profile"] = profile
                plan = publication_layout.build(spec, figure, {})
                self.assertIsNotNone(plan, figure.get("composition_diagnostics"))
                self.assertEqual(spec, original)
                measured = plan["symbol_metrics"]["paths"]
                self.assertGreaterEqual(measured["entry_gutter_height"], 3 * plan["typography"]["body_px"])
                self.assertEqual(measured["entry_port_spacing_px"], 54)
                quality = publication_layout.input_trace_quality(plan, plan["layout_scene"])
                self.assertTrue(quality["clear"], quality)
                owner = next(q for q in quality["owners"] if q["owner"] == "paths")
                self.assertGreaterEqual(owner["minimum_port_gap_px"], 53.9)
                # Port separation is >=1.5F.  Tiny router grid stubs may lower
                # whole-path distance slightly, but it remains >=one full F.
                self.assertGreaterEqual(owner["minimum_path_clearance_px"], 36)
                self.assertFalse(owner["paths_touch_or_share"])
                incoming = [r for r in plan["layout_scene"]["routes"] if r["target"] == "paths"]
                upper = min(incoming, key=lambda r: plan["boxes"][r["source"]]["y"])
                source = plan["boxes"][upper["source"]]
                producer_y = (source["y"] + source["height"] / 2) * plan["layout_scene"]["height"]
                target_y = upper["points"][-1][1] * plan["layout_scene"]["height"]
                self.assertGreaterEqual(target_y + .1, producer_y)
                self.assertLess(target_y - producer_y, 18.1)
                self.assertCountEqual([i for r in plan["layout_scene"]["routes"] for i in r["members"]], range(14))

    def test_cached_input_contact_or_old_narrow_gutter_is_rejected(self):
        spec, figure = fixture()
        figure["design_contract"]["symbol_profile"] = "ink-header"
        figure["structure_layout"] = publication_layout.build(spec, figure, {})
        changed = copy.deepcopy(figure)
        incoming = [r for r in changed["layout_scene"]["routes"] if r["target"] == "paths"]
        common_y = incoming[0]["points"][-1][1]
        incoming[1]["points"][-1][1] = common_y
        incoming[1]["points"][-2][1] = common_y
        # Do not trust a stale or manually asserted ready/clear flag.
        changed["layout_scene"]["quality"]["input_traces"]["clear"] = True
        self.assertIsNone(publication_render.render({"spec": spec}, changed, labels_only=True))
        changed = copy.deepcopy(figure)
        changed["structure_layout"]["symbol_metrics"]["paths"]["entry_gutter_height"] = 51
        self.assertIsNone(publication_render.render({"spec": spec}, changed, labels_only=True))

    def test_optional_profile_does_not_change_control_graph_or_ordinary_boundaries(self):
        spec, _ = fixture()
        ids = {end for e in spec["edges"][14:] for end in [e["source"], e["target"]]}
        base = {"id": "control", "title": "Control", "abstract": False, "view_role": "control",
                "node_ids": sorted(ids), "edge_indices": list(range(14, 22)),
                "design_contract": {"grammar": "control-band", "target_width_mm": 160, "body_pt": 9, "signal_pt": 8.5}}
        base["structure_layout"] = publication_layout.build(spec, base, {})
        optional = copy.deepcopy(base)
        optional["design_contract"]["symbol_profile"] = "ink-header"
        optional["structure_layout"] = publication_layout.build(spec, optional, {})
        self.assertEqual(base["layout_scene"]["routes"], optional["layout_scene"]["routes"])
        self.assertFalse(any(m.get("ink_header") for m in optional["structure_layout"]["symbol_metrics"].values()))
        self.assertEqual(publication_render.render({"spec": spec}, base), publication_render.render({"spec": spec}, optional))

    def test_guide_is_real_png_and_stale_route_endpoint_is_rejected(self):
        from PIL import Image
        spec, figure = fixture()
        figure["structure_layout"] = publication_layout.build(spec, figure, {})
        data = publication_render.render({"spec": spec}, figure)
        self.assertIsInstance(data, bytes)
        self.assertEqual(Image.open(io.BytesIO(data)).width, 1800)
        labels = publication_render.render({"spec": spec}, figure, labels_only=True)
        self.assertEqual(labels["body_font_px"], 36)
        changed = copy.deepcopy(figure)
        source = changed["structure_layout"]["boxes"][changed["layout_scene"]["routes"][0]["source"]]
        changed["layout_scene"]["routes"][0]["points"][0] = [source["x"] + source["width"] / 2, source["y"] + source["height"] / 2]
        self.assertIsNone(publication_render.render({"spec": spec}, changed))

    def test_chinese_labels_keep_same_measurement_and_render_font(self):
        spec, figure = fixture()
        for n in spec["nodes"]:
            if n["id"] == "external":
                n["label"] = "外部存储"
        figure["macro_nodes"][0]["label"] = "外部存储"
        plan = publication_layout.build(spec, figure, {"language": "zh"})
        self.assertIsNotNone(plan, figure.get("composition_diagnostics"))
        figure["structure_layout"] = plan
        self.assertTrue(publication_render.render({"spec": spec}, figure))
        if "Windows" in publication_render.font_path():
            self.assertTrue(publication_render.font_path().endswith("msyh.ttc"))

    def test_resource_partial_adjacency_does_not_add_peer_access_or_copy_inventory(self):
        path = Path(__file__).resolve().parent.parent / "tests/fixtures/editorial_benchmark/gpu-reading-plan.json"
        if not path.is_file():
            self.skipTest("Saved API projection fixture is not available")
        original = json.loads(path.read_text(encoding="utf-8"))
        figure = copy.deepcopy(original["plan"]["figures"][0])
        family = figure["repeat_families"][0]
        peers = set(family["instances"])
        omitted = [e for e in figure["macro_edges"] if e["kind"] == "data" and peers & {e["source"], e["target"]}]
        figure["macro_edges"] = [e for e in figure["macro_edges"] if e not in omitted]
        figure["source_edge_indices"] = sorted(i for e in figure["macro_edges"] for i in e["members"])
        plan = publication_layout.build(original["spec"], figure, original["settings"])
        self.assertIsNotNone(plan, figure.get("composition_diagnostics"))
        self.assertFalse(any(r["kind"] == "data" and peers & {r["source"], r["target"]} for r in plan["layout_scene"]["routes"]))
        storage = next(n for n in plan["macro_nodes"] if n["kind"] == "memory" and n.get("zone") == "memory")
        self.assertLess(plan["boxes"][storage["id"]]["width"], .4)
        self.assertEqual(len(plan["insets"]), 1)
        inset = plan["insets"][0]
        self.assertEqual(inset["source_object"], family["template_group"])
        self.assertTrue(inset["same_hardware"])
        self.assertFalse(any(n.get("children") for n in plan["macro_nodes"] if n["id"] in peers))
        figure["structure_layout"] = plan
        self.assertTrue(publication_render.render({"spec": original["spec"]}, figure))

    def test_exact_small_flow_uses_measured_layout_but_fsm_keeps_fallback(self):
        spec, figure = fixture()
        figure["design_contract"]["grammar"] = "exact-flow"
        exact = {"id": "small", "title": "A Small Data Path", "abstract": False, "view_role": "datapath",
                 "node_ids": ["external", "transfer", "first"], "edge_indices": [0, 1],
                 "design_contract": {"grammar": "exact-flow", "body_pt": 9, "signal_pt": 8.5, "target_width_mm": 160}}
        self.assertIsNotNone(publication_layout.build(spec, exact, {}), exact.get("composition_diagnostics"))
        spec["category"] = "fsm"
        self.assertIsNone(publication_layout.build(spec, exact, {}))

    def test_three_node_payload_and_ready_condition_fit_at_publication_type(self):
        spec = {"title": "Transfer Pipeline", "category": "dataflow", "groups": [], "verbatim_labels": [],
                "nodes": [{"id": "in", "label": "DMA", "kind": "io", "group": "", "detail": ""},
                          {"id": "hold", "label": "Buffer", "kind": "memory", "group": "", "detail": ""},
                          {"id": "work", "label": "MAC", "kind": "compute", "group": "", "detail": ""}],
                "edges": [{"source": "in", "target": "hold", "kind": "data", "label": "payload[31:0]"},
                          {"source": "hold", "target": "work", "kind": "data", "label": "ready=1"}]}
        figure = {"id": "small", "title": spec["title"], "abstract": False, "view_role": "datapath",
                  "node_ids": ["in", "hold", "work"], "edge_indices": [0, 1],
                  "design_contract": {"grammar": "exact-flow", "body_pt": 9, "signal_pt": 8.5, "target_width_mm": 160}}
        plan = publication_layout.build(spec, figure, {})
        self.assertIsNotNone(plan, figure.get("composition_diagnostics"))
        self.assertEqual(plan["typography"]["body_px"], 36)
        self.assertEqual(plan["typography"]["signal_px"], 34)
        figure["structure_layout"] = plan
        labels = publication_render.render({"spec": spec}, figure, labels_only=True)
        self.assertEqual({item["text"] for item in labels["labels"]}, {"payload[31:0]", "ready=1"})
        self.assertEqual(labels["deferred_labels"], [])
        self.assertTrue(publication_render.render({"spec": spec}, figure))

    def ownership_fixture(self, name):
        from silicon_canvas import reading_plan
        path = Path(__file__).resolve().parent.parent / ("tests/fixtures/editorial_benchmark/" + name + ".json")
        if not path.is_file():
            self.skipTest("Saved normal API source fixture is not available")
        saved = json.loads(path.read_text(encoding="utf-8"))
        figure = reading_plan._ownership_main(saved["spec"], saved["settings"].get("language", "en"))
        figure["design_contract"]["symbol_profile"] = "ink-header"
        return saved, figure

    def test_single_owner_quantity_uses_native_document_composition_without_copying_instances(self):
        saved, figure = self.ownership_fixture("fresh-gpu-result")
        original = copy.deepcopy(saved["spec"])
        projected = copy.deepcopy((figure["macro_nodes"], figure["macro_edges"]))
        plan = publication_layout.build(saved["spec"], figure, saved["settings"])
        self.assertIsNotNone(plan, figure.get("composition_diagnostics"))
        self.assertEqual(saved["spec"], original)
        self.assertEqual((figure["macro_nodes"], figure["macro_edges"]), projected)
        self.assertEqual(plan["candidate_id"], "left-to-right-1")
        self.assertEqual(plan["typography"]["body_px"], 36)
        self.assertEqual(plan["layout_scene"]["quality"]["document_fit"]["status"], "pass")
        self.assertLessEqual(plan["layout_scene"]["quality"]["document_fit"]["height_mm"], 140)
        quantities = [node for node in plan["macro_nodes"] if "x4" in node["label"]]
        self.assertEqual(len(quantities), 1)
        self.assertEqual(len(quantities[0]["children"]), 4)
        mapped = {i for e in plan["layout_scene"]["routes"] for i in e["members"]}
        self.assertEqual(mapped | set(plan["projection"]["internal_edges"]), set(range(15)))
        self.assertTrue(any(e["kind"] == "control" and "x4" in e["label"] for e in plan["layout_scene"]["routes"]))
        objects = {n["id"]: n for n in plan["macro_nodes"]}
        entry = next(e for e in plan["layout_scene"]["routes"] if not objects[e["source"]]["children"])
        self.assertEqual(entry["source_side"], "bottom")
        self.assertEqual(entry["target_side"], "left")
        outputs = [e for e in plan["layout_scene"]["routes"] if e["source"] == entry["target"]]
        self.assertTrue(outputs)
        self.assertTrue(all(e["source_side"] == "right" for e in outputs))
        width, height = plan["layout_scene"]["width"], plan["layout_scene"]["height"]
        incoming_points = [(x * width, y * height) for x, y in entry["points"]]
        for edge in outputs:
            outgoing_points = [(x * width, y * height) for x, y in edge["points"]]
            clearance = min(publication_layout._segment_distance(a, b, c, d) for a, b in zip(incoming_points, incoming_points[1:])
                            for c, d in zip(outgoing_points, outgoing_points[1:]))
            self.assertGreaterEqual(clearance, 54)
        figure["structure_layout"] = plan
        self.assertTrue(publication_render.render(saved, figure))

    def test_ownership_internal_evidence_cannot_hide_a_cross_owner_relationship(self):
        saved, figure = self.ownership_fixture("fresh-gpu-result")
        crossing = figure["macro_edges"][0]["members"][0]
        figure["projection"]["internal_edges"].append(crossing)
        with self.assertRaisesRegex(ValueError, "crosses display owners"):
            publication_layout.build(saved["spec"], figure, saved["settings"])
        saved, figure = self.ownership_fixture("fresh-gpu-result")
        figure["source_edge_indices"].remove(figure["projection"]["internal_edges"][0])
        with self.assertRaisesRegex(ValueError, "scope"):
            publication_layout.build(saved["spec"], figure, saved["settings"])

    def test_owned_inventory_arrows_enter_common_strip_including_outputs_and_plain_profile(self):
        saved, base = self.ownership_fixture("fresh-gpu-result")
        for profile in ["plain", "ink-header"]:
            with self.subTest(profile=profile):
                figure = copy.deepcopy(base)
                figure["design_contract"]["symbol_profile"] = profile
                plan = publication_layout.build(saved["spec"], figure, saved["settings"])
                self.assertIsNotNone(plan, figure.get("composition_diagnostics"))
                self.assertTrue(publication_layout.owner_scope_quality(plan, plan["layout_scene"])["clear"])
                figure["structure_layout"] = plan
                self.assertTrue(publication_render.render(saved, figure))
                for route in plan["layout_scene"]["routes"]:
                    for nid, point in [(route["source"], route["points"][0]), (route["target"], route["points"][-1])]:
                        measured = plan["symbol_metrics"][nid]
                        if not measured["children"]:
                            continue
                        local_y = (point[1] - plan["boxes"][nid]["y"]) * plan["layout_scene"]["height"]
                        self.assertGreater(local_y, measured["header_height"])
                        self.assertLess(local_y, min(c["box_px"]["y"] for c in measured["children"]))
                changed = copy.deepcopy(figure)
                route = next(r for r in changed["layout_scene"]["routes"] if plan["symbol_metrics"][r["target"]]["children"])
                target = plan["boxes"][route["target"]]
                measured = plan["symbol_metrics"][route["target"]]
                route["points"][-1][1] = target["y"] + (measured["children"][0]["box_px"]["y"] + 20) / plan["layout_scene"]["height"]
                self.assertIsNone(publication_render.render(saved, changed, labels_only=True))

    def test_existing_hub_keeps_complete_owner_inventory_and_real_offchip_context(self):
        saved, figure = self.ownership_fixture("fresh-soc-physical-result")
        original = copy.deepcopy(saved["spec"])
        plan = publication_layout.build(saved["spec"], figure, saved["settings"])
        self.assertIsNotNone(plan, figure.get("composition_diagnostics"))
        self.assertEqual(saved["spec"], original)
        self.assertEqual(plan["candidate_id"], "ownership-hub-2")
        self.assertEqual(plan["containers"], [])
        self.assertEqual(len(plan["layout_scene"]["routes"]), 8)
        self.assertEqual(plan["layout_scene"]["quality"]["document_fit"]["status"], "pass")
        self.assertLessEqual(plan["layout_scene"]["quality"]["document_fit"]["height_mm"], 140)
        selected = next(c for c in plan["composition_diagnostics"]["candidates"] if c["id"] == plan["candidate_id"])
        self.assertEqual(selected["geometry"]["crossings"], 0)
        displayed = {c["id"] for n in plan["macro_nodes"] for c in n.get("children", [])}
        clocks = [n for n in saved["spec"]["nodes"] if "Clock" in n["label"]]
        self.assertEqual(len(clocks), 1)
        self.assertIn(clocks[0]["id"], displayed)
        for node in plan["macro_nodes"]:
            if node.get("source_group"):
                self.assertEqual(set(node["members"]), {n["id"] for n in saved["spec"]["nodes"] if n["group"] == node["source_group"]})
        self.assertTrue(publication_layout.owner_scope_quality(plan, plan["layout_scene"])["clear"])
        self.assertTrue(publication_layout.input_trace_quality(plan, plan["layout_scene"])["clear"])
        self.assertTrue(publication_layout.organization_trace_quality(plan, plan["layout_scene"])["clear"])
        figure["structure_layout"] = plan
        self.assertTrue(publication_render.render(saved, figure))

    def test_organization_gate_rejects_elbow_touch_even_without_strict_crossing(self):
        scene = {"width": 1800, "height": 1000, "routes": [
            {"id": "primary", "points": [[.2, .4], [.4, .4], [.6, .4]]},
            {"id": "secondary", "points": [[.4, .2], [.4, .4], [.4, .6]]}]}
        self.assertEqual(publication_layout._route_metrics(scene)["crossings"], 0)
        quality = publication_layout.organization_trace_quality({"view_type": "publication-ownership-flow"}, scene)
        self.assertFalse(quality["clear"])
        self.assertEqual(quality["contacts"][0]["routes"], ["primary", "secondary"])

    def test_hub_composition_depends_on_real_topology_not_product_ids(self):
        from silicon_canvas import reading_plan
        saved, _ = self.ownership_fixture("fresh-soc-physical-result")
        spec = saved["spec"]
        aliases = {item["id"]: "object_" + str(index) for index, item in enumerate(spec["nodes"] + spec["groups"])}
        for node in spec["nodes"]:
            node["id"] = aliases[node["id"]]
            node["group"] = aliases.get(node["group"], "")
        for group in spec["groups"]:
            group["id"] = aliases[group["id"]]
            group["parent"] = aliases.get(group["parent"], "")
        for edge in spec["edges"]:
            edge["source"], edge["target"] = aliases[edge["source"]], aliases[edge["target"]]
        figure = reading_plan._ownership_main(spec, "en")
        figure["design_contract"]["symbol_profile"] = "ink-header"
        plan = publication_layout.build(spec, figure, saved["settings"])
        self.assertIsNotNone(plan, figure.get("composition_diagnostics"))
        self.assertEqual(plan["candidate_id"], "ownership-hub-2")
        self.assertEqual(plan["layout_scene"]["quality"]["document_fit"]["height_mm"], 138.1)
        self.assertTrue(publication_layout.organization_trace_quality(plan, plan["layout_scene"])["clear"])


if __name__ == "__main__":
    unittest.main()
