"""Frozen arbitrary-input evaluation. Software checks never certify ImageGen pixels.

Replay: python scripts/generalization_eval.py --mode compile --split development
Live (costs the configured provider): --mode live --split development
No provider/model fallback, no prompt rescue, at most the product's one repair.
"""
from __future__ import annotations

import argparse
import ast
import concurrent.futures
import copy
import hashlib
import importlib
import itertools
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import time
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "tests/fixtures/generalization"
PRIVATE = ROOT / ".local/system-v07/holdout"


def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n",encoding="utf-8",newline="\n")


def load_cases(split="development", include_variants=False):
    manifest=json.loads((PUBLIC/"manifest.json").read_text(encoding="utf-8"))
    result=[]
    for item in manifest["cases"]:
        if split!="all" and item["split"]!=split:
            continue
        location=PUBLIC if item["split"]=="development" else (PUBLIC/"heldout" if (PUBLIC/"heldout").exists() else PRIVATE)
        path=location/(item["id"]+".json")
        case=json.loads(path.read_text(encoding="utf-8"))
        if digest(case)!=item["sha256"]:
            raise ValueError("Frozen input/expectation digest mismatch: "+item["id"])
        result.append(case)
    if include_variants and split in {"all","development"}:
        variants=PUBLIC/"variants"
        for item in json.loads((variants/"manifest.json").read_text(encoding="utf-8"))["cases"]:
            case=json.loads((variants/(item["id"]+".json")).read_text(encoding="utf-8"))
            if digest(case)!=item["sha256"]:
                raise ValueError("Frozen variant digest mismatch: "+item["id"])
            result.append(case)
    return result


def chosen(result):
    return next(f for f in result["figures"] if f["id"]==result["selected_figure_id"])


def check(condition, name, failures):
    if not condition:
        failures.append(name)


def normalized(text):
    return re.sub(r"[^\w]+", "", unicodedata.normalize("NFKC",text).casefold())


def predicates_equal(left, right):
    """Check Boolean meaning, accepting written unconditional synonyms.

    Only a tiny parsed Boolean grammar is supported; no eval or code execution.
    Unsupported prose stays a review disagreement, never silently equivalent.
    """
    def parse(text):
        constant=text.strip().casefold()
        if re.fullmatch(r"\(\s*(?:always|unconditional|true|1|无条件)\s*\)",constant):constant=constant[1:-1].strip()
        if constant in {"", "always", "unconditional", "true", "1", "无条件"}:
            return ast.Constant(True)
        text=re.sub(r"!(?!=)"," not ",text).replace("&&"," and ").replace("||"," or ")
        return ast.parse(text.strip(),mode="eval").body
    def names(node):
        return {n.id for n in ast.walk(node) if isinstance(n,ast.Name)}
    def value(node,ctx):
        if isinstance(node,ast.Name):return ctx[node.id]
        if isinstance(node,ast.Constant) and isinstance(node.value,(bool,int)):return bool(node.value)
        if isinstance(node,ast.UnaryOp) and isinstance(node.op,ast.Not):return not value(node.operand,ctx)
        if isinstance(node,ast.BoolOp) and isinstance(node.op,(ast.And,ast.Or)):
            values=[value(v,ctx) for v in node.values]
            return all(values) if isinstance(node.op,ast.And) else any(values)
        raise ValueError("Unsupported predicate grammar")
    try:
        a,b=parse(left),parse(right);variables=sorted(names(a)|names(b))
        if len(variables)>10:return False
        return all(value(a,dict(zip(variables,values)))==value(b,dict(zip(variables,values))) for values in itertools.product((False,True),repeat=len(variables)))
    except (SyntaxError,ValueError,KeyError):
        return False


