"""JSON bridge for the browser Worker; no API transport or credential handling."""
from __future__ import annotations

import base64
import json
import copy
import hashlib
from collections import OrderedDict

from . import bundle, engine, layout_guide

MAX_REQUEST_BYTES = 4 * 1024 * 1024
_COMPILED = OrderedDict()


def _source_input(payload):
    return {"spec": payload.get("spec"), "settings": engine.normalize_settings(payload.get("settings", {})),
            "description": payload.get("description", ""), "feedback": payload.get("feedback", ""), "figure_id": payload.get("figure_id", "")}


def _key(payload):
    return hashlib.sha256(json.dumps(_source_input(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _compile(payload):
    """Keep only trusted compiler output in bounded Worker memory.

    Source, normalized settings and description form the key. Imported
    geometry, prompts and paths can never populate or replace this cache.
    A deep copy prevents UI mutations from poisoning later exports.
    """
    key = _key(payload)
    if key in _COMPILED:
        _COMPILED.move_to_end(key)
        return copy.deepcopy(_COMPILED[key])
    result = engine.compile_manual(_source_input(payload))
    for entry in {key, _key(result)}:
        _COMPILED[entry] = copy.deepcopy(result)
        _COMPILED.move_to_end(entry)
    while len(_COMPILED) > 8:
        _COMPILED.popitem(last=False)
    return copy.deepcopy(result)


def _figure(result, figure_id=""):
    figures = result.get("figures", [])
    if figure_id:
        for figure in figures:
            if figure.get("id") == figure_id:
                return figure
        raise ValueError("指定视图不存在。")
    if not figures:
        raise ValueError("没有可用视图。")
    return next((item for item in figures if item.get("primary")), figures[0])


def dispatch(action: str, payload: dict | None = None):
    """All compilation goes through the same core used by the MCP server."""
    payload = {} if payload is None else payload
    if not isinstance(payload, dict):
        raise ValueError("输入必须为 JSON 对象。")
    if len(json.dumps(payload, ensure_ascii=False).encode()) > MAX_REQUEST_BYTES:
        raise ValueError("项目过大，请拆分后再导入。")
    if action == "catalog":
        return engine.CATALOG
    if action == "prepare":
        messages, context = engine.prepare_request(payload)
        return {"messages": messages, "context": context}
    if action == "finish":
        return engine.finish_request(payload["data"], payload["context"])
    if action == "repair":
        return {"messages": engine.prepare_repair(payload["messages"], payload["data"], payload["context"], ValueError(str(payload.get("error", "结构无效"))[:1000]))}
    if action == "compile":
        return _compile(payload)
    if action in {"guide", "bundle", "review"}:
        # Discard imported geometry/paths. Recompile source or reuse only a
        # compiler-owned snapshot for the exact same source and settings.
        result = _compile(payload["result"])
        figure_id = payload.get("figure_id", "")
        figure = _figure(result, figure_id)
        if action == "review":
            return figure["review_task"]
        if action == "guide":
            data = layout_guide.render(result, figure)
            if not data:
                raise ValueError("此视图暂时没有合格底稿，请检查预检与限制。")
            framing = figure.get("representation") in {"product_render", "system_illustration"}
            return {"base64": base64.b64encode(data).decode("ascii"), "mime": "image/png", "filename": "composition-guide.png" if framing else "layout-guide.png", "role": "composition_reference" if framing else "target_structure", "optional": framing}
        data = bundle.build(result, figure_id)
        return {"base64": base64.b64encode(data).decode("ascii"), "mime": "application/zip", "filename": "silicon-canvas-generation-pack.zip"}
    raise ValueError("未知编译操作。")
