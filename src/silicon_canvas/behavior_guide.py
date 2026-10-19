"""Semantic state, sampled-time and logical-topology guides for Image Gen.

The guide is a newly drawn source reference. It is never the generated image.
Every state loop, sample value and topology coordinate comes from the source.
"""
from __future__ import annotations

import copy
import io
import json
import math
import re
from collections import defaultdict, deque

RANGE = re.compile(r"\b([A-Za-z]+)(\d+)\s*\.\.\s*\1(\d+)\s*:\s*(.+)")
COORD = re.compile(r"(?:logical\s+)?(?:grid\s+)?(?:position|coordinate|坐标)\s*[:=]?\s*\(?\s*(\d+)\s*[,，]\s*(\d+)\s*\)?", re.I)
INITIAL = re.compile(r"(?<!not )(?<!not an )(?<!not the )(?<!not a )initial\s+state|(?<!not )(?<!not a )reset\s+state|(?<!非)(?<!不是)初始状态|(?<!非)(?<!不是)复位状态", re.I)
WIDTH = 1800


def _state_outputs(detail):
    """Only explicit output clauses; an input predicate is not an output."""
    values=[]
    for clause in re.split(r"[;；\n]",detail):
        clause=clause.strip()
        if re.match(r"(?:outputs?\s*[:=]|输出\s*[:：=])",clause,re.I) or re.match(r"^[A-Za-z_]\w*\s*=\s*[01]\b",clause):
            values.extend(re.findall(r"[A-Za-z_][\w]*\s*=\s*(?:0|1)\b",clause))
    return list(dict.fromkeys(values))


def _traces(spec):
    rows, axis = [], None
    for node in spec["nodes"]:
        match = RANGE.search(node.get("detail", ""))
        if match:
            prefix, start, stop, raw = match.groups()
            start, stop = int(start), int(stop)
            values = re.split(r"[\s,，]+", raw.strip())
            candidate = [prefix + str(i) for i in range(start, stop + 1)]
            if not 2 <= len(candidate) <= 32 or len(values) != len(candidate):
                return None
            if axis is not None and candidate != axis:
                return None
            axis = candidate
            rows.append({"id": node["id"], "label": node["label"], "values": values,
                         "source_field": "nodes.detail", "source_text": match.group(0),
                         "kind": "binary" if set(values) <= {"0", "1", "x", "X", "z", "Z"} else "bus"})
        elif re.search(r"rising\s+(?:sampling\s+)?edges|上升.*采样|采样.*上升", node.get("detail", ""), re.I):
            rows.append({"id": node["id"], "label": node["label"], "kind": "sample-markers",
                         "values": [], "source_field": "nodes.detail", "source_text": node["detail"]})
        else:
            return None
    if axis is None or not rows:
        return None
    return {"axis": axis, "rows": rows, "sampling_policy": "Source values at named sample points; between-sample changes are unspecified, not exact timing or pulse widths."}


def _topology(spec):
    anchored = []
    for node in spec["nodes"]:
        match = COORD.search(node.get("detail", ""))
        if match:
            anchored.append({"id": node["id"], "coordinate": [int(v) for v in match.groups()],
                             "source_field": "nodes.detail", "source_text": match.group(0)})
    if not anchored:
        # A stated logical grid may have no coordinate table. A drawing embeds
        # ONLY existing adjacency; it does not claim physical router placement.
        for group in spec["groups"]:
            match = re.search(r"(\d+)\s*[x×]\s*(\d+)\s*(?:router\s*)?(?:mesh|网格)",group["label"],re.I)
            if not match:
                continue
            rows,columns = map(int,match.groups())
            members = [n for n in spec["nodes"] if n["group"]==group["id"]]
            if not 3 <= len(members) <= 9 or len(members)!=rows*columns:
                continue
            ids = [n["id"] for n in members]
            links = {frozenset((e["source"],e["target"])) for e in spec["edges"] if e["source"] in ids and e["target"] in ids and e["source"]!=e["target"]}
            slots = [(col,row) for row in range(rows) for col in range(columns)]
            def embed(assigned,remaining):
                if not remaining:return assigned
                nid=remaining[0]
                for slot in slots:
                    if slot in assigned.values():continue
                    if all(abs(slot[0]-other[0])+abs(slot[1]-other[1])==1 for peer,other in assigned.items() if frozenset((nid,peer)) in links):
                        found=embed({**assigned,nid:slot},remaining[1:])
                        if found:return found
                return None
            mapped=embed({},ids)
            if mapped:
                anchored=[{"id":nid,"coordinate":list(mapped[nid]),"source_field":"groups.label + source adjacency",
                           "source_text":group["label"],"coordinate_origin":"logical drawing embedding"} for nid in ids]
                break
    if len(anchored) < 3 or len({tuple(item["coordinate"]) for item in anchored}) != len(anchored):return None
    inferred=any(item.get("coordinate_origin")=="logical drawing embedding" for item in anchored)
    return {"anchors": anchored, "meaning": ("Drawing embedding of the stated logical grid and existing adjacency; coordinates are a layout choice, not supplied measurements. " if inferred else "Supplied logical coordinates. ")+"Distances do not assert die placement, area, bandwidth or latency."}