def matching_nodes(spec, requirements):
    found={}; used=set()
    for requirement in requirements:
        expected=requirement["pattern"]
        candidates=[n for n in spec["nodes"] if n["id"] not in used and normalized(n["label"])==normalized(expected)]
        if not candidates:
            regex=r"(?<![A-Za-z0-9])"+re.escape(expected)+r"(?![A-Za-z0-9])"
            candidates=[n for n in spec["nodes"] if n["id"] not in used and re.search(regex,n["label"],re.I)]
        if len(candidates)==1:
            found[requirement["concept"]]=candidates[0]
            used.add(candidates[0]["id"])
    return found


def owner_ids(node, groups):
    path=[]; current=node.get("group",""); seen=set()
    while current:
        if current in seen or current not in groups:
            raise ValueError("Invalid ownership tree")
        seen.add(current);path.append(current);current=groups[current].get("parent","")
    return path


def owners(node, groups):
    return [groups[group_id]["label"] for group_id in owner_ids(node,groups)]


def semantic_contract(case, result):
    failures=[]; spec=result["spec"]; expected=case["expectations"]
    check(spec["category"] in expected["categories"],"category",failures)
    check(len(spec["nodes"])>=expected["minimum_nodes"],"useful_nonempty_inventory",failures)
    found=matching_nodes(spec,expected["required_concepts"])
    missing=sorted(set(x["concept"] for x in expected["required_concepts"])-set(found))
    check(not missing,"missing_concepts:"+",".join(missing),failures)
    if expected["closed_inventory"]:
        check(len(spec["nodes"])==len(expected["required_concepts"]),"closed_node_inventory",failures)
        check(len(spec["edges"])==len(expected["relations"]),"closed_edge_inventory",failures)
    for source,target,label,kind in expected["relations"]:
        if source not in found or target not in found:
            continue
        matches=[e for e in spec["edges"] if e["source"]==found[source]["id"] and e["target"]==found[target]["id"] and e["kind"]==kind]
        if spec["category"]=="fsm":
            matches=[e for e in matches if predicates_equal(e["label"],label)]
        check(bool(matches),"relation:"+source+"->"+target+":"+kind+(":"+label if spec["category"]=="fsm" else ""),failures)
    original=case["manual_payload"]["spec"]
    source_groups={g["id"]:g for g in original["groups"]};groups={g["id"]:g for g in spec["groups"]}
    # Group IDs/titles are the extractor's choice unless explicitly fixed. The
    # oracle compares actual descendant sets and ancestry, not the word "Chip".
    expected_desc={gid:{n["id"] for n in original["nodes"] if gid in owner_ids(n,source_groups)} for gid in source_groups}
    actual_desc={gid:{n["id"] for n in spec["nodes"] if gid in owner_ids(n,groups)} for gid in groups}
    group_matches={gid:[other for other,members in actual_desc.items() if members=={found[n]["id"] for n in wanted if n in found}]
                   for gid,wanted in expected_desc.items()}
    for concept,node in found.items():
        original_node=next(n for n in original["nodes"] if n["id"]==concept)
        actual_path=owner_ids(node,groups);expected_path=owner_ids(original_node,source_groups)
        current=original_node.get("group","")
        while current:
            check(any(gid in actual_path for gid in group_matches[current]),"owner:"+concept,failures)
            current=source_groups[current].get("parent","")
        # Additional external-only grouping is fine; moving an external endpoint
        # under any supplied internal owner is not.
        if not expected_path:
            check(not any(gid in actual_path for matches in group_matches.values() for gid in matches),"external_scope:"+concept,failures)
    text="\n".join(str(case["natural_input"].get(k,"")) for k in ("description","notes","labels"))
    for section in ("groups","nodes","edges"):
        for item in spec[section]:
            if item.get("origin")=="given":
                check(bool(item.get("evidence")) and item["evidence"] in text,"given_evidence:"+section,failures)
            elif item.get("origin")=="assumed":
                check(not item.get("evidence") and bool(item.get("rationale")),"assumed_provenance:"+section,failures)
            else:
                failures.append("missing_origin:"+section)
    if expected["assumptions_required"]:
        check(bool(spec.get("assumptions")),"completion_assumptions",failures)
        check(all(n["origin"]=="assumed" for n in spec["nodes"]),"sparse_completion_not_given",failures)
        check(len(spec["edges"])>=3,"sparse_connected_example",failures)
    if expected["numeric_claims_not_supplied"]:
        printed=json.dumps(spec,ensure_ascii=False)
        check(not re.search(r"\b\d+(?:\.\d+)?\s*(?:GHz|MHz|GB|MB|TOPS|TFLOPS)\b",printed,re.I),"unsupported_numeric_claim",failures)
    check(chosen(result).get("representation")==expected["representation"],"representation_intent",failures)
    return sorted(set(failures))


