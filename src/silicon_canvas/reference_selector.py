"""Select local figure grammar by the current expression task, never by a model.

Scores are inspectable relevance heuristics, not visual quality certification.
Only focus/diagram_type/features are used as reference evidence. Paper captions,
source module inventories and prompt_rules are deliberately not content rules.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path, PurePosixPath
import re

REFERENCE_ROOT = Path(__file__).resolve().parent / "reference_images"
MANIFESTS = ("paper_manifest.json", "isca_manifest.json", "commercial_manifest.json", "algorithm_manifest.json")
REFERENCE_SCOPE = (
    "Learn only the matched visual grammar. Keep the target style's palette and "
    "the target spec's objects, ownership, counts and directed relationships; "
    "do not import source topology, brands, numerical values or figure captions."
)

# A small vocabulary of drawing mechanisms, shared by new and old references.
# None of these rules mention a vendor, input title, or a preferred image path.
TRAITS = {
    "tensor": ("tensor-shapes", "matrix-glyphs", "feature-maps", "张量形状", "矩阵图形", "特征图"),
    "operator": ("operator-graph", "explicit-operators", "tensor-versus-operator", "算子图", "显式运算"),
    "recurrence": ("state-rail", "state-update", "recurrence", "状态通道", "状态更新", "递推"),
    "reuse": ("data-residency", "tile-reuse", "materialization", "streamed-tiles", "驻留", "分块复用", "物化"),
    "organization": ("system-overview", "system_overview", "overview-to", "system-and-pe-detail", "chip-to-subsystem", "functional-groups", "resource-columns", "private-shared-hierarchy", "nested-cores", "shared-resource-bands", "系统总览", "资源层级", "芯片阵列", "共同骨架"),
    "hierarchy": ("hierarchy", "hierarchical", "nested", "containment", "functional-zones", "层级", "嵌套", "容器", "分区"),
    "repetition": ("repeat", "regular-array", "regular-row-array", "aligned-columns", "simd-lanes", "chiplet-array", "同构", "重复", "等宽列", "规整网格"),
    "private_shared": ("private-shared", "repeated-partitions", "shared-resources", "cache-hierarchy", "各自", "私有", "共享指令", "共享资源"),
    "shared_band": ("shared-bands", "shared-resource-bands", "horizontal-bands", "shared-memory-band", "fixed-function-bands", "全局缓冲", "共享", "横带", "连续竖条"),
    "zoom": ("zoom", "representative-detail", "representative-instance", "overview-plus-detail", "system-and-pe-detail", "overview-to-hbm-to-unit", "chip-to-subsystem-to-datapath", "展开", "放大引线"),
    "flow": ("datapath", "main-path", "main-chain", "short-connectors", "named-streams", "numbered-flow", "input-engine-output", "主路径", "主链", "数据方向", "短直角"),
    "dual_input": ("dual-input", "两个输入", "双输入", "two input", "two operand", "两个操作数"),
    "branch_merge": ("compute-accumulate-separation", "dual-path", "parallel-execution", "并行支路", "汇入", "分支", "归并", "计算与累加"),
    "return": ("return-path", "feedback-routing", "outer-route", "返回", "回写", "折回", "外围绕行"),
    "memory": ("memory-paths", "memory-hierarchy", "cache-hierarchy", "aligned-cache-levels", "memory-behavior", "memory-domain", "control-datapath-memory-zones", "aligned-memory-compute-stages", "访存", "缓存层级", "存储层", "行缓冲", "读写路径"),
    "banked": ("buffer-banks", "bank", "banked", "行缓冲区", "多个 Bank", "存储 Bank"),
    "control": ("controller-row", "cpu-microarchitecture", "separate-configuration-plane", "control-datapath-separation", "instruction", "控制核", "指令", "调度", "仲裁"),
    "control_data": ("control-versus-data", "control-datapath-separation", "separate-control-path", "separate-configuration-plane", "control-datapath-memory-zones", "控制与数据", "控制命令", "配置关系", "副通道"),
    "swimlane": ("swimlane", "resource-swimlanes", "生命线", "泳道", "时间轴"),
    "pipeline": ("pipeline", "stage-backgrounds", "dependency-arrows", "event-alignment", "流水", "计算阶段", "执行阶段", "生成阶段"),
    "timing": ("coherence-sequence", "space-time-grid", "event-alignment", "pipeline-fill-versus-steady-state", "周期", "时刻", "时间自上而下", "消息"),
    "topology": ("mesh-topology", "multi-network-topology", "noc-router", "noc-behavior", "interconnect-backbone", "typed-endpoints", "protocol-routing", "互联拓扑", "路由器", "网格"),
    "reduction": ("reduction-tree", "active-path-highlight", "partial-sum-flow", "归约", "加法树", "乘法和累加"),
    "comparison": ("comparison", "before-after", "matched-layout", "small-multiples", "并列方案", "对照", "两种方案", "相同拓扑"),
    "package": ("layered-package", "3d-package", "package-exploded", "isometric", "exploded-layer", "立体", "堆叠封装", "爆炸图"),
}
TRAIT_NAMES = {
    "tensor": "张量与形状", "operator": "运算表达", "recurrence": "递推状态", "reuse": "分块与驻留",
    "organization": "资源组织", "hierarchy": "包含层级", "repetition": "重复单元",
    "private_shared": "私有与共享分区", "shared_band": "共享资源带", "zoom": "代表实例展开",
    "flow": "连续主路径", "dual_input": "双输入汇合", "branch_merge": "分支与汇合",
    "return": "外围返回路径", "memory": "存储路径", "banked": "存储 Bank",
    "control": "控制组织", "control_data": "控制与数据区分", "swimlane": "资源泳道",
    "pipeline": "流水/阶段依赖", "timing": "时间与交互", "topology": "互联拓扑",
    "reduction": "归约", "comparison": "同布局对比", "package": "封装分层",
}
GENRES = {
    "algorithm": {"algorithm": 6, "dataflow": 3, "behavior": 1, "flow": 1},
    "organization": {"architecture": 4, "microarchitecture": 1, "memory": 0},
    "control": {"microarchitecture": 4, "architecture": 2, "dataflow": 0, "algorithm": 0},
    "flow": {"dataflow": 4, "microarchitecture": 4, "memory": 2, "architecture": 1, "pipeline": 1},
    "memory": {"memory": 6, "microarchitecture": 2, "dataflow": 2, "architecture": 1},
    "pipeline": {"pipeline": 6, "dataflow": 3, "timing": 1, "microarchitecture": 1},
    "timing": {"timing": 6, "pipeline": 2, "dataflow": 0},
    "topology": {"architecture": 4, "memory": 4, "microarchitecture": 2, "dataflow": 0},
    "package": {"architecture": 4, "memory": 3, "microarchitecture": 0},
    "behavior": {"algorithm": 4, "fsm": 4, "dataflow": 1},
}

# Reference metadata chooses mechanisms; reference captions never become
# generation instructions. These refine the selected display without changing
# its objects, routing, ownership, palette or fixed guide coordinates.
_EXPRESSION_RULES = {
    "organization": "Within the selected arrangement, make existing ownership headings quieter than resource names and keep peer labels on consistent typographic baselines; do not add headings or group boundaries.",
    "hierarchy": "Use a consistent stroke hierarchy for the existing ownership boundaries, keeping enclosing frames quieter than contained resources; preserve every supplied boundary and placement.",
    "repetition": "Give confirmed equivalent instances the same graphic treatment and label rhythm within their existing positions, while retaining all source-backed differences; do not duplicate, fold or relocate instances.",
    "private_shared": "Make the existing distinction between private ownership and shared resources readable through heading and boundary hierarchy; keep the selected membership and individual connections intact.",
    "shared_band": "Treat each already shared resource as a coherent visual unit across its existing extent; do not create a bus or merge independent links to achieve a continuous appearance.",
    "zoom": "Keep the existing representative-detail inset visually subordinate and its identity link unambiguous, preserving its approved position and the distinction between an explanation and another hardware instance.",
    "flow": "Make the selected data path easy to trace with consistent arrowheads, clear endpoints and restrained line weight; preserve fixed guide routes and avoid ornamental bends on unconstrained clear segments.",
    "dual_input": "Keep the supplied operands individually traceable at their existing convergence, with distinct readable endpoints and labels; do not imply an additional merge or an order between independent inputs.",
    "branch_merge": "Make existing branch and join points readable with clean junctions and distinct arrowheads; preserve the supplied branches, convergence semantics and selected route geometry.",
    "return": "Keep each existing return path distinguishable from forward traffic through clear arrowheads and endpoint labels; preserve its routing and do not add an outer detour for decoration.",
    "memory": "Use consistent silhouettes and text hierarchy for the visible storage resources while preserving their distinct levels and connections; do not add storage tiers or a common bus.",
    "control_data": "Differentiate the existing control and data paths using the selected stroke conventions and a consistent weight hierarchy; preserve their endpoints without introducing another lane or legend.",
    "tensor": "Keep supplied mathematical objects visually distinct from operations, with shape annotations legible and associated with their own object; preserve the selected glyph grammar and do not invent dimensions.",
    "operator": "Give existing operation names and exact mathematical expressions a consistent typographic hierarchy, retaining their full meaning without duplicating prose inside the glyphs.",
    "recurrence": "Keep the supplied state symbols and update dependencies recognizable throughout the existing recurrence, using consistent label treatment; do not unroll iterations or invent an extra state rail.",
    "reuse": "Make the already specified residency and reuse annotations concise and consistently placed beside their existing objects; do not invent buffers, copies or data movement.",
    "timing": "Use consistent visual alignment for the supplied event or time positions and keep labels clear of their marks; preserve every event position, interval and stated ordering.",
    "reduction": "Make the existing reduction and its supplied operands readable with a consistent operator treatment and precise endpoints; do not infer additional reduction levels from a junction.",
}


def _items(value):
    return value if isinstance(value, list) else []


def _text(value):
    return value if isinstance(value, str) else ""


def _safe_raster(relative):
    """Reject escapes, absolute paths, links outside the root and fake rasters."""
    if not isinstance(relative, str) or not relative or "\x00" in relative or ":" in relative:
        return None
    relative = relative.replace("\\", "/")
    name = PurePosixPath(relative)
    if name.is_absolute() or ".." in name.parts or name.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        return None
    try:
        root = REFERENCE_ROOT.resolve()
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            return None
        with path.open("rb") as stream:
            header = stream.read(12)
        valid = (name.suffix.lower() == ".png" and header.startswith(b"\x89PNG\r\n\x1a\n")) or (
            name.suffix.lower() in {".jpg", ".jpeg"} and header.startswith(b"\xff\xd8\xff")) or (
            name.suffix.lower() == ".webp" and header[:4] == b"RIFF" and header[8:12] == b"WEBP")
        return path.relative_to(root).as_posix() if valid else None
    except (OSError, RuntimeError, ValueError):
        return None


def _reference_traits(record):
    parts = [*_items(record.get("focus")), *_items(record.get("features")), record.get("diagram_type", "")]
    corpus = "\n".join(_text(part) for part in parts).casefold().replace("_", "-")
    return {trait for trait, needles in TRAITS.items() if any(needle.casefold().replace("_", "-") in corpus for needle in needles)}


def _records():
    merged = {}
    for manifest in MANIFESTS:
        try:
            data = json.loads((REFERENCE_ROOT / manifest).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for raw in _items(data.get("items")) if isinstance(data, dict) else []:
            if not isinstance(raw, dict):
                continue
            path = _safe_raster(raw.get("path"))
            if not path and data.get("metadata_only") is True:
                candidate = raw.get("path", "")
                name = PurePosixPath(candidate) if isinstance(candidate, str) else PurePosixPath("..")
                if not name.is_absolute() and ".." not in name.parts and "\\" not in str(name) and name.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
                    path = str(name)
            if not path:
                continue
            kind = _text(raw.get("diagram_type")).casefold()
            focus = [_text(item).casefold() for item in _items(raw.get("focus"))]
            if kind in {"caption", "figure-caption", "legend", "legend-only", "performance", "chart", "table", "photo"} or set(focus) & {"caption-only", "legend-only", "performance-chart"}:
                continue
            item = merged.setdefault(path, {"path": path, "focus": [], "features": [], "manifests": [], "source_url": ""})
            for field in ("focus", "features"):
                item[field] = list(dict.fromkeys([*item[field], *(_text(value) for value in _items(raw.get(field)) if _text(value))]))
            item["manifests"].append(manifest)
            for field in ("diagram_type", "category", "verification", "width", "height", "source_url", "reference_tier"):
                if field in {"diagram_type", "category", "source_url", "reference_tier"} and not isinstance(raw.get(field), str):
                    continue
                if raw.get(field):
                    item[field] = raw[field]
    for record in merged.values():
        record["traits"] = _reference_traits(record)
        record["genre"] = record.get("diagram_type") or record.get("category") or record["path"].split("/")[0]
    return list(merged.values())


def _visible_graph(spec, figure):
    """Rank the drawing the reader sees, not the source ledger it summarizes."""
    layout = figure.get("structure_layout") if isinstance(figure.get("structure_layout"), dict) else {}
    brief = figure.get("render_brief") if isinstance(figure.get("render_brief"), dict) else {}
    visible = brief.get("visible_content")
    if isinstance(visible, dict):
        # Region membership is a caption/inventory, not visible internal wiring.
        nodes = [{"id": item["id"], "label": item.get("label", ""),
                  "kind": item.get("role", "resource")}
                 for item in _items(visible.get("regions")) + _items(visible.get("context_objects"))
                 if isinstance(item, dict) and isinstance(item.get("id"), str)]
        edges = [{**edge, "kind": (_items(edge.get("kinds")) or ["relation"])[0]}
                 for edge in _items(visible.get("relationships")) if isinstance(edge, dict)]
    elif layout.get("type") in {"publication", "behavioral"} and isinstance(layout.get("macro_nodes"), list):
        # Finalized guides can differ from the initial reading-plan projection.
        nodes, edges = layout["macro_nodes"], _items(layout.get("macro_edges"))
    elif isinstance(figure.get("macro_nodes"), list) or figure.get("abstract"):
        nodes = _items(figure.get("macro_nodes", layout.get("macro_nodes")))
        edges = _items(figure.get("macro_edges", layout.get("macro_edges")))
    else:
        nodes = _items(spec.get("nodes"))
        if isinstance(figure.get("node_ids"), list):
            wanted = {item for item in figure["node_ids"] if isinstance(item, str)}
            nodes = [node for node in nodes if isinstance(node, dict) and node.get("id") in wanted]
        all_edges = _items(spec.get("edges"))
        edges = [all_edges[index] for index in figure["edge_indices"] if type(index) is int and 0 <= index < len(all_edges)] if isinstance(figure.get("edge_indices"), list) else all_edges
    nodes = [node for node in nodes if isinstance(node, dict) and isinstance(node.get("id"), str)]
    ids = {node["id"] for node in nodes}
    return nodes, [edge for edge in edges if isinstance(edge, dict) and edge.get("source") in ids and edge.get("target") in ids]


def _visible_groups(spec, nodes, layout):
    """Only ownership represented by this display can suggest visual nesting."""
    ids = {node["id"] for node in nodes}
    ids.update(node.get("original_group", node.get("group", "")) for node in nodes)
    ids.update(container.get("source_group") for container in _items(layout.get("containers")) if isinstance(container, dict) and container.get("render_boundary") is not False)
    return [group for group in _items(spec.get("groups")) if isinstance(group, dict) and group.get("id") in ids]


def _visible_repetition(nodes, figure, layout):
    ids = {node["id"] for node in nodes}
    families = _items(layout.get("repeat_families")) + _items(figure.get("repeat_families"))
    for family in families:
        if not isinstance(family, dict):
            continue
        instances = {item for item in _items(family.get("instances")) if isinstance(item, str)}
        if len(ids & instances) >= 2:
            return True
    equivalents = Counter(node.get("equivalent_to") for node in nodes if node.get("equivalent_to") and node["id"] != node["equivalent_to"])
    return any(count >= 2 or (target in ids and count >= 1) for target, count in equivalents.items())


def _has_cycle(edges):
    remaining, successors = Counter(), defaultdict(set)
    for edge in edges:
        if edge.get("kind") == "clock":
            continue
        source, target = edge["source"], edge["target"]
        remaining.setdefault(source, 0)
        if target not in successors[source]:
            successors[source].add(target)
            remaining[target] += 1
    ready = [node for node, count in remaining.items() if not count]
    visited = 0
    while ready:
        source = ready.pop()
        visited += 1
        for target in successors[source]:
            remaining[target] -= 1
            if remaining[target] == 0:
                ready.append(target)
    return visited < len(remaining)


def _task(spec, figure):
    """Use the view's semantics/geometry, not source model or title branding."""
    nodes, edges = _visible_graph(spec, figure)
    layout = figure.get("structure_layout") if isinstance(figure.get("structure_layout"), dict) else {}
    role = _text(figure.get("view_role")).casefold()
    mode = " ".join(_text(layout.get(key)) for key in ("mode", "type", "view_type", "diagram_role")).casefold()
    mode += " " + _text(figure.get("view_type")).casefold()
    category = _text(spec.get("category"))
    if not nodes:
        return {"family": "unknown", "view_role": role, "mode": mode.strip(), "weights": {},
                "visible_nodes": 0, "edge_kinds": {}, "package_allowed": False, "expression_traits": []}
    package_allowed = role in {"package", "packaging", "package-overview"} or bool(re.search(r"package|packaging|封装", mode))
    data = [edge for edge in edges if edge.get("kind", "data") == "data"]
    control = [edge for edge in edges if edge.get("kind") in {"control", "feedback", "clock"}]
    incoming, outgoing = defaultdict(set), defaultdict(set)
    for edge in data:
        if edge["source"] != edge["target"]:
            incoming[edge["target"]].add(edge["source"])
            outgoing[edge["source"]].add(edge["target"])
    by_id = {node["id"]: node for node in nodes}
    algorithm = figure.get("algorithm_flow_plan")
    if isinstance(algorithm, dict):
        objects = [item for item in _items(algorithm.get("objects")) if isinstance(item, dict) and item.get("source_node_id") in by_id]
        roles = {item.get("role") for item in objects}
        weights = {"flow": 5} if edges else {}
        if roles & {"operator", "reduction", "decision"}:
            weights["operator"] = 9
        if "tensor" in roles:
            weights["tensor"] = 14
        if any(len(sources) >= 2 for sources in incoming.values()):
            weights.update(dual_input=10, branch_merge=7)
        elif any(len(targets) >= 2 for targets in outgoing.values()):
            weights["branch_merge"] = 7
        if _has_cycle(edges):
            weights.update({"recurrence": 16, "return": 7})
        if "reduction" in roles:
            weights["reduction"] = 10
        if any(item.get("residency") for item in objects):
            weights.update(reuse=15, memory=5)
        expression_traits = set(weights) - {"recurrence", "memory"}
        if "state" in roles and "recurrence" in weights:
            expression_traits.add("recurrence")
        return {"family": "algorithm", "view_role": role, "mode": algorithm.get("composition", {}).get("grammar", "algorithm"),
                "weights": weights, "visible_nodes": len(nodes),
                "edge_kinds": dict(Counter(edge.get("kind", "data") for edge in edges)), "package_allowed": False,
                "expression_traits": sorted(expression_traits)}
    compute = {node["id"] for node in nodes if node.get("kind") == "compute"}
    memory = {node["id"] for node in nodes if node.get("kind") == "memory"}
    dual = any(len(incoming[nid]) >= 2 for nid in compute)
    branch = any(len(targets) >= 2 for targets in outgoing.values()) and any(len(sources) >= 2 for sources in incoming.values())
    returning = any(edge["source"] in outgoing.get(edge["target"], set()) for edge in data)
    labels = "\n".join(_text(node.get("label")) for node in nodes)
    cache_nodes = sum(bool(re.search(r"\bL[123]\b|cache|DRAM|HBM|DDR|memory controller|缓存|内存", _text(node.get("label")), re.I)) for node in nodes)
    memory_path = cache_nodes >= 2 or any(edge["source"] in memory and edge["target"] in memory for edge in data)
    groups = _visible_groups(spec, nodes, layout)
    parents = {group.get("id"): group.get("parent") for group in groups}
    nested = any(parent in parents for parent in parents.values()) or any(node.get("children") for node in nodes) or any(container.get("render_boundary") is not False for container in _items(layout.get("containers")) if isinstance(container, dict))
    evidenced_repetition = _visible_repetition(nodes, figure, layout)
    projected = figure.get("abstract") or isinstance(figure.get("macro_nodes"), list) or isinstance(layout.get("macro_nodes"), list) or bool(figure.get("render_brief"))
    repetition = evidenced_repetition or (not projected and bool(layout.get("repeat_families")))
    scope_text = "\n".join(_text(group.get("label")) for group in groups)
    lane_roles = {_text(lane.get("role")) for lane in _items(layout.get("role_lanes")) if isinstance(lane, dict)}
    has_private = repetition or bool(re.search(r"private|私有", scope_text, re.I))
    has_shared = "shared" in lane_roles or bool(re.search(r"shared|共享", scope_text, re.I))
    private_shared = has_private and has_shared
    shared_band = has_shared or bool(lane_roles & {"shared", "memory"}) or any(len(incoming[nid] | outgoing[nid]) >= 3 for nid in memory)
    zoom = bool(figure.get("expand_ids") or layout.get("expand_ids") or layout.get("insets")) or bool(re.search(r"zoom|expansion|representative-detail", mode))
    owner_of = {nid: _text(node.get("original_group", node.get("group"))) for nid, node in by_id.items()}
    cross_owner = sum(owner_of.get(edge["source"]) != owner_of.get(edge["target"]) for edge in edges)
    owner_count = len(set(owner_of.values()) - {""})
    swimlane = "swimlane" in mode or (bool(data and control) and owner_count >= 3 and cross_owner >= 2 and bool(spec.get("steps")))
    temporal = category == "timing" or role in {"timing", "sequence", "interaction"} or bool(re.search(r"timing|sequence", mode))
    pipeline = category == "pipeline" or "pipeline" in mode
    topology = bool(re.search(r"mesh|network-topology|noc-topology|interconnect-topology", mode)) or (
        sum(node.get("kind") == "io" for node in nodes) >= 3 and bool(re.search(r"router|\bNoC\b|路由器", labels, re.I)))
    comparison = bool(figure.get("comparison")) or bool(re.search(r"comparison|compare|before-after", mode))

    weights = {}
    if package_allowed:
        family, weights = "package", {"package": 15, "hierarchy": 5, "memory": 6}
    elif temporal:
        family, weights = "timing", {"timing": 15, "swimlane": 8, "pipeline": 4}
    elif pipeline:
        family, weights = "pipeline", {"pipeline": 12, "timing": 4, "flow": 4}
    elif role == "control":
        family, weights = "control", {"control": 12, "control_data": 7, "hierarchy": 3}
    elif topology:
        family, weights = "topology", {"topology": 14, "repetition": 4, "shared_band": 3}
    elif role == "resource-organization" or (category == "architecture" and role not in {"datapath", "support"} and figure.get("kind") != "detail" and "private" not in mode):
        family, weights = "organization", {"organization": 7, "hierarchy": 5}
    elif category == "memory" or "memory" in mode or (memory_path and not dual and (cache_nodes >= 2 or not compute)):
        family, weights = "memory", {"memory": 13, "flow": 4, "return": 3}
    elif category in {"algorithm", "fsm"}:
        family, weights = "behavior", {"flow": 6, "control_data": 3, "return": 2}
    else:
        family, weights = "flow", {"flow": 6}
    if repetition:
        weights["repetition"] = 10
    if nested and family == "organization":
        weights["hierarchy"] = 7
    if shared_band and family == "organization":
        weights["shared_band"] = 4
    if private_shared and family == "organization":
        weights["private_shared"] = 9
    if zoom:
        weights["zoom"] = 12
    if family in {"flow", "memory", "pipeline"}:
        if dual:
            weights["dual_input"] = 15
        if branch:
            weights["branch_merge"] = 6
        if returning or any(edge.get("kind") == "feedback" for edge in edges):
            weights["return"] = max(weights.get("return", 0), 5)
        if memory_path:
            weights["memory"] = max(weights.get("memory", 0), 10)
        if any(re.search(r"\b\d+\s+banks\b|\d+\s*个?\s*bank", _text(node.get("detail")), re.I) for node in nodes):
            weights["banked"] = 7
    if data and control:
        weights["control_data"] = max(weights.get("control_data", 0), 8)
    if swimlane:
        weights["swimlane"] = 14
        weights["pipeline"] = max(weights.get("pipeline", 0), 5)
    if comparison:
        weights["comparison"] = 9
    if any(len(incoming[nid]) >= 3 and re.search(r"reduce|accumulat|adder|sum|归约|累加", _text(by_id[nid].get("label")), re.I) for nid in compute):
        weights["reduction"] = 12
    # Family affinities help retrieve references, but are not evidence that a
    # motif exists (a memory view need not have a return; a topology need not
    # repeat). Only witnessed mechanisms may influence a generated prompt.
    expression_traits = {trait for trait, present in {
        "organization": family == "organization" and len(nodes) > 1,
        "hierarchy": nested, "repetition": evidenced_repetition,
        "private_shared": has_shared and bool(re.search(r"private|私有", scope_text, re.I)), "shared_band": has_shared,
        "zoom": bool(layout.get("insets")), "flow": bool(data),
        "dual_input": dual, "branch_merge": branch,
        "return": returning or any(edge.get("kind") == "feedback" for edge in edges),
        "memory": memory_path, "control": bool(control), "control_data": bool(data and control),
        "swimlane": "swimlane" in mode, "pipeline": pipeline, "timing": temporal,
        "topology": topology, "comparison": comparison,
        "reduction": "reduction" in weights,
    }.items() if present}
    return {"family": family, "view_role": role, "mode": mode.strip(), "weights": weights,
            "visible_nodes": len(nodes), "edge_kinds": dict(Counter(edge.get("kind", "data") for edge in edges)),
            "package_allowed": package_allowed, "expression_traits": sorted(expression_traits)}


