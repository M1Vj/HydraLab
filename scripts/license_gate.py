#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ATTRIBUTION = ROOT / "ATTRIBUTION.md"
DEFAULT_ALLOWLIST = Path(__file__).with_name("license_allowlist.json")


@dataclass(frozen=True)
class LicenseRow:
    name: str
    spdx: str
    role: str


@dataclass(frozen=True)
class LicenseFinding:
    name: str
    spdx: str
    reason: str


def load_policy(path: Path = DEFAULT_ALLOWLIST) -> tuple[set[str], tuple[str, ...]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return set(payload["allowed_spdx"]), tuple(payload["denied_spdx_patterns"])


def parse_dependency_register(markdown: str) -> list[LicenseRow]:
    marker = "## Dependency Licensing Register"
    start = markdown.find(marker)
    if start == -1:
        raise ValueError("Dependency Licensing Register heading not found")
    section = markdown[start:]
    next_heading = section.find("\n## ", len(marker))
    if next_heading != -1:
        section = section[:next_heading]

    rows: list[LicenseRow] = []
    for raw_line in section.splitlines():
        line = raw_line.strip()
        if not line.startswith("|") or "---" in line or "SPDX license" in line:
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 4:
            continue
        rows.append(LicenseRow(name=cells[0], spdx=cells[1], role=cells[3]))
    return rows


def _split_spdx_expression(spdx: str) -> list[str]:
    parts = re.split(r"\s*/\s*|\s+OR\s+|\s+AND\s+|,\s*", spdx)
    return [part.strip(" ()") for part in parts if part.strip(" ()")]


def _matches_pattern(value: str, pattern: str) -> bool:
    if pattern.endswith("*"):
        return value.startswith(pattern[:-1])
    return value == pattern


def evaluate_license_rows(
    rows: list[LicenseRow],
    *,
    allowed_spdx: set[str] | None = None,
    denied_spdx_patterns: tuple[str, ...] | None = None,
) -> list[LicenseFinding]:
    if allowed_spdx is None or denied_spdx_patterns is None:
        allowed_spdx, denied_spdx_patterns = load_policy()

    findings: list[LicenseFinding] = []
    for row in rows:
        if row.role != "bundled-dependency":
            continue
        if row.spdx in allowed_spdx:
            continue
        tokens = _split_spdx_expression(row.spdx)
        denied = [token for token in tokens if any(_matches_pattern(token, pattern) for pattern in denied_spdx_patterns)]
        if denied:
            findings.append(LicenseFinding(row.name, row.spdx, f"denied SPDX id(s): {', '.join(denied)}"))
            continue
        unknown = [token for token in tokens if token not in allowed_spdx]
        if unknown:
            findings.append(LicenseFinding(row.name, row.spdx, f"unrecognized SPDX id(s): {', '.join(unknown)}"))
    return findings


def cleared_bundled_dependencies(rows: list[LicenseRow]) -> list[dict[str, str]]:
    return [asdict(row) for row in rows if row.role == "bundled-dependency"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fail if bundled dependencies use denied or unknown SPDX licenses.")
    parser.add_argument("--attribution", type=Path, default=DEFAULT_ATTRIBUTION)
    parser.add_argument("--evidence", type=Path, default=None)
    args = parser.parse_args(argv)

    rows = parse_dependency_register(args.attribution.read_text(encoding="utf-8"))
    findings = evaluate_license_rows(rows)
    if findings:
        for finding in findings:
            print(f"{finding.name}: {finding.spdx} ({finding.reason})", file=sys.stderr)
        return 1
    if args.evidence:
        args.evidence.parent.mkdir(parents=True, exist_ok=True)
        args.evidence.write_text(json.dumps(cleared_bundled_dependencies(rows), indent=2), encoding="utf-8")
    print(f"license gate passed: {len(cleared_bundled_dependencies(rows))} bundled dependencies cleared")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