def software_contract(source, result):
    """Independent ledger and basic geometric failures; no aesthetic score."""
    failures=[];spec=result["spec"]
    check(spec==source,"canonical_source_changed",failures)
    check(result["source_hash"]==digest(spec),"source_hash",failures)
    source_nodes={n["id"]:n for n in spec["nodes"]};groups={g["id"]:g for g in spec["groups"]}
    for figure in result["figures"]:
        plan=figure.get("diagram_design",{})
        check(plan.get("actual_image_status")=="not_reviewed","pixel_review_status",failures)
        check(bool(plan.get("reading_strategy",{}).get("kind")),"reader_strategy_missing",failures)
        for appearance in plan.get("inventory",{}).get("appearances",[]):
            node_id=appearance.get("source_node_id")
            if node_id:
                check(node_id in source_nodes,"invented_source_node",failures)
                if node_id in source_nodes:
                    check(appearance["label"]==source_nodes[node_id]["label"],"visible_label_changed",failures)
                    path=list(reversed(owners(source_nodes[node_id],groups)))
                    ids=appearance.get("source_owner_path",[])
                    check(path==[groups[g]["label"] for g in ids],"visible_ownership_changed",failures)
        indices=figure.get("source_edge_indices",figure.get("edge_indices",[]))
        check(all(isinstance(i,int) and 0<=i<len(spec["edges"]) for i in indices),"invented_edge_index",failures)
        for edge in figure.get("macro_edges",[]):
            for index in edge.get("members",[]):
                check(0<=index<len(spec["edges"]),"invented_projected_edge",failures)
        # Screen-space boxes of peer actual resources cannot overlap. Containers
        # intentionally contain boxes and are not counted as peers.
        boxes=figure.get("structure_layout",{}).get("boxes",{})
        if isinstance(boxes,dict):
            items=list(boxes.items())
            for i,(aid,a) in enumerate(items):
                for bid,b in items[i+1:]:
                    if all(k in a and k in b for k in ("x","y","width","height")):
                        overlap=min(a["x"]+a["width"],b["x"]+b["width"])-max(a["x"],b["x"])>1e-5 and min(a["y"]+a["height"],b["y"]+b["height"])-max(a["y"],b["y"])>1e-5
                        check(not overlap,"peer_box_overlap:"+aid+":"+bid,failures)
    return sorted(set(failures))


def proxies(result):
    figure=chosen(result); plan=figure.get("diagram_design",{});layout=figure.get("structure_layout",{})
    boxes=layout.get("boxes",{});area=sum(b.get("width",0)*b.get("height",0) for b in boxes.values()) if isinstance(boxes,dict) else None
    grammar="algorithm-flow" if figure.get("algorithm_flow_plan") else "product-explanation" if figure.get("render_brief") else figure.get("composition_diagnostics",{}).get("grammar",layout.get("type",figure.get("layout_strategy")))
    return {"representation":figure.get("representation"),"effective_figure_grammar":grammar,"reading_kind":plan.get("reading_strategy",{}).get("kind"),
            "visible_leaf_appearances":plan.get("burden",{}).get("leaf_appearances"),"peer_box_area_fraction":round(area,5) if area is not None else None,
            "composition_status":plan.get("composition_action",{}).get("status"),"software_proxy_only":True,"imagegen_visual_acceptance":"not_run"}


