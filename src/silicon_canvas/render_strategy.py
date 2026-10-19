"""Choose an image subject and shot before decorating its material surface.

These are editorial decisions over the canonical source, never new hardware.
The source ledger, not a product-vendor reference, owns counts and membership.
"""
from __future__ import annotations

import re
from . import scene_profiles


_OBJECTS = [
    ("rack", r"\bracks?\b|机架|机柜"),
    ("server", r"\bservers?\b|服务器|整机"),
    ("board", r"\bPCB\b|(?:accelerator|GPU)\s*(?:cards?|boards?)|电路板|开发板|板卡|加速卡|显卡"),
    ("package", r"\bpackage\b|封装"),
    ("wafer", r"\bwafer\b|晶圆"),
    ("die", r"bare\s*die|exposed\s*die|裸片"),
]
_DEVICE = re.compile(r"\b(?:server|rack|switch|appliance|(?:inference|compute)\s+node|accelerator\s+(?:card|board))\b|服务器|交换(?:机|节点)|推理节点|计算节点|板卡|加速卡", re.I)
_CHIP = r"\b(?:SoC|chip|processor|silicon)\b|芯片|处理器"


def _positive(text, pattern):
    return scene_profiles.visual_cue(text, pattern)[0]


def _style_reference(text, match):
    """A source of visual style does not become the depicted whole object."""
    suffix = text[match.end():]
    prefix = text[:match.start()]
    return bool(
        re.match(r"(?:[ -]+[A-Za-z]+){0,4}[ -]+style\b", suffix, re.I)
        or re.match(r"[^。；;，,\n]{0,12}(?:风格|画风|样式)", suffix)
        or re.search(r"(?:style\s+of|inspired\s+by)\s+(?:an?\s+|the\s+)?$", prefix, re.I)
    )


def _whole_package_owner(text, spec):
    """Resolve a stated containment relation using actual source ownership.

    This is a whole-versus-part decision, not a new package inference. An
    explicit close-up/only-part view remains free to depict the contained die.
    """
    package = dict(_OBJECTS)["package"]
    if not _positive(text, package):
        return False
    containment = (r"\b(?:inside|within)\b[^.;。；\n]{0,32}\bpackage\b|"
                   r"\bpackage\b\s*(?:(?:that|which)\s+)?(?:contains?|containing|with|housing|enclosing)\b|"
                   r"封装(?:内|里|包含|容纳)|(?:位于|放在)[^。；\n]{0,16}封装")
    if not _positive(text, containment):
        return False
    groups = {group["id"]: group for group in spec["groups"]}
    owners = {gid for gid, group in groups.items()
              if re.search(package, group["label"] + " " + group.get("evidence", ""), re.I)}
    for node in spec["nodes"]:
        gid = node.get("group", "")
        while gid:
            if gid in owners:
                return True
            gid = groups.get(gid, {}).get("parent", "")
    return False


def _explicit_die_focus(text):
    die = dict(_OBJECTS)["die"]
    return _positive(text,
        r"(?:\b(?:only|just)\b\s+(?:(?:show|render|depict|the|a)\s+){0,3}|"
        r"\bclose[ -]?up\s+(?:of\s+)?(?:the\s+|a\s+)?|"
        r"\bfocus\s+on\s+(?:the\s+|a\s+)?)" + "(?:" + die + ")"
        r"|(?:" + die + r")\s*(?:hero\b|close[ -]?up\b|的?特写)"
        r"|(?:只画|仅画|只展示|仅展示|特写|聚焦)[^。；，\n]{0,8}裸片")


