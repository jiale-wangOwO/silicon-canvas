import io
import json
import unittest
import zipfile

from silicon_canvas import bundle
from silicon_canvas import engine
from silicon_canvas import reading_plan
from silicon_canvas import quality_review
from tests.test_engine import sample


class QualityReviewTests(unittest.TestCase):
    def test_text_only_scope_keeps_relationships_without_fabricating_display_counts(self):
        result = engine.compile_manual({"spec": sample()})
        figure = result["figures"][0]
        figure.pop("layout_scene")
        figure["requires_layout_guide"] = False
        review = quality_review.build(result["spec"], figure, result["source_hash"])
        self.assertEqual(len(review["expected_connections"]), 3)
        self.assertFalse(review["has_controlled_plate"])
        self.assertEqual(review["counts"], {})
        self.assertIn("geometry unplanned", review["connection_basis"])

    def test_manifest_is_unreviewed_and_tracks_actual_display_directions(self):
        result = engine.compile_manual({"spec": sample()})
        figure = result["figures"][0]
        review = figure["review_task"]
        self.assertEqual(review["status"], "not_reviewed")
        self.assertEqual(review["source_hash"], reading_plan.source_hash(result["spec"]))
        self.assertEqual(review["counts"]["visible_connections"], len(review["expected_connections"]))
        self.assertEqual(review["counts"]["arrowheads"], sum(2 if e["bidirectional"] else 1 for e in review["expected_connections"]))
        self.assertTrue(review["has_controlled_plate"])
        mac = next(o for o in review["objects"] if o["label"] == "MAC")
        self.assertEqual(mac["source_facts"][0]["owner"], "NPU")
        self.assertEqual(mac["original_owner_path"], ["NPU"])
        self.assertTrue(any(l["text"] == "payload[31:0]" for l in review["planned_labels"]))
        self.assertIn("not_checked", review["prompt"])
        self.assertIn("Do not infer acceptance", review["prompt"])

    def test_portable_review_manifest_and_prompt_never_claim_bitmap_pass(self):
        result = engine.compile_manual({"spec": sample()})
        with zipfile.ZipFile(io.BytesIO(bundle.build(result))) as archive:
            review = json.loads(archive.read("figures/overview/review-manifest.json"))
            prompt = archive.read("figures/overview/review-prompt.txt").decode("utf-8")
        self.assertEqual(review["status"], "not_reviewed")
        self.assertNotIn("prompt", review)
        self.assertIn("actual attached Image Gen bitmap", prompt)
