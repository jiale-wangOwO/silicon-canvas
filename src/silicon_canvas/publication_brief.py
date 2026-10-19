"""Compile a publication design brief, keeping geometry in the supplied guide.

This compiler is deliberately independent of the semantic model and image
provider.  It consumes the normalized source facts and the editorial projection;
it never asks a renderer to interpret source IDs, coordinates or routing arrays.
"""

from __future__ import annotations

import json
import math
import re

from .publication_render import required_detail


POLICY_VERSION = "CPS6"


def _quote(value):
    return json.dumps(str(value), ensure_ascii=False)


def _number(value, default):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) and number > 0 else default


def _faithful_finisher(figure):
    return (figure.get("requires_layout_guide") is not False
            and (figure.get("layout_strategy") == "publication-candidates"
                 or figure.get("structure_layout", {}).get("type") == "publication"))


def product_concept(figure):
    contract = figure.get("design_contract", {})
    return contract.get("scene_id") == "concept" and contract.get("grammar") == "product-concept"


def connection_contract(figure):
    """Verification metadata for visible strokes, never source-graph counts.

    A reverse pair projected onto one two-headed connector is one visible
    connection and two arrowheads.  This is a finisher checklist, not artwork.
    """
    if figure.get("requires_layout_guide") is False:
        return {}
    scene = figure.get("layout_scene")
    if not isinstance(scene, dict) or not isinstance(scene.get("routes"), list):
        return {}
    routes = scene["routes"]
    double = sum(bool(route.get("bidirectional")) for route in routes)
    return {"visible_connections": len(routes), "single_headed_connections": len(routes) - double,
            "double_headed_connections": double, "arrowheads": len(routes) + double,
            "counts_source": "reviewed layout_scene.routes, not canonical source edges",
            "print_in_artwork": False}


def input_roles(figure):
    """Describe the actual image inputs; references are opt-in, never automatic.

    An explicit ``imagegen_style_reference`` string or {path: ...} adds one
    style-only image.  Existing research ``reference_images`` remain upstream
    knowledge and do not implicitly become generation inputs.
    """
    if figure.get("requires_layout_guide") is False:
        return []
    instruction = (
        "Use the target guide for the visible inventory, ownership, relative "
        "organization and directed endpoints. Improve typography, spacing "
        "and clean bends without changing technical facts."
    )
    if _faithful_finisher(figure):
        instruction = (
            "This is the reviewed target plate. Make a clean faithful redraw: "
            "keep the module boxes, ownership, spacing, text placements, all "
            "connection paths and their source/target boundary attachments. "
            "Preserve every arrowhead at its existing endpoint. Improve only "
            "crisp typography, line weight and uniform flat fills; do not "
            "re-layout, reroute, duplicate or reinterpret the graph."
        )
    if product_concept(figure):
        instruction = (
            "This is the compiled whole-product composition guide. Preserve its "
            "functional regions, logical ownership, context objects, names and "
            "all visible directed interface endpoints. Render a polished product "
            "concept illustration for a pitch deck: a clear central chip/system "
            "silhouette, understated dimensional finish on its outer enclosure, "
            "and flat readable functional tiles. Use a contemporary vector-like "
            "product graphic, not a beveled glass card or dashboard. No metallic "
            "rims, glossy surfaces, gradients or shadows on internal tiles. "
            "The silhouette is illustrative; "
            "it is not a die photograph, physical floorplan or extra hardware. "
            "Do not expand queues, registers or internal microarchitecture."
        )
    roles = [{
        "image_index": 1,
        "role": "target_structure",
        "source": "layout-guide",
        "instruction": instruction,
        "technical_revision": (
            "If a generated image has a technical error, regenerate from the "
            "source specification and a clean corrected guide; do not continue "
            "a chain of local edits to the failed bitmap."
        ),
    }]
    if _faithful_finisher(figure):
        roles[0]["connection_contract"] = connection_contract(figure)
    reference = figure.get("imagegen_style_reference")
    path = reference.get("path") if isinstance(reference, dict) else reference
    if isinstance(path, str) and path.strip():
        roles.append({
            "image_index": 2,
            "role": "style_reference",
            "source": path,
            "instruction": (
                "Use only the typography, restrained line weight and visual "
                "hierarchy of this reference. The target preset owns the palette. "
                "Do not copy its topology, module names, counts, parameters or branding."
            ),
        })
    return roles


