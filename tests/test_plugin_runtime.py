import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "plugins/silicon-canvas/scripts/run_mcp.py"
SPEC = importlib.util.spec_from_file_location("silicon_plugin_runtime", MODULE)
runtime = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runtime)


class PluginRuntimeTests(unittest.TestCase):
    def test_pin_rejects_abbreviated_sha_and_other_repositories(self):
        pin = runtime.load_backend()
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / "backend.json"
            for invalid in ({**pin, "commit": pin["commit"][:7]},
                            {**pin, "repository": "https://example.com/untrusted"}):
                manifest.write_text(json.dumps(invalid), encoding="utf-8")
                with self.assertRaises(ValueError):
                    runtime.load_backend(manifest)

    def test_cache_uses_full_source_commit_and_is_outside_plugin(self):
        pin = runtime.load_backend()
        with patch.dict(os.environ, {"SILICON_CANVAS_RUNTIME_DIR": ""}):
            self.assertEqual(runtime.runtime_directory(pin).name, pin["commit"])
        with patch.dict(os.environ, {"SILICON_CANVAS_RUNTIME_DIR": str(runtime.PLUGIN_ROOT / "runtime")}):
            with self.assertRaises(ValueError):
                runtime.runtime_directory(pin)

    def test_ready_cache_has_no_bootstrap_or_network(self):
        pin = runtime.load_backend()
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            (target / runtime.READY).write_text(json.dumps(pin), encoding="utf-8")
            with patch.object(runtime, "verify_install", return_value=True), \
                 patch.object(runtime, "install") as install:
                self.assertEqual(runtime.ensure_runtime(target, pin), runtime.interpreter(target))
                install.assert_not_called()

    def test_failed_install_never_marks_ready_and_releases_lock(self):
        pin = runtime.load_backend()
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            with patch.object(runtime, "install", side_effect=RuntimeError("failed")):
                with self.assertRaisesRegex(RuntimeError, "failed"):
                    runtime.ensure_runtime(target, pin)
            self.assertFalse((target / runtime.READY).exists())
            self.assertFalse((target / ".plugin-bootstrap.lock").exists())

    def test_only_matching_explicit_provenance_can_reuse_an_install(self):
        pin = runtime.load_backend()
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            (target / "installed-source.json").write_text(json.dumps(pin), encoding="utf-8")
            with patch.object(runtime, "verify_install", return_value=True), \
                 patch.object(runtime, "install") as install:
                runtime.ensure_runtime(target, pin, allow_existing=True)
                install.assert_not_called()
            self.assertEqual(json.loads((target / runtime.READY).read_text()), pin)

    def test_check_writes_only_stderr(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(runtime, "ensure_runtime", return_value=Path("backend.exe")), \
             contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            runtime.main(["--check"])
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("backend ready:", stderr.getvalue())

    def test_server_uses_the_cached_isolated_interpreter(self):
        python = Path("runtime-python")
        with patch.object(runtime, "ensure_runtime", return_value=python), \
             patch.object(runtime.os, "execv") as execute:
            runtime.main([])
        execute.assert_called_once_with(str(python), [str(python), "-I", "-m", "silicon_canvas.mcp_server"])


if __name__ == "__main__":
    unittest.main()
