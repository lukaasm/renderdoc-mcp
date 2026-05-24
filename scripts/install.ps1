# renderdoc-mcp Windows installer.
#
# Usage:
#   pwsh -ExecutionPolicy Bypass -File scripts/install.ps1
#       [-Python <path-to-python.exe>]      # default: auto-detect Python 3.10 via py launcher
#       [-ConfigScope user|project]          # default: user (~/.claude.json)
#       [-ProjectClaudeJson <path>]          # required when -ConfigScope project
#       [-NoConfig]                          # skip writing MCP config
#       [-SkipBinaries]                      # don't run fetch_binaries.py (e.g. for build-from-source users)
#
# Idempotent. Re-running upgrades.

[CmdletBinding()]
param(
    [string]$Python = "",
    [ValidateSet("user","project")] [string]$ConfigScope = "user",
    [string]$ProjectClaudeJson = "",
    [switch]$NoConfig,
    [switch]$SkipBinaries
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Write-Host "renderdoc-mcp installer  repo=$repoRoot" -ForegroundColor Cyan

function Resolve-Python {
    param([string]$Hint)
    if ($Hint) {
        if (-not (Test-Path $Hint)) { throw "specified -Python not found: $Hint" }
        return (Resolve-Path $Hint).Path
    }
    $cands = @()
    try { $cands += (& py -3.10 -c "import sys; print(sys.executable)" 2>$null) } catch {}
    $cands += "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe"
    $cands += "C:\Python310\python.exe"
    foreach ($c in $cands) {
        if ($c -and (Test-Path $c)) {
            $ver = & $c -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
            if ($ver -eq "3.10") { return (Resolve-Path $c).Path }
        }
    }
    throw "Could not find Python 3.10 on this machine. Install it from python.org or pass -Python <path-to-3.10-python.exe>."
}

$py = Resolve-Python -Hint $Python
Write-Host "python: $py" -ForegroundColor Green

# 1. Fetch prebuilt binaries (renderdoc.pyd + DLLs) unless skipped
$binDir = Join-Path $repoRoot "binaries\py310-win64"
if (-not $SkipBinaries) {
    Write-Host "fetching prebuilt renderdoc.pyd bundle..." -ForegroundColor Cyan
    $fetch = Join-Path $repoRoot "scripts\fetch_binaries.py"
    & $py $fetch --dest $binDir
    if ($LASTEXITCODE -ne 0) { throw "fetch_binaries.py failed with exit code $LASTEXITCODE" }
} else {
    Write-Host "skipping binary fetch (SkipBinaries set)" -ForegroundColor Yellow
}
if (-not (Test-Path (Join-Path $binDir "renderdoc.pyd"))) {
    throw "renderdoc.pyd not present at $binDir — either fetch_binaries.py failed or -SkipBinaries was set without placing it manually"
}

# 2. pip install -e .
Write-Host "pip install -e ." -ForegroundColor Cyan
& $py -m pip install --upgrade pip 2>&1 | Select-Object -Last 2
& $py -m pip install -e $repoRoot
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

# 3. Smoke test: import renderdoc + import renderdoc_mcp.server
Write-Host "smoke test..." -ForegroundColor Cyan
$smoke = @"
import os, sys
os.environ['RENDERDOC_MODULE_PATH'] = r'$binDir'
sys.path.insert(0, r'$binDir')
os.add_dll_directory(r'$binDir')
import renderdoc as rd
rd.InitialiseReplay(rd.GlobalEnvironment(), [])
from renderdoc_mcp import server
import asyncio
async def n():
    ts = await server.mcp.list_tools()
    print(f'OK: renderdoc {rd.GetVersionString() if hasattr(rd, "GetVersionString") else ""} loaded, {len(list(ts))} MCP tools registered')
asyncio.run(n())
rd.ShutdownReplay()
"@
$tmp = Join-Path $env:TEMP "renderdoc-mcp-smoke.py"
$smoke | Set-Content -Encoding utf8 $tmp
& $py $tmp
if ($LASTEXITCODE -ne 0) { Remove-Item $tmp -ErrorAction SilentlyContinue; throw "smoke test failed" }
Remove-Item $tmp -ErrorAction SilentlyContinue

# 4. Write MCP server config
if ($NoConfig) {
    Write-Host "skipping MCP config (NoConfig set)" -ForegroundColor Yellow
} else {
    $target = if ($ConfigScope -eq "user") { Join-Path $env:USERPROFILE ".claude.json" } else { $ProjectClaudeJson }
    if ($ConfigScope -eq "project" -and -not $target) { throw "-ProjectClaudeJson is required when -ConfigScope project" }
    if (-not (Test-Path $target)) {
        Write-Host "creating $target" -ForegroundColor Yellow
        '{}' | Set-Content -Encoding utf8 $target
    }
    $backup = "$target.bak.$(Get-Date -Format yyyyMMddHHmmss)"
    Copy-Item $target $backup
    Write-Host "backup written: $backup" -ForegroundColor DarkGray

    $j = Get-Content $target -Raw | ConvertFrom-Json -Depth 32
    if (-not ($j.PSObject.Properties.Name -contains 'mcpServers')) {
        $j | Add-Member -MemberType NoteProperty -Name mcpServers -Value ([pscustomobject]@{})
    }
    if ($j.mcpServers.PSObject.Properties.Name -contains 'renderdoc') {
        $j.mcpServers.PSObject.Properties.Remove('renderdoc')
    }
    $entry = [ordered]@{
        command = $py
        args    = @("-m", "renderdoc_mcp")
        env     = [ordered]@{ RENDERDOC_MODULE_PATH = $binDir }
    }
    $j.mcpServers | Add-Member -MemberType NoteProperty -Name renderdoc -Value ([pscustomobject]$entry)
    $j | ConvertTo-Json -Depth 32 | Set-Content -Encoding utf8 $target
    Write-Host "wrote mcpServers.renderdoc entry to $target" -ForegroundColor Green
}

Write-Host ""
Write-Host "Done. Restart Claude Code (or /mcp -> reconnect renderdoc) to pick up the server." -ForegroundColor Green
Write-Host "Try: 'list the tools the renderdoc MCP exposes' to confirm it's wired."
