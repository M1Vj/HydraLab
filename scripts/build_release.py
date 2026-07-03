#!/usr/bin/env python3
"""Build a distributable that bundles the built web UI into the Python package.

Normal ``uv build`` ships only the backend. For a self-contained install
(``pip install`` / Homebrew), the packaged ``hydralab`` command should also
serve the web UI. This script builds the frontend, copies it into the package
as ``hydra/web`` (picked up by hatchling as package data and served at ``/`` by
``create_app``), builds the sdist + wheel, then removes the copied assets so the
working tree stays clean.

Usage:  uv run python scripts/build_release.py
Output: dist/hydralab-<version>.tar.gz and .whl (frontend bundled)
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB_DIST = ROOT / "apps" / "web" / "dist"
PKG_WEB = ROOT / "backend" / "hydra" / "web"


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=ROOT)


def main() -> int:
    run(["bun", "install"])
    run(["bun", "run", "build"])
    if not WEB_DIST.is_dir():
        print(f"error: frontend build not found at {WEB_DIST}", file=sys.stderr)
        return 1

    if PKG_WEB.exists():
        shutil.rmtree(PKG_WEB)
    shutil.copytree(WEB_DIST, PKG_WEB)
    try:
        run(["uv", "build"])
    finally:
        shutil.rmtree(PKG_WEB, ignore_errors=True)

    print("\nBuilt distributables with the web UI bundled:")
    for artifact in sorted((ROOT / "dist").glob("hydralab-*")):
        print(f"  {artifact.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
