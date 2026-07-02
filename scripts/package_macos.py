#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ArtifactCheck:
    ok: bool
    message: str


def _read_manifest(artifact_path: Path) -> dict:
    if artifact_path.is_dir():
        manifest = artifact_path / "release-manifest.json"
    else:
        manifest = artifact_path
    return json.loads(manifest.read_text(encoding="utf-8"))


def validate_signed_notarized_artifact(artifact_path: Path) -> ArtifactCheck:
    payload = _read_manifest(Path(artifact_path))
    if not payload.get("signed"):
        return ArtifactCheck(False, "artifact is not signed")
    if not payload.get("notarized"):
        return ArtifactCheck(False, "artifact is not notarized")
    return ArtifactCheck(True, "artifact is signed and notarized")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a simulated macOS release artifact before upload.")
    parser.add_argument("artifact", type=Path)
    args = parser.parse_args(argv)
    result = validate_signed_notarized_artifact(args.artifact)
    output = sys.stdout if result.ok else sys.stderr
    print(result.message, file=output)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
