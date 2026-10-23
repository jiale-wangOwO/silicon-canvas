"""A shared graphic language; semantic grammar decides what a color means.

This is appearance policy, not topology or an aesthetic score. Geometry and
technical notation remain owned by the selected figure plan.
"""
from . import visual_style


VERSION = "VIS1"


def build(settings, family="engineering"):
    colors = visual_style.palette(settings.get("style", "paper"))
    if family == "algorithm":
        fills = {"tensor": colors["primary"], "operator": colors["secondary"],
                 "state": colors["background"]}
    else:
        fills = {role: visual_style.role_fill(kind, colors) for role, kind in
                 [("compute", "compute"), ("storage", "memory"),
                  ("control/state", "state"), ("interface", "io")]}
    character = {
        "paper": "Light role fills and quiet boundaries; structure and readable names carry the hierarchy.",
        "blueprint": "Precise boundary and attachment definition; restrained navy linework on white, without a decorative grid.",
        "signal": "Emphasize the supplied main journey by alignment and continuity; secondary relationships remain lighter, never turn every edge into a thick arrow.",
        "monochrome": "Neutral grayscale only. Distinguish roles by shape, grouping and line convention, without colored accents.",
    }
    return {"version": VERSION, "family": family, "style": settings.get("style", "paper"),
            "palette": colors, "role_fills": fills,
            "character": character.get(settings.get("style"), character["paper"]),
            "typography": "Neutral sans-serif: medium object names, regular signals/conditions, subdued ownership headings. Typeset mathematics properly. No all-bold text or dark title banners.",
            "hierarchy": "Structure leads; role fills support it, unfilled containers recede. Align peers; reserve whitespace for branches and labels, not padded cards.",
            "surface": "Solid fills, crisp narrow strokes, small arrowheads. No gradients, texture, glow, shadows or bevels. Tensor shape cues may express supplied dimensions.",
            "precedence": "Explicit user appearance requests override preset defaults; they never change the selected technical scope, ownership, quantities or directed endpoints."}


def describe(contract):
    colors = contract["palette"]
    fills = "; ".join(role + " " + value for role, value in contract["role_fills"].items())
    return "\n".join([
        "Graphic language: " + contract["character"],
        "Palette: background " + colors["background"] + "; ink " + colors["ink"]
        + "; object outline " + visual_style.boundary_color(colors, strong=True)
        + "; quiet ownership boundary " + visual_style.boundary_color(colors) + ".",
        "Semantic fills: " + fills + ". Apply each role consistently, not a separate hue per object. Meaning must survive grayscale.",
        "Typography: " + contract["typography"],
        "Visual hierarchy: " + contract["hierarchy"],
        "Surface: " + contract["surface"],
        contract["precedence"],
    ])


def user_intent(description, notes):
    """Retain free-form visual requests without pretending to parse all language.

    The selected source ledger still owns technical content. The original user
    description is context, not permission to expand a selected view.
    """
    parts = []
    if description.strip():
        parts.append("Original user brief (context, not additional objects to draw): " + description.strip())
    if notes.strip() and notes.strip() != description.strip():
        parts.append("User presentation requests: " + notes.strip())
    if not parts:
        return ""
    return "\n".join(["USER VISUAL INTENT — apply explicit appearance requests before preset defaults; the selected inventory and source facts below still govern technical content. Do not typeset this instruction block.", *parts])
