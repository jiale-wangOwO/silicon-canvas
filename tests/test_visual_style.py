"""Selected colors stay consistent between the brief and actual guide pixels."""
import io
import json
from pathlib import Path
import unittest

from PIL import Image, ImageColor
from silicon_canvas import behavior_guide, engine, presentation, publication_render, structure_scene
from silicon_canvas import visual_style


def pixels(data):
    with Image.open(io.BytesIO(data)) as image:
        return {rgb for _, rgb in image.convert("RGB").getcolors(image.width * image.height)}


def path_source():
    return engine.normalize_spec({"title": "Memory Path", "category": "microarchitecture", "groups": [],
        "nodes": [{"id": "compute", "label": "Compute", "kind": "compute", "group": "", "detail": ""},
                  {"id": "memory", "label": "Buffer", "kind": "memory", "group": "", "detail": ""}],
        "edges": [{"source": "compute", "target": "memory", "kind": "data", "label": "payload"}]})


class VisualStyleTests(unittest.TestCase):
    def test_catalog_values_are_independent_and_unknown_style_uses_paper(self):
        expected = engine.STYLES["paper"]["palette"]
        selected = visual_style.palette("paper")
        self.assertEqual(selected, expected)
        selected["ink"] = "#FF0000"
        self.assertEqual(visual_style.palette("paper"), expected)
        self.assertEqual(visual_style.palette("missing"), expected)

    def test_settings_override_stale_prose_and_legacy_prompts_still_work(self):
        legacy = "Palette: background #FFFFFC; ink #101010; primary #DDEEAA; secondary #EEDDAA; muted #F0F0F0."
        current = {"settings": {"style": "signal"}, "style_prompt": legacy}
        self.assertEqual(visual_style.result_palette(current), visual_style.palette("signal"))
        self.assertEqual(publication_render._palette(current), visual_style.palette("signal"))
        self.assertEqual(visual_style.result_palette({"style_prompt": legacy})["background"], "#FFFFFC")
        self.assertEqual(visual_style.result_palette({"style_prompt": "No palette in this old file."}), visual_style.palette())
        self.assertEqual(visual_style.result_palette({"settings": {"style": "unknown"}, "style_prompt": legacy}), visual_style.palette())
        gray = {"style_prompt": "Palette: background #FFFFFF; ink #222222; primary #FFFFFF; secondary #EEEEEE; muted #F6F6F6."}
        self.assertEqual(visual_style.route_color("#8855AA", visual_style.result_palette(gray)), "#222222")

    def test_both_hardware_renderers_use_selected_brief_colors(self):
        source = path_source()
        legacy_figure = presentation.build_plan(source, "medium", "en")["figures"][0]
        for style in ("paper", "blueprint", "signal", "monochrome"):
            with self.subTest(style=style):
                result = engine.compile_manual({"spec": source, "settings": {
                    "style": style, "representation": "diagram", "scene": "detail", "language": "en"}})
                colors = visual_style.palette(style)
                for color in colors.values():
                    self.assertIn(color, result["style_prompt"])
                # A stale cached route hue must not defeat monochrome selection.
                legacy_figure["layout_scene"]["routes"][0]["line_color"] = "#3E6785"
                for renderer, figure in ((publication_render.render, result["figures"][0]),
                                         (structure_scene.render, legacy_figure)):
                    data = renderer({**result, "style_prompt": "malformed cached prose"}, figure)
                    self.assertIsInstance(data, bytes)
                    painted = pixels(data)
                    for key in ("background", "ink", "primary", "secondary"):
                        self.assertIn(ImageColor.getrgb(colors[key]), painted)
                    if style == "monochrome":
                        self.assertTrue(all(r == g == b for r, g, b in painted))

    def test_state_guide_uses_selected_palette_including_monochrome_ink(self):
        source = engine.normalize_spec({"title": "Command States", "category": "fsm", "groups": [],
            "nodes": [{"id": "idle", "label": "IDLE", "kind": "state", "group": "", "detail": "Initial state; busy=0"},
                      {"id": "run", "label": "RUN", "kind": "state", "group": "", "detail": "busy=1"}],
            "edges": [{"source": "idle", "target": "run", "kind": "control", "label": "start"}]})
        for style in ("paper", "blueprint", "signal", "monochrome"):
            with self.subTest(style=style):
                result = engine.compile_manual({"spec": source, "settings": {
                    "style": style, "representation": "diagram", "language": "en"}})
                figure = result["figures"][0]
                colors = visual_style.palette(style)
                prompt = behavior_guide.compile_figure(figure, source, result["settings"], colors)
                self.assertEqual(figure["visual_contract"]["palette"], colors)
                for color in (colors["background"], colors["ink"], visual_style.role_fill("state", colors)):
                    self.assertIn(color, prompt)
                painted = pixels(behavior_guide.render(result, figure))
                for color in (colors["background"], colors["ink"], visual_style.role_fill("state", colors)):
                    self.assertIn(ImageColor.getrgb(color), painted)
                if style == "monochrome":
                    self.assertTrue(all(r == g == b for r, g, b in painted))

    def test_monochrome_sample_grid_and_markers_have_no_blue_gray_leak(self):
        fixture = Path(__file__).parent / "fixtures/design_coverage/ready-valid-trace.json"
        request = json.loads(fixture.read_text(encoding="utf-8"))
        request["settings"]["style"] = "monochrome"
        result = engine.compile_manual(request)
        figure = next(item for item in result["figures"] if item.get("behavior_plan"))
        painted = pixels(behavior_guide.render(result, figure))
        self.assertTrue(all(r == g == b for r, g, b in painted))


if __name__ == "__main__":
    unittest.main()
