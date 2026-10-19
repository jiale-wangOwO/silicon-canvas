"""Synthetic hardware mechanism regressions; no private design fixture."""
import copy
import json
from pathlib import Path
import unittest

from silicon_canvas import engine, layout_guide, reading_plan


def source():
    return {"title": "Buffered Local and Shared Compute", "category": "dataflow",
            "groups": [{"id": "private", "label": "Private channel", "parent": ""},
                       {"id": "shared", "label": "Shared service", "parent": ""}],
            "nodes": [{"id": "bank", "label": "Register Bank", "kind": "memory", "group": "private", "detail": "4 banks; 32-B entry"},
                      {"id": "input", "label": "Operand Buffer", "kind": "memory", "group": "private", "detail": "Operand collection"},
                      {"id": "local", "label": "Local Unit", "kind": "compute", "group": "private", "detail": "Local execution"},
                      {"id": "helper", "label": "Helper Unit", "kind": "compute", "group": "shared", "detail": "Shared execution"},
                      {"id": "output", "label": "Result Buffer", "kind": "memory", "group": "private", "detail": "Result collection"}],
            "edges": [{"source": "bank", "target": "input", "kind": "data", "label": "read selection"},
                      {"source": "input", "target": "local", "kind": "data", "label": "operands"},
                      {"source": "input", "target": "helper", "kind": "data", "label": "operands"},
                      {"source": "local", "target": "output", "kind": "data", "label": "results"},
                      {"source": "helper", "target": "output", "kind": "data", "label": "results"},
                      {"source": "output", "target": "bank", "kind": "data", "label": "writeback"}],
            "layout": "Register bank to operand collection; local and shared units are parallel; both feed result collection. The result returns through an outer corridor to the same bank. The private boundary must not enclose the shared helper. No serial local-to-helper path or second bank.",
            "annotations": ["Same register bank for read and writeback", "Helper is shared; buffers and local unit are private"]}


def compile_source(spec=None):
    return engine.compile_manual({"spec": source() if spec is None else spec,
                                  "settings": {"scene": "flow", "representation": "diagram", "style": "paper", "aspect": "16:9"}})


class BoundedHardwareFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = compile_source()

    def test_primary_retains_five_actual_resources_and_six_directed_mechanism_edges(self):
        result = self.result
        primary = result["figures"][0]
        self.assertEqual(primary["projection"]["abstraction_policy"], "bounded-leaf-flow")
        self.assertEqual(primary["projection"]["folded_groups"], [])
        self.assertEqual(primary["projection"]["internal_edges"], [])
        self.assertEqual(primary["projection"]["deferred_edges"], [])
        self.assertEqual({n["id"] for n in primary["macro_nodes"]}, {n["id"] for n in source()["nodes"]})
        self.assertEqual(len(primary["macro_nodes"]), 5)
        self.assertEqual(len(primary["macro_edges"]), 6)
        self.assertEqual([edge["members"] for edge in primary["macro_edges"]], [[i] for i in range(6)])
        self.assertFalse(any(edge.get("bidirectional") for edge in primary["macro_edges"]))
        self.assertNotIn("algorithm_flow_plan", primary)
        self.assertEqual(primary["design_contract"]["grammar"], "exact-flow")

    def test_source_ledger_hash_and_ownership_are_unchanged(self):
        raw = source()
        before = copy.deepcopy(raw)
        result = compile_source(raw)
        self.assertEqual(raw, before)
        self.assertEqual(result["spec"], engine.normalize_spec(before))
        self.assertEqual(result["source_hash"], reading_plan.source_hash(result["spec"]))
        primary = result["figures"][0]
        owners = {node["id"]: node["original_group"] for node in primary["macro_nodes"]}
        self.assertEqual(owners["helper"], "shared")
        self.assertEqual({owners[n] for n in ("bank", "input", "local", "output")}, {"private"})
        self.assertEqual(primary["projection"]["source_node_to_macro"], {node["id"]: node["id"] for node in result["spec"]["nodes"]})

    def test_parallel_execution_and_same_bank_return_remain_distinct_endpoints(self):
        edges = self.result["figures"][0]["macro_edges"]
        pairs = [(edge["source"], edge["target"]) for edge in edges]
        self.assertEqual([target for start, target in pairs if start == "input"], ["local", "helper"])
        self.assertEqual([start for start, target in pairs if target == "output"], ["local", "helper"])
        self.assertIn(("output", "bank"), pairs)
        self.assertNotIn(("local", "helper"), pairs)
        self.assertNotIn(("helper", "local"), pairs)
        self.assertEqual(sum(node["label"] == "Register Bank" for node in self.result["figures"][0]["macro_nodes"]), 1)

    def test_real_layout_routes_preserve_all_six_directions_without_duplex_summary(self):
        primary = self.result["figures"][0]
        self.assertEqual(primary["layout_strategy"], "publication-candidates")
        self.assertTrue(primary["requires_layout_guide"])
        scene = primary["layout_scene"]
        self.assertTrue(scene["quality"]["routes_complete"])
        self.assertEqual(len(scene["routes"]), 6)
        self.assertEqual(sorted(i for route in scene["routes"] for i in route["members"]), list(range(6)))
        for route in scene["routes"]:
            self.assertFalse(route.get("bidirectional"))
            original = self.result["spec"]["edges"][route["members"][0]]
            self.assertEqual((route["source"], route["target"]), (original["source"], original["target"]))
        self.assertTrue(layout_guide.render(self.result, primary).startswith(b"\x89PNG\r\n\x1a\n"))

    def test_document_type_scale_keeps_numeric_bank_parameter_in_actual_label_plan(self):
        primary = self.result["figures"][0]
        self.assertGreaterEqual(primary["design_contract"]["body_pt"], 9)
        self.assertGreaterEqual(primary["design_contract"]["signal_pt"], 8.5)
        self.assertTrue(primary["layout_scene"]["quality"]["typography_measured"])
        metrics = primary["structure_layout"]["symbol_metrics"]
        for node in self.result["spec"]["nodes"]:
            self.assertEqual(" ".join(metrics[node["id"]]["lines"]), node["label"])
            self.assertGreaterEqual(metrics[node["id"]]["font_px"], primary["structure_layout"]["typography"]["body_px"])
        self.assertEqual(metrics["bank"]["detail_lines"], ["4 banks; 32-B entry"])
        labels = [label["text"] for label in primary["label_layout"]["labels"]]
        self.assertIn("read selection", labels)
        self.assertIn("writeback", labels)

    def test_true_opposite_leaf_relations_keep_separate_meanings_and_arrows(self):
        spec = source()
        spec["edges"].append({"source": "input", "target": "bank", "kind": "data", "label": "read response"})
        primary = compile_source(spec)["figures"][0]
        forward = [e for e in primary["macro_edges"] if (e["source"], e["target"]) == ("bank", "input")]
        reverse = [e for e in primary["macro_edges"] if (e["source"], e["target"]) == ("input", "bank")]
        self.assertEqual(len(forward), 1)
        self.assertEqual(len(reverse), 1)
        self.assertEqual(forward[0]["label"], "read selection")
        self.assertEqual(reverse[0]["label"], "read response")
        self.assertFalse(any(e.get("bidirectional") for e in forward + reverse))

    def test_long_numeric_resource_description_widens_symbol_without_shrinking_or_omission(self):
        spec = source()
        spec["nodes"][0]["label"] = "Operand Register Bank / Physical Entries"
        spec["nodes"][0]["detail"] = "4 banks; 32-B entry; per-bank request queues and arbitration"
        result = compile_source(spec)
        primary = result["figures"][0]
        self.assertEqual(primary["layout_strategy"], "publication-candidates")
        self.assertEqual(len(primary["layout_scene"]["routes"]), 6)
        metrics = primary["structure_layout"]["symbol_metrics"]["bank"]
        self.assertEqual(" ".join(metrics["lines"]), spec["nodes"][0]["label"])
        self.assertEqual(" ".join(metrics["detail_lines"]), spec["nodes"][0]["detail"])
        self.assertGreater(metrics["width"], 400)
        self.assertGreaterEqual(metrics["font_px"], primary["structure_layout"]["typography"]["body_px"])
        self.assertTrue(primary["structure_layout"]["typography"]["no_font_shrink"])
        self.assertTrue(layout_guide.render(result, primary))

    def test_leaf_policy_does_not_depend_on_names_or_algorithm_brand(self):
        spec = source()
        rename = {node["id"]: "resource" + str(i) for i, node in enumerate(spec["nodes"])}
        for i, node in enumerate(spec["nodes"]):
            node["id"] = rename[node["id"]]
            node["label"] = "Hardware resource " + str(i)
        for edge in spec["edges"]:
            edge["source"], edge["target"] = rename[edge["source"]], rename[edge["target"]]
        primary = compile_source(spec)["figures"][0]
        self.assertEqual(primary["projection"]["abstraction_policy"], "bounded-leaf-flow")
        self.assertEqual(len(primary["macro_nodes"]), 5)
        self.assertEqual(len(primary["macro_edges"]), 6)
        self.assertNotIn("algorithm_flow_plan", primary)

    def test_larger_source_can_keep_exact_flow_when_measured_layout_fits(self):
        root = Path(__file__).resolve().parents[1]
        data = json.loads((root / "examples" / "gpu.json").read_text(encoding="utf-8"))
        data["settings"].update(scene="flow", representation="diagram")
        primary = engine.compile_manual(data)["figures"][0]
        self.assertEqual(primary["projection"]["abstraction_policy"], "bounded-leaf-flow")
        self.assertFalse(primary["projection"]["folded_groups"])
        self.assertTrue(primary["layout_scene"]["quality"]["routes_complete"])
        self.assertTrue(primary["projection_diagnostics"]["candidates"][0]["selected"])


if __name__ == "__main__":
    unittest.main()
