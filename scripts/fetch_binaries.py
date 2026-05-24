"""Download the prebuilt renderdoc.pyd bundle from this repo's GitHub Release.

Usage:
    python scripts/fetch_binaries.py [--dest <dir>] [--tag <release-tag>]

Default dest: <repo-root>/binaries/py310-win64/
Default tag: latest release that has a matching asset.

Exits 0 on success, non-zero on failure. Prints the resolved asset URL and
final extracted directory so calling scripts can pick it up.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

REPO_API = "https://api.github.com/repos/{owner}/{repo}/releases/{tag_or_latest}"
DEFAULT_OWNER_REPO = ("lukaasm", "renderdoc-mcp")
ASSET_NAME = "renderdoc-pymodules-py{py_major_minor}-win64.zip"
EXPECTED_FILES = ("renderdoc.pyd", "renderdoc.dll", "d3dcompiler_47.dll", "renderdoc.json")


def _detect_owner_repo() -> tuple[str, str]:
    env = os.environ.get("RENDERDOC_MCP_REPO")
    if env and "/" in env:
        owner, repo = env.split("/", 1)
        return owner.strip(), repo.strip()
    return DEFAULT_OWNER_REPO


def _fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "renderdoc-mcp-fetch"})
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _download(url: str, dest: Path) -> None:
    req = urllib.request.Request(url, headers={"Accept": "application/octet-stream", "User-Agent": "renderdoc-mcp-fetch"})
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(req, timeout=300) as resp, open(tmp, "wb") as f:
        shutil.copyfileobj(resp, f, length=1024 * 1024)
    tmp.replace(dest)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dest", type=Path, default=None, help="Where to extract the binaries (default: <repo>/binaries/py310-win64/)")
    p.add_argument("--tag", default="latest", help="Release tag to fetch from (default: latest)")
    p.add_argument("--py", default=f"{sys.version_info.major}{sys.version_info.minor}", help="Python major+minor for asset selection (default: detected)")
    args = p.parse_args()

    if sys.platform != "win32":
        print(f"error: this script only supports Windows (sys.platform={sys.platform!r})", file=sys.stderr)
        return 2
    if args.py != "310":
        print(f"error: only Python 3.10 binaries are currently published (asked for py={args.py}). Build from source or open an issue.", file=sys.stderr)
        return 2

    owner, repo = _detect_owner_repo()
    if owner == "OWNER_PLACEHOLDER":
        print("error: GitHub owner not set. Set RENDERDOC_MCP_REPO=<owner>/<repo> or edit DEFAULT_OWNER_REPO in this script.", file=sys.stderr)
        return 2

    repo_root = Path(__file__).resolve().parent.parent
    dest = args.dest or (repo_root / "binaries" / f"py{args.py}-win64")
    dest.mkdir(parents=True, exist_ok=True)

    asset_name = ASSET_NAME.format(py_major_minor=args.py)
    tag_path = "latest" if args.tag == "latest" else f"tags/{args.tag}"
    api_url = REPO_API.format(owner=owner, repo=repo, tag_or_latest=tag_path)
    print(f"querying release: {api_url}", file=sys.stderr)
    try:
        release = _fetch_json(api_url)
    except urllib.error.HTTPError as e:
        print(f"error: {e.code} {e.reason} for {api_url}", file=sys.stderr)
        return 3

    matching = [a for a in release.get("assets", []) if a["name"] == asset_name]
    if not matching:
        names = ", ".join(a["name"] for a in release.get("assets", []))
        print(f"error: release {release.get('tag_name')!r} has no asset named {asset_name!r}. Available: {names}", file=sys.stderr)
        return 4
    asset = matching[0]
    download_url = asset.get("browser_download_url") or asset.get("url")
    print(f"asset: {asset['name']}  size: {asset['size']} bytes", file=sys.stderr)

    zip_path = dest.parent / asset_name
    print(f"downloading -> {zip_path}", file=sys.stderr)
    _download(download_url, zip_path)

    print(f"extracting -> {dest}", file=sys.stderr)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest)
    zip_path.unlink(missing_ok=True)

    missing = [f for f in EXPECTED_FILES if not (dest / f).is_file()]
    if missing:
        print(f"error: extracted bundle is missing expected files: {missing}", file=sys.stderr)
        return 5

    print(str(dest))
    return 0


if __name__ == "__main__":
    sys.exit(main())
