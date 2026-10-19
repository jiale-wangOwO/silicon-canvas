import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from silicon_canvas import engine
from silicon_canvas import service

BASE=Path(__file__).resolve().parents[1]/'tests/fixtures/publication_benchmark'


def read(name):
    return json.loads((BASE/name).read_text(encoding='utf-8'))


class PublicationPipelineTests(unittest.TestCase):
    def test_duplicate_expanded_gateway_triggers_bounded_semantic_repair(self):
        payload=read('requests/two_input_engine.json')
        bad=read('two-input-baseline-result.json')['spec']
        good=read('two-input-semantic-v2-result.json')['spec']
        replies=[{'data':copy.deepcopy(spec),'model':'test-model','usage':{}} for spec in [bad,good]]
        with patch('silicon_canvas.provider.complete',side_effect=replies) as complete:
            result=service.generate_result(payload,engine)
        self.assertEqual(complete.call_count,2)
        self.assertTrue(result['repaired'])
        self.assertNotIn('n_fpu',{n['id'] for n in result['spec']['nodes']})
        self.assertIn('n_alu',{n['id'] for n in result['spec']['nodes']})

    def test_data_and_control_views_partition_the_original_relationships(self):
        source=read('two-input-semantic-v2-result.json')
        result=engine.compile_manual(source)
        self.assertEqual(result['spec'],source['spec'])
        figures={f['view_role']:f for f in result['figures']}
        self.assertEqual(len(figures['datapath']['edge_indices']),14)
        self.assertEqual(len(figures['control']['edge_indices']),8)
        indices=[i for f in result['figures'] for i in f['edge_indices']]
        self.assertCountEqual(indices,range(22))
        self.assertEqual(len(indices),len(set(indices)))
        for figure in result['figures']:
            self.assertTrue(figure['layout_scene']['quality']['routes_complete'])
            for route in figure['layout_scene']['routes']:
                originals=[result['spec']['edges'][i] for i in route['members']]
                self.assertTrue(all(e['kind']==route['kind'] for e in originals))

    def test_non_dense_repeated_system_keeps_exact_views_and_internal_interfaces(self):
        source=read('gpu-baseline-result.json')
        result=engine.compile_manual(source)
        self.assertEqual(result['spec'],source['spec'])
        overview=result['figures'][0]
        objects={o['id']:o for o in overview['structure_layout']['macro_nodes']}
        self.assertEqual(objects['n_memif']['zone'],'memory')
        self.assertEqual(objects['n_host']['zone'],'external')
        self.assertEqual(overview['structure_layout']['node_to_macro']['n_rf0'],'g_cluster0')
        self.assertEqual(len(overview['layout_scene']['routes']),13)
        indices=[i for f in result['figures'] if not f['abstract'] for i in f['edge_indices']]
        self.assertCountEqual(indices,range(23))
        self.assertEqual(len(indices),len(set(indices)))
        self.assertTrue(all(f.get('structure_layout') for f in result['figures']))
        support=next(f for f in result['figures'] if f['id']=='detail-full')
        self.assertNotEqual(support['title'],overview['title'])
        self.assertNotIn('完整结构在一张图',support['summary'])
        self.assertIn(str(support['edge_count']),support['summary'])


if __name__=='__main__':
    unittest.main()