def _quality(record):
    verified = record.get("verification")
    bonus = 2 if verified else 0
    if isinstance(verified, dict) and verified.get("individual_png_view_image_checked"):
        bonus += 1
    if all(type(record.get(key)) is int and record[key] >= minimum for key, minimum in (("width", 500), ("height", 150))):
        bonus += 1
    return bonus


def explain(spec, figure, style="paper"):
    """Return at most two paths plus auditable metadata matches and use scope."""
    spec = spec if isinstance(spec, dict) else {}
    figure = figure if isinstance(figure, dict) else {}
    task = _task(spec, figure)
    style_id = style.get("id", "paper") if isinstance(style, dict) else style
    ranked = []
    for record in _records():
        traits = record["traits"]
        if "package" in traits and not task["package_allowed"]:
            continue
        focus_text = " ".join(record["focus"]).casefold()
        if task["family"] != "behavior" and any(word in focus_text for word in ("framework", "file-vs-process", "intent-to-hardware")):
            continue
        matches = sorted(set(task["weights"]) & traits)
        relevance = sum(task["weights"][trait] for trait in matches)
        if relevance < 5:
            continue
        genre = GENRES[task["family"]].get(record["genre"], -6)
        score = relevance + genre + _quality(record)
        if "comparison" in traits and "comparison" not in task["weights"]:
            score -= 2  # The mechanism may fit; paired comparison is secondary.
        if style_id == "monochrome" and ("monochrome" in focus_text or "黑白" in " ".join(record["features"])):
            score += 6
        # Style only controls a modest affinity. The returned grammar scope
        # always leaves palette authority with the target, including blueprint.
        if style_id in {"paper", "blueprint", "signal"} and any(word in " ".join(record["features"]) for word in ("低饱和", "浅色", "灰白", "浅粉", "浅黄")):
            score += 1
        if score > 0:
            ranked.append((score, record, matches))
    ranked.sort(key=lambda candidate: (-candidate[0], candidate[1]["path"]))
    selected, covered = [], set()
    while ranked and len(selected) < 2:
        # Prefer a second reference that contributes another relevant grammar,
        # without replacing a strongly matching example with an unrelated one.
        ranked.sort(key=lambda item: (-(item[0] + .25 * sum(task["weights"][trait] for trait in item[2] if trait not in covered)), item[1]["path"]))
        score, record, matches = ranked.pop(0)
        selected.append({"path": record["path"], "score": score,
                         "reason": "匹配：" + "、".join(TRAIT_NAMES[trait] for trait in matches),
                         "matched_traits": matches, "metadata_focus": record["focus"],
                         "metadata_features": record["features"], "metadata_diagram_type": record.get("diagram_type", ""),
                         "source_url": record["source_url"],
                         "manifests": record["manifests"], "use_scope": REFERENCE_SCOPE})
        covered.update(matches)
    return {"task": task, "selected": selected, "use_scope": REFERENCE_SCOPE,
            "palette_source": "target_style", "selection_is_visual_certification": False}


