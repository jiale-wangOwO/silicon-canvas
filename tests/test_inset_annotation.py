"""A view expansion must not erase ownership or look like a technical path."""
import copy
import json
from pathlib import Path
import unittest

from silicon_canvas import engine, layout_guide, publication_render


ROOT = Path(__file__).resolve().parents[1]


def rect(box, width, height):
    return (box["x"] * width, box["y"] * height,
            (box["x"] + box["width"]) * width, (box["y"] + box["height"]) * height)


def overlap(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def segment_enters(a, b, box):
    if abs(a[0] - b[0]) < .01:
        return box[0] < a[0] < box[2] and max(min(a[1], b[1]), box[1]) < min(max(a[1], b[1]), box[3])
    if abs(a[1] - b[1]) < .01:
        return box[1] < a[1] < box[3] and max(min(a[0], b[0]), box[0]) < min(max(a[0], b[0]), box[2])
    raise AssertionError("Annotation and technical paths must be orthogonal")


class InsetAnnotationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads((ROOT / "tests/fixtures/design_coverage/repeated-ingress.json").read_text(encoding="utf-8"))
        cls.result = engine.compile_manual(cls.payload)
        cls.figure = next(item for item in cls.result["figures"] if item["id"] == cls.result["selected_figure_id"])

    def test_same_hardware_expansion_is_outside_every_rendered_source_scope(self):
        result, figure = self.result, self.figure
        plan, scene = figure["structure_layout"], figure["layout_scene"]
        width, height = scene["width"], scene["height"]
        self.assertEqual(result["spec"], self.payload["spec"])
        self.assertEqual(len(result["spec"]["nodes"]), 22)
        self.assertEqual(len(result["spec"]["edges"]), 21)
        self.assertEqual(len(scene["routes"]), 9)
        self.assertEqual(len(plan["insets"]), 1)
        inset = plan["insets"][0]
        self.assertEqual(inset["source_members"], ["rx0", "parse0", "q0", "tag0"])
        self.assertEqual(inset["source_internal_edge_indices"], [0, 1, 2])
        owner = next(item for item in plan["containers"] if item["source_group"] == "engine")
        self.assertIsNot(owner.get("render_boundary"), False)
        for scope in plan["containers"]:
            if scope.get("render_boundary") is not False:
                self.assertFalse(overlap(rect(inset["box"], width, height), rect(scope["box"], width, height)))
        marker = next(item for item in figure["label_layout"]["labels"] if item.get("role") == "same-hardware-view")
        self.assertEqual(marker["text"], "Same hardware detail")
        self.assertEqual(marker["source_edge_indices"], [])
        self.assertEqual(marker["source_object"], inset["source_object"])
        self.assertTrue(plan["typography"]["no_font_shrink"])
        self.assertEqual(plan["typography"]["body_pt"], 9)
        self.assertLessEqual(scene["quality"]["document_fit"]["height_mm"], 140)
        self.assertTrue(layout_guide.render(result, figure))

    def test_dedicated_arrow_free_leader_is_clear_of_real_routes_and_signal_text(self):
        figure = self.figure
        scene, inset = figure["layout_scene"], figure["structure_layout"]["insets"][0]
        width, height = scene["width"], scene["height"]
        self.assertEqual(inset["leader_mode"], "dedicated annotation corridor without arrowhead")
        self.assertTrue(inset["leader"])
        self.assertNotIn("source_edge_indices", inset)
        self.assertNotIn("members", inset)
        leader = [[x * width, y * height] for x, y in inset["leader"]]
        regions = [(min(a[0], b[0]) - 8, min(a[1], b[1]) - 8,
                    max(a[0], b[0]) + 8, max(a[1], b[1]) + 8) for a, b in zip(leader, leader[1:])]
        for route in scene["routes"]:
            points = [[x * width, y * height] for x, y in route["points"]]
            self.assertFalse(any(segment_enters(a, b, box) for a, b in zip(points, points[1:]) for box in regions))
        for label in figure["label_layout"]["labels"]:
            if label.get("source_edge_indices"):
                self.assertFalse(any(overlap(rect(label["box"], width, height), box) for box in regions))

    def test_renderer_rejects_an_inset_which_would_cover_its_owner_outline(self):
        figure = copy.deepcopy(self.figure)
        plan = figure["structure_layout"]
        owner = next(item for item in plan["containers"] if item["source_group"] == "engine")
        plan["insets"][0]["box"]["x"] = owner["box"]["x"] + .01
        plan["insets"][0]["box"]["y"] = owner["box"]["y"] + .01
        scene = figure["layout_scene"]
        self.assertTrue(overlap(rect(plan["insets"][0]["box"], scene["width"], scene["height"]),
                                rect(owner["box"], scene["width"], scene["height"])))
        self.assertIsNone(publication_render.render(self.result, figure))

    def test_blocked_leader_uses_matching_view_labels_instead_of_a_fake_junction(self):
        figure = copy.deepcopy(self.figure)
        inset = figure["structure_layout"]["insets"][0]
        inset["leader"] = copy.deepcopy(figure["layout_scene"]["routes"][0]["points"])
        before = copy.deepcopy(self.result["spec"])
        self.assertIsNotNone(publication_render.render(self.result, figure, labels_only=True))
        self.assertEqual(inset["leader"], [])
        self.assertEqual(inset["leader_mode"], "matched owner name and same-hardware marker")
        self.assertEqual(self.result["spec"], before)
        self.assertEqual(len(figure["layout_scene"]["routes"]), 9)

    def test_unequal_second_detail_retains_ownership_and_context_bypasses_both_views(self):
        payload = copy.deepcopy(self.payload)
        next(node for node in payload["spec"]["nodes"] if node["id"] == "q3")["detail"] = "Private; 32-entry exception queue"
        result = engine.compile_manual(payload)
        figure = next(item for item in result["figures"] if item["id"] == result["selected_figure_id"])
        self.assertEqual(figure["layout_strategy"], "publication-candidates")
        plan, scene = figure["structure_layout"], figure["layout_scene"]
        self.assertEqual(result["spec"], payload["spec"])
        self.assertEqual(len(plan["insets"]), 2)
        self.assertFalse(next(node for node in figure["macro_nodes"] if node["id"] == "lane3").get("equivalent_to"))
        width, height = scene["width"], scene["height"]
        for inset in plan["insets"]:
            box = rect(inset["box"], width, height)
            for route in scene["routes"]:
                points = [[x * width, y * height] for x, y in route["points"]]
                self.assertFalse(any(segment_enters(a, b, box) for a, b in zip(points, points[1:])))
        context = next(route for route in scene["routes"] if route["source"] == "host")
        self.assertEqual(context["target"], "manage")
        self.assertEqual(context["kind"], "control")
        original_index = next(index for index, edge in enumerate(payload["spec"]["edges"])
                              if edge["source"] == "host" and edge["target"] == "manage")
        self.assertEqual(context["members"], [original_index])
        self.assertEqual(context["label"], payload["spec"]["edges"][original_index]["label"])
        self.assertFalse(context.get("bidirectional"))
        self.assertEqual(context["stroke_style"], "dashed")
        for nid, point in ((context["source"], context["points"][0]), (context["target"], context["points"][-1])):
            b = plan["boxes"][nid]
            x0, y0, x1, y1 = b["x"], b["y"], b["x"] + b["width"], b["y"] + b["height"]
            self.assertTrue(x0 - .000002 <= point[0] <= x1 + .000002 and y0 - .000002 <= point[1] <= y1 + .000002)
            self.assertLessEqual(min(abs(point[0] - x0), abs(point[0] - x1),
                                     abs(point[1] - y0), abs(point[1] - y1)), .000002)
        self.assertTrue(layout_guide.render(result, figure))


if __name__ == "__main__":
    unittest.main()
