import copy
import importlib.util
import io
import json
from pathlib import Path
import unittest

from silicon_canvas import engine
from silicon_canvas import layout_guide
from silicon_canvas import presentation


class StructureSceneTests(unittest.TestCase):
    def result(self):
        path=Path(__file__).resolve().parents[1]/'tests/fixtures/structure_benchmark/core_source.json'
        return engine.compile_manual(json.loads(path.read_text(encoding='utf-8')))

    def legacy_result(self):
        """Exercise CPS5 geometry directly, outside the active editorial primary."""
        path = Path(__file__).resolve().parents[1] / 'tests/fixtures/structure_benchmark/core_source.json'
        payload = json.loads(path.read_text(encoding='utf-8'))
        settings = engine.normalize_settings(payload.get('settings', {}))
        result = engine._source_result(payload['spec'], settings)
        plan = presentation.build_plan(result['spec'], result['settings']['density'], result['settings']['language'])
        result['figures'] = plan['figures']
        result['render_plan'] = plan
        return result

    def test_normal_compile_keeps_source_hierarchy_and_all_relationships(self):
        r=self.result();source=json.loads((Path(__file__).resolve().parents[1]/'tests/fixtures/structure_benchmark/core_source.json').read_text(encoding='utf-8'))['spec']
        independent = json.loads((Path(__file__).resolve().parent / 'fixtures/strategy_benchmark/containment_core_fixture.json').read_text(encoding='utf-8'))
        self.assertEqual(source, independent)
        self.assertEqual(engine.normalize_spec(source), source)
        self.assertEqual((len(source['nodes']), len(source['edges'])), (17, 27))
        self.assertEqual(r['spec']['nodes'],source['nodes'])
        self.assertEqual(r['spec']['edges'],source['edges'])
        self.assertEqual(r['spec']['groups'],source['groups'])
        owned=[i for f in r['figures'] if not f['abstract'] for i in f['edge_indices']]
        self.assertCountEqual(owned,range(len(source['edges'])))
        self.assertEqual(r['render_plan']['coverage']['missing_nodes'],[])

    def test_organization_overview_retains_three_workers_and_explicit_source_cut(self):
        f=self.legacy_result()['figures'][0];p=f['structure_layout']
        units=[o for o in p['macro_nodes'] if o['zone']=='units']
        self.assertEqual(len(units),3)
        self.assertEqual(p['node_to_macro']['scratch'],'worker0')
        self.assertNotIn('scratch',{o['id'] for o in p['macro_nodes']})
        self.assertEqual(len(f['layout_scene']['routes']),9)
        self.assertTrue(p['deferred_links'])
        self.assertEqual(f['view_role'],'resource-organization')

    def test_feed_transform_input_and_output_do_not_use_the_same_side(self):
        routes=self.legacy_result()['figures'][0]['layout_scene']['routes']
        upstream=next(e for e in routes if e['source']=='sharedram' and e['target']=='loader')
        downstream=next(e for e in routes if e['source']=='loader' and e['target']=='staging')
        self.assertNotEqual(upstream['target_side'],downstream['source_side'])
        self.assertFalse(upstream.get('bidirectional',False))
        self.assertFalse(downstream.get('bidirectional',False))

    def test_routes_remain_inside_engine_and_do_not_imply_a_common_bus(self):
        f=self.legacy_result()['figures'][0];p=f['structure_layout'];scene=f['layout_scene'];self.assertTrue(scene['quality']['routes_complete'])
        boxes=p['boxes'];frame=p['system_frame']['box'];segments=[]
        byid={o['id']:o for o in p['macro_nodes']}
        for e in scene['routes']:
            if all(byid[n]['zone']!='external' for n in [e['source'],e['target']]):
                for x,y in e['points']:
                    self.assertLessEqual(frame['x']-1e-5,x);self.assertLessEqual(x,frame['x']+frame['width']+1e-5)
                    self.assertLessEqual(frame['y']-1e-5,y);self.assertLessEqual(y,frame['y']+frame['height']+1e-5)
            for a,b in zip(e['points'],e['points'][1:]):
                for other in p['macro_nodes']:
                    if other['id'] in (e['source'],e['target']):continue
                    box=boxes[other['id']];x0,y0=box['x'],box['y'];x1,y1=x0+box['width'],y0+box['height']
                    if a[0]==b[0]:self.assertFalse(x0<a[0]<x1 and max(min(a[1],b[1]),y0)<min(max(a[1],b[1]),y1))
                    if a[1]==b[1]:self.assertFalse(y0<a[1]<y1 and max(min(a[0],b[0]),x0)<min(max(a[0],b[0]),x1))
                for c,d in segments:
                    if a[0]==b[0]==c[0]==d[0]:self.assertFalse(max(min(a[1],b[1]),min(c[1],d[1]))<min(max(a[1],b[1]),max(c[1],d[1]))-1e-5)
                    if a[1]==b[1]==c[1]==d[1]:self.assertFalse(max(min(a[0],b[0]),min(c[0],d[0]))<min(max(a[0],b[0]),max(c[0],d[0]))-1e-5)
                segments.append((a,b))

    def test_pairing_preserves_all_original_payload_facts_and_direction_labels(self):
        r=self.result();f=next(f for f in r['figures'] if f.get('view_role')=='datapath');routes=f['layout_scene']['routes']
        self.assertEqual(len(routes),9)
        self.assertEqual(len(f['edge_indices']), 13)
        self.assertTrue(all(r['spec']['edges'][index]['kind'] == 'data' for index in f['edge_indices']))
        self.assertCountEqual([i for e in routes for i in e['members']],f['edge_indices'])
        for e in routes:
            if not e.get('bidirectional'):continue
            original=[r['spec']['edges'][i] for i in e['members']]
            self.assertEqual(len(original),2)
            self.assertEqual(original[0]['source'],original[1]['target'])
            self.assertEqual(original[0]['target'],original[1]['source'])
            self.assertEqual([x['label'] for x in e['directional_labels']],[x['label'] for x in original])

    def test_crossing_independent_control_paths_does_not_create_a_junction(self):
        """Fixed owner/context lanes can cross; a crossing is no new relation."""
        result = self.result()
        figure = next(f for f in result['figures'] if f.get('view_role') == 'control')
        scene = figure['layout_scene']
        self.assertTrue(scene['quality']['routes_complete'])
        self.assertTrue(scene['quality']['no_common_bus_inferred'])
        crossings = []
        for index, first in enumerate(scene['routes']):
            for second in scene['routes'][index + 1:]:
                if {first['source'], first['target']} & {second['source'], second['target']}:
                    continue
                for a, b in zip(first['points'], first['points'][1:]):
                    for c, d in zip(second['points'], second['points'][1:]):
                        vertical_first = (a[0] == b[0] and c[1] == d[1]
                                          and min(c[0], d[0]) < a[0] < max(c[0], d[0])
                                          and min(a[1], b[1]) < c[1] < max(a[1], b[1]))
                        horizontal_first = (a[1] == b[1] and c[0] == d[0]
                                            and min(a[0], b[0]) < c[0] < max(a[0], b[0])
                                            and min(c[1], d[1]) < a[1] < max(c[1], d[1]))
                        if vertical_first or horizontal_first:
                            crossings.append((first, second))
        self.assertTrue(crossings, 'Synthetic control graph must exercise a real wire crossing.')
        for first, second in crossings:
            self.assertFalse(set(first['members']) & set(second['members']))
            for route in (first, second):
                self.assertEqual(len(route['members']), 1)
                source = result['spec']['edges'][route['members'][0]]
                self.assertEqual((route['source'], route['target']), (source['source'], source['target']))
        self.assertCountEqual([i for route in scene['routes'] for i in route['members']], figure['edge_indices'])

    def test_structural_error_regenerates_selected_scope_from_source_and_clean_carrier(self):
        r=self.result();f=next(f for f in r['figures'] if f.get('view_role')=='datapath')
        revised=engine.compile_result(r['spec'],r['settings'],feedback='Restore one missing arrowhead',previous_spec=r['spec'],figure_id=f['id'])
        selected = next(figure for figure in revised['figures'] if figure['id'] == f['id'])
        self.assertEqual(selected['revision_mode'], 'regenerate-from-source')
        self.assertEqual(revised['selected_figure_id'], f['id'])
        self.assertEqual(selected['node_ids'], f['node_ids'])
        self.assertEqual(selected['edge_indices'], f['edge_indices'])
        self.assertEqual(revised['source_hash'], r['source_hash'])
        self.assertIn('Regenerate this selected illustration with Image Gen from the clean current target plate', revised['edit_prompt'])
        self.assertIn('The failed bitmap is not a reference', revised['edit_prompt'])
        self.assertNotIn('Make only the requested local patch', revised['edit_prompt'])
        self.assertNotIn('reshape <-> assist', revised['edit_prompt'])
        self.assertNotIn('OBJECTS AND POSITIONS:',revised['edit_prompt'])
        self.assertNotIn('Keep the guide path', revised['edit_prompt'])
        self.assertNotIn('"x":', revised['edit_prompt'])
        names = {node['id']: node['label'] for node in r['spec']['nodes']}
        for index in f['edge_indices']:
            edge = r['spec']['edges'][index]
            relationship = json.dumps(names[edge['source']], ensure_ascii=False) + ' -> ' + json.dumps(names[edge['target']], ensure_ascii=False) + ' [' + edge['kind'] + ']'
            self.assertIn(relationship, revised['edit_prompt'])
        self.assertIn('"Local scratchpad" — memory; belongs to "Worker0 private resources"', revised['edit_prompt'])
        self.assertIn('"Shared lookup" — compute; belongs to "Shared services"', revised['edit_prompt'])
        self.assertEqual([item['role'] for item in selected['generation_inputs']], ['target_structure'])
        self.assertEqual(revised['spec'],r['spec'])

    @unittest.skipUnless(importlib.util.find_spec('PIL'),'optional Pillow')
    def test_scope_carriers_are_real_png_and_do_not_mutate_canonical_source(self):
        from PIL import Image
        r=self.result();original=copy.deepcopy(r['spec'])
        for f in r['figures']:
            if not f.get('structure_layout'):continue
            data=layout_guide.render(r,f);self.assertIsInstance(data,bytes)
            with Image.open(io.BytesIO(data)) as im:im.load();self.assertEqual(im.format,'PNG')
        self.assertEqual(r['spec'],original)
