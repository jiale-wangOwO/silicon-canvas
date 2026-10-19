"""Whole subjects and device relationships survive the editorial shot choice."""
import copy
import unittest

from silicon_canvas import engine, render_brief, render_strategy


def source(nodes, groups=(), edges=()):
    return engine.normalize_spec({"title":"Concept", "category":"architecture",
        "nodes":nodes, "groups":list(groups), "edges":list(edges)})


def compile_view(spec, description, mode="auto"):
    settings=engine.normalize_settings({"representation":"system_illustration", "scene":"concept", "explanatory_mode":mode})
    fig=render_brief.primary(spec,"system_illustration")
    prompt=render_brief.compile_figure(fig,spec,settings,description)
    return fig['render_brief'], prompt


class RenderSubjectTests(unittest.TestCase):
    def test_whole_package_ownership_is_stable_when_contained_parts_are_named_first(self):
        spec=source([{'id':'die','label':'Compute die','kind':'compute','group':'pkg'},
                     {'id':'io','label':'Conversion module','kind':'io','group':'pkg'}],
                    [{'id':'pkg','label':'Package'}],
                    [{'source':'die','target':'io','kind':'data'}])
        before=copy.deepcopy(spec)
        descriptions=(
            'A package illustration with a compute bare die and conversion module inside.',
            'Show a compute bare die and conversion module inside one complete package.',
            'A complete package containing a bare die and conversion module.',
            'Show the conversion module and exposed die within the package.',
            '展示计算裸片和转换模块位于同一封装内的整体结构。',
            '封装内包含计算裸片和转换模块，展示整个封装。',
        )
        for description in descriptions:
            plan=render_strategy.subject_plan(description,spec)
            self.assertEqual(plan['scale'],'package',description)
            self.assertEqual(plan['kind'],'package_assembly_concept',description)
            self.assertEqual(plan['source_ownership'][0]['members'],['die','io'])
        self.assertEqual(spec,before)

    def test_explicit_contained_die_closeup_or_only_part_still_wins(self):
        spec=source([{'id':'die','label':'Bare die','kind':'compute','group':'pkg'}],
                    [{'id':'pkg','label':'Package'}])
        for description in (
            'A close-up of the bare die inside the package.',
            'Show only the bare die inside the complete package.',
            'Focus on the exposed die within the package.',
            'A bare die hero inside a package.',
            '只展示封装内的裸片。',
            '封装中的裸片特写。',
        ):
            self.assertEqual(render_strategy.subject_plan(description,spec)['scale'],'die',description)
        self.assertEqual(render_strategy.subject_plan('No close-up of the bare die; show the complete package containing it.',spec)['scale'],'package')

    def test_style_reference_does_not_replace_source_peer_system_with_a_chip(self):
        spec=source([{'id':'a','label':'Compute node A','kind':'compute','group':'sys'},
                     {'id':'b','label':'Compute node B','kind':'compute','group':'sys'},
                     {'id':'hub','label':'Shared switch','kind':'io','group':'sys'}],
                    [{'id':'sys','label':'Compute system'}],
                    [{'source':'a','target':'hub','kind':'relation'},
                     {'source':'b','target':'hub','kind':'relation'}])
        before=copy.deepcopy(spec)
        for description in (
            'An illustration of the compute system.',
            'A chip-launch-style illustration of the compute system.',
            'A chip launch style illustration of the compute system.',
            'A system illustration in the style of a chip.',
            '用芯片发布会风格展示这个计算节点系统。',
        ):
            plan=render_strategy.subject_plan(description,spec)
            self.assertEqual(plan['scale'],'system',description)
            self.assertEqual(plan['kind'],'system_assembly_concept',description)
            self.assertCountEqual(plan['source_device_node_ids'],['a','b','hub'])
        self.assertEqual(spec,before)

    def test_style_reference_does_not_make_plain_chip_resources_into_devices(self):
        spec=source([{'id':'cpu','label':'CPU','kind':'compute'},
                     {'id':'cache','label':'Shared cache','kind':'memory'}])
        plan=render_strategy.subject_plan('A chip-launch-style illustration of a logical processor system.',spec)
        self.assertEqual(plan['kind'],'generic_package_concept')
        self.assertEqual(plan['source_device_node_ids'],[])

    def test_board_appearance_can_have_generic_minor_detail_without_new_major_hardware(self):
        spec=source([{'id':'a','label':'Compute package A','kind':'compute','group':'board'}],
                    [{'id':'board','label':'Accelerator board'}])
        plan=render_strategy.subject_plan('An accelerator board concept image.',spec)
        self.assertEqual(plan['scale'],'board')
        self.assertIn('unlabeled generic passive components, fasteners and surface details',plan['instruction'])
        self.assertIn('illustrative finish, not verified circuitry',plan['instruction'])
        self.assertIn('Do not invent additional major compute or memory objects',plan['instruction'])
        self.assertIn('interface families, product identifiers or layout parameters',plan['instruction'])
        self.assertEqual(plan['source_physical_part_ids'],['a'])

    def test_requested_package_owns_contained_die_instead_of_becoming_the_die(self):
        spec=source([{'id':'die','label':'Compute die','kind':'compute','group':'pkg'},
                     {'id':'io','label':'Optical I/O','kind':'io','group':'pkg'}],
                    [{'id':'pkg','label':'Package'}],
                    [{'source':'die','target':'io','kind':'data'}])
        before=copy.deepcopy(spec)
        brief,prompt=compile_view(spec,'A package technical illustration. The package contains a compute die and optical I/O.')
        self.assertEqual(brief['subject']['kind'],'package_assembly_concept')
        self.assertEqual(brief['explanation_plan']['mode'],'assembly')
        self.assertEqual(len(brief['visible_content']['regions']),2)
        self.assertEqual(brief['visible_content']['deferred_edge_indices'],[])
        self.assertNotIn('Do not collapse the system into a single chip',prompt)
        self.assertEqual(spec,before)

    def test_system_roles_keep_peer_objects_and_shared_hub_without_a_chip_base(self):
        spec=source([{'id':'n'+str(i),'label':'Inference node '+str(i),'kind':'compute','group':'system'} for i in range(4)]
                    +[{'id':'switch','label':'High-speed switch','kind':'io','group':'system'},
                      {'id':'storage','label':'Shared storage','kind':'memory'}],
                    [{'id':'system','label':'Inference system'}],
                    [{'source':'n'+str(i),'target':'switch','kind':'relation'} for i in range(4)]
                    +[{'source':'switch','target':'storage','kind':'relation'}])
        before=copy.deepcopy(spec)
        brief,prompt=compile_view(spec,'An inference system for a business presentation. Four equal inference nodes connect to a central switch and shared storage.')
        self.assertEqual(brief['subject']['plan']['scale'],'system')
        self.assertEqual(brief['explanation_plan']['mode'],'assembly')
        self.assertEqual(len(brief['visible_content']['regions']),6)
        self.assertEqual(brief['visible_content']['deferred_edge_indices'],[])
        self.assertIn('Never place these separate system nodes on one chip base',prompt)
        self.assertIn('Inference node 0 ~ High-speed switch',prompt)
        self.assertIn('High-speed switch ~ Shared storage',prompt)
        self.assertEqual(spec,before)

    def test_logical_chip_resources_do_not_establish_a_multidevice_system(self):
        spec=source([{'id':'cpu','label':'CPU','kind':'compute'}, {'id':'cache','label':'Shared cache','kind':'memory'}])
        brief,_=compile_view(spec,'SoC product rendering. An external server supplies work.')
        self.assertEqual(brief['subject']['kind'],'generic_package_concept')
        self.assertEqual(brief['subject']['plan']['source_device_node_ids'],[])

    def test_rack_board_and_die_choose_different_scale_appropriate_shots(self):
        spec=source([{'id':'part','label':'Product','kind':'compute'}])
        rack,_=compile_view(spec,'A rack product hero. No text.')
        board,_=compile_view(spec,'An accelerator board product hero. No text.')
        die,_=compile_view(spec,'A bare die hero on a package substrate. No text.')
        self.assertIn('corrected verticals',rack['art_direction']['camera'])
        self.assertIn('board plane',board['art_direction']['camera'])
        self.assertEqual(die['subject']['kind'],'bare_die_concept')
        self.assertEqual(rack['explanation_plan']['mode'],'hero')
        self.assertNotEqual(board['art_direction']['camera'],rack['art_direction']['camera'])

    def test_explicit_camera_and_finish_exclusions_override_the_shot_default(self):
        spec=source([{'id':'p','label':'Package','kind':'compute'}])
        brief,prompt=compile_view(spec,'A package hero. No top-down view. No metal finish. No dark background.')
        art=brief['art_direction']
        self.assertIn('near-level',art['camera'])
        self.assertNotIn('satin metal',art['materials'])
        self.assertNotIn('dark charcoal',art['background'])
        self.assertIn('Equivalent objects retain the same finish',prompt)

    def test_explicit_hero_copy_does_not_gain_a_disclosure_or_inventory(self):
        spec=source([{'id':'p','label':'Product','kind':'compute'}])
        brief,prompt=compile_view(spec,'A product hero with short English labels.')
        self.assertEqual(brief['visible_content']['regions'],[])
        self.assertIn("Do not add a marketing subtitle",prompt)
        self.assertIn("a default 'Functional concept' badge",prompt)
        self.assertNotIn('Functional content (',prompt)

    def test_unlabelled_board_hero_keeps_actual_physical_parts_without_printing_inventory(self):
        spec=source([{'id':'a','label':'Compute package A','kind':'compute','group':'board'},
                     {'id':'b','label':'Compute package B','kind':'compute','group':'board'}],
                    [{'id':'board','label':'Accelerator board'}])
        brief,prompt=compile_view(spec,'An accelerator board product hero. No text.')
        self.assertEqual(brief['visible_content']['regions'],[])
        self.assertCountEqual(brief['subject']['plan']['source_physical_part_ids'],['a','b'])
        self.assertIn('Compute package A',prompt)
        self.assertIn('object identities and counts, not requested printed labels',prompt)


if __name__=='__main__': unittest.main()
