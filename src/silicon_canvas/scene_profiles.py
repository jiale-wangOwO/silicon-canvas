"""Reader-purpose contracts, independent of a model and of palette selection.

Scenes decide abstraction, reading order and graphic language.  The older color
presets remain valid project data; callers that omit ``scene`` keep their original
technical compilation behavior.
"""
from __future__ import annotations

import copy
import re

PROFILES = {
    "concept": {
        "id": "concept", "name": "产品概念", "subtitle": "商业展示 · BP · 方案介绍",
        "question": "What is the complete product or solution, and what are its major capabilities and interfaces?",
        "granularity": "whole-system functional regions; do not expand internal queues, ports or per-unit wiring",
        "visual_language": "a complete hero system silhouette, compact capability regions, generous separation and a few source-proven interfaces",
        "annex_policy": "the first image stands alone as a whole-system concept; exact source inventory and all implementation relations remain in captions and optional technical companions",
        "target_width_mm": 240, "body_pt": 11, "signal_pt": 9.5, "default_density": "low",
        "rules": [
            "Design a professional product-concept illustration for a business plan or product introduction. Give the whole solution one coherent silhouette and arrange a small number of real functional regions inside it; external resources are shown beside it only when their external ownership is established.",
            "A restrained chip or system outline, rounded functional zones and a stronger visual hierarchy are allowed. They are illustrative graphic language, never evidence of a measured physical floorplan, die area, packaging, fabricated chip photograph or physical placement.",
            "Use prominent concise region names, clear whitespace and only a few essential source-proven interface paths. Source clock, reset, issue queues, per-port wiring and secondary controls stay in the exact companion views. Do not enlarge a full wiring schematic and call it a concept image.",
            "Preserve supplied resource names, multiplicity and ownership. Do not invent performance benefits, use-case icons, speed numbers, package pins, brand logos, new arrows or decorative circuits. No neon, glass, metallic texture or futuristic poster lighting."
        ]
    },
    "system": {
        "id": "system", "name": "系统架构", "subtitle": "白皮书 · 产品架构 · 技术文档",
        "question": "How are the real subsystems, shared resources and external interfaces organized?",
        "granularity": "subsystem boundaries plus selected visible internal resources; retain logical hierarchy and shared/private ownership",
        "visual_language": "flat nested ownership diagram with compact internal resource inventory and aligned interface boundaries",
        "annex_policy": "lead with subsystem organization; expand a representative real owner only when needed; complete wiring is an optional exact companion",
        "target_width_mm": 160, "body_pt": 9, "signal_pt": 8.5, "default_density": "medium",
        "rules": [
            "Draw a technical product architecture or white-paper figure. Explain containment and subsystem interaction with compact nested ownership boundaries, aligned shared-resource bands and external interfaces on the perimeter.",
            "Show useful internal resource names inside their real owners. A repeated instance expansion refers to the same source hardware, never an extra unit. Keep equivalent instances aligned without inventing a count or assuming area equivalence.",
            "Use flat role-dependent hardware shapes: storage bars, compute rectangles and quiet interface cells. Normal-weight technical type, thin boundaries, minimal padding and small arrowheads. Avoid hero-chip ornament, oversized cards and presentation slogans.",
            "Show the main supplied inter-subsystem relationships; secondary internal operation belongs in companion figures. Proximity and containment are not a bus, physical floorplan or implicit coherence link."
        ]
    },
    "flow": {
        "id": "flow", "name": "数据流讲解", "subtitle": "工作原理 · 数据路径 · 阶段演示",
        "question": "Where does the input come from, what transforms it, and where do the outputs or returns go?",
        "granularity": "source, transfer or buffering, transformations and destinations along one explained lifecycle",
        "visual_language": "a source-led dependency progression with aligned branches, separate return lanes and compact supporting control",
        "annex_policy": "lead with the actual payload or dependency lifecycle; retain secondary control and complete source relationships in separate exact companions",
        "target_width_mm": 200, "body_pt": 10, "signal_pt": 9, "default_density": "medium",
        "rules": [
            "Explain the supplied data or dependency lifecycle in an orientation suited to its actual structure. Align independent producers, transport or buffers, computation and consumers; cyclic, multi-branch or owned-resource paths need appropriate return corridors and grouping rather than a compulsory linear row. The graphic is a process explanation, not a chip floorplan.",
            "Distinguish transformations from storage using shape and position, with spacious labeled connection corridors. Returning payload uses a separate continuous outer lane; supporting controls are secondary and remain technically correct.",
            "A restrained numbered stage treatment is permitted only for a genuinely specified operation order. Dependency does not imply a guaranteed serial schedule or one stage per clock. Keep exact tensor dimensions, predicates and mathematical merge operators.",
            "Use selective contrast to let the primary path be followed at a glance, while preserving source fan-in, fan-out, directions and identities. Do not add storytelling arrows, duplicate a DMA, or turn a control edge into payload traffic."
        ]
    },
    "detail": {
        "id": "detail", "name": "实现细节", "subtitle": "设计评审 · 微架构 · 精确行为",
        "question": "How do the specified resources, signals, conditions and return paths actually implement this design?",
        "granularity": "exact original resource and edge scope; no product-level folding in the primary view",
        "visual_language": "compact engineering schematic with role-shaped resources, exact endpoint attachments and explicit conditions",
        "annex_policy": "start with an exact selected technical scope; split large designs by real source ownership and retain every source relation",
        "target_width_mm": 160, "body_pt": 9, "signal_pt": 8.5, "default_density": "high",
        "rules": [
            "Produce an implementation-review figure with exact queues, registers, buffers, execution resources, states or interactions present in the source. Show a bounded technical scope at a legible document size; use separate scopes when the full design is too dense.",
            "Keep endpoint attachment, arrow direction, fan-out, parallel predicates, widths, conditions and feedback paths explicit. Do not collapse internals into capability tiles or hide technical details to imitate a product image.",
            "Use compact role-dependent engineering symbols, shallow storage bars, aligned ports, narrow solid data and finer dashed control strokes where the category permits them. Keep recovery and global control in clearly reserved corridors.",
            "Preserve the category's actual notation: decision diamonds for decisions, state nodes for states and a common time axis for timing. A behavioral figure must not inherit chip illustrations merely because its scene is technical."
        ]
    },
}

