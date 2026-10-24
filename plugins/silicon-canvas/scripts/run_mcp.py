"""Start the plugin's pinned MCP backend, installing it once in a user cache.

Requires Python 3.11+. Bootstrap output goes to STDERR; STDOUT belongs to MCP.
The plugin directory remains read-only and never supplies a development checkout.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.request import Request, urlopen
import zipfile

REPOSITORY = "https://github.com/jiale-wangOwO/silicon-canvas"
PLUGIN_ROOT = Path(__file__).resolve().parents[1]
READY = "plugin-runtime-ready.json"


def log(message):
    print("Silicon Canvas: " + message, file=sys.stderr, flush=True)


def load_backend(path=None):
    pin = json.loads((path or PLUGIN_ROOT / "backend.json").read_text(encoding="utf-8"))
    if pin.get("repository") != REPOSITORY:
        raise ValueError("Unexpected backend repository")
    if not isinstance(pin.get("commit"), str) or not re.fullmatch(r"[0-9a-f]{40}", pin["commit"]):
        raise ValueError("Backend commit must be a full lowercase Git SHA")
    if not isinstance(pin.get("version"), str) or not re.fullmatch(r"\d+\.\d+\.\d+", pin["version"]):
        raise ValueError("Invalid backend version")
    return {key: pin[key] for key in ("repository", "commit", "version")}


def runtime_directory(pin):
    explicit = os.environ.get("SILICON_CANVAS_RUNTIME_DIR", "").strip()
    if explicit:
        directory = Path(explicit).expanduser().resolve()
    elif os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
        directory = (base / "SiliconCanvas/plugin-runtime" / pin["commit"]).resolve()
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
        directory = (base / "silicon-canvas/mcp" / pin["commit"]).expanduser().resolve()
    if directory == PLUGIN_ROOT or directory.is_relative_to(PLUGIN_ROOT):
        raise ValueError("Runtime directory must be outside the installed plugin")
    return directory


def interpreter(directory):
    return directory / ("venv/Scripts/python.exe" if os.name == "nt" else "venv/bin/python")


def executable(directory):
    return directory / ("venv/Scripts/silicon-canvas-mcp.exe" if os.name == "nt" else "venv/bin/silicon-canvas-mcp")


def verify_install(directory, pin):
    python, launcher = interpreter(directory), executable(directory)
    if not python.is_file() or not launcher.is_file():
        return False
    code = (
        "import importlib.metadata, pathlib, sys; "
        "from silicon_canvas.visual_language import VERSION; "
        "assert importlib.metadata.version('silicon-canvas') == sys.argv[1]; "
        "assert VERSION == 'VIS1'; "
        "assert pathlib.Path(sys.prefix).resolve() == pathlib.Path(sys.argv[2]).resolve()"
    )
    result = subprocess.run([str(python), "-I", "-c", code, pin["version"], str(directory / "venv")],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
    return result.returncode == 0


def ready(directory, pin):
    try:
        recorded = json.loads((directory / READY).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return recorded == pin and verify_install(directory, pin)


@contextmanager
def bootstrap_lock(directory, timeout=180):
    lock = directory / ".plugin-bootstrap.lock"
    deadline = time.monotonic() + timeout
    while True:
        try:
            lock.mkdir()
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise RuntimeError("Timed out waiting for another bootstrap. If it crashed, remove " + str(lock))
            time.sleep(.25)
    try:
        yield
    finally:
        lock.rmdir()


def install(directory, pin):
    archive = directory / (pin["commit"] + ".zip")
    temporary = archive.with_suffix(".download")
    log("preparing backend " + pin["version"] + " (" + pin["commit"][:7] + ")")
    request = Request(REPOSITORY + "/archive/" + pin["commit"] + ".zip",
                      headers={"User-Agent": "Silicon-Canvas-plugin/" + pin["version"]})
    try:
        with urlopen(request, timeout=60) as response, temporary.open("wb") as stream:
            total = 0
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > 256 * 1024 * 1024:
                    raise RuntimeError("Backend source archive exceeds the size limit")
                stream.write(chunk)
        with zipfile.ZipFile(temporary) as source:
            expected = "silicon-canvas-" + pin["commit"] + "/pyproject.toml"
            if expected not in source.namelist():
                raise RuntimeError("The downloaded archive does not match the pinned source")
        temporary.replace(archive)
    finally:
        if temporary.exists():
            temporary.unlink()
    subprocess.run([sys.executable, "-I", "-m", "venv", str(directory / "venv")],
                   check=True, stdout=sys.stderr, stderr=sys.stderr, timeout=120)
    subprocess.run([str(interpreter(directory)), "-I", "-m", "pip", "install",
                    "--disable-pip-version-check", "--no-input", str(archive)],
                   check=True, stdout=sys.stderr, stderr=sys.stderr, timeout=600)


def ensure_runtime(directory, pin, allow_existing=False):
    directory.mkdir(parents=True, exist_ok=True)
    directory = directory.resolve(strict=True)
    if ready(directory, pin):
        return interpreter(directory)
    with bootstrap_lock(directory):
        if ready(directory, pin):
            return interpreter(directory)
        # Explicit reuse is limited to an installation whose own provenance
        # names this exact source and version. No host configuration is read.
        existing = False
        if allow_existing:
            try:
                record = json.loads((directory / "installed-source.json").read_text(encoding="utf-8"))
                existing = record.get("commit") == pin["commit"] and record.get("version") == pin["version"]
            except (OSError, ValueError):
                pass
        marker = directory / READY
        if marker.exists():
            marker.unlink()
        if not existing or not verify_install(directory, pin):
            install(directory, pin)
        if not verify_install(directory, pin):
            raise RuntimeError("Installed backend did not pass its startup verification")
        temporary = marker.with_suffix(".tmp")
        temporary.write_text(json.dumps(pin, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(marker)
    return interpreter(directory)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Prepare and verify the backend without starting MCP")
    args = parser.parse_args(argv)
    if sys.version_info < (3, 11):
        raise RuntimeError("Python 3.11 or newer is required")
    pin = load_backend()
    python = ensure_runtime(runtime_directory(pin), pin,
                            allow_existing=bool(os.environ.get("SILICON_CANVAS_RUNTIME_DIR", "").strip()))
    if args.check:
        log("backend ready: " + str(python))
        return
    # Run the module through the isolated interpreter. On Windows this avoids
    # console-script launchers whose embedded interpreter path can be stale.
    os.execv(str(python), [str(python), "-I", "-m", "silicon_canvas.mcp_server"])


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, zipfile.BadZipFile) as error:
        log(str(error))
        sys.exit(1)
