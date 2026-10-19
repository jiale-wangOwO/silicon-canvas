"""Generalization checks use original frozen sources, not polished demo outputs."""
import copy
import importlib.util
import itertools
import json
from pathlib import Path
import unittest

from silicon_canvas import engine

ROOT = Path(__file__).resolve().parents[1]
MODULE = importlib.util.spec_from_file_location("coverage_helpers", ROOT / "scripts" / "design_coverage.py")
coverage = importlib.util.module_from_spec(MODULE)
MODULE.loader.exec_module(coverage)


class DesignCoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = {name: coverage.source(name) for name in coverage.CASES}
        cls.before = copy.deepcopy(cls.sources)
        cls.results = {name: engine.compile_manual(payload) for name, payload in cls.sources.items()}

    def test_all_twelve_sources_preserve_facts_ownership_and_actual_display_burden(self):
        for name, payload in self.sources.items():
            with self.subTest(case=name):
                coverage.assert_contract(name, payload, self.results[name])
                self.assertEqual(payload, self.before[name])

    def test_reader_strategies_distinguish_state_time_math_stage_and_ownership(self):
        expected = {"retry-controller": "state-transition", "ready-valid-trace": "signal-time",
                    "residual-projection": "mathematical-dependency", "elastic-pipeline": "stage-dependency",
                    "mesh-memory": "ownership-network"}
        for name, kind in expected.items():
            with self.subTest(case=name):
                figure = coverage.selected(self.results[name])
                self.assertEqual(figure["diagram_design"]["reading_strategy"]["kind"], kind)

    def test_fsm_fixture_predicates_are_complete_disjoint_and_obey_success_priority(self):
        spec = self.sources["retry-controller"]["spec"]
        outgoing = {node["id"]: [edge for edge in spec["edges"] if edge["source"] == node["id"]] for node in spec["nodes"]}
        variables = ("start", "accepted", "ok", "timeout", "retried", "clear")
        for values in itertools.product((False, True), repeat=len(variables)):
            context = dict(zip(variables, values))
            for state, relations in outgoing.items():
                if state in {"retry", "done"}:
                    self.assertEqual(len(relations), 1)
                    self.assertNotEqual(relations[0]["target"], state)
                    continue
                matches = []
                for relation in relations:
                    predicates = relation["label"].split(" && ")
                    self.assertTrue(all(token.removeprefix("!") in context for token in predicates))
                    enabled = all(not context[token[1:]] if token.startswith("!") else context[token]
                                  for token in predicates)
                    if enabled:
                        matches.append(relation)
                self.assertEqual(len(matches), 1, (state, context))
                if state == "wait" and context["ok"]:
                    self.assertEqual(matches[0]["target"], "done")
        self.assertIn("Synchronous reset has highest priority and sends every state to IDLE; retried=0.", spec["annotations"])

    def test_fsm_primary_keeps_every_self_loop_and_exact_transition_predicate(self):
        spec, figure = self.sources["retry-controller"]["spec"], coverage.selected(self.results["retry-controller"])
        self.assertEqual({node["id"] for node in figure["macro_nodes"]}, {node["id"] for node in spec["nodes"]})
        self.assertEqual(len(figure["macro_edges"]), len(spec["edges"]))
        for relation in figure["macro_edges"]:
            self.assertEqual(len(relation["members"]), 1)
            original = spec["edges"][relation["members"][0]]
            self.assertEqual({key: relation[key] for key in ("source", "target", "label", "kind")}, {key: original[key] for key in ("source", "target", "label", "kind")})
        self.assertEqual(sum(edge["source"] == edge["target"] for edge in figure["macro_edges"]), 4)

    def test_timing_fixture_accepts_exactly_three_beats_and_holds_stalled_data(self):
        spec = self.sources["ready-valid-trace"]["spec"]
        samples = {node["id"]: node["detail"].split(": ", 1)[1].split() for node in spec["nodes"] if node["id"] != "clk"}
        self.assertTrue(all(len(row) == 8 for row in samples.values()))
        accepted = []
        for cycle in range(8):
            transfer = all(samples[name][cycle] == "1" for name in ("rst_n", "valid", "ready"))
            self.assertEqual(samples["transfer"][cycle], str(int(transfer)))
            if transfer:
                accepted.append((cycle, samples["data"][cycle]))
            if cycle > 0 and samples["valid"][cycle - 1] == "1" and samples["ready"][cycle - 1] == "0":
                self.assertEqual(samples["valid"][cycle], "1")
                self.assertEqual(samples["data"][cycle], samples["data"][cycle - 1])
        self.assertEqual(accepted, [(4, "A"), (5, "B"), (6, "C")])
        figure = coverage.selected(self.results["ready-valid-trace"])
        timing = figure["structure_layout"]
        self.assertEqual(timing["axis"], [f"c{i}" for i in range(8)])
        rows = {item["id"]: item for item in timing["rows"]}
        self.assertEqual(rows["clk"]["kind"], "sample-markers")
        self.assertEqual(rows["clk"]["values"], [])
        for node_id, values in samples.items():
            self.assertEqual(rows[node_id]["values"], values)
            self.assertIn(" | ".join(values), figure["prompt"])

    def test_residual_operand_joins_shapes_and_identity_skip_remain_source_exact(self):
        result = self.results["residual-projection"]
        spec, figure = result["spec"], coverage.selected(result)
        plan = figure["algorithm_flow_plan"]
        self.assertEqual(len(plan["objects"]), 10)
        self.assertEqual(len(plan["relations"]), 10)
        joins = {item["target_node_id"]: set(item["source_node_ids"]) for item in plan["motifs"]["joins"]}
        self.assertEqual(joins["mm1"], {"x", "w1"})
        self.assertEqual(joins["bias"], {"mm1", "b1"})
        self.assertEqual(joins["mm2"], {"relu", "w2"})
        self.assertEqual(joins["res"], {"mm2", "x"})
        self.assertNotIn("state", {item["role"] for item in plan["objects"]})
        self.assertFalse(plan["motifs"]["recurrence_components"])
        shapes = {node["id"]: node["tensor_shape"] for node in spec["nodes"]}
        self.assertEqual(shapes["x"], shapes["mm2"])
        self.assertEqual(shapes["res"], shapes["y"])

    def test_pipeline_preserves_two_separate_senses_without_inventing_a_schedule(self):
        spec, figure = self.sources["elastic-pipeline"]["spec"], coverage.selected(self.results["elastic-pipeline"])
        self.assertEqual(len(figure["macro_nodes"]), 6)
        self.assertEqual(len(figure["macro_edges"]), 10)
        for relation in figure["macro_edges"]:
            self.assertEqual(len(relation["members"]), 1)
            self.assertFalse(relation.get("bidirectional"))
            original = spec["edges"][relation["members"][0]]
            self.assertEqual((relation["source"], relation["target"], relation["label"], relation["kind"]), (original["source"], original["target"], original["label"], original["kind"]))
        self.assertIn("2 entries; absorption capacity, not 2-cycle latency", figure["prompt"])
        self.assertIn("No stage latency, initiation interval or cycle schedule has been supplied", figure["prompt"])

    def test_mesh_keeps_four_router_adjacencies_and_external_memory_scope(self):
        spec, figure = self.sources["mesh-memory"]["spec"], coverage.selected(self.results["mesh-memory"])
        self.assertEqual(len(figure["macro_nodes"]), 12)
        self.assertEqual(len(figure["macro_edges"]), 24)
        routes = [(edge["source"], edge["target"]) for edge in figure["macro_edges"]]
        self.assertNotIn(("r0", "r3"), routes)
        self.assertNotIn(("r1", "r2"), routes)
        self.assertIn(("r0", "r1"), routes)
        self.assertIn(("r1", "r0"), routes)
        self.assertEqual(next(node for node in spec["nodes"] if node["id"] == "dram")["group"], "external")

    def test_repeated_private_instances_count_as_actual_display_work(self):
        spec = self.sources["repeated-ingress"]["spec"]
        figure = coverage.selected(self.results["repeated-ingress"])
        plan = figure["diagram_design"]
        objects = {item["id"]: item for item in figure["macro_nodes"]}
        source_map = figure["projection"]["source_node_to_macro"]
        self.assertEqual(set(source_map), {node["id"] for node in spec["nodes"]})
        for i in range(4):
            group_id = f"lane{i}"
            actual_members = [node["id"] for node in spec["nodes"] if node["group"] == group_id]
            self.assertEqual(objects[group_id]["label"], f"Ingress Lane {i}")
            self.assertEqual(set(objects[group_id]["members"]), set(actual_members))
            self.assertTrue(all(source_map[node_id] == group_id for node_id in actual_members))
            self.assertEqual(objects[group_id]["original_group"], "engine")
        families = figure["repeat_families"]
        self.assertEqual(len(families), 1)
        family = families[0]
        self.assertEqual(family["template_group"], "lane0")
        self.assertEqual(set(family["instances"]), {"lane1", "lane2", "lane3"})
        self.assertTrue(family["evidence"])
        insets = [item for item in figure["structure_layout"].get("insets", []) if item.get("same_hardware")]
        self.assertEqual(len(insets), 1)
        self.assertEqual(insets[0]["source_object"], "lane0")
        self.assertEqual(len(insets[0]["metrics"]["children"]), 4)
        self.assertLess(plan["burden"]["unique_source_leaves"], 22)
        self.assertGreaterEqual(plan["burden"]["leaf_appearances"], 10)
        self.assertGreater(plan["burden"]["text_items"], plan["burden"]["top_level_objects"])
        represented = [index for relation in figure["macro_edges"] for index in relation["members"]]
        internal = figure["projection"]["internal_edges"]
        self.assertEqual(sorted(represented + internal), list(range(len(spec["edges"]))))
        self.assertEqual(len(represented + internal), len(set(represented + internal)))

    def test_unequal_repeated_peer_is_never_summarized_as_the_same_inventory(self):
        payload = copy.deepcopy(self.sources["repeated-ingress"])
        next(node for node in payload["spec"]["nodes"] if node["id"] == "q3")["detail"] = "Private; 32-entry exception queue"
        result = engine.compile_manual(payload)
        coverage.assert_contract("repeated-ingress", payload, result)
        figure = coverage.selected(result)
        self.assertTrue(all("lane3" not in family["instances"] for family in figure.get("repeat_families", [])))
        peers = {item["id"]: item for item in figure["macro_nodes"]}
        if "lane3" in peers:
            self.assertFalse(peers["lane3"].get("equivalent_to"))
        self.assertIn("Private; 32-entry exception queue", json.dumps(result["spec"]))

    def test_same_source_produces_three_different_commercial_reading_tasks(self):
        names = ("commercial-context", "commercial-cutaway", "commercial-hero")
        self.assertEqual(len({self.results[name]["source_hash"] for name in names}), 1)
        modes = [coverage.selected(self.results[name])["render_brief"]["explanation_plan"]["mode"] for name in names]
        self.assertEqual(modes, ["annotated_context", "functional_cutaway", "hero"])

    def test_sparse_completion_remains_assumed_and_informative(self):
        spec = self.results["sparse-acquisition"]["spec"]
        self.assertEqual(len(spec["nodes"]), 5)
        self.assertTrue(all(item["origin"] == "assumed" and not item["evidence"] for item in spec["nodes"] + spec["edges"]))
        figure = coverage.selected(self.results["sparse-acquisition"])
        if figure.get("render_brief"):
            self.assertNotEqual(figure["render_brief"]["explanation_plan"]["mode"], "hero")
        self.assertEqual(spec, self.sources["sparse-acquisition"]["spec"])


if __name__ == "__main__":
    unittest.main()