def expression_rules(selection) -> list[str]:
    """Translate confident, visible reference matches into bounded polish.

    Retrieval affinities alone cannot authorize a motif. The selected metadata,
    current display evidence and current task weight must all agree; otherwise
    the ordinary compiler grammar remains sufficient.
    """
    if not isinstance(selection, dict):
        return []
    task = selection.get("task", {})
    if not isinstance(task, dict) or not task.get("visible_nodes"):
        return []
    weights = task.get("weights", {})
    evidence = set(_items(task.get("expression_traits")))
    candidates = {}
    for item in _items(selection.get("selected")):
        if not isinstance(item, dict) or not isinstance(item.get("score"), (int, float)) or item["score"] < 5:
            continue
        provenance = _reference_traits({"focus": item.get("metadata_focus"), "features": item.get("metadata_features"),
                                        "diagram_type": item.get("metadata_diagram_type")})
        for trait in set(_items(item.get("matched_traits"))) & provenance & evidence & _EXPRESSION_RULES.keys():
            weight = weights.get(trait, 0)
            if isinstance(weight, (int, float)) and weight >= 5:
                candidates[trait] = max(candidates.get(trait, (0, 0)), (weight, item["score"]))
    output, families = [], set()
    for trait in sorted(candidates, key=lambda name: (-candidates[name][0], -candidates[name][1], name)):
        family = "ownership" if trait in {"organization", "hierarchy", "private_shared", "shared_band"} else "junction" if trait in {"dual_input", "branch_merge"} else trait
        if family in families:
            continue
        families.add(family)
        output.append(_EXPRESSION_RULES[trait])
        if len(output) == 2:
            break
    return output


def select(spec, figure, style="paper") -> list[str]:
    """Return up to two verified relative raster paths; never call an API."""
    return [item["path"] for item in explain(spec, figure, style)["selected"] if _safe_raster(item["path"])]
