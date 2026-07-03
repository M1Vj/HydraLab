"""Safe SQLite backup + project restore (HL-EXPORT-05 / HL-EXPORT-06, Section 26.16).

A backup uses the SQLite online-backup API (``sqlite3.Connection.backup``), which
takes a transactionally-consistent snapshot of a live database — it never copies a
mid-write file byte-for-byte. The restored copy is verified with ``PRAGMA
integrity_check`` before being reported as usable.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional


def safe_sqlite_backup(source_db_path: Path, dest_path: Path) -> dict[str, Any]:
    source_db_path = Path(source_db_path)
    dest_path = Path(dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    source = sqlite3.connect(str(source_db_path))
    dest = sqlite3.connect(str(dest_path))
    try:
        # Online backup API: safe against concurrent writers, no live file copy.
        with dest:
            source.backup(dest)
    finally:
        source.close()
        dest.close()

    verify = sqlite3.connect(str(dest_path))
    try:
        integrity = verify.execute("PRAGMA integrity_check").fetchone()
        integrity_ok = bool(integrity and integrity[0] == "ok")
    finally:
        verify.close()

    return {
        "backup_path": str(dest_path),
        "method": "sqlite-online-backup",
        "integrity_ok": integrity_ok,
        "live_file_copied": False,
    }


async def restore_project(
    project_root: Path,
    *,
    reindex: Optional[Callable[[], Awaitable[list[str]]]] = None,
) -> dict[str, Any]:
    """Reopen a project folder and rebuild its search index where possible.

    Emits a progress structure so the UI can surface a progress state.
    """
    project_root = Path(project_root).resolve()
    progress: list[dict[str, Any]] = [
        {"step": "open_folder", "status": "done", "path": str(project_root)},
    ]
    if not project_root.exists():
        progress.append({"step": "reindex", "status": "skipped", "reason": "folder missing"})
        return {"reopened": False, "progress": progress, "reindexed": []}

    reindexed: list[str] = []
    if reindex is not None:
        progress.append({"step": "reindex", "status": "running"})
        reindexed = await reindex()
        progress[-1] = {"step": "reindex", "status": "done", "count": len(reindexed)}
    else:
        progress.append({"step": "reindex", "status": "skipped", "reason": "no reindexer bound"})

    return {"reopened": True, "progress": progress, "reindexed": reindexed}
