"""Source truth and readable repeated ownership on synthetic holdouts."""
import copy
import json
from pathlib import Path
import unittest

from silicon_canvas import engine, presentation, publication_layout, reading_plan, structure_layout


def repeated(count=4, families=1, connected=False):
    groups = [{"id": "system", "label": "Processing Appliance", "parent": ""}]
    nodes, edges = [], []
    for family in range(families):
        stem = "Input Channel" if family == 0 else "Output Channel"
        for instance in range(count):
            gid = f"g{family}_{instance}"
            groups.append({"id": gid, "label": f"{stem} {instance}", "parent": "system"})
            for role, kind in [("Transform", "compute"), ("Queue", "memory")]:
                nodes.append({"id": f"n{family}_{instance}_{role}", "label": f"{role} {instance}", "kind": kind,
                              "group": gid, "detail": "32-bit payload" if role == "Queue" else "Process one item"})
            if connected:
                edges.append({"source": f"n{family}_{instance}_Transform", "target": f"n{family}_{instance}_Queue", "kind": "data", "label": "32-bit payload"})
    return engine.normalize_spec({"title": "Resource Appliance", "category": "architecture", "groups": groups,
                                  "nodes": nodes, "edges": edges, "steps": [], "annotations": []})


def primary(spec):
    settings = engine.normalize_settings({"settings": {"representation": "diagram", "scene": "system", "style": "paper"}})
    plan = reading_plan.build(spec, settings, presentation.build_plan(spec, settings["density"], "en"))
    return plan, plan["figures"][0], settings


