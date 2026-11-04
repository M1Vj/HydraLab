"""Confidence boundaries and real SQLite cache restart regressions."""
from __future__ import annotations

from contextlib import closing, contextmanager
import json
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from hydra.services.discovery.base import result_from_dict
from hydra.services.discovery.cache import DiscoveryCache


@contextmanager
def tracked_connections(fail_prefix=None, fail_commit=False):
    """Keep real handles alive so tests cannot pass through garbage collection."""
    original_connect = sqlite3.connect
    connections = []

    class TrackedConnection(sqlite3.Connection):
        closed = False

        def execute(self, sql, *args, **kwargs):
            result = super().execute(sql, *args, **kwargs)
            if fail_prefix and sql.strip().lower().startswith(fail_prefix):
                raise sqlite3.OperationalError("synthetic database failure")
            return result

        def commit(self):
            if fail_commit:
                raise sqlite3.OperationalError("synthetic database failure")
            return super().commit()

        def close(self):
            super().close()
            self.closed = True

    def connect(*args, **kwargs):
        connection = original_connect(*args, **kwargs, factory=TrackedConnection)
        connections.append(connection)
        return connection

    try:
        with patch.object(sqlite3, "connect", connect):
            yield connections
    finally:
        # Cleanup still runs if a regression assertion fails.
        for connection in connections:
            connection.close()


class DiscoveryConfidenceTests(unittest.TestCase):
    def test_numeric_confidence_survives_serialization(self):
        for value in [0, 0.0, -0.0, 0.25, 0.5, 1, "0", "0.25", "1"]:
            with self.subTest(value=value):
                result = result_from_dict({"title": "Synthetic source", "confidence": value})
                self.assertEqual(result.confidence, float(value))
                self.assertEqual(result_from_dict(result.to_dict()).to_dict(), result.to_dict())

    def test_missing_null_and_empty_string_keep_default(self):
        for payload in [{}, {"confidence": None}, {"confidence": ""}]:
            with self.subTest(payload=payload):
                self.assertEqual(result_from_dict(payload).confidence, 0.5)

    def test_invalid_confidence_is_rejected(self):
        for value in [-0.01, 1.01, float("nan"), float("inf"), "invalid", [], {}, ()]:
            with self.subTest(value=value):
                with self.assertRaises((ValueError, TypeError)):
                    result_from_dict({"confidence": value})

    def test_boolean_uses_python_numeric_conversion(self):
        self.assertEqual(result_from_dict({"confidence": False}).confidence, 0.0)
        self.assertEqual(result_from_dict({"confidence": True}).confidence, 1.0)

    def test_other_fields_keep_their_values(self):
        payload = {"title": "Synthetic paper", "authors": ["Fixture Author"], "year": 2026,
                   "venue": "Fixture", "doi": "10.0000/fixture", "provider": "fixture",
                   "retrieved_at": "2026-10-31T00:00:00Z", "response_status": 200,
                   "confidence": 0, "query": "fixture query", "abstract": "Synthetic abstract"}
        serialized = result_from_dict(payload).to_dict()
        for key, value in payload.items():
            self.assertEqual(serialized[key], value)

    def test_query_cache_restart_keeps_zero_confidence(self):
        # Start with a valid nonzero object, then replace its confidence with zero.
        # This isolates cache decoding even when running against the old decoder.
        from dataclasses import replace
        source = replace(result_from_dict({"confidence": 0.75, "provider": "fixture",
                                         "doi": "10.0000/fixture"}), confidence=0.0)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cache.db"
            writer = DiscoveryCache(db_path=path)
            writer.set_query("fixture", "synthetic query", [source])
            with closing(sqlite3.connect(path)) as connection:
                payload = connection.execute(
                    "SELECT payload_json FROM discovery_cache_entries WHERE cache_key = ?",
                    (writer.query_key("fixture", "synthetic query"),),
                ).fetchone()[0]
            self.assertEqual(json.loads(payload)[0]["confidence"], 0.0)
            reader = DiscoveryCache(db_path=path)
            results, age = reader.get_query("fixture", "synthetic query")
            self.assertIsNotNone(results)
            self.assertGreaterEqual(age, 0)
            self.assertEqual(results[0].confidence, 0.0)
            self.assertEqual(results[0].to_dict(), source.to_dict())

    def test_result_cache_restart_keeps_zero_for_all_keys(self):
        from dataclasses import replace
        source = replace(result_from_dict({"confidence": 0.75, "provider": "fixture",
                                         "doi": "10.0000/fixture"}), confidence=0.0)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cache.db"
            DiscoveryCache(db_path=path).set_query("fixture", "synthetic query", [source])
            for identifier in [source.id, "fixture:id:10.0000/fixture"]:
                with self.subTest(identifier=identifier):
                    result, age = DiscoveryCache(db_path=path).get_result(identifier)
                    self.assertIsNotNone(result)
                    self.assertGreaterEqual(age, 0)
                    self.assertEqual(result.confidence, 0.0)
                    self.assertEqual(result.to_dict(), source.to_dict())


    def test_cache_closes_connections_after_success(self):
        source = result_from_dict({"confidence": 0.25, "provider": "fixture"})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cache.db"
            with tracked_connections() as connections:
                writer = DiscoveryCache(db_path=path)
                writer.set_query("fixture", "query", [source])
                reader = DiscoveryCache(db_path=path)
                self.assertEqual(reader.get_query("fixture", "query")[0][0].confidence, 0.25)
                self.assertEqual(reader.get_result(source.id)[0].confidence, 0.25)
                reader.clear()
                self.assertTrue(connections)
                self.assertTrue(all(connection.closed for connection in connections))
            self.assertIsNone(DiscoveryCache(db_path=path).get_query("fixture", "query")[0])

    def test_cache_closes_and_rolls_back_on_database_errors(self):
        source = result_from_dict({"confidence": 0.25, "provider": "fixture"})
        for prefix in ["create table", "insert or replace", "select payload_json", "delete from", "commit"]:
            with self.subTest(prefix=prefix), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "cache.db"
                cache = DiscoveryCache(db_path=path)
                cache.set_query("fixture", "original", [source])
                with closing(sqlite3.connect(path)) as connection:
                    before = connection.execute("SELECT * FROM discovery_cache_entries ORDER BY cache_key").fetchall()
                with tracked_connections(None if prefix == "commit" else prefix, fail_commit=prefix == "commit") as connections:
                    with self.assertRaisesRegex(sqlite3.OperationalError, "synthetic database failure"):
                        if prefix == "create table":
                            DiscoveryCache(db_path=path)
                        elif prefix in ("insert or replace", "commit"):
                            cache.set_query("fixture", "new query", [source])
                        elif prefix == "select payload_json":
                            DiscoveryCache(db_path=path).get_query("fixture", "original")
                        else:
                            cache.clear()
                    self.assertTrue(connections)
                    self.assertTrue(all(connection.closed for connection in connections))
                with closing(sqlite3.connect(path)) as connection:
                    after = connection.execute("SELECT * FROM discovery_cache_entries ORDER BY cache_key").fetchall()
                self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
