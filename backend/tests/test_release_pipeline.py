from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.license_gate import LicenseRow, evaluate_license_rows, parse_dependency_register
from scripts.package_macos import validate_signed_notarized_artifact
from scripts.release import build_channel_metadata, channel_feed_path


def test_license_gate_fails_seeded_agpl_bundled_dependency():
    findings = evaluate_license_rows(
        [
            LicenseRow(name="bad-agpl", spdx="AGPL-3.0-only", role="bundled-dependency"),
            LicenseRow(name="reference-agpl", spdx="AGPL-3.0-only", role="reference-only"),
        ]
    )

    assert len(findings) == 1
    assert findings[0].name == "bad-agpl"
    assert findings[0].spdx == "AGPL-3.0-only"


def test_real_attribution_register_passes_license_gate():
    rows = parse_dependency_register(Path("ATTRIBUTION.md").read_text(encoding="utf-8"))

    findings = evaluate_license_rows(rows)

    assert findings == []


def test_package_gate_rejects_signed_but_unnotarized_artifact(tmp_path):
    artifact = tmp_path / "HydraLab.app"
    artifact.mkdir()
    (artifact / "release-manifest.json").write_text(json.dumps({"signed": True, "notarized": False}))

    result = validate_signed_notarized_artifact(artifact)

    assert result.ok is False
    assert "not notarized" in result.message


def test_package_gate_accepts_signed_and_notarized_artifact(tmp_path):
    artifact = tmp_path / "release-manifest.json"
    artifact.write_text(json.dumps({"signed": True, "notarized": True}))

    result = validate_signed_notarized_artifact(artifact)

    assert result.ok is True


def test_release_channel_metadata_supports_three_channels():
    for channel in ("stable", "preview", "dev"):
        metadata = build_channel_metadata(channel=channel, version="1.4.0", artifact=f"HydraLab-{channel}.dmg")
        assert metadata.channel == channel
        assert channel_feed_path(channel) == f"releases/{channel}/latest.json"
