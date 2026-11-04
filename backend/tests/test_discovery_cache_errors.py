"""Discovery isolates failed cache reads without calling a provider as fallback."""
from __future__ import annotations

import asyncio
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from hydra.services.discovery.base import result_from_dict
from hydra.services.discovery.cache import DiscoveryCache
from hydra.services.discovery.coordinator import DiscoveryCoordinator


class SyntheticProvider:
    def __init__(self, name: str):
        self.name = name
        self.calls = 0

    async def search(self, query, config):
        self.calls += 1
        return [result_from_dict({"title": self.name, "provider": self.name, "query": query})]


class DiscoveryCacheErrorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.db = Path(self.temporary.name) / "synthetic.sqlite"
        self.query = "synthetic cache read"

    def make_cache(self, payload=None):
        cache = DiscoveryCache(db_path=self.db)
        cache.set_query("broken", self.query, [])
        if payload is not None:
            with closing(sqlite3.connect(self.db)) as conn:
                conn.execute("UPDATE discovery_cache_entries SET payload_json = ? WHERE cache_key = ?", (payload, cache.query_key("broken", self.query)))
                conn.commit()
        # Reopen so the real SQLite/JSON read runs, rather than the memory hit.
        return DiscoveryCache(db_path=self.db)

    def search(self, cache, providers, **kwargs):
        return asyncio.run(DiscoveryCoordinator(cache=cache, providers=providers).search(self.query, **kwargs))

    def test_corrupt_json_keeps_healthy_provider_results(self):
        broken, healthy = SyntheticProvider("broken"), SyntheticProvider("healthy")
        result = self.search(self.make_cache('{"private-fragment":'), [broken, healthy])
        self.assertEqual(result["state"], "partial")
        self.assertEqual([row["title"] for row in result["results"]], ["healthy"])
        self.assertEqual((broken.calls, healthy.calls), (0, 1))
        self.assertEqual(result["provider_statuses"], [{"provider": "broken", "state": "error", "error": "JSONDecodeError"}, {"provider": "healthy", "state": "ready", "count": 1}])
        self.assertNotIn("private-fragment", repr(result))

    def test_corrupt_cache_only_reports_failure(self):
        broken = SyntheticProvider("broken")
        result = self.search(self.make_cache("not-json"), [broken])
        self.assertEqual(result["state"], "failure")
        self.assertEqual(result["results"], [])
        self.assertEqual(broken.calls, 0)

    def test_invalid_decoded_record_is_isolated(self):
        for payload, error in [('null', 'TypeError'), ('[null]', 'AttributeError'), ('[{"confidence": 2}]', 'ValueError')]:
            with self.subTest(payload=payload):
                broken = SyntheticProvider("broken")
                result = self.search(self.make_cache(payload), [broken])
                self.assertEqual(result["state"], "failure")
                self.assertEqual(result["provider_statuses"][0]["error"], error)
                self.assertEqual(broken.calls, 0)

    def test_offline_modes_do_not_fall_back_to_provider(self):
        for kwargs in [{"offline_only": True}, {"scholarly_apis_enabled": False}]:
            with self.subTest(kwargs=kwargs):
                cache = self.make_cache("not-json")
                cache.set_query("healthy", self.query, [result_from_dict({"title": "cached", "provider": "healthy"})])
                providers = [SyntheticProvider(name) for name in ["broken", "healthy", "missing"]]
                result = self.search(DiscoveryCache(db_path=self.db), providers, **kwargs)
                self.assertEqual(result["state"], "offline-permission")
                self.assertTrue(result["cache_hit"])
                self.assertEqual([row["title"] for row in result["results"]], ["cached"])
                self.assertEqual([provider.calls for provider in providers], [0, 0, 0])
                self.assertEqual([status["state"] for status in result["provider_statuses"]], ["error", "cache-hit", "offline"])

    def test_sqlite_error_is_isolated_and_details_are_not_returned(self):
        cache = self.make_cache()
        original = cache.get_query
        def get_query(provider, query):
            if provider == "broken":
                raise sqlite3.OperationalError("synthetic-private-path")
            return original(provider, query)
        providers = [SyntheticProvider("broken"), SyntheticProvider("healthy")]
        with patch.object(cache, "get_query", side_effect=get_query):
            result = self.search(cache, providers)
        self.assertEqual(result["state"], "partial")
        self.assertEqual(result["provider_statuses"][0]["error"], "OperationalError")
        self.assertNotIn("synthetic-private-path", repr(result))
        self.assertEqual([provider.calls for provider in providers], [0, 1])

    def test_valid_empty_cache_remains_hit_without_network(self):
        provider = SyntheticProvider("broken")
        result = self.search(self.make_cache(), [provider])
        self.assertEqual(result["state"], "empty")
        self.assertTrue(result["cache_hit"])
        self.assertEqual(result["provider_statuses"][0]["state"], "cache-hit")
        self.assertEqual(provider.calls, 0)

    def test_cancellation_is_not_converted_to_provider_error(self):
        cache = self.make_cache()
        with patch.object(cache, "get_query", side_effect=asyncio.CancelledError):
            with self.assertRaises(asyncio.CancelledError):
                self.search(cache, [SyntheticProvider("broken")])


if __name__ == "__main__":
    unittest.main()
