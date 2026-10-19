"""Opt-in visual choices from the existing semantic response, not another call.

Legacy callers keep their established defaults. New callers explicitly request
automatic style, detail and canvas; the same provider response selects finite
catalog values. Artwork language defaults to English independently of input
language. Saved resolved choices make local recompile deterministic.
"""
from __future__ import annotations

import copy

FIELDS = ("style", "density", "language", "aspect")
DEFAULTS = {"style": "paper", "density": "medium", "language": "en", "aspect": "auto"}
DETAIL_CHOICES = {
    "low": "Overview: principal functions, real ownership and main relationships; defer implementation mechanisms.",
    "medium": "Balanced explanation: useful subsystem context and the key mechanism needed to answer the reader's question.",
    "high": "Mechanism detail: exact supplied resources, paths, predicates, parameters and required labels in the selected scope; preserve all facts without inventing internals.",
}


def requested(settings):
    # Aspect=auto predates semantic option selection and already means an
    # adaptive canvas. Keep that old contract unless this request opts into the
    # new automatic visual fields.
    # Keep language in the saved-record vocabulary for historical projects,
    # but new automatic requests cannot infer artwork language from input prose.
    selected = [key for key in ("style", "density") if settings.get(key) == "auto"]
    if selected and settings.get("aspect") == "auto":
        selected.append("aspect")
    return selected


def schema(fields, choices):
    return {"type": "object", "properties": {key: {"enum": list(choices[key])} for key in fields},
            "required": list(fields), "additionalProperties": False}


def validate_selection(value, fields, choices):
    if not isinstance(value, dict):
        raise ValueError("visual_settings 必须是自动视觉选项对象。")
    if set(value) != set(fields):
        missing, extra = sorted(set(fields) - set(value)), sorted(set(value) - set(fields))
        detail = ("缺少 " + ", ".join(missing) if missing else "") + ("；多余 " + ", ".join(extra) if extra else "")
        raise ValueError("visual_settings 字段不匹配：" + detail + "。请只返回请求自动选择的字段。")
    for key, selected in value.items():
        if not isinstance(selected, str) or selected not in choices[key]:
            raise ValueError("visual_settings." + key + " 必须从允许选项中选择：" + ", ".join(choices[key]) + "。")
    return {key: value[key] for key in fields}


def saved_record(value, choices):
    """Read bounded portable selection metadata without trusting free fields."""
    if not isinstance(value, dict) or not isinstance(value.get("requested"), dict):
        raise ValueError("automatic_visual_settings 格式无效。")
    fields = [key for key in FIELDS if key in value["requested"]]
    if not fields or set(value["requested"]) != set(fields) or any(value["requested"][key] != "auto" for key in fields):
        raise ValueError("automatic_visual_settings.requested 只能包含已自动选择的视觉字段。")
    selection = validate_selection(value.get("selected"), fields, choices)
    method = value.get("method")
    if method not in {"semantic-response", "saved-selection", "compatibility-defaults"}:
        raise ValueError("automatic_visual_settings.method 无效。")
    return {"requested": {key: "auto" for key in fields}, "selected": selection, "method": method}


def resolve(settings, selection, fields, choices, method="semantic-response"):
    selected = validate_selection(selection, fields, choices)
    output = copy.deepcopy(settings)
    for key in fields:
        # A field is only selectable while the user's request remains auto.
        if output.get(key) == "auto":
            output[key] = selected[key]
    output["automatic_visual_settings"] = {"requested": {key: "auto" for key in fields},
                                            "selected": selected, "method": method}
    return output


def local_resolution(settings, choices):
    fields = requested(settings)
    if not fields:
        return settings
    saved = settings.get("automatic_visual_settings", {}).get("selected", {})
    selected = {key: saved.get(key, DEFAULTS[key]) for key in fields}
    method = "saved-selection" if all(key in saved for key in fields) else "compatibility-defaults"
    return resolve(settings, selected, fields, choices, method)
