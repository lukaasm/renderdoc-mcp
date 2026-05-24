# ONBOARDING (for AI agents)

This file is the auto-consumable setup guide. If a human asks you (an AI) to install this repo's MCP server on their Windows machine, follow these steps. They're written to be machine-executable.

## Preconditions to verify first

Run each check; abort with the suggested action if any fails.

1. **OS**: `[System.Environment]::OSVersion.Platform -eq 'Win32NT'`. Linux/macOS users currently need to build `renderdoc.so` themselves — see `docs/build-from-source.md` and stop.
2. **Architecture**: `[System.Environment]::Is64BitOperatingSystem`. Must be `True`.
3. **Python 3.10** present. Check in order:
   - `py -3.10 -c "import sys; print(sys.executable)"`
   - `%LOCALAPPDATA%\Programs\Python\Python310\python.exe`
   - `C:\Python310\python.exe`
   If none exist, ask the user to install Python 3.10 from https://www.python.org/downloads/release/python-31011/ (Windows installer 64-bit). Do not silently install for them.
4. **Git** present: `git --version`. If missing, install via `winget install Git.Git`.
5. **PowerShell 5.1+** present (default on Windows 10/11).

## Install (happy path)

```pwsh
git clone https://github.com/<owner>/renderdoc-mcp.git
cd renderdoc-mcp
pwsh -ExecutionPolicy Bypass -File scripts/install.ps1
```

`scripts/install.ps1` is idempotent. It:
- Resolves Python 3.10 (or honors `-Python <path>`).
- Calls `scripts/fetch_binaries.py` to download `renderdoc-pymodules-py310-win64.zip` from the latest Release into `binaries/py310-win64/`.
- `pip install -e .` against Python 3.10.
- Runs a smoke test that imports `renderdoc` and lists MCP tools.
- Writes/updates `~/.claude.json` → `mcpServers.renderdoc` with the right command + env. Backup goes to `~/.claude.json.bak.<timestamp>`.

After it exits, tell the user to **restart Claude Code** (or `/mcp` → reconnect `renderdoc`). The server should expose 46 tools.

## Validation step (after install)

In a fresh Claude Code session, ask the model to call `list_capture_targets`. Expect `{"url":"localhost","targets":[]}` (or a non-empty list if the user has a RenderDoc-injected process running). This proves the server starts, the .pyd loads, and the bridge works end-to-end.

If validation fails, capture stderr:
- Run the smoke test manually: `python -m renderdoc_mcp` and look at the error. Common failures:
  - `ImportError: DLL load failed`: RENDERDOC_MODULE_PATH env var didn't propagate; check `~/.claude.json` was written correctly.
  - `ModuleNotFoundError: No module named 'renderdoc'`: `binaries/py310-win64/renderdoc.pyd` is missing — re-run `python scripts/fetch_binaries.py`.
  - `RuntimeError: Python version mismatch`: The user is not actually on Python 3.10. Check `python --version`.

## Non-defaults

- `--SkipBinaries` if the user already built their own .pyd; ask where they staged it and set `RENDERDOC_MODULE_PATH` manually in the MCP config.
- `-ConfigScope project -ProjectClaudeJson <path>` to write a project-scoped `.claude/.mcp.json`-style entry instead of user-scope.
- `-NoConfig` to skip the MCP wiring (the user will do it themselves).
- `RENDERDOC_MCP_REPO=<owner>/<repo>` env var if fetching from a fork's releases.

## After install — quick task to demonstrate value

Suggest the user try:
> "Launch `<some_graphics_app.exe>` and capture a frame, then summarize its render passes."

Then call `launch_and_capture(executable=..., wait_seconds_before_capture=5, num_frames=1, auto_open=True)` followed by `analyze_render_passes()`.

## Uninstall

```pwsh
python -m pip uninstall -y renderdoc-mcp
# Then manually remove the `renderdoc` entry under `mcpServers` in ~/.claude.json.
```
