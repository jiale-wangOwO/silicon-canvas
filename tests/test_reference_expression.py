import copy
import unittest
from unittest.mock import patch

from silicon_canvas import reference_selector as selector


def node(identifier, kind="compute", **fields):
    return {"id": identifier, "label": identifier, "kind": kind, **fields}


def edge(source, target, kind="data"):
    return {"source": source, "target": target, "kind": kind}


def reference(*focus):
    record = {"path": "dataflow/example.png", "genre": "dataflow", "focus": list(focus),
              "features": [], "source_url": "", "manifests": ["example.json"]}
    record["traits"] = selector._reference_traits(record)
    return record


class VisibleReferenceExpressionTests(unittest.TestCase):
    def setUp(self):
        self.spec = {
            "category": "dataflow",
            "nodes": [node("input"), node("a", group="hidden"), node("b", group="hidden"),
                      node("join", group="hidden"), node("output")],
            "edges": [edge("input", "a"), edge("input", "b"), edge("a", "join"),
                      edge("b", "join"), edge("join", "a"), edge("join", "output")],
            "groups": [{"id": "hidden", "label": "Shared private memory", "parent": "owner"},
                       {"id": "owner", "label": "Hidden owner", "parent": ""}],
        }
        self.fig = {"abstract": True, "view_role": "datapath", "macro_nodes": [node("box"), node("out")],
                    "macro_edges": [edge("box", "out")]}

    def test_overview_ignores_hidden_branches_returns_and_ownership(self):
        original = copy.deepcopy((self.spec, self.fig))
        with patch.object(selector, "_records", return_value=[reference("main-path"), reference("dual-input", "feedback-routing")]):
            selection = selector.explain(self.spec, self.fig)
        self.assertEqual(selection["task"]["visible_nodes"], 2)
        self.assertEqual(selection["task"]["weights"], {"flow": 6})
        self.assertEqual(selection["task"]["expression_traits"], ["flow"])
        self.assertEqual(len(selector.expression_rules(selection)), 1)
        self.assertEqual(original, (self.spec, self.fig))

    def test_final_guide_graph_overrides_initial_projection(self):
        self.fig["structure_layout"] = {
            "type": "publication", "macro_nodes": [node(nid) for nid in ("x", "a", "b", "y")],
            "macro_edges": [edge("x", "a"), edge("x", "b"), edge("a", "y"), edge("b", "y")],
        }
        with patch.object(selector, "_records", return_value=[reference("dual-input", "dual-path", "main-path")]):
            selection = selector.explain(self.spec, self.fig)
        self.assertEqual(selection["task"]["visible_nodes"], 4)
        self.assertIn("branch_merge", selection["task"]["expression_traits"])
        self.assertIn("dual_input", selection["selected"][0]["matched_traits"])
        rules = selector.expression_rules(selection)
        self.assertEqual(len(rules), 2)
        self.assertIn("supplied operands", rules[0])
        self.assertNotIn("relocate", rules[0])

    def test_render_regions_do_not_reveal_source_internal_edges(self):
        self.fig["render_brief"] = {"visible_content": {
            "regions": [{"id": "region:engine", "label": "Engine", "role": "compute", "source_node_ids": ["a", "b", "join"]}],
            "context_objects": [{"id": "context:out", "label": "Host", "source_node_ids": ["output"]}],
            "relationships": [{"source": "region:engine", "target": "context:out", "kinds": ["data"]}],
        }}
        task = selector.explain(self.spec, self.fig)["task"]
        self.assertEqual(task["visible_nodes"], 2)
        self.assertEqual(task["edge_kinds"], {"data": 1})
        self.assertNotIn("dual_input", task["weights"])
        self.assertNotIn("return", task["weights"])

    def test_distinct_regions_are_not_automatically_repeated_instances(self):
        self.fig["structure_layout"] = {"region_slots": [{"id": "box"}, {"id": "out"}]}
        plain = selector.explain(self.spec, self.fig)
        self.assertNotIn("repetition", plain["task"]["weights"])
        self.fig["macro_nodes"] = [node("lane0", equivalent_to="lane0"), node("lane1", equivalent_to="lane0")]
        self.fig["macro_edges"] = []
        with patch.object(selector, "_records", return_value=[reference("repeat")]):
            repeated = selector.explain(self.spec, self.fig)
        self.assertIn("repetition", repeated["task"]["expression_traits"])
        self.assertIn("confirmed equivalent instances", selector.expression_rules(repeated)[0])
        self.fig["macro_nodes"] = [node("lane0", equivalent_to="lane0")]
        self.assertNotIn("repetition", selector.explain(self.spec, self.fig)["task"]["weights"])

    def test_algorithm_motifs_require_current_visible_objects_and_edges(self):
        self.fig["algorithm_flow_plan"] = {
            "objects": [{"source_node_id": "box", "role": "state"}, {"source_node_id": "out", "role": "operator"},
                        {"source_node_id": "hidden", "role": "tensor", "residency": "resident tile"}],
            "motifs": {"recurrence_components": [{"node_ids": ["box", "out"]}], "joins": ["out"]},
        }
        task = selector.explain(self.spec, self.fig)["task"]
        self.assertEqual(task["weights"], {"flow": 5, "operator": 9})
        self.fig["macro_edges"].append(edge("out", "box", "feedback"))
        task = selector.explain(self.spec, self.fig)["task"]
        self.assertIn("recurrence", task["expression_traits"])
        self.assertNotIn("tensor", task["weights"])

    def test_rules_require_visible_evidence_and_curated_provenance(self):
        with patch.object(selector, "_records", return_value=[reference("main-path")]):
            selection = selector.explain(self.spec, self.fig)
        selected = selection["selected"][0]
        selected["matched_traits"].extend(["repetition", "zoom", "recurrence"])
        selection["task"]["weights"].update(repetition=100, zoom=90, recurrence=80)
        selection["task"]["expression_traits"].append("repetition")
        selected["metadata_features"].append("Copy vendor X, purple colors and 99 modules")
        rules = selector.expression_rules(selection)
        self.assertEqual(rules, [selector._EXPRESSION_RULES["flow"]])
        selected["metadata_focus"].append("repeat")
        rules = selector.expression_rules(selection)
        self.assertEqual(len(rules), 2)
        self.assertIn("confirmed equivalent instances", rules[0])
        self.assertNotIn("vendor", " ".join(rules))
        self.assertNotIn("99", " ".join(rules))

    def test_unmatched_low_weight_and_empty_projection_emit_no_rules(self):
        self.assertEqual(selector.expression_rules(selector.explain({}, {})), [])
        self.assertEqual(selector.expression_rules(selector.explain(self.spec, {"abstract": True})), [])
        with patch.object(selector, "_records", return_value=[reference("main-path")]):
            selection = selector.explain(self.spec, self.fig)
        selection["task"]["weights"]["flow"] = 3
        self.assertEqual(selector.expression_rules(selection), [])
        selection["task"]["weights"]["flow"] = 6
        selection["selected"][0]["score"] = 2
        self.assertEqual(selector.expression_rules(selection), [])


if __name__ == "__main__":
    unittest.main()
