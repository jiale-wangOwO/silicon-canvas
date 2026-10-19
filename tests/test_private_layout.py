"""Ownership detail regressions using an independently designed synthetic engine."""
import copy
import json
from pathlib import Path
import unittest

from silicon_canvas import private_layout, structure_scene

FIXTURE = Path(__file__).resolve().parent / "fixtures/strategy_benchmark/containment_core_fixture.json"


def contains(outer, inner):
    return (outer["x"] - 1e-5 <= inner["x"] and outer["y"] - 1e-5 <= inner["y"]
            and inner["x"] + inner["width"] <= outer["x"] + outer["width"] + 1e-5
            and inner["y"] + inner["height"] <= outer["y"] + outer["height"] + 1e-5)


class PrivateLayoutTests(unittest.TestCase):
    def fixture(self):
        spec = json.loads(FIXTURE.read_text(encoding="utf-8"))
        owned = {node["id"] for node in spec["nodes"] if node["group"] == "worker0"}
        indices = [i for i, edge in enumerate(spec["edges"]) if owned & {edge["source"], edge["target"]}]
        endpoints = {nid for i in indices for nid in (spec["edges"][i]["source"], spec["edges"][i]["target"])}
        figure = {"title": "Worker0 local resources", "main_group": "worker0", "abstract": False,
                  "node_ids": [node["id"] for node in spec["nodes"] if node["id"] in endpoints], "edge_indices": indices}
        return spec, figure

    def phase(self, control):
        spec, figure = self.fixture()
        selected = [i for i in figure["edge_indices"]
                    if (spec["edges"][i]["kind"] in {"control", "feedback", "clock"}) == control]
        endpoints = {nid for i in selected for nid in (spec["edges"][i]["source"], spec["edges"][i]["target"])}
        figure.update(edge_indices=selected, node_ids=[node["id"] for node in spec["nodes"] if node["id"] in endpoints])
        return spec, figure

    def test_exact_objects_and_directed_relations_survive_without_mutation(self):
        spec, figure = self.fixture()
        original = copy.deepcopy((spec, figure))
        plan = private_layout.build_detail(spec, figure)
        self.assertEqual((spec, figure), original)
        self.assertEqual(plan["type"], "ownership_detail")
        self.assertFalse(plan["abstract"])
        self.assertEqual(plan["node_ids"], figure["node_ids"])
        for node in plan["macro_nodes"]:
            source = next(n for n in spec["nodes"] if n["id"] == node["id"])
            self.assertEqual(node["members"], [source["id"]])
            self.assertEqual((node["label"], node["detail"]), (source["label"], source["detail"]))
        for link, index in zip(plan["macro_edges"], figure["edge_indices"]):
            self.assertEqual(link["members"], [index])
            for key in ("source", "target", "kind", "label"):
                self.assertEqual(link[key], spec["edges"][index][key])
        self.assertEqual(plan["deferred_links"], [])
        self.assertEqual(plan["node_to_macro"], {nid: nid for nid in figure["node_ids"]})

    def test_local_storage_and_transfer_queue_stay_inside_actual_owner(self):
        spec, figure = self.fixture()
        plan = private_layout.build_detail(spec, figure)
        owner = plan["system_frame"]["box"]
        for nid in ("scratch", "linebuf", "inbox"):
            self.assertTrue(contains(owner, plan["boxes"][nid]))
            self.assertEqual(plan["source_ownership"][nid], "worker0")
            self.assertNotIn(nid, plan["context_nodes"])
        self.assertEqual(plan["local_storage_backbone"], "scratch")
        execution = next(lane for lane in plan["role_lanes"] if lane["role"] == "execution")
        self.assertGreater(plan["boxes"]["scratch"]["y"], execution["box"]["y"] + execution["box"]["height"])
        self.assertNotIn("focal_hub", plan)

    def test_context_placement_comes_from_source_ancestry_and_edge_roles(self):
        spec, figure = self.fixture()
        figure["context_nodes"] = []
        plan = private_layout.build_detail(spec, figure)
        owner = plan["system_frame"]["box"]
        for nid in ("command", "coordinator", "assist", "staging", "bridge", "sharedram"):
            self.assertIn(nid, plan["context_nodes"])
            self.assertFalse(contains(owner, plan["boxes"][nid]))
            self.assertEqual(plan["source_ownership"][nid], next(n["group"] for n in spec["nodes"] if n["id"] == nid))
        self.assertLess(plan["boxes"]["command"]["y"] + plan["boxes"]["command"]["height"], owner["y"])
        self.assertGreater(plan["boxes"]["assist"]["x"], owner["x"] + owner["width"])
        self.assertGreater(plan["boxes"]["sharedram"]["y"], owner["y"] + owner["height"])

    def test_nested_storage_retains_exact_source_owner(self):
        spec, figure = self.fixture()
        spec["groups"].append({"id": "local_memory", "label": "Private local storage", "parent": "worker0"})
        for node in spec["nodes"]:
            if node["id"] in {"scratch", "linebuf", "inbox"}:
                node["group"] = "local_memory"
        plan = private_layout.build_detail(spec, figure)
        for nid in ("scratch", "linebuf", "inbox"):
            self.assertEqual(plan["source_ownership"][nid], "local_memory")
            self.assertNotIn(nid, plan["context_nodes"])
            self.assertTrue(contains(plan["system_frame"]["box"], plan["boxes"][nid]))
        self.assertIn("local_memory", plan["source_nested_groups"])

    def test_reading_order_follows_dependencies_instead_of_alphabetical_names(self):
        spec, figure = self.fixture()
        figure["node_ids"] = sorted(figure["node_ids"])
        next(n for n in spec["nodes"] if n["id"] == "entry")["label"] = "Z task entry"
        next(n for n in spec["nodes"] if n["id"] == "schedule")["label"] = "A scheduler"
        plan = private_layout.build_detail(spec, figure)
        self.assertEqual(next(lane for lane in plan["role_lanes"] if lane["role"] == "control-entry")["members"], ["entry"])
        self.assertEqual(next(lane for lane in plan["role_lanes"] if lane["role"] == "execution")["members"], ["dot", "reshape", "inbox"])

    def test_symbols_fit_separate_routing_slots_and_backbone_remains_readable(self):
        spec, figure = self.fixture()
        plan = private_layout.build_detail(spec, figure)
        entry, slot = plan["boxes"]["entry"], plan["slot_boxes"]["entry"]
        self.assertLess(entry["width"], slot["width"] / 2)
        self.assertAlmostEqual(entry["x"] + entry["width"] / 2, slot["x"] + slot["width"] / 2, places=5)
        for nid in figure["node_ids"]:
            self.assertTrue(contains(plan["slot_boxes"][nid], plan["boxes"][nid]))
        self.assertLess(plan["boxes"]["assist"]["width"], plan["system_frame"]["box"]["width"] / 3)
        scratch = next(node for node in plan["macro_nodes"] if node["id"] == "scratch")
        self.assertEqual(scratch["box"]["width"], scratch["slot_box"]["width"])
        self.assertEqual(scratch["visual_caption_policy"]["max_lines"], 2)

    def test_transfer_queue_and_consumer_buffer_are_graph_derived(self):
        spec, figure = self.phase(control=False)
        plan = private_layout.build_detail(spec, figure)
        self.assertEqual(plan["transfer_nodes"], ["inbox"])
        queue = next(node for node in plan["macro_nodes"] if node["id"] == "inbox")
        self.assertEqual((queue["kind"], queue["source_owner"], queue["visual_lane"]), ("memory", "worker0", "execution-transfer"))
        self.assertEqual(plan["boxes"]["inbox"]["y"], plan["boxes"]["dot"]["y"])
        buffer, consumer = plan["boxes"]["linebuf"], plan["boxes"]["reshape"]
        self.assertAlmostEqual(buffer["x"] + buffer["width"] / 2, consumer["x"] + consumer["width"] / 2, places=5)
        self.assertGreater(buffer["y"], consumer["y"] + consumer["height"])
        for node in spec["nodes"]:
            if node["id"] in {"inbox", "bridge", "linebuf", "reshape"}:
                node["label"] = "Renamed " + node["id"]
        renamed = private_layout.build_detail(spec, figure)
        self.assertEqual(renamed["transfer_nodes"], ["inbox"])
        self.assertEqual(renamed["source_ownership"], plan["source_ownership"])

    def test_parallel_control_and_returning_payloads_remain_distinct(self):
        spec, figure = self.fixture()
        spec["edges"].append({"source": "entry", "target": "schedule", "kind": "control", "label": "cancel task"})
        figure["edge_indices"].append(len(spec["edges"]) - 1)
        plan = private_layout.build_detail(spec, figure)
        self.assertEqual(len([e for e in plan["macro_edges"] if e["source"] == "entry" and e["target"] == "schedule"]), 2)
        returns = [e for e in plan["macro_edges"] if e["source"] == "dot" and e["target"] == "scratch"]
        self.assertEqual([edge["label"] for edge in returns], ["partials"])
        self.assertFalse(any(e.get("bidirectional") for e in plan["macro_edges"]))

    def test_control_only_projection_keeps_invisible_storage_in_owner_inventory(self):
        spec, figure = self.phase(control=True)
        original = copy.deepcopy((spec, figure))
        self.assertEqual(len(figure["edge_indices"]), 7)
        plan = private_layout.build_detail(spec, figure)
        self.assertEqual((spec, figure), original)
        self.assertEqual(plan["system_frame"]["source_group"], "worker0")
        self.assertIn("scratch", plan["scope_owner_nodes"])
        self.assertNotIn("scratch", plan["node_ids"])
        self.assertIsNone(plan["local_storage_backbone"])
        self.assertFalse(any(lane["role"].startswith("local-storage") for lane in plan["role_lanes"]))
        self.assertEqual(plan["edge_indices"], figure["edge_indices"])
        for nid in ("command", "coordinator", "sharedram"):
            self.assertIn(nid, plan["context_nodes"])
            self.assertFalse(contains(plan["system_frame"]["box"], plan["boxes"][nid]))

    def test_data_only_projection_covers_every_payload_without_reassigning_control(self):
        spec, figure = self.phase(control=False)
        _, control = self.phase(control=True)
        _, full = self.fixture()
        self.assertEqual(len(figure["edge_indices"]), 13)
        self.assertFalse(set(figure["edge_indices"]) & set(control["edge_indices"]))
        self.assertCountEqual(figure["edge_indices"] + control["edge_indices"], full["edge_indices"])
        plan = private_layout.build_detail(spec, figure)
        self.assertEqual(plan["system_frame"]["source_group"], "worker0")
        self.assertIn("entry", plan["scope_owner_nodes"])
        self.assertFalse({"entry", "schedule"} & set(plan["node_ids"]))
        self.assertFalse(any(lane["role"].startswith("control") for lane in plan["role_lanes"]))
        self.assertEqual(plan["edge_indices"], figure["edge_indices"])
        for nid in ("scratch", "linebuf", "inbox"):
            self.assertTrue(contains(plan["system_frame"]["box"], plan["boxes"][nid]))
        for nid in ("assist", "bridge", "sharedram", "staging"):
            self.assertIn(nid, plan["context_nodes"])
            self.assertFalse(contains(plan["system_frame"]["box"], plan["boxes"][nid]))

    def test_normalized_boxes_and_one_owner_boundary_do_not_invent_a_bus(self):
        spec, figure = self.fixture()
        plan = private_layout.build_detail(spec, figure)
        self.assertEqual(len(plan["containers"]), 1)
        self.assertEqual(plan["containers"][0]["source_group"], "worker0")
        self.assertEqual(plan["system_frame"]["replaces_container"], "worker0")
        for box in list(plan["boxes"].values()) + [c["box"] for c in plan["routing_corridors"]]:
            self.assertGreaterEqual(box["x"], 0)
            self.assertGreaterEqual(box["y"], 0)
            self.assertLessEqual(box["x"] + box["width"], 1.000001)
            self.assertLessEqual(box["y"] + box["height"], 1.000001)
        self.assertTrue(all(c["routing_is_not_a_hardware_bus"] for c in plan["routing_corridors"]))

    def test_other_grammars_repeated_parent_and_shared_scope_are_declined(self):
        spec, figure = self.fixture()
        for category in ("dataflow", "fsm", "algorithm"):
            spec["category"] = category
            self.assertIsNone(private_layout.build_detail(spec, figure))
        spec["category"] = "architecture"
        for owner in ("missing", "engine", "services"):
            figure.update(main_group=owner, node_ids=[n["id"] for n in spec["nodes"]], edge_indices=list(range(len(spec["edges"]))))
            self.assertIsNone(private_layout.build_detail(spec, figure))

    def test_invalid_visible_endpoint_and_duplicate_relation_are_rejected(self):
        spec, figure = self.fixture()
        broken = copy.deepcopy(figure)
        broken["node_ids"].remove("scratch")
        with self.assertRaisesRegex(ValueError, "endpoints"):
            private_layout.build_detail(spec, broken)
        broken = copy.deepcopy(figure)
        broken["edge_indices"].append(broken["edge_indices"][0])
        with self.assertRaisesRegex(ValueError, "indices"):
            private_layout.build_detail(spec, broken)

    def test_planning_is_deterministic(self):
        spec, figure = self.fixture()
        self.assertEqual(private_layout.build_detail(spec, figure), private_layout.build_detail(spec, figure))

    def gpu_fixture(self):
        path = FIXTURE.parents[1] / "publication_benchmark" / "gpu-baseline-result.json"
        spec = json.loads(path.read_text(encoding="utf-8"))["spec"]
        owned = {node["id"] for node in spec["nodes"] if node["group"] == "g_cluster0"}
        indices = [index for index, edge in enumerate(spec["edges"]) if owned & {edge["source"], edge["target"]}]
        endpoints = {nid for index in indices for nid in (spec["edges"][index]["source"], spec["edges"][index]["target"])}
        figure = {"title": "Representative private resources", "main_group": "g_cluster0", "abstract": False,
                  "node_ids": [node["id"] for node in spec["nodes"] if node["id"] in endpoints], "edge_indices": indices}
        return spec, figure

    def test_root_representative_cluster_with_direct_private_storage_routes_all_phases(self):
        spec, figure = self.gpu_fixture()
        original = copy.deepcopy(spec)
        self.assertEqual(figure["edge_indices"], [3, 7, 8, 9, 10, 11, 12])
        for phase in (None, "control", "datapath"):
            with self.subTest(phase=phase):
                selected = [index for index in figure["edge_indices"] if phase is None or
                            ((spec["edges"][index]["kind"] in {"control", "feedback", "clock"}) == (phase == "control"))]
                endpoints = {nid for index in selected for nid in (spec["edges"][index]["source"], spec["edges"][index]["target"])}
                projected = {**figure, "view_role": phase, "edge_indices": selected,
                             "node_ids": [nid for nid in figure["node_ids"] if nid in endpoints]}
                plan = private_layout.build_detail(spec, projected)
                self.assertIsNotNone(plan)
                self.assertEqual(plan["system_frame"]["source_group"], "g_cluster0")
                self.assertEqual(plan["edge_indices"], selected)
                scene = structure_scene.prepare(plan)
                self.assertTrue(scene["quality"]["routes_complete"], scene["quality"])
                self.assertCountEqual([index for route in scene["routes"] for index in route["members"]], selected)
                for nid in ("n_rf0", "n_l10"):
                    if nid in endpoints:
                        self.assertEqual(plan["source_ownership"][nid], "g_cluster0")
                        self.assertTrue(contains(plan["system_frame"]["box"], plan["boxes"][nid]))
                if "n_l2" in endpoints:
                    self.assertIn("n_l2", plan["context_nodes"])
                    self.assertFalse(contains(plan["system_frame"]["box"], plan["boxes"]["n_l2"]))
        self.assertEqual(spec, original)

    def test_root_parent_cannot_borrow_private_qualification_from_descendants(self):
        spec, figure = self.gpu_fixture()
        for group in spec["groups"]:
            group["parent"] = "core"
        spec["groups"].append({"id": "core", "label": "Core", "parent": "", "evidence": "Core contains private resources inside its child clusters."})
        for node in spec["nodes"]:
            if node["id"] in {"n_cmd", "n_exec0"}:
                node["group"] = "core"
        figure.update(main_group="core", node_ids=[node["id"] for node in spec["nodes"]], edge_indices=list(range(len(spec["edges"]))))
        self.assertIsNone(private_layout.build_detail(spec, figure))
        # Even a directly owned private resource does not reclassify an
        # explicitly shared scope as a closed private cluster.
        spec, figure = self.gpu_fixture()
        next(group for group in spec["groups"] if group["id"] == "g_cluster0")["label"] = "Shared Services"
        self.assertIsNone(private_layout.build_detail(spec, figure))

    def test_root_private_storage_requires_an_explicit_direct_claim(self):
        spec, figure = self.gpu_fixture()
        for node in spec["nodes"]:
            if node["id"] in {"n_rf0", "n_l10"}:
                node["label"] = "Operand Storage" if node["id"] == "n_rf0" else "Data Storage"
                node["detail"] = "Storage connected to the execution resources"
        self.assertIsNone(private_layout.build_detail(spec, figure))
        next(node for node in spec["nodes"] if node["id"] == "n_rf0")["detail"] = "Private to this compute cluster"
        self.assertIsNotNone(private_layout.build_detail(spec, figure))


if __name__ == "__main__":
    unittest.main()
