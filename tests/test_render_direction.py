"""A sparse product explanation still preserves each selected relation's meaning."""
import copy
import unittest

from silicon_canvas import engine, quality_review, render_brief


def source():
    return engine.normalize_spec({"title": "Product system", "category": "architecture", "groups": [],
                                  "nodes": [{"id": "core", "label": "Compute", "kind": "compute"},
                                            {"id": "mem", "label": "Storage", "kind": "memory"},
                                            {"id": "host", "label": "External Host", "kind": "io"}],
                                  "edges": [{"source": "core", "target": "mem", "kind": "data", "label": "write"},
                                            {"source": "mem", "target": "core", "kind": "data", "label": "read"},
                                            {"source": "core", "target": "mem", "kind": "relation", "label": "interface"},
                                            {"source": "host", "target": "core", "kind": "relation", "label": "host interface"}]})


def compile_brief(spec=None, mode="functional_cutaway", description="整体产品的功能组织"):
    spec = source() if spec is None else spec
    settings = engine.normalize_settings({"representation": "system_illustration", "scene": "concept"})
    settings["explanatory_mode"] = mode
    figure = render_brief.primary(spec, "system_illustration")
    prompt = render_brief.compile_figure(figure, spec, settings, description)
    return figure, prompt


class RenderDirectionTests(unittest.TestCase):
    def test_source_data_direction_does_not_require_user_to_say_arrow(self):
        figure, prompt = compile_brief()
        visible = figure["render_brief"]["visible_content"]
        self.assertFalse(visible["relationship_portrayal"]["directed_traffic"])
        data = [rel for rel in visible["relationships"] if "data" in rel["kinds"]]
        self.assertEqual({tuple(pair) for rel in data for pair in rel["source_node_pairs"]}, {("core", "mem"), ("mem", "core")})
        self.assertTrue(all(rel["directionality"] == "source-directed" for rel in data))
        self.assertIn("Compute -> Storage: write", prompt)
        self.assertIn("Storage -> Compute: read", prompt)
        self.assertNotIn("without arrowheads", prompt)

    def test_association_is_not_absorbed_into_directed_payload(self):
        figure, prompt = compile_brief()
        relations = figure["render_brief"]["visible_content"]["relationships"]
        association = next(rel for rel in relations if rel["source_edge_indices"] == [2])
        self.assertEqual(association["directionality"], "association")
        self.assertIn("Compute ~ Storage", prompt)
        self.assertIn("Compute -> Storage: write", prompt)
        self.assertEqual({index for rel in relations for index in rel["source_edge_indices"]}, {0, 1, 2, 3})

    def test_context_association_and_external_payload_use_distinct_semantics(self):
        spec = source()
        spec["edges"].append({"source": "core", "target": "host", "kind": "data", "label": "result", "origin": "given", "evidence": "", "rationale": ""})
        figure, prompt = compile_brief(spec, mode="annotated_context")
        self.assertIn("External Host ~ Compute", prompt)
        self.assertIn("Compute -> External Host: result", prompt)
        selected = {index for rel in figure["render_brief"]["visible_content"]["relationships"] for index in rel["source_edge_indices"]}
        self.assertEqual(selected, {3, 4})
        self.assertIn(0, figure["render_brief"]["visible_content"]["deferred_edge_indices"])

    def test_selected_control_feedback_and_clock_keep_directions_without_adding_unsupplied_links(self):
        spec = source()
        for kind in ("control", "feedback", "clock"):
            spec["edges"].append({"source": "host", "target": "mem", "kind": kind, "label": kind, "origin": "given", "evidence": "", "rationale": ""})
        figure, _ = compile_brief(spec, description="整体功能组织及控制路径")
        relations = figure["render_brief"]["visible_content"]["relationships"]
        chosen = {index for rel in relations for index in rel["source_edge_indices"]}
        self.assertEqual(chosen, set(range(len(spec["edges"]))))
        control = next(rel for rel in relations if "control" in rel["kinds"])
        self.assertEqual(control["directionality"], "source-directed")

    def test_hero_and_no_edge_source_remain_quiet(self):
        hero, hero_prompt = compile_brief(mode="hero")
        self.assertEqual(hero["render_brief"]["visible_content"]["relationships"], [])
        self.assertNotIn("Routing instructions", hero_prompt)
        empty = copy.deepcopy(source())
        empty["edges"] = []
        figure, prompt = compile_brief(empty)
        self.assertEqual(figure["render_brief"]["visible_content"]["relationships"], [])
        self.assertNotIn("Routing instructions", prompt)

    def test_review_uses_selected_direction_contract_without_certifying_pixels(self):
        figure, _ = compile_brief()
        report = quality_review.build(source(), figure, figure["render_brief"]["source_hash"])
        self.assertEqual(report["status"], "not_reviewed")
        self.assertIn("opposite flows remain separately traceable", report["prompt"])
        self.assertIn("Only an association/interface relationship may be an unheaded link", report["prompt"])
        self.assertEqual(report["visible_content"], figure["render_brief"]["visible_content"])


if __name__ == "__main__":
    unittest.main()