def applicable(spec):
    return (spec.get("category") == "fsm"
            or spec.get("category") == "timing" and _traces(spec) is not None
            or spec.get("category") in {"memory", "architecture"} and _topology(spec) is not None)


def primary(spec, language="en"):
    if not applicable(spec):
        return None
    grammar = "state-machine" if spec["category"] == "fsm" else "sampled-timing" if spec["category"] == "timing" else "logical-topology"
    ids = [node["id"] for node in spec["nodes"]]
    indices = list(range(len(spec["edges"])))
    question = {"state-machine": "Which events change state, which outputs hold, and how do reset and retry operate?",
                "sampled-timing": "Which supplied sample values demonstrate waiting and actual events?",
                "logical-topology": "Which real endpoints attach to each router, and which source links connect them?"}[grammar]
    return {"id": grammar, "title": spec["title"], "summary": question, "kind": "overview", "abstract": False,
            "primary": True, "technical_annex": False, "semantic_grammar": grammar,
            "view_role": grammar, "view_type": grammar, "node_ids": ids, "edge_indices": indices,
            "source_edge_indices": indices, "context_nodes": [],
            "macro_nodes": [{**copy.deepcopy(n), "members": [n["id"]], "original_group": n["group"], "children": []} for n in spec["nodes"]],
            "macro_edges": [{**copy.deepcopy(e), "id": "s" + str(i), "members": [i]} for i, e in enumerate(spec["edges"])],
            "projection": {"source_node_to_macro": {nid: nid for nid in ids}, "deferred_edges": [],
                           "ownership_unchanged": True, "meaning": "Identity source scope; loops, samples and original directed relationships remain explicit."},
            "design_contract": {"grammar": grammar, "question": question, "claim": question, "scope": "exact source semantics",
                                "target_width_mm": 200, "body_pt": 10, "signal_pt": 9}}


def _state_layout(spec, process=False):
    ids = [n["id"] for n in spec["nodes"]]
    initial = [n["id"] for n in spec["nodes"] if INITIAL.search(n.get("detail", ""))]
    start = initial[0] if len(initial) == 1 else ids[0]
    graph = defaultdict(list)
    from . import edge_semantics
    for e in spec["edges"]:
        if process and edge_semantics.stroke(e)!="solid":continue
        if e["target"] != e["source"]:
            graph[e["source"]].append(e["target"])
    ranks, queue = {start: 0}, deque([start])
    while queue:
        node = queue.popleft()
        for target in graph[node]:
            if target not in ranks:
                ranks[target] = ranks[node] + 1
                queue.append(target)
    for nid in ids:
        ranks.setdefault(nid, max(ranks.values(), default=0) + 1)
    layers = defaultdict(list)
    for nid in ids:
        layers[ranks[nid]].append(nid)
    columns = max(ranks.values()) + 1
    rows = max(len(value) for value in layers.values())
    height = max(860, 280 + rows * 280)
    positions = {}
    for rank, peers in layers.items():
        # Peers are source-ordered. Their equal rank is dependency, not time.
        for row, nid in enumerate(peers):
            positions[nid] = [180 + rank * (WIDTH - 480) / max(1, columns - 1),
                              180 + (row + .5) * (height - 360) / len(peers)]
    routes, labels = [], []
    returns = 0
    internal_returns = 0
    loop_counts = defaultdict(int)
    for i, e in enumerate(spec["edges"]):
        a, b = positions[e["source"]], positions[e["target"]]
        if e["source"] == e["target"]:
            loop = loop_counts[e["source"]]
            loop_counts[e["source"]] += 1
            reach = 124 + loop * 70
            # Asymmetric departure/re-entry makes a single directed hold
            # visible; symmetric U-loops are often redrawn with two heads.
            points = [[a[0]-55, a[1]-55], [a[0]-124-loop*20, a[1]-90],
                      [a[0]-124-loop*20,a[1]-reach], [a[0],a[1]-reach], [a[0],a[1]-78]]
            label_at = [a[0]-28, a[1]-reach-27]
            mode = "self-loop"
        elif ranks[e["target"]] <= ranks[e["source"]]:
            if ranks[e["target"]]>0:
                # An internal retry returns through an upper corridor to a
                # separate NE attachment, clear of the target's hold loop.
                lane=190-internal_returns*45
                corner=b[0]+135
                points=[[a[0]-55,a[1]-55],[a[0]-55,lane],[corner,lane],
                        [corner,b[1]-135],[b[0]+55,b[1]-55]]
                label_at=[(a[0]-55+corner)/2,lane-45]
                gutter=310
                internal_returns+=1
            else:
                lane = height - 90 + returns * 46
                outer_x=a[0]+110+returns*28
                inlet_x=b[0]-105-returns*22
                points = [[a[0]+80,a[1]],[outer_x,a[1]],[outer_x,lane],[inlet_x,lane],[inlet_x,b[1]],[b[0]-80,b[1]]]
                # Associate terminal returns with their departing state.
                gutter = max(85, WIDTH-outer_x-30)
                label_at = [outer_x+12+gutter/2, a[1]+38]
                returns += 1
            mode = "return"
        else:
            dx, dy = b[0]-a[0], b[1]-a[1]
            length = math.hypot(dx, dy)
            unit = [dx/length, dy/length]
            points = [[a[0]+unit[0]*78, a[1]+unit[1]*78], [b[0]-unit[0]*78, b[1]-unit[1]*78]]
            label_at = [(points[0][0]+points[-1][0])/2, (points[0][1]+points[-1][1])/2-17]
            if dy < -40:label_at[1]-=65
            elif dy>40:
                label_at=[points[0][0]*.8+points[-1][0]*.2, max(a[1]+200,points[0][1]*.8+points[-1][1]*.2+70)]
            mode = "forward"
        routes.append({**copy.deepcopy(e), "members": [i], "points": points, "label_at": label_at,
                       "mode": mode, "stroke_style": edge_semantics.stroke(e) if process else "solid", "bidirectional": False})
        if e["label"]:
            labels.append({"text": e["label"], "role": "transition", "source_edge_indices": [i], "at": label_at,
                           "max_width": gutter if mode == "return" else 310})
    height += returns * 46
    return {"positions": positions, "initial_node_ids": initial, "routes": routes,
            "labels": labels, "height": height, "reading_direction": "state progression and separate conditional returns"}


