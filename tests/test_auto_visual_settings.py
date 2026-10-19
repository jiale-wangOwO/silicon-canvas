"""Opt-in natural-language options share one semantic call and survive export."""
import copy
import io
import json
import unittest
import zipfile
from unittest.mock import patch

from silicon_canvas import auto_settings, browser_bridge, bundle, engine, service


AUTO = {"style": "auto", "density": "auto", "language": "auto", "aspect": "auto", "scene": "auto", "representation": "auto"}
SELECTED = {"style": "monochrome", "density": "high", "aspect": "A4"}


def source():
    return {"title": "Receive buffer", "category": "dataflow", "nodes": [
        {"id": "input", "label": "Input", "kind": "io", "evidence": "输入", "origin": "given"},
        {"id": "buffer", "label": "Buffer", "kind": "memory", "evidence": "缓冲", "origin": "given"}],
        "edges": [{"source": "input", "target": "buffer", "kind": "data", "label": "", "evidence": "输入到缓冲", "origin": "given"}]}


def request(**extra):
    return {**AUTO, "description": "画输入到缓冲，黑白配色、竖版 A4，详细一点。", **extra}


class AutomaticVisualSettingsTests(unittest.TestCase):
    def test_omitted_legacy_defaults_and_provider_response_shape_are_unchanged(self):
        messages, context = engine.prepare_request({"description": "输入到缓冲"})
        self.assertEqual({key: context["settings"][key] for key in auto_settings.DEFAULTS}, auto_settings.DEFAULTS)
        user = json.loads(messages[1]["content"])
        self.assertNotIn("automatic_visual_settings", user)
        self.assertNotIn("visual_settings", user["specification_schema"]["properties"])
        self.assertNotIn("automatic_visual_fields", context)
        result = engine.finish_request(source(), context)
        self.assertNotIn("automatic_visual_settings", result["settings"])

    def test_auto_request_exposes_complete_conditional_typed_contract_in_same_response(self):
        messages, context = engine.prepare_request(request())
        user = json.loads(messages[1]["content"])
        schema = user["specification_schema"]
        self.assertIn("visual_settings", schema["required"])
        automatic = schema["properties"]["visual_settings"]
        self.assertEqual(set(automatic["required"]), set(SELECTED))
        self.assertFalse(automatic["additionalProperties"])
        self.assertNotIn("language", automatic["properties"])
        self.assertNotIn("language_choices", user["automatic_visual_settings"])
        self.assertEqual(user["automatic_visual_settings"]["manual_overrides"]["language"], "en")
        self.assertIn("source", schema["$defs"]["edge"]["required"])
        self.assertIn("target", schema["$defs"]["edge"]["required"])
        self.assertEqual(context["settings"]["language"], "en")
        self.assertEqual(user["image_label_language"], "en")
        self.assertIn("Evidence still copies the original input language exactly", messages[0]["content"])

    def test_auto_detail_contract_uses_reader_abstraction_not_inventory_budget(self):
        cases = ["详细解释只有两个模块的握手机制。", "十二个模块只做系统整体概览，不展开实现。"]
        for description in cases:
            with self.subTest(description=description):
                messages, _ = engine.prepare_request(request(description=description))
                user = json.loads(messages[1]["content"])
                choices = user["automatic_visual_settings"]["density_choices"]
                self.assertEqual(choices, auto_settings.DETAIL_CHOICES)
                self.assertIn("predicates", choices["high"])
                self.assertIn("main relationships", choices["low"])
                self.assertNotEqual(choices["high"], engine.DENSITIES["high"][1])
                self.assertIn("NOT the current inventory size", messages[0]["content"])
                self.assertEqual(user["description"], description)

    def test_semantic_choices_resolve_before_compile_without_entering_source_hash(self):
        _, context = engine.prepare_request(request())
        data = {**source(), "visual_settings": SELECTED}
        result = engine.finish_request(data, context)
        for field, value in SELECTED.items():
            self.assertEqual(result["settings"][field], value)
        self.assertEqual(result["settings"]["automatic_visual_settings"]["method"], "semantic-response")
        self.assertNotIn("visual_settings", result["spec"])
        baseline = engine.compile_manual({"spec": result["spec"], "settings": {**SELECTED, "scene": "auto", "representation": "auto"}, "description": request()["description"]})
        self.assertEqual(result["source_hash"], baseline["source_hash"])
        self.assertEqual(result["prompt"], baseline["prompt"])

    def test_manual_values_are_never_overridden_by_model_and_only_auto_fields_are_requested(self):
        messages, context = engine.prepare_request(request(style="blueprint", language="en", aspect="16:9"))
        automatic = json.loads(messages[1]["content"])["automatic_visual_settings"]
        self.assertEqual(automatic["fields"], ["density"])
        self.assertEqual(automatic["manual_overrides"]["style"], "blueprint")
        result = engine.finish_request({**source(), "visual_settings": {"density": "low"}}, context)
        self.assertEqual(result["settings"]["style"], "blueprint")
        self.assertEqual(result["settings"]["language"], "en")
        self.assertEqual(result["settings"]["aspect"], "16:9")
        self.assertEqual(result["settings"]["density"], "low")
        with self.assertRaisesRegex(ValueError, "多余 style"):
            engine.finish_request({**source(), "visual_settings": {"density": "low", "style": "paper"}}, context)

    def test_unknown_missing_free_color_and_invalid_choices_are_rejected(self):
        _, context = engine.prepare_request(request())
        for selection in (None, {}, {**SELECTED, "color": "#00f"}, {**SELECTED, "style": "neon"}, {**SELECTED, "language": "auto"}):
            with self.subTest(selection=selection):
                with self.assertRaises(ValueError):
                    engine.finish_request({**source(), "visual_settings": selection}, context)

    def test_one_provider_call_can_select_options_and_graph_together(self):
        reply = {"data": {**source(), "visual_settings": SELECTED}, "model": "test-provider", "usage": {}}
        with patch("silicon_canvas.provider.complete", return_value=reply) as complete:
            result = service.generate_result(request(), engine)
        self.assertEqual(complete.call_count, 1)
        self.assertEqual(result["settings"]["language"], "en")
        self.assertNotIn("repaired", result)

    def test_invalid_selection_has_only_existing_bounded_repair(self):
        bad = {"data": {**source(), "visual_settings": {**SELECTED, "style": "unknown"}}, "model": "test", "usage": {}}
        good = {"data": {**source(), "visual_settings": SELECTED}, "model": "test", "usage": {}}
        with patch("silicon_canvas.provider.complete", side_effect=[bad, good]) as complete:
            result = service.generate_result(request(), engine)
        self.assertEqual(complete.call_count, 2)
        self.assertTrue(result["repaired"])
        with patch("silicon_canvas.provider.complete", return_value=bad) as complete:
            with self.assertRaises(service.GenerationError):
                service.generate_result(request(), engine)
        self.assertEqual(complete.call_count, 2)

    def test_local_recompile_and_bundle_reuse_saved_choices_without_api(self):
        _, context = engine.prepare_request(request())
        result = engine.finish_request({**source(), "visual_settings": SELECTED}, context)
        result["settings"].update({key: "auto" for key in SELECTED})
        with patch("silicon_canvas.provider.complete", side_effect=AssertionError("local recompile must not call a provider")):
            local = browser_bridge.dispatch("compile", result)
            package = bundle.build(local)
        self.assertEqual(local["settings"]["automatic_visual_settings"]["method"], "saved-selection")
        self.assertEqual({key: local["settings"][key] for key in SELECTED}, SELECTED)
        with zipfile.ZipFile(io.BytesIO(package)) as archive:
            restored = json.loads(archive.read("result.json"))
        self.assertEqual(restored["settings"]["automatic_visual_settings"], local["settings"]["automatic_visual_settings"])

    def test_unresolved_manual_auto_is_honest_compatibility_fallback(self):
        result = engine.compile_manual({"spec": source(), "settings": AUTO})
        selection = result["settings"]["automatic_visual_settings"]
        self.assertEqual(selection["method"], "compatibility-defaults")
        self.assertTrue(any("不是模型" in warning for warning in result["warnings"]))

    def test_locked_feedback_keeps_previous_resolved_visual_settings(self):
        _, context = engine.prepare_request(request())
        previous = engine.finish_request({**source(), "visual_settings": SELECTED}, context)
        _, revision = engine.prepare_request({**request(), "feedback": "增加模块间距", "previous": previous})
        self.assertNotIn("automatic_visual_fields", revision)
        self.assertEqual(revision["settings"]["style"], "monochrome")
        modified = copy.deepcopy(previous["spec"])
        modified["layout"] = "More open spacing."
        result = engine.finish_request(modified, revision)
        self.assertEqual(result["spec"]["nodes"], previous["spec"]["nodes"])
        self.assertEqual(result["settings"]["automatic_visual_settings"], previous["settings"]["automatic_visual_settings"])


if __name__ == "__main__":
    unittest.main()
