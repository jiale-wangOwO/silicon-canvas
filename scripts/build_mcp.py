"""Build a portable MCP executable; no GUI or user-facing CLI workflow."""
from pathlib import Path
import json
import importlib.metadata
import re
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parent.parent
REPOSITORY = "https://github.com/jiale-wangOwO/silicon-canvas"
PORTABLE_DOCUMENTS = (
    "LICENSE", "README.md", "SECURITY.md", "CONTRIBUTING.md", ".env.example",
    "docs/mcp.md", "docs/web.md", "docs/privacy.md", "docs/third-party.md",
)
PORTABLE_EXAMPLES = (
    "gpu.json", "soc.json", "attention-dataflow.json", "online-attention-dataflow.json",
)


def copy_documentation(portable):
    """Ship installation docs; link to repository-only pages and image assets."""
    included = set(PORTABLE_DOCUMENTS)

    def public_link(match, source):
        prefix, target, suffix = match.groups()
        if target.startswith(("https://", "http://", "mailto:", "#")):
            return match.group(0)
        file, separator, anchor = target.partition("#")
        destination = (source.parent / file).resolve()
        if not destination.is_relative_to(ROOT):
            raise ValueError("Documentation link escapes repository: " + target)
        relative = destination.relative_to(ROOT).as_posix()
        if relative in included:
            return match.group(0)
        base = ("https://raw.githubusercontent.com/jiale-wangOwO/silicon-canvas/main/"
                if prefix.startswith("!") else REPOSITORY + "/blob/main/")
        return prefix + base + relative + (separator + anchor if separator else "") + suffix

    for name in PORTABLE_DOCUMENTS:
        source, destination = ROOT / name, portable / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.suffix == ".md":
            text = source.read_text(encoding="utf-8")
            text = re.sub(r"(!?\[[^\]]*\]\()([^)]+)(\))", lambda match: public_link(match, source), text)
            destination.write_text(text, encoding="utf-8", newline="\n")
        else:
            shutil.copy2(source, destination)


def main():
    build_dir = ROOT / "build" / "portable"
    build_dir.mkdir(parents=True, exist_ok=True)
    launcher = build_dir / "launcher.py"
    launcher.write_text("from silicon_canvas.mcp_server import main\nif __name__ == '__main__':\n    main()\n", encoding="utf-8")
    subprocess.run([
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir",
        "--name", "silicon-canvas-mcp", "--distpath", str(ROOT / "dist" / "portable"),
        "--workpath", str(build_dir / "work"), "--specpath", str(build_dir),
        "--collect-data", "silicon_canvas", "--collect-submodules", "mcp.server",
        "--collect-submodules", "mcp.shared",
        "--collect-submodules", "mcp_types", str(launcher)
    ], check=True, cwd=ROOT)
    portable = ROOT / "dist" / "portable" / "silicon-canvas-mcp"
    copy_documentation(portable)
    (portable / "examples").mkdir(exist_ok=True)
    for name in PORTABLE_EXAMPLES:
        shutil.copy2(ROOT / "examples" / name, portable / "examples" / name)
    notices = portable / "THIRD-PARTY-LICENSES"
    notices.mkdir(exist_ok=True)
    licenses = {}
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata.get("Name", "unknown")
        destination = notices / name
        destination.mkdir(exist_ok=True)
        (destination / "METADATA.txt").write_text(distribution.read_text("METADATA") or json.dumps(dict(distribution.metadata), ensure_ascii=False, indent=2), encoding="utf-8")
        included = []
        for relative in distribution.files or []:
            if any("license" in part.lower() or "copying" in part.lower() for part in relative.parts):
                path = Path(distribution.locate_file(relative))
                if path.is_file() and path.stat().st_size < 2 * 1024 * 1024:
                    target = destination / str(relative).replace("/", "_").replace("\\", "_")
                    shutil.copy2(path, target)
                    included.append(target.name)
        licenses[name] = {"version": distribution.version, "license_files": included}
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if python_license.is_file():
        shutil.copy2(python_license, notices / "Python-LICENSE.txt")
    (notices / "inventory.json").write_text(json.dumps(licenses, indent=2), encoding="utf-8")
    (portable / "MCP-CONFIG.json").write_text(json.dumps({"mcpServers": {"silicon-canvas": {"command": "REPLACE_WITH_ABSOLUTE_PATH/silicon-canvas-mcp.exe" if sys.platform == "win32" else "REPLACE_WITH_ABSOLUTE_PATH/silicon-canvas-mcp", "args": []}}}, indent=2), encoding="utf-8")
    archive = ROOT / "dist" / ("silicon-canvas-mcp-windows-x64.zip" if sys.platform == "win32" else "silicon-canvas-mcp-" + sys.platform + ".zip")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as out:
        for path in sorted(portable.rglob("*")):
            if path.is_file():
                out.write(path, path.relative_to(portable.parent))
    print(json.dumps({"archive": str(archive), "bytes": archive.stat().st_size}))


if __name__ == "__main__":
    main()
