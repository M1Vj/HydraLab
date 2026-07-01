from __future__ import annotations

import json
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MigrationReport:
    id_map: dict[str, dict[str, str]]
    zero_dangling: bool
    report_path: Path


def migrate_legacy_hydra_project(project_root: Path) -> MigrationReport:
    project_root = Path(project_root)
    legacy_db = project_root / ".hydra" / "hydra.db"
    if not legacy_db.exists():
        raise FileNotFoundError(legacy_db)

    target_dir = project_root / ".hydralab"
    target_dir.mkdir(exist_ok=True)
    logs_dir = target_dir / "logs"
    logs_dir.mkdir(exist_ok=True)
    target_db = target_dir / "hydralab.db"
    if target_db.exists():
        target_db.unlink()

    id_map: dict[str, dict[str, str]] = {"sources": {}, "claims": {}, "evidence_links": {}, "annotations": {}}
    legacy = sqlite3.connect(legacy_db)
    target = sqlite3.connect(target_db)
    try:
        _create_target_tables(target)
        target.execute("begin")

        for source_id, title in legacy.execute("select id, title from sources"):
            id_map["sources"][source_id] = source_id
            target.execute("insert into sources (id, title) values (?, ?)", (source_id, title))

        for claim_id, location_type, location_id, text in legacy.execute("select id, location_type, location_id, text from claims"):
            id_map["claims"][claim_id] = claim_id
            new_location_id = id_map.get("sources", {}).get(location_id, location_id)
            target.execute(
                "insert into claims (id, location_type, location_id, text) values (?, ?, ?, ?)",
                (claim_id, location_type, new_location_id, text),
            )

        for evidence_id, claim_id, source_id, passage in legacy.execute("select id, claim_id, source_id, passage from evidence_links"):
            id_map["evidence_links"][evidence_id] = evidence_id
            target.execute(
                "insert into evidence_links (id, claim_id, source_id, passage) values (?, ?, ?, ?)",
                (evidence_id, id_map["claims"][claim_id], id_map["sources"][source_id], passage),
            )

        for ann_id, source_id, text in legacy.execute("select sidecar_record_id, source_id, text from annotations"):
            id_map["annotations"][ann_id] = ann_id
            target.execute(
                "insert into annotations (sidecar_record_id, source_id, text) values (?, ?, ?)",
                (ann_id, id_map["sources"][source_id], text),
            )

        zero_dangling = _zero_dangling(target)
        if not zero_dangling:
            target.rollback()
        else:
            target.commit()
    finally:
        legacy.close()
        target.close()

    report_path = logs_dir / "hydra-to-hydralab-migration.json"
    report_path.write_text(json.dumps({"id_map": id_map, "zero_dangling": zero_dangling}, indent=2, sort_keys=True))
    return MigrationReport(id_map=id_map, zero_dangling=zero_dangling, report_path=report_path)


def _create_target_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        create table sources (id text primary key, title text);
        create table claims (id text primary key, location_type text, location_id text, text text);
        create table evidence_links (id text primary key, claim_id text, source_id text, passage text);
        create table annotations (sidecar_record_id text primary key, source_id text, text text);
        create table schema_versions (component text primary key, version text);
        insert into schema_versions values ('database', '2026.01.02');
        """
    )


def _zero_dangling(conn: sqlite3.Connection) -> bool:
    dangling_evidence = conn.execute(
        """
        select count(*)
        from evidence_links e
        left join sources s on s.id = e.source_id
        left join claims c on c.id = e.claim_id
        where s.id is null or c.id is null
        """
    ).fetchone()[0]
    dangling_claims = conn.execute(
        """
        select count(*)
        from claims c
        left join sources s on s.id = c.location_id
        where c.location_type = 'source' and s.id is null
        """
    ).fetchone()[0]
    dangling_annotations = conn.execute(
        """
        select count(*)
        from annotations a
        left join sources s on s.id = a.source_id
        where s.id is null
        """
    ).fetchone()[0]
    return dangling_evidence == 0 and dangling_claims == 0 and dangling_annotations == 0
