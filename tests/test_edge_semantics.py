import copy
import unittest
from silicon_canvas import edge_semantics


class EdgeSemanticsTests(unittest.TestCase):
    def test_payload_returns_are_solid_without_changing_source_kind(self):
        source = {"kind": "feedback", "label": "resp", "rationale": "存储返回数据/响应"}
        original = copy.deepcopy(source)
        self.assertEqual(edge_semantics.stroke(source), "solid")
        self.assertEqual(source, original)

    def test_direction_or_response_name_does_not_invent_payload(self):
        for label in ["resp", "ready", "grant", "done", "recovery"]:
            self.assertEqual(edge_semantics.stroke({"kind": "feedback", "label": label}), "dashed")

    def test_control_labels_override_ambiguous_payload_prose(self):
        self.assertEqual(edge_semantics.stroke({"kind": "feedback", "label": "ready", "rationale": "return data ready"}), "dashed")
        self.assertEqual(edge_semantics.stroke({"kind": "control", "label": "return data"}), "dashed")

    def test_a_mixed_projection_is_not_retyped_as_one_payload(self):
        spec = {"edges": [{"kind": "feedback", "label": "data return"}, {"kind": "feedback", "label": "done"}]}
        self.assertEqual(edge_semantics.stroke({"kind": "feedback", "members": [0, 1]}, spec), "dashed")