def _palette(style_prompt, style="paper"):
    # Extract preset facts, not the old prompt's uncalibrated pixel-font advice.
    match = re.search(r"Palette:\s*([^\n]+)", style_prompt or "")
    values = {}
    if match:
        values = dict(re.findall(r"([a-zA-Z_]+)\s+(#[0-9a-fA-F]{6})", match.group(1)))
    defaults = {"background": "#FFFFFF", "ink": "#263238", "primary": "#EDF2F5", "secondary": "#E8EEE8"}
    if style == "paper":
        defaults.update(ink="#17324D", primary="#DCEAFF", secondary="#FFF0BE", control="#EEE5FF", outline="#6E8BAB", container="#BFCFE0")
    return {name: values.get(name, value) for name, value in defaults.items()}


def _inventory(figure, spec):
    nodes = {node["id"]: node for node in spec.get("nodes", [])}
    layout = figure.get("structure_layout", {})
    if layout.get("type") == "publication" and "macro_nodes" in layout:
        # The actual plate owns the display inventory. A representative inset
        # may replace the planner's initial in-place expansion.
        edges = figure.get("macro_edges", []) if figure.get("abstract") else [spec["edges"][index] for index in figure.get("edge_indices", range(len(spec.get("edges", []))))]
        return list(layout["macro_nodes"]), list(edges), nodes
    if figure.get("abstract"):
        visible = figure.get("macro_nodes")
        if visible is None:
            visible = figure.get("structure_layout", {}).get("macro_nodes", [])
        return list(visible), list(figure.get("macro_edges", [])), nodes
    ids = figure.get("node_ids", list(nodes))
    indices = figure.get("edge_indices", range(len(spec.get("edges", []))))
    return [nodes[nid] for nid in ids], [spec["edges"][index] for index in indices], nodes


def _children(node, sources):
    children = node.get("children")
    if children is None:
        children = node.get("template_slots")
    if children is None:
        children = [sources[mid] for mid in node.get("members", []) if mid in sources and mid != node.get("id")]
    result = []
    for child in children:
        if isinstance(child, str):
            child = sources.get(child, {"label": child})
        if isinstance(child, dict) and child.get("label"):
            result.append(child)
    return result


def _scope_labels(figure, visible, spec):
    groups = {group["id"]: group for group in spec.get("groups", [])}
    present = set()
    for node in visible:
        gid = node.get("group") or node.get("original_group") or node.get("source_owner")
        if node.get("id") in groups:
            present.add(node["id"])
        visited = set()
        while gid in groups and gid not in visited:
            present.add(gid)
            visited.add(gid)
            gid = groups[gid].get("parent")
    return groups, [group for group in spec.get("groups", []) if group["id"] in present]


def _owner(node, sources, groups):
    gid = node.get("group") or node.get("original_group") or node.get("source_owner")
    if not gid and node.get("id") in groups:
        gid = groups[node["id"]].get("parent")
    if not gid and node.get("id") in sources:
        gid = sources[node["id"]].get("group")
    owner = groups.get(gid)
    # A label-identical singleton scope is a real logical owner, but printing
    # another identically named frame obscures the physical organization. Its
    # parent's name accurately describes the transitive source containment.
    if owner and owner["label"] == node["label"]:
        owner = groups.get(owner.get("parent"))
    return owner


def _endpoint(nid, display, sources, groups):
    if nid in display:
        return _quote(display[nid]["label"])
    if nid in sources:
        return _quote(sources[nid]["label"])
    if nid in groups:
        return _quote(groups[nid]["label"])
    raise ValueError("A publication relationship must have a named source object: " + str(nid))


def _detail(node, sources):
    detail = node.get("detail", "")
    if not detail and node.get("id") in sources:
        detail = sources[node["id"]].get("detail", "")
    return detail if isinstance(detail, str) else ""


def _has_exact_notation(text):
    return bool(re.search(r"\d|[=<>≤≥≠∑×÷]|\[[^\]]+\]|\b(?:mod|cycle|cycles|bits?|bytes?)\b", text, re.I))


def _mandatory_edge_text(text, required_labels):
    return (_has_exact_notation(text)
            or bool(re.search(r"\b(?:if|when|unless|otherwise|until)\b|若|当|否则|条件", text, re.I))
            or any(str(literal) and str(literal) in text for literal in (required_labels or [])))


def _edge_members(edge, spec):
    if "members" in edge:
        return set(edge.get("members", []))
    return {index for index, source_edge in enumerate(spec.get("edges", [])) if source_edge == edge}


