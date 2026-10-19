import copy
import json
from pathlib import Path
import unittest

from silicon_canvas import publication_brief


ROOT = Path(__file__).resolve().parents[1]
STYLE = "STYLE CONTRACT CPS5-paper-old\nPalette: background #FFFFFF; ink #263238; primary #EDF2F5; secondary #E8EEE8; muted #F7F8F9.\nFor a 1600px-wide figure, start with labels F=20–24px."


def source():
    return {"category": "microarchitecture", "title": "Engine", "verbatim_labels": [],
            "groups": [{"id": "g_engine", "label": "Engine", "parent": ""},
                       {"id": "g_fpu", "label": "FPU", "parent": "g_engine"}],
            "nodes": [{"id": "n_ctrl", "label": "Controller", "kind": "control", "group": "g_engine", "detail": "Issue commands"},
                      {"id": "n_alu", "label": "Arithmetic Unit", "kind": "compute", "group": "g_fpu", "detail": "x[3:0] <= 7"},
                      {"id": "n_rf", "label": "Private RF", "kind": "memory", "group": "g_fpu", "detail": "8 banks"}],
            "edges": [{"source": "n_ctrl", "target": "n_alu", "kind": "control", "label": "issue"},
                      {"source": "n_rf", "target": "n_alu", "kind": "data", "label": "operand"},
                      {"source": "n_alu", "target": "n_ctrl", "kind": "feedback", "label": "done"}],
            "steps": [], "annotations": []}


def exact():
    return {"abstract": False, "node_ids": ["n_ctrl", "n_alu", "n_rf"], "edge_indices": [0, 1, 2],
            "design_contract": {"grammar": "control-distribution", "question": "Who receives commands?", "target_width_mm": 160, "body_pt": 9, "signal_pt": 8.5},
            "layout_scene": {"width": 1600, "routes": [{"points": [[0.123456, 0.987654]]}]}}


