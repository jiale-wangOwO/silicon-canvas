"""Small, private-by-default DeepSeek client using only the Python standard library."""
from __future__ import annotations

import http.client
import json
import os
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-flash"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class ProviderError(Exception):
    """A safe, user-facing provider failure. Never includes upstream response text."""


@dataclass(frozen=True)
class Settings:
    api_key: str = field(repr=False)
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    key_source: str = "未配置"
    max_tokens: int = 12000


def _read_dotenv(path: Path) -> dict[str, str]:
    """Read plain KEY=value entries without executing or interpolating anything."""
    try:
        content = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError):
        return {}
    result: dict[str, str] = {}
    allowed = {"DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL", "DEEPSEEK_MAX_TOKENS"}
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[7:].strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name, value = name.strip(), value.strip()
        if name not in allowed:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        result[name] = value
    return result


def _windows_user_environment(name: str) -> str:
    if os.name != "nt":
        return ""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            value, value_type = winreg.QueryValueEx(key, name)
        if value_type in (winreg.REG_SZ, winreg.REG_EXPAND_SZ) and isinstance(value, str):
            return value.strip()
    except (OSError, ImportError):
        pass
    return ""


def _validate_base_url(value: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(value)
        port = parsed.port  # Validate malformed port numbers, even when unused.
    except ValueError:
        raise ProviderError("DEEPSEEK_BASE_URL 格式不正确，请检查本地配置。") from None
    if (
        not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or any(character.isspace() for character in value)
        or "\\" in value
        or (port is not None and not 1 <= port <= 65535)
    ):
        raise ProviderError("DEEPSEEK_BASE_URL 格式不正确，请检查本地配置。")
    local = parsed.hostname.lower() in {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme != "https" and not (parsed.scheme == "http" and local):
        raise ProviderError("API 地址必须使用 HTTPS；仅本机调试地址可使用 HTTP。")
    return value.rstrip("/")


def load_settings(project_dir: Path | None = None) -> Settings:
    dotenv = _read_dotenv((project_dir or PROJECT_DIR) / ".env")

    def pick(name: str, default: str = "") -> tuple[str, str]:
        for value, source in (
            (os.environ.get(name, "").strip(), "进程环境变量"),
            (dotenv.get(name, "").strip(), "项目 .env"),
        ):
            if value:
                return value, source
        windows_value = _windows_user_environment(name)
        if windows_value:
            return windows_value, "Windows 用户环境变量"
        return default, "未配置"

    api_key, source = pick("DEEPSEEK_API_KEY")
    base_url, _ = pick("DEEPSEEK_BASE_URL", DEFAULT_BASE_URL)
    model, _ = pick("DEEPSEEK_MODEL", DEFAULT_MODEL)
    token_text, _ = pick("DEEPSEEK_MAX_TOKENS", "12000")
    if not token_text.isdigit() or not 1024 <= int(token_text) <= 32768:
        raise ProviderError("DEEPSEEK_MAX_TOKENS 应为 1024 到 32768 之间的整数。")
    if len(model) > 150 or any(character.isspace() for character in model):
        raise ProviderError("DEEPSEEK_MODEL 格式不正确，请检查本地配置。")
    if "\r" in api_key or "\n" in api_key:
        raise ProviderError("API Key 配置格式不正确，请检查是否包含换行。")
    return Settings(api_key, _validate_base_url(base_url), model, source, int(token_text))


def status() -> dict[str, Any]:
    settings = load_settings()
    return {
        "configured": bool(settings.api_key),
        "model": settings.model,
        "base_url": settings.base_url,
        "key_source": settings.key_source,
    }


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _safe_http_error(code: int) -> str:
    if code in (301, 302, 303, 307, 308):
        return "API 地址发生重定向，已停止请求以保护密钥。请配置最终 HTTPS 地址。"
    if code in (401, 403):
        return "API 身份验证失败或无访问权限，请检查本地 DEEPSEEK_API_KEY。"
    if code == 402:
        return "DeepSeek 账户余额不足，请充值后重试。"
    if code == 429:
        return "DeepSeek 请求过于频繁或配额受限，请稍后重试。"
    if code == 404:
        return "API 地址或模型不存在，请检查 DEEPSEEK_BASE_URL 和 DEEPSEEK_MODEL。"
    if code == 400 or code == 422:
        return "上游拒绝了请求，请检查模型是否支持 JSON 输出和当前请求参数。"
    if code >= 500:
        return "DeepSeek 服务暂时不可用，请稍后重试。"
    return "API 请求未成功，请检查服务配置后重试。"


def complete(messages: list[dict[str, str]]) -> dict[str, Any]:
    settings = load_settings()
    if not settings.api_key:
        raise ProviderError("尚未配置 DeepSeek API Key。请在 MCP 宿主或本机进程环境设置 DEEPSEEK_API_KEY。")
    payload = {
            "model": settings.model,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": settings.max_tokens,
            "response_format": {"type": "json_object"},
            "stream": False,
        }
    # Vendor-specific options must not leak into a configured compatible backend.
    if urllib.parse.urlsplit(settings.base_url).hostname == "api.deepseek.com":
        payload["thinking"] = {"type": "disabled"}
    body = json.dumps(
        payload,
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        settings.base_url + "/chat/completions",
        data=body,
        headers={
            "Authorization": "Bearer " + settings.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "SiliconCanvas/1.0",
        },
        method="POST",
    )
    opener = urllib.request.build_opener(
        _NoRedirect(), urllib.request.HTTPSHandler(context=ssl.create_default_context())
    )
    try:
        with opener.open(request, timeout=120) as response:
            if response.status != 200:
                raise ProviderError(_safe_http_error(response.status))
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        code = exc.code
        exc.close()
        raise ProviderError(_safe_http_error(code)) from None
    except (TimeoutError, socket.timeout):
        raise ProviderError("API 请求超时（120 秒），请稍后重试；已发出的请求可能仍会产生费用。") from None
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, (TimeoutError, socket.timeout)):
            raise ProviderError("API 请求超时（120 秒），请稍后重试；已发出的请求可能仍会产生费用。") from None
        raise ProviderError("无法连接 API，请检查网络、代理或 HTTPS 证书配置。") from None
    except http.client.HTTPException:
        raise ProviderError("上游连接中断或响应不完整，请稍后重试。") from None
    except (OSError, ValueError, UnicodeError):
        raise ProviderError("API 请求失败，请检查网络和本地配置。") from None
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ProviderError("上游返回内容过大，请缩短描述后重试。")
    try:
        envelope = json.loads(raw, parse_constant=_reject_json_constant)
        if not isinstance(envelope, dict):
            raise ValueError()
        choice = envelope["choices"][0]
        if choice.get("finish_reason") == "length":
            raise ProviderError("结构输出达到 token 上限。请提高 DEEPSEEK_MAX_TOKENS 后重试；完整设计不应为此删掉模块。")
        if choice.get("finish_reason") not in (None, "stop"):
            raise ProviderError("模型未能完成本次结构化输出，请调整描述后重试。")
        content = choice["message"]["content"]
        if not isinstance(content, str) or not content.strip():
            raise ValueError()
        data = json.loads(content, parse_constant=_reject_json_constant)
        if not isinstance(data, dict) or not data:
            raise ValueError()
    except (KeyError, IndexError, TypeError, ValueError, AttributeError, UnicodeError, RecursionError):
        raise ProviderError("上游未返回有效的 JSON 图规格，请重新生成；若持续出现，请检查模型配置。") from None
    usage = envelope.get("usage", {})
    if not isinstance(usage, dict):
        usage = {}
    usage = {
        name: value
        for name, value in usage.items()
        if name in {"prompt_tokens", "completion_tokens", "total_tokens", "prompt_cache_hit_tokens", "prompt_cache_miss_tokens"}
        and isinstance(value, int)
        and not isinstance(value, bool)
        and value >= 0
    }
    return {"data": data, "usage": usage, "model": settings.model}


def _reject_json_constant(value: str):
    raise ValueError("Non-standard JSON number")
