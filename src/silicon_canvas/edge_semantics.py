"""Visual stroke semantics derived from the immutable relationship ledger."""
import re

_PAYLOAD = re.compile(r"return(?:ed|ing)?\s+(?:read\s+)?(?:data|payload)|data\s+return|read\s+data|返回数据|回传数据|数据返回|读数据返回|返回负载", re.I)
_CONTROL = re.compile(r"\b(?:ready|grant|done|flush|recover|recovery|completion|status|ack)\b|就绪|授权|完成状态|恢复|清空|状态响应", re.I)


def stroke(edge, spec=None):
    kind = edge.get("kind", "relation")
    if kind not in {"control", "clock", "feedback"}:
        return "solid"
    if kind != "feedback":
        return "dashed"
    members = edge.get("members", [])
    sources = [spec["edges"][i] for i in members] if spec is not None and members else [edge]
    for original in sources:
        label = original.get("label", "")
        meaning = " ".join(str(original.get(key, "")) for key in ["label", "evidence", "rationale"])
        if _CONTROL.search(label) or not _PAYLOAD.search(meaning):
            return "dashed"
    return "solid"


def annotate(figure, spec):
    for edge in figure.get("macro_edges", []):
        edge["stroke_style"] = stroke(edge, spec)
    for edge in figure.get("structure_layout", {}).get("projected_links", []):
        edge["stroke_style"] = stroke(edge, spec)
