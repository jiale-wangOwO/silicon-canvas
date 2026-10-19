"""Natural intent arbitration transfers across names, languages and settings."""
import copy
import json
from pathlib import Path
import unittest

from silicon_canvas import algorithm_flow, engine, render_brief, scene_profiles


ROOT = Path(__file__).resolve().parents[1]


class VisualIntentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = engine.normalize_spec(json.loads((ROOT / "examples/soc.json").read_text(encoding="utf-8"))["spec"])

    def mode(self, description, feedback="", settings=None):
        return render_brief._explanation_mode(description, feedback, settings or {}, "generic_package_concept", self.spec)[0]

    def test_english_and_chinese_choose_message_before_exterior_decoration(self):
        cases = [
            ("For an executive presentation, keep the intact chip exterior with capability callouts and external host context.", "annotated_context"),
            ("For a product introduction, show an internal logical function-region cutaway and the shared interconnect.", "functional_cutaway"),
            ("A product launch cover hero with quiet material and light. Do not show internal functional regions.", "hero"),
            ("产品介绍，保留整颗芯片的封装外观，用外围引线说明能力与外部存储。", "annotated_context"),
            ("商业插画，展示内部逻辑功能分区与片上互联。", "functional_cutaway"),
            ("发布封面主视觉，只画产品外观，不展示内部功能分区。", "hero"),
        ]
        for description, expected in cases:
            with self.subTest(description=description):
                self.assertEqual(self.mode(description), expected)

    def test_commercial_holdout_descriptions_are_not_specific_title_triggers(self):
        for filename, expected in [("commercial-context", "annotated_context"),
                                   ("commercial-cutaway", "functional_cutaway"),
                                   ("commercial-hero", "hero")]:
            payload = json.loads((ROOT / "tests/fixtures/design_coverage" / (filename + ".json")).read_text(encoding="utf-8"))
            description = payload["description"]
            for subject in ("acquisition", "compression", "vision", "motion", "arbitrary"):
                with self.subTest(case=filename, subject=subject):
                    self.assertEqual(self.mode(description.replace("acquisition", subject)), expected)
            requested = {"representation": "auto", "scene": "auto", "category": "architecture"}
            representation = scene_profiles.resolve_representation(requested, description)["id"]
            self.assertEqual(representation, "product_render" if expected == "hero" else "system_illustration")

    def test_partial_product_intent_gets_informative_default_without_extra_fields(self):
        for description in ("数据采集系统用在产品介绍", "An acquisition system for a product introduction"):
            with self.subTest(description=description):
                settings = {"representation": "auto", "scene": "auto", "category": "architecture"}
                self.assertEqual(scene_profiles.resolve_representation(settings, description)["id"], "system_illustration")
                self.assertEqual(self.mode(description), "annotated_context")

    def test_no_internal_microstructure_does_not_cancel_functional_explanation(self):
        for description in ("功能分区和共享互联需要可见，内部微结构不用全部展开。",
                            "Reveal internal logical function regions, but do not expand every internal queue or register."):
            self.assertEqual(self.mode(description), "functional_cutaway")
        self.assertEqual(self.mode("功能分区和共享互联需要可见。", "不要展开内部微结构。"), "functional_cutaway")

    def test_negated_alternatives_do_not_select_the_rejected_medium_or_subject(self):
        settings = {"representation": "auto", "scene": "auto", "category": "architecture"}
        self.assertEqual(scene_profiles.resolve_representation(settings, "A block diagram, not a commercial product render.")["id"], "diagram")
        self.assertEqual(scene_profiles.resolve_representation(settings, "Not a flat diagram; use a product studio render.")["id"], "product_render")
        self.assertEqual(scene_profiles.resolve_representation(settings, "Not a cover; use a technical cutaway illustration.")["id"], "system_illustration")
        self.assertEqual(self.mode("Not just a cover: show internal functional regions."), "functional_cutaway")
        self.assertEqual(render_brief._subject_kind("Do not draw a PCB; use a bare die.", self.spec)[0], "bare_die_concept")
        self.assertEqual(render_brief._subject_kind("不要画晶圆或裸片，画通用芯片外观。", self.spec)[0], "generic_package_concept")

    def test_local_negation_preserves_unrelated_positive_requests(self):
        self.assertEqual(scene_profiles.visual_cue("No metallic finish, use a dark background without decorative lighting.", r"dark\s*background"), (True, False))
        self.assertEqual(scene_profiles.visual_cue("Use a dark background. No dark background.", r"dark\s*background"), (False, True))
        self.assertEqual(scene_profiles.visual_cue("No dark background. Use a dark background.", r"dark\s*background"), (True, False))
        self.assertEqual(scene_profiles.visual_cue("Do not hide internal functional regions.", r"internal\s*functional\s*regions"), (True, False))
        self.assertEqual(scene_profiles.visual_cue("Use a top-down view rather than an isometric view.", r"isometric"), (False, True))
        self.assertFalse(scene_profiles._positive_hero("Show recovery resources in the architecture explanation."))
        self.assertFalse(scene_profiles._positive_hero("Cover every supplied resource in the system diagram."))
        self.assertEqual(scene_profiles.visual_cue("A dark background is not wanted.", r"dark\s*background"), (False, True))
        self.assertEqual(scene_profiles.visual_cue("俯视不要，采用等距。", r"俯视"), (False, True))
        self.assertEqual(self.mode("A cover hero. Show no internal functional regions."), "hero")

    def test_latest_visual_feedback_selects_new_explanation_without_rewriting_facts(self):
        original = "Reveal internal function regions with shared interconnect on a dark background."
        self.assertEqual(self.mode(original, "Keep the intact exterior and use external capability callouts instead."), "annotated_context")
        self.assertEqual(self.mode(original, "Use a launch cover hero. No internal functional regions."), "hero")
        self.assertEqual(self.mode("Cover hero with no internal regions.", "Switch to a functional cutaway showing internal regions."), "functional_cutaway")
        before = copy.deepcopy(self.spec)
        figure = render_brief.primary(self.spec, "system_illustration")
        brief = render_brief.build(self.spec, figure, {"style": "paper", "aspect": "auto"}, original,
                                   visual_feedback="Keep the intact exterior with external callouts. Use a light background, not overhead.")
        self.assertEqual(brief["explanation_plan"]["mode"], "annotated_context")
        self.assertIn("light neutral", brief["art_direction"]["background"])
        self.assertIn("near-level", brief["art_direction"]["camera"])
        self.assertEqual(self.spec, before)
        self.assertEqual(brief["user_intent"]["description"], original)
        self.assertIn("not overhead", brief["user_intent"]["visual_feedback"]["text"])

    def test_explicit_api_choices_remain_compatible_and_not_palette_bound(self):
        for style in engine.STYLES:
            settings = {"style": style, "representation": "diagram", "explanatory_mode": "annotated_context"}
            self.assertEqual(scene_profiles.resolve_representation(settings, "A product launch hero")["id"], "diagram")
            self.assertEqual(self.mode("A cover hero", "Reveal internal functional regions", settings), "annotated_context")
        self.assertEqual(scene_profiles.resolve_representation({}, "commercial rendering")["id"], "diagram")
        self.assertEqual(scene_profiles.resolve_representation({"representation": "product_render", "category": "fsm"}, "A cover")["id"], "diagram")

    def test_overview_and_negated_detail_do_not_turn_purpose_into_detailed_schematic(self):
        settings = {"scene": "auto", "category": "microarchitecture"}
        self.assertEqual(scene_profiles.resolve(settings, "A whole-core overview for the design review")["id"], "system")
        self.assertEqual(scene_profiles.resolve({"scene": "auto", "category": "architecture"}, "No implementation details; explain the system overview.")["id"], "system")
        self.assertEqual(scene_profiles.resolve({"scene": "auto", "category": "architecture"}, "Not a commercial pitch; explain the dataflow.")["id"], "flow")

    def test_algorithm_uses_purposeful_depth_real_scope_and_selected_palette(self):
        payload = json.loads((ROOT / "examples/attention-dataflow.json").read_text(encoding="utf-8"))
        spec = engine.normalize_spec(payload["spec"])
        figure = algorithm_flow.primary(spec)
        figure["design_contract"].update(target_width_mm=190, body_pt=10, signal_pt=9)
        palette = {"background": "#F4F4F2", "ink": "#263238", "primary": "#E3EDF4", "secondary": "#E6EEE5"}
        before = copy.deepcopy(spec)
        prompt = algorithm_flow.compile_figure(figure, spec, {"style": "paper", "notes": "Use a symbolic tensor plane to explain the supplied dimensions."}, palette)
        self.assertNotIn("No 3D tensors", prompt)
        self.assertNotIn("omit any broad enclosing frame", prompt)
        self.assertIn("depth cue may explain a supplied tensor shape", prompt)
        self.assertIn("do not add an unsupplied tensor axis", prompt)
        self.assertIn("thin enclosure when it clarifies the real iteration, residency or phase scope", prompt)
        self.assertIn("Every shown boundary must stop before nonmembers", prompt)
        self.assertIn("selected background #F4F4F2", prompt)
        self.assertIn("190 mm document width", prompt)
        self.assertEqual(spec, before)


if __name__ == "__main__":
    unittest.main()
