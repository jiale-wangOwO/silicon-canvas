"""Extraction contracts: display language, source provenance and math meaning."""
import json
import unittest
from unittest.mock import patch

from silicon_canvas import algorithm_flow, engine, service


def spec():
    return {"title": "Value transform", "category": "dataflow", "groups": [],
            "nodes": [{"id": "a", "label": "Input", "kind": "io", "group": "", "detail": "", "origin": "given", "evidence": "输入"},
                      {"id": "b", "label": "Transform", "kind": "compute", "group": "", "detail": "", "origin": "given", "evidence": "计算"}],
            "edges": [{"source": "a", "target": "b", "kind": "data", "label": "", "origin": "given", "evidence": "输入连接计算"}]}


def prepared():
    return engine.prepare_request({"description": "输入连接计算。", "completion_mode": "strict", "language": "en"})


class SemanticContractTests(unittest.TestCase):
    def test_strict_example_contains_no_assumed_structure_or_invented_verbatim_label(self):
        messages, _ = prepared()
        system = messages[0]["content"]
        example = json.loads(system.split("The required JSON shape is:\n", 1)[1].split("\nNode kind:", 1)[0])
        self.assertEqual(example["verbatim_labels"], [])
        self.assertEqual(example["groups"], [])
        self.assertEqual(example["edges"], [])
        self.assertTrue(all(item["origin"] == "given" for item in example["nodes"]))
        self.assertIn("never copy its placeholder objects", system)

    def test_auto_example_keeps_transparent_assumptions_without_mandatory_labels(self):
        messages, _ = engine.prepare_request({"description": "完整的传感器系统"})
        system = messages[0]["content"]
        example = json.loads(system.split("The required JSON shape is:\n", 1)[1].split("\nNode kind:", 1)[0])
        self.assertEqual(example["verbatim_labels"], [])
        self.assertTrue(any(item["origin"] == "assumed" for item in example["nodes"]))

    def test_original_chinese_evidence_with_english_artwork_stays_given(self):
        _, context = prepared()
        result = engine.finish_request(spec(), context)
        self.assertEqual([item["origin"] for item in result["spec"]["nodes"]], ["given", "given"])
        self.assertEqual(result["spec"]["nodes"][0]["label"], "Input")
        self.assertEqual(result["spec"]["nodes"][0]["evidence"], "输入")

    def test_bad_provenance_reports_exact_path_and_leaves_valid_facts_out_of_repair_list(self):
        messages, context = prepared()
        bad = spec()
        bad["nodes"][1]["evidence"] = "Transform"
        with self.assertRaises(engine.ProvenanceError) as caught:
            engine.finish_request(bad, context)
        issues = caught.exception.issues
        self.assertEqual([issue["path"] for issue in issues], ["nodes[1].evidence"])
        repaired = engine.prepare_repair(messages, bad, context, caught.exception)
        instruction = repaired[-1]["content"]
        self.assertIn("nodes[1].evidence", instruction)
        self.assertIn("exact contiguous original-language quote", instruction)
        self.assertIn("Preserve every valid supplied object", instruction)
        self.assertNotIn('"path": "nodes[0].evidence"', instruction)

    def test_strict_assumptions_remain_rejected_instead_of_downgraded_to_given(self):
        _, context = prepared()
        bad = spec()
        bad["nodes"][1].update(origin="assumed", rationale="A proposed action.", evidence="")
        with self.assertRaises(engine.ProvenanceError) as caught:
            engine.finish_request(bad, context)
        self.assertEqual(caught.exception.issues[0]["path"], "nodes[1].origin")

    def test_failed_repair_still_stops_after_two_provider_calls(self):
        bad = spec()
        bad["nodes"][1]["evidence"] = "translated quote"
        reply = {"data": bad, "model": "test", "usage": {}}
        with patch("silicon_canvas.provider.complete", return_value=reply) as complete:
            with self.assertRaises(service.GenerationError):
                service.generate_result({"description": "输入连接计算。", "completion_mode": "strict"}, engine)
        self.assertEqual(complete.call_count, 2)

    def test_typed_mathematical_dataflow_does_not_depend_on_category_name_or_keywords(self):
        raw = spec()
        for index, node in enumerate(raw["nodes"]):
            node.update(label="Object " + str(index), diagram_role="tensor" if index == 0 else "operator")
        normalized = engine.normalize_spec(raw)
        self.assertTrue(algorithm_flow.applicable(normalized))
        result = engine.compile_manual({"spec": normalized, "settings": {"scene": "flow", "representation": "diagram"}})
        self.assertIn("algorithm_flow_plan", result["figures"][0])
        self.assertEqual(result["spec"]["category"], "dataflow")
        messages, _ = engine.prepare_request({"description": "变换给定张量", "category": "dataflow"})
        self.assertIn("Set diagram_role=", messages[0]["content"])
        self.assertIn("independently of its English/Chinese name or the category token", messages[0]["content"])

    def test_empty_example_arrays_do_not_erase_complete_object_contracts(self):
        messages, _ = prepared()
        schema = json.loads(messages[1]["content"])["specification_schema"]
        self.assertEqual(schema["properties"]["groups"]["items"], {"$ref": "#/$defs/group"})
        self.assertEqual(schema["properties"]["edges"]["items"], {"$ref": "#/$defs/edge"})
        group, node, edge = (schema["$defs"][key] for key in ("group", "node", "edge"))
        self.assertTrue({"id", "label", "parent", "origin", "evidence", "rationale"} <= set(group["required"]))
        self.assertTrue({"source", "target", "kind", "label", "origin", "evidence", "rationale"} <= set(edge["required"]))
        self.assertEqual(edge["properties"]["source"]["type"], "string")
        self.assertEqual(edge["properties"]["target"]["type"], "string")
        self.assertTrue({"diagram_role", "tensor_shape", "reduction_axis", "residency"} <= set(node["properties"]))
        self.assertEqual(node["properties"]["origin"], {"const": "given"})
        self.assertEqual(node["properties"]["evidence"]["minLength"], 1)
        # Exercise the actual matching output path, not only the prompt text.
        _, context = prepared()
        self.assertEqual(len(engine.finish_request(spec(), context)["spec"]["edges"]), 1)

    def test_misnamed_endpoint_fields_are_rejected_with_actionable_paths(self):
        bad = spec()
        bad["edges"] = [{"from": "a", "to": "b", "id": "e0", "kind": "data", "label": ""}]
        with self.assertRaisesRegex(ValueError, r"edges\[0\]\.source.*source.*target.*from/to/id"):
            engine.normalize_spec(bad)
        self.assertNotIn("source", bad["edges"][0], "validation must not silently accept an alias")

    def test_reference_diagnostics_distinguish_type_and_missing_target_identity(self):
        bad = spec()
        bad["edges"][0]["source"] = 5
        with self.assertRaisesRegex(ValueError, r"edges\[0\]\.source.*字符串"):
            engine.normalize_spec(bad)
        bad = spec()
        bad["edges"][0]["target"] = "not-a-source-node"
        with self.assertRaisesRegex(ValueError, r"edges\[0\]\.target.*not-a-source-node.*nodes\[\]\.id"):
            engine.normalize_spec(bad)

    def test_single_repair_can_correct_wrong_endpoint_keys_without_changing_given_graph(self):
        good, bad = spec(), spec()
        edge = bad["edges"][0]
        edge["from"], edge["to"] = edge.pop("source"), edge.pop("target")
        replies = [{"data": item, "model": "test", "usage": {}} for item in (bad, good)]
        with patch("silicon_canvas.provider.complete", side_effect=replies) as complete:
            result = service.generate_result({"description": "输入连接计算。", "completion_mode": "strict"}, engine)
        self.assertEqual(complete.call_count, 2)
        repair = complete.call_args_list[1].args[0][-1]["content"]
        self.assertIn("edges[0].source", repair)
        self.assertIn("source 和 target", repair)
        self.assertTrue(result["repaired"])
        self.assertEqual(result["spec"]["edges"], engine.normalize_spec(good)["edges"])

    def test_explicit_state_category_example_and_schema_agree(self):
        messages, _ = engine.prepare_request({"description": "IDLE收到start进入DONE", "category": "fsm", "completion_mode": "strict"})
        example = json.loads(messages[0]["content"].split("The required JSON shape is:\n", 1)[1].split("\nNode kind:", 1)[0])
        schema = json.loads(messages[1]["content"])["specification_schema"]
        self.assertEqual(example["category"], "fsm")
        self.assertEqual(example["nodes"][0]["kind"], "state")
        self.assertEqual(schema["properties"]["category"], {"const": "fsm"})


if __name__ == "__main__":
    unittest.main()
