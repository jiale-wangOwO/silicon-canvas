import io
import http.client
import json
import tempfile
import threading
import zipfile
import unittest
from pathlib import Path
from unittest.mock import patch

from silicon_canvas import bundle
from silicon_canvas import engine
from silicon_canvas import provider
from tests.test_engine import sample


class BundleTests(unittest.TestCase):
    def test_single_view_export_metadata_matches_its_selected_view_and_preserves_source(self):
        source=json.loads((Path(__file__).resolve().parents[1]/'examples'/'gpu.json').read_text(encoding='utf-8'))
        result=engine.compile_manual(source)
        selected=next(figure for figure in result['figures'] if figure['id']!=result['selected_figure_id'])
        original=json.loads(json.dumps(result))
        with zipfile.ZipFile(io.BytesIO(bundle.build(result,selected['id']))) as archive:
            portable=json.loads(archive.read('result.json'))
            self.assertEqual(portable['selected_figure_id'],selected['id'])
            self.assertEqual(portable['figure_strategy'],selected['figure_strategy'])
            self.assertEqual(portable['prompt'],selected['prompt'])
            self.assertEqual(portable['edit_prompt'],selected['edit_prompt'])
            self.assertEqual(portable['spec'],result['spec'])
            self.assertEqual([figure['id'] for figure in portable['figures']],[selected['id']])
            self.assertEqual(json.loads(archive.read('figures/'+selected['id']+'/figure-strategy.json')),selected['figure_strategy'])
        self.assertEqual(result,original)

    def test_package_keeps_upstream_research_separate_from_generation_inputs(self):
        result=engine.compile_manual({'spec':sample()})
        with zipfile.ZipFile(io.BytesIO(bundle.build(result))) as archive:
            names=archive.namelist()
            self.assertIn('figures/overview/prompt.txt',names)
            self.assertIn('figures/overview/caption.txt',names)
            self.assertFalse(any(n.startswith('references/') for n in names))
            data=json.loads(archive.read('result.json'))
            self.assertEqual(data['spec'],result['spec'])
            figure = data['figures'][0]
            self.assertEqual(figure['reference_images'], [])
            self.assertEqual(figure['inspiration_images'], [])
            self.assertTrue(figure['reference_selection']['selected'])
            self.assertTrue(all('upstream' in ref['role'] and 'not a default Image Gen input' in ref['role'] for ref in figure['inspiration_images']))
            for ref in figure['reference_selection']['selected']:
                self.assertTrue(ref['source_url'].startswith('https://'))
                self.assertTrue(ref['use_scope'])
            self.assertEqual([item['role'] for item in figure['generation_inputs']], ['target_structure'])
            self.assertEqual(figure['generation_inputs'][0]['source'], 'figures/overview/layout-guide.png')
            self.assertIn(figure['generation_inputs'][0]['source'], names)
            self.assertTrue(archive.read(figure['generation_inputs'][0]['source']).startswith(b'\x89PNG\r\n\x1a\n'))
            self.assertEqual(figure['required_verbatim_labels'], [])
            self.assertIn('payload[31:0]', archive.read('figures/overview/caption.txt').decode('utf-8'))
            self.assertIn('ready=1', archive.read('figures/overview/caption.txt').decode('utf-8'))
            self.assertIn('工程图使用 prompt.txt 和 layout-guide.png', archive.read('USE.txt').decode('utf-8'))
            self.assertNotIn('.env',names)

    def test_external_file_and_zip_path_escape_rejected(self):
        r=engine.compile_manual({'spec':sample()})
        r['figures'][0]['reference_images']=[{'path':str((Path(__file__).parent.parent/'silicon_canvas.provider.py').resolve())}]
        with self.assertRaises(ValueError):bundle.build(r)
        r=engine.compile_manual({'spec':sample()});r['figures'][0]['id']='../../escape'
        with self.assertRaises(ValueError):bundle.build(r)
