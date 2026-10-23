"""Drawing depth follows explicit global intent without changing source scope."""
import copy
import unittest

from silicon_canvas import engine, render_brief


def source():
    return engine.normalize_spec({"title": "Shared Sensor Engine", "category": "architecture",
        "groups": [{"id": "engine", "label": "Sensor Engine"}],
        "nodes": [{"id": "adc", "label": "Acquisition", "kind": "compute", "group": "engine"},
                  {"id": "store", "label": "Shared Storage", "kind": "memory", "group": "engine"},
                  {"id": "host", "label": "External Host", "kind": "io"}],
        "edges": [{"source": "adc", "target": "store", "kind": "data", "label": "samples"},
                  {"source": "store", "target": "host", "kind": "data", "label": "results"}]})


def compile_view(description, feedback="", notes="", representation="system_illustration", mode="functional_cutaway", style="paper"):
    spec = source()
    settings = engine.normalize_settings({"representation": representation, "explanatory_mode": mode, "notes": notes, "style": style})
    figure = render_brief.primary(spec, representation)
    before = copy.deepcopy(spec)
    prompt = render_brief.compile_figure(figure, spec, settings, description, visual_feedback=feedback)
    assert spec == before
    return figure, prompt


class RenderProjectionTests(unittest.TestCase):
    def test_flat_instructions_replace_all_dimensional_defaults(self):
        requests = ("A front-facing flat technical schematic. No perspective, no shadows, no 3D.",
                    "Make a strictly two-dimensional engineering illustration.",
                    "画二维架构图，正向直视，不要立体。",
                    "把系统平面化，采用正视图。")
        for request in requests:
            with self.subTest(request=request):
                fig, prompt = compile_view(request)
                brief = fig["render_brief"]
                active = prompt.split("Original intent and visual revision history")[0]
                self.assertEqual(brief["art_direction"]["projection"], "flat_2d")
                for unwanted in ("dimensional semiconductor system", "three-quarter", "isometric camera", "single chip base",
                                 "Believable satin metal", "Large soft studio", "common perspective", "material/light quality"):
                    self.assertNotIn(unwanted, active)
                self.assertIn("flat two-dimensional", active)
                self.assertIn("two-dimensional logical map", active)
                self.assertEqual(prompt, fig["generation_steps"][0]["prompt"])

    def test_notes_and_latest_feedback_are_effective_projection_sources(self):
        for description, notes, feedback in (
            ("Show the system with 3D materials.", "Use a flat technical diagram.", ""),
            ("An isometric system illustration.", "", "Make it flat, with no perspective."),
            ("An isometric system illustration.", "", "改成平面图。")):
            with self.subTest(feedback=feedback, notes=notes):
                fig, _ = compile_view(description, feedback, notes)
                self.assertEqual(fig["render_brief"]["art_direction"]["projection"], "flat_2d")

    def test_latest_dimensional_request_can_replace_flat_and_unrelated_edits_cannot(self):
        flat, _ = compile_view("A flat diagram.", "Use a dark background.")
        dimensional, _ = compile_view("A flat diagram.", "Make this a 3D isometric illustration.")
        excluded, _ = compile_view("Use an isometric illustration, not a flat diagram.")
        self.assertEqual(flat["render_brief"]["art_direction"]["projection"], "flat_2d")
        self.assertIn("dark charcoal", flat["render_brief"]["art_direction"]["background"])
        self.assertEqual(dimensional["render_brief"]["art_direction"]["projection"], "dimensional")
        self.assertIn("isometric", dimensional["render_brief"]["art_direction"]["camera"])
        self.assertEqual(excluded["render_brief"]["art_direction"]["projection"], "dimensional")

    def test_flat_overlays_and_top_down_do_not_flatten_product_materials(self):
        for request in ("A 3D package with flat functional overlays and flat labels.",
                        "Top-down product render with satin metal and material highlights.",
                        "A package with 2D labels on its surface."):
            with self.subTest(request=request):
                fig, prompt = compile_view(request, representation="product_render")
                self.assertEqual(fig["render_brief"]["art_direction"]["projection"], "dimensional")
                self.assertIn("studio illumination", prompt)
        top, _ = compile_view("Top-down product render with material highlights.")
        self.assertIn("top-down", top["render_brief"]["art_direction"]["camera"])

    def test_parallel_projection_is_not_a_ban_on_material_depth(self):
        for request in ("A front-facing orthographic product view.", "A product rendering with no perspective."):
            with self.subTest(request=request):
                fig, _ = compile_view(request, representation="product_render")
                art = fig["render_brief"]["art_direction"]
                self.assertEqual(art["projection"], "orthographic")
                self.assertIn("orthographic", art["camera"])
                self.assertNotIn("three-quarter", art["camera"])
                self.assertIn("studio illumination", art["lighting"])

    def test_excluded_isometric_does_not_imply_flat_and_later_positive_wins(self):
        excluded, _ = compile_view("A product rendering; no isometric view.")
        restored, _ = compile_view("No 3D, use a flat diagram. Instead use a three-dimensional product view.")
        self.assertEqual(excluded["render_brief"]["art_direction"]["projection"], "dimensional")
        self.assertNotIn("isometric", excluded["render_brief"]["art_direction"]["camera"])
        self.assertEqual(restored["render_brief"]["art_direction"]["projection"], "dimensional")

    def test_projection_changes_no_source_or_selected_relationships(self):
        rendered, _ = compile_view("An isometric system illustration.")
        flat, _ = compile_view("An isometric system illustration.", "Use a flat diagram.")
        first, second = rendered["render_brief"], flat["render_brief"]
        self.assertEqual(first["source_hash"], second["source_hash"])
        self.assertEqual(first["semantic_contract"], second["semantic_contract"])
        for field in ("regions", "relationships", "context_objects", "deferred_edge_indices"):
            self.assertEqual(first["visible_content"][field], second["visible_content"][field])

    def test_optional_refinement_uses_the_same_resolved_medium(self):
        fig, prompt = compile_view("Make a flat technical illustration in a staged two-pass workflow.")
        self.assertEqual(len(fig["generation_steps"]), 2)
        self.assertIn(prompt, fig["generation_steps"][1]["prompt"])
        self.assertIn("Preserve the approved flat visual identity", fig["generation_steps"][1]["prompt"])
        self.assertNotIn("coherent camera/material/light system", fig["generation_steps"][1]["prompt"])

    def test_flat_projection_obeys_selected_graphic_palette_and_typography(self):
        fig, prompt = compile_view("A flat system illustration.", style="monochrome")
        art = fig["render_brief"]["art_direction"]
        self.assertEqual(art["graphic_language"]["style"], "monochrome")
        self.assertIn("Neutral grayscale only", art["palette_policy"])
        self.assertIn("No all-bold text", art["labels"]["policy"])
        self.assertIn("Do not assign a different hue to each region", prompt)
        self.assertIn("one small quiet heading", prompt)
        self.assertNotIn("one hue per meaningful region", prompt)

    def test_full_source_history_cannot_expand_selected_explanatory_scope(self):
        fig, prompt = compile_view("A flat system illustration. Acquisition sends samples to Shared Storage and then the External Host.", mode="annotated_context")
        visible = fig["render_brief"]["visible_content"]
        self.assertEqual(visible["deferred_edge_indices"], [0])
        self.assertIn("Closed selected relationship list", prompt)
        self.assertIn("Unlisted internal paths remain outside this image", prompt)
        self.assertIn("not another drawing inventory", prompt)
        self.assertIn("Member names describe ownership, not an implicit dependency chain", prompt)


if __name__ == "__main__":
    unittest.main()
