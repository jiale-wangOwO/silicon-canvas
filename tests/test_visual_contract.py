import copy
import io
import json
from pathlib import Path
import unittest
import zipfile

from silicon_canvas import browser_bridge, bundle, engine, visual_style


ROOT = Path(__file__).resolve().parents[1]


class VisualContractTests(unittest.TestCase):
    def test_engineering_keeps_user_appearance_and_matches_web_export(self):
        payload = {"spec": {"title": "Transfer", "category": "dataflow", "nodes": [
            {"id": "input", "label": "Input", "kind": "io"},
            {"id": "process", "label": "Transform", "kind": "compute"},
            {"id": "output", "label": "Output", "kind": "memory"}], "edges": [
            {"source": "input", "target": "process", "kind": "data"},
            {"source": "process", "target": "output", "kind": "data"}]},
            "description": "Show the supplied transfer path. Use generous open whitespace.",
            "settings": {"representation": "diagram", "style": "monochrome", "notes": "Use a serif heading."}}
        before = copy.deepcopy(payload)
        result = engine.compile_manual(payload)
        web = browser_bridge.dispatch("compile", payload)
        figure = next(f for f in result["figures"] if f["id"] == result["selected_figure_id"])
        self.assertEqual(result["prompt"], web["prompt"])
        self.assertEqual(result["visual_contract"], web["visual_contract"])
        self.assertEqual(payload, before)
        self.assertIn("Use a serif heading.", figure["prompt"])
        self.assertIn("generous open whitespace", figure["prompt"])
        self.assertEqual(figure["visual_contract"]["palette"], visual_style.palette("monochrome"))
        self.assertEqual(figure["review_task"]["status"], "not_reviewed")
        data = bundle.build(result)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            contract = json.loads(archive.read("figures/" + figure["id"] + "/visual-contract.json"))
            self.assertEqual(contract, figure["visual_contract"])

    def test_algorithm_uses_tensor_operator_colors_and_keeps_source(self):
        payload = json.loads((ROOT / "examples/attention-dataflow.json").read_text(encoding="utf-8"))
        payload["settings"].update(style="signal", representation="diagram")
        result = engine.compile_manual(payload)
        primary = next(f for f in result["figures"] if f.get("primary"))
        contract = primary["visual_contract"]
        self.assertEqual(contract["family"], "algorithm")
        self.assertEqual(set(contract["role_fills"]), {"tensor", "operator", "state"})
        self.assertNotIn("compute #", primary["prompt"])
        self.assertEqual(result["spec"], engine.normalize_spec(payload["spec"]))

    def test_flat_render_edit_and_generate_use_same_projection(self):
        payload = json.loads((ROOT / "examples/soc.json").read_text(encoding="utf-8"))
        payload.update(description="An internal functional system illustration, flat and strictly two-dimensional.", feedback="Correct missing paths.")
        payload["settings"].update(representation="system_illustration", notes="No perspective or shadows.")
        result = engine.compile_manual(payload)
        primary = next(f for f in result["figures"] if f.get("primary"))
        self.assertEqual(primary["visual_contract"]["projection"], "flat_2d")
        self.assertEqual(primary["prompt"], primary["generation_steps"][0]["prompt"])
        self.assertIn("Regenerate the flat illustration", primary["edit_prompt"])
        self.assertNotIn("physical-looking finish", primary["edit_prompt"])

    def test_product_camera_does_not_override_flat_technical_companions(self):
        payload = json.loads((ROOT / "examples/soc.json").read_text(encoding="utf-8"))
        request = "A photorealistic angled chip render with metallic surfaces and studio lighting."
        payload.update(description=request, feedback="Make the metal glossier.")
        payload["settings"].update(representation="product_render", notes="Use perspective and realistic material highlights.")
        result = engine.compile_manual(payload)
        annexes = [f for f in result["figures"] if f.get("technical_annex")]
        self.assertTrue(annexes)
        for figure in annexes:
            self.assertNotIn(request, figure["prompt"])
            self.assertNotIn("Use perspective and realistic material highlights.", figure["prompt"])
            self.assertNotIn("Make the metal glossier.", figure["edit_prompt"])
            self.assertIn("do not apply", figure["visual_contract"]["user_intent_scope"])


if __name__ == "__main__":
    unittest.main()
