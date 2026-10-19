import copy
import json
from pathlib import Path
import unittest

from silicon_canvas import structure_layout


FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "strategy_benchmark" / "containment_core_fixture.json"


class StructureLayoutTests(unittest.TestCase):
    def fixture(self):
        return json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_source_hierarchy_and_local_storage_ownership_survive_overview(self):
        spec = self.fixture()
        original = copy.deepcopy(spec)
        plan = structure_layout.build_overview(spec)
        self.assertEqual(spec, original)
        self.assertEqual(plan["type"], "hierarchy_overview")
        self.assertEqual(plan["system_frame"]["source_group"], "engine")
        self.assertFalse(plan["system_frame"]["display_only"])
        self.assertEqual(plan["source_ownership"]["scratch"], "worker0")
        self.assertEqual(plan["node_to_macro"]["scratch"], "worker0")
        self.assertNotIn("scratch", {n["id"] for n in plan["macro_nodes"]})
        self.assertNotIn("focal_hub", plan)
        containers = {c["id"]: c for c in plan["containers"]}
        self.assertEqual(containers["worker0"]["parent"], "engine")
        self.assertEqual(containers["services"]["parent"], "engine")
        self.assertEqual(containers["worker0"]["replaces_region"], "worker0")

    def test_three_declared_workers_have_equal_geometry_and_full_template_skeleton(self):
        plan = structure_layout.build_overview(self.fixture())
        units = plan["region_slots"]
        self.assertEqual([u["id"] for u in units], ["worker0", "worker1", "worker2"])
        self.assertEqual(len({(u["box"]["width"], u["box"]["height"], u["box"]["y"]) for u in units}), 1)
        self.assertEqual(len(units[0]["template_slots"]), 7)
        self.assertEqual({s["source_node_id"] for s in units[0]["template_slots"]}, {"entry", "schedule", "dot", "reshape", "scratch", "inbox", "linebuf"})
        for unit in units[1:]:
            self.assertEqual([s["box"] for s in unit["template_slots"]], [s["box"] for s in units[0]["template_slots"]])
            self.assertTrue(all(s["visual_reference_only"] for s in unit["template_slots"]))
        slots = {s["source_node_id"]: s for s in units[0]["template_slots"]}
        self.assertLess(slots["entry"]["box"]["y"], slots["schedule"]["box"]["y"])
        self.assertEqual(slots["entry"]["role_lane"], "control")
        self.assertGreater(slots["scratch"]["box"]["width"], slots["inbox"]["box"]["width"])
        self.assertGreater(slots["scratch"]["box"]["y"], slots["inbox"]["box"]["y"])

    def test_command_fanout_keeps_every_worker_not_only_the_expanded_one(self):
        plan = structure_layout.build_overview(self.fixture())
        links = [link for link in plan["projected_links"] if link["source"] == "command"]
        self.assertEqual({link["target"] for link in links}, {"worker0", "worker1", "worker2"})
        self.assertEqual({i for link in links for i in link["members"]}, {0, 1, 2})
        self.assertTrue(all(link["family"] == "instruction" for link in links))
        self.assertTrue(all(link in plan["macro_edges"] for link in links))

    def test_projection_plus_deferred_and_internal_edges_preserves_every_fact(self):
        spec = self.fixture()
        plan = structure_layout.build_overview(spec, hints={"main_family_limit": 2})
        self.assertTrue(plan["deferred_links"])
        seen = [i for link in plan["projected_links"] for i in link["members"]]
        seen += [i for item in plan["internal_edges"] for i in item["members"]]
        self.assertCountEqual(seen, range(len(spec["edges"])))
        self.assertEqual(len(seen), len(set(seen)))
        self.assertEqual(plan["coverage"]["missing_edges"], [])
        self.assertEqual(plan["coverage"]["missing_nodes"], [])
        self.assertEqual({link["id"] for link in plan["macro_edges"]} | {link["id"] for link in plan["deferred_links"]}, {link["id"] for link in plan["projected_links"]})
        for link in plan["projected_links"]:
            for index in link["members"]:
                edge = spec["edges"][index]
                self.assertEqual(plan["node_to_macro"][edge["source"]], link["source"])
                self.assertEqual(plan["node_to_macro"][edge["target"]], link["target"])
                self.assertEqual(edge["kind"], link["kind"])
                if edge["label"]:
                    self.assertIn(edge["label"], link["labels"])

    def test_external_memory_is_outside_system_and_shared_transfer_chain_adjacent(self):
        plan = structure_layout.build_overview(self.fixture())
        frame = plan["system_frame"]["box"]
        mem = plan["boxes"]["external"]
        self.assertGreaterEqual(mem["x"], frame["x"] + frame["width"])
        chain = next(c for c in plan["component_lanes"] if set(c["members"]) == {"loader", "staging"})
        self.assertEqual(chain["members"], ["loader", "staging"])
        a, b = plan["boxes"]["loader"], plan["boxes"]["staging"]
        self.assertEqual(a["x"], b["x"])
        self.assertLess(a["y"], b["y"])
        self.assertTrue(chain["display_only"])

    def test_boxes_and_corridors_are_normalized_and_no_bus_is_invented(self):
        plan = structure_layout.build_overview(self.fixture())
        geometries = list(plan["boxes"].values()) + [c["box"] for c in plan["routing_corridors"]]
        for box in geometries:
            self.assertGreaterEqual(box["x"], 0)
            self.assertGreaterEqual(box["y"], 0)
            self.assertGreater(box["width"], 0)
            self.assertGreater(box["height"], 0)
            self.assertLessEqual(box["x"] + box["width"], 1.000001)
            self.assertLessEqual(box["y"] + box["height"], 1.000001)
        corridor_ids = {c["id"] for c in plan["routing_corridors"]}
        for link in plan["projected_links"]:
            self.assertIn(link["routing"]["corridor"], corridor_ids)
            self.assertTrue(link["routing"]["no_broadcast_bus_is_inferred"])
        self.assertFalse(any(n["label"] in {"Interconnect", "Common Bus"} for n in plan["macro_nodes"]))

    def test_flat_groups_get_visual_shell_without_claiming_a_new_owner(self):
        spec = self.fixture()
        spec["groups"] = [{"id": "worker0", "label": "Worker0 private resources", "parent": ""}, {"id": "services", "label": "Shared services", "parent": ""}]
        for node in spec["nodes"]:
            if node["group"] != "worker0":
                node["group"] = "" if node["id"] == "external" else "services"
        next(n for n in spec["nodes"] if n["id"] == "scratch")["label"] = "Worker0 Local scratchpad"
        original = copy.deepcopy(spec)
        plan = structure_layout.build_overview(spec)
        self.assertEqual(spec, original)
        self.assertTrue(plan["system_frame"]["display_only"])
        self.assertIsNone(plan["system_frame"]["source_group"])
        peer = next(n for n in plan["macro_nodes"] if n["id"] == "worker1")
        storage_slot = next(s for s in peer["template_slots"] if s["source_node_id"] == "scratch")
        self.assertEqual(storage_slot["source_label"], "Worker0 Local scratchpad")
        self.assertEqual(storage_slot["display_label"], "Local scratchpad")

    def test_pure_dataflow_does_not_receive_inferred_system_containment(self):
        spec = self.fixture()
        spec["category"] = "dataflow"
        self.assertIsNone(structure_layout.build_overview(spec))

    def test_larger_actual_peer_inventory_forms_a_balanced_array_without_added_instances(self):
        for count in (6, 9):
            with self.subTest(count=count):
                spec = self.fixture()
                peer = next(node for node in spec["nodes"] if node["id"] == "worker2")
                for ordinal in range(3, count):
                    node = copy.deepcopy(peer)
                    node["id"], node["label"] = "worker" + str(ordinal), "Worker" + str(ordinal)
                    spec["nodes"].append(node)
                original = copy.deepcopy(spec)
                plan = structure_layout.build_overview(spec)
                self.assertEqual(spec, original)
                units = plan["region_slots"]
                self.assertEqual(len(units), count)
                rows = {}
                for unit in units:
                    rows.setdefault(round(unit["box"]["y"], 6), []).append(unit)
                self.assertEqual(sorted(len(row) for row in rows.values()), [3] * (count // 3))
                self.assertEqual({unit["id"] for unit in units}, {"worker" + str(i) for i in range(count)})
                self.assertEqual(plan["coverage"]["missing_edges"], [])

    def test_determinism_and_invalid_containment_rejected(self):
        spec = self.fixture()
        self.assertEqual(structure_layout.build_overview(spec), structure_layout.build_overview(spec))
        spec["groups"][0]["parent"] = "worker0"
        with self.assertRaisesRegex(ValueError, "containment"):
            structure_layout.build_overview(spec)


if __name__ == "__main__":
    unittest.main()
