"""Removing typography never removes the subject; appearance edits keep scope."""
import unittest

from silicon_canvas import engine, render_brief


def system():
    return engine.normalize_spec({'title':'Inference system','category':'architecture',
        'groups':[{'id':'pod','label':'Inference system'}],
        'nodes':[{'id':'p'+str(i),'label':'Inference node '+str(i),'kind':'compute','group':'pod'} for i in range(4)]
              +[{'id':'switch','label':'High-speed switch','kind':'io','group':'pod'},
                {'id':'store','label':'Shared storage','kind':'memory'}],
        'edges':[{'source':'p'+str(i),'target':'switch','kind':'relation'} for i in range(4)]})


def compile_view(spec,description,mode='auto',feedback=''):
    settings=engine.normalize_settings({'representation':'system_illustration','scene':'concept','explanatory_mode':mode})
    fig=render_brief.primary(spec,'system_illustration')
    prompt=render_brief.compile_figure(fig,spec,settings,description,visual_feedback=feedback)
    return fig['render_brief'],prompt


class TextAndScopeTests(unittest.TestCase):
    def test_no_text_system_hero_keeps_supplied_objects_as_nonprinted_identities(self):
        spec=system()
        brief,prompt=compile_view(spec,'An inference system product hero. No text.')
        self.assertEqual(brief['explanation_plan']['mode'],'hero')
        self.assertEqual(brief['visible_content']['regions'],[])
        for n in spec['nodes']: self.assertIn(n['label'],prompt)
        self.assertIn('object identities and counts, not requested printed labels',prompt)

    def test_no_text_assembly_has_no_competing_typography_instructions(self):
        brief,prompt=compile_view(system(),'An inference system. No text.',mode='assembly')
        self.assertEqual(brief['explanation_plan']['mode'],'assembly')
        self.assertIn('Text-free artwork',prompt)
        self.assertIn('do not print these names',prompt)
        self.assertNotIn('exact headings',prompt)
        self.assertNotIn('concise group headings',prompt)
        self.assertNotIn('short labels beside',prompt)
        self.assertIn('Inference node 3',prompt)

    def test_background_only_feedback_does_not_change_the_requested_hero(self):
        spec=system()
        brief,prompt=compile_view(spec,'A rack product hero. No text.',feedback='Change to a light background.')
        self.assertEqual(brief['explanation_plan']['mode'],'hero')
        self.assertIn('light neutral',brief['art_direction']['background'])
        self.assertIn('Inference node 3',prompt)

    def test_explicit_explanation_feedback_can_still_change_scope(self):
        brief,prompt=compile_view(system(),'An inference system product hero.',feedback='Explain the assembled system and its connections.')
        self.assertEqual(brief['explanation_plan']['mode'],'assembly')
        self.assertIn('Inference node 3',prompt)


if __name__=='__main__': unittest.main()
