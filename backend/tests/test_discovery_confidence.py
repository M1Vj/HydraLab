"""Confidence boundaries and real SQLite cache restart regressions."""
from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from hydra.services.discovery.base import result_from_dict
from hydra.services.discovery.cache import DiscoveryCache


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
            with sqlite3.connect(path) as connection:
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


if __name__ == "__main__":
    unittest.main()