class ArchitectureDesignTests(unittest.TestCase):
    def test_multiword_instance_names_need_no_dispatcher_to_establish_truthful_array(self):
        request = json.loads((Path(__file__).parent / "fixtures/design_coverage/repeated-ingress.json").read_text(encoding="utf-8"))
        spec = request["spec"]
        before = copy.deepcopy(spec)
        plan, figure, settings = primary(spec)
        self.assertEqual(spec, before)
        self.assertEqual(figure["design_contract"]["grammar"], "resource-array")
        owners = {node["id"]: node for node in figure["macro_nodes"]}
        for index in range(4):
            gid = "lane" + str(index)
            self.assertEqual(owners[gid]["original_group"], "engine")
            self.assertEqual(set(owners[gid]["members"]), {node["id"] for node in spec["nodes"] if node["group"] == gid})
        self.assertEqual(sum(bool(owners["lane" + str(index)]["children"]) for index in range(4)), 1)
        self.assertEqual([node["id"] for node in owners["lane0"]["children"]], ["rx0", "parse0", "q0", "tag0"])
        self.assertEqual(set(figure["projection"]["source_node_to_macro"]), {node["id"] for node in spec["nodes"]})
        indices = [index for edge in figure["macro_edges"] for index in edge["members"]] + figure["projection"]["internal_edges"]
        self.assertCountEqual(indices, range(21))
        self.assertEqual(len(indices), len(set(indices)))
        exact = [index for item in plan["figures"] if not item["abstract"] for index in item["edge_indices"]]
        self.assertCountEqual(exact, range(21))
        layout = publication_layout.build(spec, figure, settings)
        self.assertIsNotNone(layout, figure.get("composition_diagnostics"))
        self.assertEqual(len(layout["insets"]), 1)
        inset = layout["insets"][0]
        self.assertTrue(inset["same_hardware"])
        self.assertEqual(inset["source_object"], "lane0")
        self.assertEqual(inset["source_internal_edge_indices"], [0, 1, 2])
        self.assertEqual(layout["source_ownership"], {node["id"]: node["group"] for node in spec["nodes"]})
        self.assertEqual(set(layout["boxes"]), set(owners))
        self.assertTrue(layout["typography"]["no_font_shrink"])
        self.assertLessEqual(160 / layout["canvas"]["natural_aspect"], 140)
        self.assertTrue(layout["layout_scene"]["quality"]["routes_complete"])
        self.assertFalse(any("Dispatcher" in node["label"] or "Bus" in node["label"] for node in layout["macro_nodes"]))

    def test_quantity_tensor_and_residency_differences_never_prove_equivalence(self):
        for field, value in [("detail", "64-bit payload"), ("tensor_shape", "[64, 32]"), ("residency", "External DRAM")]:
            with self.subTest(field=field):
                spec = repeated(2, connected=True)
                spec["nodes"][-1][field] = value
                layout = structure_layout.build_overview(spec)
                self.assertIsNotNone(layout)
                self.assertEqual(layout["repeat_families"], [])

    def test_same_inventory_with_different_internal_arrows_is_not_equivalent(self):
        spec = repeated(2, connected=True)
        edge = spec["edges"][-1]
        edge["source"], edge["target"] = edge["target"], edge["source"]
        self.assertEqual(structure_layout.build_overview(spec)["repeat_families"], [])

    def test_numeric_detail_matching_instance_number_remains_a_fact(self):
        spec = repeated(2)
        spec["nodes"][1]["detail"] = "Depth 0"
        spec["nodes"][3]["detail"] = "Depth 1"
        self.assertEqual(structure_layout.build_overview(spec)["repeat_families"], [])

    def test_bilingual_and_nonnumeric_owner_names_use_only_actual_identity_prefixes(self):
        for names in [("输入通道甲", "输入通道乙"), ("Input Channel A", "Input Channel B")]:
            with self.subTest(names=names):
                spec = repeated(2, connected=True)
                for index, name in enumerate(names):
                    group = next(group for group in spec["groups"] if group["id"] == "g0_" + str(index))
                    group["label"] = name
                    for node in spec["nodes"]:
                        if node["group"] == group["id"]:
                            node["label"] = name + ("：数据变换" if node["kind"] == "compute" else "：数据队列")
                plan = structure_layout.build_overview(spec)
                self.assertEqual(len(plan["repeat_families"]), 1)
                self.assertEqual(plan["repeat_families"][0]["instances"], ["g0_1"])
                spec["nodes"][-1]["detail"] = "64-bit payload"
                self.assertEqual(structure_layout.build_overview(spec)["repeat_families"], [])

    def test_wholly_different_owner_roles_are_not_equated_from_generic_child_names(self):
        spec = repeated(2, connected=True)
        spec["groups"][1]["label"] = "Decryptor"
        spec["groups"][2]["label"] = "Encryptor"
        self.assertEqual(structure_layout.build_overview(spec)["repeat_families"], [])

    def test_cache_level_and_precision_numbers_do_not_become_instance_ordinals(self):
        for labels in [("L2 Cache", "L3 Cache"), ("FP32 Engine", "FP64 Engine")]:
            with self.subTest(labels=labels):
                spec = repeated(2)
                for group, label in zip(spec["groups"][1:], labels):
                    group["label"] = label
                self.assertEqual(structure_layout.build_overview(spec)["repeat_families"], [])

    def test_heterogeneous_sibling_stays_a_real_owner_with_its_distinct_inventory(self):
        spec = repeated(4, connected=True)
        spec["nodes"][-1]["detail"] = "64-bit payload"
        _, figure, _ = primary(spec)
        objects = {node["id"]: node for node in figure["macro_nodes"]}
        varied = objects["g0_3"]
        self.assertNotIn("equivalent_to", varied)
        self.assertEqual(varied["original_group"], "system")
        self.assertEqual(len(varied["children"]), 2)
        self.assertEqual(figure["projection"]["source_node_to_macro"]["n0_3_Queue"], "g0_3")
        self.assertIn("64-bit payload", str(varied["children"]))
        family = figure["repeat_families"][0]
        self.assertNotIn("g0_3", family["instances"])

    def test_variable_count_and_multiple_families_preserve_actual_instances(self):
        for count, family_count in [(2, 1), (7, 1), (3, 2)]:
            with self.subTest(count=count, families=family_count):
                spec = repeated(count, family_count)
                _, figure, settings = primary(spec)
                layout = publication_layout.build(spec, figure, settings)
                self.assertIsNotNone(layout, figure.get("composition_diagnostics"))
                self.assertEqual(len(layout["insets"]), family_count)
                self.assertEqual(set(layout["boxes"]), {group["id"] for group in spec["groups"] if group["parent"]})
                self.assertEqual({index for inset in layout["insets"] for index in inset["source_members"]},
                                 {node["id"] for node in spec["nodes"] if node["group"] in {family["template_group"] for family in figure["repeat_families"]}})
                self.assertEqual(layout["typography"]["body_px"], 36)

    def test_claimed_equivalence_cannot_override_different_supplied_parameters(self):
        spec = repeated(2)
        spec["nodes"][-1]["detail"] = "64-bit payload"
        with self.assertRaisesRegex(ValueError, "technical internals"):
            structure_layout.build_overview(spec, hints={"repeated_sets": [{"template_group": "g0_0", "instances": ["g0_1"], "evidence": "Caller says same"}]})

    def test_source_owned_join_is_readable_without_a_fake_dispatcher_or_hub(self):
        request = json.loads((Path(__file__).parent / "fixtures/design_coverage/heterogeneous-instrument.json").read_text(encoding="utf-8"))
        spec = request["spec"]
        original = copy.deepcopy(spec)
        _, figure, settings = primary(spec)
        layout = publication_layout.build(spec, figure, settings)
        self.assertIsNotNone(layout, figure.get("composition_diagnostics"))
        self.assertEqual(spec, original)
        self.assertEqual(layout["canvas"]["reading_direction"], "existing-owned-join")
        self.assertLessEqual(160 / layout["canvas"]["natural_aspect"], 140)
        self.assertEqual(set(layout["boxes"]), {"fast", "slow", "common", "external"})
        self.assertTrue(layout["layout_scene"]["quality"]["organization_traces"]["clear"])
        self.assertTrue(layout["layout_scene"]["quality"]["owner_scope_entries"]["clear"])
        self.assertTrue(layout["layout_scene"]["quality"]["routes_complete"])
        common = next(node for node in layout["macro_nodes"] if node["id"] == "common")
        self.assertEqual(set(common["members"]), {"timestamp", "merge", "store", "dma"})
        self.assertIn("Timestamp-Aligned Event Merger", str(layout["symbol_metrics"]["common"]["children"]))
        original_indices = [index for edge in figure["macro_edges"] for index in edge["members"]] + figure["projection"]["internal_edges"]
        self.assertCountEqual(original_indices, range(11))


if __name__ == "__main__":
    unittest.main()
