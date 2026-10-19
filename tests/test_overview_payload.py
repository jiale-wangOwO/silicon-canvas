"""An organizational overview must still explain supplied payload paths."""
import copy
import unittest

from silicon_canvas import engine, presentation, reading_plan


def source():
    return {"title": "Accelerator organization", "category": "architecture",
            "groups": [{"id": "host", "label": "Host", "parent": ""},
                       {"id": "device", "label": "Processing device", "parent": ""}],
            "nodes": [{"id": "cpu", "label": "Application processor", "kind": "compute", "group": "host"},
                      {"id": "ram", "label": "System memory", "kind": "memory", "group": "host"},
                      {"id": "input", "label": "Host interface", "kind": "io", "group": "device"},
                      {"id": "work", "label": "Dispatch", "kind": "control", "group": "device"},
                      {"id": "execute", "label": "Compute engines", "kind": "compute", "group": "device"},
                      {"id": "cache", "label": "Shared cache", "kind": "memory", "group": "device"},
                      {"id": "controller", "label": "Memory controller", "kind": "control", "group": "device"},
                      {"id": "dram", "label": "External memory", "kind": "memory", "group": ""}],
            "edges": [{"source": a, "target": b, "kind": kind, "label": label} for a, b, kind, label in [
                ("cpu", "ram", "data", "input"), ("ram", "input", "data", "transfer"),
                ("input", "work", "data", "command"), ("work", "execute", "control", "dispatch"),
                ("execute", "cache", "data", "request"), ("cache", "execute", "data", "return"),
                ("cache", "controller", "data", "miss"), ("controller", "dram", "data", "read"),
                ("execute", "work", "feedback", "complete")]]}


class OverviewPayloadTests(unittest.TestCase):
    def plan(self, raw):
        spec = engine.normalize_spec(raw)
        settings = engine.normalize_settings({"scene": "system", "representation": "diagram", "density": "low"})
        return spec, reading_plan.build(spec, settings, presentation.build_plan(spec, "low", "en"),
                                       description="Show the main data path through computation, cache and external memory.")

    def test_source_inventory_alone_does_not_request_all_internal_mechanisms(self):
        spec = engine.normalize_spec(source())
        settings = engine.normalize_settings({"scene": "system", "representation": "diagram"})
        legacy = presentation.build_plan(spec, "medium", "en")
        for description in ("", "Explain subsystem ownership and shared resources.", "Do not show the main data path."):
            with self.subTest(description=description):
                plan = reading_plan.build(spec, settings, legacy, description=description)
                self.assertFalse(plan["figures"][0].get("projection", {}).get("retained_payload_groups"))

    def test_overview_keeps_compute_cache_external_chain_and_defers_secondary_status(self):
        raw = source()
        before = copy.deepcopy(raw)
        spec, plan = self.plan(raw)
        figure = plan["figures"][0]
        self.assertEqual(raw, before)
        self.assertEqual(figure["design_contract"]["grammar"], "exact-flow")
        visible = {node["id"]: node for node in figure["macro_nodes"]}
        self.assertTrue({"execute", "cache", "controller", "dram"} <= visible.keys())
        self.assertEqual(visible["cache"]["original_group"], "device")
        self.assertEqual(visible["dram"]["original_group"], "")
        rendered = {i for edge in figure["macro_edges"] for i in edge["members"]}
        self.assertTrue({4, 5, 6, 7} <= rendered)
        self.assertIn(3, rendered, "A real dispatch into the payload consumer remains visible")
        self.assertNotIn(8, rendered, "Status is retained in the source/annex rather than cluttering the main path")
        self.assertEqual({item["index"] for item in figure["projection"]["deferred_edges"]}, {8})
        exact = {i for other in plan["figures"] if not other["abstract"] for i in other["edge_indices"]}
        self.assertEqual(exact, set(range(len(spec["edges"]))))
        for edge in figure["macro_edges"]:
            for index in edge["members"]:
                original = spec["edges"][index]
                self.assertEqual({edge["source"], edge["target"]}, {original["source"], original["target"]})
        self.assertFalse(any(node["label"] == "Common bus" for node in figure["macro_nodes"]))

    def test_decision_is_not_bound_to_gpu_names_ids_or_source_order(self):
        raw = source()
        raw["title"] = "Unbranded system"
        aliases = {node["id"]: "r" + str(index) for index, node in enumerate(raw["nodes"])}
        for index, node in enumerate(raw["nodes"]):
            node["id"], node["label"] = aliases[node["id"]], "Resource " + str(index)
        for edge in raw["edges"]:
            edge["source"], edge["target"] = aliases[edge["source"]], aliases[edge["target"]]
        raw["nodes"].reverse()
        _, plan = self.plan(raw)
        figure = plan["figures"][0]
        self.assertTrue({aliases[key] for key in ("execute", "cache", "controller", "dram")} <= {node["id"] for node in figure["macro_nodes"]})
        self.assertTrue({4, 5, 6, 7} <= {i for edge in figure["macro_edges"] for i in edge["members"]})

    def test_memory_only_hierarchy_is_not_replaced_by_an_unordered_list(self):
        raw = source()
        raw["nodes"] = [node for node in raw["nodes"] if node["id"] in {"cache", "controller", "dram"}]
        raw["nodes"][1]["kind"] = "memory"
        raw["edges"] = [raw["edges"][6], raw["edges"][7]]
        _, plan = self.plan(raw)
        figure = plan["figures"][0]
        self.assertEqual({node["id"] for node in figure["macro_nodes"]}, {"cache", "controller", "dram"})
        self.assertEqual({i for edge in figure["macro_edges"] for i in edge["members"]}, {0, 1})


if __name__ == "__main__":
    unittest.main()
