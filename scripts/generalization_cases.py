"""Original synthetic evaluation inputs; no fixture is a model response."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "tests/fixtures/generalization"
PRIVATE = ROOT / ".local/system-v07/holdout"


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def make(case_id, split, description, category, nodes, edges, *, groups=(), scene="auto", representation="auto", expected_representation="diagram", assumptions=False):
    """Independent authored graph tests compilation; original sentence tests semantics."""
    spec = {"title": case_id, "summary": "Original synthetic evaluation, not a real product.", "category": category,
            "verbatim_labels": [], "groups": [], "nodes": [], "edges": [], "layout": "", "steps": [],
            "annotations": [], "assumptions": ["通用示意，未给定的模块与连接为建议。"] if assumptions else [], "questions": [], "checks": []}
    provenance = {"origin": "assumed" if assumptions else "given", "evidence": "" if assumptions else description,
                  "rationale": "通用架构建议" if assumptions else ""}
    for group_id, label, parent in groups:
        spec["groups"].append({"id": group_id, "label": label, "parent": parent, **provenance})
    for item in nodes:
        node_id, label, kind, group, *extra = item
        spec["nodes"].append({"id": node_id, "label": label, "kind": kind, "group": group, "detail": "", **provenance, **(extra[0] if extra else {})})
    for source, target, label, kind in edges:
        spec["edges"].append({"source": source, "target": target, "label": label, "kind": kind, **provenance})
    required = [] if assumptions else [{"concept": item[0], "pattern": item[1]} for item in nodes]
    return {"id": case_id, "split": split, "natural_input": {"description": description, "scene": scene, "representation": representation,
            "completion_mode": "auto" if assumptions else "strict", "language": "en"},
            "expectations": {"categories": [category], "required_concepts": required, "relations": [list(edge) for edge in edges] if not assumptions else [],
                "ownership": {item[0]: item[3] for item in nodes if item[3]}, "closed_inventory": not assumptions,
                "minimum_nodes": 5 if assumptions else len(nodes), "representation": expected_representation,
                "assumptions_required": assumptions, "numeric_claims_not_supplied": assumptions},
            "manual_payload": {"description": description, "settings": {"scene": scene, "representation": representation, "completion_mode": "strict"}, "spec": spec}}


def authored_cases():
    # Expectations are frozen before comparison. Holdout contents stay under .local
    # until the implementation owner declares its core freeze; IDs/hashes are public.
    cases = []
    cases.append(make("fresh-01-soc", "development", "画一个完整的通用 SoC 系统，面向架构文档。", "architecture",
        [("cpu","CPU","compute","soc"),("fabric","Interconnect","io","soc"),("rom","Boot ROM","memory","soc"),("sram","SRAM","memory","soc"),("dma","DMA","io","soc"),("mc","Memory Controller","control","soc"),("dram","External DRAM","memory","")],
        [("cpu","fabric","","data"),("dma","fabric","","data"),("fabric","rom","","data"),("fabric","sram","","data"),("fabric","mc","","data"),("mc","dram","","data")],groups=[("soc","SoC","")],assumptions=True))
    cases.append(make("fresh-02-camera", "development", "System overview. Only these resources: on-chip Sensor Port, ISP, Encoder, SRAM, DMA; off-chip Host. Sensor Port sends pixels to ISP; ISP writes frames to SRAM; Encoder reads SRAM; Encoder sends bitstream to DMA; DMA sends bitstream to Host. Do not add resources or connections.", "architecture",
        [("sensor","Sensor Port","io","chip"),("isp","ISP","compute","chip"),("enc","Encoder","compute","chip"),("sram","SRAM","memory","chip"),("dma","DMA","io","chip"),("host","Host","io","")],
        [("sensor","isp","pixels","data"),("isp","sram","frames","data"),("sram","enc","frames","data"),("enc","dma","bitstream","data"),("dma","host","bitstream","data")],groups=[("chip","Chip","")]))
    cases.append(make("fresh-03-softmax", "development", "Algorithm dataflow for stable softmax. Only X, Reduce Max, Subtract, Exponential, Reduce Sum, Divide, Y. X is a vector N; m=max_i X_i; Z_i=X_i-m; E_i=exp(Z_i); s=sum_i E_i; Y_i=E_i/s. Both X and Reduce Max feed Subtract, Exponential feeds both Reduce Sum and Divide, and Reduce Sum also feeds Divide. Divide produces Y. No hardware mapping.", "algorithm",
        [("x","X","compute","",{"diagram_role":"tensor","tensor_shape":"N"}),("max","Reduce Max","compute","",{"diagram_role":"reduction","reduction_axis":"i","detail":"m=max_i X_i"}),("sub","Subtract","compute","",{"diagram_role":"operator","detail":"Z_i=X_i-m"}),("exp","Exponential","compute","",{"diagram_role":"operator","detail":"E_i=exp(Z_i)"}),("sum","Reduce Sum","compute","",{"diagram_role":"reduction","reduction_axis":"i","detail":"s=sum_i E_i"}),("div","Divide","compute","",{"diagram_role":"operator","detail":"Y_i=E_i/s"}),("y","Y","compute","",{"diagram_role":"tensor","tensor_shape":"N"})],
        [("x","max","X","data"),("x","sub","X","data"),("max","sub","m","data"),("sub","exp","Z","data"),("exp","sum","E","data"),("exp","div","E","data"),("sum","div","s","data"),("div","y","Y","data")]))
    cases.append(make("fresh-04-filter-state", "development", "Show a one-step recurrent filter computation with only X, Previous State, Scale Input, Scale State, Add, Next State. Scale Input computes a*x[t]; Scale State computes b*h[t-1]; both terms feed Add; Add produces Next State h[t]. Previous State and Next State are different logical versions. No feedback control, no hardware, no cycle schedule.", "algorithm",
        [("x","X","compute","",{"diagram_role":"tensor"}),("prev","Previous State","memory","",{"diagram_role":"state","detail":"h[t-1]"}),("sx","Scale Input","compute","",{"diagram_role":"operator","detail":"a*x[t]"}),("sh","Scale State","compute","",{"diagram_role":"operator","detail":"b*h[t-1]"}),("add","Add","compute","",{"diagram_role":"operator"}),("next","Next State","memory","",{"diagram_role":"state","detail":"h[t]"})],
        [("x","sx","x[t]","data"),("prev","sh","h[t-1]","data"),("sx","add","a*x[t]","data"),("sh","add","b*h[t-1]","data"),("add","next","h[t]","data")]))
    cases.append(make("fresh-05-request-fsm", "development", "Draw an exact state transition diagram with only IDLE, BUSY, DONE. Reset enters IDLE. IDLE goes to BUSY on start, holds on !start. BUSY goes to DONE on ack, holds on !ack. DONE unconditionally goes to IDLE. Events are transition labels, not resource nodes.", "fsm",
        [("idle","IDLE","state",""),("busy","BUSY","state",""),("done","DONE","state","")],
        [("idle","busy","start","control"),("idle","idle","!start","control"),("busy","done","ack","control"),("busy","busy","!ack","control"),("done","idle","","control")]))
    cases[-1]["manual_payload"]["spec"]["annotations"]=["Reset enters IDLE."]
    cases.append(make("fresh-06-credit-pipeline", "development", "Dataflow for a credit-controlled pipeline; only Producer, Pack, FIFO, Unpack, Consumer. Payload flows Producer -> Pack -> FIFO -> Unpack -> Consumer. Separate control credit flows Consumer -> Unpack -> FIFO -> Pack -> Producer. FIFO capacity is 3 entries, not a latency. No cycles or stage latencies are supplied.", "pipeline",
        [("p","Producer","io",""),("pack","Pack","stage",""),("fifo","FIFO","memory","",{"detail":"3 entries"}),("unpack","Unpack","stage",""),("c","Consumer","io","")],
        [("p","pack","payload","data"),("pack","fifo","payload","data"),("fifo","unpack","payload","data"),("unpack","c","payload","data"),("c","unpack","credit","control"),("unpack","fifo","credit","control"),("fifo","pack","credit","control"),("pack","p","credit","control")]))
    cases.append(make("fresh-07-storage-product", "development", "Commercial product introduction for a storage controller. Explain the system relationships with a functional cutaway, not just an exterior cover. Inside the Controller: Host Interface, Command Processor, ECC Engine, Flash Interface. Host and Flash Devices are external. Only these paths: Host -> Host Interface -> Command Processor -> ECC Engine -> Flash Interface -> Flash Devices. This is a logical illustration, not a measured floorplan.", "architecture",
        [("host","Host","io",""),("hi","Host Interface","io","chip"),("cmd","Command Processor","control","chip"),("ecc","ECC Engine","compute","chip"),("fi","Flash Interface","io","chip"),("flash","Flash Devices","memory","")],
        [("host","hi","","data"),("hi","cmd","","data"),("cmd","ecc","","data"),("ecc","fi","","data"),("fi","flash","","data")],groups=[("chip","Controller","")],expected_representation="system_illustration"))
    ringnodes=[(f"r{i}",f"Router {i}","io","") for i in range(5)]
    ringedges=[(f"r{i}",f"r{(i+1)%5}","ring hop","data") for i in range(5)]
    cases.append(make("fresh-08-directed-ring", "development", "Topology diagram with only Router 0, Router 1, Router 2, Router 3, Router 4. A unidirectional ring has exactly Router 0 -> Router 1 -> Router 2 -> Router 3 -> Router 4 -> Router 0. No reverse or diagonal links, no shared bus and no implicit coherence guarantee.", "memory",ringnodes,ringedges))
    return cases


def freeze():
    PUBLIC.mkdir(parents=True,exist_ok=True)
    PRIVATE.mkdir(parents=True,exist_ok=True)
    manifest = {"schema":"SC-GEN1", "status":"expectations_frozen_before_core_changes", "cases":[],
                "hash_basis":"sha256 of UTF-8 canonical JSON object: ensure_ascii=false, sort_keys=true, separators comma/colon; independent of file line endings"}
    heldout=PUBLIC/"heldout" if (PUBLIC/"heldout").exists() else PRIVATE
    cases = authored_cases() + [json.loads(p.read_text(encoding="utf-8")) for p in sorted(heldout.glob("sealed-*.json"))]
    for case in cases:
        target=(PUBLIC if case["split"]=="development" else PRIVATE)/(case["id"]+".json")
        body=json.dumps(case,ensure_ascii=False,indent=2)+"\n"
        if target.exists() and target.read_text(encoding="utf-8") != body:
            raise RuntimeError("Refusing to rewrite frozen case "+case["id"])
        target.write_text(body,encoding="utf-8",newline="\n")
        manifest["cases"].append({"id":case["id"],"split":case["split"],"sha256":digest(case)})
    path=PUBLIC/"manifest.json"
    if path.exists() and json.loads(path.read_text(encoding="utf-8"))!=manifest:
        raise RuntimeError("Frozen manifest changed")
    path.write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8",newline="\n")
    return manifest


if __name__=="__main__":
    print(json.dumps(freeze(),indent=2))
