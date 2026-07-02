#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

CHANNELS = ("stable", "preview", "dev")


@dataclass(frozen=True)
class ChannelMetadata:
    channel: str
    version: str
    artifact: str
    previous_installer: str | None = None


def channel_feed_path(channel: str) -> str:
    if channel not in CHANNELS:
        raise ValueError(f"channel must be one of {', '.join(CHANNELS)}")
    return f"releases/{channel}/latest.json"


def build_channel_metadata(
    *,
    channel: str,
    version: str,
    artifact: str,
    previous_installer: str | None = None,
) -> ChannelMetadata:
    channel_feed_path(channel)
    return ChannelMetadata(channel, version, artifact, previous_installer)


def retain_previous_installer(previous_installer: str, retention_dir: Path) -> Path:
    retention_dir.mkdir(parents=True, exist_ok=True)
    retained = retention_dir / Path(previous_installer).name
    retained.write_text(str(previous_installer), encoding="utf-8")
    return retained


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write simulated HydraLab release channel metadata.")
    parser.add_argument("--channel", required=True, choices=CHANNELS)
    parser.add_argument("--version", required=True)
    parser.add_argument("--artifact", required=True)
    parser.add_argument("--previous-installer")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    metadata = build_channel_metadata(
        channel=args.channel,
        version=args.version,
        artifact=args.artifact,
        previous_installer=args.previous_installer,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(asdict(metadata), indent=2), encoding="utf-8")
    print(f"wrote {channel_feed_path(args.channel)} metadata to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
