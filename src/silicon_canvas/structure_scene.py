"""Geometry carrier for Image Gen: ownership regions, replica slots, clear routes.

This creates a new reference image. It is not the requested Image Gen output.
The routing grid is visual geometry only, never an inferred bus or hardware port.
"""
from collections import defaultdict
import heapq
import io
import math
from pathlib import Path
import re


def compact_path(points, tolerance=1e-7):
    """Remove zero-length/collinear geometry without changing a connection."""
    compact = []
    for point in points:
        point = list(point)
        if compact and math.dist(point, compact[-1]) <= tolerance:
            continue
        compact.append(point)
        while len(compact) > 2:
            a, b, c = compact[-3:]
            same_x = max(a[0], b[0], c[0]) - min(a[0], b[0], c[0]) <= tolerance
            same_y = max(a[1], b[1], c[1]) - min(a[1], b[1], c[1]) <= tolerance
            # A collinear reversal caused by grid snapping is redundant too:
            # its shortcut is a subset of the already clear painted segment.
            # Keep a true out-and-back loop whose endpoints coincide.
            if not ((same_x or same_y) and math.dist(a, c) > tolerance):
                break
            compact.pop(-2)
    return compact


def _crosses_rect(a, b, rect, clearance=0):
    x0, y0, x1, y1 = rect
    x0 -= clearance; y0 -= clearance; x1 += clearance; y1 += clearance
    if abs(a[0] - b[0]) < .005:
        return x0 + .005 < a[0] < x1 - .005 and max(min(a[1], b[1]), y0) < min(max(a[1], b[1]), y1) - .005
    if abs(a[1] - b[1]) < .005:
        return y0 + .005 < a[1] < y1 - .005 and max(min(a[0], b[0]), x0) < min(max(a[0], b[0]), x1) - .005
    return True


def _paths_contact(points, previous):
    for a, b in zip(points, points[1:]):
        for path in previous:
            for c, d in zip(path, path[1:]):
                if abs(a[0] - b[0]) < .005 and abs(c[1] - d[1]) < .005:
                    if min(c[0], d[0]) - .1 <= a[0] <= max(c[0], d[0]) + .1 and min(a[1], b[1]) - .1 <= c[1] <= max(a[1], b[1]) + .1:
                        return True
                elif abs(a[1] - b[1]) < .005 and abs(c[0] - d[0]) < .005:
                    if min(a[0], b[0]) - .1 <= c[0] <= max(a[0], b[0]) + .1 and min(c[1], d[1]) - .1 <= a[1] <= max(c[1], d[1]) + .1:
                        return True
                elif abs(a[0] - b[0]) < .005 and abs(c[0] - d[0]) < .005 and abs(a[0] - c[0]) < .1:
                    if max(min(a[1], b[1]), min(c[1], d[1])) <= min(max(a[1], b[1]), max(c[1], d[1])) + .1:
                        return True
                elif abs(a[1] - b[1]) < .005 and abs(c[1] - d[1]) < .005 and abs(a[1] - c[1]) < .1:
                    if max(min(a[0], b[0]), min(c[0], d[0])) <= min(max(a[0], b[0]), max(c[0], d[0])) + .1:
                        return True
    return False


def _pair(links, exact):
    if exact:return [dict(e) for e in links]
    used=set();out=[]
    for i,e in enumerate(links):
        if i in used:continue
        item=dict(e);used.add(i)
        reverse=next((j for j,r in enumerate(links) if j not in used and e['kind']=='data' and r['source']==e['target'] and r['target']==e['source'] and r['kind']==e['kind']),None)
        if reverse is not None:
            used.add(reverse);item['bidirectional']=True
            item['members']=[*e['members'],*links[reverse]['members']]
            item['paired_ids']=[e.get('id'),links[reverse].get('id')]
            item['directional_labels']=[{'source':e['source'],'target':e['target'],'label':e.get('label','')},{'source':e['target'],'target':e['source'],'label':links[reverse].get('label','')}]
            item['label']=e.get('label','') if e.get('label')==links[reverse].get('label') else ' / '.join(x for x in [e.get('label',''),links[reverse].get('label','')] if x)
        out.append(item)
    return out


