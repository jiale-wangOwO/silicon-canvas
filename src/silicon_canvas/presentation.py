"""Model-independent view planning. A view is a projection, never new hardware."""
from collections import Counter, defaultdict
import hashlib
import json
import math
import re
from . import structure_layout
from . import private_layout
from . import flow_layout
from . import structure_scene

POLICY_VERSION = "CPS5"
BUDGETS = {"low": (8, 12), "medium": (16, 24), "high": (20, 32)}


def _key(node):
    return (node["label"].casefold(), node["id"])


def _buckets(spec, language="en"):
    """Use the supplied containment tree, unwrapping only universal wrappers."""
    groups = {g["id"]: g for g in spec["groups"]}
    if not groups:
        return [('@graph',spec['title'],spec['nodes'])]
    if spec['category']=='architecture':
        # Keep an actual ownership cut for detail planning. A system wrapper
        # with direct shared resources must not swallow its private children.
        direct=defaultdict(list)
        for node in spec['nodes']:direct[node['group'] or '@'+node['id']].append(node)
        return [(gid,groups[gid]['label'] if gid in groups else members[0]['label'],members) for gid,members in direct.items()]
    root_members = defaultdict(list)
    for node in spec["nodes"]:
        path, current = [], node["group"]
        while current:
            path.append(current)
            current = groups[current]["parent"]
        root_members[path[-1] if path else "@" + node["id"]].append(node)
    buckets = []
    loose=[gid for gid in root_members if gid.startswith('@')]
    if len(loose)>=4:
        members=[node for gid in loose for node in root_members.pop(gid)]
        root_members['@loose']=members

    def expand(gid, members):
        direct = [n for n in members if n["group"] == gid]
        children = [g for g in groups.values() if g["parent"] == gid]
        if not direct and len(children) == 1:
            return expand(children[0]["id"], members)
        # Universal wrapper has no analytical value in a macro overview.
        if not direct and len(root_members) == 1 and children:
            out = []
            for child in sorted(children, key=lambda g: (g["label"], g["id"])):
                subset = []
                for n in members:
                    ancestor = n["group"]
                    while ancestor and ancestor != child["id"]:
                        ancestor = groups[ancestor]["parent"]
                    if ancestor:
                        subset.append(n)
                if subset:
                    out.append((child["id"], child["label"], subset))
            return out
        return [(gid, groups[gid]["label"], members)]

    for gid, members in root_members.items():
        if gid.startswith("@"):
            label=('Other resources' if language=='en' else '其他资源') if gid=='@loose' else members[0]['label']
            buckets.append((gid, label, members))
        else:
            buckets.extend(expand(gid, members))
    safe = []
    for gid, label, members in buckets:
        if re.search(r"shared|共享", label, re.I) and any(re.search(r"\bprivate\b|\blocal\b|私有|本地", n['label'], re.I) for n in members):
            # A visual collection does not establish a physical sharing domain.
            label = "Resource interfaces" if language == "en" else "资源接口"
        safe.append((gid, label, members))
    degree=Counter(x for e in spec['edges'] for x in (e['source'],e['target']))
    # Keep a shared memory hub visible even if an extractor puts it in a large
    # resource group. This is a view boundary, not a change of physical owner.
    out=[]
    for gid,label,members in safe:
        hubs=[n for n in members if (n['kind']=='memory' or (n['kind']=='io' and re.search(r'interconnect|fabric|\bNoC\b|\bbus\b|crossbar',n['label'],re.I))) and degree[n['id']]>=6]
        if len(members)>1 and hubs:
            rest=[n for n in members if n not in hubs]
            if rest:out.append((gid,label,rest))
            out.extend(('@'+n['id'],n['label'],[n]) for n in hubs)
        else:out.append((gid,label,members))
    return sorted(out, key=lambda b: (b[1].casefold(), b[0]))


def _paired_links(links):
    """Two real opposite relationships may use one two-headed connector."""
    used=set();out=[]
    for i,e in enumerate(links):
        if i in used:continue
        reverse=next((j for j,r in enumerate(links) if j not in used and j!=i and r['source']==e['target'] and r['target']==e['source'] and r['kind']==e['kind']),None)
        item=dict(e);used.add(i)
        if reverse is not None:
            used.add(reverse)
            item['bidirectional']=True
            item['members']=[*e['members'],*links[reverse]['members']]
        out.append(item)
    return out


def compact_detail(detail, required_labels=()):
    """Literal short excerpts only; full prose remains in the companion caption."""
    if any(label and label in detail for label in required_labels):
        return detail
    parts=[p.strip() for p in detail.split(';') if p.strip()]
    numeric=[p for p in parts if re.search(r'\d',p) and len(p)<=80]
    roles=[p for p in parts if re.search(r'core-shared|private|共享|私有',p,re.I) and len(p)<=48]
    # Functional prose belongs in the caption; do not obstruct terminals with it.
    selected=[]
    for part in dict.fromkeys([*numeric,*roles]):
        if len('; '.join([*selected,part]))<=160:
            selected.append(part)
    return '; '.join(selected)


def visual_role(node):
    """Memory hierarchy membership does not turn a controller into storage."""
    if re.search(r'\bcontrollers?\s*$|控制器$',node['label'],re.I):return 'control'
    if re.search(r'\binterfaces?\s*$|接口$',node['label'],re.I):return 'io'
    return node['kind']


def hardware_glyph(node):
    """Visual vocabulary from facts; bank repetition requires an explicit count."""
    banks=re.search(r'\b(\d+)\s+banks\b',node.get('detail',''),re.I)
    role=visual_role(node)
    if role=='memory' and banks and 1<=int(banks.group(1))<=16:
        return {'shape':'banked-memory','bank_count':int(banks.group(1))}
    if role=='memory':
        return {'shape':'shallow-queue' if re.search(r'queue|\bIQ\b',node['label'],re.I) else 'storage-bar'}
    return {'shape':{'compute':'compact-functional-block','control':'compact-control-block','io':'interface-block','state':'state-circle','decision':'decision-diamond'}.get(role,'compact-functional-block')}


def _depth(spec):
    parents = {g["id"]: g["parent"] for g in spec["groups"]}
    maximum = 0
    for gid in parents:
        depth, cur = 0, gid
        while cur:
            depth += 1
            cur = parents[cur]
        maximum = max(maximum, depth)
    return maximum


def _inside_scope(group_id, scope_id, groups):
    parents={g['id']:g['parent'] for g in groups}
    current=group_id
    while current:
        if current==scope_id:return True
        current=parents.get(current,'')
    return False