def _planned_for_edge(text, edge, planned, spec):
    members = _edge_members(edge, spec)
    for label in planned:
        if label.get("text") != text:
            continue
        indices = set(label.get("source_edge_indices", []))
        if not indices or not members or members & indices:
            return True
    return False


def _text_authority(figure, spec, display, sources, groups, required_labels):
    if figure.get("requires_layout_guide") is False:
        return None, []
    layout = figure.get("label_layout")
    if not isinstance(layout, dict) or not any(key in layout for key in ("labels", "deferred_labels")):
        return None, []
    planned = [label for label in layout.get("labels", []) if isinstance(label, dict) and isinstance(label.get("text"), str)]
    deferred = [label for label in layout.get("deferred_labels", []) if isinstance(label, dict) and isinstance(label.get("text"), str)]
    for label in deferred:
        must_print = any(literal and literal in label["text"] for literal in required_labels)
        if must_print or (not product_concept(figure) and _mandatory_edge_text(label["text"], required_labels)):
            raise ValueError("Required edge text cannot be deferred; revise the clean guide: " + label["text"])
    lines = [
        "Edge text authority: Print only the planned edge text listed here, in its assigned open region in Image 1, plus any matching mandatory literal or numerical/conditional expression required below. Preserve the guide's association and placement; never add another label simply because the semantic relationship list contains its meaning.",
        "Planned edge text to print (this manifest is an instruction, not extra artwork):",
    ]
    mapping = figure.get("projection", {}).get("source_node_to_macro", {})
    if not planned:
        lines.append("None. Optional edge meanings belong only in the companion caption.")
    for label in planned:
        endpoints = []
        for index in label.get("source_edge_indices", []):
            if not isinstance(index, int) or not 0 <= index < len(spec.get("edges", [])):
                continue
            edge = spec["edges"][index]
            pair = (_endpoint(mapping.get(edge["source"], edge["source"]), display, sources, groups)
                    + " -> " + _endpoint(mapping.get(edge["target"], edge["target"]), display, sources, groups))
            if pair not in endpoints:
                endpoints.append(pair)
        lines.append(_quote(label["text"]) + (" — for " + "; ".join(endpoints) if endpoints else " — at its placement in Image 1") + ".")
    lines.append("Relationship meanings below are the full technical and caption contract, not a request to squeeze every phrase into the bitmap. Unplanned optional edge prose remains outside the image.")
    return planned, lines


