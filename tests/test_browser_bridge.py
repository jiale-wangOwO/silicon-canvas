import base64
import io
import json
import unittest
import zipfile
from silicon_canvas.browser_bridge import dispatch
from tests.test_engine import sample


class BrowserBridgeTests(unittest.TestCase):
    def test_repeated_source_uses_trusted_cache_and_copies_do_not_poison_it(self):
        from silicon_canvas import browser_bridge, engine
        from unittest.mock import patch
        browser_bridge._COMPILED.clear()
        payload = {"spec": sample(), "settings": {"scene": "system"}}
        with patch.object(engine, "compile_manual", wraps=engine.compile_manual) as compiler:
            first = dispatch("compile", payload)
            first["figures"][0]["prompt"] = "forged prompt"
            second = dispatch("compile", payload)
            self.assertEqual(compiler.call_count, 1)
            self.assertNotEqual(second["figures"][0]["prompt"], "forged prompt")
            second["figures"][0]["reference_images"] = [{"path": "file:///private"}]
            dispatch("review", {"result": second})
            self.assertEqual(compiler.call_count, 1)
            dispatch("compile", {**payload, "settings": {"scene": "concept"}})
            self.assertEqual(compiler.call_count, 2)

    def test_no_key_prepare_compile_export_review_uses_source(self):
        prepared = dispatch("prepare", {"description": "完整的 SoC 系统"})
        self.assertIn("context", prepared)
        self.assertEqual(len(prepared["messages"]), 2)
        self.assertNotIn("api_key", json.dumps(prepared))
        result = dispatch("compile", {"spec": sample()})
        guide = dispatch("guide", {"result": result})
        self.assertTrue(base64.b64decode(guide["base64"]).startswith(b"\x89PNG"))
        review = dispatch("review", {"result": result})
        self.assertEqual(review["status"], "not_reviewed")
        exported = dispatch("bundle", {"result": result})
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(exported["base64"]))) as archive:
            self.assertEqual(json.loads(archive.read("result.json"))["spec"], result["spec"])

    def test_unsafe_forged_geometry_and_unknown_action_rejected(self):
        with self.assertRaises(ValueError):
            dispatch("run_python", {})
        with self.assertRaises(ValueError):
            dispatch("guide", {"result": {"spec": sample()}, "figure_id": "../../escape"})
        result = dispatch("compile", {"spec": sample()})
        result["figures"][0]["id"] = "../../escape"
        result["figures"][0]["reference_images"] = [{"path": "file:///private"}]
        exported = dispatch("bundle", {"result": result})
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(exported["base64"]))) as archive:
            self.assertFalse(any(".." in path for path in archive.namelist()))
