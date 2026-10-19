from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from silicon_canvas import provider


class FakeResponse:
    status = 200

    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self, limit):
        return self.body[:limit]


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.settings = provider.Settings("test-secret-not-real")

    def invoke(self, envelope):
        response = FakeResponse(json.dumps(envelope).encode())
        with patch.object(provider, "load_settings", return_value=self.settings), patch.object(provider.urllib.request, "build_opener") as opener:
            opener.return_value.open.return_value = response
            return provider.complete([{"role": "user", "content": "JSON"}])

    def test_environment_has_precedence_and_secrets_are_not_status(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            (path / ".env").write_text("DEEPSEEK_API_KEY=dotenv-test\nDEEPSEEK_MODEL=dotenv-model\n", encoding="utf-8")
            with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "environment-test", "DEEPSEEK_MODEL": "environment-model"}, clear=True), patch.object(provider, "_windows_user_environment", side_effect=lambda name: "registry-test" if name == "DEEPSEEK_API_KEY" else ""):
                settings = provider.load_settings(path)
                self.assertEqual(settings.api_key, "environment-test")
                self.assertEqual(settings.model, "environment-model")
                self.assertNotIn("environment-test", repr(settings))
                with patch.object(provider, "load_settings", return_value=settings):
                    public = provider.status()
                self.assertTrue(public["configured"])
                self.assertNotIn("environment-test", json.dumps(public))

    def test_dotenv_and_windows_fallback(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            (path / ".env").write_text('export DEEPSEEK_API_KEY="dotenv-test"\nOTHER=ignore\n', encoding="utf-8")
            with patch.dict(os.environ, {}, clear=True), patch.object(provider, "_windows_user_environment", side_effect=lambda name: "registry-test" if name == "DEEPSEEK_API_KEY" else ""):
                self.assertEqual(provider.load_settings(path).api_key, "dotenv-test")
                (path / ".env").unlink()
                self.assertEqual(provider.load_settings(path).api_key, "registry-test")

    def test_insecure_remote_and_credential_urls_rejected(self):
        for value in ("http://example.com", "https://key@example.com", "https://example.com?key=secret", "file:///tmp/test", "https://example.com:bad", "https://example.com:0", "https://example.com\\other"):
            with self.subTest(value=value), self.assertRaises(provider.ProviderError):
                provider._validate_base_url(value)
        self.assertEqual(provider._validate_base_url("https://api.deepseek.com/v1/"), "https://api.deepseek.com/v1")
        self.assertEqual(provider._validate_base_url("http://127.0.0.1:8099"), "http://127.0.0.1:8099")

    def test_request_parameters_and_success(self):
        response = FakeResponse(json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": '{"nodes": []}'}}], "usage": {"prompt_tokens": 22, "completion_tokens": 11, "extra": "test-secret-not-real"}}).encode())
        with patch.object(provider, "load_settings", return_value=self.settings), patch.object(provider.urllib.request, "build_opener") as opener:
            opener.return_value.open.return_value = response
            result = provider.complete([{"role": "user", "content": "JSON 架构"}])
            request = opener.return_value.open.call_args.args[0]
            payload = json.loads(request.data)
            self.assertEqual(payload["thinking"], {"type": "disabled"})
            self.assertEqual(payload["response_format"], {"type": "json_object"})
            self.assertEqual(payload["temperature"], 0.2)
            self.assertEqual(payload["max_tokens"], 12000)
            self.assertEqual(opener.return_value.open.call_args.kwargs["timeout"], 120)
            self.assertEqual(result["data"], {"nodes": []})
            self.assertEqual(result["usage"], {"prompt_tokens": 22, "completion_tokens": 11})
            self.assertEqual(result["model"], "deepseek-flash")

    def test_invalid_or_empty_structured_output(self):
        envelopes = [
            {},
            {"choices": []},
            {"choices": [{"message": {"content": ""}}]},
            {"choices": [{"message": {"content": "not-json"}}]},
            {"choices": [{"message": {"content": "{}"}}]},
            {"choices": [{"message": {"content": "[]"}}]},
            {"choices": [{"message": {"content": '{"invalid":NaN}'}}]},
            {"choices": [{"message": {"content": "{\"nodes\":[]}"}, "finish_reason": "length"}]},
        ]
        for envelope in envelopes:
            with self.subTest(envelope=envelope), self.assertRaises(provider.ProviderError):
                self.invoke(envelope)

    def test_compatible_backends_do_not_receive_deepseek_only_thinking_field(self):
        envelope = {"choices": [{"finish_reason": "stop", "message": {"content": '{"nodes": []}'}}]}
        for base_url in (
            "https://compatible.example/v1",
            "https://api.deepseek.com.compatible.example/v1",
            "http://127.0.0.1:8099/v1",
        ):
            with self.subTest(base_url=base_url):
                configured = provider.Settings("test-secret-not-real", base_url, "compatible-model", max_tokens=18000)
                with patch.object(provider, "load_settings", return_value=configured), patch.object(provider.urllib.request, "build_opener") as opener:
                    opener.return_value.open.return_value = FakeResponse(json.dumps(envelope).encode())
                    result = provider.complete([{"role": "user", "content": "JSON"}])
                    request = opener.return_value.open.call_args.args[0]
                    payload = json.loads(request.data)
                self.assertNotIn("thinking", payload)
                self.assertEqual(payload["max_tokens"], 18000)
                self.assertEqual(payload["model"], "compatible-model")
                self.assertEqual(payload["response_format"], {"type": "json_object"})
                self.assertEqual(request.full_url, base_url + "/chat/completions")
                self.assertEqual(result["model"], "compatible-model")

    def test_token_budget_loads_from_dotenv_and_environment_without_real_keys(self):
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            (project / ".env").write_text("DEEPSEEK_API_KEY=test-secret-not-real\nDEEPSEEK_MAX_TOKENS=16000\n", encoding="utf-8")
            with patch.dict(os.environ, {}, clear=True), patch.object(provider, "_windows_user_environment", return_value=""):
                self.assertEqual(provider.load_settings(project).max_tokens, 16000)
                with patch.dict(os.environ, {"DEEPSEEK_MAX_TOKENS": "24000"}):
                    self.assertEqual(provider.load_settings(project).max_tokens, 24000)
            (project / ".env").unlink()
            with patch.dict(os.environ, {}, clear=True), patch.object(provider, "_windows_user_environment", return_value=""):
                self.assertEqual(provider.load_settings(project).max_tokens, 12000)

    def test_invalid_token_budgets_fail_before_network_access(self):
        with tempfile.TemporaryDirectory() as temp:
            for value in ("1023", "32769", "-1", "12000.5", "many"):
                with self.subTest(value=value), patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-secret-not-real", "DEEPSEEK_MAX_TOKENS": value}, clear=True), patch.object(provider, "_windows_user_environment", return_value=""), patch.object(provider.urllib.request, "build_opener") as opener:
                    with self.assertRaisesRegex(provider.ProviderError, "DEEPSEEK_MAX_TOKENS"):
                        provider.load_settings(Path(temp))
                    opener.assert_not_called()

    def test_http_errors_do_not_expose_upstream_body(self):
        for code in (400, 401, 402, 403, 404, 429, 500, 503):
            with self.subTest(code=code), patch.object(provider, "load_settings", return_value=self.settings), patch.object(provider.urllib.request, "build_opener") as opener:
                opener.return_value.open.side_effect = urllib.error.HTTPError("https://api.deepseek.com", code, "SECRET-UPSTREAM", {}, io.BytesIO(b"SECRET-UPSTREAM"))
                with self.assertRaises(provider.ProviderError) as error:
                    provider.complete([])
                self.assertNotIn("SECRET", str(error.exception))

    def test_redirect_does_not_forward_authorization(self):
        observed = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                observed.append(self.path)
                self.send_response(307)
                self.send_header("Location", f"http://127.0.0.1:{self.server.server_port}/leak")
                self.end_headers()

            def do_GET(self):
                observed.append(self.path)
                self.send_response(200)
                self.end_headers()

        local = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=local.serve_forever, daemon=True)
        worker.start()
        try:
            settings = provider.Settings("test-secret-not-real", f"http://127.0.0.1:{local.server_port}")
            with patch.object(provider, "load_settings", return_value=settings):
                with self.assertRaisesRegex(provider.ProviderError, "重定向"):
                    provider.complete([])
            self.assertEqual(observed, ["/chat/completions"])
        finally:
            local.shutdown()
            local.server_close()
            worker.join(2)


if __name__ == "__main__":
    unittest.main()