def prepare(plan):
    """Add obstacle-aware orthogonal paths without editing source facts."""
    width=1800;height=round(width/plan['canvas']['natural_aspect'])
    scale=lambda b:(b['x']*width,b['y']*height,(b['x']+b['width'])*width,(b['y']+b['height'])*height)
    boxes={nid:scale(b) for nid,b in plan['boxes'].items()}
    links=_pair(plan['macro_edges'],not plan.get('abstract',True) and not plan.get('pair_data_relations'))
    anchors=[nid for lane in plan.get('role_lanes',[]) if lane['role']=='execution' for nid in lane['members']]
    adjacency=defaultdict(set)
    for e in plan['macro_edges']:
        adjacency[e['source']].add(e['target']);adjacency[e['target']].add(e['source'])
    backbone=plan.get('local_storage_backbone');family_colors=['#3E6785','#55785C','#8B704E','#765F87'];family_of={}
    for e in links:
        endpoints=[nid for nid in (e['source'],e['target']) if nid!=backbone]
        ready=list(endpoints);seen=set();found=None
        while ready and found is None:
            node=ready.pop(0)
            if node in seen:continue
            seen.add(node)
            if node in anchors:found=node;break
            ready.extend(n for n in adjacency[node] if n!=backbone and n not in seen)
        if plan.get('pair_data_relations') and found:
            e['path_family']=found;e['line_color']=family_colors[anchors.index(found)%len(family_colors)];family_of[found]=e['line_color']
    if plan.get('type')=='directed_flow' and plan.get('flow_basis')!='control':
        objects={o['id']:o for o in plan['macro_nodes']};forward=defaultdict(set);incoming=defaultdict(set)
        for e in plan['macro_edges']:
            if e['kind']=='data' and e.get('family')=='forward':forward[e['source']].add(e['target']);incoming[e['target']].add(e['source'])
        joins={nid for nid,parents in incoming.items() if objects[nid]['kind']=='compute' and len(parents)>=2}
        operand_sources=sorted({nid for target in joins for nid in incoming[target] if objects[nid]['kind']=='memory'})
        if 2<=len(operand_sources)<=4:
            def reaches_operand(nid,seen=None):
                if nid in operand_sources:return {nid}
                if nid in joins:return set()
                seen=set() if seen is None else set(seen)
                if nid in seen:return set()
                seen.add(nid);return set().union(*(reaches_operand(child,seen) for child in forward[nid])) if forward[nid] else set()
            for e in links:
                if e['kind']!='data' or e.get('family')!='forward':continue
                families={e['source']} if e['source'] in operand_sources else reaches_operand(e['target'])
                if len(families)==1:
                    family=next(iter(families));color=family_colors[operand_sources.index(family)];e['path_family']=family;e['line_color']=color;family_of[family]=color
    step=4;maxx=width//step;maxy=height//step;blocked=set()
    for x0,y0,x1,y1 in boxes.values():
        for x in range(max(0,math.floor((x0-5)/step)),min(maxx,math.ceil((x1+5)/step))+1):
            for y in range(max(0,math.floor((y0-5)/step)),min(maxy,math.ceil((y1+5)/step))+1):blocked.add((x,y))
    # Scope headings are outside the actual circuit blocks but also need space.
    captions=[plan.get('system_frame'),*plan.get('containers',[])];caption_boxes=[]
    scope_boxes=[scale(cap['box']) for cap in plan.get('containers',[]) if cap.get('render_boundary') is not False and not cap.get('replaces_region')]
    for cap in captions:
        if not cap or cap.get('replaces_region') or cap.get('is_system_boundary'):continue
        if cap.get('display_only') or cap.get('render_boundary') is False:continue
        x0,y0,x1,y1=scale(cap['box']);title_height=plan.get('typography',{}).get('body_px',20)*1.2;y0-=title_height
        tw=min(x1-x0-10,len(cap['label'])*11)
        if plan.get('type')=='publication':
            from . import publication_render
            tw=publication_render.font(plan['typography']['body_px']).getlength(cap['label'])
        title_left=x0+14 if plan.get('type')=='publication' else x0+8
        if plan.get('type')=='publication' and tw<=x1-x0-30:
            # Headings are layout choices. Try the free end of their real
            # boundary before routing a wire around the default text position.
            expected=[]
            for edge in links:
                s,t=boxes[edge['source']],boxes[edge['target']];r=edge.get('routing',{})
                if s[3]<=t[1]:
                    sx=s[0]+(s[2]-s[0])*r.get('source_fraction',.5)
                    tx=t[0]+(t[2]-t[0])*r.get('target_fraction',.5)
                    if t[0]+14<=sx<=t[2]-14:tx=sx
                    expected.extend([((sx,s[3]),(sx,t[1])),((tx,s[3]),(tx,t[1]))])
                elif t[3]<=s[1]:
                    sx=s[0]+(s[2]-s[0])*r.get('source_fraction',.5)
                    tx=t[0]+(t[2]-t[0])*r.get('target_fraction',.5)
                    if s[0]+14<=tx<=s[2]-14:sx=tx
                    expected.extend([((sx,t[3]),(sx,s[1])),((tx,t[3]),(tx,s[1]))])
            for candidate_left in [title_left,x1-14-tw,(x0+x1-tw)/2,x1+14,x0-14-tw]:
                rect=(candidate_left,y0,candidate_left+tw,y0+title_height)
                if rect[0]<8 or rect[2]>width-8:continue
                if any(_crosses_rect(a,b,rect,8) for a,b in expected):continue
                if any(rect[0]<b[2]+6 and b[0]-6<rect[2] and rect[1]<b[3]+6 and b[1]-6<rect[3] for b in boxes.values()):continue
                title_left=candidate_left;break
            cap['heading_box']={'x':title_left/width,'y':y0/height,'width':tw/width,'height':title_height/height}
        caption_boxes.append((title_left,y0,title_left+tw,y0+title_height))
        for x in range(max(0,int(title_left/step)),min(maxx,math.ceil((title_left+tw)/step))+1):
            for y in range(max(0,int(y0/step)),min(maxy,math.ceil((y0+title_height)/step))+1):blocked.add((x,y))
    sides=defaultdict(list)
    for i,e in enumerate(links):
        r=e.get('routing',{});s=boxes[e['source']];t=boxes[e['target']]
        if not r:
            if s[3]<=t[1]:ss,ts='bottom','top'
            elif t[3]<=s[1]:ss,ts='top','bottom'
            else:ss,ts=('right','left') if s[0]<t[0] else ('left','right')
        else:ss,ts=r['source_side'],r['target_side']
        objects={o['id']:o for o in plan['macro_nodes']}
        if plan.get('type')=='directed_flow' and plan.get('flow_basis')!='control' and e['kind']=='data' and e.get('family')=='forward' and objects[e['source']]['kind']=='memory' and objects[e['target']]['kind']=='compute':
            peers={edge['source'] for edge in plan['macro_edges'] if edge['kind']=='data' and edge['target']==e['target'] and objects[edge['source']]['kind']=='memory'}
            receivers={edge['target'] for edge in plan['macro_edges'] if edge['kind']=='data' and edge['source']==e['source'] and objects[edge['target']]['kind']=='compute'}
            if len(peers)==2 and len(receivers)==2:
                peer_order=sorted(peers,key=lambda nid:boxes[nid][1]+boxes[nid][3]);receiver_order=sorted(receivers,key=lambda nid:boxes[nid][1]+boxes[nid][3])
                if peer_order.index(e['source'])!=receiver_order.index(e['target']):
                    ts='top' if (s[1]+s[3])<(t[1]+t[3]) else 'bottom'
                    e.setdefault('routing',{})['target_fraction']=.35 if ts=='top' else .65
        # A feed arriving from below a transform whose output also goes down
        # gets a side input. Keep input/output physically distinct in the guide.
        if e['kind']=='data' and not e.get('bidirectional') and objects[e['target']]['kind']=='compute' and objects[e['source']].get('source_owner')!=objects[e['target']].get('source_owner'):
            downstream=[boxes[r['target']] for r in plan['macro_edges'] if r['source']==e['target'] and r['kind']=='data']
            if s[1]>=t[3] and any(b[1]>=t[3] and max(t[0],b[0])<min(t[2],b[2]) for b in downstream):ts='right' if (s[0]+s[2])>(t[0]+t[2]) else 'left'
        def clear_side(nid,side,other):
            x0,y0,x1,y1=boxes[nid];cx=(x0+x1)/2;cy=(y0+y1)/2
            choices={ 'top':(cx,y0-18),'bottom':(cx,y1+18),'left':(x0-18,cy),'right':(x1+18,cy)}
            def score(candidate):
                p=tuple(round(v/step) for v in choices[candidate])
                n=sum((p[0]+dx,p[1]+dy) in blocked for dx,dy in ((0,0),(1,0),(-1,0),(0,1),(0,-1)))
                return n
            if score(side)>=3:
                b=boxes[other];tx=(b[0]+b[2])/2;ty=(b[1]+b[3])/2
                return min(choices,key=lambda c:(score(c),abs(choices[c][0]-tx)+abs(choices[c][1]-ty)))
            return side
        if e.get('family')!='instruction':
            ss=clear_side(e['source'],ss,e['target']);ts=clear_side(e['target'],ts,e['source'])
        e['_sides']=(ss,ts)
        sides[(e['source'],ss)].append((i,'source'));sides[(e['target'],ts)].append((i,'target'))
    # Order ports by their actual neighboring geometry, rather than source
    # array order. Explicit publication scope-strip ports stay authoritative.
    positions={}
    for (nid,side),entries in sides.items():
        axis=0 if side in {'top','bottom'} else 1
        entries.sort(key=lambda item: (sum(boxes[links[item[0]]['target' if item[1]=='source' else 'source']][axis::2])/2,item[0]))
        for rank,(index,which) in enumerate(entries):
            box=boxes[nid];fraction=links[index].get('routing',{}).get(which+'_fraction',(rank+1)/(len(entries)+1))
            positions[(index,which)]=box[axis]+(box[axis+2]-box[axis])*fraction
    for index,edge in enumerate(links):
        ss,ts=edge['_sides'];routing=edge.get('routing',{})
        if routing.get('outer_route') or (ss,ts) not in {('right','left'),('left','right'),('bottom','top'),('top','bottom')}:
            continue
        axis=0 if ss in {'top','bottom'} else 1
        s,t=boxes[edge['source']],boxes[edge['target']]
        low=max(s[axis]+min(18,(s[axis+2]-s[axis])*.2),t[axis]+min(18,(t[axis+2]-t[axis])*.2))
        high=min(s[axis+2]-min(18,(s[axis+2]-s[axis])*.2),t[axis+2]-min(18,(t[axis+2]-t[axis])*.2))
        if low>high:continue
        fixed=[positions[(index,which)] for which in ('source','target') if which+'_fraction' in routing]
        if fixed and max(fixed)-min(fixed)>.005:continue
        desired=fixed[0] if fixed else min(high,max(low,(positions[(index,'source')]+positions[(index,'target')])/2))
        choices=[desired,positions[(index,'source')],positions[(index,'target')],(low+high)/2]
        for value in choices:
            if not low-.005<=value<=high+.005 or any(abs(value-f)>.005 for f in fixed):continue
            if any(abs(value-positions[(other,w)])<18 for nid,side,which in [(edge['source'],ss,'source'),(edge['target'],ts,'target')] for other,w in sides[(nid,side)] if (other,w)!=(index,which)):
                continue
            positions[(index,'source')]=positions[(index,'target')]=value;break
    occupied=set();segment_colors={};routes=[];failures=[];exact_paths=[]
    def port(nid,side,i,which,other,instruction):
        x0,y0,x1,y1=boxes[nid];indices=sides[(nid,side)];fraction=(indices.index((i,which))+1)/(len(indices)+1)
        fraction=links[i].get('routing',{}).get(which+'_fraction',fraction)
        if side in {'top','bottom'}:
            x=positions[(i,which)];y=y0 if side=='top' else y1
            if instruction and which=='source':
                b=boxes[other];middle=(b[0]+b[2])/2
                if x0+14<=middle<=x1-14:x=middle
            elif instruction:x=(x0+x1)/2
            out=(x,y+(-18 if side=='top' else 18))
        else:
            x=x0 if side=='left' else x1;y=positions[(i,which)];out=(x+(-18 if side=='left' else 18),y)
        grid=(round(out[0]/step),round(out[1]/step))
        stub=[(x,y),(grid[0]*step,y),(grid[0]*step,grid[1]*step)] if side in {'left','right'} else [(x,y),(x,grid[1]*step),(grid[0]*step,grid[1]*step)]
        return stub,grid
    def astar(start,goal,bounds=None,line_color=None):
        initial=(start[0],start[1],-1);queue=[(abs(start[0]-goal[0])+abs(start[1]-goal[1]),0,initial)];best={initial:0};parent={};end=None
        while queue:
            _,cost,state=heapq.heappop(queue);x,y,d=state
            if cost!=best.get(state):continue
            if (x,y)==goal:end=state;break
            for nd,(dx,dy) in enumerate(((1,0),(0,1),(-1,0),(0,-1))):
                nx,ny=x+dx,y+dy;point=(nx,ny)
                if not (1<=nx<maxx and 1<=ny<maxy) or (point in blocked and point not in (start,goal)):continue
                if bounds and not (bounds[0]<=nx<=bounds[2] and bounds[1]<=ny<=bounds[3]):continue
                segment=tuple(sorted(((x,y),point)))
                if segment in occupied:continue
                if line_color:
                    close=False
                    for offset in [-4,-3,-2,-1,1,2,3,4]:
                        neighbor=tuple(sorted(((x+(offset if dy else 0),y+(offset if dx else 0)),(nx+(offset if dy else 0),ny+(offset if dx else 0)))))
                        if segment_colors.get(neighbor)==line_color:close=True;break
                    if close:continue
                nc=cost+1+(4 if d>=0 and d!=nd else 0);ns=(nx,ny,nd)
                if nc<best.get(ns,math.inf):
                    best[ns]=nc;parent[ns]=state
                    heapq.heappush(queue,(nc+abs(nx-goal[0])+abs(ny-goal[1]),nc,ns))
        if end is None:return None
        points=[]
        while end!=initial:points.append(end[:2]);end=parent[end]
        points.append(start);points.reverse();return points
    def simple_path(edge,start,end,ss,ts,bounds):
        """Try exact orthogonal geometry before quantizing onto the fallback grid."""
        routing=edge.get('routing',{});normals={'left':(-1,0),'right':(1,0),'top':(0,-1),'bottom':(0,1)}
        def valid(points):
            if len(points)<2:return False
            if math.dist(points[0],points[1])<.01 or math.dist(points[-2],points[-1])<.01:return False
            sx,sy=normals[ss];tx,ty=normals[ts]
            if (points[1][0]-start[0])*sx+(points[1][1]-start[1])*sy<=.005:return False
            if (points[-2][0]-end[0])*tx+(points[-2][1]-end[1])*ty<=.005:return False
            if bounds and any(not bounds[0]*step-.01<=x<=bounds[2]*step+.01 or not bounds[1]*step-.01<=y<=bounds[3]*step+.01 for x,y in points):return False
            if any(_crosses_rect(a,b,box,0 if nid in {edge['source'],edge['target']} else 5) for a,b in zip(points,points[1:]) for nid,box in boxes.items()):return False
            if any(_crosses_rect(a,b,box,5) for a,b in zip(points,points[1:]) for box in caption_boxes):return False
            # These grammars retain scope outlines around resource symbols.
            # Folded views can defer a surrounding context outline during
            # label preflight; their measured parent-header entries must not
            # move merely to avoid an outline that will not be painted.
            if plan.get('view_type') in {'publication-resource-array','publication-exact-flow'}:
                clearance=max(20,plan['typography']['signal_px']/2)
                for x0,y0,x1,y1 in scope_boxes:
                    for a,b in zip(points,points[1:]):
                        if abs(a[1]-b[1])<.005:
                            near=min(abs(a[1]-y0),abs(a[1]-y1))<clearance
                            span=min(max(a[0],b[0]),x1)-max(min(a[0],b[0]),x0)
                        else:
                            near=min(abs(a[0]-x0),abs(a[0]-x1))<clearance
                            span=min(max(a[1],b[1]),y1)-max(min(a[1],b[1]),y0)
                        if near and span>44:return False
            if _paths_contact(points,exact_paths):return False
            return True
        candidates=[]
        if routing.get('outer_route'):
            if routing.get('waypoint_axis')!='y':return None
            value=routing['waypoint_value']*height
            candidates=[[start,(start[0],value),(end[0],value),end]]
        else:
            candidates=[[start,end],[start,(start[0],end[1]),end],[start,(end[0],start[1]),end]]
            # Midpoint tracks make unconstrained facing ports a shortest
            # Manhattan path; obstacle-edge tracks retain necessary bypasses.
            xs={(start[0]+end[0])/2};ys={(start[1]+end[1])/2}
            for x0,y0,x1,y1 in [*boxes.values(),*caption_boxes]:
                xs.update((x0-12,x1+12));ys.update((y0-12,y1+12))
            for x0,y0,x1,y1 in scope_boxes:
                xs.update((x0-24,x1+24));ys.update((y0-24,y1+24))
            candidates.extend([start,(x,start[1]),(x,end[1]),end] for x in sorted(xs))
            candidates.extend([start,(start[0],y),(end[0],y),end] for y in sorted(ys))
        feasible=[]
        for candidate in candidates:
            points=compact_path(candidate,.005)
            if valid(points):
                length=sum(math.dist(a,b) for a,b in zip(points,points[1:]))
                feasible.append((length+16*max(0,len(points)-2),len(points),points))
        return min(feasible,key=lambda item:item[:2])[-1] if feasible else None
    for i,e in enumerate(links):
        ss,ts=e.pop('_sides');instruction=e.get('family')=='instruction'
        a,start=port(e['source'],ss,i,'source',e['target'],instruction)
        b,goal=port(e['target'],ts,i,'target',e['source'],instruction)
        bounds=None
        if plan['abstract'] and all(next(o for o in plan['macro_nodes'] if o['id']==nid).get('zone')!='external' for nid in (e['source'],e['target'])):
            x0,y0,x1,y1=scale(plan['system_frame']['box'])
            bounds=(math.ceil((x0+6)/step),math.ceil((y0+35)/step),math.floor((x1-6)/step),math.floor((y1-6)/step))
        simple=simple_path(e,a[0],b[0],ss,ts,bounds)
        if simple is not None:
            exact_paths.append(simple)
            for left,right in zip(simple,simple[1:]):
                p=(round(left[0]/step),round(left[1]/step));q=(round(right[0]/step),round(right[1]/step))
                dx=0 if p[0]==q[0] else 1 if q[0]>p[0] else -1;dy=0 if p[1]==q[1] else 1 if q[1]>p[1] else -1
                # Exact segments have one axis; only their grid projection
                # is reserved, without adding new visible bends.
                count=max(abs(q[0]-p[0]),abs(q[1]-p[1]))
                for offset in range(count):
                    first=(p[0]+offset*dx,p[1]+offset*dy);second=(first[0]+dx,first[1]+dy)
                    segment=tuple(sorted((first,second)));occupied.add(segment);segment_colors[segment]=e.get('line_color')
            routes.append({**e,'source_side':ss,'target_side':ts,'points':[[round(x/width,6),round(y/height,6)] for x,y in simple]});continue
        routing=e.get('routing',{})
        if routing.get('outer_route') and routing.get('waypoint_axis')=='y':
            outer_y=round(routing['waypoint_value']*height/step)
            via_a=(start[0],outer_y);via_b=(goal[0],outer_y)
            legs=[]
            for left,right in [(start,via_a),(via_a,via_b),(via_b,goal)]:
                leg=astar(left,right,bounds,e.get('line_color'))
                if leg is None:legs=[];break
                legs.append(leg)
            path=[p for index,leg in enumerate(legs) for p in (leg if index==0 else leg[1:])] if legs else None
        else:
            path=astar(start,goal,bounds,e.get('line_color'))
        if path is None:failures.append({'id':e.get('id',str(i)),'source':e['source'],'target':e['target'],'start':list(start),'goal':list(goal),'source_side':ss,'target_side':ts,'start_neighbors_blocked':sum((start[0]+dx,start[1]+dy) in blocked for dx,dy in ((1,0),(-1,0),(0,1),(0,-1))),'goal_neighbors_blocked':sum((goal[0]+dx,goal[1]+dy) in blocked for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)))});continue
        for p,q in zip(path,path[1:]):
            segment=tuple(sorted((p,q)));occupied.add(segment);segment_colors[segment]=e.get('line_color')
        points=[*a,*[(x*step,y*step) for x,y in path],*reversed(b)]
        compact=compact_path(points,.005);exact_paths.append(compact)
        routes.append({**e,'source_side':ss,'target_side':ts,'points':[[round(x/width,6),round(y/height,6)] for x,y in compact]})
    return {'width':width,'height':height,'routes':routes,'line_legend':family_of,'quality':{'routes_complete':not failures,'failed_routes':failures,'route_count':len(routes),'requested_routes':len(links),'no_common_bus_inferred':True}}


