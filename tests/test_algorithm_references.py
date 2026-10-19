import json
from pathlib import Path
import unittest

from silicon_canvas import engine, reference_selector


ROOT = Path(__file__).resolve().parents[1]


class AlgorithmReferenceTests(unittest.TestCase):
    def compiled(self, name, style="paper"):
        source = json.loads((ROOT / "examples" / (name + ".json")).read_text(encoding="utf-8"))
        source["settings"]["style"] = style
        result = engine.compile_manual(source)
        return result, result["figures"][0]

    def test_attention_prefers_algorithm_operator_reference_without_borrowing_topology(self):
        result, figure = self.compiled("attention-dataflow")
        report = figure["reference_selection"]
        self.assertEqual(report["task"]["family"], "algorithm")
        self.assertEqual(report["selected"][0]["path"], "dataflow/transformer-2017-fig2-attention-operators.png")
        self.assertIn("operator", report["selected"][0]["matched_traits"])
        self.assertFalse(report["selection_is_visual_certification"])
        self.assertEqual(figure["algorithm_flow_plan"]["source_hash"], result["source_hash"])
        self.assertEqual(figure["generation_inputs"], [])

    def test_online_state_and_residency_receive_distinct_reference_grammars(self):
        result, figure = self.compiled("online-attention-dataflow")
        selected = figure["reference_selection"]["selected"]
        traits = set().union(*(set(item["matched_traits"]) for item in selected))
        self.assertTrue({"recurrence", "reuse"} <= traits)
        self.assertTrue(all("algorithm_manifest.json" in item["manifests"] for item in selected))
        monochrome, mono_figure = self.compiled("online-attention-dataflow", "monochrome")
        self.assertEqual(monochrome["spec"], result["spec"])
        self.assertEqual(mono_figure["algorithm_flow_plan"], figure["algorithm_flow_plan"])
        self.assertEqual(mono_figure["reference_selection"]["palette_source"], "target_style")

    def test_distributed_metadata_has_exact_sources_without_third_party_pixels(self):
        manifest = json.loads((reference_selector.REFERENCE_ROOT / "algorithm_manifest.json").read_text(encoding="utf-8"))
        self.assertTrue(manifest["metadata_only"])
        self.assertEqual(len(manifest["items"]), 10)
        self.assertEqual(len({item["paper"] for item in manifest["items"]}), 8)
        for item in manifest["items"]:
            self.assertTrue(item["source_url"].startswith("https://"))
            self.assertGreater(item["pdf_page"], 0)
            self.assertTrue(item["inspected"])
            self.assertEqual(len(item["image_sha256"]), 64)
            self.assertFalse((reference_selector.REFERENCE_ROOT / item["path"]).exists())


if __name__ == "__main__":
    unittest.main()
