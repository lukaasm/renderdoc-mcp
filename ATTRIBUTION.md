# Attribution

This repository is a hard fork of [Linkingooo/renderdoc-mcp](https://github.com/Linkingooo/renderdoc-mcp), bundled with prebuilt binaries and a setup script aimed at zero-touch installation (including by AI agents).

## Upstream Python source

- **Repo**: https://github.com/Linkingooo/renderdoc-mcp
- **License**: MIT
- **Original author**: Linkingooo

Files under `src/renderdoc_mcp/` are vendored from upstream commit-as-of-fork, with these local additions:

- `src/renderdoc_mcp/tools/capture_tools.py` — new (this fork): `launch_and_capture`, `inject_into_running_process`, `list_capture_targets`, `trigger_capture_on_target`. Uses `ExecuteAndInject` + `TargetControl` to drive live processes, not just analyze pre-existing `.rdc` files.
- `src/renderdoc_mcp/server.py` — modified to register `capture_tools`.

## Prebuilt `renderdoc.pyd`

- **Source repo**: https://github.com/baldurk/renderdoc (v1.x branch, commit captured in build provenance)
- **License**: MIT (RenderDoc)
- **Original author**: Baldur Karlsson
- **Build target**: Windows x64, Python 3.10 (must match — the .pyd is ABI-locked to the Python minor version)

The .pyd is **not redistributed in tree**; it lives as a Release asset and is fetched at install time by `scripts/fetch_binaries.py`. See `docs/build-from-source.md` for the exact build recipe that produced the shipped binary.

## Why ship prebuilt binaries at all

Official RenderDoc Windows binary distributions (MSI installer AND Portable ZIP) do **not** include `pymodules/renderdoc.pyd` — the RenderDoc maintainers don't ship it because the .pyd is locked to a specific Python minor-version ABI, and shipping all combinations is impractical for them. So in practice, anyone wanting to use the RenderDoc Python API from an external Python interpreter has to build RenderDoc from source themselves. This bundle does that build once and publishes the artifact.
