"""Identifier refresh must not masquerade as a complete query search."""
import asyncio
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from hydra.services.discovery.base import result_from_dict
from hydra.services.discovery.cache import DiscoveryCache
from hydra.services.discovery.coordinator import DiscoveryCoordinator

class Provider:
    name = "synthetic"
    def __init__(self, result):
        self.result = result
        self.search_calls = 0
    async def fetch_by_id(self, identifier, config):
        return self.result
    async def search(self, query, config):
        self.search_calls += 1
        return [self.result.with_query(query)]

class RefreshCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "cache.sqlite"
        self.a = result_from_dict({"title": "original", "doi": "10.1/a", "provider": "synthetic"})
        self.b = result_from_dict({"title": "other", "doi": "10.1/b", "provider": "synthetic"})
        self.fresh = result_from_dict({"title": "refreshed", "doi": "10.1/a", "provider": "synthetic"})
    def refresh(self, cache):
        return asyncio.run(DiscoveryCoordinator(providers=[Provider(self.fresh)], cache=cache).refresh("10.1/a", "query"))
    def test_refresh_preserves_full_query_and_timestamp(self):
        for persist in (False, True):
            with self.subTest(persist=persist):
                cache = DiscoveryCache(db_path=self.path, persist=persist)
                with patch("hydra.services.discovery.cache.time.time", return_value=1000):
                    cache.set_query("synthetic", "query", [self.a, self.b])
                with patch("hydra.services.discovery.cache.time.time", return_value=1050):
                    response = self.refresh(cache)
                    self.assertEqual(response["result"]["title"], "refreshed")
                    if persist:
                        cache = DiscoveryCache(db_path=self.path)
                    rows, age = cache.get_query("synthetic", "query")
                    self.assertEqual([r.title for r in rows], ["original", "other"])
                    self.assertEqual(age, 50)
                    result, result_age = cache.get_result(self.a.id)
                    self.assertEqual(result.title, "refreshed")
                    self.assertEqual(result_age, 0)
                    self.assertEqual(cache.get_result("synthetic:id:10.1/a")[0].title, "refreshed")
    def test_refresh_does_not_create_query_hit(self):
        for persist in (False, True):
            with self.subTest(persist=persist):
                cache = DiscoveryCache(db_path=self.path, persist=persist)
                cache.clear()
                self.refresh(cache)
                if persist:
                    cache = DiscoveryCache(db_path=self.path)
                self.assertEqual(cache.get_query("synthetic", "query"), (None, None))
                provider = Provider(self.fresh)
                result = asyncio.run(DiscoveryCoordinator(providers=[provider], cache=cache).search("query"))
                self.assertEqual(provider.search_calls, 1)
                self.assertFalse(result["cache_hit"])
    def test_refresh_does_not_extend_expired_query(self):
        cache = DiscoveryCache(db_path=self.path, ttl_seconds=10)
        with patch("hydra.services.discovery.cache.time.time", return_value=1000):
            cache.set_query("synthetic", "query", [self.a, self.b])
        with patch("hydra.services.discovery.cache.time.time", return_value=1020):
            self.refresh(cache)
            self.assertIsNone(cache.get_query("synthetic", "query")[0])
            self.assertEqual(cache.get_result(self.a.id)[0].title, "refreshed")
    def test_no_match_leaves_cache_unchanged(self):
        cache = DiscoveryCache(db_path=self.path)
        cache.set_query("synthetic", "query", [self.a, self.b])
        result = asyncio.run(DiscoveryCoordinator(providers=[Provider(None)], cache=cache).refresh("missing", "query"))
        self.assertIsNone(result["result"])
        self.assertEqual(len(cache.get_query("synthetic", "query")[0]), 2)