def compile_figure(figure, spec, settings, style_prompt, required_labels):
    """Return one concise generation brief with an exact semantic manifest.

    Rich technical facts are never truncated to satisfy a cosmetic word limit.
    Oversize source inventories should be split by the editorial planner rather
    than silently discarded here.  Neither function mutates any source object.
    """
    contract = figure.get("design_contract") or {}
    visible, edges, sources = _inventory(figure, spec)
    display = {node["id"]: node for node in visible}
    groups, scopes = _scope_labels(figure, visible, spec)
    width_mm = _number(contract.get("target_width_mm"), 160)
    body_pt = _number(contract.get("body_pt"), 9)
    signal_pt = _number(contract.get("signal_pt"), 8.5)
    palette = _palette(style_prompt, settings.get("style", "paper"))
    roles = input_roles(figure)
    faithful = _faithful_finisher(figure)
    design = figure.get("diagram_design", {})
    question = design.get("reading_question") or contract.get("question") or figure.get("summary") or "How are the supplied resources organized and how do their stated relationships operate?"
    scene_id = contract.get("scene_id", "")
    concept = product_concept(figure)
    lines = [
        "Use case: productivity-visual. Create one polished whole-chip product concept illustration for a BP or commercial presentation using Image Gen." if concept else "Use case: infographic-diagram. Create one finished raster engineering figure for an architecture document using Image Gen.",
        "Primary request: Make the structure understandable at normal document size. The reader should be able to answer: " + str(question),
    ]
    if roles:
        lines.append("Input images:")
    else:
        lines.append("Input mode: Text-only semantic contract without a reviewed layout plate. The layout is unreviewed; check the actual generated bitmap before accepting its structure or appearance.")
    for role in roles:
        lines.append(f"Image {role['image_index']}: {role['role'].replace('_', ' ')}. {role['instruction']}")
    if faithful:
        lines.extend([
            "Finishing task: The plate already supplies the composition. Preserve its exact module arrangement, box dimensions, ownership boundaries, spacing and planned label positions. Redraw the existing paths and arrowheads faithfully with crisp strokes and consistent typography. Add no direct shortcut, duplicate branch, floating stub, alternate endpoint or source arrowhead. Do not move an inlet from a group boundary onto an internal child, or reinterpret a group projection as new internal wiring.",
            "Layout changes belong to the upstream design stage. In this image, improve visual finish only: clean text, neutral line weights, solid flat fills and a pure background. Keep the plate's geometry, route corridors and directed connections intact.",
        ])
        if concept:
            lines[-1] = "Visual finishing: Keep the guide's functional arrangement and directed connections. Use premium presentation typography, flat functional tiles and a coherent central product silhouette. At most a narrow understated side edge or very subtle outer shadow may distinguish the whole product; do not use a metallic bezel, glossy bevel, glass panel, UI dashboard cards, internal tile shadows or gradient fills. Preserve the silhouette's logical member boundary without presenting tile placement as a physical die floorplan. No wafer photograph, neon circuitry or decorative extra ports."
        counts = connection_contract(figure)
        if counts:
            lines.append(f"Verification metadata — never print these numbers in the artwork: {counts['visible_connections']} visible connections; {counts['single_headed_connections']} one-headed and {counts['double_headed_connections']} two-headed connectors; exactly {counts['arrowheads']} arrowheads total. Count the plate's visible routes, not the underlying source relationships.")
    elif roles:
        lines.extend([
            "Composition: Follow the guide's hierarchy and reading direction. Align equivalent branches and instances. Fit each symbol to its role and label, rather than uniform cards. Keep interfaces close to their resources, shared services distinct from private resources, and whitespace useful for labels and paths.",
            "The guide is a structure reference, not a pixel tracing exercise. Refine symbol dimensions, gutters and connector bends while preserving ownership and directed endpoints. The arrangement is logical organization, not a measured silicon floorplan or an implied cycle schedule.",
        ])
    else:
        lines.extend([
            "Unreviewed composition: Organize the supplied hierarchy and dependencies with one clear reading direction. Align equivalent branches and instances, keep private and shared resources distinct, and fit symbols to their real roles. Create no connections from spatial adjacency. The arrangement is logical organization, not a measured silicon floorplan or an implied cycle schedule.",
        ])
    document_scale = f"Document scale: Intended figure width {width_mm:g} mm; module names {body_pt:g} pt and signal labels {signal_pt:g} pt at that width. Choose a canvas that remains readable after insertion. Wrap a long exact name before reducing its size. Use one neutral sans-serif family, normal or medium weight, and subordinate scope names."
    if figure.get("layout_strategy") == "legacy-technical-annex":
        document_scale = f"Legacy structure sketch: This plate has not passed the physical typography contract at {width_mm:g} mm width. Its current geometry is technical context, not a publication-ready composition. Recompose and verify the actual document-size result before document use; do not claim readable type from this plate."
    style_line = f"Style: Flat drawing on {palette['background']}; text and neutral outlines {palette['ink']}, compute fill {palette['primary']}, storage fill {palette['secondary']}; control and interfaces mostly unfilled. Color is sparse and meaningful. Use narrow crisp strokes, small arrowheads and unfilled ownership boundaries. No gradients, shadows, texture, decorative icons, vendor branding, heavy frames or empty padded cards."
    if settings.get("style", "paper") == "paper":
        style_line = f"Style: Clear white-paper technical drawing on {palette['background']}; deep blue-gray text {palette['ink']}, compute fill {palette['primary']}, storage fill {palette['secondary']}, sparse control fill {palette['control']}; interfaces stay white. Repeat these role colors consistently, never one hue per module. Use restrained outlines {palette['outline']} and very light unfilled ownership boundaries {palette['container']}. Containers and same-hardware details have white bodies with light headings, never black or charcoal title bars. Establish hierarchy with aligned peer arrays, shared-resource bands and concise medium-weight names; secondary labels are regular weight. Keep the technical information visible without dashboard cards, heavy all-bold text or a washed-out gray-green palette. No gradients, shadows, texture, decorative icons, vendor branding or heavy frames."
    if concept:
        style_line = f"Style: Professional commercial product graphic on {palette['background']}, with typography in {palette['ink']}. Use a dominant central product enclosure and concise functional region tiles, contextual I/O or external memory around it, and few source-backed interface paths. Use refined geometry and generous presentation whitespace. The visible inventory is a functional concept, not a manufacturing layout. No fabricated branding, performance numbers, application icons, pins or internal wiring."
    elif scene_id == "flow":
        style_line += " Make the supplied data journey visually dominant through continuous paths and a single reading direction; secondary controls belong in their separate view. Do not number dependency edges as clock cycles or create unsupplied processing stages."
    lines.extend([
        document_scale,
        style_line,
        "Connections: Follow each planned stroke encoding: solid data or relation lines; dashed control, clock or recovery lines. Control feedback is also dashed. A feedback relationship explicitly carrying return data/payload is solid; returning direction by itself does not establish payload semantics. Preserve every source kind and its meaning. One-way relations have only a target arrowhead; two opposite heads require a supplied reverse pair. Keep paths traceable without crossing labels or unrelated modules. Crossings without junctions are not connections. Never create a bus, mux, operator or port to simplify routing.",
    ])
    if design.get("render_instructions") and not concept:
        lines.append("Selected visual grammar: " + " ".join(design["render_instructions"]))
    claim = contract.get("claim")
    scope = contract.get("scope")
    if isinstance(claim, str) and claim.strip():
        lines.append("Emphasis: " + claim)
    if isinstance(scope, str) and scope.strip():
        lines.append("View scope: " + scope)
    grammar = contract.get("grammar")
    if grammar:
        lines.append(("Use the plate's " if roles else "Suggested unreviewed organization: ") + str(grammar).replace("_", " ").replace("-", " ") + " composition. This describes the visual organization, not extra circuitry or text to print.")
    if figure.get("abstract"):
        lines.append("Projection: Group symbols summarize original members; macro arrows summarize only their mapped source relationships. Neither creates a physical bus, port, broadcast mechanism or additional hardware. Unshown wiring belongs to the detail view. Contents labels imply no execution order or internal connection.")
    else:
        lines.append("Scope: This is an exact selected view. Each listed module and directed relationship must be represented. Context resources keep their original owner. The companion caption carries long explanatory prose; absence of a drawn edge in this view never implies a missing edge in the full design.")
    lines.append("Visible inventory (quoted strings are the supplied names, not source IDs):")
    local_text = []
    for group in scopes:
        if figure.get("abstract"):
            # The target plate, not a list of all root groups, decides which
            # boundaries to display. Original owner names remain per object.
            continue
        if any(node["label"] == group["label"] for node in visible):
            continue
        parent = groups.get(group.get("parent"))
        line = "Scope " + _quote(group["label"])
        if parent:
            line += "; original parent " + _quote(parent["label"])
        lines.append(line + (". Preserve the plate's shown containment and boundary positions; do not add or remove an ownership boundary." if faithful else ". Keep the real containment clear; an unnecessary outer wrapper may be omitted without changing ownership."))
        local_text.append(group["label"])
    for node in visible:
        owner = _owner(node, sources, groups)
        role = "original subsystem scope, not another hardware module" if node.get("logical_group") else str(node.get("kind", "resource"))
        line = _quote(node["label"]) + " — " + role
        if owner:
            line += "; belongs to " + _quote(owner["label"])
        children = _children(node, sources) if figure.get("abstract") else []
        if children:
            line += "; original contents " + ", ".join(_quote(child["label"]) for child in children)
            local_text.extend(child["label"] for child in children)
        detail = _detail(node, sources)
        equivalent_id = node.get("equivalent_to")
        if not equivalent_id:
            match = re.fullmatch(r"Same resources as\s+([a-zA-Z_][a-zA-Z_0-9]*)", detail, re.I)
            if match and (match.group(1) in display or match.group(1) in groups or match.group(1) in sources):
                equivalent_id = match.group(1)
        detail_node = {**sources.get(node.get("id"), {}), **node, "detail": detail}
        if owner:
            detail_node["group"] = owner["id"]
        parameter_detail = "" if equivalent_id else required_detail(detail_node, spec, required_labels or [])
        if parameter_detail:
            line += "; supplied parameter or expression " + _quote(parameter_detail)
            local_text.append(parameter_detail)
        lines.append(line + ".")
        local_text.append(node["label"])
        if detail and not _has_exact_notation(detail):
            local_text.append(detail)
        for child in children:
            child_detail = _detail(child, sources)
            if child_detail:
                local_text.append(child_detail)
                detail_child = {**sources.get(child.get("id"), {}), **child, "detail": child_detail}
                if required_detail(detail_child, spec, required_labels or []):
                    lines.append("Supplied content parameter within " + _quote(node["label"]) + ": " + _quote(child["label"]) + " — " + _quote(child_detail) + ".")
        if equivalent_id:
            equivalent = _endpoint(equivalent_id, display, sources, groups)
            if children:
                lines.append("It has the same explicitly supplied private inventory as " + equivalent + ". Preserve its shown private contents as in the guide; they are separate private resources, not common storage. Do not connect equivalent peers in series.")
            else:
                lines.append("It has the same explicitly supplied private inventory as " + equivalent + ". Keep this peer compact as in the guide; do not repeat all of the representative's interior text or connect the peers in series.")
        elif node.get("inherited_visual_only") or node.get("inherited"):
            lines.append("Its shown private contents follow the supplied instance equivalence; they are not an additional common resource or an invented connection.")
    for inset in figure.get("structure_layout", {}).get("insets", []):
        if not inset.get("same_hardware"):
            continue
        parent = display.get(inset.get("source_object"))
        if not parent:
            continue
        children = inset.get("metrics", {}).get("children", [])
        if children:
            lines.append("Same-hardware detail expansion of " + _quote(parent["label"]) + " contains " + ", ".join(_quote(child["label"]) for child in children) + ". This expands the same named source instance, not a new hardware copy; its explanatory leader has no data arrowhead.")
            local_text.extend(child["label"] for child in children)
    planned, authority_lines = _text_authority(figure, spec, display, sources, groups, required_labels)
    lines.extend(authority_lines)
    lines.append("Directed relationships (endpoint names identify the objects above; meanings preserve the full semantic contract):")
    if not edges:
        lines.append("No relationship is supplied in this view. Add no arrows.")
    for edge in edges:
        arrow = " <-> " if edge.get("bidirectional") else " -> "
        label = edge.get("label", "")
        line = _endpoint(edge["source"], display, sources, groups) + arrow + _endpoint(edge["target"], display, sources, groups)
        line += " [" + str(edge.get("kind", "relation")) + "]"
        if edge.get("stroke_style"):
            line += "; planned stroke " + edge["stroke_style"]
        if label:
            line += "; meaning " + _quote(label)
            if planned is not None and not _planned_for_edge(label, edge, planned, spec) and not _mandatory_edge_text(label, required_labels):
                line += " (caption only; do not print as edge text)"
            local_text.append(label)
        directional = edge.get("directional_labels", [])
        for fact in directional:
            fact_label = fact.get("label", "")
            line += "; " + _endpoint(fact["source"], display, sources, groups) + " -> " + _endpoint(fact["target"], display, sources, groups) + ": " + _quote(fact_label)
            if planned is not None and not _planned_for_edge(fact_label, edge, planned, spec) and not _mandatory_edge_text(fact_label, required_labels):
                line += " (caption meaning)"
            local_text.append(fact.get("label", ""))
        lines.append(line + ".")
    behavior = []
    if not figure.get("abstract") and set(figure.get("node_ids", sources)) == set(sources):
        behavior = list(spec.get("steps", [])) + list(spec.get("annotations", []))
    behavior = list(figure.get("steps", [])) + list(figure.get("annotations", [])) or behavior
    if figure.get("abstract"):
        # Preserve an explicit relationship between named visible contents,
        # such as alternative execution paths, without copying global prose
        # from a subsystem absent from this view.
        names = set(local_text)
        behavior.extend(item for item in spec.get("annotations", []) if isinstance(item, str) and sum(bool(name) and name in item for name in names) >= 2)
    if behavior:
        lines.append("Supplied behavior and expressions; preserve the order, predicates, values and operations:")
        lines.extend(_quote(item) for item in behavior)
        local_text.extend(behavior)
    manifest = "\n".join(local_text)
    mandatory = list(dict.fromkeys(str(label) for label in (required_labels or []) if str(label) and str(label) in manifest))
    if mandatory:
        lines.append("Mandatory verbatim text, only on its matching supplied object: " + "; ".join(_quote(label) for label in mandatory) + ".")
    lines.extend([
        "Text policy: Preserve names, identifiers, numerical parameters, equations and conditions. Edge labels belong in associated open gaps, never in white boxes over wires. Optional explanatory prose stays in the caption. Print no source IDs, grammar names, provenance or review notes. The title stays in the document caption unless explicitly required in the guide.",
        "Final review: Require legible names, coherent hierarchy, purposeful spacing and traceable directed paths. Add no facts, capacities, cycles or protocols. For technical failure, regenerate from the source specification and a clean corrected guide instead of repeatedly editing the failed bitmap.",
    ])
    return "\n".join(lines)