class PublicationBriefTests(unittest.TestCase):
    def test_owner_identity_prose_is_caption_only_but_real_parameters_and_literals_print(self):
        spec = source()
        spec["groups"][1]["label"] = "Cluster 0"
        spec["nodes"][1]["detail"] = "Cluster 0 scheduling"
        spec["nodes"][2]["detail"] = "Cluster 0 reset value 0"
        prompt = publication_brief.compile_figure(exact(), spec, {"style": "paper"}, "", [])
        self.assertNotIn('supplied parameter or expression "Cluster 0 scheduling"', prompt)
        self.assertIn('supplied parameter or expression "Cluster 0 reset value 0"', prompt)
        literal = publication_brief.compile_figure(exact(), spec, {"style": "paper"}, "", ["Cluster 0 scheduling"])
        self.assertIn('supplied parameter or expression "Cluster 0 scheduling"', literal)

    def test_exact_view_uses_original_edges_and_owners_without_coordinates(self):
        prompt = publication_brief.compile_figure(exact(), source(), {"language": "en"}, STYLE, [])
        self.assertIn('"Controller" -> "Arithmetic Unit" [control]; meaning "issue"', prompt)
        self.assertIn('"Arithmetic Unit" -> "Controller" [feedback]; meaning "done"', prompt)
        self.assertIn('"Arithmetic Unit" — compute; belongs to "FPU"', prompt)
        self.assertIn('original parent "Engine"', prompt)
        self.assertNotIn("0.123456", prompt)
        self.assertNotIn("n_ctrl", prompt)
        self.assertNotIn("CPS5", prompt)
        self.assertNotIn("20–24px", prompt)

    def test_preset_palette_and_print_scale_replace_legacy_font_advice(self):
        figure = exact()
        figure["design_contract"].update(target_width_mm=170, body_pt=10, signal_pt=9)
        prompt = publication_brief.compile_figure(figure, source(), {}, STYLE, [])
        self.assertIn("width 170 mm; module names 10 pt and signal labels 9 pt", prompt)
        self.assertIn("compute fill #EDF2F5", prompt)
        self.assertIn("storage fill #E8EEE8", prompt)

    def test_default_inputs_do_not_inherit_research_references(self):
        figure = exact()
        figure["reference_images"] = [{"path": "a.png"}, {"path": "b.png"}]
        roles = publication_brief.input_roles(figure)
        self.assertEqual(len(roles), 1)
        self.assertEqual(roles[0]["role"], "target_structure")
        self.assertEqual(roles[0]["source"], "layout-guide")
        self.assertIn("regenerate", roles[0]["technical_revision"])

    def test_optional_reference_has_an_explicit_role_and_no_topology_authority(self):
        figure = exact()
        figure["imagegen_style_reference"] = {"path": "style.png"}
        roles = publication_brief.input_roles(figure)
        self.assertEqual(roles[1]["role"], "style_reference")
        self.assertEqual(roles[1]["source"], "style.png")
        prompt = publication_brief.compile_figure(figure, source(), {}, STYLE, [])
        self.assertIn("Image 2: style reference", prompt)
        self.assertIn("Do not copy its topology", prompt)

    def test_projection_preserves_children_without_inventing_their_wiring(self):
        figure = {"abstract": True,
                  "macro_nodes": [{"id": "n_ctrl", "label": "Controller", "kind": "control", "members": ["n_ctrl"]},
                                  {"id": "g_fpu", "label": "FPU", "kind": "compute", "members": ["n_alu", "n_rf"],
                                   "children": [{"id": "n_alu", "label": "Arithmetic Unit", "kind": "compute"},
                                                {"id": "n_rf", "label": "Private RF", "kind": "memory"}]}],
                  "macro_edges": [{"source": "n_ctrl", "target": "g_fpu", "kind": "control", "label": "issue", "members": [0]}]}
        prompt = publication_brief.compile_figure(figure, source(), {}, STYLE, [])
        self.assertIn('"FPU" — compute; belongs to "Engine"; original contents "Arithmetic Unit", "Private RF"', prompt)
        self.assertIn('"Controller" -> "FPU" [control]', prompt)
        self.assertIn("Neither creates a physical bus, port, broadcast", prompt)
        self.assertNotIn('"Arithmetic Unit" -> "Private RF"', prompt)

    def test_exact_parameters_and_mandatory_predicates_are_not_truncated(self):
        prompt = publication_brief.compile_figure(exact(), source(), {}, STYLE, ["x[3:0] <= 7", "Absent other-view label"])
        self.assertIn('supplied parameter or expression "x[3:0] <= 7"', prompt)
        self.assertIn('supplied parameter or expression "8 banks"', prompt)
        self.assertIn('Mandatory verbatim text, only on its matching supplied object: "x[3:0] <= 7"', prompt)
        self.assertNotIn("Absent other-view label", prompt)

    def test_a_selected_view_does_not_include_other_edges_or_global_behavior(self):
        spec = source()
        spec["steps"] = ["Unrelated complete-engine operation"]
        figure = exact()
        figure.update(node_ids=["n_ctrl", "n_alu"], edge_indices=[0])
        prompt = publication_brief.compile_figure(figure, spec, {}, STYLE, [])
        self.assertIn('"Controller" -> "Arithmetic Unit"', prompt)
        self.assertNotIn('"Private RF"', prompt)
        self.assertNotIn('meaning "done"', prompt)
        self.assertNotIn("Unrelated complete-engine operation", prompt)

    def test_source_and_figure_are_immutable(self):
        figure, spec = exact(), source()
        before = copy.deepcopy((figure, spec))
        publication_brief.compile_figure(figure, spec, {}, STYLE, [])
        self.assertEqual((figure, spec), before)

    def test_missing_projection_endpoint_fails_instead_of_inventing_an_object(self):
        figure = exact()
        figure.update(abstract=True, macro_nodes=[], macro_edges=[{"source": "unknown", "target": "n_alu", "kind": "data"}])
        with self.assertRaisesRegex(ValueError, "named source object"):
            publication_brief.compile_figure(figure, source(), {}, STYLE, [])

    def test_normal_engine_source_has_all_fourteen_data_facts_and_a_short_brief(self):
        result = json.loads((ROOT / "tests/fixtures/publication_benchmark/engine-release-cps5.json").read_text(encoding="utf8"))
        figure = next(item for item in result["figures"] if item["view_role"] == "datapath")
        prompt = publication_brief.compile_figure(figure, result["spec"], result["settings"], result["style_prompt"], [])
        by_id = {node["id"]: node["label"] for node in result["spec"]["nodes"]}
        for index in figure["edge_indices"]:
            edge = result["spec"]["edges"][index]
            self.assertIn(json.dumps(by_id[edge["source"]]) + " -> " + json.dumps(by_id[edge["target"]]), prompt)
        self.assertEqual(len(figure["edge_indices"]), 14)
        self.assertLess(len(prompt.split()), 1000)
        self.assertNotIn("Keep the guide path", prompt)

    def test_cps6_engine_projection_keeps_parallel_alternatives_and_real_parent(self):
        result = json.loads((ROOT / "tests/fixtures/editorial_benchmark/engine-reading-plan.json").read_text(encoding="utf8"))
        figure = result["plan"]["figures"][0]
        prompt = publication_brief.compile_figure(figure, result["spec"], result["settings"], STYLE, [])
        self.assertIn('"FPU" — compute; belongs to "Tensor Compute Engine"', prompt)
        self.assertIn("Arithmetic Unit and Special Function Unit are alternative selectable paths; they are not chained in series.", prompt)
        self.assertNotIn('"Arithmetic Unit" -> "Special Function Unit"', prompt)
        self.assertNotIn('Scope "Source Registers A"', prompt)
        self.assertNotIn("n_ctrl", prompt)
        self.assertLess(len(prompt.split()), 1000)

    def test_cps6_gpu_peer_equivalence_has_no_source_id_or_repeated_contents(self):
        result = json.loads((ROOT / "tests/fixtures/editorial_benchmark/gpu-reading-plan.json").read_text(encoding="utf8"))
        figure = result["plan"]["figures"][0]
        prompt = publication_brief.compile_figure(figure, result["spec"], result["settings"], STYLE, [])
        self.assertIn('same explicitly supplied private inventory as "Compute Cluster 0 (Representative)"', prompt)
        self.assertNotIn("g_cluster0", prompt)
        self.assertEqual(prompt.count('original contents "Local Scheduler", "Execution Resources", "Private Register File", "Private L1 Cache"'), 1)
        self.assertNotIn('Scope "Shared Memory System"', prompt)

    def test_planned_text_is_the_only_optional_bitmap_edge_manifest(self):
        spec = source()
        spec["edges"][0]["label"] = "launch and coordinate every arithmetic operation"
        figure = exact()
        figure["label_layout"] = {
            "labels": [{"text": "done", "source_edge_indices": [2], "box": {"x": 0.123456}}],
            "deferred_labels": [{"text": spec["edges"][0]["label"], "source_edge_indices": [0]}],
        }
        prompt = publication_brief.compile_figure(figure, spec, {}, STYLE, [])
        self.assertIn("Edge text authority: Print only the planned edge text", prompt)
        manifest = prompt.split("Planned edge text to print", 1)[1].split("Directed relationships", 1)[0]
        self.assertIn('"done" — for "Arithmetic Unit" -> "Controller"', manifest)
        self.assertNotIn("launch and coordinate", manifest)
        self.assertIn('meaning "launch and coordinate every arithmetic operation" (caption only; do not print as edge text)', prompt)
        self.assertIn('meaning "done".', prompt)
        self.assertNotIn("0.123456", prompt)

    def test_an_empty_planned_manifest_defers_optional_prose_without_losing_edges(self):
        figure = exact()
        figure["label_layout"] = {"labels": [], "deferred_labels": []}
        prompt = publication_brief.compile_figure(figure, source(), {}, STYLE, [])
        self.assertIn("None. Optional edge meanings belong only", prompt)
        self.assertIn('"Controller" -> "Arithmetic Unit" [control]; meaning "issue" (caption only', prompt)
        self.assertIn('"Arithmetic Unit" -> "Controller" [feedback]; meaning "done" (caption only', prompt)

    def test_deferred_required_literal_or_condition_is_rejected_before_generation(self):
        for label, required in [("when ready=1", []), ("4 cycles", []), ("issue", ["issue"])]:
            with self.subTest(label=label):
                figure = exact()
                figure["label_layout"] = {"labels": [], "deferred_labels": [{"text": label}]}
                with self.assertRaisesRegex(ValueError, "Required edge text cannot be deferred"):
                    publication_brief.compile_figure(figure, source(), {}, STYLE, required)

    def test_identical_text_uses_planned_source_mapping_instead_of_global_string_match(self):
        spec = source()
        spec["edges"][0]["label"] = "issue"
        spec["edges"][2]["label"] = "issue"
        figure = exact()
        figure["label_layout"] = {"labels": [{"text": "issue", "source_edge_indices": [0]}],
                                  "deferred_labels": [{"text": "issue", "source_edge_indices": [2]}]}
        prompt = publication_brief.compile_figure(figure, spec, {}, STYLE, [])
        self.assertIn('"Controller" -> "Arithmetic Unit" [control]; meaning "issue".', prompt)
        self.assertIn('"Arithmetic Unit" -> "Controller" [feedback]; meaning "issue" (caption only', prompt)

    def test_publication_finisher_locks_geometry_and_does_not_invite_relayout(self):
        figure = exact()
        figure["layout_strategy"] = "publication-candidates"
        prompt = publication_brief.compile_figure(figure, source(), {}, STYLE, [])
        self.assertIn("clean faithful redraw", prompt)
        self.assertIn("Preserve every arrowhead at its existing endpoint", prompt)
        self.assertIn("exact module arrangement, box dimensions", prompt)
        self.assertIn("Do not move an inlet from a group boundary onto an internal child", prompt)
        self.assertNotIn("not a pixel tracing exercise", prompt)
        self.assertNotIn("Refine symbol dimensions", prompt)

    def test_finisher_counts_visible_pairs_instead_of_canonical_edges(self):
        figure = exact()
        figure["structure_layout"] = {"type": "publication"}
        figure["layout_scene"]["routes"] = [
            {"source": "n_ctrl", "target": "n_alu", "bidirectional": True},
            {"source": "n_rf", "target": "n_alu"},
        ]
        counts = publication_brief.connection_contract(figure)
        self.assertEqual(counts["visible_connections"], 2)
        self.assertEqual(counts["arrowheads"], 3)
        self.assertEqual(counts["double_headed_connections"], 1)
        self.assertIs(counts["print_in_artwork"], False)
        self.assertEqual(publication_brief.input_roles(figure)[0]["connection_contract"], counts)
        prompt = publication_brief.compile_figure(figure, source(), {}, STYLE, [])
        self.assertIn("Verification metadata — never print these numbers in the artwork: 2 visible connections", prompt)
        self.assertIn("exactly 3 arrowheads total", prompt)

    def test_text_only_mode_has_no_image_role_or_false_plate_authority(self):
        figure = exact()
        figure["requires_layout_guide"] = False
        figure["layout_strategy"] = "publication-candidates"
        figure["imagegen_style_reference"] = "style.png"
        figure["label_layout"] = {"labels": [{"text": "done"}], "deferred_labels": []}
        self.assertEqual(publication_brief.input_roles(figure), [])
        self.assertEqual(publication_brief.connection_contract(figure), {})
        prompt = publication_brief.compile_figure(figure, source(), {}, STYLE, [])
        self.assertIn("Text-only semantic contract without a reviewed layout plate", prompt)
        self.assertNotIn("Image 1", prompt)
        self.assertNotIn("Image 2", prompt)
        self.assertNotIn("Print only the planned edge text", prompt)
        self.assertNotIn("clean faithful redraw", prompt)


if __name__ == "__main__":
    unittest.main()
