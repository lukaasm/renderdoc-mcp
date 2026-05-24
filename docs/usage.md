# Usage

The MCP server exposes 46 tools. The full set is documented in [tool-design.md](tool-design.md) (upstream). This page focuses on workflows.

## Workflow A — analyze an existing capture

```
open_capture("C:\\captures\\frame_42.rdc")
get_capture_info()                  # API, resolution, GPU quirks
get_frame_overview()                # action counts, render target list
analyze_render_passes()             # pass-by-pass breakdown
get_pass_timing("pass")             # most expensive passes
```

## Workflow B — capture + analyze a live app (this fork)

```
launch_and_capture(
    executable="C:\\path\\to\\app.exe",
    cmdline="--scene=test",
    wait_seconds_before_capture=5,    # let the app initialize its API + present a few frames
    num_frames=1,
    auto_open=True                    # chains into open_capture on the returned .rdc
)
get_frame_overview()
```

`launch_and_capture` returns:
```json
{
  "ident": 38920,
  "executable": "...",
  "api": "D3D12",
  "captures": [{"path":"...\\frame_1.rdc","frame_number":42,"byte_size":12345678,...}],
  "timed_out": false,
  "opened": {...}            // present when auto_open=True succeeded
}
```

## Workflow C — capture from an already-running app

```
list_capture_targets()                              # find idents
# → {"targets":[{"ident":38920,"pid":12345,"target":"app.exe","api":"D3D12",...}]}
trigger_capture_on_target(ident=38920, num_frames=3, auto_open=True)
```

Or inject into a process that wasn't launched with RenderDoc:

```
inject_into_running_process(pid=12345, num_frames=1, auto_open=True)
```

(Usually needs admin privileges on Windows.)

## CaptureOptions exposed by the capture tools

All four capture tools accept these (forwarded to `CaptureOptions`):

| Param | Default | Effect |
|-------|---------|--------|
| `hook_into_children` | `false` | Also inject into child processes the app spawns. |
| `api_validation` | `false` | Enable graphics-API validation layer for the run (slower). |
| `capture_callstacks` | `false` | Record callstacks at each API call site (larger captures). |
| `ref_all_resources` | `false` | Force-reference every resource each frame (larger but more complete). |
| `capture_file_template` | `""` | Override the `.rdc` output path. Empty = RenderDoc default (typically `%TEMP%\RenderDoc\`). |
| `leave_running` | `false` | Don't close the TargetControl connection after capture. Useful if you plan to trigger more captures. The app keeps running regardless. |

## Common pitfalls

- **Capture times out** — usually means the app didn't present a frame before `capture_timeout_seconds` elapsed (default 60s). Increase `wait_seconds_before_capture` or `capture_timeout_seconds`. Headless apps or compute-only apps don't present, so they can't be captured this way.
- **`ExecuteAndInject failed: InjectionFailed`** — the path doesn't exist or Windows refused injection. Check the executable path is absolute and accessible.
- **`InjectIntoProcess` fails with access denied** — run Claude Code as administrator, or launch the target via `launch_and_capture` instead.
- **MCP tools don't appear after install** — restart Claude Code. The MCP server is spawned at startup and isn't hot-reloaded.
