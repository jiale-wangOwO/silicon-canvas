"""Composition guidance distilled from the locally reviewed engineering figures.

These are editorial heuristics, not a pixel renderer or a visual quality score.
They complement the technical specification without changing its graph.
"""

PLANNING_BRIEF = """PLAN THE FIGURE, not just its inventory.
Infer the single question the figure should answer from the user's intent. A broad GPU/SoC request defaults to a system overview with one representative detail when useful. The user need not choose a diagram type or supply layout instructions.
For open-ended requests, draft a modest number of meaningful functional units at a consistent abstraction level. For a detailed supplied design, preserve the specified units and edges; use panels rather than deleting details to meet a block budget.
Write a concrete layout using actual node/group IDs: identify the dominant view and focal subsystem; assign groups to top/center/bottom or left/right zones; specify reading order; reserve corridors for forward, return, and control paths. Avoid generic phrases such as 'clean professional layout' as the whole plan.
Choose an overview with one detail inset only when the content benefits from it. Name the group/node that is expanded and state that the inset is a magnified view of the same hardware. A magnification leader has no arrowhead and is not a technical edge. Do not turn a workflow into a hardware floorplan or imply time from spatial order.
For large repeated structures, use a representative slice only when equivalence and multiplicity are established by the target specification. Preserve distinct instances with different edges; never invent a repeat count or silently collapse different modules.
When the user explicitly says peer instances have the same resources, represent one populated template group and the peer instance nodes. Preserve the equivalence in each peer's detail as "Same resources as <template group ID>" with verbatim evidence of the equivalence. Keep every distinct supplied connection; this shorthand describes resources, not implicit wiring. A representative detail and its overview refer to the same hardware.
If panels are necessary, explicitly assign IDs and edge ownership to them. Each technical edge appears in one designated view; shared context may repeat as the same logical object. Preserve cross-panel connectivity with matching endpoint labels from the existing text manifest. Do not introduce fictional interface nodes or add unapproved text to solve routing.
Allocate useful canvas area to the main subject; give secondary controls less space without hiding their connections. Use concise noun labels, put optional prose in summary, and keep all required equations, conditions and numbers. Layout is instructions, not image text. Do not add colors/fonts here: the selected style contract owns those.
"""

# Presentation patterns, not vendor hardware templates. The pipeline, FSM and
# timing patterns come from the existing catalog, not from ISCA figure claims.
PATTERNS = {
    "architecture": "System overview: align peer subsystems, place shared resources in a common band and external interfaces on the perimeter. Favor containment over decorative arrows. Use one explicitly linked detail inset only for a relevant subsystem (Eyeriss/FlexMiner overview-to-detail pattern).",
    "microarchitecture": "Engine detail: organize storage, scheduling, compute and outputs around the actual primary path; draw only the roles present. Align equivalent lanes/stages and reserve a separate control corridor (SCNN/Plasticine detail pattern).",
    "dataflow": "Data movement: separate sources, buffers, computation, accumulation and sinks when present. Keep returning payloads solid. For distinct reuse mechanisms, aligned small multiples may be clearer than overlaid arrows; use the same object identities across views (Eyeriss/SCNN pattern).",
    "memory": "Memory view: choose a layered ownership hierarchy or an explicit network topology. Align private/shared levels for a hierarchy; align routers and edge endpoints for a topology. Never turn an access relationship into a physical link (GPU proxy/Plasticine pattern).",
    "pipeline": "Pipeline: use stage columns for spatial organization OR operation lanes on a time axis for scheduling. Put reverse ready/backpressure on an outer corridor. Do not mix spatial order and cycle timing.",
    "algorithm": "Behavior: place input, transformation/decision and output in dependency order. Put branch predicates beside their arrows and route loops outside. For contrasting concepts, use aligned views with identical node styling; do not force hardware containers onto procedural steps.",
    "fsm": "State machine: arrange the normal path prominently and route recovery/error arcs outside it. Leave generous space for exact predicates. Preserve self-loops, reset semantics and transition priorities; use state shapes, not processing-stage boxes.",
    "timing": "Timing/interaction: use one shared time axis and fixed signal or participant lanes. Give each event an unambiguous lane and time position. Keep exact cycles aligned; missing timing stays explicitly illustrative.",
}


def request_guidance(category):
    patterns = PATTERNS if category == "auto" else {category: PATTERNS[category]}
    return {"planning_brief": PLANNING_BRIEF, "view_patterns": patterns}


def render_guidance(spec, maximum):
    """Emit a bounded composition contract and objective crowding warnings."""
    nodes, edges = spec["nodes"], spec["edges"]
    incident = {node["id"]: 0 for node in nodes}
    for edge in edges:
        incident[edge["source"]] += 1
        if edge["target"] != edge["source"]:
            incident[edge["target"]] += 1
    hubs = [node for node in nodes if incident[node["id"]] >= 6]
    crowded = len(nodes) > maximum or len(edges) > maximum * 2
    lines = [
        "FIGURE PLAN — apply to the exact target graph below:",
        PATTERNS[spec["category"]],
        "Prioritize technical correctness, then legibility at document size, then visual consistency. Use the space for the subject, not an oversized title or ornamental empty zones.",
        "The stated block budget is per panel. A multi-panel canvas must still keep labels readable; do not solve crowding by making many tiny panels. Preserve explicit layout constraints and every required fact.",
        "An overview/detail inset shows the same hardware at another scale. Its non-directional magnification leader is not a data/control link. Never duplicate a module as additional hardware.",
        "In multiple views, assign every edge to one designated view and retain recognizable endpoint labels. Do not print internal IDs or invent interface nodes. Visual repetition is context, not extra hardware.",
    ]
    warnings = []
    if hubs:
        ids = ", ".join(node["id"] for node in hubs)
        lines.append(f"Routing hotspots: {ids}. Distribute their incident links over aligned ports/sides and reserve clear lanes. Keep each direction and label; never replace distinct connections with an unlabeled common bus.")
        warnings.append("连线集中在 " + "、".join(node["label"] for node in hubs) + "，已要求预留端口和走线通道；成图需重点核对端点与方向。")
    if crowded:
        lines.append("This target exceeds the selected panel budget. Use the supplied groups or functional boundaries to plan a small number of explicit views before routing. Do not silently remove nodes/edges or shrink text to force one panel.")
    return "\n".join(lines), warnings