def _positions(ids, edges, nodes, category, context=()):
    """Fixed, bounded grid; flow columns derived from directed dependencies."""
    columns = min(4, max(1, math.ceil(math.sqrt(len(ids)))))
    if category in {"dataflow", "pipeline", "algorithm"}:
        # Stable Kahn order, then deterministic cycle leftovers (not a timing claim).
        indegree = {i: 0 for i in ids}
        adjacency = defaultdict(set)
        for edge in edges:
            s, t = edge["source"], edge["target"]
            if s != t and s in indegree and t in indegree and t not in adjacency[s]:
                adjacency[s].add(t)
                indegree[t] += 1
        ordered, ready = [], sorted((i for i in ids if not indegree[i]), key=lambda i: _key(nodes[i]))
        while ready:
            src = ready.pop(0)
            ordered.append(src)
            for dst in sorted(adjacency[src], key=lambda i: _key(nodes[i])):
                indegree[dst] -= 1
                if not indegree[dst]:
                    ready.append(dst)
                    ready.sort(key=lambda i: _key(nodes[i]))
        ordered.extend(sorted(set(ids) - set(ordered), key=lambda i: _key(nodes[i])))
    else:
        # Put supplied control in the first row, compute next, memory at bottom.
        ranks = {"control": 0, "stage": 1, "compute": 1, "decision": 1, "state": 1, "memory": 2, "io": 2, "event": 1, "signal": 1}
        ordered = sorted(ids, key=lambda i: (ranks.get(nodes[i]["kind"], 1), _key(nodes[i])))
    positions = {nid: {"row": pos // columns + 1, "column": pos % columns + 1} for pos, nid in enumerate(ordered)}
    if category in {"architecture", "microarchitecture", "memory"}:
        degrees = Counter(x for edge in edges for x in (edge["source"], edge["target"]))
        shared = sorted((nid for nid in ids if nodes[nid]["kind"] == "memory" and degrees[nid] >= 6), key=lambda nid: (-degrees[nid], _key(nodes[nid])))
        if shared:
            hub = shared[0]
            peers = [nid for nid in ordered if nid != hub]
            positions = {nid: {"row": pos // columns + 1, "column": pos % columns + 1} for pos, nid in enumerate(peers)}
            positions[hub] = {"row": math.ceil(len(peers) / columns) + 1, "column": math.ceil(columns / 2)}
    return positions


def _flow_positions(ids, edges, nodes, context=()):
    """Cycle-safe dependency lanes. Back edges are routing choices, not new kinds."""
    forward = defaultdict(set)
    for e in edges:
        if e['kind'] in {'data', 'relation', 'control'} and e['source'] != e['target']:
            forward[e['source']].add(e['target'])
    state, dag, returns = {}, defaultdict(set), set()
    indegree = Counter(t for targets in forward.values() for t in targets)
    def visit(src):
        state[src] = 1
        for dst in sorted(forward[src], key=lambda i: _key(nodes[i])):
            if state.get(dst) == 1:
                returns.add((src,dst))
            else:
                dag[src].add(dst)
                if not state.get(dst):
                    visit(dst)
        state[src] = 2
    starts = sorted(ids, key=lambda i: (bool(indegree[i]), 0 if i in context else 1, 0 if nodes[i]['kind']=='memory' else 1, _key(nodes[i])))
    for nid in starts:
        if not state.get(nid):visit(nid)
    indegree = {i:0 for i in ids}
    for targets in dag.values():
        for t in targets:indegree[t]+=1
    ready = sorted((i for i in ids if not indegree[i]), key=lambda i:_key(nodes[i]))
    levels = {i:0 for i in ids}
    while ready:
        src=ready.pop(0)
        for dst in sorted(dag[src], key=lambda i:_key(nodes[i])):
            levels[dst]=max(levels[dst],levels[src]+1)
            indegree[dst]-=1
            if not indegree[dst]:ready.append(dst)
    # Long chains wrap in clearly separated rows, never shrink label font.
    lanes=defaultdict(list)
    for nid in ids:lanes[levels[nid]].append(nid)
    width=len(lanes) if len(lanes)<=8 and all(len(v)==1 for v in lanes.values()) and all(len(nodes[i]['label'])<=24 for i in ids) else 5
    positions={}
    for level, members in sorted(lanes.items()):
        for lane,nid in enumerate(sorted(members,key=lambda i:_key(nodes[i]))):
            positions[nid]={'column':level%width+1,'row':(level//width)*max(2,max(len(v) for v in lanes.values()))+lane+1}
    # Producers/consumers sit between their parallel lanes, not aligned to one
    # lane in a way that tempts the renderer to make a tall empty buffer card.
    for nid in ids:
        targets=sorted(dag[nid])
        sources=[s for s,ts in dag.items() if nid in ts]
        neighbors=targets if len(targets)==2 else sources if len(sources)==2 else []
        if neighbors and len({positions[x]['column'] for x in neighbors})==1:
            row=sum(positions[x]['row'] for x in neighbors)/2
            if not any(i!=nid and p['column']==positions[nid]['column'] and p['row']==row for i,p in positions.items()):positions[nid]['row']=row
    for nid in sorted(ids,key=lambda i:-levels[i]):
        if len(dag[nid])==1:
            dst=next(iter(dag[nid]));row=positions[dst]['row']
            # A converging consumer sits between lanes; do not pull one of its
            # parallel producers into that midpoint and break lane symmetry.
            if sum(dst in targets for targets in dag.values())==1 and positions[dst]['column']==positions[nid]['column']+1 and not any(i!=nid and p['column']==positions[nid]['column'] and p['row']==row for i,p in positions.items()):positions[nid]['row']=row
    connected={x for e in edges for x in (e['source'],e['target'])}
    isolated=sorted(set(ids)-connected,key=lambda i:_key(nodes[i]))
    if isolated:
        for nid in isolated:positions.pop(nid,None)
        baseline=max((v['row'] for v in positions.values()),default=0)+1
        for i,nid in enumerate(isolated):positions[nid]={'row':baseline+i//5,'column':i%5+1}
    return positions, returns


def _attachment_points(links, positions, outer_routes=()):
    """Separate fanout/fanin terminals geometrically, without new hardware pins."""
    outgoing,incoming=defaultdict(list),defaultdict(list)
    for i,e in enumerate(links):
        if i not in outer_routes:
            outgoing[e['source']].append(i)
            incoming[e['target']].append(i)
    assignments=[]
    for i,e in enumerate(links):
        if i in outer_routes:
            assignments.append({'source':'bottom boundary','target':'bottom boundary','lane':'outer return/control'})
            continue
        out=sorted(outgoing[e['source']],key=lambda k:(positions[links[k]['target']]['row'],positions[links[k]['target']]['column'],k))
        inc=sorted(incoming[e['target']],key=lambda k:(positions[links[k]['source']]['row'],positions[links[k]['source']]['column'],k))
        def port(indices,side):
            if len(indices)==1:return side+' center'
            if len(indices)==2:return side+(' upper' if indices.index(i)==0 else ' lower')
            return side+' distinct attachment '+str(indices.index(i)+1)+' of '+str(len(indices))
        assignments.append({'source':port(out,'right boundary'),'target':port(inc,'left boundary'),'lane':'forward'})
    return assignments


def glyph_dimensions(node,glyph):
    """Small role-dependent dimensions in multiples of the label font F."""
    longest=max((len(s.strip()) for s in node['label'].split('/')),default=len(node['label']))
    width=max(5,min(12,0.55*min(longest,18)+1.4))
    if glyph['shape']=='banked-memory':return {'width_f':9,'height_f':round(3.5+0.8*glyph['bank_count'],1)}
    if glyph['shape'] in {'storage-bar','shallow-queue'}:return {'width_f':max(8,width),'height_f':2.2}
    return {'width_f':round(width,1),'height_f':3.1 if len(node['label'])>18 else 2.2}


def _closed_private_views(spec, figures, limit, edge_limit, language='en'):
    """Keep complete incident control/data stories instead of source-owned cuts."""
    if spec['category']!='architecture':return figures
    source={n['id']:n for n in spec['nodes']};groups=spec['groups'];replaced=set();new=[]
    for group in groups:
        gid=group['id'];direct=[n for n in spec['nodes'] if n['group']==gid]
        if len(direct)<4 or not {'control','compute','memory'}<={n['kind'] for n in direct}:continue
        if re.search(r'shared|共享',group['label'],re.I) and not re.search(r'private|私有',group['label'],re.I):continue
        direct_private=any(n['kind']=='memory' and re.search(r'\bprivate\b|\blocal\b|私有|本地',n['label']+' '+n.get('detail',''),re.I) for n in direct)
        if not group['parent'] and not re.search(r'private|私有',group['label'],re.I) and not direct_private:continue
        owned={n['id'] for n in spec['nodes'] if _inside_scope(n['group'],gid,groups)}
        incident=[i for i,e in enumerate(spec['edges']) if owned&{e['source'],e['target']}]
        phases=[]
        for phase in ['control','datapath']:
            indices=[i for i in incident if (spec['edges'][i]['kind'] in {'control','feedback','clock'})==(phase=='control')]
            if not indices:continue
            ids={x for i in indices for x in (spec['edges'][i]['source'],spec['edges'][i]['target'])}
            if len(ids)>limit or len(indices)>edge_limit:phases=[];break
            fid='detail-'+hashlib.sha256(gid.encode()).hexdigest()[:8]+'-'+phase
            phases.append({'id':fid,'kind':'detail','abstract':False,'title':group['label']+' — '+phase,
                           'view_role':phase,'main_group':gid,'node_ids':sorted(ids,key=lambda i:_key(source[i])),
                           'edge_indices':indices,'context_nodes':sorted(ids-owned),
                           'summary':'按完整控制关系展开。' if phase=='control' else '按完整数据供给、计算和返回关系展开。'})
        if phases:
            new.extend(phases);replaced.update(incident)
    if not new:return figures
    degree=Counter(x for e in spec['edges'] for x in (e['source'],e['target']))
    remaining=[]
    for f in figures:
        indices=[i for i in f['edge_indices'] if i not in replaced]
        isolated=[nid for nid in f['node_ids'] if not degree[nid]]
        if not indices and not isolated:continue
        ids={x for i in indices for x in (spec['edges'][i]['source'],spec['edges'][i]['target'])}|set(isolated)
        remaining.append({**f,'edge_indices':indices,'node_ids':sorted(ids,key=lambda i:_key(source[i])),
                          'context_nodes':sorted(n for n in ids if not _inside_scope(source[n]['group'],f.get('main_group',''),groups))})
    # A tiny feed fragment joins its connected support view; never a one-link page.
    for f in list(remaining):
        if len(f['edge_indices'])>2 or not f['edge_indices']:continue
        choices=[g for g in remaining if g is not f and set(g['node_ids'])&set(f['node_ids']) and len(set(g['node_ids'])|set(f['node_ids']))<=limit and len(g['edge_indices'])+len(f['edge_indices'])<=edge_limit]
        if choices:
            target=max(choices,key=lambda g:len(set(g['node_ids'])&set(f['node_ids'])))
            target['node_ids']=sorted(set(target['node_ids'])|set(f['node_ids']),key=lambda i:_key(source[i]))
            target['edge_indices']=sorted(set(target['edge_indices'])|set(f['edge_indices']))
            target['context_nodes']=sorted(n for n in target['node_ids'] if not _inside_scope(source[n]['group'],target.get('main_group',''),groups))
            remaining.remove(f)
    for f in remaining:
        if len(f['edge_indices']) < len(spec['edges']):
            suffix=('其余连接' if f.get('main_group') else '系统连接') if language=='zh' else ('remaining connections' if f.get('main_group') else 'system connections')
            f['title'] += ' — '+suffix
            f['summary']=f"本图保留其余 {len(f['edge_indices'])} 条源关系；私有单元的控制与数据关系见对应独立视图。"
    return [*new,*remaining]


def build_plan(spec, density="medium", language="en"):
    limit, edge_limit = BUDGETS[density]
    nodes = {n["id"]: n for n in spec["nodes"]}
    edges = spec["edges"]
    dense = len(nodes) > limit or len(edges) > edge_limit or _depth(spec) > 2
    checks = [f"每张图最多 {limit} 个可见模块、{edge_limit} 条关系；超出预算生成独立视图。", "单图同一资源 ID 只绘制一次；跨图重现是同一资源的视图引用。", "覆盖检查只针对结构清单，实际图片的文字、端点和方向仍需核对。"]
    if not dense:
        fig = {"id": "overview", "kind": "overview", "abstract": False, "title": spec["title"],
               "summary": "完整结构在一张图内呈现。", "node_ids": sorted(nodes, key=lambda i: _key(nodes[i])),
               "edge_indices": list(range(len(edges))), "context_nodes": []}
        figures = [fig]
        data_indices=[i for i,e in enumerate(edges) if e['kind'] in {'data','relation'}]
        control_indices=[i for i,e in enumerate(edges) if e['kind'] in {'control','feedback','clock'}]
        if spec['category'] in {'microarchitecture','dataflow','pipeline'} and len(data_indices)>=8 and len(control_indices)>=5:
            figures=[];used={x for e in edges for x in (e['source'],e['target'])};isolated=set(nodes)-used
            for role,indices in [('datapath',data_indices),('control',control_indices)]:
                ids={x for i in indices for x in (edges[i]['source'],edges[i]['target'])}
                ids|={nid for nid in isolated if (nodes[nid]['kind']=='control')==(role=='control')}
                figures.append({'id':role,'kind':'detail','abstract':False,'title':spec['title']+' — '+role,'view_role':role,'summary':'完整数据路径与独立控制关系分别讲解。','node_ids':sorted(ids,key=lambda i:_key(nodes[i])),'edge_indices':indices,'context_nodes':[]})
            checks.append('控制关系较多，已按数据与控制拆成独立精确视图；每条源关系只属于一个视图。')
    else:
        buckets = _buckets(spec, language)
        unsafe_groups = [g['label'] for g in spec['groups'] if re.search(r'shared|共享',g['label'],re.I) and any(n['group']==g['id'] and re.search(r'\bprivate\b|\blocal\b|私有|本地',n['label'],re.I) for n in spec['nodes'])]
        if unsafe_groups:
            checks.append('分组名称暗示共享域，但含 Local / Private 资源：'+'、'.join(unsafe_groups)+'。绘图使用中性资源接口分区；物理归属保留为待核查项。')
        owner = {n["id"]: gid for gid, _, ns in buckets for n in ns}
        bucket_map = {gid: (label, ns) for gid, label, ns in buckets}
        degree = Counter(endpoint for e in edges for endpoint in (e["source"], e["target"]))
        assigned = defaultdict(list)
        for index, edge in enumerate(edges):
            src, dst = edge["source"], edge["target"]
            gid = owner[src]
            # Shared-source data belongs with its consumer's local datapath.
            if gid != owner[dst] and edge["kind"] == "data" and (len(bucket_map[gid][1]) == 1 or (nodes[src]["kind"] == "memory" and degree[src] >= 6)):
                gid = owner[dst]
            assigned[gid].append(index)
        figures = []
        represented = set()
        for gid, label, members in buckets:
            indices = sorted(assigned[gid], key=lambda i: (edges[i]["source"], edges[i]["target"], edges[i]["kind"], edges[i]["label"]))
            packs, current_nodes, current_edges = [], set(), []
            for index in indices:
                ends = {edges[index]["source"], edges[index]["target"]}
                if current_edges and (len(current_nodes | ends) > limit or len(current_edges) >= edge_limit):
                    packs.append((current_nodes, current_edges))
                    current_nodes, current_edges = set(), []
                current_nodes |= ends
                current_edges.append(index)
            if current_nodes:
                packs.append((current_nodes, current_edges))
            # Resource nodes with no owned edges are added later only if absent
            # everywhere, avoiding a redundant one-block shared-resource image.
            for part, (ids, links) in enumerate(packs, 1):
                fid = "detail-" + hashlib.sha256(gid.encode()).hexdigest()[:8] + f"-{part}"
                figures.append({"id": fid, "kind": "detail", "abstract": False,
                                "title": label + (f" ({part})" if len(packs) > 1 else ""),
                                "main_group":gid,
                                "summary": "独立展开，外围模块是同一逻辑资源的上下文引用。", "node_ids": sorted(ids, key=lambda i: _key(nodes[i])),
                                "edge_indices": links, "context_nodes": sorted(n for n in ids if owner[n]!=gid and not _inside_scope(nodes[n]['group'],gid,spec['groups']))})
                represented |= ids
        remaining = sorted(set(nodes) - represented, key=lambda i: _key(nodes[i]))
        # Add isolated members to their own local view whenever it has room.
        for nid in remaining:
            label = bucket_map[owner[nid]][0]
            candidates = [f for f in figures if f["title"] == label and len(f["node_ids"]) < limit]
            if candidates:
                candidates[0]["node_ids"].append(nid)
            else:
                fid = "resource-" + hashlib.sha256(owner[nid].encode()).hexdigest()[:8]
                candidates = [f for f in figures if f["id"].startswith(fid) and len(f["node_ids"]) < limit]
                if candidates:
                    candidates[0]["node_ids"].append(nid)
                else:
                    figures.append({"id": fid + f"-{sum(f['id'].startswith(fid) for f in figures) + 1}", "kind": "detail", "abstract": False,
                                    "title": label, "summary": "资源清单视图；未指定的连接保持省略。", "node_ids": [nid], "edge_indices": [], "context_nodes": []})
        figures=_closed_private_views(spec,figures,limit,edge_limit,language)
        # A containment projection is useful only with meaningful supplied groups.
        # Without groups, exact views remain the default; no invented hierarchy.
        if 1 < len(buckets) <= min(limit, 12) and spec["groups"]:
            macro_nodes = []
            for gid, label, members in buckets:
                roles = Counter(n['kind'] for n in members)
                role = 'control' if roles['control'] / len(members) >= .2 else 'compute' if roles['compute'] else 'memory' if roles['memory']==len(members) else 'io'
                macro_nodes.append({"id": gid, "label": label, "kind": role, "members": sorted(n["id"] for n in members)})
            aggregated = defaultdict(list)
            for index, edge in enumerate(edges):
                src, dst = owner[edge["source"]], owner[edge["target"]]
                if src != dst:
                    aggregated[(src, dst, edge["kind"])].append(index)
            priority = {"data": 0, "relation": 1, "control": 2, "feedback": 3, "clock": 4}
            abstract_edges = [{"source": s, "target": t, "kind": kind, "label": "", "members": indices}
                              for (s, t, kind), indices in sorted(aggregated.items(), key=lambda entry: (priority[entry[0][2]], entry[0][0], entry[0][1]))[:edge_limit]]
            structural = spec['category'] in {'architecture','microarchitecture','memory'}
            hub_candidates=[n for n in macro_nodes if n['kind'] in {'memory','io'} and len(n['members'])==1 and degree[n['members'][0]]>=6]
            focal_hub=max(hub_candidates,key=lambda n:degree[n['members'][0]])['id'] if hub_candidates else ''
            overview_links=_paired_links([e for e in abstract_edges if focal_hub in (e['source'],e['target']) and e['kind']=='data']) if focal_hub else _paired_links(abstract_edges)
            figures.insert(0, {"id": "overview", "kind": "overview", "abstract": True, "title": spec["title"],
                               "summary": "突出共享资源与执行路径的主关系；控制和完整接线保留在独立细节图中。" if focal_hub else "功能分区和给定主关系概览；精确连接保留在独立细节图中。", "node_ids": [], "edge_indices": [],
                               "context_nodes": [], "macro_nodes": macro_nodes, "macro_edges": overview_links if structural else abstract_edges,
                               "overview_relations": abstract_edges, "focal_hub":focal_hub, "view_type": 'shared-resource-overview' if focal_hub else 'dependency-overview' if overview_links else 'resource-map'})
        checks.append("总览中的宏块和汇总关系均映射到原始内容，不新增硬件；总览不替代完整接线图。")
    hierarchy=structure_layout.build_overview(spec,language,hints={'main_family_limit':6})
    if hierarchy and hierarchy.get('repeat_families'):
        # A resource organization overview follows commercial chip figures:
        # show instruction entry and the external/feed backbone. Per-unit
        # service traffic belongs to the complete control/data planes.
        units={o['id'] for o in hierarchy['macro_nodes'] if o['zone']=='units'}
        backbones={o['id'] for o in hierarchy['macro_nodes'] if o['kind']=='memory' and o['zone']=='memory' and len(units)>=2 and units<={e['target'] if e['source']==o['id'] else e['source'] for e in hierarchy['projected_links'] if e['kind']=='data' and o['id'] in (e['source'],e['target'])}}
        shown=[];deferred=[]
        for e in hierarchy['projected_links']:
            if e['family']=='instruction' or not units&{e['source'],e['target']} or (e['kind']=='data' and backbones&{e['source'],e['target']}):
                shown.append(e)
            else:deferred.append({**e,'reason':'Unit service interaction belongs to the control/datapath view; this overview answers resource organization.'})
        hierarchy['macro_edges']=shown;hierarchy['deferred_links']=deferred
        hierarchy['diagram_role']='resource-organization'
        structured={'id':'overview','kind':'overview','abstract':True,'title':spec['title'],'summary':'先看实例阵列、私有资源与共同服务，再沿主关系进入细节。',
                    'node_ids':[],'edge_indices':[],'context_nodes':[], 'macro_nodes':hierarchy['macro_nodes'],'macro_edges':hierarchy['macro_edges'],
                    'view_type':hierarchy['view_type'],'view_role':'resource-organization','structure_layout':hierarchy,'layout_scene':structure_scene.prepare(hierarchy),'focal_hub':''}
        exact_views=[]
        for f in figures:
            if f['id']=='overview':
                if f['abstract']:continue
                f={**f,'id':'detail-full','kind':'detail'}
            exact_views.append(f)
        if not dense:exact_views=_closed_private_views(spec,exact_views,limit,edge_limit,language)
        figures=[structured,*exact_views]
    covered_nodes, covered_edges = set(), set()
    for fig in figures:
        visible = {n["id"]: n for n in fig.get("macro_nodes", [])} if fig["abstract"] else {nid: nodes[nid] for nid in fig["node_ids"]}
        links = fig.get("macro_edges", []) if fig["abstract"] else [edges[i] for i in fig["edge_indices"]]
        if (not fig['abstract'] or spec['category']=='dataflow') and spec['category'] in {'architecture','dataflow','pipeline','microarchitecture','algorithm'} and links:
            fig['positions'], returns = _flow_positions(list(visible),links,visible,fig['context_nodes'])
            fig['outer_routes'] = [i for i,e in enumerate(links) if (e['source'],e['target']) in returns or e['kind']=='feedback']
        else:
            fig["positions"] = _positions(list(visible), links, visible, spec["category"])
        if not fig['abstract'] and fig.get('main_group'):
            core=[nid for nid in fig['node_ids'] if nid not in fig['context_nodes']]
            if core:
                left=min(fig['positions'][nid]['column'] for nid in core);right=max(fig['positions'][nid]['column'] for nid in core)
                for nid in fig['context_nodes']:
                    if left<=fig['positions'][nid]['column']<=right:
                        column=right+1;row=fig['positions'][nid]['row']
                        while any(i!=nid and p['column']==column and p['row']==row for i,p in fig['positions'].items()):row+=1
                        fig['positions'][nid]={'column':column,'row':row}
        if fig.get('focal_hub') and 1<=len(links)<=6:
            hub=fig['focal_hub']
            neighbors=sorted({e['target'] if e['source']==hub else e['source'] for e in links},key=lambda i:_key(visible[i]))
            contexts=sorted(set(visible)-{hub}-set(neighbors),key=lambda i:_key(visible[i]))
            if len(contexts)<=3:
                fig['positions']={nid:{'row':1,'column':i+1} for i,nid in enumerate(contexts)}
                slots=[(2,1),(2,3),(3,1),(3,3),(4,1),(4,3)]
                for nid,(row,col) in zip(neighbors,slots):fig['positions'][nid]={'row':row,'column':col}
                fig['positions'][hub]={'row':3,'column':2}
        fig["node_count"], fig["edge_count"] = len(visible), len(links)
        fig["label_characters"] = sum(len(n["label"]) for n in visible.values())
        fig['glyphs']={nid:hardware_glyph(nodes[node['members'][0]] if fig['abstract'] and len(node['members'])==1 else node) for nid,node in visible.items()}
        fig['dimensions']={nid:glyph_dimensions(node,fig['glyphs'][nid]) for nid,node in visible.items()}
        fig['attachment_points']=_attachment_points(links,fig['positions'],fig.get('outer_routes',[])) if not fig['abstract'] else []
        if not fig['abstract']:
            detail_layout=private_layout.build_detail(spec,fig,language)
            if not detail_layout:
                detail_layout=flow_layout.build(spec,fig,language)
            if detail_layout:
                detail_layout['pair_data_relations']=fig.get('view_role')=='datapath'
                fig['structure_layout']=detail_layout
                fig['layout_scene']=structure_scene.prepare(detail_layout)
        if fig['abstract']:
            source_degree=Counter(x for e in edges for x in (e['source'],e['target']))
            fig['member_labels']={n['id']:[nodes[i]['label'] for i in sorted(n['members'],key=lambda i:(-source_degree[i],_key(nodes[i])))[:2]] for n in visible.values() if len(n['members'])>1}
        if not fig["abstract"]:
            covered_nodes.update(fig["node_ids"])
            covered_edges.update(fig["edge_indices"])
        if not fig.get('structure_layout') and (len(visible) > limit or len(links) > edge_limit):
            raise ValueError("视图预算未能满足，请检查结构。")
    coverage = {"nodes_total": len(nodes), "edges_total": len(edges), "nodes_covered": len(covered_nodes), "edges_covered": len(covered_edges),
                "missing_nodes": sorted(set(nodes) - covered_nodes), "missing_edges": sorted(set(range(len(edges))) - covered_edges)}
    if coverage["missing_nodes"] or coverage["missing_edges"]:
        raise ValueError("视图拆分遗漏了原始结构。")
    return {"policy_version": POLICY_VERSION, "strategy": "atlas" if len(figures)>1 else "single", "summary": "复杂结构已拆成总览和独立细节，避免把所有信息压进一张图。" if len(figures)>1 else "当前内容适合一张清楚的图。",
            "figures": figures, "coverage": coverage, "checks": checks,
            "quality": {"node_budget": limit, "edge_budget": edge_limit, "max_nodes_per_figure": max(f["node_count"] for f in figures), "max_edges_per_figure": max(f["edge_count"] for f in figures)}}


def compile_structure_figure(fig,spec,settings,style_prompt,required_labels):
    plan=fig['structure_layout'];scene=fig['layout_scene'];quote=lambda s:json.dumps(s,ensure_ascii=False)
    palette={p.split()[0]:p.split()[1].rstrip('.') for p in style_prompt.split('Palette: ')[1].split('\n')[0].split('; ')}
    overview=plan['abstract'];source={n['id']:n for n in spec['nodes']}
    flow=plan.get('type')=='directed_flow'
    control_flow=plan.get('flow_basis')=='control'
    question="Which real modules receive commands, and which completion signals return to the controller?" if control_flow else "How do the actual inputs pass through parallel branches, merge at computation, and reach the output while control and returning streams remain separate?" if flow else "How are the system's instances, private resources, common services and external interface organized?" if overview else "How do the supplied "+fig.get('view_role','resource')+" relationships operate inside this owner and reach its external services?"
    lines=["Use Image Gen to produce one finished flat engineering diagram for a technical paper or architecture document.",
           "PRIMARY QUESTION: "+question,
           "The attached layout guide is the structural authority: keep its regions, identical instance skeletons, module positions and continuous routes. Do not solve this as loose cards or a global memory-hub star.",
           "Use the supplied arrangement as a logical architecture organization, not an area-accurate silicon floorplan. Diagram IDs and coordinates are instructions; never print them.",
           f"Canvas: follow the guide, approximately {plan['canvas']['natural_aspect']}:1. Solid pure white, crisp narrow lines, no texture, gradients, shadows, icons or poster furniture.",
           style_prompt,
           "READING ORDER: "+' -> '.join(l['role'] for l in plan['role_lanes']),
           "Unfilled ownership boundaries are subordinate to their contents. Keep source scope names normal-weight, close to the same size as module labels. A private RF/cache stays inside its original unit. Its degree never makes it a core-shared resource.",
           "At this organization scale, local storage is a compact bar: preserve explicit parameters as text, and do not expand a local RF into a giant banked centerpiece. Internal subdivisions are reserved for storage-mechanism detail views."]
    frame=plan['system_frame']
    if frame['display_only']:
        lines.append('Display envelope: '+json.dumps(frame['box'])+'. This reserves composition space only; do not draw its outline or title as another hardware container. The actual supplied scope boundaries below remain visible.')
    else:
        lines.append('Main boundary: '+quote(frame['label'])+'; box '+json.dumps(frame['box'])+('. This is only a display shell, not a new owner.' if frame['display_only'] else '. This is the supplied ownership boundary.'))
    for cap in plan['containers']:
        if cap.get('is_system_boundary') or cap.get('replaces_region') or cap['id']==frame.get('replaces_container'):continue
        if cap.get('render_boundary') is False:
            lines.append('Logical scope '+quote(cap['label'])+' includes '+', '.join(cap['members'])+'. It spans internal and external roles; preserve this source membership in the caption, without drawing a physical enclosure across those contexts.')
            continue
        lines.append('Scope '+quote(cap['label'])+': contains only '+', '.join(cap['members'])+'; subordinate unfilled boundary. Preserve its original parent '+(cap.get('parent') or 'none')+'.')
    lines.append('OBJECTS AND POSITIONS:')
    if required_labels:
        lines.append('Mandatory verbatim strings (on their matching supplied objects): '+'; '.join(quote(label) for label in required_labels)+'.')
    if any(source[nid].get('origin')=='assumed' for obj in plan['macro_nodes'] for nid in obj.get('members',[]) if nid in source):
        lines.append('This target is a generic conceptual proposal with transparently recorded assumptions. Render only the listed objects; provenance remains outside the bitmap.')
    lines.append('Unfilled white interior for real group boundaries; only resource blocks receive their stated role fill.')
    printed=set()
    for obj in plan['macro_nodes']:
        lines.append(obj['id']+': exact label '+quote(obj['label'])+'; '+obj['type']+'; box '+json.dumps(obj['box'])+'; original owner '+(obj.get('source_owner') or 'external/unassigned')+'.')
        role='container' if obj.get('template_slots') else visual_role(obj);fill=palette['secondary'] if role=='memory' else palette['primary'] if role=='compute' else palette['background']
        lines.append(obj['id']+' appearance: '+role+'; exact solid fill '+fill+'; narrow neutral outline. This is visual role encoding; do not print these attributes.')
        if obj.get('template_slots'):
            template=obj['template_id']
            if template in printed:
                lines.append('Use the identical internal skeleton of '+template+' inside '+obj['id']+'. This equivalence is explicitly supplied. It is the private resource set of this instance, never a shared RF copy outside the unit.')
            else:
                printed.add(template);lines.append('Internal skeleton for '+template+' (no internal wires in the organization overview):')
                for slot in obj['template_slots']:
                    node=source[slot['source_node_id']];detail=compact_detail(node.get('detail',''),required_labels)
                    lines.append('  '+quote(slot['label'])+'; '+slot['role_lane']+'; relative box '+json.dumps(slot['box'])+('; parameters '+quote(detail) if detail else '')+'.')
        else:
            node=source.get(obj['id']);detail=compact_detail(node.get('detail',''),required_labels) if node else ''
            if detail:lines.append('  Permitted short parameter '+quote(detail)+'. Keep full prose in the external caption.')
    lines.append('EXACT DISPLAYED RELATIONSHIPS:')
    label_layout=fig.get('label_layout');visible_edge_labels={x['text'] for x in label_layout.get('labels',[])} if label_layout else None
    if label_layout:
        lines.append('EDGE TEXT PLACEMENT: Render only the guide-planned edge labels below at these normalized empty-space boxes. Never put a text white-out on a wire or group border. Other full relationship meanings are retained in the external caption and canonical specification, not squeezed into this bitmap.')
        for label in label_layout['labels']:lines.append('Edge text '+quote(label['text'])+'; box '+json.dumps(label['box'])+'; subdued color '+label['color']+'.')
    if scene.get('line_legend'):
        lines.append('Trace the supplied path families using the guide\'s subdued edge colors; fills keep the preset. Colors aid tracing and do not define extra buses: '+', '.join(quote(source[nid]['label'])+' '+color for nid,color in scene['line_legend'].items())+'.')
    for i,e in enumerate(scene['routes'],1):
        arrow='<->' if e.get('bidirectional') else '->';treatment='fine dashed control' if e['kind'] in {'control','clock','feedback'} else 'narrow solid data'
        full_label=e.get('label','');deferred=visible_edge_labels is not None and full_label and full_label not in visible_edge_labels and full_label not in required_labels
        lines.append(f"R{i}: {e['source']} {arrow} {e['target']}; {treatment}; "+('no edge text; full meaning '+quote(full_label)+' belongs in caption' if deferred else 'label '+quote(full_label) if full_label else 'no edge text')+'.')
        lines.append('  Keep the guide path '+json.dumps(e['points'])+'. '+('Two arrowheads at the two boundaries, from two real opposite source relationships.' if e.get('bidirectional') else 'Exactly one arrowhead at the TARGET; the SOURCE boundary has none.'))
        if e.get('directional_labels'):
            lines.append('  Direction meanings: '+'; '.join(x['source']+' -> '+x['target']+': '+quote(x['label']) for x in e['directional_labels'])+'. Both original facts are retained; a combined connector does not define a shared physical channel.')
    if overview:
        lines.append('Each displayed relationship is a projection of explicitly supplied source edges. Internal unit wiring remains in detail views. Do not infer a bus, add shared-service arrows to other instances, or invent lines from visual adjacency. Repeated skeletons are justified by the supplied instance-equivalence declarations.')
    else:
        lines.append('This is an exact scoped view. Every listed module and directed relationship remains visible. Keep real nested resources within their supplied owner. Context remains outside its actual source owner; proximity is not shared ownership.')
    if flow:
        lines.append('The stage ranks are dependency positions, not clock cycles. Keep equivalent branches aligned, computation compact, and storage/register bars shallow. Control and returning payload routes use their reserved outer tracks; returning data stays solid and does not become control. Only actual supplied groups are hardware boundaries; a display shell is visual organization only.')
    lines.append('FINAL CHECK: Preserve the organized regions, repeated alignment, private/shared separation, all labels and displayed endpoints. Only the listed text and original scope names may appear. No giant title, copied vendor hardware, extra legend, unlisted connections or decorative arrows.')
    return '\n'.join(lines)


def compile_figure(fig, spec, settings, style_prompt, category_rules, aspect, required_labels, inline_title=False):
    if fig.get('structure_layout'):return compile_structure_figure(fig,spec,settings,style_prompt,required_labels)
    quote = lambda s: json.dumps(s, ensure_ascii=False)
    source_nodes = {n["id"]: n for n in spec["nodes"]}
    visible = fig.get("macro_nodes", []) if fig["abstract"] else [source_nodes[nid] for nid in fig["node_ids"]]
    nodes = {n["id"]: n for n in visible}
    links = fig.get("macro_edges", []) if fig["abstract"] else [spec["edges"][i] for i in fig["edge_indices"]]
    palette={item.split()[0]:item.split()[1].rstrip('.') for item in style_prompt.split('Palette: ')[1].split('\n')[0].split('; ')}
    if settings['aspect']=='auto':
        aspect='Tightly cropped wide publication figure, about 2.6:1 for a short datapath or 2:1 for an overview. Adapt the canvas to the actual circuitry, not a slide page; retain a small clean white perimeter.'
    lines = ["Use Image Gen to render ONE publication-quality chip architecture figure, not code or an explanation. Use the graphic grammar of an ISCA/MICRO hardware paper, not a presentation of large cards.",
             f"CANVAS: {aspect}. Solid white. One view only, not a collage of the entire atlas.",
             f"PURPOSE: {fig['kind']} of the supplied design. Show {len(nodes)} blocks and {len(links)} directed relationships. Each logical object appears once in this image.",
             "TEXT LANGUAGE: " + ("English" if settings["language"] == "en" else "简体中文") + "; literal names, signal identifiers and numbers remain exact.",
             "", style_prompt, "", "VIEW COMPOSITION:",
             "Use the following dependency lanes as a topology scaffold, not equal-sized grid cells. Blocks fit their labels and hardware roles; only equivalent hardware has matching dimensions. Short gaps accommodate signal labels and ports; no decorative grid.",
             "If an attached layout guide is supplied, its module geometry and continuous connections take precedence over these approximate row/column hints. Preserve it while applying the visual contract. Any paper/vendor references are style-only, never a source of extra circuits, labels or numerical parameters.",
             "Let F be the main label font: one-line block height 1.7–2.4F, two-line block 2.7–3.4F. Buffers/registers are shallow bars about 3–4 times wider than tall. Banked storage may be tall because it spans lanes. Avoid uniformly large cards.",
             "Horizontal signal gaps are 0.25–0.60 of an adjacent block width. Ordinary strokes are 0.07–0.12F, block outlines 0.045–0.07F, arrowheads only 0.35–0.55F. Group headers 0.85–1.0F, normal/medium weight. Compact whitespace serves the circuit, not poster framing."]
    grouped_architecture = spec['category']=='architecture' and not fig['abstract'] and bool(spec['groups'])
    if grouped_architecture:
        lines.append('For this system architecture, supplied containment takes priority over a linear datapath grid. Arrange functional regions compactly: front-end/control at the input side, the parallel compute region central, shared memory as a shallow common band, external memory and interfaces on the perimeter. Keep an explicitly expanded representative subsystem inside its true parent. Grouping is not a new connection or a physical floorplan.')
    else:
        for nid, slot in fig["positions"].items():
            lines.append(f"{nid}: row {slot['row']}, column {slot['column']}.")
    lines += ["Follow the dependency order while compacting the lanes tightly. Do not spread sparse circuitry over an entire page. Adjust shapes, distances and connector bends to avoid crossings; no separate miniature panels in this canvas.",
              "Keep data routes continuous and visible. Put recovery/return paths in outer corridors. Never route through boxes or words. Place arrowheads at the destination boundary; crossings without a dot do not connect.",
              "Every one-way edge has exactly ONE arrowhead, touching its named target boundary. Its source boundary has no arrowhead. Only an explicitly listed bidirectional edge may have arrowheads at both ends. In particular, a bottom return must leave its source without an arrow and enter its target with one arrow.",
              "", "CONTENT:"]
    if inline_title:
        lines.append('Title (verbatim): '+quote(fig['title'])+'. Use one small heading, no larger than 1.2 times the module names; do not repeat it in a container.')
    else:
        lines.append('The figure title is supplied separately as a document caption. Do NOT draw a title, subtitle, header or footer in the bitmap. Use the space for the technical content; container labels may appear once at their boundary.')
    degree = Counter(x for e in links for x in (e["source"], e["target"]))
    hubs = [nid for nid in nodes if degree[nid] >= 6]
    if hubs:
        lines.append("Routing hotspots: " + ", ".join(hubs) + ". Attach each incident relationship at a separate aligned port on an appropriate side. Spread short orthogonal corridors; no overlapping arrowheads or invented broadcast bus.")
    lines += ["DIAGRAM GRAMMAR:", *category_rules]
    if fig["abstract"]:
        lines.append("This overview shows functional collections and selected main relationships. Each composite region has a small group header and at most two supplied representative member captions, not an empty giant card. Member captions identify real contents; they are not new hardware or invented connections. The full wiring belongs to detail views. Context modules without a listed edge remain unconnected.")
        if fig.get('focal_hub'):
            lines.append('Make '+fig['focal_hub']+' the central shared-resource block. Keep control/interface context in the top row, outside all shared-resource corridors. Each surrounding datapath connects directly to the central block in its own open quadrant. No path may pass through a third block.')
    elif any(n["origin"] == "assumed" for n in visible):
        lines.append("This target is a generic conceptual proposal with transparent suggested content. Render exactly the listed objects; provenance remains outside the image.")
    if not fig["abstract"]:
        present_groups = {n["group"] for n in visible if n["group"]}
        groups = {g["id"]: g for g in spec["groups"]}
        for gid in list(present_groups):
            parent = groups[gid]["parent"]
            while parent:
                present_groups.add(parent)
                parent = groups[parent]["parent"]
        safe_labels = {g[0]:g[1] for g in _buckets(spec,settings['language'])}
        for g in spec["groups"]:
            if g["id"] not in present_groups:
                continue
            members = [n["id"] for n in visible if n["group"] == g["id"]] + [child["id"] for child in spec["groups"] if child["parent"] == g["id"] and child["id"] in present_groups]
            if fig.get('main_group') and g['id']!=fig['main_group']:
                lines.append(f"Context resource labels from {quote(safe_labels.get(g['id'],g['label']))}: {', '.join(members)}. Keep these modules outside the main group boundary; use a small scope tag, not another large enclosing frame.")
            else:
                lines.append(f"Container {g['id']}: label {quote(safe_labels.get(g['id'],g['label']))}; parent {g['parent'] or 'none'}; contains only {', '.join(members)}. Unfilled white interior; a fine neutral boundary and a normal-weight label at 0.9F. Do not make a shaded card or a bold section banner.")
        lines.append("For a scoped detail view, enclosing ownership belongs to the source design. Limit visible boundaries to two levels; omit an outer wrapper rather than moving objects into another subsystem. Context objects keep their original owner.")
    for n in visible:
        lines.append(f"Node {n['id']}: label {quote(n['label'])}; role {n['kind']}" + ("; overview of " + ", ".join(n["members"]) if fig["abstract"] else f"; container {n['group'] or 'none'}") + ".")
        glyph=fig['glyphs'][n['id']]
        dims=fig['dimensions'][n['id']]
        role=visual_role(n)
        fill=palette['secondary'] if role=='memory' else palette['primary'] if role=='compute' else palette['background']
        lines.append(f"{n['id']} appearance: {glyph['shape']}; width {dims['width_f']}F, height {dims['height_f']}F; exact solid fill {fill}; thin outline {palette['ink']}; normal-weight name. F is the module font size. No gradient. Do not enlarge to fill a lane.")
        if glyph['shape']=='banked-memory':
            lines.append(f"Visual glyph for {n['id']}: ONE banked-memory enclosure with {glyph['bank_count']} thin internal bank rows, from its supplied bank count. These are subdivisions of the same resource, never extra RF copies. Label the enclosure once; internal rows remain unlabeled, do not invent bank IDs or addresses.")
        if n['id'] in fig.get('member_labels',{}):
            lines.append('Representative contents inside '+n['id']+': '+ '; '.join(quote(x) for x in fig['member_labels'][n['id']])+'. Use short plain text or tiny internal bars under the group header, not another full miniature diagram. An ellipsis may indicate the other supplied members.')
        if not fig["abstract"] and n["detail"]:
            detail=compact_detail(n['detail'],required_labels)
            if detail:
                lines.append("Permitted callout for " + n["id"] + ": " + quote(detail) + ". Place beside a side with no assigned connector, never between a block boundary and its arrow. Descriptive prose stays in the companion document caption.")
    lines.append("EXACT DIRECTED EDGE LIST (IDs guide routing; do not print IDs):")
    if not links:
        lines.append("No connections specified. Do not add any arrows.")
    for index, edge in enumerate(links, 1):
        treatment = "solid directed arrow" if edge["kind"] in {"data", "relation"} or spec["category"] in {"fsm", "algorithm"} else "dashed directed arrow"
        if edge["kind"] == "feedback":
            treatment += ", outer corridor"
        if index-1 in fig.get('outer_routes',[]):
            treatment += ', uninterrupted outer return/control lane; never through intermediate blocks'
        if edge.get('bidirectional'):
            treatment='one clean connector with arrowheads at BOTH endpoint boundaries, representing two explicitly specified opposite directions'
        arrow='<->' if edge.get('bidirectional') else '->'
        lines.append(f"E{index}: {edge['source']} ({quote(nodes[edge['source']]['label'])}) {arrow} {edge['target']} ({quote(nodes[edge['target']]['label'])}); {edge['kind']}; {treatment}; " + ("edge label " + quote(edge["label"]) if edge["label"] else "no edge text") + ".")
        if fig['attachment_points'] and not grouped_architecture:
            ports=fig['attachment_points'][index-1]
            lines.append(f"E{index} attachment: start directly on {edge['source']} {ports['source']}; terminate directly on {edge['target']} {ports['target']}. No floating or disconnected branch stubs. Marks are visual attachment locations, not newly specified hardware ports.")
    if not fig["abstract"]:
        if len(spec["nodes"]) == len(visible) or spec["category"] in {"fsm", "algorithm", "timing", "pipeline"}:
            if spec["steps"]:
                lines += ["EXACT BEHAVIOR / CYCLES / OPERATIONS:", *spec["steps"]]
            if spec["annotations"]:
                lines += ["PERMITTED ANNOTATIONS:", *spec["annotations"]]
        else:
            lines.append("This detail owns only the listed nodes/edges. Other subsystem behaviors remain in their separate figures and full specification; never add an implicit interface or reconstruct a missing edge.")
        if spec["layout"] and len(spec["nodes"]) == len(visible):
            lines += ["SUPPLIED LAYOUT ADVISORY (only within this view and immutable style):", spec["layout"]]
    manifest = "\n".join([fig["title"], *(n["label"] for n in visible), *(e["label"] for e in links), *(n.get("detail", "") for n in visible)])
    local_labels = [label for label in required_labels if label in manifest]
    if local_labels:
        lines.append("Mandatory verbatim strings (only on their matching object): " + "; ".join(quote(x) for x in local_labels))
    lines += ["", "FINAL CHECK: Account for every listed block and relation in this view. Preserve directed endpoints, numbers, predicates, operators and exact names. Do not add facts to make the picture prettier.",
              "Only the permitted title, object names, edge labels and supplied details/behavior may appear. No IDs, source evidence, review notes, assumptions, badges, long explanatory paragraphs or extra footer.",
              "Exact module blocks contain only their name; composite regions may also contain the explicitly supplied member captions. All parameter callouts sit outside blocks. Keep a small white perimeter, compact gutters, and no headline unless explicitly supplied above. No duplicate title.",
              "Avoid: gradients, shadows, glow, tinted page backgrounds, all-blue frames, ornamental icons, tiny text, crowded wire bundles, copied resources and decorative arrows."]
    return "\n".join(lines)
