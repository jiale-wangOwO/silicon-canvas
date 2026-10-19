"""Quoted-code-free checks shared by Windows PowerShell installers.

Paths are native process arguments. Keep these actions in a file so Windows
PowerShell 5.1 cannot strip the quotes from Python expressions passed to -c.
"""
import argparse
import json
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("version")
    resolve = actions.add_parser("resolve-paths")
    resolve.add_argument("install_dir")
    resolve.add_argument("package_path")
    launcher = actions.add_parser("launcher-canonical")
    launcher.add_argument("launcher")
    launcher.add_argument("interpreter")
    actions.add_parser("startup")
    config = actions.add_parser("write-config")
    config.add_argument("install_dir")
    config.add_argument("command")
    arguments = parser.parse_args()
    if sys.version_info < (3, 11):
        parser.exit(1, "Python 3.11 or newer is required.\n")
    if arguments.action == "version":
        return
    if arguments.action == "resolve-paths":
        print(json.dumps({"install_dir": str(Path(arguments.install_dir).resolve(strict=True)),
                          "package_path": str(Path(arguments.package_path).resolve(strict=True))}))
    elif arguments.action == "launcher-canonical":
        expected = str(Path(arguments.interpreter).resolve(strict=True)).encode("utf-8").lower()
        raw = Path(arguments.launcher).read_bytes().lower()
        print("true" if expected in raw else "false")
    elif arguments.action == "write-config":
        directory = Path(arguments.install_dir).resolve(strict=True)
        command = str(Path(arguments.command).resolve(strict=True))
        generic = {"mcpServers": {"silicon-canvas": {"command": command, "args": []}}}
        (directory / "mcp-config.json").write_text(json.dumps(generic, indent=2) + "\n", encoding="utf-8", newline="\n")
        (directory / "codex-mcp.toml").write_text("[mcp_servers.silicon-canvas]\ncommand = " + json.dumps(command)
            + "\nargs = []\nstartup_timeout_sec = 30\ntool_timeout_sec = 180\n", encoding="utf-8", newline="\n")
    else:
        from silicon_canvas.mcp_server import create_server
        create_server()


if __name__ == "__main__":
    main()
