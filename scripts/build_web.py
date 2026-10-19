"""Build a static Pages artifact with the shared compiler and licensed font."""
from pathlib import Path
import hashlib
import json
import shutil
import zipfile
import tomllib

ROOT = Path(__file__).resolve().parent.parent


def main():
    target = ROOT / "dist" / "web"
    # Only the explicitly owned build output may be replaced.
    if target.exists():
        if not target.resolve().is_relative_to(ROOT.resolve()) or target.is_symlink() or target.parent.is_symlink():
            raise RuntimeError("Unexpected build destination")
        shutil.rmtree(target)
    shutil.copytree(ROOT / "web", target, ignore=shutil.ignore_patterns("tests", "package.json", "node_modules"))
    shutil.copy2(ROOT / "LICENSE", target / "LICENSE")
    # Keep the downloadable static distribution's notices self contained.
    (target / "docs").mkdir(exist_ok=True)
    shutil.copy2(ROOT / "docs" / "third-party.md", target / "docs" / "third-party.md")
    (target / "assets").mkdir(exist_ok=True)
    shutil.copy2(ROOT / "examples" / "gpu.json", target / "assets" / "gpu-example.json")
    archive = target / "assets" / "compiler.zip"
    package = ROOT / "src" / "silicon_canvas"
    # Browser has no model transport, MCP dependency or filesystem artifact store.
    excluded = {"provider.py", "service.py", "mcp_server.py", "artifact_store.py"}
    files = {}
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as out:
        for path in sorted(package.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts or path.name in excluded:
                continue
            if path.suffix not in {".py", ".json", ".otf"} and path.name != "LICENSE":
                continue
            relative = path.relative_to(package.parent).as_posix()
            data = path.read_bytes()
            info = zipfile.ZipInfo(relative, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            out.writestr(info, data)
            files[relative] = hashlib.sha256(data).hexdigest()
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    (target / "assets" / "compiler-manifest.json").write_text(json.dumps({"version": version, "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(), "files": files}, indent=2), encoding="utf-8")
    (target / ".nojekyll").touch()
    print(json.dumps({"site": str(target), "compiler_bytes": archive.stat().st_size, "files": len(files)}))


if __name__ == "__main__":
    main()