def metamorphics(case):
    base=case["manual_payload"]
    renamed=copy.deepcopy(base);mapping={n["id"]:"q"+str(i) for i,n in enumerate(base["spec"]["nodes"])}
    labels=sorted({n["label"] for n in base["spec"]["nodes"]},key=len,reverse=True)
    pattern=r"(?<![A-Za-z0-9])(?:"+"|".join(re.escape(label) for label in labels)+r")(?![A-Za-z0-9])"
    renamed_description=re.sub(pattern,lambda match:"Renamed "+match.group(0),base["description"])
    renamed["description"]=renamed_description
    for n in renamed["spec"]["nodes"]:n["id"]=mapping[n["id"]];n["label"]="Renamed "+n["label"]
    for e in renamed["spec"]["edges"]:e["source"]=mapping[e["source"]];e["target"]=mapping[e["target"]]
    for section in ("groups","nodes","edges"):
        for item in renamed["spec"][section]:
            if item.get("origin")=="given":item["evidence"]=renamed_description
    yield "rename_ids_and_labels",renamed
    reordered=copy.deepcopy(base)
    for section in ("nodes","edges","groups"):reordered["spec"][section].reverse()
    yield "reverse_input_arrays",reordered
    punctuation=copy.deepcopy(base);punctuation["description"]="请按以下内容绘图。\n"+base["description"].replace(";","；").replace(".","。")
    yield "chinese_punctuation_description",punctuation
    override=copy.deepcopy(base);override["settings"].update(scene="detail",representation="diagram")
    yield "explicit_technical_override",override


