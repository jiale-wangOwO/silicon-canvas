"""Spatial art direction selects one geometry without changing source facts."""
import copy
import hashlib
import io
import unittest

from PIL import Image
from silicon_canvas import engine, render_brief, render_guide


def package_source():
    return engine.normalize_spec({"title": "Generic package", "category": "architecture", "groups": [],
        "nodes": [{"id": "lid", "label": "Heat Spreader / Lid", "kind": "memory"},
                  {"id": "tim", "label": "Thermal Interface Layer", "kind": "memory"},
                  {"id": "die", "label": "Compute Die", "kind": "compute"},
                  {"id": "sub", "label": "Package Substrate", "kind": "memory"},
                  {"id": "board", "label": "Circuit Board", "kind": "io"}],
        "edges": [{"source": "die", "target": "tim", "kind": "data", "label": "heat"},
                  {"source": "tim", "target": "lid", "kind": "data", "label": "heat"},
                  {"source": "die", "target": "sub", "kind": "data", "label": "signal"},
                  {"source": "sub", "target": "board", "kind": "data", "label": "signal"}]})


def compile_render(spec, description, mode="auto", aspect="16:9", feedback=""):
    settings = engine.normalize_settings({"representation": "system_illustration", "explanatory_mode": mode, "aspect": aspect})
    figure = render_brief.primary(spec, "system_illustration")
    figure["prompt"] = render_brief.compile_figure(figure, spec, settings, description, visual_feedback=feedback)
    return figure, {"settings": settings}