_CONCEPT = re.compile(r"\bbp\b|business\s*plan|commercial|executive\s*(?:system|presentation)|pitch|investor|marketing|product\s*(?:concept|launch)|商业|商务|路演|融资|概念|产品展示|产品介绍|方案介绍|发布会", re.I)
_OVERVIEW = re.compile(r"\boverview\b|whole\s*(?:system|core)|整体|总览|全局架构", re.I)
_DETAIL = re.compile(r"implementation|microarchitecture|exact\s*(?:signal|timing)|design\s*review|实现细节|微架构|设计评审|精确时序|端口接线|内部细节", re.I)
_FLOW = re.compile(r"data\s*flow|datapath|lifecycle|how\s*(?:it\s*)?works|数据流|数据路径|工作原理|流向|处理流程|流水", re.I)


_CLAUSE_BREAK = re.compile(r"[。！？!?;；\n，,]|\b(?:but|instead(?!\s+of))\b|但是|但(?!是)|而是", re.I)
_NEGATIVE_INTENT = re.compile(r"不要|不用|避免|不需要|无需|不能|别|禁止|不可|不是|并非|没有|不(?=展示|显示|揭示|画|加|保留|做|展开|扩展|呈现)|\b(?:without|avoid|never|no|not)\b|do\s*not|don't|instead\s+of|rather\s+than", re.I)
_REASSERT = re.compile(r"(?:展示|显示|揭示|保留|保持|改成|换成|使用|采用|要画)|\b(?:show|reveal|preserve|keep|use|make|change\s+to|switch\s+to|draw)\b", re.I)


def visual_cue(text, pattern):
    """Resolve affirmative and excluded cues locally, in the user's order.

    Negation belongs to the matched request, not every noun in its sentence.
    The final occurrence of one visual property wins within a request; callers
    arbitrate a later feedback message separately from the original request.
    This selects defaults only; the complete free-form intent remains available
    to generation and review, including constructions this parser cannot resolve.
    """
    matcher = re.compile(pattern, re.I) if isinstance(pattern, str) else pattern
    last = None
    for clause in _CLAUSE_BREAK.split(text or ""):
        for match in matcher.finditer(clause):
            prefix = clause[:match.start()]
            negative = list(_NEGATIVE_INTENT.finditer(prefix))
            negated = False
            if negative:
                latest = negative[-1]
                tail = prefix[latest.end():]
                # Keep the exclusion local to this phrase. An affirmative verb
                # starts another request unless that verb itself is negated.
                reassert = list(_REASSERT.finditer(tail))
                direct_negative_verb = bool(re.match(r"\s*(?:(?:show|reveal|preserve|keep|use|make|draw)\b|展示|显示|揭示|使用|采用|画)", tail, re.I))
                negated = len(tail) <= 72 and (not reassert or direct_negative_verb)
                if re.search(r"(?:hide|omit|remove|lose|隐藏|省略|去掉|删掉)\s*(?:the\s*)?$", tail, re.I):
                    # 'Do not hide internal regions' asks to retain regions.
                    negated = False
            # Negative rendering is an affirmative request for the flat medium;
            # it must not make a broad 'show ... no internal regions' pattern
            # affirmative. Only these known cue families own that reversal.
            if matcher is _FLAT:
                pass  # its own 'no rendering' phrase requests flat; prefix exclusions still apply
            elif matcher is not _HERO and _NEGATIVE_INTENT.search(match.group(0)):
                negated = True
            suffix = clause[match.end():]
            if re.match(r"\s*(?:(?:is|are|was|should\s+be)\s+)?(?:not\s+(?:wanted|needed|desired|required|allowed|the\s+goal)|不(?:要|需要|允许|用))", suffix, re.I):
                negated = True
            last = not negated
    return last is True, last is False