def execute_case(case, mode, engine, provider, output, cache_dir=None):
    start=time.monotonic();entry={"id":case["id"],"split":case["split"],"case_sha256":digest(case),"mode":mode,"provider_called":False}
    try:
        if mode=="compile":
            payload=case["manual_payload"];result=engine.compile_manual(copy.deepcopy(payload))
            entry["software_failures"]=software_contract(payload["spec"],result)
            entry["semantic_extraction_status"]="not_tested_authored_spec"
            variations=[]
            for name,variant in metamorphics(case):
                try:
                    other=engine.compile_manual(variant)
                    failures=software_contract(variant["spec"],other)
                    if name=="explicit_technical_override" and chosen(other).get("representation")!="diagram":failures.append("explicit_representation_override")
                    if name!="explicit_technical_override":
                        if other["spec"]["category"]!=result["spec"]["category"]:failures.append("metamorphic_category_changed")
                        if chosen(other).get("representation")!=chosen(result).get("representation"):failures.append("metamorphic_representation_changed")
                        if proxies(other)["reading_kind"]!=proxies(result)["reading_kind"]:failures.append("metamorphic_reader_task_changed")
                    variations.append({"transformation":name,"failures":failures,"proxies":proxies(other)})
                except Exception as exc:
                    variations.append({"transformation":name,"error":type(exc).__name__,"safe_detail":str(exc)[:500]})
            entry["metamorphics"]=variations
        else:
            messages,context=engine.prepare_request(copy.deepcopy(case["natural_input"]))
            request_path=output/"messages"/(case["id"]+".json")
            write_json(request_path,messages)
            entry["semantic_request_sha256"]=digest(messages)
            if cache_dir:
                data=json.loads((cache_dir/(case["id"]+".json")).read_text(encoding="utf-8"))
                entry["semantic_extraction_status"]="cached_provider_output_new_compilation"
                result=engine.finish_request(copy.deepcopy(data),context)
            else:
                entry["provider_called"]=True
                completion=provider.complete(messages);data=completion["data"]
                entry["provider_model"]=completion["model"];entry["usage"]=completion["usage"]
                write_json(output/"attempts"/(case["id"]+"-initial-response.json"),data)
                write_json(output/"responses"/(case["id"]+".json"),data)
                try:
                    result=engine.finish_request(copy.deepcopy(data),context)
                    entry["repair_attempted"]=False
                except ValueError as exc:
                    entry["repair_attempted"]=True
                    entry["initial_validation_error"]=str(exc)[:1000]
                    repair=engine.prepare_repair(messages,data,context,exc)
                    write_json(output/"attempts"/(case["id"]+"-repair-messages.json"),repair)
                    completion=provider.complete(repair);data=completion["data"]
                    write_json(output/"attempts"/(case["id"]+"-repair-response.json"),data)
                    write_json(output/"responses"/(case["id"]+".json"),data)
                    result=engine.finish_request(copy.deepcopy(data),context)
                entry["semantic_extraction_status"]="live_configured_provider"
            entry["semantic_failures"]=semantic_contract(case,result)
            entry["software_failures"]=software_contract(result["spec"],result)
        write_json(output/"results"/(case["id"]+".json"),result)
        entry["proxies"]=proxies(result)
        entry["source_hash"]=result["source_hash"]
    except Exception as exc:
        entry["error"]=type(exc).__name__
        # ProviderError is sanitized by product. Do not dump transport internals.
        entry["safe_detail"]=str(exc)[:500] if type(exc).__name__ in {"ProviderError","ValueError","AssertionError"} else "See exception class; raw internals suppressed."
    entry["elapsed_seconds"]=round(time.monotonic()-start,3)
    write_json(output/"cases"/(case["id"]+".json"),entry)
    return entry


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode",choices=("compile","live"),default="compile")
    parser.add_argument("--split",choices=("development","holdout","all"),default="development")
    parser.add_argument("--output",type=Path,default=ROOT/".local/system-v07/evaluation")
    parser.add_argument("--source-root",type=Path,default=ROOT/"src")
    parser.add_argument("--cached-responses",type=Path)
    parser.add_argument("--workers",type=int,default=1)
    parser.add_argument("--ids",nargs="*")
    parser.add_argument("--include-variants",action="store_true")
    parser.add_argument("--fail-on-error",action="store_true",help="Exit nonzero for software/semantic fact failures; classification notes are separate.")
    args=parser.parse_args()
    sys.path.insert(0,str(args.source_root.resolve()))
    engine=importlib.import_module("silicon_canvas.engine");provider=importlib.import_module("silicon_canvas.provider")
    cases=[case for case in load_cases(args.split,args.include_variants) if not args.ids or case["id"] in args.ids]
    files={str(p.relative_to(args.source_root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(args.source_root.glob("silicon_canvas/*.py"))}
    report={"schema":"SC-GEN1","mode":args.mode,"split":args.split,"core_files_sha256":digest(files),"source_root":str(args.source_root.resolve()),
            "natural_input_status":"live_configured_provider" if args.mode=="live" and not args.cached_responses else "not_live",
            "cross_provider_neutrality":"not_verified","imagegen_aesthetic_acceptance":"not_run","cases":[]}
    args.output.mkdir(parents=True,exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1,min(3,args.workers))) as pool:
        futures=[pool.submit(execute_case,case,args.mode,engine,provider,args.output,args.cached_responses) for case in cases]
        for future in concurrent.futures.as_completed(futures):
            entry=future.result();report["cases"].append(entry)
            report["cases"].sort(key=lambda x:x["id"]);write_json(args.output/"report.json",report)
            print(json.dumps({k:v for k,v in entry.items() if k in {"id","error","safe_detail","software_failures","semantic_failures","elapsed_seconds","provider_called"}},ensure_ascii=False),flush=True)
    print("Report: "+str(args.output/"report.json"),flush=True)
    failed=any(c.get("error") or c.get("software_failures") or [f for f in c.get("semantic_failures",[]) if f!="category"]
               or any(v.get("error") or v.get("failures") for v in c.get("metamorphics",[])) for c in report["cases"])
    if args.fail_on_error and failed:raise SystemExit(1)


if __name__=="__main__":main()