def render(result,figure,labels_only=False):
    plan=figure.get('structure_layout')
    if not plan:return None
    scene=figure.get('layout_scene') or prepare(plan)
    if not scene['quality']['routes_complete']:return None
    source_nodes={n['id']:n for n in result['spec']['nodes']}
    if not plan.get('abstract') and any(o['id'] not in source_nodes or o['label']!=source_nodes[o['id']]['label'] or o['kind']!=source_nodes[o['id']]['kind'] for o in plan['macro_nodes']):return None
    for route in scene['routes']:
        points=route['points']
        for endpoint,nid in [(points[0],route['source']),(points[-1],route['target'])]:
            box=plan['boxes'][nid];x0,y0=box['x'],box['y'];x1,y1=x0+box['width'],y0+box['height']
            if not (x0-1e-5<=endpoint[0]<=x1+1e-5 and y0-1e-5<=endpoint[1]<=y1+1e-5 and min(abs(endpoint[0]-x0),abs(endpoint[0]-x1),abs(endpoint[1]-y0),abs(endpoint[1]-y1))<=1e-5):return None
        for a,b in zip(points,points[1:]):
            if abs(a[0]-b[0])>1e-5 and abs(a[1]-b[1])>1e-5:return None
            for nid,box in plan['boxes'].items():
                if nid in {route['source'],route['target']}:continue
                x0,y0=box['x'],box['y'];x1,y1=x0+box['width'],y0+box['height']
                if abs(a[0]-b[0])<=1e-5 and x0+1e-5<a[0]<x1-1e-5 and max(min(a[1],b[1]),y0)<min(max(a[1],b[1]),y1)-1e-5:return None
                if abs(a[1]-b[1])<=1e-5 and y0+1e-5<a[1]<y1-1e-5 and max(min(a[0],b[0]),x0)<min(max(a[0],b[0]),x1)-1e-5:return None
    try:
        from PIL import Image,ImageDraw,ImageFont
    except ImportError:return None
    from .publication_render import font_path as shared_font_path
    font_path=shared_font_path()
    if font_path is None:return None
    width,height=scene['width'],scene['height']
    if plan.get('flow_basis')=='control' and plan['canvas'].get('label_unit_pixels',0)>40:
        width=1100;height=round(scene['height']*width/scene['width'])
    img=Image.new('RGB',(width,height),'white');draw=ImageDraw.Draw(img)
    fonts={size:ImageFont.truetype(str(font_path),size,layout_engine=ImageFont.Layout.BASIC) for size in [14,16,18,20,22,24]}
    source={n['id']:n for n in result['spec']['nodes']}
    palette={p.split()[0]:p.split()[1].rstrip('.') for p in result['style_prompt'].split('Palette: ')[1].split('\n')[0].split('; ')}
    ink=palette['ink'];scale=lambda b:(b['x']*width,b['y']*height,(b['x']+b['width'])*width,(b['y']+b['height'])*height)
    def text_lines(text,box,size=20):
        x0,y0,x1,y1=box;font=fonts[size];lines=[];current=''
        for word in text.split():
            trial=(current+' '+word).strip()
            if current and draw.textlength(trial,font=font)>x1-x0-10:lines.append(current);current=word
            else:current=trial
        if current:lines.append(current)
        if len(lines)*(size+3)>y1-y0-4 or any(draw.textlength(line,font=font)>x1-x0-8 for line in lines):return False
        y=(y0+y1)/2-len(lines)*(size+3)/2
        for line in lines:
            tw=draw.textlength(line,font=font);draw.text(((x0+x1-tw)/2,y),line,font=font,fill=ink);y+=size+3
        return True
    def label_and_parameters(node,label,box,size):
        detail=node.get('detail','') if node else ''
        params=re.findall(r'\b\d+\s+banks\b|\b\d+[- ]B\s+CELL\b',detail,re.I)
        if not params:return text_lines(label,box,size)
        x0,y0,x1,y1=box;parameter=' · '.join(params)
        if y1-y0<size+25:return False
        if not text_lines(label,(x0,y0,x1,y1-20),size):return False
        return text_lines(parameter,(x0,y1-23,x1,y1-1),14)
    frame=plan['system_frame'];x0,y0,x1,y1=scale(frame['box'])
    if not frame.get('display_only'):
        draw.rectangle((x0,y0,x1,y1),outline=ink,width=2)
        draw.text((x0+12,y0+7),frame['label'],font=fonts[24],fill=ink)
    for cap in plan.get('containers',[]):
        if cap.get('is_system_boundary') or cap.get('replaces_region') or cap.get('render_boundary') is False:continue
        x0,y0,x1,y1=scale(cap['box']);draw.rectangle((x0,y0,x1,y1),outline='#AFB8BE',width=1)
        tw=draw.textlength(cap['label'],font=fonts[20]);draw.rectangle((x0+7,y0-23,x0+11+tw,y0+1),fill='white')
        draw.text((x0+9,y0-23),cap['label'],font=fonts[20],fill=ink)
    # Continuous connections first; symbols mask only their own interiors.
    def arrow(a,b,color):
        length=math.dist(a,b)
        if not length:return
        dx=(b[0]-a[0])/length;dy=(b[1]-a[1])/length
        draw.polygon([b,(b[0]-9*dx+3*dy,b[1]-9*dy-3*dx),(b[0]-9*dx-3*dy,b[1]-9*dy+3*dx)],fill=color)
    label_boxes=[];label_tasks=[]
    if not frame.get('display_only'):
        x0,y0,x1,y1=scale(frame['box']);label_boxes.append((x0+10,y0+5,x0+15+draw.textlength(frame['label'],font=fonts[24]),y0+34))
    for cap in plan.get('containers',[]):
        if cap.get('is_system_boundary') or cap.get('replaces_region') or cap.get('render_boundary') is False:continue
        x0,y0,x1,y1=scale(cap['box']);label_boxes.append((x0+7,y0-23,x0+11+draw.textlength(cap['label'],font=fonts[20]),y0+1))
    def overlaps(a,b):return a[0]<b[2] and b[0]<a[2] and a[1]<b[3] and b[1]<a[3]
    obstacles=[scale(b) for b in plan['boxes'].values()]
    routes_pixels=[[(x*width,y*height) for x,y in e['points']] for e in scene['routes']]
    def text_crosses_wire(box):
        for path in routes_pixels:
            for a,b in zip(path,path[1:]):
                if a[0]==b[0] and box[0]-2<a[0]<box[2]+2 and max(min(a[1],b[1]),box[1]-2)<min(max(a[1],b[1]),box[3]+2):return True
                if a[1]==b[1] and box[1]-2<a[1]<box[3]+2 and max(min(a[0],b[0]),box[0]-2)<min(max(a[0],b[0]),box[2]+2):return True
        return False
    for e in scene['routes']:
        points=[(x*width,y*height) for x,y in e['points']];dashed=e.get('stroke_style', 'dashed' if e['kind'] in {'control','clock','feedback'} else 'solid')=='dashed';color='#727E87' if dashed else e.get('line_color',ink)
        for a,b in zip(points,points[1:]):
            if dashed:
                length=math.dist(a,b)
                for offset in range(0,math.ceil(length),10):
                    t0=offset/length;t1=min((offset+5)/length,1)
                    draw.line([(a[0]+(b[0]-a[0])*t0,a[1]+(b[1]-a[1])*t0),(a[0]+(b[0]-a[0])*t1,a[1]+(b[1]-a[1])*t1)],fill=color,width=1)
            else:draw.line([a,b],fill=color,width=2)
        arrow(points[-2],points[-1],color)
        if e.get('bidirectional'):arrow(points[1],points[0],color)
        literal_source=result.get('description','')+' '+result.get('settings',{}).get('notes','')
        hard_labels=set(result['spec'].get('verbatim_labels',[]))|set(result.get('settings',{}).get('labels','').splitlines())
        feedback_caption=plan.get('flow_basis')=='control' and e['kind']=='feedback' and e.get('label') not in hard_labels and e.get('label','').casefold() not in literal_source.casefold() and not re.search(r'[\d=<>!&|]',e.get('label',''))
        if e.get('label') and e.get('family')!='instruction' and not feedback_caption:
            text=e['label'];tw=draw.textlength(text,font=fonts[16]);placed=False
            segments=sorted(zip(points,points[1:]),key=lambda ab:math.dist(*ab),reverse=True)
            for a,b in segments:
                for fraction in [.5,.3,.7]:
                    x=a[0]+(b[0]-a[0])*fraction;y=a[1]+(b[1]-a[1])*fraction
                    candidates=[(x-tw/2,y-37,x+tw/2,y-16),(x-tw/2,y+16,x+tw/2,y+37)] if a[1]==b[1] else [(x+16,y-10,x+16+tw,y+11),(x-16-tw,y-10,x-16,y+11)]
                    for box in candidates:
                        if box[0]<6 or box[1]<6 or box[2]>width-6 or box[3]>height-6:continue
                        if any(overlaps(box,ob) for ob in [*obstacles,*label_boxes]) or text_crosses_wire(box):continue
                        label_boxes.append(box);label_tasks.append((text,box,color));placed=True;break
                    if placed:break
                if placed:break
    for obj in plan['macro_nodes']:
        box=scale(obj['box']);x0,y0,x1,y1=box
        if obj.get('template_slots'):
            draw.rectangle(box,fill='white',outline=ink,width=1)
            label_box=(x0+5,y0+3,x1-5,y0+(y1-y0)*obj.get('header_fraction',.14))
            if not text_lines(obj['label'],label_box,22):return None
            for slot in obj['template_slots']:
                b=slot['box'];child=(x0+b['x']*(x1-x0),y0+b['y']*(y1-y0),x0+(b['x']+b['width'])*(x1-x0),y0+(b['y']+b['height'])*(y1-y0))
                fill=palette['secondary'] if slot['kind']=='memory' else palette['primary'] if slot['kind']=='compute' else 'white'
                draw.rectangle(child,fill=fill,outline='#65747D',width=1)
                size=18 if child[3]-child[1]>=48 else 16
                if not label_and_parameters(source.get(slot['source_node_id']),slot.get('display_label',slot['label']),child,size) and not (size>16 and label_and_parameters(source.get(slot['source_node_id']),slot.get('display_label',slot['label']),child,16)):return None
        else:
            fill=palette['secondary'] if obj['kind']=='memory' else palette['primary'] if obj['kind']=='compute' else 'white'
            draw.rectangle(box,fill=fill,outline=ink,width=1)
            if not label_and_parameters(source.get(obj['id']),obj['label'],box,22):return None
    for text,box,color in label_tasks:
        draw.rectangle((box[0]-2,box[1]-1,box[2]+2,box[3]+1),fill='white')
        draw.text((box[0],box[1]),text,font=fonts[16],fill=color)
    if labels_only:
        return {'width':width,'height':height,'labels':[{'text':text,'box':{'x':round(box[0]/width,6),'y':round(box[1]/height,6),'width':round((box[2]-box[0])/width,6),'height':round((box[3]-box[1])/height,6)},'color':color} for text,box,color in label_tasks]}
    out=io.BytesIO();img.save(out,format='PNG');return out.getvalue()
