"""English new-request defaults do not rewrite historical source or evidence."""
import copy
import json
import unittest
from unittest.mock import patch

from silicon_canvas import auto_settings, browser_bridge, engine, service


DESCRIPTION = "输入到缓冲，黑白配色。"


def source(language="en"):
    return {"title": "接收缓冲" if language == "zh" else "Receive buffer", "category": "dataflow",
            "nodes": [{"id": "input", "label": "输入" if language == "zh" else "Input", "kind": "io", "evidence": "输入"},
                      {"id": "buffer", "label": "缓冲" if language == "zh" else "Buffer", "kind": "memory", "evidence": "缓冲"}],
            "edges": [{"source": "input", "target": "buffer", "kind": "data", "evidence": "输入到缓冲"}]}


class ArtworkLanguageTests(unittest.TestCase):
    def test_new_chinese_requests_share_english_policy_in_prepare_finish_compile_and_generate(self):
        for language in (None, "auto", "en"):
            with self.subTest(language=language):
                payload = {"description": DESCRIPTION, "completion_mode": "strict"}
                if language is not None:
                    payload["language"] = language
                messages, context = engine.prepare_request(payload)
                user = json.loads(messages[1]["content"])
                self.assertEqual(user["image_label_language"], "en")
                self.assertEqual(user["description"], DESCRIPTION)
                self.assertNotIn("automatic_visual_fields", context)
                self.assertNotIn("visual_settings", user["specification_schema"]["properties"])
                self.assertIn("image_label_language is authoritative", messages[0]["content"])
                self.assertIn("never translate it", messages[0]["content"])
                finished = engine.finish_request(source(), context)
                local = engine.compile_manual({"spec": source(), "settings": payload, "description": DESCRIPTION})
                with patch("silicon_canvas.provider.complete", return_value={"data": source(), "model": "test", "usage": {}}) as complete:
                    generated = service.generate_result(payload, engine)
                self.assertEqual(complete.call_count, 1)
                self.assertEqual(json.loads(complete.call_args.args[0][1]["content"])["image_label_language"], "en")
                for result in (finished, local, generated):
                    self.assertEqual(result["settings"]["language"], "en")
                    self.assertEqual(result["spec"]["nodes"][0]["label"], "Input")
                    self.assertEqual(result["spec"]["nodes"][0]["evidence"], "输入")
                self.assertEqual(finished["source_hash"], local["source_hash"])
                self.assertEqual(finished["source_hash"], generated["source_hash"])

    def test_auto_language_is_not_a_model_choice_or_an_aspect_opt_in(self):
        self.assertEqual(auto_settings.requested({"language": "auto", "aspect": "auto"}), [])
        messages, context = engine.prepare_request({"description": DESCRIPTION, "style": "auto", "language": "auto"})
        options = json.loads(messages[1]["content"])["automatic_visual_settings"]
        self.assertEqual(options["fields"], ["style", "aspect"])
        self.assertEqual(options["manual_overrides"]["language"], "en")
        with self.assertRaisesRegex(ValueError, "多余 language"):
            engine.finish_request({**source(), "visual_settings": {"style": "monochrome", "aspect": "1:1", "language": "zh"}}, context)

    def test_explicit_historical_chinese_project_and_locked_revision_are_preserved(self):
        old_selection = {"requested": {"style": "auto", "language": "auto"},
                         "selected": {"style": "monochrome", "language": "zh"}, "method": "semantic-response"}
        prior = engine.compile_manual({"spec": source("zh"), "description": DESCRIPTION,
                                       "settings": {"style": "monochrome", "language": "zh", "automatic_visual_settings": old_selection}})
        restored = browser_bridge.dispatch("compile", prior)
        self.assertEqual(restored["spec"], prior["spec"])
        self.assertEqual(restored["source_hash"], prior["source_hash"])
        self.assertEqual(restored["settings"]["language"], "zh")
        self.assertEqual(restored["settings"]["automatic_visual_settings"], old_selection)
        messages, context = engine.prepare_request({"description": DESCRIPTION, "language": "en", "feedback": "增加间距", "previous": restored, "lock_structure": True})
        self.assertEqual(json.loads(messages[1]["content"])["image_label_language"], "zh")
        changed = copy.deepcopy(source())
        changed["layout"] = "More open spacing."
        revised = engine.finish_request(changed, context)
        self.assertEqual(revised["spec"]["nodes"], prior["spec"]["nodes"])
        self.assertEqual({key: value for key, value in revised["spec"].items() if key not in {"layout", "checks"}},
                         {key: value for key, value in prior["spec"].items() if key not in {"layout", "checks"}})
        self.assertEqual(revised["settings"]["language"], "zh")
        fresh_messages, fresh_context = engine.prepare_request({"description": DESCRIPTION, "language": "auto"})
        fresh = engine.finish_request(source(), fresh_context)
        self.assertEqual(json.loads(fresh_messages[1]["content"])["image_label_language"], "en")
        self.assertEqual(fresh["settings"]["language"], "en")
        self.assertEqual(fresh["spec"]["nodes"][0]["label"], "Input")


if __name__ == "__main__":
    unittest.main()