class SpatialCompositionTests(unittest.TestCase):
    def test_grouped_section_keeps_both_internal_routes_and_individual_parts_visible(self):
        spec = package_source()
        spec['groups'] = [{'id': 'pkg', 'label': 'Package', 'parent': ''}]
        for node in spec['nodes']:
            if node['id'] != 'board':
                node['group'] = 'pkg'
        before = copy.deepcopy(spec)
        figure, _ = compile_render(spec, 'A local cross-section of the assembled package: heat travels upward through the interface to the lid, signal travels downward through the substrate to the board.')
        visible = figure['render_brief']['visible_content']
        self.assertEqual({index for rel in visible['relationships'] for index in rel['source_edge_indices']}, {0, 1, 2, 3})
        self.assertTrue(all(len(region['source_node_ids']) == 1 for region in visible['regions']))
        self.assertEqual(visible['deferred_node_ids'], [])
        self.assertEqual(spec, before)

    def test_section_layers_and_routes_do_not_inherit_the_six_region_eight_link_budget(self):
        spec = package_source()
        for index in range(5):
            spec['nodes'].append({'id': 'layer' + str(index), 'label': 'Assembly Layer ' + str(index), 'kind': 'memory', 'group': ''})
            spec['edges'].append({'source': 'die', 'target': 'layer' + str(index), 'kind': 'data', 'label': 'path ' + str(index)})
        figure, _ = compile_render(spec, 'Local cross-section of all supplied assembly layers and their paths.')
        visible = figure['render_brief']['visible_content']
        self.assertEqual(visible['deferred_node_ids'], [])
        self.assertEqual(visible['deferred_edge_indices'], [])
        self.assertEqual(len(visible['relationships']), 9)

    def test_local_physical_section_preserves_assembly_instead_of_becoming_a_function_plane(self):
        spec = package_source(); original = copy.deepcopy(spec)
        figure, _ = compile_render(spec, "Show a local cross-section of the package assembly. Keep its supplied layers assembled; do not use an exploded view.")
        brief = figure["render_brief"]
        self.assertEqual(brief["composition_plan"]["geometry"], "assembled_section")
        self.assertEqual(brief["subject"]["kind"], "sectioned_assembly_concept")
        self.assertFalse(brief["composition_plan"]["detail_view"]["requested"])
        self.assertIn("preserving their supplied layer order", figure["prompt"])
        self.assertNotIn("Role overlays stay flat", figure["prompt"])
        self.assertNotIn("one common chip plane", figure["prompt"])
        self.assertEqual(spec, original)
        self.assertEqual(len(brief["semantic_contract"]["source_relations"]), len(spec["edges"]))

    def test_logical_functions_do_not_authorize_manufactured_package_layers(self):
        spec = engine.normalize_spec({"title": "Logic overview", "category": "architecture", "nodes": [{"id": "cpu", "label": "CPU", "kind": "compute"}, {"id": "cache", "label": "Shared Cache", "kind": "memory"}], "edges": [{"source": "cpu", "target": "cache", "kind": "data"}]})
        figure, _ = compile_render(spec, "Logical functional cutaway of the system; no physical die layout.")
        self.assertEqual(figure["render_brief"]["composition_plan"]["geometry"], "logical_function_plane")
        self.assertIn("single chip base", figure["prompt"])
        self.assertNotIn("preserving their supplied layer order", figure["prompt"])

    def test_exploded_and_assembled_views_are_distinct_without_changing_counts(self):
        spec = package_source()
        exploded, _ = compile_render(spec, "Exploded assembly view of the supplied package layers.")
        intact, _ = compile_render(spec, "Keep the assembly together, without an exploded view.", mode="assembly")
        self.assertEqual(exploded["render_brief"]["composition_plan"]["geometry"], "exploded_assembly")
        self.assertEqual(intact["render_brief"]["composition_plan"]["geometry"], "coherent_assembly")
        self.assertEqual(exploded["render_brief"]["source_hash"], intact["render_brief"]["source_hash"])
        self.assertIn("Do not turn assembly associations into invented up/down data or heat arrows", exploded["prompt"])
        ordinary, _ = compile_render(spec, "画封装爆炸图，展示盖板、基板和电路板。")
        self.assertEqual(ordinary["render_brief"]["composition_plan"]["geometry"], "exploded_assembly")

    def test_same_object_detail_is_opt_in_and_never_an_extra_component(self):
        spec = package_source()
        whole, _ = compile_render(spec, "Explain the complete assembly.", mode="assembly")
        detail, _ = compile_render(spec, "Explain the whole assembly with a detail inset of the supplied package.", mode="assembly")
        self.assertFalse(whole["render_brief"]["composition_plan"]["detail_view"]["requested"])
        self.assertTrue(detail["render_brief"]["composition_plan"]["detail_view"]["requested"])
        self.assertEqual(whole["render_brief"]["semantic_contract"], detail["render_brief"]["semantic_contract"])
        self.assertIn("does not increase component count", detail["prompt"])

    def test_latest_feedback_can_remove_section_or_detail_without_mutating_source(self):
        spec = package_source()
        figure, _ = compile_render(spec, "Package cross-section with a detail inset.", feedback="No cutaway or detail inset; keep the intact exterior with callouts.")
        self.assertEqual(figure["render_brief"]["composition_plan"]["geometry"], "whole_with_context")
        self.assertFalse(figure["render_brief"]["composition_plan"]["detail_view"]["requested"])
        self.assertIn("latest visual request", figure["prompt"])

    def test_ordinary_component_detail_wording_and_its_exclusion_are_not_template_specific(self):
        spec = package_source()
        for wording in ("主图保持完整产品，旁边用局部展示解释已有部件。", "保留整体，部件展开说明已有结构。", "放大一个部件，解释同一装配的内部。"):
            figure, _ = compile_render(spec, wording, mode="assembly")
            self.assertTrue(figure["render_brief"]["composition_plan"]["detail_view"]["requested"])
        excluded, _ = compile_render(spec, "保持整体，不要局部展示。", mode="assembly")
        self.assertFalse(excluded["render_brief"]["composition_plan"]["detail_view"]["requested"])

    def test_optional_framing_respects_canvas_and_changes_geometry_without_electrical_authority(self):
        spec = package_source(); pixels = set()
        for aspect, size in [("16:9", (1600, 900)), ("4:3", (1600, 1200)), ("1:1", (1200, 1200)), ("A4", (1131, 1600))]:
            figure, result = compile_render(spec, "Package cross-section with layers still assembled.", aspect=aspect)
            data = render_guide.render(result, figure)
            with Image.open(io.BytesIO(data)) as image:
                self.assertEqual(image.size, size)
            self.assertTrue(figure["composition_guide_optional"])
            self.assertFalse(figure["requires_layout_guide"])
            self.assertEqual(figure["render_brief"]["composition_plan"]["authority"].split(";")[0], "editorial explanation only")
            pixels.add(hashlib.sha256(data).hexdigest())
        self.assertEqual(len(pixels), 4)


if __name__ == "__main__":
    unittest.main()
