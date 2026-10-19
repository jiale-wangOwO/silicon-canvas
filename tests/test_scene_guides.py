import io
import json
from pathlib import Path
import unittest

from PIL import Image
from silicon_canvas import engine, layout_guide, reading_plan

ROOT = Path(__file__).resolve().parents[1]


class SceneGuideTests(unittest.TestCase):
    def test_whole_soc_and_gpu_have_controlled_distinct_guides_with_one_palette(self):
        for name in ["gpu", "soc"]:
            source = json.loads((ROOT / "examples" / (name + ".json")).read_text(encoding="utf-8"))
            hashes, graphs = set(), set()
            canonical = None
            for scene in ["concept", "system", "flow", "detail"]:
                with self.subTest(case=name, scene=scene):
                    result = engine.compile_manual({**source, "settings": {**source["settings"], "style": "paper", "scene": scene}})
                    canonical = canonical or result["spec"]
                    self.assertEqual(result["spec"], canonical)
                    self.assertEqual(result["source_hash"], reading_plan.source_hash(canonical))
                    figure = next(f for f in result["figures"] if f["primary"])
                    self.assertEqual(figure["layout_strategy"], "publication-candidates")
                    self.assertTrue(figure["layout_scene"]["quality"]["routes_complete"])
                    png = layout_guide.render(result, figure)
                    self.assertTrue(png, "A changed prompt without a usable guide is not a controlled scene")
                    image = Image.open(io.BytesIO(png)).convert("RGB")
                    hashes.add(image.tobytes())
                    graphs.add(tuple(n["id"] for n in figure["macro_nodes"]))
                    self.assertEqual(figure["review_task"]["status"], "not_reviewed")
                    if scene == "concept":
                        self.assertEqual(set(figure["projection"]["source_node_to_macro"]), {n["id"] for n in canonical["nodes"]})
                        self.assertTrue(all(not n.get("children") for n in figure["macro_nodes"]))
                        self.assertTrue(figure["structure_layout"].get("presentation_frame"))
            self.assertEqual(len(hashes), 4)
            self.assertGreaterEqual(len(graphs), 3)
