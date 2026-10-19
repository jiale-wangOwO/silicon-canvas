"""Generation service shared by the web server and local MCP."""
from typing import Any

from . import provider


class GenerationError(Exception):
    pass


def generate_result(payload: dict[str, Any], engine) -> dict[str, Any]:
    messages, context = engine.prepare_request(payload)
    completion = provider.complete(messages)
    completions = [completion]
    repaired = False
    try:
        result = engine.finish_request(completion["data"], context)
    except ValueError as error:
        repair_messages = engine.prepare_repair(messages, completion["data"], context, error)
        completion = provider.complete(repair_messages)
        completions.append(completion)
        try:
            result = engine.finish_request(completion["data"], context)
        except ValueError:
            raise GenerationError("这次未能整理成可绘制方案，请重试。") from None
        repaired = True
    usage: dict[str, int] = {}
    for item in completions:
        reported = item.get("usage", {})
        if not isinstance(reported, dict):
            continue
        for key in ("prompt_tokens", "completion_tokens", "total_tokens", "prompt_cache_hit_tokens", "prompt_cache_miss_tokens"):
            value = reported.get(key)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                usage[key] = usage.get(key, 0) + value
    result["usage"] = usage
    result["model"] = completion["model"]
    if repaired:
        result["repaired"] = True
    return result
