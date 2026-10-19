"""Exercise the real SDK and subprocess transport, not a hand-built JSON-RPC stub."""
from __future__ import annotations

import base64
import copy
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from mcp import Client, ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import BlobResourceContents, ImageContent, TextResourceContents

from silicon_canvas import engine, provider, reading_plan
from silicon_canvas.artifact_store import ArtifactStore
from silicon_canvas.mcp_server import create_server

ROOT = Path(__file__).resolve().parents[1]
DESCRIPTION = "Input flows through a buffer to the compute engine."


def source_spec():
    return {
        "title": "Buffered Compute Path", "summary": "输入经缓冲后计算", "category": "dataflow",
        "nodes": [
            {"id": "input", "label": "Input", "kind": "io", "evidence": "Input"},
            {"id": "buffer", "label": "Buffer", "kind": "memory", "evidence": "buffer"},
            {"id": "compute", "label": "Compute", "kind": "compute", "evidence": "compute"},
        ],
        "edges": [
            {"source": "input", "target": "buffer", "kind": "data", "evidence": "Input flows through a buffer"},
            {"source": "buffer", "target": "compute", "kind": "data", "evidence": "buffer to the compute engine"},
        ],
    }


class ArtifactStoreTests(unittest.TestCase):
    def test_owned_handles_and_filenames_reject_traversal(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = ArtifactStore(Path(temporary))
            handle = store.create("test", {"example": 1})
            self.assertEqual(store.read(handle, "test"), {"example": 1})
            for value in ["../../anything", "a" * 31, "a" * 33, "A" * 32, "", "00000000-0000-0000-0000-000000000000"]:
                with self.subTest(value=value), self.assertRaises(ValueError):
                    store.read(value, "test")
            for value in ["../result.json", "a/b.json", "a\\b.json", ".", ".."]:
                with self.subTest(value=value), self.assertRaises(ValueError):
                    store.write(handle, value, b"should not be written")
            with self.assertRaises(ValueError):
                store.figure_name("../../elsewhere", "guide.png")
            with self.assertRaises(ValueError):
                store.read(handle, "compiled")

    def test_records_survive_new_store_instance(self):
        with tempfile.TemporaryDirectory() as temporary:
            handle = ArtifactStore(Path(temporary)).create("test", {"example": 2})
            self.assertEqual(ArtifactStore(Path(temporary)).read(handle, "test"), {"example": 2})


class MCPTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        # Match ArtifactStore's physical root: Windows TEMP may use a junction
        # or short-path alias that differs from the generated file's real path.
        self.output = Path(self.temporary.name).resolve(strict=True)
        self.server = create_server(self.output)

    async def asyncTearDown(self):
        self.temporary.cleanup()

    async def test_chinese_input_uses_english_by_default_across_real_mcp_tools(self):
        from tests.test_artwork_language import DESCRIPTION as chinese_description, source as chinese_evidence_source

        async with Client(self.server) as client:
            for language in (None, "auto"):
                with self.subTest(language=language):
                    settings = {} if language is None else {"language": language}
                    prepared = await client.call_tool("silicon_prepare", {"description": chinese_description, "settings": settings})
                    self.assertFalse(prepared.is_error, str(prepared.content))
                    user = json.loads(prepared.structured_content["messages"][1]["content"])
                    self.assertEqual(user["image_label_language"], "en")
                    self.assertNotIn("visual_settings", user["specification_schema"]["properties"])
                    hosted = await client.call_tool("silicon_compile", {"spec": chinese_evidence_source(), "preparation_id": prepared.structured_content["preparation_id"]})
                    local = await client.call_tool("silicon_compile", {"spec": chinese_evidence_source(), "description": chinese_description, "settings": settings})
                    with patch("silicon_canvas.provider.complete", return_value={"data": chinese_evidence_source(), "model": "test", "usage": {}}) as complete:
                        generated = await client.call_tool("silicon_generate", {"description": chinese_description, "settings": settings})
                    self.assertEqual(complete.call_count, 1)
                    self.assertEqual(json.loads(complete.call_args.args[0][1]["content"])["image_label_language"], "en")
                    for response in (hosted, local, generated):
                        self.assertFalse(response.is_error, str(response.content))
                        result = json.loads((await client.read_resource(response.structured_content["result_uri"])).contents[0].text)
                        self.assertEqual(result["settings"]["language"], "en")
                        self.assertEqual(result["spec"]["nodes"][0]["label"], "Input")
                        self.assertEqual(result["spec"]["nodes"][0]["evidence"], "输入")

    async def test_historical_chinese_mcp_import_and_locked_feedback_keep_saved_language(self):
        from tests.test_artwork_language import DESCRIPTION as chinese_description, source as chinese_evidence_source

        async with Client(self.server) as client:
            imported = await client.call_tool("silicon_compile", {"spec": chinese_evidence_source("zh"), "description": chinese_description, "settings": {"language": "zh"}})
            self.assertFalse(imported.is_error, str(imported.content))
            prepared = await client.call_tool("silicon_prepare", {"description": chinese_description, "settings": {"language": "en"}, "previous_artifact_id": imported.structured_content["artifact_id"], "feedback": "增加间距", "lock_structure": True})
            self.assertEqual(json.loads(prepared.structured_content["messages"][1]["content"])["image_label_language"], "zh")
            revised = await client.call_tool("silicon_compile", {"spec": chinese_evidence_source(), "preparation_id": prepared.structured_content["preparation_id"]})
            self.assertFalse(revised.is_error, str(revised.content))
            result = json.loads((await client.read_resource(revised.structured_content["result_uri"])).contents[0].text)
            self.assertEqual(result["settings"]["language"], "zh")
            self.assertEqual(result["spec"]["nodes"][0]["label"], "输入")
            self.assertEqual(result["source_hash"], imported.structured_content["source_hash"])

    async def test_generation_handoff_uses_actual_guide_availability_and_form(self):
        async with Client(self.server) as client:
            required = (await client.call_tool("silicon_compile", {"spec": source_spec()})).structured_content
            self.assertIsNotNone(required["guide_uri"])
            self.assertFalse(required["guide_optional"])
            self.assertIn("with the selected prompt and target guide", required["next_step"])
            with patch("silicon_canvas.mcp_server.layout_guide.render", return_value=None):
                missing = (await client.call_tool("silicon_compile", {"spec": source_spec()})).structured_content
            self.assertIsNone(missing["guide_uri"])
            self.assertIn("no available controlled target guide", missing["next_step"])
            self.assertIn("recompose", missing["next_step"])
            self.assertEqual(missing["review_status"], "not_reviewed")
            optional = (await client.call_tool("silicon_compile", {"spec": source_spec(), "settings": {"representation": "product_render", "scene": "concept"}})).structured_content
            self.assertTrue(optional["guide_optional"])
            self.assertIn("optional composition reference", optional["next_step"])
            self.assertNotIn("no available controlled target guide", optional["next_step"])

    async def test_host_model_workflow_returns_image_source_and_zip_without_provider(self):
        with patch("silicon_canvas.provider.complete", side_effect=AssertionError("Host workflow must not call a provider")):
            async with Client(self.server) as client:
                tools = (await client.list_tools()).tools
                self.assertEqual({tool.name for tool in tools}, {"silicon_prepare", "silicon_compile", "silicon_generate", "silicon_export", "silicon_prepare_review"})
                prepared = await client.call_tool("silicon_prepare", {"description": DESCRIPTION})
                self.assertFalse(prepared.is_error)
                preparation = prepared.structured_content
                self.assertEqual([m["role"] for m in preparation["messages"]], ["system", "user"])
                compiled = await client.call_tool("silicon_compile", {"spec": source_spec(), "preparation_id": preparation["preparation_id"]})
                self.assertFalse(compiled.is_error, str(compiled.content))
                data = compiled.structured_content
                self.assertEqual(data["review_status"], "not_reviewed")
                self.assertIn("Image Gen", data["prompt"])
                images = [item for item in compiled.content if isinstance(item, ImageContent)]
                self.assertEqual(len(images), 1)
                guide = base64.b64decode(images[0].data)
                self.assertTrue(guide.startswith(b"\x89PNG\r\n\x1a\n"))
                self.assertEqual(guide, Path(data["guide_path"]).read_bytes())
                self.assertTrue(Path(data["guide_path"]).resolve(strict=True).is_relative_to(self.output))
                guide_resource = await client.read_resource(data["guide_uri"])
                self.assertIsInstance(guide_resource.contents[0], BlobResourceContents)
                self.assertEqual(base64.b64decode(guide_resource.contents[0].blob), guide)
                saved_brief = await client.read_resource(data["figures"][0]["brief_uri"])
                self.assertEqual(json.loads(saved_brief.contents[0].text)["prompt"], data["prompt"])
                self.assertEqual(json.loads(saved_brief.contents[0].text)["figure_strategy"], data["figure_strategy"])
                source = await client.read_resource(data["result_uri"])
                self.assertIsInstance(source.contents[0], TextResourceContents)
                complete = json.loads(source.contents[0].text)
                self.assertEqual(complete["figure_strategy"], data["figure_strategy"])
                self.assertEqual(complete["spec"], engine.normalize_spec(source_spec()))
                self.assertEqual(len(complete["spec"]["edges"]), 2)
                reviewed = await client.call_tool("silicon_prepare_review", {"artifact_id": data["artifact_id"]})
                self.assertEqual(reviewed.structured_content["status"], "not_reviewed")
                self.assertEqual(reviewed.structured_content["review_task"]["status"], "not_reviewed")
                exported = await client.call_tool("silicon_export", {"artifact_id": data["artifact_id"]})
                self.assertFalse(exported.is_error)
                pack_data = exported.structured_content
                resource = await client.read_resource(pack_data["uri"])
                pack = base64.b64decode(resource.contents[0].blob)
                self.assertEqual(pack, Path(pack_data["path"]).read_bytes())
                with zipfile.ZipFile(io.BytesIO(pack)) as archive:
                    zipped = json.loads(archive.read("result.json"))
                    self.assertEqual(zipped["spec"], complete["spec"])
                    self.assertEqual(json.loads(archive.read("figures/" + data["selected_figure_id"] + "/figure-strategy.json")), data["figure_strategy"])
                    self.assertTrue(any(name.endswith("review-manifest.json") for name in archive.namelist()))
                    self.assertEqual(archive.read("figures/" + data["selected_figure_id"] + "/layout-guide.png"), guide)
                templates = (await client.list_resource_templates()).resource_templates
                self.assertEqual(len(templates), 5)
                self.assertIn("silicon://catalog", [str(r.uri) for r in (await client.list_resources()).resources])

    async def test_malformed_and_unowned_inputs_return_tool_errors(self):
        async with Client(self.server) as client:
            cases = [
                ("silicon_prepare", {"description": ""}),
                ("silicon_prepare", {"description": "GPU", "settings": {"style": "unknown"}}),
                ("silicon_compile", {"spec": {"title": "Broken", "category": "architecture", "nodes": []}}),
                ("silicon_compile", {"spec": source_spec(), "preparation_id": "../secrets"}),
                ("silicon_export", {"artifact_id": "../secrets"}),
                ("silicon_prepare_review", {"artifact_id": "f" * 32}),
                ("silicon_compile", {"spec": source_spec(), "figure_id": "../../write"}),
            ]
            broken_edge = source_spec()
            broken_edge["edges"][0]["target"] = "missing"
            cases.append(("silicon_compile", {"spec": broken_edge}))
            for tool, arguments in cases:
                with self.subTest(tool=tool, arguments=arguments):
                    result = await client.call_tool(tool, arguments)
                    self.assertTrue(result.is_error)
                    self.assertIsNone(result.structured_content)

    async def test_complex_soc_preserves_entire_source_and_reports_real_preflight(self):
        fixture = json.loads((ROOT / "tests/fixtures/editorial_benchmark/fresh-soc-final-source.json").read_text(encoding="utf-8"))
        with patch("silicon_canvas.provider.complete", side_effect=AssertionError("No provider needed")):
            async with Client(self.server) as client:
                prepared = await client.call_tool("silicon_prepare", {"description": fixture["description"], "settings": fixture.get("settings", {})})
                compiled = await client.call_tool("silicon_compile", {"spec": fixture["spec"], "preparation_id": prepared.structured_content["preparation_id"]})
                self.assertFalse(compiled.is_error, str(compiled.content))
                data = compiled.structured_content
                source = json.loads((await client.read_resource(data["result_uri"])).contents[0].text)
                self.assertEqual(source["spec"], engine.normalize_spec(fixture["spec"]))
                self.assertEqual(len(source["spec"]["nodes"]), 13)
                self.assertEqual(len(source["spec"]["edges"]), 15)
                self.assertEqual(data["source_hash"], reading_plan.source_hash(source["spec"]))
                quality = data["preflight"]["quality"]
                self.assertTrue(quality["routes_complete"])
                self.assertEqual(quality["document_fit"]["status"], "pass")
                self.assertTrue(quality["geometry_is_not_raster_acceptance"])
                self.assertEqual(data["review_status"], "not_reviewed")
                exported = await client.call_tool("silicon_export", {"artifact_id": data["artifact_id"], "figure_id": data["selected_figure_id"]})
                self.assertFalse(exported.is_error)
                downloaded = await client.read_resource(exported.structured_content["uri"])
                with zipfile.ZipFile(io.BytesIO(base64.b64decode(downloaded.contents[0].blob))) as archive:
                    zipped = json.loads(archive.read("result.json"))
                    self.assertEqual(zipped["spec"], source["spec"])
                    self.assertEqual(len(zipped["figures"]), 1)

    async def test_explicit_revision_lock_keeps_source_semantics(self):
        async with Client(self.server) as client:
            compiled = await client.call_tool("silicon_compile", {"spec": source_spec()})
            data = compiled.structured_content
            prepared = await client.call_tool("silicon_prepare", {"description": DESCRIPTION, "previous_artifact_id": data["artifact_id"], "feedback": "Improve spacing", "lock_structure": True})
            changed = source_spec()
            changed["nodes"][1]["label"] = "Unexpected replacement"
            revised = await client.call_tool("silicon_compile", {"spec": changed, "preparation_id": prepared.structured_content["preparation_id"]})
            self.assertFalse(revised.is_error)
            source = await client.read_resource(revised.structured_content["result_uri"])
            self.assertEqual(json.loads(source.contents[0].text)["spec"]["nodes"][1]["label"], "Buffer")

    async def test_optional_provider_errors_are_safe(self):
        with patch("silicon_canvas.provider.complete", side_effect=provider.ProviderError("API 身份验证失败或无访问权限，请检查本地 DEEPSEEK_API_KEY。")):
            async with Client(self.server) as client:
                response = await client.call_tool("silicon_generate", {"description": "完整的 SoC 系统"})
                self.assertTrue(response.is_error)
                self.assertIn("DEEPSEEK_API_KEY", response.content[0].text)
                self.assertIsNone(response.structured_content)
        self.assertEqual(list(self.output.iterdir()), [])

    async def test_real_stdio_classic_client_initialize_compile_and_read(self):
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(ROOT / "src")
        environment["SILICON_CANVAS_OUTPUT_DIR"] = str(self.output)
        parameters = StdioServerParameters(command=sys.executable, args=["-m", "silicon_canvas.mcp_server"], env=environment, cwd=ROOT)
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write) as client:
                initialized = await client.initialize()
                self.assertEqual(initialized.server_info.name, "Silicon Canvas")
                self.assertEqual(len((await client.list_tools()).tools), 5)
                compiled = await client.call_tool("silicon_compile", {"spec": source_spec()})
                self.assertFalse(compiled.is_error, str(compiled.content))
                data = compiled.structured_content
                self.assertTrue(data["source_hash"])
                read_source = await client.read_resource(data["result_uri"])
                self.assertEqual(json.loads(read_source.contents[0].text)["source_hash"], data["source_hash"])
                exported = await client.call_tool("silicon_export", {"artifact_id": data["artifact_id"]})
                self.assertFalse(exported.is_error)
                self.assertTrue(Path(exported.structured_content["path"]).is_file())


if __name__ == "__main__":
    unittest.main()
