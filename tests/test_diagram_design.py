import copy
import json
from pathlib import Path
import unittest

from silicon_canvas import diagram_design, engine, publication_brief


ROOT = Path(__file__).resolve().parents[1]


def source(category="dataflow"):
    return {"title": "Sample transfer", "category": category, "summary": "", "verbatim_labels": [],
            "groups": [{"id": "private", "label": "Private engine", "parent": ""}],
            "nodes": [{"id": "input", "label": "Input", "kind": "io", "group": "", "detail": ""},
                      {"id": "left", "label": "Transform A", "kind": "compute", "group": "private", "detail": ""},
                      {"id": "right", "label": "Transform B", "kind": "compute", "group": "private", "detail": ""},
                      {"id": "output", "label": "Output storage", "kind": "memory", "group": "", "detail": ""}],
            "edges": [{"source": "input", "target": "left", "kind": "data", "label": "a[31:0]"},
                      {"source": "input", "target": "right", "kind": "data", "label": "b[31:0]"},
                      {"source": "left", "target": "output", "kind": "data", "label": ""},
                      {"source": "right", "target": "output", "kind": "data", "label": ""},
                      {"source": "output", "target": "input", "kind": "feedback", "label": "return payload"}],
            "layout": "", "steps": [], "annotations": [], "assumptions": [], "questions": [], "checks": []}


def exact(spec):
    return {"id": "all", "abstract": False, "node_ids": [node["id"] for node in spec["nodes"]],
            "edge_indices": list(range(len(spec["edges"]))), "context_nodes": [],
            "design_contract": {"target_width_mm": 160, "body_pt": 9, "signal_pt": 8.5}}


