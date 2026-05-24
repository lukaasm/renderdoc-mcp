# renderdoc-mcp

MCP server for [RenderDoc](https://renderdoc.org/). Lets an AI assistant analyze `.rdc` frame captures **and** drive RenderDoc to capture frames from live applications, all via the [Model Context Protocol](https://modelcontextprotocol.io/).

> **Hard fork** of [Linkingooo/renderdoc-mcp](https://github.com/Linkingooo/renderdoc-mcp). See [ATTRIBUTION.md](ATTRIBUTION.md). This fork adds:
> - **Prebuilt `renderdoc.pyd` for Windows x64 / Python 3.10** as a Release asset (official RenderDoc binaries don't ship it).
> - **Live capture tools** — `launch_and_capture`, `inject_into_running_process`, `list_capture_targets`, `trigger_capture_on_target` — so the AI can launch your app, capture a frame, and analyze it without leaving the chat.
> - **One-shot installer** (`scripts/install.ps1`) that fetches the binary, installs the package, and writes the Claude Code MCP config.

## Quickstart (Windows, ~2 min)

Requires Python 3.10 (other minor versions will not work — `renderdoc.pyd` is ABI-locked).

```pwsh
git clone https://github.com/<owner>/renderdoc-mcp.git
cd renderdoc-mcp
pwsh -ExecutionPolicy Bypass -File scripts/install.ps1
```

The script:
1. Locates Python 3.10 (via `py -3.10` launcher) or accepts `-Python <path>`.
2. Downloads `renderdoc-pymodules-py310-win64.zip` from this repo's latest Release and extracts to `binaries/py310-win64/`.
3. Runs `pip install -e .` so the `renderdoc_mcp` package + `mcp` deps land in your Python 3.10.
4. Runs a smoke test (`import renderdoc; InitialiseReplay`).
5. Writes the MCP server entry to `~/.claude.json` under `mcpServers.renderdoc` (backup first).

Restart Claude Code (or `/mcp` → reconnect) and the `renderdoc` MCP appears with 46 tools.

## What the tools can do

### Analyze a pre-existing `.rdc` capture
- `open_capture`, `get_capture_info`, `get_frame_overview`
- `list_actions`, `search_actions`, `find_draws`, `get_action`, `set_event`
- `get_pipeline_state`, `get_vertex_inputs`, `get_shader_bindings`, `get_shader_reflection`, `get_cbuffer_contents`, `disassemble_shader`
- `list_textures`, `list_buffers`, `list_resources`, `get_resource_usage`, `get_texture_stats`
- `save_texture`, `save_render_target`, `read_texture_pixels`, `pick_pixel`, `sample_pixel_region`, `pixel_history`, `debug_shader_at_pixel`
- `export_mesh`, `export_draw_textures`, `get_buffer_data`, `get_post_vs_data`
- `get_draw_call_state`, `diff_draw_calls`, `analyze_overdraw`, `analyze_bandwidth`, `analyze_state_changes`, `analyze_render_passes`, `get_pass_timing`
- `diagnose_negative_values`, `diagnose_precision_issues`, `diagnose_reflection_mismatch`, `diagnose_mobile_risks`

### Drive a live app *(this fork)*
- `launch_and_capture(executable, cmdline, wait_seconds_before_capture, num_frames, auto_open, ...)`
- `inject_into_running_process(pid, ...)`
- `list_capture_targets()`
- `trigger_capture_on_target(ident, num_frames, ...)`

All 4 forward `hook_into_children`, `api_validation`, `capture_callstacks`, `ref_all_resources` to `CaptureOptions`, accept `capture_file_template`, and offer `auto_open=True` to chain straight into analysis.

## Example session

```
User: launch the model editor, capture one frame, and tell me what render targets it uses

Claude: [launch_and_capture(executable=".../model_editor_win_release.exe",
                           wait_seconds_before_capture=5, num_frames=1, auto_open=True)]
        [get_frame_overview()]
        → Frame uses 4 render targets: 1920x1080 R11G11B10_FLOAT (HDR), ...
```

## Docs

- [docs/usage.md](docs/usage.md) — tool reference + recipes
- [docs/build-from-source.md](docs/build-from-source.md) — how the bundled `renderdoc.pyd` was built (and how to rebuild for a different Python version)
- [docs/test-plan.md](docs/test-plan.md) — manual test plan (from upstream)
- [docs/tool-design.md](docs/tool-design.md) — upstream design notes
- [docs/roadmap.md](docs/roadmap.md) — upstream roadmap

## Limitations

- **Windows x64 + Python 3.10 only** (current Release asset). Other ABIs require building `renderdoc.pyd` yourself — see `docs/build-from-source.md`.
- `inject_into_running_process` often needs admin privileges on Windows.
- `launch_and_capture` blocks until the first present after `wait_seconds_before_capture`; apps that don't render in that window will return `timed_out=true`.

## License

MIT. See [LICENSE](LICENSE) and [ATTRIBUTION.md](ATTRIBUTION.md).
