"""General scope/contract checks independent of the demonstration fixtures."""
import copy
import unittest
from unittest.mock import patch

from silicon_canvas import diagram_design, engine, presentation, publication_layout, reading_plan


def chain(count=9):
    return {"title": "Packet transformations", "category": "dataflow",
            "groups": [{"id": "engine", "label": "Processing engine", "parent": ""}],
            "nodes": [{"id": f"r{i}", "label": f"Stage {i}", "kind": "compute", "group": "engine", "detail": ""}
                      for i in range(count)],
            "edges": [{"source": f"r{i}", "target": f"r{i+1}", "kind": "data", "label": ""}
                      for i in range(count - 1)]}


def primary_plan(raw):
    spec = engine.normalize_spec(raw)
    settings = engine.normalize_settings({"scene": "flow", "representation": "diagram"})
    legacy = presentation.build_plan(spec, settings["density"], settings["language"])
    return reading_plan.build(spec, settings, legacy)["figures"][0]


class MeasuredFlowScopeTests(unittest.TestCase):
    def test_ninth_stage_does_not_erase_all_internal_operation(self):
        for count in (8, 9, 13):
            with self.subTest(count=count):
                figure = primary_plan(chain(count))
                self.assertEqual({node["id"] for node in figure["macro_nodes"]}, {f"r{i}" for i in range(count)})
                self.assertEqual([edge["members"] for edge in figure["macro_edges"]], [[i] for i in range(count-1)])
                self.assertEqual(figure["projection"]["internal_edges"], [])

    def test_unrelated_control_inventory_does_not_change_payload_projection(self):
        raw = chain(6)
        first = primary_plan(raw)
        for i in range(8):
            raw["nodes"].append({"id": f"c{i}", "label": f"Management {i}", "kind": "control", "group": "", "detail": ""})
        second = primary_plan(raw)
        self.assertEqual(first["macro_nodes"], second["macro_nodes"])
        self.assertEqual(first["macro_edges"], second["macro_edges"])
        self.assertEqual(first["projection"]["folded_groups"], second["projection"]["folded_groups"])

    def test_dense_short_graph_does_not_become_infallibly_legible_from_small_count(self):
        raw = chain(4)
        raw["edges"] = [{"source": f"r{i}", "target": f"r{j}", "kind": "data", "label": f"path {i} to {j}"}
                        for i in range(4) for j in range(4) if i != j]
        figure = primary_plan(raw)
        self.assertEqual(len(figure["macro_edges"]), 12)
        self.assertTrue(all(len(edge["members"]) == 1 for edge in figure["macro_edges"]))
        self.assertFalse(any(edge.get("bidirectional") for edge in figure["macro_edges"]))

    def test_owner_summary_cannot_pass_when_it_hides_the_entire_journey(self):
        raw = engine.normalize_spec(chain())
        alternate, reason = reading_plan.flow_owner_alternative(raw, primary_plan(raw), "en")
        self.assertIsNone(alternate)
        self.assertIn("hide every selected relationship", reason)

    def test_owner_alternative_keeps_boundary_source_mapping_and_defers_internals(self):
        raw = chain(10)
        raw["groups"].append({"id": "second", "label": "Second owner", "parent": ""})
        for node in raw["nodes"][5:]:
            node["group"] = "second"
        spec = engine.normalize_spec(raw)
        original = primary_plan(spec)
        alternate, reason = reading_plan.flow_owner_alternative(spec, original, "en")
        self.assertIsNone(reason)
        self.assertEqual(len(alternate["macro_edges"]), 1)
        self.assertEqual(alternate["macro_edges"][0]["members"], [4])
        self.assertEqual(set(alternate["projection"]["internal_edges"]), set(range(9)) - {4})
        self.assertEqual(len(original["macro_nodes"]), 10)

    def test_must_show_object_cannot_be_hidden_to_make_summary_fit(self):
        raw = chain(10)
        raw["groups"].append({"id": "second", "label": "Second owner", "parent": ""})
        for node in raw["nodes"][5:]:
            node["group"] = "second"
        spec = engine.normalize_spec(raw)
        figure = primary_plan(spec)
        figure["required_verbatim_labels"] = ["Stage 2"]
        alternate, reason = reading_plan.flow_owner_alternative(spec, figure, "en")
        self.assertIsNone(alternate)
        self.assertIn("required object text", reason)

    def test_actual_composition_preserves_a_nine_stage_source_without_count_folding(self):
        raw = chain()
        result = engine.compile_manual({"spec": raw, "settings": {"scene": "flow", "representation": "diagram"}})
        figure = result["figures"][0]
        self.assertEqual(len(figure["macro_nodes"]), 9)
        self.assertEqual(len(figure["layout_scene"]["routes"]), 8)
        self.assertTrue(figure["layout_scene"]["quality"]["routes_complete"])
        self.assertEqual(figure["figure_strategy"]["scope"]["deferred_primary_relationships"], 0)
        self.assertTrue(figure["projection_diagnostics"]["candidates"][0]["selected"])
        self.assertEqual(result["spec"], engine.normalize_spec(raw))

    def test_failed_exact_layout_does_not_silently_become_an_empty_owner_card(self):
        with patch("silicon_canvas.publication_layout.build", return_value=None), patch("silicon_canvas.behavior_guide.flow_fallback", return_value=None):
            result = engine.compile_manual({"spec": chain(), "settings": {"scene": "flow", "representation": "diagram"}})
        figure = result["figures"][0]
        self.assertEqual(len(figure["macro_nodes"]), 9)
        self.assertEqual(figure["layout_strategy"], "text-only")
        self.assertEqual(figure["figure_strategy"]["planning_status"], "limited")
        owner = figure["projection_diagnostics"]["candidates"][1]
        self.assertFalse(owner["admissible"])
        self.assertFalse(owner["selected"])
        self.assertEqual(figure["figure_strategy"]["actual_image_status"], "not_reviewed")

    def test_strategy_is_shared_and_selected_alias_does_not_change_source(self):
        raw = chain(4)
        raw["assumptions"] = ["Illustrative resource roles."]
        before = copy.deepcopy(raw)
        result = engine.compile_manual({"spec": raw, "settings": {"scene": "flow", "representation": "diagram"}})
        for figure, public in zip(result["figures"], result["render_plan"]["figures"]):
            self.assertEqual(figure["figure_strategy"], public["figure_strategy"])
            self.assertEqual(figure["figure_strategy"]["scope"]["source_nodes"], 4)
            self.assertEqual(figure["figure_strategy"]["actual_image_status"], "not_reviewed")
            self.assertTrue(figure["figure_strategy"]["not_aesthetic_certification"])
        self.assertEqual(result["figure_strategy"], result["figures"][0]["figure_strategy"])
        self.assertEqual(result["figure_strategy"]["assumptions"]["statements"], raw["assumptions"])
        self.assertEqual(raw, before)

    def test_strategy_distinguishes_top_level_nested_and_leaf_appearances(self):
        spec = engine.normalize_spec(chain(3))
        figure = {"id": "nested", "abstract": True,
                  "macro_nodes": [{"id": "owner", "label": "Owner", "kind": "compute", "members": ["r0", "r1"],
                                   "children": spec["nodes"][:2]}, spec["nodes"][2]], "macro_edges": [], "source_edge_indices": []}
        figure["diagram_design"] = diagram_design.build(spec, figure)
        strategy = diagram_design.figure_strategy(spec, figure)
        self.assertEqual(strategy["scope"]["top_level_objects"], 2)
        self.assertEqual(strategy["scope"]["nested_appearances"], 2)
        self.assertEqual(strategy["scope"]["leaf_appearances"], 3)
        self.assertEqual(strategy["document_size_status"], "not_checked")

    def test_sampled_rows_do_not_falsely_certify_unencoded_source_relationships(self):
        spec = engine.normalize_spec(chain(2))
        spec["category"] = "timing"
        figure = {"id": "samples", "abstract": False, "node_ids": ["r0", "r1"], "edge_indices": [0],
                  "behavior_plan": {"grammar": "sampled-timing"}, "layout_scene": {"routes": [], "quality": {}}}
        figure["diagram_design"] = diagram_design.build(spec, figure)
        strategy = diagram_design.figure_strategy(spec, figure)
        self.assertEqual(strategy["scope"]["relationship_accounting_status"], "not_checked")
        self.assertEqual(strategy["scope"]["not_checked_source_relationships"], [0])
        self.assertIsNone(strategy["scope"]["deferred_relationships"])
        self.assertEqual(strategy["scope"]["visible_source_relationships"], [])

    def test_actual_fallback_scope_reconciles_extra_controls_without_changing_prompt_or_projection(self):
        raw = chain(3)
        raw["edges"].append({"source": "r2", "target": "r0", "kind": "control", "label": "ready"})
        original = publication_layout.build
        def compose(spec, figure, settings):
            return None if figure.get("primary") else original(spec, figure, settings)
        request = {"spec": raw, "settings": {"scene": "flow", "representation": "diagram"}}
        with patch.object(publication_layout, "build", side_effect=compose):
            result = engine.compile_manual(request)
            with patch.object(diagram_design, "reconcile_scope_metadata", side_effect=lambda spec, figure: figure["projection_diagnostics"]):
                before = engine.compile_manual(request)
        figure = result["figures"][0]
        self.assertEqual(figure["layout_strategy"], "semantic-guide")
        self.assertEqual(figure["prompt"], before["figures"][0]["prompt"])
        self.assertEqual(figure["source_edge_indices"], [0, 1])
        self.assertEqual([item["index"] for item in figure["projection"]["deferred_edges"]], [2])
        actual = figure["projection_diagnostics"]["actual_scope"]
        self.assertEqual(actual["source_edge_indices"], [0, 1, 2])
        self.assertEqual(actual["additional_source_edge_indices"], [2])
        candidate = figure["projection_diagnostics"]["candidates"][0]
        self.assertEqual(candidate["attempted_scope"]["visible_relationships"], 2)
        self.assertEqual(candidate["visible_relationships"], 3)
        self.assertEqual(figure["review_task"]["source_scope"], [0, 1, 2])
        self.assertEqual(figure["review_task"]["declared_source_scope"], [0, 1])
        self.assertEqual(figure["figure_strategy"]["actual_scope_accounting_status"], "reconciled-from-controlled-scene")
        self.assertTrue(figure["figure_strategy"]["limitations"])
        self.assertEqual(result["spec"], engine.normalize_spec(raw))


if __name__ == "__main__":
    unittest.main()