def _process_layout(spec):
    data=_state_layout(spec,process=True)
    source={n["id"]:n for n in spec["nodes"]}
    from .publication_render import font,wrap_text
    face=font(32)
    sizes={};texts={}
    for nid,n in source.items():
        maximum=270 if n["kind"]=="memory" else 230
        name_lines=wrap_text(n["label"],face,maximum-20,max_lines=4)
        if name_lines is None: return None
        numeric=[part.strip() for part in re.split(r";\s*",n["detail"]) if re.search(r"\d",part) and not re.search(r"\bnot\b|不是|不表示",part,re.I)]
        extra=[]
        for item in numeric:
            wrapped=wrap_text(item,face,maximum-20,max_lines=4)
            if wrapped is None:return None
            extra+=wrapped
        texts[nid]={"name_lines":name_lines,"required_detail_lines":extra,"source_detail":numeric}
        sizes[nid]=[maximum,max(84,24+len(name_lines)*39+len(extra)*34)]
    # Reject a guide which cannot keep actual resource glyphs distinct. The
    # caller retains the complete source and chooses another perspective.
    boxes=[(nid,(p[0]-sizes[nid][0]/2,p[1]-sizes[nid][1]/2,p[0]+sizes[nid][0]/2,p[1]+sizes[nid][1]/2)) for nid,p in data["positions"].items()]
    for i,(_,a) in enumerate(boxes):
        if any(a[0]<b[2]+12 and b[0]<a[2]+12 and a[1]<b[3]+12 and b[1]<a[3]+12 for _,b in boxes[i+1:]):
            return None
    incoming,outgoing=defaultdict(list),defaultdict(list)
    for i,e in enumerate(spec["edges"]):
        incoming[e["target"]].append(i);outgoing[e["source"]].append(i)
    bottom=max(p[1]+sizes[nid][1]/2 for nid,p in data["positions"].items())+80
    corridors=[]
    for index,route in enumerate(data["routes"]):
        a,b=data["positions"][route["source"]],data["positions"][route["target"]]
        sa,sb=sizes[route["source"]],sizes[route["target"]]
        source_offset=(outgoing[route["source"]].index(index)-(len(outgoing[route["source"]])-1)/2)*17
        target_offset=(incoming[route["target"]].index(index)-(len(incoming[route["target"]])-1)/2)*17
        if b[0]>a[0] and route["stroke_style"]=="solid":
            first=[a[0]+sa[0]/2+3,a[1]+source_offset]
            last=[b[0]-sb[0]/2-3,b[1]+target_offset]
            mid=(first[0]+last[0])/2
            route["points"]=[first,[mid,first[1]],[mid,last[1]],last]
            route["label_at"]=[mid,min(a[1]-sa[1]/2,b[1]-sb[1]/2)-40]
        else:
            # A stage receives downstream ready and emits upstream ready at
            # distinct attachments. Sharing their outside leg would draw a
            # T-junction bypassing the intervening resource.
            source_port=a[0]-sa[0]*.25+source_offset
            target_port=b[0]+sb[0]*.25+target_offset
            interval=sorted((source_port,target_port))
            lane_index=next((i for i,occupied in enumerate(corridors) if all(interval[1]+12<old[0] or old[1]+12<interval[0] for old in occupied)),len(corridors))
            if lane_index==len(corridors):corridors.append([])
            corridors[lane_index].append(interval)
            lane=bottom+lane_index*50
            route["points"]=[[source_port,a[1]+sa[1]/2+3],[source_port,lane],[target_port,lane],[target_port,b[1]+sb[1]/2+3]]
            route["label_at"]=[(a[0]+b[0])/2,lane-32]
    data["labels"]=[{"text":r["label"],"role":"signal","source_edge_indices":r["members"],"at":r["label_at"]} for r in data["routes"] if r["label"]]
    # Fresh guide geometry uses its content extent, not a default slide page.
    top=min([p[1]-sizes[nid][1]/2 for nid,p in data["positions"].items()]+[l["at"][1] for l in data["labels"]])-70
    for p in data["positions"].values():p[1]-=top
    for r in data["routes"]:
        for p in r["points"]:p[1]-=top
        r["label_at"][1]-=top
    for label in data["labels"]:label["at"]=list(label["at"])
    data.update(sizes=sizes,object_text=texts,height=int(max([p[1]+sizes[nid][1]/2+70 for nid,p in data["positions"].items()]+[p[1]+70 for r in data["routes"] for p in r["points"]])),reading_direction="functional dependency progression with separate return/control corridors",initial_node_ids=[])
    return data