def _positive(text, pattern):
    return visual_cue(text, pattern)[0]


def resolve(settings, description="", spec=None):
    """Return the effective purpose, or None for an untouched legacy project."""
    if "scene" not in settings:
        return None
    requested = settings.get("scene", "auto")
    if requested not in {"auto", *PROFILES}:
        raise ValueError("不支持的 scene 选项。")
    text = description + "\n" + settings.get("notes", "")
    category = (spec or {}).get("category", settings.get("category", "auto"))
    if requested != "auto":
        actual, reason = requested, "用户指定用途"
    elif _positive(text, _CONCEPT):
        actual, reason = "concept", "输入要求商业或概念展示"
    elif _positive(text, _DETAIL) and not _positive(text, _OVERVIEW):
        actual, reason = "detail", "输入要求实现细节或设计评审"
    elif _positive(text, _FLOW):
        actual, reason = "flow", "输入要求解释数据或处理过程"
    elif _positive(text, _OVERVIEW):
        actual, reason = "system", "输入要求整体组织与主要关系"
    elif category in {"fsm", "timing", "microarchitecture"}:
        actual, reason = "detail", "内容的核心是精确资源、状态或时序"
    elif category in {"dataflow", "pipeline", "algorithm"}:
        actual, reason = "flow", "内容的核心是数据或行为过程"
    else:
        actual, reason = "system", "默认先解释系统层级和主要接口"
    profile = copy.deepcopy(PROFILES[actual])
    profile.update(requested=requested, selection_reason=reason,
                   category_adaptation="Preserve the original behavioral grammar; do not draw a chip enclosure." if category in {"algorithm", "fsm", "timing", "pipeline"} else "Use the reader-purpose projection while preserving source ownership and edge provenance.")
    return profile


def request_guidance(settings, description=""):
    profile = resolve(settings, description)
    if profile is None:
        return None
    return {key: profile[key] for key in ("id", "question", "granularity", "annex_policy", "category_adaptation")}


def catalog_entries():
    return [{key: item[key] for key in ("id", "name", "subtitle", "question", "granularity", "visual_language", "annex_policy")} for item in PROFILES.values()]


# Purpose and representation are independent axes. A product launch can use a
# physical-looking render, an explanatory illustration, or a precise diagram.
# Missing representation is an explicit compatibility boundary for old projects.
REPRESENTATIONS = {
    "product_render": {
        "id": "product_render", "name": "商业产品渲染", "subtitle": "材质 · 光照 · 镜头 · 产品主体",
        "visual_language": "an art-directed product image using materials, lighting and perspective, with explanatory context or functional overlays when the message needs them",
        "source_fact_policy": "Preserve source capabilities and relationships. A conceptual functional overlay may explain them without asserting measured die geometry or actual packaging.",
    },
    "system_illustration": {
        "id": "system_illustration", "name": "技术产品插画", "subtitle": "空间组织 · 原理说明 · 选择性标注",
        "visual_language": "a coherent dimensional technical illustration that explains the whole source system through selective cutaway, context and source-backed annotation",
        "source_fact_policy": "Illustrative perspective, sectioning and separation explain functional organization; they do not establish a measured floorplan, package stack or fabrication process.",
    },
    "diagram": {
        "id": "diagram", "name": "技术图解", "subtitle": "层级 · 数据关系 · 精确行为",
        "visual_language": "source-backed flat engineering notation with controlled ownership, labels and directed relationships",
        "source_fact_policy": "The selected technical view retains its original diagram grammar and exact endpoint meaning.",
    },
}
_RENDER = re.compile(r"\brender(?:ed|ing|s)?\b|\bphotoreal(?:istic)?\b|product\s*hero\b|studio\s*(?:shot|light)|commercial\s*(?:image|visual)|product\s*photograph|商业(?:产品)?渲染|产品渲染|渲染图|产品摄影|质感|材质|光照|摄影棚|透视产品|立体产品|三维|\b3d\b", re.I)
_ILLUSTRATION = re.compile(
    r"(?:(?:system|technical|product|spatial|dimensional|assembly)\s*){1,3}(?:(?:concept|demonstration|explanatory)\s*)?illustration|"
    r"dimensional\s*system|spatial\s*system|"
    r"(?:产品|技术|系统|空间|原理|装配|封装)(?:产品|技术|系统|概念|展示|原理|空间|装配|封装){0,3}(?:插图|插画)|"
    r"空间(?:系统)?(?:示意|插画)|系统[^。\n]{0,20}(?:空间|三维)", re.I)