def subject_plan(text, spec):
    """Prefer the requested whole object to nouns naming its contained parts."""
    # The opening sentence normally names the asset. A later list of dies,
    # modules or connectors must not replace that whole object with a part.
    opening = re.split(r"[。.!?！？\n]", text, maxsplit=1)[0]
    matches = []
    for name, pattern in _OBJECTS:
        match = re.search(pattern, opening, re.I)
        if match and _positive(opening, pattern) and not _style_reference(opening, match):
            matches.append((match.start(), name))
    focus = min(matches)[1] if matches else None
    if _explicit_die_focus(opening):
        focus = "die"
    elif focus in {None, "die", "package"} and _whole_package_owner(opening, spec):
        focus = "package"
    node_text = {n["id"]: n["label"] for n in spec["nodes"]}
    device_ids = [node_id for node_id, label in node_text.items() if _DEVICE.search(label)]
    system_cue = _positive(text, r"\bsystem\b|\bplatform\b|系统|平台|整机|多(?:块|张|个)|四块|四个")
    # A chip has many logical resources too. Only source-named device roles
    # establish a multi-object system, not a graph's node count alone.
    multi_device = system_cue and len(device_ids) >= 2
    chip_matches = [match for match in re.finditer(_CHIP, opening, re.I)
                    if not _style_reference(opening, match)]
    chip_subject = bool(chip_matches) and _positive(opening, _CHIP)
    if focus is None and not chip_subject and multi_device:
        focus = "system"
    if focus is None and not chip_subject:
        for name, pattern in _OBJECTS:
            if _positive(text, pattern):
                focus = name
                break
    # Several explicitly requested boards, rather than a solitary board.
    if focus == "board" and _positive(text, r"(?:多|四|两|三|\d+)\s*(?:块|张)\s*(?:GPU\s*)?(?:加速卡|板卡|显卡)|(?:multiple|four|two|three|\d+)\s+(?:GPU\s*)?(?:cards?|boards?)"):
        focus = "system"
    kind = {"rack":"system_assembly_concept", "server":"system_assembly_concept",
            "system":"system_assembly_concept", "board":"board_concept",
            "package":"generic_package_concept", "wafer":"wafer_concept",
            "die":"bare_die_concept"}.get(focus, "generic_package_concept")
    physical_parts = [n["id"] for n in spec["nodes"] if re.search(r"\b(?:die|chiplet|package|substrate|lid|interposer|tray|chassis)\b|裸片|封装|基板|散热盖|中介层|托盘|机箱", n["label"], re.I)]
    if focus == "package" and physical_parts:
        kind = "package_assembly_concept"
    instruction = {
        "rack":"the source-described rack-scale system, with a recognizable vertical enclosure and readable front rhythm; it is not a chip package enlarged to rack size",
        "server":"the source-described complete server or system chassis, with subordinate source-backed modules; preserve the whole system scale rather than replacing it by one semiconductor package",
        "system":"a coherent system-scale ensemble of the supplied peer devices and shared resources. Use restrained dimensional role objects when exterior geometry is unknown. Never place these separate system nodes on one chip base or turn them into dies. Keep the selected source topology visible",
        "board":"the supplied board or accelerator card as a complete product, with enough top face to recognize its source-backed major parts. A few unlabeled generic passive components, fasteners and surface details may support a believable concept appearance; they are illustrative finish, not verified circuitry, part counts or a measured layout. Do not invent additional major compute or memory objects, interface families, product identifiers or layout parameters",
        "package":"one complete chip package as the main subject; contained dies and functional modules are subordinate parts, not alternate whole-product subjects",
        "wafer":"an illustrative semiconductor wafer, with its circular silhouette and surface reflectance; do not invent wafer size, process, die yield or manufacturing claims",
        "die":"the requested bare silicon die as the whole subject; surface pattern may be abstract texture, never proof of the logical functions' physical floorplan",
    }.get(focus, "one coherent generic chip package exterior, standing for the supplied complete product without asserting how many internal dies it contains")
    return {"kind":kind,"scale":focus or "chip", "instruction":instruction,
            "basis":"requested whole-object wording and source-named device roles; contained component mentions do not select the whole subject",
            "source_device_node_ids":device_ids,"source_physical_part_ids":physical_parts,
            "source_ownership":[{"id":g["id"],"label":g["label"],"parent":g.get("parent", ""),
                                  "members":[n["id"] for n in spec["nodes"] if n.get("group")==g["id"]]}
                                 for g in spec["groups"]]}


