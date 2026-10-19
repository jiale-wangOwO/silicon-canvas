"""Optional deterministic layout reference, not the requested Image Gen output.

Pillow is optional: prompt compilation remains standard-library only. This module
creates a fresh reference from graph geometry; it never edits a user's image.
"""
import io
import math
import re
from . import presentation
from . import structure_scene
from pathlib import Path


def render(result,figure):
    if figure.get('structure_layout',{}).get('type')=='behavioral':
        from . import behavior_guide
        return behavior_guide.render(result,figure)
    if figure.get('algorithm_flow_plan'):
        # Mathematical roles/layers are not a hardware target plate. Returning
        # no guide also prevents the generic dataflow fallback from tracing it.
        return None
    if figure.get('representation') in {'product_render', 'system_illustration'}:
        from . import render_guide
        return render_guide.render(result, figure)
    if figure.get('structure_layout',{}).get('type')=='publication':
        from . import publication_render
        return publication_render.render(result,figure)
    if figure.get('structure_layout'):return structure_scene.render(result,figure)
    if result['spec']['category'] not in {'architecture','microarchitecture','memory','dataflow','pipeline'}:return None
    try:
        from PIL import Image,ImageDraw,ImageFont
    except ImportError:
        return None
    spec=result['spec'];abstract=figure['abstract'];F=20
    if abstract:return None
    # A flow-only guide cannot represent a full hierarchical system boundary.
    # Let the scoped prompt preserve containment for these architecture views.
    if spec['category']=='architecture' and spec['groups'] and not figure.get('main_group'):return None
    source={n['id']:n for n in spec['nodes']}
    nodes=figure.get('macro_nodes',[]) if abstract else [source[n] for n in figure['node_ids']]
    links=figure.get('macro_edges',[]) if abstract else [spec['edges'][i] for i in figure['edge_indices']]
    from .publication_render import font_path as shared_font_path
    font_path=shared_font_path()
    if font_path is None:return None
    font=ImageFont.truetype(str(font_path),F,layout_engine=ImageFont.Layout.BASIC);small=ImageFont.truetype(str(font_path),15,layout_engine=ImageFont.Layout.BASIC)
    positions=figure['positions'];dims=figure['dimensions']
    columns=sorted({positions[n['id']]['column'] for n in nodes})
    widths={c:max(dims[n['id']]['width_f']*F for n in nodes if positions[n['id']]['column']==c) for c in columns}
    # Size each lane from its actual symbols. A global RF-width stride makes
    # every later compute gap unnecessarily wide.
    x_by_column={columns[0]:28};row_stride=100
    for previous,column in zip(columns,columns[1:]):
        labels=[e['label'] for e in links if positions[e['source']]['column']==previous and positions[e['target']]['column']==column]
        word_width=max((small.getlength(w) for label in labels for w in label.split()),default=0)
        gap=max(55,min(widths[previous],widths[column])*.45,word_width+22)
        x_by_column[column]=x_by_column[previous]+widths[previous]+gap
    boxes={}
    for n in nodes:
        w=dims[n['id']]['width_f']*F;h=dims[n['id']]['height_f']*F
        x=x_by_column[positions[n['id']]['column']]
        if n['kind']=='compute':x+=(widths[positions[n['id']]['column']]-w)/2
        cy=120+(positions[n['id']]['row']-1)*row_stride
        boxes[n['id']]=(x,cy-h/2,x+w,cy+h/2)
    # Tall banked resources cannot overlap a peer on the same layout column.
    for column in sorted({positions[n['id']]['column'] for n in nodes}):
        previous=-1e9
        for nid in sorted((n['id'] for n in nodes if positions[n['id']]['column']==column),key=lambda i:positions[i]['row']):
            x0,y0,x1,y1=boxes[nid]
            if y0<previous+24:
                shift=previous+24-y0;y0+=shift;y1+=shift
            boxes[nid]=(x0,y0,x1,y1);previous=y1
    width=math.ceil(max(b[2] for b in boxes.values())+28)
    bottom=max(b[3] for b in boxes.values())
    height=math.ceil(bottom+65+len(links)*3)
    canvas=Image.new('RGB',(width,height),'white');draw=ImageDraw.Draw(canvas)
    palette=result['style_prompt'].split('Palette: ')[1].split('\n')[0]
    colors={part.split()[0]:part.split()[1].rstrip('.') for part in palette.split('; ')}
    ink=colors.get('ink','#202020');routes=[]
    def point(nid,description):
        x0,y0,x1,y1=boxes[nid]
        if 'bottom' in description:return ((x0+x1)/2,y1)
        y=(y0+y1)/2
        if 'upper' in description:y=y0+(y1-y0)*.3
        if 'lower' in description:y=y0+(y1-y0)*.7
        distinct=re.search(r'distinct attachment (\d+) of (\d+)',description)
        if distinct:y=y0+(y1-y0)*int(distinct[1])/(int(distinct[2])+1)
        return (x1 if 'right' in description else x0,y)
    def crosses(path):
        for a,b in zip(path,path[1:]):
            for nid,box in boxes.items():
                if nid in (edge['source'],edge['target']):continue
                x0,y0,x1,y1=box
                if a[0]==b[0] and x0<a[0]<x1 and max(min(a[1],b[1]),y0)<min(max(a[1],b[1]),y1):return True
                if a[1]==b[1] and y0<a[1]<y1 and max(min(a[0],b[0]),x0)<min(max(a[0],b[0]),x1):return True
        return False
    for i,edge in enumerate(links):
        if abstract:return None  # Exact route previews only, no invented macro pins.
        ports=figure['attachment_points'][i];a=point(edge['source'],ports['source']);b=point(edge['target'],ports['target'])
        if ports['lane'].startswith('outer'):
            y=bottom+32+i*3;path=[a,(a[0],y),(b[0],y),b]
        else:
            fanout=sum(e['source']==edge['source'] for e in links)
            fanin=sum(e['target']==edge['target'] for e in links)
            mid=a[0]+12 if fanout>1 else b[0]-12 if fanin>1 else (a[0]+b[0])/2
            path=[a,(mid,a[1]),(mid,b[1]),b]
        path=[point for i,point in enumerate(path) if i==0 or point!=path[i-1]]
        k=1
        while k<len(path)-1:
            if (path[k-1][0]==path[k][0]==path[k+1][0]) or (path[k-1][1]==path[k][1]==path[k+1][1]):path.pop(k)
            else:k+=1
        if crosses(path):return None  # Never supply an invalid guide as authority.
        routes.append((edge,path))
    def wrap(text,width,font):
        lines=[];current=''
        for word in text.replace(' / ',' / ').split():
            trial=(current+' '+word).strip()
            if current and draw.textlength(trial,font=font)>width:lines.append(current);current=word
            else:current=trial
        if current:lines.append(current)
        return lines
    def arrow(a,b):
        dx=b[0]-a[0];dy=b[1]-a[1];length=math.hypot(dx,dy)
        if not length:return
        ux,uy=dx/length,dy/length
        draw.polygon([b,(b[0]-8*ux+3*uy,b[1]-8*uy-3*ux),(b[0]-8*ux-3*uy,b[1]-8*uy+3*ux)],fill=ink)
    for edge,path in routes:
        from . import edge_semantics
        dashed=edge_semantics.stroke(edge)=='dashed' and spec['category'] not in {'fsm','algorithm'}
        for a,b in zip(path,path[1:]):
            if dashed:
                length=math.dist(a,b)
                for distance in range(0,math.ceil(length),9):
                    if not length:continue
                    t0=distance/length;t1=min((distance+5)/length,1)
                    draw.line([(a[0]+(b[0]-a[0])*t0,a[1]+(b[1]-a[1])*t0),(a[0]+(b[0]-a[0])*t1,a[1]+(b[1]-a[1])*t1)],fill=ink,width=1)
            else:draw.line(path,fill=ink,width=2);break
        arrow(path[-2],path[-1])
        if edge['label']:
            horizontal=[(a,b) for a,b in zip(path,path[1:]) if a[1]==b[1]]
            fanout=sum(e['source']==edge['source'] for e,_ in routes)
            fanin=sum(e['target']==edge['target'] for e,_ in routes)
            if horizontal and fanout>1:a,b=horizontal[-1]
            elif horizontal and fanin>1:a,b=horizontal[0]
            else:a,b=max(horizontal,key=lambda pair:abs(pair[1][0]-pair[0][0])) if horizontal else (path[0],path[1])
            available=max(20,abs(b[0]-a[0])-8)
            label_lines=wrap(edge['label'],available,small)
            if any(draw.textlength(line,font=small)>available for line in label_lines):return None
            cx=(a[0]+b[0])/2;y=a[1]-len(label_lines)*20-4
            for line in label_lines:
                tw=draw.textlength(line,font=small)
                draw.rectangle((cx-tw/2-2,y,cx+tw/2+2,y+20),fill='white')
                draw.text((cx-tw/2,y),line,font=small,fill=ink);y+=20
    for n in nodes:
        x0,y0,x1,y1=boxes[n['id']];glyph=figure['glyphs'][n['id']]
        role=presentation.visual_role(n)
        fill=colors.get('secondary','#eeeeee') if role=='memory' else colors.get('primary','#ffffff') if role=='compute' else '#ffffff'
        draw.rectangle((x0,y0,x1,y1),fill=fill,outline=ink,width=1)
        lines=wrap(n['label'],x1-x0-12,font)
        if any(draw.textlength(line,font=font)>x1-x0-12 for line in lines):return None
        if glyph['shape']!='banked-memory' and len(lines)*23>y1-y0-6:return None
        if glyph['shape']=='banked-memory':
            header=70;top=y0+header
            for bank in range(glyph['bank_count']):
                by=top+bank*(y1-top-8)/glyph['bank_count']
                draw.rectangle((x0+8,by,x1-8,by+(y1-top-8)/glyph['bank_count']-3),outline=ink,width=1)
            ty=y0+5
            params=next((part.strip() for part in n.get('detail','').split(';') if re.search(r'\d+\s+banks',part)), '')
            if params:
                micro=ImageFont.truetype(str(font_path),14,layout_engine=ImageFont.Layout.BASIC)
                draw.text((x0+8,y0+50),params,font=micro,fill=ink)
        else:ty=(y0+y1)/2-len(lines)*23/2
        for line in lines:
            tw=draw.textlength(line,font=font);draw.text(((x0+x1-tw)/2,ty),line,font=font,fill=ink);ty+=23
        scope=re.search(r'core-shared|private',n.get('detail',''),re.I)
        if scope and n['kind']!='memory':
            text=scope.group(0);tw=draw.textlength(text,font=small)
            draw.text(((x0+x1-tw)/2,y0-24),text,font=small,fill=ink)
    # Small scope tags, not artificial parent domains around context resources.
    groups={g['id']:g for g in spec['groups']}
    core=[n for n in nodes if n['id'] not in figure.get('context_nodes',[])]
    if figure.get('main_group') in groups and core:
        bounds=[boxes[n['id']] for n in core];x=min(b[0] for b in bounds);y=min(b[1] for b in bounds)-38
        draw.text((x,y),groups[figure['main_group']]['label'],font=small,fill=ink)
    output=io.BytesIO();canvas.save(output,format='PNG')
    return output.getvalue()
