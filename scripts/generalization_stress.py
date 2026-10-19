"""Post-freeze structural stress families, deliberately NOT blind evaluation.

Selected-view endpoint coverage is measured separately from source retention.
No ImageGen quality is inferred from a controlled guide or a compilation pass.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
FIXTURES=ROOT/"tests/fixtures/generalization/stress"
sys.path.insert(0,str(Path(__file__).resolve().parent))
from generalization_cases import make,digest
from generalization_eval import chosen,software_contract,write_json


def families():
    cases=[]
    for length in (5,9,16,32):
        nodes=[(f"n{i}",f"Transform {i}","compute","engine") for i in range(length)]
        edges=[(f"n{i}",f"n{i+1}","payload","data") for i in range(length-1)]
        case=make(f"stress-chain-{length}","post_freeze_stress",f"Explain the exact payload mechanism of one Engine with {length} named transforms in the supplied serial dependency order. Keep all source endpoint relations. This is functional dependency, not cycle latency.","dataflow",nodes,edges,groups=[("engine","Engine","")],scene="flow",representation="diagram")
        cases.append(case)
    for width in (2,5,10):
        nodes=[("in","Input","io","")]+[(f"b{i}",f"Parallel Transform {i}","compute","") for i in range(width)]+[("join","Operand Join","compute","")]
        edges=[("in",f"b{i}","operand","data") for i in range(width)]+[(f"b{i}","join",f"term {i}","data") for i in range(width)]
        cases.append(make(f"stress-forkjoin-{width}","post_freeze_stress","Explain an exact parallel operand dependency graph. Each branch consumes Input and independently feeds Operand Join. The join is not specified as addition; dependency is not serialization.","dataflow",nodes,edges,scene="flow",representation="diagram"))
    for size in (4,8):
        nodes=[(f"n{i}",f"Resource {i}","compute","") for i in range(size)]
        edges=[(f"n{i}",f"n{j}",f"request {i}:{j}","control") for i in range(size) for j in range(size) if i!=j]
        cases.append(make(f"stress-dense-control-{size}","post_freeze_stress","Explain exact directed control requests between every distinct supplied pair of resources. There is no shared bus and no implied payload traffic. If the scope cannot fit legibly, report the limit and retain exact source-backed companions.","microarchitecture",nodes,edges,scene="detail",representation="diagram"))
    for lengths in ((2,3,5),(3,7,12)):
        groups=[("device","Device","")]+[(f"g{k}",f"Front End {k}","device") for k in range(3)]
        nodes=[("in","External Source","io","")];edges=[]
        for k,length in enumerate(lengths):
            for i in range(length):
                node=f"n{k}_{i}";nodes.append((node,f"Channel {k} Resource {i}","memory" if i%3==1 else "compute",f"g{k}"))
                edges.append(("in" if i==0 else f"n{k}_{i-1}",node,"samples","data"))
        nodes.extend([("merge","Shared Collector","compute","device"),("out","External Sink","io","")])
        edges.extend([(f"n{k}_{length-1}","merge","result","data") for k,length in enumerate(lengths)])
        edges.append(("merge","out","result","data"))
        for purpose in ("system","flow"):
            intent="Explain subsystem ownership and principal interfaces" if purpose=="system" else "Explain the exact producer/transform/collector mechanism and all supplied endpoint paths"
            cases.append(make(f"stress-heterogeneous-{'-'.join(map(str,lengths))}-{purpose}","post_freeze_stress",intent+". The three front ends intentionally contain unequal resource inventories. Shared Collector belongs directly to Device; source and sink are external. Do not duplicate hardware or treat front ends as identical.","dataflow",nodes,edges,groups=groups,scene=purpose,representation="diagram"))
    return cases


def freeze():
    FIXTURES.mkdir(parents=True,exist_ok=True)
    manifest={"schema":"SC-GEN1-STRESS","status":"post_first_core_freeze_not_blind_not_in_first_run_score","cases":[],
              "hash_basis":"sha256 of UTF-8 canonical JSON object: ensure_ascii=false, sort_keys=true, separators comma/colon; independent of file line endings"}
    for case in families():
        path=FIXTURES/(case["id"]+".json")
        if path.exists() and json.loads(path.read_text(encoding="utf-8"))!=case:
            raise ValueError("Refusing changed stress source "+case["id"])
        write_json(path,case);manifest["cases"].append({"id":case["id"],"sha256":digest(case)})
    write_json(FIXTURES/"manifest.json",manifest)
    return manifest


def view_metrics(case,result,layout_guide):
    figure=chosen(result);spec=case["manual_payload"]["spec"];source_edges=spec["edges"]
    # Only an actual rendered route with original endpoint IDs counts as exact.
    # A group-summary route may carry indices without exposing the mechanism.
    routes=figure.get("layout_scene",{}).get("routes",[])
    exact=set();projected=set();route_members=set()
    for route in routes:
        for i in route.get("members",[]):
            if not isinstance(i,int) or not 0<=i<len(source_edges):continue
            route_members.add(i);edge=source_edges[i]
            if route.get("source")==edge["source"] and route.get("target")==edge["target"]:exact.add(i)
            elif route.get("bidirectional") and route.get("source")==edge["target"] and route.get("target")==edge["source"]:exact.add(i)
            else:projected.add(i)
    selected_nodes={a["source_node_id"] for a in figure.get("diagram_design",{}).get("inventory",{}).get("appearances",[]) if a.get("source_node_id")}
    layout=figure.get("structure_layout",{});canvas=layout.get("canvas",{});typography=layout.get("typography",{})
    scene=figure.get("layout_scene",{});width=scene.get("width");height=scene.get("height");target=typography.get("target_width_mm")
    required=bool(figure.get("requires_layout_guide"));guide=layout_guide.render(result,figure)
    limitations=[]
    if required and not guide:limitations.append("required_guide_unavailable")
    if len(exact)<len(source_edges):limitations.append("primary_not_complete_endpoint_mechanism")
    if len(selected_nodes)<len(spec["nodes"]):limitations.append("primary_has_deferred_source_resources")
    if figure.get("diagram_design",{}).get("composition_action",{}).get("status")!="planned":limitations.append("planner_does_not_report_planned_composition")
    physical_height=(target*height/width) if target and width and height else None
    if physical_height and physical_height>240:limitations.append("primary_height_exceeds_240mm_at_declared_width")
    return {"source_nodes":len(spec["nodes"]),"source_edges":len(source_edges),"selected_visible_source_nodes":len(selected_nodes),
            "selected_rendered_routes":len(routes),"selected_exact_endpoint_source_edges":len(exact),"selected_projected_source_edges":len(projected),
            "selected_unrouted_or_deferred_source_edges":len(set(range(len(source_edges)))-route_members),
            "selected_unrepresented_source_node_ids":sorted({n["id"] for n in spec["nodes"]}-selected_nodes),
            "source_ledger_retained":spec==result["spec"],"primary_figure_id":figure["id"],"figure_count":len(result["figures"]),
            "scene":case["manual_payload"]["settings"]["scene"],"layout_strategy":figure.get("layout_strategy"),
            "composition_status":figure.get("diagram_design",{}).get("composition_action",{}).get("status"),"geometry_controlled":figure.get("diagram_design",{}).get("composition_action",{}).get("geometry_controlled"),"required_guide":required,"required_guide_available":bool(guide) if required else None,"guide_rendered_for_audit":bool(guide),
            "target_width_mm":target,"nominal_body_pt":typography.get("body_pt"),"height_at_declared_width_mm":round(physical_height,2) if physical_height else None,
            "document_size_typography_actually_checked":False,"limitations":limitations,"imagegen_aesthetics":"not_run"}


def evaluate_one(entry,source_root,output):
    sys.path.insert(0,str(source_root.resolve()))
    engine=importlib.import_module("silicon_canvas.engine");layout_guide=importlib.import_module("silicon_canvas.layout_guide")
    case=json.loads((FIXTURES/(entry["id"]+".json")).read_text(encoding="utf-8"));start=time.monotonic()
    if digest(case)!=entry["sha256"]:raise ValueError("Frozen stress source changed")
    record={"id":entry["id"],"source_sha256":entry["sha256"]}
    try:
        result=engine.compile_manual(case["manual_payload"]);record.update(view_metrics(case,result,layout_guide));record["software_failures"]=software_contract(case["manual_payload"]["spec"],result)
        write_json(output/"results"/(entry["id"]+".json"),result)
    except Exception as exc:record.update(error=type(exc).__name__,safe_detail=str(exc)[:500])
    record["elapsed_seconds"]=round(time.monotonic()-start,3)
    write_json(output/"cases"/(entry["id"]+".json"),record)
    return record


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--freeze",action="store_true");p.add_argument("--source-root",type=Path,default=ROOT/"src");p.add_argument("--output",type=Path,default=ROOT/".local/system-v07/stress-current");p.add_argument("--case-timeout-seconds",type=int,default=90);p.add_argument("--one-case",help=argparse.SUPPRESS);args=p.parse_args()
    if args.freeze:print(json.dumps(freeze(),indent=2));return
    if not 1<=args.case_timeout_seconds<=120:p.error("Per-case timeout must be 1..120 seconds")
    manifest=json.loads((FIXTURES/"manifest.json").read_text(encoding="utf-8"));report={"schema":"SC-GEN1-STRESS","not_blind":True,"per_case_timeout_seconds":args.case_timeout_seconds,"cases":[]}
    if args.one_case:
        entry=next(entry for entry in manifest["cases"] if entry["id"]==args.one_case)
        evaluate_one(entry,args.source_root,args.output);return
    files={str(q.relative_to(args.source_root)):hashlib.sha256(q.read_bytes()).hexdigest() for q in sorted(args.source_root.glob("silicon_canvas/*.py"))};report["core_files_sha256"]=digest(files)
    for entry in manifest["cases"]:
        try:
            completed=subprocess.run([sys.executable,str(Path(__file__).resolve()),"--one-case",entry["id"],"--source-root",str(args.source_root.resolve()),"--output",str(args.output.resolve())],capture_output=True,timeout=args.case_timeout_seconds)
            if completed.returncode:record={"id":entry["id"],"error":"EvaluationChildFailure","exit_code":completed.returncode}
            else:record=json.loads((args.output/"cases"/(entry["id"]+".json")).read_text(encoding="utf-8"))
        except subprocess.TimeoutExpired:record={"id":entry["id"],"error":"Timeout","timeout_seconds":args.case_timeout_seconds}
        report["cases"].append(record);write_json(args.output/"report.json",report)
        print(json.dumps({k:record[k] for k in ("id","source_nodes","source_edges","selected_exact_endpoint_source_edges","selected_unrouted_or_deferred_source_edges","limitations","error") if k in record}),flush=True)


if __name__=="__main__":main()
