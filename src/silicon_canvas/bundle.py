"""Portable prompt/reference package. Accept only locally compiled results."""
import copy
import io
import json
from pathlib import Path
import zipfile
import re
from . import layout_guide

ROOT=Path(__file__).resolve().parent
REFERENCE_ROOT=(ROOT/'reference_images').resolve()


def build(result,figure_id=''):
    figures=result.get('figures',[])
    if figure_id:
        figures=[f for f in figures if f['id']==figure_id]
        if not figures:raise ValueError('指定视图不存在。')
    portable=copy.deepcopy(result)
    portable['figures']=copy.deepcopy(figures)
    if figure_id:
        selected=portable['figures'][0]
        portable['selected_figure_id']=selected['id']
        for key in ('figure_strategy','visual_contract','prompt','edit_prompt'):
            if key in selected:portable[key]=copy.deepcopy(selected[key])
    buf=io.BytesIO();seen=set();sources={}
    for name in ('paper_manifest.json','isca_manifest.json','commercial_manifest.json'):
        path=REFERENCE_ROOT/name
        if path.is_file():
            for item in json.loads(path.read_text(encoding='utf-8')).get('items',[]):sources[item['path']]=item.get('source_url','')
    sources['architecture/nvidia-hopper-sm-official.png']='https://developer.nvidia.com/blog/nvidia-hopper-architecture-in-depth/'
    with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as archive:
        for f in portable['figures']:
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',f['id']):raise ValueError('视图 ID 无效。')
            folder='figures/'+f['id']+'/'
            archive.writestr(folder+'prompt.txt',f['prompt'])
            archive.writestr(folder+'caption.txt',f['caption'])
            archive.writestr(folder+'edit-prompt.txt',f['edit_prompt'])
            if f.get('review_task'):
                archive.writestr(folder+'review-prompt.txt',f['review_task']['prompt'])
                archive.writestr(folder+'review-manifest.json',json.dumps({k:v for k,v in f['review_task'].items() if k!='prompt'},ensure_ascii=False,indent=2))
            if f.get('diagram_design'):
                archive.writestr(folder+'diagram-design.json',json.dumps(f['diagram_design'],ensure_ascii=False,indent=2))
            if f.get('visual_contract'):
                archive.writestr(folder+'visual-contract.json',json.dumps(f['visual_contract'],ensure_ascii=False,indent=2))
            if f.get('figure_strategy'):
                archive.writestr(folder+'figure-strategy.json',json.dumps(f['figure_strategy'],ensure_ascii=False,indent=2))
            if f.get('behavior_plan'):
                archive.writestr(folder+'semantic-plan.json',json.dumps(f['behavior_plan'],ensure_ascii=False,indent=2))
            guide=layout_guide.render(result,f)
            if guide:
                guide_name = 'composition-guide.png' if f.get('representation') in {'product_render', 'system_illustration'} else 'layout-guide.png'
                archive.writestr(folder+guide_name,guide)
                f['layout_guide']=folder+guide_name
                for image_input in f.get('generation_inputs',[]):
                    if image_input.get('role') in {'target_structure', 'composition_reference'}:image_input['source']=f['layout_guide']
            if f.get('render_brief'):
                archive.writestr(folder+'render-brief.json',json.dumps(f['render_brief'],ensure_ascii=False,indent=2))
                for step in f.get('generation_steps', []):
                    if re.fullmatch(r'[a-z][a-z0-9_-]{0,39}', step['id']):
                        archive.writestr(folder+step['id']+'-prompt.txt',step['prompt'])
            if f.get('algorithm_flow_plan'):
                archive.writestr(folder+'algorithm-flow-plan.json',json.dumps(f['algorithm_flow_plan'],ensure_ascii=False,indent=2))
            for ref in f.get('reference_images',[]):
                path=Path(ref['path']).resolve()
                if not path.is_relative_to(REFERENCE_ROOT) or path.suffix.lower() not in {'.png','.jpg','.jpeg','.webp'} or not path.is_file():
                    raise ValueError('参考图路径无效。')
                rel='references/'+path.name
                if rel not in seen:archive.write(path,rel);seen.add(rel)
                ref['source_url']=sources.get(path.relative_to(REFERENCE_ROOT).as_posix(),'')
                ref['path']=rel
        archive.writestr('result.json',json.dumps(portable,ensure_ascii=False,indent=2))
        archive.writestr('USE.txt','先选择 primary=true 的主图；technical_annex 是按需使用的精确附图。最终图片由 Image Gen 生成。\n商业渲染与系统插画默认用 prompt.txt 或 complete-prompt.txt 一次生成完整图文；explanation_plan 说明读者问题与可见功能、上下文和关系。只有明确要保留已批准主体或分步精修时才提供 refine-prompt.txt，编辑目标是真实成图。\ncomposition-guide.png 是可选取景参考，不是实际几何、制造图或编辑目标。逻辑功能区、器件符号与接口可解释源规格，比例与位置是概念表现；完整事实及未显示关系保存在 result.json.spec、图注与技术附图。\n算法数据流主图使用 prompt.txt 直接生图，无需 layout-guide.png；algorithm-flow-plan.json 记录张量/算子角色、源形状、并行汇合、状态循环、驻留与依赖列。generation_inputs 为空表示文本方案，不要附硬件底稿强行描图。\n工程图使用 prompt.txt 和 layout-guide.png，按 generation_inputs 的角色和编号附图，保持模块、归属、端点与方向。工程图缺少合格底稿时查看预检与限制。\n实际成图按所选用途核对解释能力、源关系、文字与审美，编译和底稿检查不等于图片通过。参考厂商与论文的画法，不继承其拓扑、数量、工艺或品牌。\n')
    return buf.getvalue()
