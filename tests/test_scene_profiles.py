"""Reader-purpose projections preserve source facts while changing the figure."""
import copy
import json
from pathlib import Path
import unittest

from silicon_canvas import engine, presentation, reading_plan, scene_profiles


ROOT = Path(__file__).resolve().parents[1]


def example(name):
    return json.loads((ROOT / "examples" / (name + ".json")).read_text(encoding="utf-8"))


def plan(data, scene):
    spec = engine.normalize_spec(data["spec"])
    settings = {**engine.normalize_settings(data.get("settings", {})), "scene": scene}
    settings["resolved_scene"] = scene_profiles.resolve(settings, data.get("description", ""), spec)["id"]
    return reading_plan.build(spec, settings, presentation.build_plan(spec, settings["density"], settings["language"]))


class SceneProfileTests(unittest.TestCase):
    def test_concept_scope_alone_does_not_request_material_rendering(self):
        descriptions = (
            "画一张简明的存储层级概念图，两个处理单元各有私有缓存，再连接共享缓存和片外存储，用于技术文档。",
            "Draw a logical system concept showing private resources and one shared service.",
            "画一张系统概念图，解释各模块归属和连接，不需要补实物外观。",
        )
        for category in ("architecture", "memory", "microarchitecture"):
            for description in descriptions:
                for scene in ("auto", "concept"):
                    settings = {"representation": "auto", "scene": scene, "resolved_scene": "concept", "category": category}
                    result = scene_profiles.resolve_representation(settings, description)
                    self.assertEqual(result["id"], "diagram", (category, scene, description))

    def test_natural_product_and_system_illustration_combinations_select_spatial_medium(self):
        settings = {"representation": "auto", "scene": "auto", "category": "architecture"}
        descriptions = (
            "希望是有空间感的产品技术插图，表现组件与外部连接。",
            "做一张系统展示插图，多个节点连接公共服务，保留空间组织。",
            "封装概念插图，解释内部部件和外部接口。",
            "A product technical illustration explaining the supplied component relationships.",
            "A system demonstration illustration with a common camera and readable labels.",
            "A technical product illustration with selected functional callouts.",
        )
        for description in descriptions:
            self.assertEqual(scene_profiles.resolve_representation(settings, description)["id"], "system_illustration", description)

    def test_medium_stays_independent_of_purpose_category_and_palette(self):
        for palette in engine.STYLES:
            for category in ("architecture", "memory", "microarchitecture"):
                settings = {"representation": "auto", "scene": "concept", "category": category, "style": palette}
                self.assertEqual(scene_profiles.resolve_representation(settings, "解释私有和共享资源的逻辑概念图")["id"], "diagram")
                self.assertEqual(scene_profiles.resolve_representation(settings, "商业产品摄影，重点展示材质和光照")["id"], "product_render")
                self.assertEqual(scene_profiles.resolve_representation(settings, "产品技术插图，展示内部组织")["id"], "system_illustration")

    def test_concept_scope_keeps_explicit_commercial_hero_and_material_requests(self):
        settings = {"representation": "auto", "scene": "concept", "category": "memory"}
        for description in ("用于发布的产品封面主视觉", "A studio product photograph, with soft light and a material finish.", "商业产品渲染图，展示完整外观"):
            self.assertEqual(scene_profiles.resolve_representation(settings, description)["id"], "product_render", description)
        self.assertEqual(scene_profiles.resolve_representation(settings, "用于 BP 的系统技术插图，说明主要部件的连接")["id"], "system_illustration")

    def test_excluded_illustration_and_render_words_do_not_override_technical_request(self):
        settings = {"representation": "auto", "scene": "concept", "category": "architecture"}
        for description in ("不要产品技术插图，只要层级关系概念图。", "Avoid product technical illustration; show logical dependency structure.", "不需要系统展示插图，也不要商业产品渲染，只说明资源归属。"):
            self.assertEqual(scene_profiles.resolve_representation(settings, description)["id"], "diagram", description)
        self.assertEqual(scene_profiles.resolve_representation(settings, "不要只做封面，要做系统展示插图，解释系统关系。")["id"], "system_illustration")

    def test_legacy_manual_and_behavioral_medium_boundaries_remain_intact(self):
        description = "产品技术插图，作为商业主视觉。"
        self.assertEqual(scene_profiles.resolve_representation({"scene": "concept"}, description)["id"], "diagram")
        self.assertEqual(scene_profiles.resolve_representation({"representation": "diagram", "scene": "concept"}, description)["id"], "diagram")
        self.assertEqual(scene_profiles.resolve_representation({"representation": "product_render", "scene": "concept"}, "逻辑概念图")["id"], "product_render")
        self.assertEqual(scene_profiles.resolve_representation({"representation": "system_illustration", "scene": "concept"}, "逻辑概念图")["id"], "system_illustration")
        for category in ("algorithm", "fsm", "pipeline", "timing"):
            self.assertEqual(scene_profiles.resolve_representation({"representation": "auto", "scene": "concept", "category": category}, description)["id"], "diagram")

    def test_assembled_cutaway_is_spatial_even_when_exploded_view_is_excluded(self):
        settings = {"representation": "auto", "scene": "auto", "category": "dataflow"}
        descriptions = (
            "用完整封装的局部剖切解释热量向上和信号向下的路线，保持装配状态，不要做爆炸图。",
            "Show a partial cutaway of an assembled package, not an exploded view.",
            "Cross-section of a package: die inside, lid above, substrate below.",
        )
        for description in descriptions:
            self.assertEqual(scene_profiles.resolve_representation(settings, description)["id"], "system_illustration", description)
        self.assertEqual(scene_profiles.resolve_representation(settings, "纯平面框图，不要局部剖切。")['id'], "diagram")
        self.assertEqual(scene_profiles.resolve_representation(settings, "不要剖面图，不要爆炸图，只画数据路径。")['id'], "diagram")

    def test_business_explanations_choose_information_while_explicit_covers_keep_hero_medium(self):
        settings = {"representation": "auto", "scene": "auto", "category": "architecture"}
        self.assertEqual(scene_profiles.resolve_representation(settings, "用商业渲染给BP讲解SoC架构，展示计算子系统、片上互联和存储路径。")['id'], "system_illustration")
        self.assertEqual(scene_profiles.resolve_representation(settings, "SoC商业封面主视觉，无文字。")['id'], "product_render")
        self.assertEqual(scene_profiles.resolve_representation(settings, "不要只做封面，要展示内部架构和功能分区，用商业渲染讲解。")['id'], "system_illustration")
        self.assertEqual(scene_profiles.resolve_representation(settings, "纯平面框图，给BP解释内部架构。")['id'], "diagram")
    def test_legacy_settings_remain_unchanged_and_derived_scene_is_not_imported(self):
        legacy = engine.normalize_settings({"style": "blueprint"})
        self.assertNotIn("scene", legacy)
        self.assertIsNone(scene_profiles.resolve(legacy, "BP 产品图"))
        settings = engine.normalize_settings({"scene": "auto", "resolved_scene": "detail"})
        self.assertNotIn("resolved_scene", settings)
        self.assertEqual(scene_profiles.resolve(settings, "用于 BP，展示完整芯片产品")['id'], "concept")
        with self.assertRaises(ValueError):
            engine.normalize_settings({"scene": "futuristic"})

    def test_auto_scene_infers_business_and_process_intents_without_palette_binding(self):
        for palette in engine.STYLES:
            settings = engine.normalize_settings({"style": palette, "scene": "auto"})
            self.assertEqual(scene_profiles.resolve(settings, "投资人 BP 中介绍整体芯片")['id'], "concept")
            self.assertEqual(scene_profiles.resolve(settings, "解释算子数据流")['id'], "flow")
            self.assertEqual(scene_profiles.resolve(settings, "设计评审中的内部细节")['id'], "detail")
            self.assertEqual(scene_profiles.resolve(settings, "完整 SoC 系统")['id'], "system")

    def test_same_gpu_has_four_different_semantic_reading_plans(self):
        data = example("gpu")
        before = copy.deepcopy(data)
        plans = {scene: plan(data, scene) for scene in scene_profiles.PROFILES}
        concept, system, flow, detail = (plans[key]["figures"][0] for key in ("concept", "system", "flow", "detail"))
        self.assertEqual(concept["design_contract"]["grammar"], "product-concept")
        self.assertTrue(all(not node["children"] for node in concept["macro_nodes"]))
        self.assertTrue(any(node["children"] for node in system["macro_nodes"]))
        self.assertEqual(flow["design_contract"]["grammar"], "exact-flow")
        self.assertTrue(all(edge["kind"] in {"data", "relation"} for edge in flow["macro_edges"]))
        self.assertEqual(flow["design_contract"]["preferred_reading_direction"], "left-to-right")
        self.assertFalse(detail["abstract"])
        self.assertLess(len(detail["node_ids"]), len(data["spec"]["nodes"]))
        self.assertTrue(detail.get("main_group"))
        self.assertFalse(flow["projection"]["folded_groups"])
        self.assertFalse(flow["projection"]["internal_edges"])
        self.assertEqual(data, before)
        source = engine.normalize_spec(data["spec"])
        for scene, result in plans.items():
            self.assertEqual(result["reading_plan"]["source_hash"], reading_plan.source_hash(source))
            exact = [i for figure in result["figures"] if not figure["abstract"] for i in figure["edge_indices"]]
            self.assertCountEqual(exact, range(len(source["edges"])))
            self.assertEqual(result["figures"][0]["design_contract"]["scene_id"], scene)

    def test_concept_represents_isolated_support_and_explicit_external_ownership(self):
        data = example("soc")
        primary = plan(data, "concept")["figures"][0]
        ids = {node["id"] for node in data["spec"]["nodes"]}
        mapping = primary["projection"]["source_node_to_macro"]
        self.assertEqual(set(mapping), ids)
        external = {node["id"] for node in primary["macro_nodes"] if node["external"]}
        self.assertEqual(external, set(primary["concept_frame"]["external_ids"]))
        self.assertTrue(external)
        self.assertFalse(primary["concept_frame"]["physical_boundary"])
        represented = {member for node in primary["macro_nodes"] for member in node["members"]}
        self.assertEqual(represented, ids)
        painted = {i for edge in primary["macro_edges"] for i in edge["members"]}
        deferred = {entry["index"] for entry in primary["projection"]["deferred_edges"]}
        self.assertEqual(painted | deferred, set(range(len(data["spec"]["edges"]))))
        self.assertFalse(painted & deferred)
        self.assertNotIn("n_memctl", external)

    def test_external_destination_does_not_move_its_controller_off_chip(self):
        groups = {"memory": {"id": "memory", "label": "Off-Chip / DRAM Interface", "parent": ""}}
        controller = {"id": "mc", "label": "DRAM Controller", "kind": "control", "group": "memory"}
        for detail in ("External memory interface", "Links to external DRAM", "Connects to off-chip HBM", "连接片外 DRAM", "访问外部内存"):
            self.assertFalse(reading_plan._external_node({**controller, "detail": detail}, groups), detail)
        dram = {"id": "dram", "label": "External DRAM", "kind": "memory", "group": "memory", "detail": "Off-chip main memory"}
        self.assertTrue(reading_plan._external_node(dram, groups))
        self.assertFalse(reading_plan._external_node({"id": "hi", "label": "Host Interface", "kind": "io", "group": "memory", "detail": "Connects to the external host"}, groups))
        self.assertTrue(reading_plan._external_node({**controller, "detail": "This controller is located outside the chip."}, groups))
        source = {"title": "Device", "summary": "", "category": "architecture", "groups": list(groups.values()),
                  "nodes": [{**controller, "detail": "External memory interface"}, dram],
                  "edges": [{"source": "mc", "target": "dram", "kind": "data", "label": "payload"}],
                  "steps": [], "annotations": [], "assumptions": [], "questions": [], "checks": []}
        primary = plan({"spec": source}, "concept")["figures"][0]
        self.assertEqual(primary["concept_frame"]["external_ids"], ["dram"])
        self.assertIn("mc", primary["concept_frame"]["member_ids"])

    def test_concept_does_not_invent_wiring_when_only_inventory_is_supplied(self):
        data = example("soc")
        data["spec"]["edges"] = []
        primary = plan(data, "concept")["figures"][0]
        self.assertEqual(primary["macro_edges"], [])
        self.assertEqual(primary["source_edge_indices"], [])
        self.assertEqual(len(primary["projection"]["source_node_to_macro"]), len(data["spec"]["nodes"]))

    def test_exact_numeric_conditions_survive_a_boundary_summary(self):
        data = example("gpu")
        for edge in data["spec"]["edges"]:
            if edge["source"] == "n_disp":
                edge["label"] = "workgroups x4"
        primary = plan(data, "concept")["figures"][0]
        for edge in primary["macro_edges"]:
            for index in edge["members"]:
                original = data["spec"]["edges"][index]
                if "x4" in original["label"]:
                    self.assertIn(original["label"], edge["label"])
        self.assertIn("Compute Cluster (x4)", [node["label"] for node in primary["macro_nodes"]])

    def test_behavioral_concept_retains_state_grammar_and_has_no_chip_frame(self):
        source = {"title": "Controller", "summary": "", "category": "fsm", "groups": [],
                  "nodes": [{"id": "a", "label": "IDLE", "kind": "state"}, {"id": "b", "label": "RUN", "kind": "state"}],
                  "edges": [{"source": "a", "target": "b", "kind": "control", "label": "start"}],
                  "steps": [], "annotations": [], "assumptions": [], "questions": [], "checks": []}
        primary = plan({"spec": source}, "concept")["figures"][0]
        self.assertEqual(primary["design_contract"]["grammar"], "state-machine")
        self.assertEqual(primary["semantic_grammar"], "state-machine")
        self.assertNotIn("concept_frame", primary)
        self.assertFalse(primary["abstract"])

    def test_flow_includes_explicit_return_payload_but_defers_ready_feedback(self):
        source = {"title": "Read lifecycle", "summary": "", "category": "dataflow", "groups": [],
                  "nodes": [{"id": "request", "label": "Requester", "kind": "compute"},
                            {"id": "memory", "label": "Memory", "kind": "memory"},
                            {"id": "sink", "label": "Output", "kind": "io"}],
                  "edges": [{"source": "request", "target": "memory", "kind": "data", "label": "read"},
                            {"source": "memory", "target": "sink", "kind": "feedback", "label": "resp", "rationale": "返回读取的数据负载", "evidence": "返回数据"},
                            {"source": "memory", "target": "request", "kind": "feedback", "label": "ready", "rationale": "就绪控制反馈"}],
                  "steps": [], "annotations": [], "assumptions": [], "questions": [], "checks": []}
        before = engine.normalize_spec(source)
        primary_plan = plan({"spec": source}, "flow")
        primary = primary_plan["figures"][0]
        self.assertEqual(primary["source_edge_indices"], [0, 1])
        self.assertTrue(any(edge["kind"] == "feedback" and edge["members"] == [1] for edge in primary["macro_edges"]))
        self.assertEqual([entry["index"] for entry in primary["projection"]["deferred_edges"]], [2])
        self.assertEqual(primary_plan["reading_plan"]["source_hash"], reading_plan.source_hash(before))
        self.assertEqual(engine.normalize_spec(source), before)
        exact = [index for figure in primary_plan["figures"] if not figure["abstract"] for index in figure["edge_indices"]]
        self.assertCountEqual(exact, [0, 1, 2])

    def test_prepare_communicates_reader_purpose_without_truncating_canonical_source(self):
        messages, context = engine.prepare_request({"scene": "auto", "description": "BP 用完整 GPU 概念图"})
        user = json.loads(messages[1]["content"])
        self.assertEqual(user["reader_purpose"]["id"], "concept")
        self.assertIn("complete useful canonical source specification", messages[0]["content"])
        self.assertEqual(context["settings"]["scene"], "auto")


if __name__ == "__main__":
    unittest.main()
