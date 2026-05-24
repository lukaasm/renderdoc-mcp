# Building `renderdoc.pyd` from source

Official RenderDoc Windows distributions (MSI and Portable ZIP) do **not** include `pymodules/renderdoc.pyd`. To use the RenderDoc Python API from an external Python interpreter, you must build it yourself. This document captures the exact recipe used to produce the binary shipped under this repo's Releases, for Windows x64 / Python 3.10.

## Prerequisites

- Visual Studio 2022 with the "Desktop development with C++" workload
- Python 3.10 installed at `%LOCALAPPDATA%\Programs\Python\Python310\` (or adapt paths below)
- Git
- ~5 GB free disk for the source tree + build outputs

## Steps

### 1. Clone RenderDoc

```pwsh
git clone --depth 1 --branch v1.x https://github.com/baldurk/renderdoc.git $env:USERPROFILE\tools\renderdoc-src
```

### 2. Create a Python 3.10 prefix shim

RenderDoc's `python.props` discovers Python via `RENDERDOC_PYTHON_PREFIX64`. It requires three files at that prefix: `include/Python.h`, `libs/python<XY>.lib` (or `python<XY>.lib` at root), and `python<XY>.zip` at root. Standard Python installs have the first two but not the third (it's only in embeddable distributions). Build a shim:

```pwsh
$prefix = "$env:USERPROFILE\tools\renderdoc-pyenv-310"
$py     = "$env:LOCALAPPDATA\Programs\Python\Python310"
New-Item -ItemType Directory $prefix -Force | Out-Null
cmd /c mklink /J "$prefix\include" "$py\include"
cmd /c mklink /J "$prefix\libs"    "$py\libs"
# Empty marker file — python.props only checks existence
Add-Type -AssemblyName System.IO.Compression
[System.IO.Compression.ZipFile]::Open("$prefix\python310.zip", 'Create').Dispose()
```

### 3. Pre-build solution-level deps that don't propagate through `.vcxproj` references

The breakpad libs and `renderdoc_version` are solution-level dependencies of `renderdoc.vcxproj`. When you build a `.vcxproj` directly (instead of via the `.sln`), MSBuild doesn't follow solution-level deps. Build them first:

```pwsh
$MSB = "C:\Program Files\Microsoft Visual Studio\2022\Community\MSBuild\Current\Bin\amd64\MSBuild.exe"
$SRC = "$env:USERPROFILE\tools\renderdoc-src"
$env:RENDERDOC_PYTHON_PREFIX64 = "$env:USERPROFILE\tools\renderdoc-pyenv-310"

$projs = @(
    "$SRC\renderdoc\3rdparty\breakpad\client\windows\common.vcxproj",
    "$SRC\renderdoc\3rdparty\breakpad\client\windows\crash_generation\crash_generation_client.vcxproj",
    "$SRC\renderdoc\3rdparty\breakpad\client\windows\crash_generation\crash_generation_server.vcxproj",
    "$SRC\renderdoc\3rdparty\breakpad\client\windows\handler\exception_handler.vcxproj",
    "$SRC\renderdoc\renderdoc_version.vcxproj"
)
foreach ($p in $projs) {
    & $MSB $p "-p:SolutionDir=$SRC\" "-p:Configuration=Release" "-p:Platform=x64" "-p:PlatformToolset=v143" -verbosity:minimal
    if ($LASTEXITCODE -ne 0) { throw "failed: $p" }
}
```

### 4. Build the Python module

```pwsh
& $MSB "$SRC\qrenderdoc\Code\pyrenderdoc\pyrenderdoc_module.vcxproj" `
    "-p:SolutionDir=$SRC\" `
    "-p:Configuration=Release" `
    "-p:Platform=x64" `
    "-p:PlatformToolset=v143" `
    -m -verbosity:minimal
```

This compiles `renderdoc.dll` (~25 MB, statically links all the driver `.lib` files) and then `renderdoc.pyd` (~6 MB, SWIG-generated Python wrapper). The link step does LTCG and takes several minutes; that's normal.

Expected output:
```
pyrenderdoc_module.vcxproj -> ...\x64\Release\pymodules\renderdoc.pyd
Built against python from C:\Users\...\renderdoc-pyenv-310
```

### 5. Stage the artifacts

```pwsh
$dst = "$env:USERPROFILE\tools\renderdoc-pymodules"
New-Item -ItemType Directory $dst -Force | Out-Null
Copy-Item "$SRC\x64\Release\pymodules\renderdoc.pyd"       $dst
Copy-Item "$SRC\x64\Release\pymodules\d3dcompiler_47.dll"  $dst
Copy-Item "$SRC\x64\Release\renderdoc.dll"                  $dst
Copy-Item "$SRC\x64\Release\renderdoc.json"                 $dst
```

`$dst` is what you set `RENDERDOC_MODULE_PATH` to in the MCP server config.

## Targeting a different Python

Change step 2 to point at your other Python install. Step 3 and 4 unchanged. The resulting `.pyd` is ABI-locked to whatever Python you point the shim at — you cannot use a `.pyd` built for 3.10 from a 3.11 interpreter.

## Why solution-level deps don't propagate

`renderdoc.vcxproj` declares `breakpad_common.lib` etc. via `<AdditionalDependencies>` rather than `<ProjectReference>`. MSBuild only auto-builds projects referenced via `<ProjectReference>`. The `.sln` knows the dependency graph but `.vcxproj` builds don't. Building the breakpad/version projects first (step 3) is the simplest workaround; the alternative is to use `devenv.com` (which is solution-aware but a black box on the CLI).
