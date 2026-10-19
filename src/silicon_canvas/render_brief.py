"""Art direction for material product renders, separate from graph geometry.

The source is an engineering ledger. A commercial image is an interpretation
of that product, not a mandatory rectangular display of that ledger. Appearance
choices are editable editorial decisions and never become engineering facts.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re

from . import scene_profiles, render_strategy

VERSION = "RENDER3"


def _hash(spec):
    return hashlib.sha256(json.dumps(spec, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def primary(spec, representation, scene="", language="en"):
    """A complete subject, with a separate source-backed explanatory layer."""
    name = "商业产品渲染" if representation == "product_render" else "技术产品插画"
    question = ("What is the complete product, and how should its material presence communicate its identity?"
                if representation == "product_render" else "How does the complete real system work, explained through a coherent dimensional illustration?")
    return {"id": "product-render" if representation == "product_render" else "system-illustration",
            "kind": "overview", "abstract": True, "primary": True, "technical_annex": False,
            "title": spec["title"], "summary": name + "；源规格完整保留，外观假设与工程事实分别记录。",
            "representation": representation, "view_role": representation, "view_type": "art-directed-render",
            "node_ids": [], "edge_indices": [], "context_nodes": [], "macro_nodes": [], "macro_edges": [],
            "source_edge_indices": [],
            "projection": {"source_node_to_macro": {}, "internal_edges": [],
                           "deferred_edges": [{"index": i, "reason": "Engineering relationship retained in the ledger and technical companions; product rendering does not assert visible wires."}
                                              for i in range(len(spec["edges"]))],
                           "ownership_unchanged": True,
                           "meaning": "A complete subject rendering may carry source-backed logical regions and relationships. Their placement is an explanatory projection, not a measured die floorplan or physical chiplet arrangement."},
            "design_contract": {"grammar": representation, "question": question,
                                "claim": "The complete source product is illustrated; material appearance is illustrative unless supplied.",
                                "scope": "whole source product, with exact technical companions", "scene_id": scene,
                                "target_width_mm": 240, "body_pt": 11, "signal_pt": 9.5,
                                "source_invariants": ["source identity", "explicit quantities", "ownership", "technical claims", "verbatim text"],
                                "editorial_decisions": ["camera", "lighting", "materials", "background", "crop", "visual detail", "caption separation"],
                                "generation_inputs": "text brief alone is sufficient; an optional composition reference controls framing only",
                                "regeneration_policy": "Regenerate from the source brief when any visible claim contradicts source facts."}}


_PHYSICAL = re.compile(r"\b(?:package|packaging|chiplet|die|dies|HBM\d*|interposer|wafer|substrate|PCB|board|BGA|LGA|lid|ceramic|metal|silicon|photograph)\b|封装|裸片|晶圆|硅片|基板|电路板|金属|陶瓷|盖板|实物|小芯片|堆叠", re.I)
_APPEARANCE = re.compile(r"camera|lighting|material|background|perspective|angle|isometric|studio|white\s*background|dark\s*background|相机|光照|材质|背景|透视|俯视|仰视|等距|视角|白底|黑底|深色|浅色|留白|质感", re.I)
_VISUAL_WISH = re.compile(r"想要|希望|风格|质感|看起来|呈现|feel|look\s*like|style|wish|would\s*like|render|渲染", re.I)
_NEGATION = re.compile(r"不要|不用|避免|不需要|无需|不能|别用|禁止|不可|without|avoid|never|do\s*not|don't|\bno\b|\bnot\b(?!\s*only)", re.I)
_EXTERNAL = re.compile(r"\boff[ -]?chip\b|\bexternal\b|片外|芯片外", re.I)
_NON_CLAIMS = [
    "Camera, materials, reflections, shadows and decorative surface detail are illustration choices, not measured product properties.",
    "Logical CPU/GPU/NPU resources are not proof of separate dies, chiplets, HBM stacks, a board or package layers.",
    "Never invent process nodes, package technology, die count, dimensions, pin count, bandwidth, capacity, benchmark numbers or logos.",
    "A render is neither a fabricated-chip photograph nor a measured floorplan. Unspecified appearance must remain a generic concept.",
]


def _sentences(text):
    return [value.strip() for value in re.split(r"(?<=[。！？!?;；])|\n", text) if value.strip()]


def _subject_kind(text, spec):
    plan = render_strategy.subject_plan(text, spec)
    return plan["kind"], plan["instruction"]


def _visual_cue(text, pattern):
    """Return a conservative positive/excluded cue without rewarding negation.

    Split common contrasting clauses so '用等距，但不要俯视' remains meaningful.
    Free-form input is also preserved verbatim in the brief: this lightweight
    default selection must not pretend to exhaustively parse natural language.
    """
    return scene_profiles.visual_cue(text, pattern)


def _art_direction(text, representation, settings, palette, required_labels, subject_kind, mode="hero"):
    dark, no_dark = _visual_cue(text, r"dark\s*(?:background|studio)|黑底|深色背景|暗色背景|黑色背景")
    light, no_light = _visual_cue(text, r"white\s*(?:background|studio)|light\s*(?:background|studio)|白底|白色背景|浅色背景")
    transparent, no_transparent = _visual_cue(text, r"transparent\s*(?:background|canvas)|透明背景|透明底")
    top, no_top = _visual_cue(text, r"top[ -]?down|overhead|俯视|顶视")
    iso, no_iso = _visual_cue(text, r"isometric|等距|轴测")
    _, no_metal = _visual_cue(text, r"metal(?:lic)?|金属")
    _, no_ceramic = _visual_cue(text, r"ceramic|陶瓷")
    camera = ("A restrained top-down camera with visible material highlights and a clear complete subject." if top else
              "An elegant orthographic three-quarter isometric camera, generous depth separation and no wide-angle distortion." if iso else
              "A low, near-level three-quarter product camera with controlled perspective; avoid overhead or elevated top-down framing." if no_top else
              "A controlled three-quarter product camera, approximately 30 degrees above the subject, a long lens with subtle perspective; choose the best orientation for its silhouette.")
    materials = "Believable satin metal, matte technical ceramic or restrained silicon finish as appropriate to the subject; coherent edge thickness and restrained surface detail."
    if subject_kind in {"wafer_concept", "bare_die_concept"}:
        materials = "Convincing silicon surface reflectance with restrained abstract microscopic texture and natural highlights. Any functional regions form a clearly illustrative overlay, not a measured lithographic floorplan."
    elif subject_kind in {"board_concept", "system_assembly_concept"}:
        materials = "Distinguish source-backed objects using believable board substrate, package and structural finishes. Keep one consistent material/light system across the assembly; unspecified mechanical details remain generic."
    if no_metal or no_ceramic:
        materials = "Use credible restrained surface finishes that respect the user's material exclusions. Let form and soft light establish depth; do not add the excluded metal or ceramic-like finish as a default."
    if transparent:
        background = "A transparent canvas with clean subject edges and isolated grounded shading; request transparent output in the image generator. Do not fill a studio backdrop."
    elif dark or (no_light and not no_dark):
        background = "A quiet dark charcoal studio field with tonal depth and controlled contrast; no neon grid, cosmic scenery or sci-fi circuits."
    elif no_light and no_dark:
        background = "Choose a quiet mid-tone neutral field satisfying the user's exclusions; avoid both white/light and dark/black studio fields."
    elif no_dark:
        background = "A clean light neutral studio field with subtle tonal separation and generous empty space; avoid dark or black background treatment."
    else:
        background = "A clean light neutral studio field with subtle tonal separation and generous empty space; transparent output only when explicitly requested by the user."
    return {"camera": camera,
            "materials": materials,
            "lighting": "Large soft studio key, gentle fill and a narrow controlled rim highlight; reflections reveal form without hiding labels. Contact shadow should ground the object naturally.",
            "background": background,
            "transparent_background": transparent,
            "exclusions": {"top_down": no_top, "isometric": no_iso, "dark_background": no_dark,
                           "light_background": no_light, "transparent_background": no_transparent,
                           "metal_finish": no_metal, "ceramic_finish": no_ceramic},
            "composition": ("One dominant coherent complete product or supplied assembly, deliberate scale and a strong overall silhouette. Explicit multiple physical objects may form that assembly. Let camera, finish and grounded lighting organize the hero image; leave usable negative space for any explicitly requested presentation copy." if mode == "hero" else
                            "One dominant coherent complete product or system assembly, deliberate scale and a strong overall silhouette. Explicit multiple physical objects may form that assembly. Organize functional roles into a few contiguous regions, give shared resources clear common ownership, and stage external context beyond the chip boundary. Leave real space for readable typography."),
            "detail": {"hero": "A tangible product hero with an intact, quiet exterior; material, silhouette and light carry the image. Minimal annotation fits a cover or visual identity request.",
                       "annotated_context": "A complete product with source-backed subsystem callouts and a small amount of useful external context. Each heading has a concise member list; restrained interface links explain how the product relates to its environment.",
                       "functional_cutaway": "An explanatory chip plane or conceptual cutaway with coherent logical regions, a clearly shared interconnect or resource, and a few source-backed principal relationships. Keep regions on one common perspective plane; they are functional overlays, not separate physical dies. Let grouping and reading order explain the architecture before decorative texture.",
                       "assembly": "A coherent whole-system assembly with source-backed objects and quantities. Choose staging that reveals ownership, shared resources and principal interfaces; mechanical detail remains secondary to the explanation."}[mode],
            "labels": {"policy": ("Only explicitly requested copy appears on this hero. Required text is exact and legible, with strong contrast against the actual surface; optional technical inventory belongs in the external caption." if mode == "hero" else
                                  "Required text is exact and legible. Use one consistent typographic hierarchy, strong contrast against the actual surface, concise member lists, and adequate spacing. Functional overlays may carry their own labels; surrounding callouts use tidy neutral leaders."),
                       "required_verbatim": list(required_labels), "optional_callout_budget": 3 if mode == "hero" else 6,
                       "title": "A small optional heading in negative space; the source title is available in the external caption."},
            "accent_palette": copy.deepcopy(palette),
            "palette_policy": ("Use a quiet material palette with restrained accent color; finish and lighting establish the visual identity." if mode == "hero" else
                               "Use a quiet base and a small family of muted accents for semantic roles. Keep one hue per meaningful region and emphasize one main route; colors do not imply physical manufacturing boundaries."),
            "canvas": settings.get("aspect", "auto"),
            "freedom": ["Choose effective framing, camera, crop, focal hierarchy and material finish.",
                        "Omit nonessential visible callouts, arrows and implementation internals while retaining facts in metadata and companions.",
                        "Do not copy geometry from a 2D technical diagram. An optional framing reference carries no engineering placement authority."]}


def _explanation_mode(text, feedback, settings, subject_kind, spec):
    """Select communicative content independently of the rendering medium."""
    requested = settings.get("explanatory_mode", "auto")
    modes = {"hero", "annotated_context", "functional_cutaway", "assembly"}
    if requested in modes:
        return requested, "The user selected this explanatory treatment."

    functional_pattern = (r"内部(?:功能|结构|组织|架构|分区|原理)|(?:显示|展示|揭示|展现)[^。;；\n]{0,5}内部|"
                          r"功能分区|逻辑分区|剖视|剖面|剖切|截面|切开|芯片平面|工作原理|\bcutaway\b|cross[ -]?section|sectioned|"
                          r"(?:internal|inside)\s+(?:(?:logical|functional|function|structural)\s+)*(?:regions?|partitions?|organization|architecture|structure)|"
                          r"functional\s*(?:map|regions?|partition|overlay|cutaway)|(?:reveal|show|display)\b[^.;\n]{0,24}\binternal\b")
    def select(value, allow_subject_default=True):
        if not value.strip():
            return None
        no_text = _omit_text(value)
        hero = scene_profiles._positive_hero(value) or _visual_cue(value, r"纯外观|产品摄影|纯[^。;；\n]{0,12}(?:产品|外观)|只[^。;；\n]{0,12}(?:外观|封装)|\b(?:only|just)\s+(?:the\s+)?(?:exterior|package|appearance)\b")[0]
        functional, no_functional = _visual_cue(value, functional_pattern)
        connective, _ = _visual_cue(value, r"\bon[ -]?chip\b|\bNoC\b|\binterconnect\b|互联")
        context, _ = _visual_cue(value, r"外围|周边|外部|片外|外设|标注|引线|能力说明|\b(?:external|context|annotated|callouts?|peripheral|environment)\b")
        assembly, _ = _visual_cue(value, r"完整[^。;；\n]{0,12}(?:服务器|机架|板卡)|多(?:块|张)[^。;；\n]{0,8}卡|整机|组装|\bassembl(?:y|ed)\b|\brack\b")
        section, _ = _visual_cue(value, r"剖切|剖面|剖视|截面|\bcutaway\b|cross[ -]?section|sectioned")
        exploded, _ = _visual_cue(value, r"爆炸(?:图|视图)?|\bexploded\b")
        intact, _ = _visual_cue(value, r"(?:保留|保持|完整|整颗)[^。;；\n]{0,18}(?:封装外观|封装外形|封装主体|盖板)|(?:intact|closed)[^.;\n]{0,35}(?:package|exterior)|(?:preserve|keep|retain)[^.;\n]{0,35}(?:package\s*)?exterior")
        if hero and (no_functional or not (functional or connective)):
            return "hero"
        if section and not exploded:
            return "functional_cutaway"
        if assembly or exploded:
            return "assembly"
        if intact:
            return "annotated_context" if functional or connective or context else "hero"
        if allow_subject_default and subject_kind in {"system_assembly_concept", "package_assembly_concept"}:
            return "assembly"
        if functional:
            return "functional_cutaway"
        if context:
            return "annotated_context"
        if connective:
            return "functional_cutaway"
        if hero:
            return "hero"
        if no_text:
            return "hero"
        return None

    revision = select(feedback, allow_subject_default=False)
    if revision:
        return revision, "The latest visual feedback changes how the information should be explained."
    _, excluded_cutaway = _visual_cue(feedback, functional_pattern)
    if excluded_cutaway:
        return "annotated_context", "The latest feedback excludes the internal cutaway; explain functions and context around the intact product."
    selected = select(text)
    if selected:
        return selected, "The description requests this explanatory treatment."
    if subject_kind == "system_assembly_concept":
        return "assembly", "A whole-system assembly is the supplied subject."
    if spec.get("groups") or spec.get("edges") or len(spec.get("nodes", [])) > 1:
        return "annotated_context", "The source contains meaningful functions and relationships; a useful presentation should explain them, rather than showing only an exterior."
    return "hero", "The source only specifies an object identity, with no explanatory structure."


def _omit_text(text):
    return bool(re.search(r"不需要(?:任何)?文字|不要(?:任何)?文字|(?<!不要)(?<!避免)无文字|不加说明|不要说明|\bno\s*(?:text|labels?)\b", text, re.I))


def _composition_plan(spec, mode, text, feedback):
    """Choose an explanatory geometry without asserting manufactured geometry."""
    def cue(pattern):
        latest = _visual_cue(feedback, pattern)
        return latest if any(latest) else _visual_cue(text, pattern)
    section, excluded_section = cue(r"剖切|剖面|剖视|截面|\bcutaway\b|cross[ -]?section|sectioned")
    exploded, _ = cue(r"爆炸(?:图|视图)?|\bexploded\b")
    physical_members = [node["id"] for node in spec["nodes"]
                        if _PHYSICAL.search(node["label"] + " " + node.get("detail", ""))]
    physical_section = mode == "functional_cutaway" and section and not excluded_section and len(physical_members) >= 2
    detail, _ = cue(r"局部(?:放大|展示|解释)|细节放大|整体与局部|部件(?:特写|展开)|放大(?:一个|局部|其中|单个)|detail\s+(?:view|inset)|\binset\b|close[ -]?up|whole[^.;\n]{0,18}detail")
    geometry = ("assembled_section" if physical_section else
                "logical_function_plane" if mode == "functional_cutaway" else
                "whole_with_context" if mode == "annotated_context" else
                "exploded_assembly" if mode == "assembly" and exploded else
                "coherent_assembly" if mode == "assembly" else "product_identity")
    instructions = {
        "assembled_section": "Keep one assembled subject in a common perspective. Reveal the explicitly supplied internal parts through one local section opening, preserving their supplied layer order and contact relationships; the rest of the assembly remains intact. Do not replace the section with two rows of flow boxes or a separated exploded stack. Unspecified thickness, interfaces and manufacturing detail remain conceptual.",
        "logical_function_plane": "Place logical regions as a deliberate contiguous composition on one common chip plane or conceptual cutaway. Concentrate depth in the single chip base. Role overlays stay flat, pale or subtly translucent, without thick slabs or raised buttons. Let shared resources and the selected principal links organize the functions; logical placement and area are illustrative, not a measured floorplan or separate chiplets.",
        "whole_with_context": "Keep the intact product surface quiet, without a second copy of its internal groups or a covered-in-labels lid. Explain selected functions through unboxed perimeter headings or a clearly subordinate requested detail. Put external roles outside the product silhouette. Interface links are nonemissive fine lines, not glowing cables or ribbons.",
        "exploded_assembly": "Separate only the source-supplied assembly layers enough to reveal membership and assembly order, while keeping a shared alignment axis and consistent perspective. Preserve explicit component counts; separation is an explanatory view, not another set of components. Do not turn assembly associations into invented up/down data or heat arrows.",
        "coherent_assembly": "Stage the source-supplied physical objects as one coherent assembly, with readable ownership and relative hierarchy. Preserve explicit quantities and membership. Objects share one camera, scale convention, material family and lighting system; do not separate layers into an exploded view unless requested.",
        "product_identity": "Keep one complete quiet product as the visual anchor. Silhouette, material and light establish its identity; leave requested copy space outside the subject and avoid adding an unsolicited technical inventory.",
    }
    return {"geometry": geometry, "instruction": instructions[geometry],
            "detail_view": {"requested": detail, "role": "same source object at a larger explanatory scale, not an additional hardware instance",
                            "instruction": ("Keep the whole subject dominant and the requested detail view subordinate, with a clear same-object association. A detail repeats the same source identity at another scale; it does not increase component count or authorize unsupported microstructure." if detail else
                                            "Do not add a detail inset by default; use the selected whole-subject explanation.")},
            "repetition_policy": "Repeated source components share the same orientation, scale, material and light; show source-specified multiplicity consistently without turning logical instances into physical dies.",
            "annotation_policy": "Place each concise label near its source-backed part or region in open space, keeping text horizontal and high-contrast. Neutral part-identification leaders are unheaded; only the listed source relationships carry direction. Align main-route endpoints before adding bends, and do not route through labels or unrelated parts.",
            "authority": "editorial explanation only; not CAD, a measured floorplan, a physical BOM or pixel-quality certification"}


def _visible_semantics(spec, mode, required_labels, no_text, control_detail=False, directed_traffic=False, preserve_parts=False):
    """A bounded, source-backed visual projection; it never edits the ledger."""
    groups = {group["id"]: group for group in spec["groups"]}
    nodes = {node["id"]: node for node in spec["nodes"]}

    def external(node):
        # A controller's 'external memory interface' is its destination, not
        # evidence that the controller itself lives off chip.
        from .reading_plan import _external_node
        return _external_node(node, groups)

    context = [{"id": "context:" + node["id"], "label": node["label"], "source_node_ids": [node["id"]],
                "role": "external resource", "origin": node.get("origin", "given"),
                "portrayal": "A simplified contextual device or icon; a role symbol, not a claimed physical BOM item or package count."}
               for node in spec["nodes"] if external(node)]
    regions = []
    source_to_region = {item["source_node_ids"][0]: item["id"] for item in context}
    # Top-level ownership groups give the overview its hierarchy. A group may
    # own subgroups; their members remain inside that one explanatory region.
    whole_roots = {group["id"] for group in spec["groups"] if not group.get("parent")
                   and re.search(r"\b(?:soc|chip|gpu|system)\b|整.*系统|芯片", group["label"], re.I)
                   and any(child.get("parent") == group["id"] for child in spec["groups"])}
    for group in (() if preserve_parts else spec["groups"]):
        if (group.get("parent") and group["parent"] not in whole_roots) or group["id"] in whole_roots or _EXTERNAL.search(group["label"]):
            continue
        descendants = {group["id"]}
        changed = True
        while changed:
            before = len(descendants)
            descendants.update(item["id"] for item in spec["groups"] if item.get("parent") in descendants)
            changed = len(descendants) != before
        members = [node for node in spec["nodes"] if node.get("group") in descendants and not external(node)]
        if not members:
            continue
        label = group["label"]
        role = ("compute" if re.search(r"compute|计算|处理|执行", label, re.I) else
                "memory" if re.search(r"memory|存储|缓存", label, re.I) else
                "management" if re.search(r"management|管理|clock|power|时钟|电源", label, re.I) else
                "interface" if re.search(r"\bIO\b|\bI/O\b|interface|peripheral|接口|外设", label, re.I) else "functional group")
        region = {"id": "region:" + group["id"], "label": label, "role": role,
                  "members": [node["label"] for node in members], "source_node_ids": [node["id"] for node in members],
                  "member_details": [{"label": node["label"], "detail": node.get("detail", ""), "source_node_id": node["id"]}
                                     for node in members if node.get("detail")],
                  "source_group_ids": sorted(descendants), "origin": group.get("origin", "given"),
                  "portrayal": "One contiguous logical role region or grouped callout; placement and area are explanatory, not measured physical implementation."}
        regions.append(region)
        source_to_region.update({node["id"]: region["id"] for node in members})
    for node in spec["nodes"]:
        if node["id"] in source_to_region:
            continue
        region = {"id": "region:" + node["id"], "label": node["label"],
                  "role": "shared interconnect" if re.search(r"interconnect|\bNoC\b|总线|互联", node["label"], re.I) else node["kind"],
                  "members": [], "member_details": ([{"label": node["label"], "detail": node["detail"], "source_node_id": node["id"]}] if node.get("detail") else []),
                  "source_node_ids": [node["id"]], "source_group_ids": [node["group"]] if node.get("group") else [],
                  "origin": node.get("origin", "given"), "portrayal": ("Individually identifiable supplied assembly part; preserve its source layer order and contact relationships." if preserve_parts else "Source-backed logical role, not a separate physical die.")}
        regions.append(region)
        source_to_region[node["id"]] = region["id"]
    # Prefer meaningful groups and shared resources, keeping the source order
    # within each class. This is an editorial budget, not an object inventory.
    ordered_regions = sorted(regions, key=lambda region: 0 if region["role"] == "shared interconnect" else 1)
    # An explicit assembly section cannot silently lose its seventh layer or
    # ninth path through the generic concept illustration's editorial budget.
    selected = ordered_regions if preserve_parts else ordered_regions[:6]
    visible_context = context if preserve_parts else context[:3]
    visible_ids = {region["id"] for region in selected} | {item["id"] for item in visible_context}
    relationship_map = {}
    for index, edge in enumerate(spec["edges"]):
        start, end = source_to_region[edge["source"]], source_to_region[edge["target"]]
        if start == end or start not in visible_ids or end not in visible_ids:
            continue
        if edge["kind"] in {"clock", "control"} and not control_detail:
            continue
        directionality = "source-directed" if edge["kind"] in {"data", "control", "feedback", "clock"} else "association"
        key = start, end, directionality
        if key not in relationship_map:
            relationship_map[key] = {"source": start, "target": end,
                                     "source_label": next((item["label"] for item in selected + context if item["id"] == start), nodes[edge["source"]]["label"]),
                                     "target_label": next((item["label"] for item in selected + context if item["id"] == end), nodes[edge["target"]]["label"]),
                                     "labels": [], "kinds": [], "source_edge_indices": [],
                                     "source_node_pairs": [], "origin": edge.get("origin", "given"),
                                     "directionality": directionality}
        item = relationship_map[key]
        item["source_edge_indices"].append(index)
        item["source_node_pairs"].append([edge["source"], edge["target"]])
        if edge.get("label") and edge["label"] not in item["labels"]:
            item["labels"].append(edge["label"])
        if edge["kind"] not in item["kinds"]:
            item["kinds"].append(edge["kind"])
        if edge.get("origin", "given") == "assumed":
            item["origin"] = "assumed"
    ordered_relationships = sorted(relationship_map.values(), key=lambda item: (0 if item["source"].startswith("context:") or item["target"].startswith("context:") else 1,
                                                                       1 if all(kind in {"clock", "control"} for kind in item["kinds"]) else 0))
    relationships = ordered_relationships if preserve_parts else ordered_relationships[:8]
    symbols = []
    for node in spec["nodes"]:
        if node.get("kind") != "io" or external(node):
            continue
        protocols = list(dict.fromkeys(re.findall(r"\b(?:UART|SPI|I2C|I²C|GPIO|USB|PCIe|Ethernet|JTAG|MIPI|CAN)\b", node.get("detail", ""), re.I)))
        if protocols:
            symbols.append({"label": " / ".join(protocols), "source_node_ids": [node["id"]],
                            "source_label": node["label"], "origin": node.get("origin", "given"),
                            "role": "symbolic interface family", "portrayal": "Optional small neutral interface glyph or caption derived from source details; not actual connector geometry, device quantity or pinout."})
    if mode == "hero":
        selected, context, relationships = [], [], []
        visible_context = []
        symbols = []
    elif mode == "annotated_context":
        # On an exterior image, links explain the environment. Internal
        # topology remains in member lists unless requested as a cutaway.
        relationships = [item for item in relationships if item["source"].startswith("context:") or item["target"].startswith("context:")]
    shown = {node_id for item in selected + visible_context for node_id in item["source_node_ids"]}
    return {"regions": selected, "relationships": relationships, "context_objects": visible_context, "interface_symbols": symbols[:3],
            "relationship_portrayal": {"directed_traffic": directed_traffic,
                                        "line_policy": "Use listed source directions for selected data, control, feedback and clock relationships, with discreet small target arrowheads. Keep opposite directed flows separately traceable. Association/interface relationships use quiet unheaded lines. The selected scope stays sparse; deferred engineering details do not become extra visible wiring.",
                                        "control_detail": control_detail},
            "optional_capability_labels": [] if no_text else [region["label"] for region in selected],
            "required_verbatim_labels": list(required_labels), "no_optional_text": no_text,
            "physical_object_policy": "Source-backed external roles may be simplified as contextual devices, connector symbols or interface links. These explain function, not a physical BOM, package count, cable pinout or measured implementation.",
            "annotation_policy": "Logical regions and principal links are permitted in the selected explanatory treatment. Their boundaries, sizes and positions are illustrative; keep shared ownership and source relationships clear.",
            "deferred_node_ids": [node["id"] for node in spec["nodes"] if node["id"] not in shown],
            "deferred_edge_indices": [i for i in range(len(spec["edges"])) if not any(i in item["source_edge_indices"] for item in relationships)],
            "disclosure": "Functional placement, area, texture and external device shapes are conceptual. Given facts and generic assumptions remain separately marked in the accompanying source; no measured floorplan, manufactured package or BOM is claimed."}


def build(spec, figure, settings, description="", palette=None, required_labels=(), visual_feedback=""):
    representation = figure["representation"]
    text = description + "\n" + settings.get("notes", "")
    subject_plan = render_strategy.subject_plan(text, spec)
    subject_kind, subject_instruction = subject_plan["kind"], subject_plan["instruction"]
    mode, mode_reason = _explanation_mode(text, visual_feedback, settings, subject_kind, spec)
    composition = _composition_plan(spec, mode, text, visual_feedback)
    if composition["geometry"] == "assembled_section":
        subject_kind = "sectioned_assembly_concept"
        subject_instruction = "one complete source-described assembly with a local section opening revealing its supplied internal parts, preserving assembly state and relative layer order; proportions and hidden mechanical detail remain conceptual"
    elif mode == "functional_cutaway" and subject_kind == "generic_package_concept":
        subject_instruction = "one coherent chip-scale conceptual plane or nonphysical cutaway, carrying the supplied logical functions and their principal relationships; keep a common perspective and make its boundaries explicitly illustrative, not a measured die floorplan"
    groups = {group["id"]: group for group in spec["groups"]}
    all_facts = [{"id": node["id"], "label": node["label"], "kind": node["kind"], "group": node["group"],
                  "detail": node.get("detail", ""), "origin": node.get("origin", "given"),
                  "evidence": node.get("evidence", ""), "rationale": node.get("rationale", "")}
                 for node in spec["nodes"]]
    sentences = list(dict.fromkeys(_sentences(text)))
    physical_constraints = [sentence for sentence in sentences
                            if _PHYSICAL.search(sentence) and re.search(r"不是|不代表|不表示|非物理|不要|不用|避免|不需要|无需|\bno\b|\bnot\b|\bwithout\b", sentence, re.I)]
    appearance_known = [{"statement": sentence, "origin": "user_input", "evidence": sentence,
                         "verified": False, "status": "supplied_not_independently_verified"}
                        for sentence in sentences
                        if _PHYSICAL.search(sentence) and sentence not in physical_constraints and not _APPEARANCE.search(sentence) and not _VISUAL_WISH.search(sentence)]
    appearance_requests = [sentence for sentence in sentences if _APPEARANCE.search(sentence) or _VISUAL_WISH.search(sentence)]
    assumptions = ["除用户明确给出的外观条件外，相机、材质、光照、轮廓和表面细节是可调整的概念表现，不代表已制造产品。"]
    if subject_kind == "generic_package_concept":
        assumptions.append("通用芯片外形承载整个产品；逻辑功能区不是独立 die/chiplet，面积、位置与轮廓不是实测 floorplan。")
    if mode != "hero":
        assumptions.append("功能分区、互联覆盖及外围器件符号用于解释源规格；它们不是实际封装结构、物理 BOM、引脚数量或接口线缆实物。")
    if any(node.get("origin", "given") == "assumed" for node in spec["nodes"]):
        assumptions.append("源规格中标为 assumed 的功能与关系是可调整的通用示例，不是已确认产品能力。")
    intent_for_copy = visual_feedback if re.search(r"文字|说明|标签|标注|text|labels?|copy", visual_feedback, re.I) else text
    no_text = _omit_text(intent_for_copy)
    control_detail, _ = _visual_cue(text + "\n" + visual_feedback, r"控制(?:流|线|路径|信号)|时钟.*(?:线|分发)|电源.*(?:线|控制)|命令|任务分发|调度|control\s*(?:flow|paths?|signals?)|clock\s*distribution|commands?|dispatch|scheduler")
    directed_traffic, _ = _visual_cue(text + "\n" + visual_feedback, r"数据流|流向|方向|箭头|有向|data\s*flow|traffic|direction|arrowheads?|directed")
    visible = _visible_semantics(spec, mode, required_labels, no_text, control_detail, directed_traffic,
                                 preserve_parts=composition["geometry"] == "assembled_section" or mode == "assembly")
    visible["primary_subject"] = subject_instruction
    visible["source_inventory_role"] = "Complete source evidence stays in the semantic contract and companions; this projection selects useful visible explanation."
    shown_edges = {index for relation in visible["relationships"] for index in relation["source_edge_indices"]}
    contract = {"source_hash": _hash(spec),
                "known_facts": [item for item in all_facts if item["origin"] == "given"],
                "assumed_facts": [item for item in all_facts if item["origin"] == "assumed"],
                "source_relations": [{"index": i, **copy.deepcopy(edge), "visible_requirement": i in shown_edges}
                                     for i, edge in enumerate(spec["edges"])],
                "ownership": [{"id": group["id"], "label": group["label"], "parent": group["parent"],
                               "origin": group.get("origin", "given"), "members": [node["id"] for node in spec["nodes"] if node["group"] == group["id"]]}
                              for group in spec["groups"]],
                "required_verbatim_labels": list(required_labels), "non_claims": list(_NON_CLAIMS),
                "visible_claim_policy": "Logical regions, contextual devices and principal relationships may be drawn from the source projection. Keep supplied quantities and ownership; illustrative placement or generic appearance never establishes physical implementation."}
    art_direction = _art_direction(text, representation, settings, palette or {}, required_labels, subject_kind, mode)
    if composition["geometry"] == "assembled_section":
        art_direction["detail"] = "A spatial explanation of one locally sectioned assembly: the supplied layers remain assembled and the opening reveals their relationships. This is distinct from a logical function overlay and an exploded stack."
        art_direction["composition"] = "One dominant assembled silhouette with a readable local section opening; use actual supplied layer order, clear part separation and subordinate labels rather than a flat flowchart."
    elif composition["geometry"] in {"coherent_assembly", "exploded_assembly"}:
        art_direction["composition"] = "One dominant coherent complete assembly with explicit physical membership and a readable hierarchy of supplied parts. Keep one camera and scale convention; show layer separation only in the requested exploded treatment."
    shot = render_strategy.shot_direction(subject_plan, mode, text)
    if shot["camera"]:
        art_direction["camera"] = shot["camera"]
    # Material exclusions are authoritative. A shot profile may not quietly
    # reintroduce a finish that the user removed.
    if not any(art_direction["exclusions"][key] for key in ("metal_finish", "ceramic_finish")):
        art_direction["materials"] = shot["materials"]
    art_direction["lighting"] = shot["lighting"]
    art_direction["palette_policy"] = shot["color"]
    art_direction["labels"]["policy"] = shot["typography"] + " Required text is exact and legible, with strong contrast against the actual surface."
    if composition["geometry"] not in {"assembled_section", "logical_function_plane", "exploded_assembly"}:
        art_direction["composition"] = shot["composition"]
    art_direction["shot_profile"] = shot
    if no_text:
        art_direction["labels"]["policy"] = "Text-free artwork: omit optional titles, labels, member lists, captions, logos, badges and lettering. Names below identify source objects, counts and connections; they are not printed copy. Only an explicit required-verbatim text request can authorize an exception."
    user_intent = {"description": description, "notes": settings.get("notes", "")}
    if visual_feedback:
        user_intent["visual_feedback"] = {"text": visual_feedback, "scope": "visual revision only; does not establish new engineering or physical facts", "priority": "latest visual request"}
        revision = _art_direction(visual_feedback, representation, settings, palette or {}, required_labels, subject_kind, mode)
        for pattern, keys, exclusions in [
            (r"background|studio|背景|白底|黑底|透明底", ("background", "transparent_background"), ("dark_background", "light_background", "transparent_background")),
            (r"camera|angle|perspective|isometric|overhead|top[ -]?down|镜头|视角|相机|俯视|顶视|等距|轴测", ("camera",), ("top_down", "isometric")),
            (r"material|metal|ceramic|材质|金属|陶瓷|质感", ("materials",), ("metal_finish", "ceramic_finish")),
        ]:
            if re.search(pattern, visual_feedback, re.I):
                for key in keys:
                    art_direction[key] = revision[key]
                for key in exclusions:
                    art_direction["exclusions"][key] = revision["exclusions"][key]
        appearance_requests.append(visual_feedback)
    questions = {"hero": "What is the product's visual identity?",
                 "annotated_context": "What does the complete product do, and how does it connect to its environment?",
                 "functional_cutaway": "How are the product's main functions organized, and what connects them?",
                 "assembly": "How do the system's objects, shared resources and interfaces work together?"}
    summary = [region["label"] + (": " + ", ".join(region["members"][:4]) if region["members"] else "") for region in visible["regions"]]
    summary.extend("External context: " + item["label"] for item in visible["context_objects"])
    staged, _ = _visual_cue(text + "\n" + visual_feedback, r"分步|两步|先.*再|保留.*(?:已批准|当前|现有|原图|主体)|staged|two[ -]?pass|preserve.*(?:approved|existing|current)\s*(?:image|subject)")
    return {"version": VERSION, "representation": representation, "source_hash": _hash(spec),
            "artwork_language": settings.get("language", "en"),
            "explanation_plan": {"mode": mode, "reason": mode_reason, "reading_question": questions[mode],
                                 "visible_summary": summary or ["Complete product silhouette, finish and lighting"],
                                 "visible_scope": summary or ["Complete product silhouette, finish and lighting"],
                                 "semantic_role": "source-backed explanatory projection; not physical implementation",
                                 "geometry": composition["geometry"],
                                 "workflow": "optional_edit" if staged else "single_pass"},
            "visible_content": visible, "user_intent": user_intent, "composition_plan": composition,
            "subject": {"title": spec["title"], "scope": "whole source product", "kind": subject_kind,
                        "instruction": subject_instruction, "source_node_ids": [node["id"] for node in spec["nodes"]],
                        "source_group_ids": list(groups), "plan": subject_plan},
            "art_direction": art_direction,
            "appearance": {"known": appearance_known, "physical_constraints": physical_constraints,
                           "unknown": ["actual exterior geometry", "physical module placement", "die count", "package technology", "dimensions", "surface markings"],
                           "illustrative_assumptions": assumptions, "user_visual_requests": appearance_requests,
                           "visual_requests": [{"statement": sentence, "origin": "user_art_direction", "verified": False,
                                                "engineering_fact": False} for sentence in appearance_requests],
                           "known_policy": "Known records are direct input statements, not model-inferred appearance. Requested art direction and later visual feedback do not establish manufacturing facts."},
            "semantic_contract": contract,
            "composition_guide": {"optional": True, "role": "composition_reference", "authority": "framing only",
                                  "instruction": "An optional composition reference only suggests scale, negative space and framing. Freely organize the explanatory regions using the source projection. Guide shapes carry no physical placement, object-count or wiring authority."}}


def _prompt(brief, spec):
    """One concise visual brief; review metadata does not become image props."""
    art, visible = brief["art_direction"], brief["visible_content"]
    mode = brief["explanation_plan"]["mode"]
    nodes = {node["id"]: node for node in spec["nodes"]}
    name = "commercial semiconductor product illustration" if brief["representation"] == "product_render" else "dimensional semiconductor system illustration"
    lines = ["Create a finished " + name + " with Image Gen.",
             "Reader question: " + brief["explanation_plan"]["reading_question"],
             "Treatment: " + mode + ". " + art["detail"],
             "Subject: " + brief["subject"]["instruction"], "Source title: " + spec["title"],
             "Camera: " + art["camera"], "Materials: " + art["materials"], "Lighting: " + art["lighting"],
             "Background: " + art["background"], "Composition: " + art["composition"],
             "Canvas: " + art["canvas"], "Typography: " + art["labels"]["policy"],
             "Color: " + art["palette_policy"],
             ("Build hierarchy before surface detail: one dominant whole-product silhouette, intentional framing, useful negative space and coherent material/light quality. The clean exterior, camera and lighting carry this hero image." if mode == "hero" else
              "Build hierarchy before surface detail: one dominant whole-product silhouette, a few meaningful functional roles and subordinate context. Keep objects under one camera and lighting system; texture remains subtle.")]
    composition = brief["composition_plan"]
    language = "Chinese" if brief["artwork_language"] == "zh" else "English"
    lines.append("Artwork language: " + language + ". Translate optional source-title prose into this language; keep explicitly required verbatim labels unchanged. Original-language source evidence and user intent below are context, not additional artwork text.")
    lines.append("Explanatory geometry: " + composition["instruction"])
    if composition["detail_view"]["requested"]:
        lines.append(composition["detail_view"]["instruction"])
    if mode != "hero":
        lines.append(composition["repetition_policy"] + (" " + composition["annotation_policy"] if not visible["no_optional_text"] else " Keep source object counts and selected relationships while omitting text and identification leaders."))
    if not visible["no_optional_text"]:
        lines.append("Only include a small source-title heading when it helps the requested view. Do not add a marketing subtitle, slogan, tagline or a default 'Functional concept' badge. Detailed assumptions and appearance limitations belong in the separate caption, outside the image.")
    if mode == "hero":
        plan = brief["subject"]["plan"]
        object_ids = list(nodes) if plan["scale"] in {"rack", "server", "system"} else plan["source_physical_part_ids"]
        if object_ids:
            physical = [nodes[node_id]["label"] for node_id in object_ids]
            lines.append("Source-specified objects, including on an unlabelled hero: " + json.dumps(physical,ensure_ascii=False) + ". These are object identities and counts, not requested printed labels. Keep their supplied membership and assembly state; do not add or duplicate parts for visual richness. Internal resources may remain inside an explicitly intact enclosure; independent system devices remain distinct.")
    if visible["regions"]:
        lines.append("Object identities and membership for the text-free composition (do not print these names):" if visible["no_optional_text"] else "Assembly parts (identify each supplied part in its stated assembled position):" if composition["geometry"] == "assembled_section" else "Functional content (exact headings and concise members; place them according to this treatment, once each):")
        for region in visible["regions"]:
            lines.append("- " + region["label"] + (": " + json.dumps(region["members"][:5], ensure_ascii=False) if region["members"] else ""))
        lines.append("Each listed assembly part remains individually identifiable, with its supplied layer position and selected paths visible through the local section. Do not fold these parts into a single package inventory box." if composition["geometry"] == "assembled_section" else "Each quoted member is one source item. Preserve compound labels such as 'Accelerator / DSP' as one member, not separate invented instances. Keep individual system devices visible; logical functions are not independent physical dies.")
    if mode == "assembly":
        ownership = brief["subject"]["plan"]["source_ownership"]
        nodes_by_group = {g["id"]:[nodes[n]["label"] for n in g["members"]] for g in ownership}
        if ownership:
            lines.append("Source membership, expressed by staging, without printed headings or invented enclosures:" if visible["no_optional_text"] else "Source membership, expressed by staging and concise group headings rather than invented physical enclosures:")
            for group in ownership:
                if nodes_by_group[group["id"]]:
                    lines.append("- " + group["label"] + ": " + json.dumps(nodes_by_group[group["id"]],ensure_ascii=False))
        if brief["subject"]["plan"]["scale"] in {"rack", "server", "system"}:
            lines.append("Do not collapse the system into a single chip, convert device roles into package parts, or duplicate the inventory in peripheral bullet lists. A system device's exact exterior is illustrative unless supplied; keep its source identity and selected connections readable.")
        else:
            lines.append("Keep the supplied parts within their actual source assembly and preserve their membership. Do not invent additional packages, duplicate the assembly, or repeat its inventory in peripheral bullet lists.")
    if visible["context_objects"]:
        context_rule = (". Keep these supplied supporting parts in their stated assembled spatial relationship, sharing the main subject's perspective; do not turn an attached board into a separate peripheral icon." if composition["geometry"] == "assembled_section" else ". Use one small representative neutral device silhouette or glyph per listed role, with unboxed text. These symbols express roles, not package quantities or a physical BOM. Do not expand a role into multiple application devices, colored cards or use-case scenes.")
        if visible["no_optional_text"]:
            context_rule = ". These names specify contextual objects, not printed labels. Keep a single source role coherent, without adding application devices for visual richness."
        lines.append("External context: " + "; ".join(item["label"] for item in visible["context_objects"]) + context_rule)
    if visible["interface_symbols"]:
        lines.append("Source interface families: " + "; ".join(item["source_label"] + " (" + item["label"] + ")" for item in visible["interface_symbols"]) + (". These are source-role constraints only; do not print protocol captions or lettering." if visible["no_optional_text"] else ". A concise protocol caption or small neutral interface glyph is sufficient.") + " A protocol does not authorize inventing cameras, robots, watches or other application products; depict those only if explicitly supplied as source roles. Actual connector shapes and pinouts are unspecified.")
    if visible["relationships"]:
        lines.append("Routing instructions, not a text panel or legend: draw only these selected source-backed interface links.")
        drawn_pairs = set()
        for relation in visible["relationships"]:
            directed = relation["directionality"] == "source-directed"
            pair = frozenset((relation["source"], relation["target"]))
            if not directed and pair in drawn_pairs:
                continue
            if not directed:
                drawn_pairs.add(pair)
            labels = ": " + "; ".join(relation["labels"][:3]) if directed and relation["labels"] else ""
            lines.append("- " + relation["source_label"] + (" -> " if directed else " ~ ") + relation["target_label"] + labels)
        lines.append(visible["relationship_portrayal"]["line_policy"] + " Use fine restrained lines, following explicit user path colors when given; otherwise use neutral contrast. Association links have no direction arrows; never add a reverse arrow for symmetry. Do not add luminous cables to every interface. Aggregate repeated links. Do not print link-kind words, a 'Key Relationships' section or an explanatory relation legend. Shared memory retains its common ownership.")
        context_targets = {}
        for relation in visible["relationships"]:
            start_external = relation["source"].startswith("context:")
            end_external = relation["target"].startswith("context:")
            if start_external == end_external:
                continue
            external_label = relation["source_label"] if start_external else relation["target_label"]
            internal_label = relation["target_label"] if start_external else relation["source_label"]
            member_ids = [pair[1 if start_external else 0] for pair in relation["source_node_pairs"]]
            member_labels = list(dict.fromkeys(nodes[node_id]["label"] for node_id in member_ids))
            target = internal_label + " at " + json.dumps(member_labels, ensure_ascii=False)
            context_targets.setdefault(external_label, []).append(target)
        for external_label, targets in context_targets.items():
            lines.append("Attach " + external_label + " only at the source-authorized internal role: " + "; ".join(dict.fromkeys(targets)) + ". Terminate its line at that role or named interface endpoint, not at a nearer central hub or unrelated region. In an intact-exterior view, align the attachment with that role's callout; this is an explanatory association, not a measured physical position.")
    if visible["no_optional_text"]:
        lines.append("The user excludes optional text: omit optional headings, legends and copy; any required verbatim text remains governed by the explicit requirements.")
    if visible["required_verbatim_labels"]:
        lines.append("Required exact text: " + json.dumps(visible["required_verbatim_labels"], ensure_ascii=False))
    if brief["appearance"]["known"]:
        lines.append("Direct user physical input, supplied but not independently verified: " + "; ".join(item["statement"] for item in brief["appearance"]["known"]))
    lines.extend(["User art direction takes precedence over defaults. Complete original intent and latest visual revision: " + json.dumps(brief["user_intent"], ensure_ascii=False),
                  "Keep explicit labels, logical ownership, quantities and source relationships. Functional overlays are not proof of physical dies, chiplets or HBM stacks. Exterior and context geometry remain illustrative. Avoid fabricated branding, measured specifications, ornamental circuit wallpaper, unrelated application props and cluttered copy.",
                  "The text brief is sufficient. " + brief["composition_guide"]["instruction"],
                  "Return one coherent finished image. The full engineering ledger remains in the brief and precise technical companions; do not force every secondary source signal onto this image."])
    return "\n".join(lines)


def workflow(brief, spec):
    """Complete image first; edit only when the user requests a staged revision."""
    complete = _prompt(brief, spec)
    staged = brief["explanation_plan"]["workflow"] == "optional_edit"
    steps = [{"id": "complete", "name": "生成完整画面", "operation": "generate", "prompt": complete, "input_role": None}]
    if staged:
        refinement = "\n".join([
            "Edit Image 1, the actual generated product image. Image 1 is the edit target; a composition guide is never the edit target.",
            "Preserve the approved visual identity, coherent camera/material/light system and all valid source-backed structure. Refine only the requested visual details, typography or explanation. A functional overlay and selected interface links may remain or improve under this explanatory treatment.",
            "Use neutral typography with strong contrast against the actual background, clear hierarchy and enough whitespace. Any new arrows retain listed source endpoints and direction; any context symbols explain source roles rather than assert a physical BOM.",
            "Target explanation, including the selected functional groups and relationships:\n" + complete,
            "Visual feedback cannot establish new physical or engineering facts. Correct contradictions from the source brief; preserve background transparency where requested. Return one finished image."])
        steps.append({"id": "refine", "name": "按反馈精修", "operation": "edit", "prompt": refinement,
                      "input_role": "edit_target", "input_from": "complete", "optional": True})
    return {"mode": "staged" if staged else "single_pass", "recommended": staged,
            "reason": "A staged refinement was explicitly requested." if staged else "The functions, context and visual treatment form one complete illustration; a separate empty-shell pass is unnecessary.",
            "steps": steps, "actual_image_review_required": True}


def compile_figure(figure, spec, settings, description="", palette=None, required_labels=(), visual_feedback=""):
    brief = build(spec, figure, settings, description, palette, required_labels, visual_feedback)
    brief["workflow"] = workflow(brief, spec)
    figure["render_brief"] = brief
    figure["generation_steps"] = brief["workflow"]["steps"]
    visible = brief["visible_content"]
    figure["render_contract"] = {"version": VERSION, "representation": brief["representation"],
                                 "explanatory_mode": brief["explanation_plan"]["mode"],
                                 "source_hash": brief["source_hash"], "source_ledger_complete": True,
                                 "appearance_status": "illustrative_unverified", "actual_image_status": "not_reviewed",
                                 "layout_authority": "art_direction", "composition_reference_optional": True,
                                 "known_physical_statement_count": len(brief["appearance"]["known"]),
                                 "source_node_count": len(spec["nodes"]), "source_edge_count": len(spec["edges"]),
                                 "visible_source_node_ids": [node_id for item in visible["regions"] + visible["context_objects"] for node_id in item["source_node_ids"]],
                                 "visible_source_edge_indices": [index for relation in visible["relationships"] for index in relation["source_edge_indices"]],
                                 "disclosure": visible["disclosure"]}
    figure["layout_strategy"] = "art-directed-render"
    figure["requires_layout_guide"] = False
    figure["requires_composition_guide"] = True
    figure["composition_guide_optional"] = True
    return brief["workflow"]["steps"][0]["prompt"]


def input_roles(figure):
    return [{"image_index": 1, "role": "composition_reference", "source": "composition-guide", "optional": True,
             "instruction": figure["render_brief"]["composition_guide"]["instruction"],
             "technical_revision": "For a source contradiction regenerate from the clean source brief, never preserve invented physical details from a failed bitmap."}]


def caption(figure, spec):
    brief = figure["render_brief"]
    groups = {group["id"]: group["label"] for group in spec["groups"]}
    nodes = {node["id"]: node for node in spec["nodes"]}
    lines = [spec["title"], "Representation: " + brief["representation"], "Explanation: " + brief["explanation_plan"]["mode"], spec.get("summary", ""),
             "Visible explanatory scope:", *brief["explanation_plan"]["visible_summary"],
             "Appearance disclosure:", *brief["appearance"]["illustrative_assumptions"],
             "Engineering inventory retained in the source; these names are not physical placement claims:"]
    for node in spec["nodes"]:
        lines.append(node["label"] + (" belongs to " + groups[node["group"]] if node["group"] else "")
                     + (": " + node["detail"] if node.get("detail") else "") + " [" + node.get("origin", "given") + "]")
    lines.append("All source relations retained; selected links are explanatory and do not assert measured physical wiring:")
    for edge in spec["edges"]:
        lines.append(nodes[edge["source"]]["label"] + " -> " + nodes[edge["target"]]["label"]
                     + (": " + edge["label"] if edge.get("label") else "") + " [" + edge["kind"] + "] [" + edge.get("origin", "given") + "]")
    lines.extend(spec.get("annotations", []))
    lines.extend(spec.get("assumptions", []))
    return "\n".join(line for line in lines if line)
