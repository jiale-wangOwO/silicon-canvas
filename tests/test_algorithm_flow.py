import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from mcp import Client
from mcp.types import ImageContent

from silicon_canvas import algorithm_flow, bundle, engine, layout_guide, reading_plan
from silicon_canvas.mcp_server import create_server

ROOT = Path(__file__).resolve().parents[1]


def fixture(name="attention-dataflow.json"):
    return json.loads((ROOT / "examples" / name).read_text(encoding="utf-8"))


class AlgorithmFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.attention = engine.compile_manual(fixture())
        cls.online = engine.compile_manual(fixture("online-attention-dataflow.json"))

    def test_complete_source_keeps_named_operations_and_all_group_leaves(self):
        raw = fixture()
        before = copy.deepcopy(raw)
        result = self.attention
        self.assertEqual(raw, before)
        self.assertEqual(result["spec"], engine.normalize_spec(raw["spec"]))
        figure = result["figures"][0]
        self.assertEqual(figure["view_role"], "algorithm-dataflow")
        self.assertEqual(figure["projection"]["folded_groups"], [])
        self.assertEqual(figure["projection"]["deferred_edges"], [])
        self.assertEqual({n["id"] for n in figure["macro_nodes"]}, {n["id"] for n in raw["spec"]["nodes"]})
        self.assertEqual([e["members"] for e in figure["macro_edges"]], [[i] for i in range(8)])
        self.assertEqual(figure["algorithm_flow_plan"]["source_hash"], reading_plan.source_hash(result["spec"]))
        for node in raw["spec"]["nodes"]:
            self.assertIn(node["label"], figure["prompt"])

    def test_separate_query_key_value_joins_do_not_become_serial_steps(self):
        plan = self.attention["figures"][0]["algorithm_flow_plan"]
        joins = {item["target_node_id"]: item for item in plan["motifs"]["joins"]}
        self.assertEqual(joins["scores"]["source_node_ids"], ["q", "k"])
        self.assertEqual(joins["weighted"]["source_node_ids"], ["softmax", "v"])
        self.assertEqual(plan["motifs"]["reductions"], ["softmax"])
        self.assertNotIn("scores", plan["motifs"]["reductions"])
        relations = [(r["source"], r["target"]) for r in plan["relations"]]
        self.assertNotIn(("q", "k"), relations)
        self.assertNotIn(("v", "softmax"), relations)
        placement = {p["source_node_id"]: p for p in plan["composition"]["matched_operand_placement"]}
        self.assertEqual(placement["v"]["consumer_node_id"], "weighted")
        self.assertEqual(placement["mask"]["consumer_node_id"], "scale_mask")

    def test_tensor_shape_and_residency_have_exact_source_field_provenance(self):
        result = self.online
        plan = result["figures"][0]["algorithm_flow_plan"]
        sources = {n["id"]: n for n in result["spec"]["nodes"]}
        for obj in plan["objects"]:
            source = sources[obj["source_node_id"]]
            for key, value in obj["source_fields"].items():
                self.assertEqual(value, source[key])
            self.assertEqual(obj["source_group"], source["group"])
            self.assertEqual(obj["tensor_shape"], source.get("tensor_shape", ""))
            self.assertEqual(obj["residency"], source.get("residency", ""))
        resident = {p["source_node_id"]: p["residency"] for p in plan["motifs"]["data_residency"]}
        self.assertEqual(resident["k_tile"], "Loaded from HBM each j")
        self.assertNotIn("normalize", resident)

    def test_real_recurrence_and_final_exit_are_not_merged(self):
        plan = self.online["figures"][0]["algorithm_flow_plan"]
        cycle = plan["motifs"]["recurrence_components"]
        self.assertEqual(len(cycle), 1)
        self.assertEqual(set(cycle[0]["node_ids"]), {"online", "accumulate", "state"})
        self.assertNotIn(8, cycle[0]["source_edge_indices"])
        self.assertEqual(plan["relations"][8]["label"], "final l, A; after all KV tiles")
        self.assertEqual(plan["relations"][8]["target"], "normalize")
        for index in (3, 6, 7):
            self.assertEqual(plan["relations"][index]["kind"], "feedback")
            self.assertEqual(plan["relations"][index]["display_role"], "state operand/update")
            self.assertEqual(plan["relations"][index]["display_stroke"], "solid")

    def test_intentional_text_plan_has_no_hardware_guide_or_required_image(self):
        result = self.attention
        figure = result["figures"][0]
        self.assertFalse(figure["requires_layout_guide"])
        self.assertEqual(figure["generation_inputs"], [])
        self.assertEqual(figure["layout_strategy"], "algorithm-dependency-plan")
        self.assertIsNone(layout_guide.render(result, figure))
        self.assertNotIn("structure_layout", figure)
        self.assertIn("No input guide image is required", figure["prompt"])
        self.assertFalse(any(w.startswith("视图 ") and figure["title"] in w for w in result["warnings"]))

    def test_export_contains_exact_plan_without_phantom_guide(self):
        result = self.online
        figure = result["figures"][0]
        with zipfile.ZipFile(io.BytesIO(bundle.build(result, figure["id"]))) as archive:
            prefix = "figures/" + figure["id"] + "/"
            self.assertEqual(json.loads(archive.read(prefix + "algorithm-flow-plan.json")), figure["algorithm_flow_plan"])
            self.assertNotIn(prefix + "layout-guide.png", archive.namelist())
            self.assertIn("generation_inputs 为空", archive.read("USE.txt").decode())

    def test_review_requires_actual_shapes_and_semantic_data_paths(self):
        figure = self.online["figures"][0]
        review = figure["review_task"]
        self.assertEqual(review["status"], "not_reviewed")
        self.assertFalse(review["has_controlled_plate"])
        self.assertEqual(review["objects"], figure["algorithm_flow_plan"]["objects"])
        self.assertEqual(review["expected_connections"], figure["algorithm_flow_plan"]["relations"])
        self.assertIn("A fan-in does not imply a reduction", review["prompt"])
        self.assertIn("does not certify the bitmap", review["prompt"])

    def test_missing_dimensions_never_acquire_shapes_or_grid_counts(self):
        spec = engine.normalize_spec(fixture()["spec"])
        for node in spec["nodes"]:
            node.pop("tensor_shape", None)
            node.pop("residency", None)
        plan = algorithm_flow.build(spec)
        self.assertEqual(plan["motifs"]["tensor_shapes"], [])
        self.assertEqual(plan["motifs"]["data_residency"], [])
        self.assertTrue(all(not obj["tensor_shape"] for obj in plan["objects"]))

    def test_generic_hardware_dma_buffer_mac_path_keeps_engineering_grammar(self):
        from tests.test_engine import sample
        spec = engine.normalize_spec(sample())
        self.assertFalse(algorithm_flow.applicable(spec))
        result = engine.compile_manual({"spec": spec, "settings": {"scene": "flow", "representation": "diagram"}})
        self.assertNotIn("algorithm_flow_plan", result["figures"][0])
        self.assertNotEqual(result["figures"][0]["layout_strategy"], "algorithm-dependency-plan")

    def test_without_optional_metadata_math_is_detected_from_supplied_content(self):
        spec = engine.normalize_spec(fixture()["spec"])
        for node in spec["nodes"]:
            node.pop("diagram_role", None)
        self.assertTrue(algorithm_flow.applicable(spec))
        plan = algorithm_flow.build(spec)
        objects = {o["source_node_id"]: o for o in plan["objects"]}
        self.assertEqual(objects["q"]["role"], "tensor")
        self.assertEqual(objects["scores"]["role"], "operator")
        self.assertNotIn("scores", plan["motifs"]["reductions"])
        self.assertIn("weighted", plan["motifs"]["reductions"])  # Supplied detail says "Weighted value sum".
        self.assertIn("graphical interpretation", objects["scores"]["role_basis"]["type"])

    def test_cycle_detection_and_identity_mapping_are_independent_of_names(self):
        spec = engine.normalize_spec(fixture("online-attention-dataflow.json")["spec"])
        renames = {n["id"]: "node_" + str(i) for i, n in enumerate(spec["nodes"])}
        for n in spec["nodes"]:
            n["id"] = renames[n["id"]]
            n["label"] = "Object " + n["id"]
        for e in spec["edges"]:
            e["source"], e["target"] = renames[e["source"]], renames[e["target"]]
        spec["title"] = "Unnamed recurrent computation"
        plan = algorithm_flow.build(spec)
        self.assertEqual(len(plan["motifs"]["recurrence_components"]), 1)
        self.assertEqual(plan["motifs"]["reductions"], [renames["online"]])

    def test_single_state_name_does_not_invent_return_loop(self):
        spec = engine.normalize_spec({"title": "A state update", "category": "algorithm", "nodes": [{"id": "state", "label": "State", "kind": "state"}, {"id": "out", "label": "Output", "kind": "io"}], "edges": [{"source": "state", "target": "out", "kind": "data"}]})
        plan = algorithm_flow.build(spec)
        self.assertEqual(plan["motifs"]["recurrence_components"], [])
        self.assertEqual(plan["composition"]["return_edge_indices"], [])
        self.assertEqual(len(plan["relations"]), 1)

    def test_payload_feedback_keeps_solid_data_return_without_state_node(self):
        spec = engine.normalize_spec(fixture()["spec"])
        spec["edges"][0]["kind"] = "feedback"
        spec["edges"][0]["label"] = "returned data"
        relation = algorithm_flow.build(spec)["relations"][0]
        self.assertEqual(relation["kind"], "feedback")
        self.assertEqual(relation["display_role"], "data return")
        self.assertEqual(relation["display_stroke"], "solid")

    def test_explicit_control_and_clock_keep_their_own_dependency_treatment(self):
        spec = engine.normalize_spec(fixture()["spec"])
        spec["edges"][0]["kind"] = "control"
        spec["edges"][0]["label"] = "enable"
        rel = algorithm_flow.build(spec)["relations"][0]
        self.assertEqual(rel["display_role"], "control dependency")
        self.assertEqual(rel["display_stroke"], "dashed")

    def test_explicit_vertical_layout_and_monochrome_are_respected(self):
        spec = engine.normalize_spec(fixture()["spec"])
        spec["layout"] = "Top-to-bottom; keep the V bypass separate."
        figure = algorithm_flow.primary(spec)
        self.assertEqual(figure["algorithm_flow_plan"]["composition"]["primary_reading_axis"], "top-to-bottom dependency order")
        prompt = algorithm_flow.compile_figure(figure, spec, {"style": "monochrome", "aspect": "4:3"}, {})
        self.assertIn("without colored accents", prompt)
        self.assertIn("Requested canvas proportions: 4:3", prompt)

    def test_optional_role_shape_axis_normalization_rejects_invalid_data(self):
        spec = fixture()["spec"]
        spec["nodes"][0]["diagram_role"] = "fake_hardware"
        with self.assertRaises(ValueError):
            engine.normalize_spec(spec)
        spec["nodes"][0]["diagram_role"] = "tensor"
        spec["nodes"][0]["tensor_shape"] = [4, 8]
        with self.assertRaises(ValueError):
            engine.normalize_spec(spec)
        spec["nodes"][0]["diagram_role"] = ""
        spec["nodes"][0]["tensor_shape"] = ""
        self.assertEqual(engine.normalize_spec(spec)["nodes"][0]["diagram_role"], "")

    def test_prepare_retains_mathematics_before_model_independent_compilation(self):
        messages, _ = engine.prepare_request({"description": "Algorithm with two parallel matrix inputs, rowmax and running state", "completion_mode": "strict"})
        self.assertIn("tensor_shape", messages[0]["content"])
        self.assertIn("reduction_axis", messages[0]["content"])
        self.assertIn("Shape/axis/tile counts and equations may not be invented", messages[0]["content"])

    def test_recurrence_exit_starts_at_source_state_and_preserves_completion_predicate(self):
        figure = self.online["figures"][0]
        plan = figure["algorithm_flow_plan"]
        self.assertEqual(len(plan["motifs"]["recurrence_exits"]), 1)
        exit = plan["motifs"]["recurrence_exits"][0]
        self.assertEqual(exit["source_edge_index"], 8)
        self.assertEqual((exit["source_node_id"], exit["target_node_id"]), ("state", "normalize"))
        self.assertEqual(exit["label"], self.online["spec"]["edges"][8]["label"])
        self.assertIn("outside the recurrent kernel", figure["prompt"])
        self.assertIn("do not extend that spine straight into this exit target", figure["prompt"])

    def test_outgoing_contract_rejects_adjacency_shortcuts_and_terminal_outgoing_arrows(self):
        plan = self.online["figures"][0]["algorithm_flow_plan"]
        outgoing = {o["source_node_id"]: o for o in plan["composition"]["outgoing_contracts"]}
        self.assertEqual(outgoing["accumulate"]["allowed_target_node_ids"], ["state"])
        self.assertEqual(outgoing["accumulate"]["source_edge_indices"], [7])
        self.assertEqual(outgoing["state"]["allowed_target_node_ids"], ["online", "accumulate", "normalize"])
        self.assertEqual(outgoing["output"]["allowed_target_node_ids"], [])
        self.assertEqual(outgoing["output"]["source_edge_indices"], [])

    def test_tuple_update_stays_one_connector_and_real_parallel_edges_remain_distinct(self):
        plan = self.online["figures"][0]["algorithm_flow_plan"]
        tuple_link = next(c for c in plan["composition"]["connector_cardinality"] if c["source_node_id"] == "accumulate" and c["target_node_id"] == "state")
        self.assertEqual(tuple_link["connector_count"], 1)
        self.assertEqual(tuple_link["source_edge_indices"], [7])
        self.assertEqual(plan["relations"][7]["label"], "m_new, l_new, A_new")
        spec = copy.deepcopy(self.online["spec"])
        spec["edges"].append({**spec["edges"][7], "label": "separately supplied condition"})
        revised = algorithm_flow.build(spec)
        parallel = next(c for c in revised["composition"]["connector_cardinality"] if c["source_node_id"] == "accumulate" and c["target_node_id"] == "state")
        self.assertEqual(parallel["connector_count"], 2)
        self.assertEqual(parallel["source_edge_indices"], [7, 10])

    def test_math_text_plan_is_compact_without_repeated_dimension_or_detail_prose(self):
        objects = {o["source_node_id"]: o for o in self.attention["figures"][0]["algorithm_flow_plan"]["objects"]}
        self.assertEqual(objects["q"]["text_plan"]["mathematical_lines"], [])
        self.assertEqual(objects["q"]["text_plan"]["shape_once"], "N × d_k")
        self.assertEqual(objects["q"]["text_plan"]["caption_only_detail"], ["Query tensor"])
        self.assertEqual(objects["scores"]["text_plan"]["mathematical_lines"], ["S = QK^T"])
        self.assertEqual(objects["scores"]["text_plan"]["axis_lines"], ["contraction over d_k"])
        self.assertEqual(objects["softmax"]["text_plan"]["mathematical_lines"], ["P = softmax(Z)"])
        self.assertNotIn('"Query tensor"', self.attention["figures"][0]["prompt"])
        self.assertIn("DO NOT TYPESET this prose or add a footer", self.attention["figures"][0]["prompt"])

    def test_unowned_output_and_final_normalization_never_join_iteration_group(self):
        plan = self.online["figures"][0]["algorithm_flow_plan"]
        group = next(g for g in plan["groups"] if g["id"] == "g_iteration")
        self.assertEqual(group["member_node_ids"], ["scores", "online", "accumulate"])
        sources = {o["source_node_id"]: o["source_group"] for o in plan["objects"]}
        self.assertEqual(sources["normalize"], "")
        self.assertEqual(sources["output"], "")
        self.assertIn("Unowned outputs stay outside every source group", self.online["figures"][0]["prompt"])
        self.assertIn("Every shown boundary must stop before nonmembers", self.online["figures"][0]["prompt"])
        self.assertIn("thin enclosure when it clarifies the real iteration, residency or phase scope", self.online["figures"][0]["prompt"])

    def test_recurrence_exit_and_cardinality_derive_from_generic_graph_not_algorithm_names(self):
        spec = engine.normalize_spec({"title": "Arbitrary streaming state", "category": "algorithm", "nodes": [{"id": "s", "label": "Accumulator", "kind": "state"}, {"id": "f", "label": "Update", "kind": "compute"}, {"id": "d", "label": "Sample", "kind": "io"}], "edges": [{"source": "s", "target": "f", "kind": "data", "label": "old"}, {"source": "f", "target": "s", "kind": "data", "label": "new"}, {"source": "s", "target": "d", "kind": "data", "label": "every iteration"}]})
        plan = algorithm_flow.build(spec)
        exit = plan["motifs"]["recurrence_exits"][0]
        self.assertEqual(exit["label"], "every iteration")
        self.assertEqual(exit["source_edge_index"], 2)
        self.assertEqual(len(plan["relations"]), 3)
        self.assertEqual(sum(c["connector_count"] for c in plan["composition"]["connector_cardinality"]), 3)

    def test_algorithm_revision_uses_source_plan_without_demanding_missing_target_plate(self):
        result = engine.compile_manual({**fixture(), "feedback": "wrong dependency endpoint", "figure_id": "algorithm-flow"})
        self.assertEqual(result["figures"][0]["revision_mode"], "regenerate-from-source")
        self.assertIn("canonical source and current source-backed algorithm plan", result["edit_prompt"])
        self.assertIn("No target plate or guide image is required", result["edit_prompt"])
        self.assertNotIn("clean current target plate", result["edit_prompt"])


class AlgorithmMCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_prompt_only_mcp_returns_and_stores_full_plan_without_guide_image(self):
        raw = fixture()
        with tempfile.TemporaryDirectory() as temporary:
            async with Client(create_server(Path(temporary))) as client:
                result = await client.call_tool("silicon_compile", {"spec": raw["spec"], "settings": raw["settings"], "description": raw["description"]})
                self.assertFalse(result.is_error)
                data = result.structured_content
                self.assertIsNone(data["guide_role"])
                self.assertTrue(data["guide_optional"])
                self.assertIsNone(data["guide_uri"])
                self.assertIsNone(data["guide_path"])
                self.assertFalse(any(isinstance(item, ImageContent) for item in result.content))
                self.assertIn("prompt alone", data["next_step"])
                saved = await client.read_resource(next(f["brief_uri"] for f in data["figures"] if f["primary"]))
                brief = json.loads(saved.contents[0].text)
                self.assertEqual(brief["algorithm_flow_plan"], data["algorithm_flow_plan"])
                self.assertEqual(brief["visual_contract"], data["visual_contract"])
                self.assertEqual(data["visual_contract"]["family"], "algorithm")
                self.assertIsNone(brief["guide_role"])
                review = await client.call_tool("silicon_prepare_review", {"artifact_id": data["artifact_id"]})
                self.assertEqual(review.structured_content["review_task"]["objects"], data["algorithm_flow_plan"]["objects"])


if __name__ == "__main__":
    unittest.main()