def flow_fallback(spec,figure,settings):
    if spec["category"] not in {"dataflow","pipeline"} or not figure.get("primary") or len(spec["nodes"])>14 or len(spec["edges"])>30:
        return None
    ids={n["id"] for n in spec["nodes"]}
    visible={n["id"] for n in figure.get("macro_nodes",[])} or set(figure.get("node_ids",[]))
    if visible!=ids:return None
    temp={**figure,"semantic_grammar":"directed-process"}
    return build(spec,temp,settings)


def _topology_layout(spec, topology):
    anchors = {a["id"]: a["coordinate"] for a in topology["anchors"]}
    xs, ys = sorted({v[0] for v in anchors.values()}), sorted({v[1] for v in anchors.values()})
    positions = {nid: [420 + xs.index(c[0])*850/max(1,len(xs)-1), 280 + ys.index(c[1])*520/max(1,len(ys)-1)] for nid,c in anchors.items()}
    near = defaultdict(list)
    for node in spec["nodes"]:
        if node["id"] in positions:
            continue
        peers = {e["target"] if e["source"]==node["id"] else e["source"] for e in spec["edges"] if node["id"] in {e["source"],e["target"]}}
        named = sorted(peers & set(anchors))
        if len(named) == 1:near[named[0]].append(node["id"])
    for anchor, attached in near.items():
        x,y = positions[anchor]
        direction = -1 if x < WIDTH/2 else 1
        memories=[nid for nid in attached if next(n for n in spec["nodes"] if n["id"]==nid)["kind"]=="memory"]
        endpoints=[nid for nid in attached if nid not in memories]
        for order,nid in enumerate(attached):
            node=next(n for n in spec["nodes"] if n["id"]==nid)
            positions[nid] = ([x,y+230+memories.index(nid)*150] if node["kind"]=="memory" else
                              [x+direction*290,y+(endpoints.index(nid)-(len(endpoints)-1)/2)*150])
    remaining={n["id"] for n in spec["nodes"]}-set(positions)
    for _ in range(len(remaining)):
        progress=False
        for nid in [n["id"] for n in spec["nodes"] if n["id"] in remaining]:
            neighbors={e["target"] if e["source"]==nid else e["source"] for e in spec["edges"] if nid in {e["source"],e["target"]}} & set(positions)
            if not neighbors:continue
            candidate=[sum(positions[p][0] for p in neighbors)/len(neighbors),max(positions[p][1] for p in neighbors)+210]
            while any(abs(candidate[0]-p[0])<220 and abs(candidate[1]-p[1])<110 for p in positions.values()):candidate[1]+=130
            positions[nid]=candidate
            remaining.remove(nid);progress=True
        if not progress:break
    # An unconnected source object is still part of the specification. Place
    # it in a separate quiet tier; adjacency never creates an invented link.
    bottom=max(y for x,y in positions.values())+210
    for i,nid in enumerate(n["id"] for n in spec["nodes"] if n["id"] in remaining):
        positions[nid]=[220+(i%5)*310,bottom+(i//5)*150]
    routes, labels = [], []
    pair_count = defaultdict(int)
    for i,e in enumerate(spec["edges"]):
        a,b = positions[e["source"]], positions[e["target"]]
        if e["source"]==e["target"]:
            points=[[a[0]+98,a[1]-18],[a[0]+140,a[1]-18],[a[0]+140,a[1]-95],[a[0],a[1]-95],[a[0],a[1]-46]]
            at=[a[0]+40,a[1]-125]
            routes.append({**copy.deepcopy(e),"members":[i],"points":points,"label_at":at,"mode":"topology-self-link","stroke_style":"solid","bidirectional":False})
            if e["label"]:labels.append({"text":e["label"],"role":"link","source_edge_indices":[i],"at":at})
            continue
        dx,dy = b[0]-a[0],b[1]-a[1]
        length = math.hypot(dx,dy)
        if not length:
            return None
        key = tuple(sorted([e["source"],e["target"]]))
        # Opposite source relations use distinct short lanes, never a new bus.
        normal = [-dy/length,dx/length]
        offset = 12 + (pair_count[key]//2)*10
        pair_count[key] += 1
        distance=min(98/abs(dx/length) if dx else float('inf'),42/abs(dy/length) if dy else float('inf'))+4
        points = [[a[0]+dx/length*distance+normal[0]*offset,a[1]+dy/length*distance+normal[1]*offset],
                  [b[0]-dx/length*distance+normal[0]*offset,b[1]-dy/length*distance+normal[1]*offset]]
        from .publication_render import font
        label_offset=max(55,font(27).getlength(e["label"])/2+18)
        at = [(a[0]+b[0])/2+normal[0]*label_offset,(a[1]+b[1])/2+normal[1]*label_offset]
        routes.append({**copy.deepcopy(e),"members":[i],"points":points,"label_at":at,"mode":"topology-link","stroke_style":"solid","bidirectional":False})
        if e["label"]:
            labels.append({"text":e["label"],"role":"link","source_edge_indices":[i],"at":at})
    return {"positions":positions,"routes":routes,"labels":labels,"height":int(max(y for x,y in positions.values())+150),"reading_direction":"source-backed logical grid and attached resource tiers"}


def build(spec, figure, settings):
    grammar = figure.get("semantic_grammar")
    if not grammar:
        return None
    if grammar == "state-machine":
        data = _state_layout(spec)
    elif grammar == "sampled-timing":
        data = _traces(spec)
        if data is None:
            return None
        data.update(height=270+len(data["rows"])*108, positions={}, routes=[], labels=[], reading_direction="aligned named sample axis")
    elif grammar=="directed-process":
        data=_process_layout(spec)
        if data is None:return None
    else:
        data = _topology(spec)
        if data is None:
            return None
        placed = _topology_layout(spec,data)
        if placed is None:
            return None
        data.update(placed)
    from .structure_scene import compact_path
    for route in data["routes"]:
        route["points"] = compact_path(route["points"])
    nodes = [{**copy.deepcopy(n),"members":[n["id"]],"original_group":n["group"],"children":[]} for n in spec["nodes"]]
    edges = [{**copy.deepcopy(e),"id":"s"+str(i),"members":[i]} for i,e in enumerate(spec["edges"])]
    labels = [{"text": n["label"],"role":"object","source_node_ids":[n["id"]]} for n in spec["nodes"]] + data["labels"]
    if grammar=="state-machine":
        data["reset_notes"]=[v for v in spec["annotations"] if re.search(r"\breset\b|复位",v,re.I)]
        data["state_outputs"]={n["id"]:_state_outputs(n["detail"]) for n in spec["nodes"]}
        labels += [{"text":text,"role":"state-output","source_node_ids":[nid]} for nid,values in data["state_outputs"].items() for text in values]
        labels += [{"text":text,"role":"reset-convention","source_field":"annotations"} for text in data["reset_notes"]]
    if grammar=="directed-process":
        labels += [{"text":text,"role":"parameter","source_node_ids":[nid]} for nid,record in data["object_text"].items() for text in record["source_detail"]]
    if grammar == "sampled-timing":
        for row in data["rows"]:
            labels.extend({"text":value,"role":"sample","source_node_ids":[row["id"]],"sample_index":i} for i,value in enumerate(row["values"]))
    plan = {"version":"SEM1","grammar":grammar,"objects":[{"id":n["id"],"label":n["label"],"kind":n["kind"],"source_group":n["group"]} for n in spec["nodes"]],
            "relations":[{**copy.deepcopy(e),"source_edge_index":i} for i,e in enumerate(spec["edges"])], **copy.deepcopy(data),
            "source_semantics_only":True,"actual_image_status":"not_reviewed"}
    layout = {"type":"behavioral","grammar":grammar,"width":WIDTH,"monochrome":settings.get("style")=="monochrome",**data,"macro_nodes":nodes,"macro_edges":edges}
    return {"structure_layout":layout,"layout_scene":{"objects":nodes,"routes":data["routes"],"labels":labels,
               "quality":{"routes_complete":len(data["routes"])==len(spec["edges"]),"semantic_scope_complete":True,"typography_measured":False,
                          "geometry_is_not_raster_acceptance":True}},"label_layout":{"labels":labels},"behavior_plan":plan,
            "macro_nodes":nodes,"macro_edges":edges,"layout_strategy":"semantic-guide","requires_layout_guide":True}


def compile_figure(figure, spec, settings, palette, required_labels=()):
    plan = figure["behavior_plan"]
    grammar = plan["grammar"]
    lines = ["Create one polished technical figure with Image Gen using the supplied semantic target guide.",
             "Image 1 is a source-grounded target structure: preserve every listed object, source membership, directed endpoint and assigned label. It is not the finished image.",
             "Prioritize the reader's task: "+figure["design_contract"]["question"],
             "Use crisp sans-serif type, compact labels and purposeful whitespace. Dark neutral text; sparse role-based accents. Avoid repeated paragraphs, uniform dashboard cards and ornamental frames. Keep technical conventions understandable in grayscale."]
    lines.append("Crop the canvas to the actual objects, labels and necessary return/branch corridors, with a small clean perimeter. A shallow path needs a shallow figure; do not leave a slide-sized empty area above or below it.")
    if re.search(r"inline\s*title|title\s*in\s*(?:the\s*)?image|图内标题",settings.get("notes",""),re.I):
        lines.append("Use the exact supplied title as a modest heading: "+json.dumps(spec["title"],ensure_ascii=False)+". Do not invent another title.")
    else:
        lines.append("The document caption carries the title and ordinary explanation. No large headline, subtitle, footer notes panel, repeated output table or summary cards inside this image. Assigned labels appear once at their objects, paths or sample cells; do not duplicate them elsewhere.")
    lines.append("Use the requested palette: "+json.dumps(palette,ensure_ascii=False)+". If it is monochrome, keep the final image in neutral grayscale even when reference roles use muted hues.")
    if grammar == "state-machine":
        lines += ["State-machine grammar: one circle/ellipse per source state. Every transition, including EACH self-loop, is a solid directed arrow with its exact predicate attached. A transition is not a dashed hardware-control wire. No decision diamonds or event boxes unless they are actual source states.",
                  "Make forward progress, branching, retry/return and hold loops separately traceable. Draw one small initial marker only for a supplied initial state; never invent reset transitions, default holds or priority."]
        lines.append("Keep the guide's state placement, transition attachments and reserved return corridors. Refine strokes and label spacing; do not move a return onto another state or retain both an old and a new route after relocating it.")
        lines.append("Each self-loop preserves the guide's asymmetric plain departure and ONE downward arrowhead at the top re-entry of the SAME state. A loop is not bidirectional. Return predicates sit adjacent to the departing state's exterior leg, not on a distant shared-looking bottom rail; keep each source, predicate and destination inseparable.")
        lines.append("Every transition arrowhead touches its target state outline at the guide's assigned attachment. A return never stops at a nearby condition label or in the gap above a state; preserve the final approach segment all the way into the intended state boundary.")
        for n in spec["nodes"]:
            outputs=plan.get("state_outputs",{}).get(n["id"],[])
            lines.append(json.dumps(n["label"],ensure_ascii=False)+"; visible state outputs: "+("; ".join(outputs) if outputs else "none supplied")+". The ordinary source meaning belongs in the caption, not a paragraph inside the circle: "+json.dumps(n["detail"],ensure_ascii=False))
    elif grammar == "sampled-timing":
        lines += ["Timing grammar: align all source signal rows under the SAME named sampling columns. Use a clean sample-value timing table or discrete trace; do not draw a chain of signal boxes or a procedural flowchart.",
                  "These are sampled values, not exact continuous waveforms. Clock row shows rising sample markers, never fabricated duty cycle. A data token at a sample belongs to that column. Preserve stalled values and adjacent transfer events; do not infer an extra delay or transaction.",
                  "Sampling columns: "+", ".join(plan["axis"])]
        for row in plan["rows"]:
            lines.append(json.dumps(row["label"],ensure_ascii=False)+": "+("rising sample markers" if row["kind"]=="sample-markers" else " | ".join(row["values"])))
    elif grammar=="directed-process":
        lines += ["Functional hardware/process grammar: preserve one symbol per actual source resource and trace the real fork, merge and same-resource return. Buffers/storage are shallow or wider than computation; interfaces are compact endpoints. Keep forward payload and reverse ready/control on separate corridors.",
                  "Every reverse ready/control connection has distinct departure and arrival ports at the resources. Adjacent return paths must not share an outside vertical leg or create a T-junction bypassing the stage; only an actual source junction may merge wires.",
                  "Spatial sequence expresses dependency only. FIFO entries are capacity, not stage latency. Do not infer a cycle schedule, insert stages, merge independent operand streams or convert feedback/control into data."]
        for n in spec["nodes"]:lines.append(json.dumps(n["label"],ensure_ascii=False)+"; source detail "+json.dumps(n["detail"],ensure_ascii=False))
    else:
        lines += ["Topology grammar: use the supplied logical coordinates as a compact regular map. Keep actual attached endpoints near their named router, distinguish storage from routing, and trace every physical-looking line back to an explicit source link.",
                  "Coordinates describe logical topology only, not a measured die floorplan. Do not replace the network with subsystem cards, invent a common bus or infer bandwidth from line width."]
        for anchor in plan["anchors"]:
            node=next(n for n in spec["nodes"] if n["id"]==anchor["id"])
            origin="source-connected drawing position" if anchor.get("coordinate_origin")=="logical drawing embedding" else "supplied logical coordinate"
            lines.append(json.dumps(node["label"],ensure_ascii=False)+" at "+origin+" "+str(anchor["coordinate"]))
        for n in spec["nodes"]:
            lines.append(json.dumps(n["label"],ensure_ascii=False)+"; "+json.dumps(n["detail"],ensure_ascii=False))
    if plan["relations"]:
        names={n["id"]:n["label"] for n in spec["nodes"]}
        lines.append("Exact directed relations, one connector per source relation, including loops:")
        for e in plan["relations"]:
            lines.append(json.dumps(names[e["source"]],ensure_ascii=False)+" → "+json.dumps(names[e["target"]],ensure_ascii=False)+": "+json.dumps(e["label"],ensure_ascii=False))
        lines.append("Closed outgoing-target contract: these are the ONLY arrow destinations allowed from each named object. Every listed source relation appears once, with one target head; no adjacency shortcut or duplicate route.")
        for n in spec["nodes"]:
            targets=list(dict.fromkeys(names[e["target"]] for e in spec["edges"] if e["source"]==n["id"]))
            lines.append(json.dumps(n["label"],ensure_ascii=False)+" may point only to "+("; ".join(json.dumps(t,ensure_ascii=False) for t in targets) if targets else "no other object (terminal)")+".")
    for group in spec["groups"]:
        members=[n["label"] for n in spec["nodes"] if n["group"]==group["id"]]
        if members:lines.append("Real scope "+json.dumps(group["label"],ensure_ascii=False)+" has exactly these members: "+", ".join(json.dumps(v,ensure_ascii=False) for v in members)+". Do not absorb resources from another scope; a visual lane is not ownership.")
    if spec["annotations"]:
        lines.append("Source conventions (keep essential conditions near their source, ordinary explanation in caption):")
        lines.extend(spec["annotations"])
    lines.extend(figure.get("diagram_design",{}).get("render_instructions",[]))
    if required_labels:
        lines.append("Required exact text: "+"; ".join(required_labels))
    if settings.get("notes"):
        lines.append("Presentation request: "+settings["notes"])
    lines.append("Review the generated bitmap against the source: sample values, transition predicates, state outputs, loop directions and logical links. A source guide is not an image-quality certificate.")
    return "\n".join(lines)


def render(result, figure):
    from PIL import Image,ImageDraw,ImageFont
    from .publication_render import font_path
    layout=figure["structure_layout"]
    height=layout["height"]
    img=Image.new("RGB",(WIDTH,height),"white")
    draw=ImageDraw.Draw(img)
    font=ImageFont.truetype(str(font_path()),32,layout_engine=ImageFont.Layout.BASIC)
    small=ImageFont.truetype(str(font_path()),27,layout_engine=ImageFont.Layout.BASIC)
    def text_at(text,center,face=small,max_width=240,erase=True):
        words=re.split(r"\s+",text)
        lines=[];line=""
        for word in words:
            candidate=(line+" "+word).strip()
            if line and draw.textlength(candidate,font=face)>max_width:
                lines.append(line);line=word
            else:line=candidate
        if line:lines.append(line)
        x,y=center
        for i,line in enumerate(lines):
            w=draw.textlength(line,font=face)
            yy=y+(i-(len(lines)-1)/2)*(face.size+4)
            if erase:draw.rectangle((x-w/2-4,yy-3,x+w/2+4,yy+face.size+4),fill="white")
            draw.text((x-w/2,yy),line,font=face,fill="#263238")
    def arrow(points,dashed=False):
        if dashed:
            for a,b in zip(points,points[1:]):
                length=math.hypot(b[0]-a[0],b[1]-a[1])
                for begin in range(0,int(length),15):
                    end=min(begin+8,length)
                    draw.line([(a[0]+(b[0]-a[0])*begin/max(1,length),a[1]+(b[1]-a[1])*begin/max(1,length)),(a[0]+(b[0]-a[0])*end/max(1,length),a[1]+(b[1]-a[1])*end/max(1,length))],fill="#596A74",width=2)
        else:draw.line([tuple(p) for p in points],fill="#263238",width=3)
        a,b=points[-2],points[-1]
        angle=math.atan2(b[1]-a[1],b[0]-a[0])
        tip=tuple(b)
        draw.polygon([tip,(b[0]-14*math.cos(angle)+6*math.sin(angle),b[1]-14*math.sin(angle)-6*math.cos(angle)),
                      (b[0]-14*math.cos(angle)-6*math.sin(angle),b[1]-14*math.sin(angle)+6*math.cos(angle))],fill="#263238")
    grammar=layout["grammar"]
    if grammar=="sampled-timing":
        axis=layout["axis"];left=360;cell=(WIDTH-left-90)/len(axis)
        for col,value in enumerate(axis):text_at(value,[left+(col+.5)*cell,64],font,cell-12)
        for row_index,row in enumerate(layout["rows"]):
            y=150+row_index*108
            draw.line((55,y+75,WIDTH-50,y+75),fill="#DDE3E5",width=1)
            text_at(row["label"],[170,y+24],font,270)
            for col in range(len(axis)):
                x=left+(col+.5)*cell
                if row["kind"]=="sample-markers":
                    draw.line((x,y+50,x,y+4),fill="#596A74",width=2)
                    draw.polygon([(x,y+4),(x-5,y+14),(x+5,y+14)],fill="#596A74")
                else:text_at(row["values"][col],[x,y+24],font,cell-12)
        text_at("Values at named sample edges; inter-edge timing unspecified",[WIDTH/2,height-70],small,1500)
    else:
        if grammar=="state-machine" and layout.get("reset_notes"):
            text_at(" ".join(layout["reset_notes"]),[WIDTH/2,70],small,1500)
        for route in layout["routes"]:arrow(route["points"],route["stroke_style"]=="dashed")
        source={n["id"]:n for n in result["spec"]["nodes"]}
        for nid,(x,y) in layout["positions"].items():
            node=source[nid]
            fill=("#F0F0F0" if node["kind"]!="memory" else "#E4E4E4") if layout.get("monochrome") else "#EDF2F5" if node["kind"]!="memory" else "#E8EEE8"
            if grammar=="state-machine":
                draw.ellipse((x-78,y-78,x+78,y+78),fill=fill,outline="#263238",width=2)
                text_at(node["label"],[x,y-18],font,138,False)
                outputs=_state_outputs(node["detail"])
                if outputs:text_at(", ".join(outputs),[x,y+25],small,140,False)
                if nid in layout["initial_node_ids"]:
                    arrow([[x-30,y+140],[x-14,y+76]])
                    draw.ellipse((x-38,y+139,x-26,y+151),fill="#263238")
            elif grammar=="directed-process":
                w,h=layout["sizes"][nid]
                draw.rectangle((x-w/2,y-h/2,x+w/2,y+h/2),fill=fill,outline="#263238",width=2)
                record=layout["object_text"][nid]
                yy=y-h/2+14
                for line in record["name_lines"]:
                    text_at(line,[x,yy],font,w-16,False);yy+=39
                for line in record["required_detail_lines"]:
                    text_at(line,[x,yy],small,w-16,False);yy+=34
            else:
                draw.rectangle((x-98,y-42,x+98,y+42),fill=fill,outline="#263238",width=2)
                text_at(node["label"],[x,y-16],font,180,False)
        for label in layout["labels"]:text_at(label["text"],label["at"],small,label.get("max_width",310))
    output=io.BytesIO();img.save(output,format="PNG");return output.getvalue()
