"""Verify rendered briefs survive actual interface, export and review boundaries."""
import base64
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from mcp import Client
from silicon_canvas.browser_bridge import dispatch
from silicon_canvas.mcp_server import create_server


def payload():
    return {"spec": {"title": "Edge SoC", "category": "architecture",
                     "nodes": [{"id": "cpu", "label": "CPU", "kind": "compute"},
                               {"id": "sram", "label": "SRAM", "kind": "memory"}],
                     "edges": [{"source": "cpu", "target": "sram", "kind": "data", "label": "payload"}]},
            "description": "商业渲染，白底，产品概念外观。",
            "settings": {"representation": "product_render", "scene": "concept"}}


class RenderBrowserTests(unittest.TestCase):
    def test_visual_revision_survives_trusted_recompile_export_and_cache_key(self):
        from silicon_canvas import browser_bridge
        revised = {**payload(), "feedback": "改成深色背景，主体放右侧。"}
        result = dispatch("compile", revised)
        browser_bridge._COMPILED.clear()  # Simulate reopening in a new Worker.
        exported = dispatch("bundle", {"result": result})
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(exported["base64"]))) as package:
            restored = json.loads(package.read("result.json"))
            self.assertEqual(restored["feedback"], revised["feedback"])
            self.assertIn("dark charcoal", restored["figures"][0]["render_brief"]["art_direction"]["background"])
            self.assertIn("主体放右侧", restored["figures"][0]["generation_steps"][0]["prompt"])
        neutral = dispatch("compile", payload())
        self.assertNotEqual(neutral["prompt"], restored["prompt"])
        self.assertEqual(neutral["source_hash"], restored["source_hash"])

    def test_export_and_review_use_optional_framing_not_target_geometry(self):
        result = dispatch("compile", payload())
        guide = dispatch("guide", {"result": result})
        self.assertTrue(guide["optional"])
        self.assertEqual(guide["role"], "composition_reference")
        review = dispatch("review", {"result": result})
        self.assertEqual(review["status"], "not_reviewed")
        self.assertTrue(review["no_cad_or_die_layout_certification"])
        archive = dispatch("bundle", {"result": result, "figure_id": result["selected_figure_id"]})
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(archive["base64"]))) as package:
            folder = "figures/" + result["selected_figure_id"] + "/"
            self.assertIn(folder + "render-brief.json", package.namelist())
            self.assertIn(folder + "complete-prompt.txt", package.namelist())
            self.assertEqual(package.read(folder + "complete-prompt.txt").decode(), result['figures'][0]['generation_steps'][0]['prompt'])
            self.assertNotIn(folder + "layout-guide.png", package.namelist())
            self.assertEqual(package.read(folder + "composition-guide.png"), base64.b64decode(guide["base64"]))
            exported = json.loads(package.read("result.json"))
            self.assertEqual(exported["spec"], result["spec"])
            self.assertTrue(exported["figures"][0]["generation_inputs"][0]["optional"])


class RenderMCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_sdk_preserves_render_role_in_tools_resources_and_export(self):
        with tempfile.TemporaryDirectory() as temporary:
            async with Client(create_server(Path(temporary))) as client:
                result = await client.call_tool("silicon_compile", payload())
                self.assertFalse(result.is_error, str(result.content))
                data = result.structured_content
                self.assertEqual(data["representation"], "product_render")
                self.assertTrue(data["guide_optional"])
                self.assertEqual(data["guide_role"], "composition_reference")
                self.assertEqual(data["preflight"]["quality"], {})
                brief = json.loads((await client.read_resource(data["figures"][0]["brief_uri"])).contents[0].text)
                self.assertTrue(brief["guide_optional"])
                self.assertEqual(brief["render_brief"], data["render_brief"])
                review = await client.call_tool("silicon_prepare_review", {"artifact_id": data["artifact_id"]})
                self.assertEqual(review.structured_content["status"], "not_reviewed")
                exported = await client.call_tool("silicon_export", {"artifact_id": data["artifact_id"]})
                with zipfile.ZipFile(exported.structured_content["path"]) as package:
                    self.assertIn("figures/" + data["selected_figure_id"] + "/render-brief.json", package.namelist())