_SECTION = re.compile(r"cutaway|cross[-\s]*section|sectioned\s*(?:package|assembly|chip)|剖视|剖面|剖切|局部切开|局部剖开", re.I)
_EXPLODED = re.compile(r"exploded\s*(?:view|assembly)|爆炸图|分解装配图", re.I)
_FLAT = re.compile(r"(?:不要|不用|不需要|无需|避免)\s*(?:商业)?(?:渲染|3d|三维|立体)|(?:no|without|avoid)\s*(?:3d|render|perspective)|纯(?:平面|框图|技术图)|flat\s*(?:diagram|schematic)|block\s*diagram", re.I)
_COMMERCIAL = re.compile(r"\bbp\b|business\s*(?:plan|presentation)|executive\s*(?:system|presentation|demonstration)|commercial|pitch|investor|marketing|product\s*(?:launch|hero|introduction)|商业|商务|路演|融资|产品展示|产品介绍|方案介绍|发布会", re.I)
_HERO = re.compile(r"\bhero\b|\bcover\b(?!\s*(?:all|each|every)\b)|\bposter\b|主视觉|封面|海报|只.*外观|无文字|不需要文字|不要文字|\bno\s*(?:text|labels?)\b", re.I)
_EXPLANATORY = re.compile(r"功能分区|内部架构|内部结构|逻辑剖视|功能覆盖|芯片.*分区|架构(?:渲染|展示)|function(?:al)?\s*(?:region|partition|overlay|cutaway)|capability\s*callouts|system\s*demonstration|architecture\s*explanation|解释.*(?:系统|关系|架构)|(?:讲解|展示|说明|突出).*(?:能力|子系统|互联|存储路径|连接|架构)", re.I)


def _positive_hero(text):
    # 'not just a cover' excludes an exterior-only interpretation even though
    # its nouns still occur. It does not exclude useful illustration generally.
    return _positive(text, _HERO) and not re.search(r"不要只|不只是|避免只|not\s*(?:just|only)[^.;。\n]{0,24}(?:cover|hero|poster)", text, re.I)


def resolve_representation(settings, description="", spec=None):
    requested = settings.get("representation", "legacy")
    if requested not in {"legacy", "auto", *REPRESENTATIONS}:
        raise ValueError("不支持的 representation 选项。")
    text = description + "\n" + settings.get("notes", "")
    category = (spec or {}).get("category", settings.get("category", "auto"))
    behavioral = category in {"algorithm", "fsm", "timing", "pipeline"}
    if requested == "legacy":
        actual, reason = "diagram", "已有项目未指定表现形式，保留原技术图解"
    elif requested != "auto":
        actual, reason = requested, "用户指定表现形式"
    elif _positive(text, _FLAT):
        actual, reason = "diagram", "输入明确要求平面技术图解"
    elif behavioral:
        actual, reason = "diagram", "状态、时序或算法以原始行为记法表达"
    elif _positive(text, _EXPLANATORY) and (_positive(text, _RENDER) or _positive(text, _COMMERCIAL)) and not _positive_hero(text):
        actual, reason = "system_illustration", "商业或渲染讲解需要可见的功能层次与主要关系"
    elif any(_positive(text, cue) for cue in (_ILLUSTRATION, _SECTION, _EXPLODED)):
        actual, reason = "system_illustration", "输入要求空间原理或技术产品插画"
    elif _positive(text, _COMMERCIAL) and not _positive(text, _RENDER) and not _positive_hero(text):
        actual, reason = "system_illustration", "产品或方案介绍默认解释系统；明确主视觉或材质镜头时再突出产品外观"
    elif _positive(text, _RENDER) or _positive(text, _COMMERCIAL) or _positive_hero(text):
        actual, reason = "product_render", "输入要求商业展示或立体产品渲染"
    else:
        # A concept is an explanatory scope, not a rendering medium. Logical
        # hierarchies and system concepts remain technical diagrams unless
        # positive commercial, spatial or material art direction requests a
        # different medium; palette and category do not supply that intent.
        actual, reason = "diagram", "输入主要说明工程结构或数据关系"
    # A material render cannot faithfully replace time axes, state transitions
    # or mathematical operations. Preserve that notation even if an old saved
    # project combines a render selection with a changed behavioral category.
    if behavioral and actual != "diagram":
        actual, reason = "diagram", "行为内容需要精确记法，产品渲染选择已适配为技术图解"
    profile = copy.deepcopy(REPRESENTATIONS[actual])
    profile.update(requested=requested, selection_reason=reason)
    return profile


def representation_entries():
    return [copy.deepcopy(profile) for profile in REPRESENTATIONS.values()]