class DiagramDesignTests(unittest.TestCase):
    def test_fork_join_and_same_resource_return_are_source_driven(self):
        spec = source()
        plan = diagram_design.build(spec, exact(spec))
        self.assertEqual(plan["reading_strategy"]["kind"], "fork-join-return")
        self.assertEqual(plan["connection_plan"]["fork_nodes"], ["input"])
        self.assertEqual(plan["connection_plan"]["join_nodes"], ["output"])
        self.assertEqual(plan["burden"]["leaf_appearances"], 4)
        self.assertEqual(plan["burden"]["visible_connections"], 5)
        self.assertEqual(plan["reading_strategy"]["cycle_components"], [["input", "left", "output", "right"]])
        self.assertIn("same resource", plan["render_instructions"][0])
        self.assertEqual(plan["actual_image_status"], "not_reviewed")
        self.assertNotIn("beauty_score", plan)

    def test_fsm_and_timing_have_distinct_non_hardware_reading_grammars(self):
        for category, expected, forbidden in [("fsm", "state-transition", "source-transform-sink"),
                                               ("timing", "signal-time", "source-transform-sink")]:
            with self.subTest(category=category):
                spec = source(category)
                plan = diagram_design.build(spec, exact(spec))
                self.assertEqual(plan["reading_strategy"]["kind"], expected)
                self.assertNotEqual(plan["reading_strategy"]["kind"], forbidden)
                self.assertNotEqual(plan["reading_strategy"]["direction"], "left-to-right")
                if category == "timing":
                    self.assertIn("one supplied time/event axis", plan["render_instructions"][0])
                    self.assertIn("never invented waveforms or latency", plan["render_instructions"][0])
                else:
                    self.assertIn("conditions sit on their transition", plan["render_instructions"][0])
                    self.assertIn("do not turn states into a numbered linear pipeline", plan["render_instructions"][0])

    def test_real_owners_and_outside_context_remain_distinct_from_display_bands(self):
        spec = source("architecture")
        figure = exact(spec)
        figure["context_nodes"] = ["output"]
        plan = diagram_design.build(spec, figure)
        owners = {item["source_node_id"]: item["source_owner_path"] for item in plan["inventory"]["appearances"]}
        self.assertEqual(owners["left"], ["private"])
        self.assertEqual(owners["output"], [])
        self.assertEqual(plan["ownership"]["context_node_ids"], ["output"])
        self.assertTrue(plan["ownership"]["display_bands_are_not_owners"])
        self.assertEqual(plan["reading_strategy"]["kind"], "ownership-network")

    def test_nested_contents_count_real_visual_burden_not_only_macros(self):
        spec = source()
        figure = {"abstract": True, "macro_nodes": [{"id": "scope", "label": "Private engine", "kind": "compute",
                  "members": ["left", "right"], "children": [spec["nodes"][1], spec["nodes"][2]]}, spec["nodes"][3]],
                  "macro_edges": [], "source_edge_indices": []}
        plan = diagram_design.build(spec, figure)
        self.assertEqual(plan["burden"]["top_level_objects"], 2)
        self.assertEqual(plan["burden"]["nested_appearances"], 2)
        self.assertEqual(plan["burden"]["leaf_appearances"], 3)
        self.assertEqual(plan["burden"]["unique_source_leaves"], 3)
        self.assertEqual(plan["burden"]["text_items"], 4)

    def test_compact_peer_contract_matches_actual_guide_instead_of_initial_expansion(self):
        spec = source()
        representative = {"id": "scope", "label": "Private engine", "kind": "compute", "members": ["left", "right"],
                          "children": [spec["nodes"][1], spec["nodes"][2]]}
        peer = {"id": "peer", "label": "Equivalent peer", "kind": "compute", "members": ["left", "right"],
                "equivalent_to": "scope", "children": [spec["nodes"][1], spec["nodes"][2]]}
        figure = {"abstract": True, "macro_nodes": [representative, peer], "macro_edges": [], "source_edge_indices": [],
                  "structure_layout": {"type": "publication", "macro_nodes": [{**representative, "children": []}, {**peer, "children": []}],
                    "macro_edges": [], "symbol_metrics": {"scope": {"children": []}, "peer": {"children": []}},
                    "insets": [{"id": "same-detail", "source_object": "scope", "same_hardware": True,
                                "metrics": {"children": representative["children"]}}]}}
        plan = diagram_design.build(spec, figure)
        modes = {item["display_id"]: item["shown_inventory"] for item in plan["repeated_instances"]}
        self.assertEqual(modes, {"scope": "representative-inset", "peer": "compact-peer"})
        self.assertEqual(plan["inventory"]["same_hardware_expansions"], ["scope"])
        self.assertEqual(plan["burden"]["nested_appearances"], 3)  # inset header + two actual children
        figure["diagram_design"] = plan
        prompt = publication_brief.compile_figure(figure, spec, {}, "", [])
        self.assertIn('Same-hardware detail expansion of "Private engine" contains "Transform A", "Transform B"', prompt)
        self.assertEqual(prompt.count('original contents "Transform A", "Transform B"'), 0)
        self.assertIn("Keep this peer compact", prompt)

    def test_expanded_equivalent_peer_is_never_told_to_hide_its_actual_children(self):
        spec = source()
        figure = {"abstract": True, "macro_nodes": [{"id": "scope", "label": "Private engine", "kind": "compute", "members": ["left", "right"], "children": []},
                  {"id": "peer", "label": "Peer", "kind": "compute", "members": ["left", "right"], "equivalent_to": "scope",
                   "children": [spec["nodes"][1], spec["nodes"][2]]}], "macro_edges": [], "source_edge_indices": []}
        figure["diagram_design"] = diagram_design.build(spec, figure)
        self.assertEqual(figure["diagram_design"]["repeated_instances"][0]["shown_inventory"], "expanded-in-place")
        prompt = publication_brief.compile_figure(figure, spec, {}, "", [])
        self.assertIn("Preserve its shown private contents", prompt)
        self.assertNotIn("Keep this peer compact", prompt)

    def test_pressure_proposes_source_backed_perspectives_and_never_small_type(self):
        spec = source()
        spec["nodes"] += [{"id": f"item{i}", "label": f"Resource {i}", "kind": "compute", "group": "private", "detail": ""} for i in range(22)]
        before = copy.deepcopy(spec)
        plan = diagram_design.build(spec, exact(spec))
        self.assertEqual(plan["composition_action"]["status"], "recompose")
        self.assertTrue(any("20 visible leaf" in reason for reason in plan["composition_action"]["reasons"]))
        self.assertEqual(plan["typography"]["body_pt"], 9)
        self.assertEqual(spec, before)
        for perspective in plan["composition_action"]["source_backed_perspectives"]:
            self.assertTrue(set(perspective.get("source_node_ids", [])).issubset({node["id"] for node in spec["nodes"]}))

    def test_source_id_title_palette_changes_do_not_change_general_reading_strategy(self):
        spec = source()
        first = diagram_design.build(spec, exact(spec), {"style": "paper"})
        renamed = copy.deepcopy(spec)
        renamed["title"] = "Different domain"
        mapping = {node["id"]: f"x{index}" for index, node in enumerate(renamed["nodes"])}
        for node in renamed["nodes"]:
            node["id"] = mapping[node["id"]]
            node["label"] = "Role " + node["id"]
        for edge in renamed["edges"]:
            edge["source"] = mapping[edge["source"]]; edge["target"] = mapping[edge["target"]]
        second = diagram_design.build(renamed, exact(renamed), {"style": "monochrome"})
        self.assertEqual(first["reading_strategy"]["kind"], second["reading_strategy"]["kind"])
        self.assertEqual(first["burden"]["leaf_appearances"], second["burden"]["leaf_appearances"])
        self.assertEqual(first["burden"]["visible_connections"], second["burden"]["visible_connections"])
        self.assertNotEqual(first["source_hash"], second["source_hash"])

    def test_engine_exposes_same_design_to_caption_review_and_public_plan(self):
        spec = source()
        result = engine.compile_manual({"spec": spec, "settings": {"scene": "flow"}})
        self.assertEqual(result["spec"], engine.normalize_spec(spec))
        for figure, exported in zip(result["figures"], result["render_plan"]["figures"]):
            self.assertEqual(figure["diagram_design"], exported["diagram_design"])
            self.assertEqual(figure["diagram_design"], figure["review_task"]["diagram_design"])
            self.assertEqual(figure["diagram_design"]["source_hash"], result["source_hash"])
            self.assertIn(figure["diagram_design"]["reading_question"], figure["caption"])
            self.assertEqual(figure["diagram_design"]["actual_image_status"], "not_reviewed")

    def test_generic_holdouts_receive_plans_without_changing_source_ledger(self):
        fixtures = list((ROOT / "tests/fixtures/design_coverage").glob("*.json"))
        self.assertGreaterEqual(len(fixtures), 10)
        for path in fixtures:
            with self.subTest(case=path.name):
                payload = json.loads(path.read_text(encoding="utf-8"))
                spec = payload.get("spec", payload)
                if "nodes" not in spec:
                    continue
                before = copy.deepcopy(spec)
                plan = diagram_design.build(spec, exact(spec))
                self.assertEqual(spec, before)
                self.assertEqual(plan["burden"]["top_level_objects"], len(spec["nodes"]))
                self.assertTrue(plan["reading_question"])
                self.assertEqual(plan["actual_image_status"], "not_reviewed")


if __name__ == "__main__":
    unittest.main()
