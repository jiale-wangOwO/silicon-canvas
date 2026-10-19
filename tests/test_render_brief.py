"""Rendering is art direction over an immutable engineering ledger."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from silicon_canvas import engine, publication_layout, render_brief, scene_profiles

ROOT = Path(__file__).resolve().parents[1]


def source(name="soc"):
    return json.loads((ROOT / "examples" / (name + ".json")).read_text(encoding="utf-8"))


def compile_as(representation="product_render", description="用于 BP 的商业渲染图", scene="concept"):
    payload = source()
    payload["settings"] = {**payload["settings"], "representation": representation, "scene": scene}
    payload["description"] = description
    return engine.compile_manual(payload)


class RepresentationTests(unittest.TestCase):
    def test_saved_projects_without_representation_preserve_diagram_contract(self):
        settings = engine.normalize_settings({"scene": "concept", "resolved_representation": "product_render"})
        self.assertNotIn("resolved_representation", settings)
        self.assertNotIn("representation", settings)
        self.assertEqual(scene_profiles.resolve_representation(settings, "商业渲染图")["id"], "diagram")

    def test_auto_infers_representation_independently_of_palette_and_purpose(self):
        for palette in engine.STYLES:
            settings = {"representation": "auto", "scene": "system", "style": palette}
            self.assertEqual(scene_profiles.resolve_representation(settings, "BP 中展示芯片，有质感的产品摄影")["id"], "product_render")
            self.assertEqual(scene_profiles.resolve_representation(settings, "技术剖视插画说明系统工作原理")["id"], "system_illustration")
            self.assertEqual(scene_profiles.resolve_representation(settings, "干净的空间系统示意，适度三维感")["id"], "system_illustration")
            self.assertEqual(scene_profiles.resolve_representation(settings, "展示 SoC 子系统和 DDR 数据接口")["id"], "diagram")
            self.assertEqual(scene_profiles.resolve_representation(settings, "BP 使用纯框图，不要渲染")["id"], "diagram")
        self.assertEqual(scene_profiles.resolve_representation({"representation": "auto", "category": "dataflow"}, "讲解缓冲与计算的数据流概念")["id"], "diagram")

    def test_explicit_choice_wins_auto_but_behavioral_notation_stays_exact(self):
        self.assertEqual(scene_profiles.resolve_representation({"representation": "diagram"}, "商业渲染")["id"], "diagram")
        self.assertEqual(scene_profiles.resolve_representation({"representation": "product_render", "category": "fsm"}, "状态转换")["id"], "diagram")
        with self.assertRaises(ValueError):
            engine.normalize_settings({"representation": "photograph"})

    def test_prepare_requests_complete_source_and_does_not_bind_material_to_model(self):
        messages, context = engine.prepare_request({"description": "BP 用完整 SoC 商业渲染图", "representation": "auto", "scene": "auto"})
        request = json.loads(messages[1]["content"])
        self.assertEqual(request["representation_intent"]["id"], "product_render")
        self.assertIn("COMPLETE engineering ledger", messages[0]["content"])
        self.assertIn("logical CPU/GPU/NPU region is not a separate physical die", messages[0]["content"])
        self.assertEqual(context["settings"]["representation"], "auto")


class RenderBriefTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.product = compile_as()
        cls.illustration = compile_as("system_illustration", "系统技术插画，说明整个芯片的原理", "system")

    def test_render_has_separate_art_direction_and_bypasses_exact_target_geometry(self):
        figure = self.product["figures"][0]
        self.assertEqual(figure["layout_strategy"], "art-directed-render")
        self.assertFalse(figure["requires_layout_guide"])
        self.assertTrue(figure["composition_guide_optional"])
        self.assertNotIn("structure_layout", figure)
        self.assertNotIn("layout_scene", figure)
        self.assertEqual(figure["generation_inputs"][0]["role"], "composition_reference")
        self.assertTrue(figure["generation_inputs"][0]["optional"])
        for key in ("camera", "materials", "lighting", "background", "composition", "detail", "labels"):
            self.assertIn(key, figure["render_brief"]["art_direction"])
        self.assertIn("Materials:", figure["prompt"])
        self.assertIn("one camera and lighting system", figure["prompt"])
        self.assertNotIn("Make a clean faithful redraw", figure["prompt"])
        self.assertNotIn("No gradients, shadows", figure["prompt"])

    def test_source_facts_are_not_reinterpreted_as_physical_chiplets_or_tiles(self):
        figure = self.product["figures"][0]
        self.assertEqual(figure["macro_nodes"], [])
        self.assertEqual(figure["macro_edges"], [])
        self.assertEqual(figure["render_brief"]["subject"]["kind"], "generic_package_concept")
        self.assertEqual(figure["render_brief"]["appearance"]["known"], [])
        self.assertIn("die count", figure["render_brief"]["appearance"]["unknown"])
        visible = figure["render_brief"]["visible_content"]
        selected = {index for relationship in visible["relationships"] for index in relationship["source_edge_indices"]}
        self.assertTrue(selected, "a source with external interfaces deserves an explanatory image")
        self.assertEqual([edge["index"] for edge in figure["render_brief"]["semantic_contract"]["source_relations"] if edge["visible_requirement"]], sorted(selected))
        self.assertIn("not proof of separate dies", " ".join(figure["render_brief"]["semantic_contract"]["non_claims"]))

    def test_purpose_selects_visible_detail_independently_of_rendering_medium(self):
        hero = compile_as(description="产品封面主视觉，不要文字")
        functional = compile_as("system_illustration", "系统技术插画，解释内部功能分区和互联", "system")
        product, illustration = (result["figures"][0] for result in (hero, functional))
        self.assertEqual(self.product["source_hash"], self.illustration["source_hash"])
        self.assertEqual(self.product["spec"], self.illustration["spec"])
        self.assertEqual(hero["source_hash"], functional["source_hash"])
        self.assertNotEqual(product["render_brief"]["art_direction"]["detail"], illustration["render_brief"]["art_direction"]["detail"])
        self.assertEqual(product["render_brief"]["visible_content"]["regions"], [])
        self.assertTrue(illustration["render_brief"]["visible_content"]["regions"])
        self.assertTrue(illustration["render_brief"]["visible_content"]["relationships"])
        steps = illustration["generation_steps"]
        self.assertFalse(illustration["render_brief"]["workflow"]["recommended"])
        self.assertEqual([step["operation"] for step in steps], ["generate"])
        self.assertEqual(steps[0]["id"], "complete")
        self.assertNotIn('"source_relations":', steps[0]["prompt"])
        self.assertIn("CPU Cluster", steps[0]["prompt"])
        self.assertIn("On-Chip Interconnect", steps[0]["prompt"])
        self.assertNotIn('"source_relations":', illustration["prompt"])
        self.assertEqual(len(illustration["render_brief"]["semantic_contract"]["source_relations"]), len(functional["spec"]["edges"]))

    def test_all_original_nodes_and_relations_have_metadata_caption_and_exact_companion_coverage(self):
        result = self.product
        primary = result["figures"][0]
        semantic = primary["render_brief"]["semantic_contract"]
        self.assertCountEqual([node["id"] for node in semantic["known_facts"] + semantic["assumed_facts"]], [node["id"] for node in result["spec"]["nodes"]])
        self.assertEqual(len(semantic["source_relations"]), len(result["spec"]["edges"]))
        for node in result["spec"]["nodes"]:
            self.assertIn(node["label"], primary["caption"])
        exact = [index for figure in result["figures"] if not figure["abstract"] for index in figure["edge_indices"]]
        self.assertCountEqual(set(exact), range(len(result["spec"]["edges"])))
        self.assertTrue(all(figure["representation"] == "diagram" for figure in result["figures"][1:]))

    def test_user_camera_background_and_physical_input_override_generic_appearance(self):
        result = compile_as(description="产品使用陶瓷盖板。商业渲染，深色背景，等距视角。")
        brief = result["figures"][0]["render_brief"]
        self.assertIn("陶瓷盖板", brief["appearance"]["known"][0]["statement"])
        self.assertIn("isometric", brief["art_direction"]["camera"])
        self.assertIn("dark charcoal", brief["art_direction"]["background"])
        self.assertIn("User art direction takes precedence", result["prompt"])
        self.assertEqual(brief["source_hash"], self.product["source_hash"])
        self.assertFalse(brief["appearance"]["known"][0]["verified"])
        wished = render_brief.build(result["spec"], result["figures"][0], result["settings"], "我想要陶瓷风格、金属质感的封装。")
        self.assertEqual(wished["appearance"]["known"], [])
        self.assertFalse(wished["appearance"]["visual_requests"][0]["engineering_fact"])

    def test_complete_system_is_not_forced_into_one_chip_and_negative_keywords_do_not_select_subjects(self):
        spec = self.product["spec"]
        figure = render_brief.primary(spec, "system_illustration")
        brief = render_brief.build(spec, figure, self.product["settings"], "主机通过 PCIe 连接四块 GPU 加速卡，每卡本地 HBM，通过高速互联连接。")
        self.assertEqual(brief["subject"]["kind"], "system_assembly_concept")
        self.assertIn("四块", brief["user_intent"]["description"])
        self.assertIn("actual source objects", brief["art_direction"]["composition"])
        generic = render_brief.build(spec, figure, self.product["settings"], "芯片商业渲染。不要画 PCB 或裸片，也不要加 HBM。")
        self.assertEqual(generic["subject"]["kind"], "generic_package_concept")
        negative = render_brief.build(spec, figure, self.product["settings"], "功能覆盖是非物理的原理示意，不是裸片或真实封装结构。")
        self.assertEqual(negative["subject"]["kind"], "generic_package_concept")
        self.assertEqual(negative["appearance"]["known"], [])
        self.assertTrue(negative["appearance"]["physical_constraints"])
        background = render_brief.build(spec, figure, self.product["settings"], "不要白色背景，也不要深色背景。")
        self.assertIn("mid-tone", background["art_direction"]["background"])

    def test_negated_camera_background_and_material_keywords_never_select_that_default(self):
        spec = self.product["spec"]
        figure = render_brief.primary(spec, "product_render")
        brief = render_brief.build(spec, figure, self.product["settings"], "商业渲染。不要俯视，不要深色背景，不要金属质感。")
        art = brief["art_direction"]
        self.assertIn("near-level", art["camera"])
        self.assertNotIn("restrained top-down camera", art["camera"])
        self.assertNotIn("dark charcoal", art["background"])
        self.assertTrue(art["exclusions"]["top_down"])
        self.assertTrue(art["exclusions"]["dark_background"])
        self.assertNotIn("satin metal", art["materials"])
        alternative = render_brief.build(spec, figure, self.product["settings"], "用等距相机，但不要俯视。不要白色背景。")
        self.assertIn("isometric camera", alternative["art_direction"]["camera"])
        self.assertIn("dark charcoal", alternative["art_direction"]["background"])
        excluded = render_brief.build(spec, figure, self.product["settings"], "No isometric camera. No top-down view. No dark background.")
        self.assertIn("near-level", excluded["art_direction"]["camera"])
        self.assertNotIn("dark charcoal", excluded["art_direction"]["background"])

    def test_transparent_request_is_an_output_hint_not_an_engineering_fact(self):
        spec = self.product["spec"]
        figure = render_brief.primary(spec, "product_render")
        requested = render_brief.build(spec, figure, self.product["settings"], "产品渲染，透明背景。")
        self.assertTrue(requested["art_direction"]["transparent_background"])
        self.assertEqual(requested["appearance"]["known"], [])
        excluded = render_brief.build(spec, figure, self.product["settings"], "产品渲染，不要透明背景。")
        self.assertFalse(excluded["art_direction"]["transparent_background"])

    def test_precise_layout_builder_is_never_called_for_art_directed_main(self):
        seen = []
        original = publication_layout.build
        def observe(spec, figure, settings):
            seen.append(figure["id"])
            return original(spec, figure, settings)
        with patch.object(publication_layout, "build", side_effect=observe):
            result = compile_as()
        self.assertNotIn(result["figures"][0]["id"], seen)
        self.assertTrue(seen, "technical companions still use the exact diagram compiler")

    def test_exported_contract_never_claims_a_generated_bitmap_passed_review(self):
        figure = self.product["figures"][0]
        self.assertEqual(figure["render_contract"]["actual_image_status"], "not_reviewed")
        self.assertEqual(figure["render_contract"]["appearance_status"], "illustrative_unverified")
        self.assertEqual(figure["render_contract"]["source_hash"], self.product["source_hash"])
        self.assertEqual(self.product["settings"]["resolved_representation"], "product_render")

    def test_staged_prompts_keep_freeform_framing_and_latest_visual_feedback_without_new_facts(self):
        result = engine.compile_result(self.product["spec"], {**self.product["settings"], "representation": "system_illustration"},
                                       description="主体放在画面右侧，左侧给介绍文案。深色背景。",
                                       feedback="改成浅色背景，不要俯视，不加说明。四个HBM不是已知产品条件。")
        brief = result["figures"][0]["render_brief"]
        self.assertEqual(result["source_hash"], self.product["source_hash"])
        self.assertIn("light neutral", brief["art_direction"]["background"])
        self.assertIn("near-level", brief["art_direction"]["camera"])
        self.assertTrue(brief["art_direction"]["exclusions"]["top_down"])
        self.assertFalse(brief["workflow"]["recommended"])
        self.assertEqual(brief["appearance"]["known"], [])
        for step in brief["workflow"]["steps"]:
            self.assertIn("主体放在画面右侧", step["prompt"])
            self.assertIn("改成浅色背景", step["prompt"])
        self.assertEqual([step["id"] for step in brief["workflow"]["steps"]], ["complete"])
        self.assertIn("Text-free artwork", brief["workflow"]["steps"][0]["prompt"])

    def test_business_intent_with_structured_source_is_explanatory_and_single_pass(self):
        figure = self.product["figures"][0]
        brief = figure["render_brief"]
        self.assertEqual(brief["explanation_plan"]["mode"], "annotated_context")
        self.assertTrue(brief["visible_content"]["regions"])
        self.assertEqual(brief["workflow"]["mode"], "single_pass")
        self.assertEqual([step["id"] for step in brief["workflow"]["steps"]], ["complete"])
        self.assertIn("CPU Cluster", figure["prompt"])
        self.assertIn("External DRAM", figure["prompt"])
        self.assertNotIn("No boxes, panels, arrows, buses, cables", figure["prompt"])
        self.assertNotIn("not a graph, die floorplan or container", figure["projection"]["meaning"])

    def test_preserving_package_exterior_keeps_context_explanation_despite_interconnect_keyword(self):
        spec = self.product["spec"]
        figure = render_brief.primary(spec, "system_illustration")
        description = "画一张 SoC 系统方案的商业渲染示意图。保留整颗芯片封装外观，同时说明计算、存储、互联与系统管理能力，并展示片外 DRAM、主机和输入输出的上下文关系。外围可以用简单的器件和接口符号表现，不需要精确封装或线缆细节。"
        brief = render_brief.build(spec, figure, self.product["settings"], description)
        self.assertEqual(brief["explanation_plan"]["mode"], "annotated_context")
        self.assertTrue(brief["visible_content"]["regions"])
        self.assertTrue(brief["visible_content"]["context_objects"])
        self.assertTrue(brief["visible_content"]["interface_symbols"])
        self.assertEqual(brief["subject"]["kind"], "generic_package_concept")

    def test_functional_projection_is_traceable_and_keeps_all_source_facts(self):
        frozen = copy.deepcopy(self.product["spec"])
        figure = render_brief.primary(frozen, "product_render")
        brief = render_brief.build(frozen, figure, self.product["settings"], "用于 BP 的内部功能分区和共享互联概念图")
        visible = brief["visible_content"]
        self.assertEqual(brief["explanation_plan"]["mode"], "functional_cutaway")
        self.assertEqual(frozen, self.product["spec"])
        projected = {item["id"]: set(item["source_node_ids"]) for item in visible["regions"] + visible["context_objects"]}
        selected_indices = set()
        for relation in visible["relationships"]:
            self.assertEqual(len(relation["source_edge_indices"]), len(relation["source_node_pairs"]))
            for index, pair in zip(relation["source_edge_indices"], relation["source_node_pairs"]):
                edge = frozen["edges"][index]
                self.assertEqual(pair, [edge["source"], edge["target"]])
                self.assertIn(edge["source"], projected[relation["source"]])
                self.assertIn(edge["target"], projected[relation["target"]])
                self.assertIn(edge["kind"], relation["kinds"])
                if edge["label"]:
                    self.assertIn(edge["label"], relation["labels"])
                selected_indices.add(index)
        self.assertTrue(selected_indices)
        self.assertEqual(len(brief["semantic_contract"]["source_relations"]), len(frozen["edges"]))
        self.assertEqual({item["index"] for item in brief["semantic_contract"]["source_relations"] if item["visible_requirement"]}, selected_indices)
        self.assertIn("not a physical BOM", visible["physical_object_policy"])

    def test_context_and_interface_symbols_come_from_source_roles_not_invented_bom(self):
        spec = copy.deepcopy(self.product["spec"])
        figure = render_brief.primary(spec, "system_illustration")
        brief = render_brief.build(spec, figure, self.product["settings"], "完整封装带外围器件示意和能力标注")
        visible = brief["visible_content"]
        self.assertEqual(brief["explanation_plan"]["mode"], "annotated_context")
        self.assertEqual({item["label"] for item in visible["context_objects"]}, {"External DRAM", "Host / External Device"})
        self.assertIn("UART / SPI / I2C / GPIO", [item["label"] for item in visible["interface_symbols"]])
        for symbol in visible["interface_symbols"]:
            node = next(node for node in spec["nodes"] if node["id"] == symbol["source_node_ids"][0])
            for protocol in symbol["label"].split(" / "):
                self.assertIn(protocol, node["detail"])
        no_context = copy.deepcopy(spec)
        external = {node_id for item in visible["context_objects"] for node_id in item["source_node_ids"]}
        no_context["nodes"] = [node for node in no_context["nodes"] if node["id"] not in external]
        no_context["edges"] = [edge for edge in no_context["edges"] if edge["source"] not in external and edge["target"] not in external]
        no_context_brief = render_brief.build(no_context, figure, self.product["settings"], "商业图，带一点外部设备感")
        self.assertEqual(no_context_brief["visible_content"]["context_objects"], [])

    def test_interface_destination_never_moves_the_controller_outside_chip(self):
        spec = copy.deepcopy(self.product["spec"])
        for node in spec["nodes"]:
            if node["id"] == "n_memctl":
                node["detail"] = "External memory interface; connects to external DRAM"
        figure = render_brief.primary(spec, "system_illustration")
        brief = render_brief.build(spec, figure, self.product["settings"], "内部功能概念图")
        self.assertNotIn("n_memctl", [node_id for item in brief["visible_content"]["context_objects"] for node_id in item["source_node_ids"]])
        memory = next(item for item in brief["visible_content"]["regions"] if item["label"] == "Memory Subsystem")
        self.assertIn("n_memctl", memory["source_node_ids"])
        self.assertNotIn("n_dram", memory["source_node_ids"])

    def test_gpu_logical_multiplicity_is_preserved_without_becoming_die_quantity(self):
        spec = source("gpu")["spec"]
        figure = render_brief.primary(spec, "system_illustration")
        prompt = render_brief.compile_figure(figure, spec, self.product["settings"], "GPU 内部功能分区用于商业介绍")
        cluster = next(region for region in figure["render_brief"]["visible_content"]["regions"] if "Cluster" in region["label"])
        self.assertIn("x4", cluster["label"])
        self.assertEqual(set(cluster["members"]), {"Warp Scheduler", "SIMD Unit", "Tensor Unit", "On-Chip Storage"})
        self.assertIn("Compute Cluster (x4)", prompt)
        self.assertEqual(figure["render_brief"]["appearance"]["known"], [])
        self.assertIn("not proof of separate dies", " ".join(figure["render_brief"]["semantic_contract"]["non_claims"]))
        self.assertIn("not a measured floorplan", prompt)

    def test_latest_feedback_changes_explanation_and_exported_steps_without_new_source_facts(self):
        spec = copy.deepcopy(self.product["spec"])
        figure = render_brief.primary(spec, "system_illustration")
        prompt = render_brief.compile_figure(figure, spec, self.product["settings"], "芯片封面主视觉，无文字，深色背景", visual_feedback="改成内部功能分区讲解，显示标签，浅色背景。")
        brief = figure["render_brief"]
        self.assertEqual(brief["explanation_plan"]["mode"], "functional_cutaway")
        self.assertFalse(brief["visible_content"]["no_optional_text"])
        self.assertIn("light neutral", brief["art_direction"]["background"])
        self.assertEqual(prompt, figure["generation_steps"][0]["prompt"])
        self.assertIn("改成内部功能分区讲解", prompt)
        self.assertEqual(brief["appearance"]["known"], [])
        self.assertEqual(spec, self.product["spec"])
        alternate = render_brief.build(spec, figure, self.product["settings"], "内部剖视解释", visual_feedback="不要剖视，用完整封装带引线标注。")
        self.assertEqual(alternate["explanation_plan"]["mode"], "annotated_context")

    def test_optional_edit_preserves_the_full_explanation_instead_of_starting_with_empty_shell(self):
        spec = self.product["spec"]
        figure = render_brief.primary(spec, "system_illustration")
        render_brief.compile_figure(figure, spec, self.product["settings"], "内部功能区和互联讲解，分步生成再精修。")
        brief = figure["render_brief"]
        self.assertEqual(brief["workflow"]["mode"], "staged")
        self.assertTrue(brief["workflow"]["recommended"])
        complete, refine = brief["workflow"]["steps"]
        self.assertEqual([complete["operation"], refine["operation"]], ["generate", "edit"])
        self.assertEqual(refine["input_from"], "complete")
        self.assertIn("CPU Cluster", complete["prompt"])
        self.assertIn("On-Chip Interconnect", complete["prompt"])
        self.assertIn("actual generated product image", refine["prompt"])
        self.assertIn("CPU Cluster", refine["prompt"])

    def test_explanatory_mode_override_is_independent_of_representation(self):
        spec = self.product["spec"]
        for representation in ("product_render", "system_illustration"):
            figure = render_brief.primary(spec, representation)
            for mode in ("hero", "annotated_context", "functional_cutaway", "assembly"):
                brief = render_brief.build(spec, figure, {**self.product["settings"], "explanatory_mode": mode}, "商业展示")
                self.assertEqual(brief["explanation_plan"]["mode"], mode)
                self.assertEqual(brief["source_hash"], self.product["source_hash"])

    def test_overview_avoids_secondary_controls_but_preserves_selected_payload_directions(self):
        spec = self.product["spec"]
        figure = render_brief.primary(spec, "system_illustration")
        prompt = render_brief.compile_figure(figure, spec, self.product["settings"], "内部功能分区与互联，展示 SoC 整体组织")
        brief = figure["render_brief"]
        self.assertFalse(brief["visible_content"]["relationship_portrayal"]["directed_traffic"])
        selected = {index for relation in brief["visible_content"]["relationships"] for index in relation["source_edge_indices"]}
        self.assertNotIn(13, selected, "peripheral DMA request is a secondary control signal")
        self.assertFalse(any(spec["edges"][index]["kind"] in {"clock", "control"} for index in selected))
        self.assertIn("discreet small target arrowheads", prompt)
        self.assertIn("Memory Subsystem -> External DRAM", prompt)
        self.assertNotIn("Memory Subsystem ~ External DRAM", prompt)

    def test_directional_traffic_request_and_explicit_control_request_select_different_link_scope(self):
        spec = self.product["spec"]
        figure = render_brief.primary(spec, "system_illustration")
        prompt = render_brief.compile_figure(figure, spec, self.product["settings"], "内部功能区，加上数据流方向箭头以及控制路径。")
        brief = figure["render_brief"]
        self.assertTrue(brief["visible_content"]["relationship_portrayal"]["directed_traffic"])
        self.assertTrue(brief["visible_content"]["relationship_portrayal"]["control_detail"])
        self.assertIn("Memory Subsystem -> External DRAM", prompt)
        self.assertIn("Use listed source directions", prompt)
        self.assertTrue(any("control" in relation["kinds"] or "clock" in relation["kinds"] for relation in brief["visible_content"]["relationships"]))

    def test_compound_source_names_remain_quoted_members_and_overlays_have_one_base(self):
        figure = render_brief.primary(self.product["spec"], "system_illustration")
        prompt = render_brief.compile_figure(figure, self.product["spec"], self.product["settings"], "解释内部功能分区")
        self.assertIn('["CPU Cluster", "Accelerator / DSP", "DMA Engine"]', prompt)
        self.assertIn("Each quoted member is one source item", prompt)
        self.assertIn("single chip base", prompt)
        self.assertIn("flat, pale or subtly translucent", prompt)

    def test_external_context_intent_is_not_overridden_by_incidental_noc_fact(self):
        figure = render_brief.primary(self.product["spec"], "system_illustration")
        brief = render_brief.build(self.product["spec"], figure, self.product["settings"], "产品为主体，用周围标注说明计算、共享互联以及外部 DRAM 和主机关系。")
        self.assertEqual(brief["explanation_plan"]["mode"], "annotated_context")
        self.assertEqual({item["label"] for item in brief["visible_content"]["context_objects"]}, {"External DRAM", "Host / External Device"})

    def test_context_links_attach_to_source_authorized_internal_endpoints_without_shortcuts(self):
        figure = render_brief.primary(self.product["spec"], "system_illustration")
        prompt = render_brief.compile_figure(figure, self.product["spec"], self.product["settings"], "内部功能分区与互联")
        self.assertIn('Attach External DRAM only at the source-authorized internal role: Memory Subsystem at ["DRAM Controller"]', prompt)
        self.assertIn('Attach Host / External Device only at the source-authorized internal role: Peripheral & IO Subsystem at ["High-Speed IO"]', prompt)
        self.assertIn("not at a nearer central hub or unrelated region", prompt)
        self.assertIn("Routing instructions, not a text panel or legend", prompt)
        self.assertNotIn("[data]", prompt)
        self.assertNotIn("[feedback]", prompt)

    def test_context_has_one_copy_of_functions_neutral_glyphs_and_minimal_disclosure(self):
        figure = render_brief.primary(self.product["spec"], "system_illustration")
        prompt = render_brief.compile_figure(figure, self.product["spec"], self.product["settings"], "保留整颗芯片封装外观，周围标注功能和外部设备。")
        self.assertIn("one small representative neutral device silhouette or glyph per listed role", prompt)
        self.assertIn("without a second copy of its internal groups", prompt)
        self.assertIn("Interface links are nonemissive fine lines", prompt)
        self.assertIn("Do not add a marketing subtitle, slogan, tagline", prompt)
        self.assertIn("not add a marketing subtitle, slogan, tagline or a default 'Functional concept' badge", prompt)
        self.assertIn("protocol does not authorize inventing cameras, robots, watches", prompt)
        self.assertNotIn("Some displayed roles are generic assumptions", prompt)
        self.assertTrue(figure["render_brief"]["appearance"]["illustrative_assumptions"])

    def test_complete_gpu_subject_with_omitted_microstructure_still_uses_functional_cutaway(self):
        description = "给技术产品介绍做一张 GPU 的解释性渲染图：主机接口接命令处理器，任务分发到四个计算簇；每簇有 warp 调度、SIMD、张量单元与片上存储，各簇共享 L2，通过内存控制器访问外部显存。希望读者能看懂任务怎样进入、计算资源怎样组织、显存怎样连接。用一块完整的芯片主体承载有层次的逻辑功能分区和清楚的主路径，适度透视与克制的材质质感，关键标签保持水平易读；四个计算簇要看出重复关系，内部微结构不用全部展开。逻辑分区仅为解释概念，不当作真实 die 布局。"
        spec = source("gpu")["spec"]
        figure = render_brief.primary(spec, "system_illustration")
        brief = render_brief.build(spec, figure, self.product["settings"], description)
        self.assertEqual(brief["explanation_plan"]["mode"], "functional_cutaway")
        self.assertTrue(brief["visible_content"]["regions"])
        self.assertTrue(brief["visible_content"]["relationships"])


if __name__ == "__main__":
    unittest.main()
