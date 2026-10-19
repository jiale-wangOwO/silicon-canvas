import copy
import unittest

from silicon_canvas import engine
from silicon_canvas import presentation
from tests.test_engine import sample


class PresentationTests(unittest.TestCase):
    def dense(self):
        s = sample()
        s['category'] = 'microarchitecture'
        s['groups'] += [{'id': 'other', 'label': 'Other path'}]
        for i in range(21):
            s['nodes'].append({'id': f'x{i}', 'label': f'Unit {i}', 'kind': 'compute', 'group': 'g' if i < 10 else 'other'})
            s['edges'].append({'source': 'buf', 'target': f'x{i}', 'kind': 'data', 'label': f'data{i}'})
        return engine.normalize_spec(s)

    def test_partition_preserves_all_endpoints_edges_and_parameters(self):
        s = self.dense()
        original = copy.deepcopy(s)
        for density, (node_budget, edge_budget) in presentation.BUDGETS.items():
            p = presentation.build_plan(s, density)
            exact = [f for f in p['figures'] if not f['abstract']]
            occurrences = [i for f in exact for i in f['edge_indices']]
            self.assertCountEqual(occurrences, range(len(s['edges'])))
            self.assertEqual(p['coverage']['missing_nodes'], [])
            self.assertEqual(p['coverage']['missing_edges'], [])
            for f in exact:
                self.assertLessEqual(len(f['node_ids']), node_budget)
                self.assertLessEqual(len(f['edge_indices']), edge_budget)
                self.assertEqual(len(f['node_ids']), len(set(f['node_ids'])))
                for index in f['edge_indices']:
                    self.assertIn(s['edges'][index]['source'], f['node_ids'])
                    self.assertIn(s['edges'][index]['target'], f['node_ids'])
        self.assertEqual(s, original)

    def test_abstract_relationships_are_only_projections_of_real_edges(self):
        s = self.dense()
        p = presentation.build_plan(s)
        f = p['figures'][0]
        self.assertTrue(f['abstract'])
        owners = {nid: n['id'] for n in f['macro_nodes'] for nid in n['members']}
        for link in f['macro_edges']:
            self.assertTrue(link['members'])
            for i in link['members']:
                e = s['edges'][i]
                self.assertEqual(owners[e['source']], link['source'])
                self.assertEqual(owners[e['target']], link['target'])
                self.assertEqual(e['kind'], link['kind'])

    def test_no_group_means_no_invented_overview_hierarchy(self):
        s = self.dense()
        s['groups'] = []
        for n in s['nodes']:
            n['group'] = ''
        p = presentation.build_plan(s)
        self.assertFalse(any(f['abstract'] for f in p['figures']))
        self.assertEqual(p['coverage']['nodes_covered'], len(s['nodes']))

    def test_overview_without_memory_hub_keeps_real_subsystem_relationships(self):
        s=self.dense()
        for n in s['nodes']:
            if n['kind']=='memory':n['kind']='compute'
        p=presentation.build_plan(s,'low')
        f=p['figures'][0]
        self.assertTrue(f['abstract'])
        self.assertFalse(f['focal_hub'])
        self.assertTrue(f['macro_edges'])
        self.assertTrue(all(e['members'] for e in f['macro_edges']))

    def test_normal_gpu_overview_keeps_fourteen_modules_in_one_view(self):
        s=sample()
        s['category']='architecture'
        s['nodes']=[{'id':f'n{i}','label':f'Unit {i}','kind':'compute','group':'g'} for i in range(14)]
        s['edges']=[{'source':f'n{i}','target':f'n{i+1}','kind':'data'} for i in range(13)]
        r=engine.compile_manual({'spec':s})
        self.assertEqual(r['render_plan']['strategy'],'single')
        self.assertEqual(r['figures'][0]['node_count'],14)
        self.assertEqual(r['render_plan']['coverage']['edges_covered'],13)

    def test_per_role_fill_and_unfilled_groups_are_explicit_in_prompt(self):
        s=sample()
        s['category']='architecture'
        s['nodes'].append({'id':'controller','label':'Control','kind':'control','group':'g'})
        r=engine.compile_manual({'spec':s})
        prompt=r['prompt']
        palette = engine.STYLES[r['settings']['style']]['palette']
        self.assertIn('compute fill ' + palette['primary'], prompt)
        self.assertIn('storage fill ' + palette['secondary'], prompt)
        self.assertIn('sparse control fill ' + palette['control'], prompt)
        self.assertIn('interfaces stay white', prompt)
        self.assertIn('unfilled ownership boundaries ' + palette['container'], prompt)
        self.assertIn('Containers and same-hardware details have white bodies with light headings', prompt)
        self.assertIn('"Control" — control; belongs to "NPU"', prompt)
        self.assertIn('"Buffer" — memory; belongs to "NPU"', prompt)
        self.assertIn('"MAC" — compute; belongs to "NPU"', prompt)
        self.assertEqual(r['figures'][0]['structure_layout']['source_ownership']['controller'], 'g')
        self.assertEqual(r['spec'], engine.normalize_spec(s))
        self.assertEqual([index for f in r['figures'] if not f['abstract'] for index in f['edge_indices']], [0, 1, 2])
        self.assertNotIn('buf: row ',prompt)
        self.assertNotIn('controller appearance:', prompt)

    def test_memory_controller_is_not_drawn_as_banked_storage(self):
        node={'id':'mc','label':'Memory Controllers','kind':'memory','detail':'handles 8 banks'}
        self.assertEqual(presentation.visual_role(node),'control')
        self.assertEqual(presentation.hardware_glyph(node)['shape'],'compact-control-block')

    def test_dense_self_loops_parallel_edges_and_isolated_resources_survive(self):
        s = self.dense()
        s['edges'] += [{'source':'x0','target':'x0','kind':'control','label':'hold'}, {'source':'buf','target':'x0','kind':'control','label':'valid'}]
        s['nodes'].append({'id':'isolated','label':'Unconnected resource','kind':'memory','group':'', 'detail':'capacity=128 B', 'origin':'given', 'rationale':'','evidence':''})
        p = presentation.build_plan(s)
        owned = [i for f in p['figures'] if not f['abstract'] for i in f['edge_indices']]
        self.assertCountEqual(owned, range(len(s['edges'])))
        self.assertEqual(p['coverage']['missing_nodes'], [])

    def test_selected_detail_edit_does_not_import_other_views(self):
        s = self.dense()
        r = engine.compile_manual({'spec':s})
        detail = next(f for f in r['figures'] if f['kind']=='detail')
        r2 = engine.compile_result(s, r['settings'], feedback='Increase spacing', figure_id=detail['id'])
        self.assertEqual(r2['selected_figure_id'], detail['id'])
        self.assertIn(detail['title'], r2['edit_prompt'])
        self.assertNotIn('overview of ', r2['edit_prompt'])
        self.assertEqual(r2['spec']['nodes'], r['spec']['nodes'])

    def test_repeated_compile_is_deterministic_and_grid_has_no_collisions(self):
        s = self.dense()
        p1 = presentation.build_plan(s)
        p2 = presentation.build_plan(s)
        self.assertEqual(p1,p2)
        for f in p1['figures']:
            slots = [(x['row'],x['column']) for x in f['positions'].values()]
            self.assertEqual(len(slots),len(set(slots)))
