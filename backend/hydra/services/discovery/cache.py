from __future__ import annotations

import time
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from hydra.database.session import get_db_url
from hydra.services.discovery.base import DiscoveryResult, query_hash, result_from_dict


@dataclass
class CacheEntry:
    results: list[DiscoveryResult]
    created_at: float


class DiscoveryCache:
    def __init__(self, ttl_seconds: int = 24 * 60 * 60, db_path: Path | None = None, persist: bool | None = None):
        self.ttl_seconds = ttl_seconds
        self.db_path = db_path or _db_path_from_url(get_db_url())
        self.persist = (db_path is not None) if persist is None else persist
        self._query_entries: dict[str, CacheEntry] = {}
        self._result_entries: dict[str, CacheEntry] = {}
        if self.persist:
            self._ensure_table()

    def query_key(self, provider: str, query: str) -> str:
        return f"{provider}:query:{query_hash(query)}"

    def get_query(self, provider: str, query: str) -> tuple[list[DiscoveryResult] | None, int | None]:
        entry = self._query_entries.get(self.query_key(provider, query))
        if not entry:
            entry = self._load_query(provider, query)
            if entry is None:
                return None, None
            self._query_entries[self.query_key(provider, query)] = entry
        age = int(time.time() - entry.created_at)
        if age > self.ttl_seconds:
            return None, age
        return entry.results, age

    def set_query(self, provider: str, query: str, results: list[DiscoveryResult]) -> None:
        now = time.time()
        key = self.query_key(provider, query)
        entry = CacheEntry(results=results, created_at=now)
        self._query_entries[key] = entry
        self._store_entry(key, provider, query_hash(query), None, results, now)
        for result in results:
            result_entry = CacheEntry(results=[result], created_at=now)
            self._result_entries[result.id] = result_entry
            self._store_entry(result.id, provider, query_hash(query), result.id, [result], now)
            for exact in filter(None, [result.doi, result.arxiv_id, result.openalex_id, result.s2_id, result.url]):
                exact_key = f"{provider}:id:{exact}".lower()
                self._result_entries[exact_key] = result_entry
                self._store_entry(exact_key, provider, query_hash(query), str(exact), [result], now)

    def get_result(self, identifier: str) -> tuple[DiscoveryResult | None, int | None]:
        entry = self._result_entries.get(identifier) or self._result_entries.get(identifier.lower())
        if not entry:
            entry = self._load_result(identifier)
            if entry is None:
                return None, None
            self._result_entries[identifier] = entry
        age = int(time.time() - entry.created_at)
        if age > self.ttl_seconds:
            return None, age
        return entry.results[0], age

    def clear(self) -> None:
        self._query_entries.clear()
        self._result_entries.clear()
        if self.persist:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("delete from discovery_cache_entries")
                conn.commit()

    def _ensure_table(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                create table if not exists discovery_cache_entries (
                    cache_key text primary key,
                    provider text not null,
                    query_hash text not null,
                    identifier text,
                    payload_json text not null,
                    created_at datetime not null,
                    expires_at datetime not null
                )
                """
            )
            conn.execute("create index if not exists ix_discovery_cache_provider on discovery_cache_entries(provider)")
            conn.execute("create index if not exists ix_discovery_cache_query_hash on discovery_cache_entries(query_hash)")
            conn.execute("create index if not exists ix_discovery_cache_identifier on discovery_cache_entries(identifier)")
            conn.commit()

    def _store_entry(
        self,
        cache_key: str,
        provider: str,
        qhash: str,
        identifier: str | None,
        results: list[DiscoveryResult],
        created_at: float,
    ) -> None:
        if not self.persist:
            return
        expires_at = created_at + self.ttl_seconds
        payload = json.dumps([result.to_dict() for result in results], sort_keys=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                insert or replace into discovery_cache_entries
                (cache_key, provider, query_hash, identifier, payload_json, created_at, expires_at)
                values (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cache_key,
                    provider,
                    qhash,
                    identifier,
                    payload,
                    datetime.fromtimestamp(created_at, timezone.utc).isoformat(),
                    datetime.fromtimestamp(expires_at, timezone.utc).isoformat(),
                ),
            )
            conn.commit()

    def _load_query(self, provider: str, query: str) -> CacheEntry | None:
        return self._load_key(self.query_key(provider, query))

    def _load_result(self, identifier: str) -> CacheEntry | None:
        return self._load_key(identifier) or self._load_key(identifier.lower())

    def _load_key(self, cache_key: str) -> CacheEntry | None:
        if not self.persist or not self.db_path.exists():
            return None
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "select payload_json, created_at, expires_at from discovery_cache_entries where cache_key = ?",
                (cache_key,),
            ).fetchone()
        if row is None:
            return None
        expires_at = datetime.fromisoformat(row[2]).timestamp()
        if time.time() > expires_at:
            return None
        created_at = datetime.fromisoformat(row[1]).timestamp()
        return CacheEntry(results=[result_from_dict(item) for item in json.loads(row[0])], created_at=created_at)


def _db_path_from_url(db_url: str) -> Path:
    prefix = "sqlite+aiosqlite:///"
    if db_url.startswith(prefix):
        return Path(db_url.removeprefix(prefix))
    return Path(".hydra") / "hydra.db"
