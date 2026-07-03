"""Bundled dependency metadata for the manuscript export path."""

from __future__ import annotations


def bundled_export_dependencies() -> list[dict[str, str]]:
    return [
        {"name": "python-docx", "spdx": "MIT", "scope": "bundled-dependency"},
        {"name": "citeproc-py", "spdx": "BSD-2-Clause-Views", "scope": "bundled-dependency"},
        {"name": "ruamel.yaml", "spdx": "MIT", "scope": "bundled-dependency"},
    ]
