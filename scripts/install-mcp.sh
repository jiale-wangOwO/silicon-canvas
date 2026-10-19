#!/bin/sh
# Install only the local MCP entry into an isolated Python environment.
set -eu
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
package_path=${1:-"$(dirname -- "$script_dir")"}
install_dir=${SILICON_CANVAS_INSTALL_DIR:-"${XDG_DATA_HOME:-"$HOME/.local/share"}/silicon-canvas/mcp"}
python_command=${PYTHON:-python3}
"$python_command" -c 'import sys; assert sys.version_info >= (3, 11), "Python 3.11 or newer is required"'
mkdir -p "$install_dir"
# Canonicalize the directory before venv creation; its shebangs and generated
# host commands must use the same absolute installation location.
install_dir=$("$python_command" -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve(strict=True))' "$install_dir")
package_path=$("$python_command" -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve(strict=True))' "$package_path")
if [ ! -x "$install_dir/venv/bin/python" ]; then
    "$python_command" -m venv "$install_dir/venv"
fi
"$install_dir/venv/bin/python" -m pip install --disable-pip-version-check "$package_path"
"$install_dir/venv/bin/python" -c 'from silicon_canvas.mcp_server import create_server; create_server()'
"$install_dir/venv/bin/python" - "$install_dir" <<'PY'
import json
from pathlib import Path
import sys
directory = Path(sys.argv[1]).resolve()
command = str(directory / 'venv/bin/silicon-canvas-mcp')
(directory / 'mcp-config.json').write_text(json.dumps({'mcpServers': {'silicon-canvas': {'command': command, 'args': []}}}, indent=2) + '\n', encoding='utf-8')
(directory / 'codex-mcp.toml').write_text('[mcp_servers.silicon-canvas]\ncommand = ' + json.dumps(command) + '\nargs = []\nstartup_timeout_sec = 30\ntool_timeout_sec = 180\n', encoding='utf-8')
print('Silicon Canvas MCP installed.')
print('Command: ' + command)
print('Generic host configuration: ' + str(directory / 'mcp-config.json'))
print('Codex configuration snippet: ' + str(directory / 'codex-mcp.toml'))
print('Add this STDIO command in your host MCP settings. Existing host settings have not been changed.')
PY
