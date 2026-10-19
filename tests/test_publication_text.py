"""Measured wrapping preserves source text, parameters and physical type."""
import re
import unittest

from silicon_canvas import publication_render as render


def compact(value):
    return re.sub(r"\s+", "", value)


class PublicationTextTests(unittest.TestCase):
    def test_numbered_owner_and_node_references_do_not_force_prose_into_the_image(self):
        spec = {"groups": [{"id": "cluster", "label": "Cluster 0", "parent": ""}]}
        for label, detail in [("Scheduler 0", "CLUSTER   0 scheduling"),
                              ("Compute Array 0", "Cluster 0 compute array (execution units not expanded)"),
                              ("Scheduler 0", "Scheduler 0 provides local scheduling")]:
            with self.subTest(detail=detail):
                node = {"label": label, "group": "cluster", "detail": detail}
                self.assertEqual(render.required_detail(node, spec), "")
                self.assertEqual(node["detail"], detail)

    def test_real_zero_capacity_and_predicate_survive_numbered_owner_removal(self):
        spec = {"groups": [{"id": "cluster", "label": "Cluster 0", "parent": ""}]}
        for detail in ("Cluster 0 reset value 0", "Cluster 0 local cache: 128 KiB", "Cluster 0: if valid && ready", "Cluster 00 reset description"):
            with self.subTest(detail=detail):
                node = {"label": "Local Cache 0", "group": "cluster", "detail": detail}
                self.assertEqual(render.required_detail(node, spec), detail)

    def test_exact_required_text_and_nonancestor_references_are_never_discarded(self):
        spec = {"groups": [{"id": "cluster", "label": "Cluster 0", "parent": ""},
                           {"id": "peer", "label": "Cluster 1", "parent": ""}]}
        detail = "Cluster 0 scheduling"
        self.assertEqual(render.required_detail({"label": "Scheduler 0", "group": "cluster", "detail": detail}, spec, [detail]), detail)
        other = "Cluster 1 scheduling"
        self.assertEqual(render.required_detail({"label": "Scheduler 0", "group": "cluster", "detail": other}, spec), other)

    def test_long_interface_label_earns_three_lines_without_smaller_type(self):
        face = render.font(32)
        label = "External Configuration Interface"
        self.assertIsNone(render.wrap_text(label, face, 260, max_lines=2))
        lines = render.wrap_text(label, face, 260, max_lines=4)
        self.assertIsNotNone(lines)
        self.assertEqual(compact("".join(lines)), compact(label))
        self.assertGreater(len(lines), 2)
        self.assertLessEqual(len(lines), 4)
        self.assertTrue(all(face.getlength(line) <= 260 for line in lines))
        self.assertEqual(face.size, 32)

    def test_multiline_wrap_keeps_hyphens_digits_and_cjk_characters_exact(self):
        face = render.font(32)
        for text, maximum in [("Timestamp-Aligned Event Merger", 230),
                              ("Private; 32-entry exception queue", 210),
                              ("共享的时间戳对齐事件合并单元", 160)]:
            with self.subTest(text=text):
                lines = render.wrap_text(text, face, maximum, max_lines=4)
                self.assertIsNotNone(lines)
                self.assertEqual(compact("".join(lines)), compact(text))
                self.assertTrue(all(face.getlength(line) <= maximum for line in lines))
                self.assertLessEqual(len(lines), 4)
                self.assertFalse(any("..." in line or "…" in line for line in lines))

    def test_unbreakable_or_over_budget_text_reports_a_limit_instead_of_truncation(self):
        face = render.font(32)
        self.assertIsNone(render.wrap_text("ABCDEFGHIJKLMNO", face, 45, max_lines=4))
        self.assertIsNone(render.wrap_text("one two three four five six seven eight nine ten", face, 85, max_lines=3))

    def test_node_and_inventory_boxes_grow_for_full_text_and_parameters(self):
        short = render.measure_node({"label": "Interface", "kind": "io"}, 32, maximum=304)
        long = render.measure_node({"label": "External Configuration Interface", "kind": "io"}, 32, maximum=304)
        self.assertIsNotNone(long)
        self.assertGreater(long["height"], short["height"])
        self.assertEqual(long["font_px"], short["font_px"])
        self.assertEqual(compact("".join(long["lines"])), compact("External Configuration Interface"))
        owner = {"label": "Analysis", "kind": "compute", "children": [
            {"id": "merge", "label": "Timestamp-Aligned Event Merger", "kind": "compute"},
            {"id": "queue", "label": "Exception Queue", "kind": "memory", "required_detail": "Private; 32-entry exception queue"}]}
        measured = render.measure_node(owner, 32, maximum=500, inventory_columns=1, compact_inventory=True)
        self.assertIsNotNone(measured)
        self.assertEqual(measured["font_px"], 32)
        children = {item["id"]: item for item in measured["children"]}
        self.assertEqual(compact("".join(children["merge"]["lines"])), compact(owner["children"][0]["label"]))
        queue_text = compact("".join(children["queue"]["lines"]))
        self.assertIn(compact("32-entry exception queue"), queue_text)
        for child in children.values():
            box = child["box_px"]
            self.assertLessEqual(box["y"] + box["height"], measured["height"])
            self.assertGreaterEqual(box["height"], len(child["lines"]) * 32)


if __name__ == "__main__":
    unittest.main()
