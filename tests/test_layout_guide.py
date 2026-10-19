"""Check whether an optional geometry reference is safe enough to supply."""
import builtins
import copy
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from silicon_canvas import engine
from silicon_canvas import layout_guide


HAS_PILLOW = importlib.util.find_spec("PIL") is not None
HAS_FONT = any(path.is_file() for path in (
    Path("C:/Windows/Fonts/msyh.ttc"),
    Path("C:/Windows/Fonts/arial.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
))


class LayoutGuideTests(unittest.TestCase):
    def processing_view(self):
        # Independently designed split/join graph; no product architecture facts.
        # Keep the shared input store under its original source owner.
        fixture_path = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "strategy_benchmark" / "publication_result.json"
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        result = engine.compile_manual({"spec": fixture["spec"], "settings": fixture["settings"]})
        figure = next(f for f in result["figures"] if not f["abstract"])
        return result, figure

    @unittest.skipUnless(HAS_PILLOW and HAS_FONT, "Pillow and a rendering font are optional")
    def test_branched_six_resource_seven_relation_reference_is_decodable_png(self):
        from PIL import Image

        result, figure = self.processing_view()
        original_spec = copy.deepcopy(result["spec"])
        self.assertEqual(len(figure["node_ids"]), 6)
        self.assertEqual(len(figure["edge_indices"]), 7)
        data = layout_guide.render(result, figure)
        self.assertIsInstance(data, bytes)
        self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"))
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            self.assertEqual(image.format, "PNG")
            self.assertGreater(image.width, 200)
            self.assertGreater(image.height, 100)
        self.assertEqual(result["spec"], original_spec)
        self.assertEqual(figure["structure_layout"]["source_ownership"]["samples"], "inputs")
        self.assertNotEqual(figure["structure_layout"]["source_ownership"]["samples"], "processing")

    @unittest.skipUnless(HAS_PILLOW and HAS_FONT, "Pillow and a rendering font are optional")
    def test_route_through_a_third_resource_is_not_exported_as_authority(self):
        result, figure = self.processing_view()
        unsafe = copy.deepcopy(figure)
        # Deliberately place an unrelated branch operator on the input path.
        route=next(e for e in unsafe['layout_scene']['routes'] if e['source']=='samples' and e['target']=='decode')
        a,b=max(zip(route['points'],route['points'][1:]),key=lambda pair:abs(pair[0][0]-pair[1][0])+abs(pair[0][1]-pair[1][1]))
        box=unsafe['structure_layout']['boxes']['filter'];cx=(a[0]+b[0])/2;cy=(a[1]+b[1])/2
        unsafe['structure_layout']['boxes']['filter']={**box,'x':cx-box['width']/2,'y':cy-box['height']/2}
        self.assertIsNone(layout_guide.render(result, unsafe))

    @unittest.skipUnless(HAS_PILLOW and HAS_FONT, "Pillow and a rendering font are optional")
    def test_unbreakable_label_that_exceeds_its_symbol_is_rejected(self):
        result, figure = self.processing_view()
        result = copy.deepcopy(result)
        next(n for n in result["spec"]["nodes"] if n["id"] == "decode")["label"] = "UnbreakableSignalName" * 7
        # The existing scaffold is intentionally too small for this new name.
        # Returning None keeps a clipped reference out of the user bundle.
        self.assertIsNone(layout_guide.render(result, figure))

    def test_no_pillow_keeps_prompt_compilation_available_without_a_guide(self):
        result, figure = self.processing_view()
        original_import = builtins.__import__

        def without_pillow(name, *args, **kwargs):
            if name == "PIL" or name.startswith("PIL."):
                raise ImportError("Pillow intentionally unavailable")
            return original_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", side_effect=without_pillow):
            self.assertIsNone(layout_guide.render(result, figure))
        self.assertIn("Image Gen", result["prompt"])

    def test_abstract_overview_never_gets_unproved_exact_pin_geometry(self):
        result, _ = self.processing_view()
        overview = {"id": "unproved-overview", "abstract": True, "node_ids": [],
                    "edge_indices": [], "macro_nodes": [], "macro_edges": []}
        self.assertIsNone(layout_guide.render(result, overview))


if __name__ == "__main__":
    unittest.main()
