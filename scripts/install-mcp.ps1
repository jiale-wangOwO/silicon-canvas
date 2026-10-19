[CmdletBinding()]
param(
    [string]$Python = 'python',
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA 'SiliconCanvas\mcp'),
    [string]$PackagePath = (Split-Path -Parent $PSScriptRoot)
)
$ErrorActionPreference = 'Stop'
$PackagePath = (Resolve-Path -LiteralPath $PackagePath).Path
$InstallDir = [IO.Path]::GetFullPath($InstallDir)
$supportScript = Join-Path $PSScriptRoot 'install_mcp_support.py'
if (-not (Test-Path -LiteralPath $supportScript)) { throw 'The adjacent install_mcp_support.py helper is required.' }
& $Python $supportScript version
if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 or newer is required.' }
New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
# MSIX hosts may virtualize LocalAppData. Resolve before creating the venv so
# both the MCP config and the console launcher's embedded interpreter are real paths.
$canonicalPathsJson = & $Python $supportScript resolve-paths $InstallDir $PackagePath
if ($LASTEXITCODE -ne 0) { throw 'Could not resolve the installation and package paths.' }
$canonicalPaths = $canonicalPathsJson | ConvertFrom-Json
$InstallDir = $canonicalPaths.install_dir
$PackagePath = $canonicalPaths.package_path
$envDirectory = Join-Path $InstallDir 'venv'
$envPython = Join-Path $envDirectory 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $envPython)) {
    & $Python -m venv $envDirectory
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the isolated MCP environment.' }
}
& $envPython -m pip install --disable-pip-version-check $PackagePath
if ($LASTEXITCODE -ne 0) { throw 'Could not install Silicon Canvas MCP.' }
$mcpCommand = Join-Path $envDirectory 'Scripts\silicon-canvas-mcp.exe'
# An existing installation of the same wheel can retain an old virtualized
# shebang. Refresh only this package's launcher, preserving its dependencies.
$launcherCanonical = & $envPython $supportScript launcher-canonical $mcpCommand $envPython
if ($LASTEXITCODE -ne 0) { throw 'Could not verify the installed MCP launcher.' }
if ($launcherCanonical -ne 'true') {
    & $envPython -m pip install --disable-pip-version-check --force-reinstall --no-deps $PackagePath
    if ($LASTEXITCODE -ne 0) { throw 'Could not refresh the MCP launcher with its canonical interpreter.' }
    $launcherCanonical = & $envPython $supportScript launcher-canonical $mcpCommand $envPython
    if ($LASTEXITCODE -ne 0 -or $launcherCanonical -ne 'true') { throw 'The refreshed MCP launcher does not use its canonical interpreter.' }
}
& $envPython $supportScript startup
if ($LASTEXITCODE -ne 0) { throw 'Installed MCP failed its startup check.' }
$jsonPath = Join-Path $InstallDir 'mcp-config.json'
$tomlPath = Join-Path $InstallDir 'codex-mcp.toml'
& $envPython $supportScript write-config $InstallDir $mcpCommand
if ($LASTEXITCODE -ne 0) { throw 'Could not write the installation configuration snippets.' }
Write-Host 'Silicon Canvas MCP installed.'
Write-Host "Command: $mcpCommand"
Write-Host "Generic host configuration: $jsonPath"
Write-Host "Codex configuration snippet: $tomlPath"
Write-Host 'Add this STDIO command in your host MCP settings. Existing host settings have not been changed.'