def shot_direction(plan, mode, text):
    """A small shot grammar, not a palette-swapped universal chip template."""
    scale = plan["scale"]
    systems = scale in {"rack", "server", "system"}
    camera = {
        "rack":"A near-frontal, slightly offset product camera with corrected verticals. Reveal a narrow side face for depth while preserving the rack's front rhythm; no overhead view or miniature-chip presentation.",
        "server":"A restrained three-quarter chassis camera, elevated only enough to show the source-backed serviceable modules. Use a long lens and straight structural edges; do not lift covers or explode trays unless requested.",
        "system":"An elevated three-quarter system view with a shared horizon and consistent scale. Arrange equivalent devices as peers around the supplied shared hub, keeping physical silhouettes distinct and the principal links traceable.",
        "board":"A moderately elevated oblique product camera that exposes the board plane and its major source-backed parts. Use a readable diagonal silhouette and controlled perspective, not a front-on sliver.",
        "wafer":"A controlled shallow three-quarter view that makes the circular wafer silhouette and restrained surface reflectance readable, without a sci-fi landscape.",
        "die":"A close, moderately elevated product camera that reveals the die face and a believable edge. Let selective reflectance carry surface detail instead of adding glowing circuit wallpaper.",
    }.get(scale, "A close three-quarter product camera with a long lens, a decisive diagonal silhouette and visible edge thickness. Keep one face dominant and avoid wide-angle distortion.")
    camera_explicit = _positive(text, r"camera|angle|perspective|isometric|overhead|top[ -]?down|镜头|视角|相机|俯视|顶视|等距|轴测")
    # Exclusions also count as explicit art direction.
    camera_explicit = camera_explicit or bool(re.search(r"(?:不要|不用|避免|no|without).{0,12}(?:俯视|等距|top.down|isometric)", text,re.I))
    composition = ("Compose one legible system ensemble using the actual source objects. Give the shared hub a clear position, preserve equivalent peers and route links in open space. Group membership is conveyed by proximity and a concise heading, not a chip slab or arbitrary mechanical enclosure." if scale == "system" else
                   "Let the complete rack's vertical silhouette organize the frame. Preserve front detail with selective edge light, use restrained staging and clear separation from its background. Reserve copy space only when requested, and avoid cropping away the identifying structure." if scale == "rack" else
                   "Use the complete source-described product as the single visual anchor. Give its silhouette deliberate scale, separate foreground and background tonally, and let visible geometry do the explanation. Additional objects are subordinate only when their source role is actually secondary.")
    return {"camera":None if camera_explicit else camera,
            "composition":composition,
            "lighting":"Use broad controlled studio illumination and one selective edge highlight. Preserve readable dark surfaces rather than crushing them to black. Separate metal, ceramic and board finishes by roughness and restrained reflections; contact shadows establish assembly. Avoid a halo on every edge, glowing rims on every module, heavy bloom or a mirror-floor spectacle.",
            "materials":("Use credible matte chassis, board and module finishes at system scale, with restrained variation in roughness. Do not cover system devices in die texture or gold package pins." if systems else
                         "Use a small coherent material family: quiet ceramic or silicon, restrained brushed/satin metal where appropriate, and believable edge thickness. Material contrast reveals form; avoid gold trim, microcircuit wallpaper and gratuitous beveled label slabs."),
            "color":"Build contrast from material value and one restrained accent family. Equivalent objects retain the same finish and accent. Reserve a second accent for a source-backed distinction or one emphasized path, not a different bright color for every logical module. Graphic diagram palettes do not paint all physical surfaces.",
            "typography":"Use only source-authorized labels that help this view. Prefer short labels beside the actual object with quiet unheaded leaders, or a few discrete direct labels; choose one treatment per object. Do not repeat the same inventory on surfaces and in perimeter bullet lists. No invented applications, marketing subtitle, specifications, labels or decorative disclosure badge.",
            "system_scale":systems,"reference_principle":"subject silhouette, scale-appropriate camera, coherent materials and lighting, and sparse task-specific annotation"}
