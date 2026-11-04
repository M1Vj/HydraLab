"""Discovery must not apply arXiv version rules to opaque identifiers."""
import unittest
import tempfile
from pathlib import Path

from hydra.services.discovery.base import normalize_identifier, result_from_dict
from hydra.services.discovery.cache import DiscoveryCache
from hydra.services.discovery.dedupe import dedupe_discovery_results


class DiscoveryIdentifierIdentityTests(unittest.TestCase):
    def result(self, field, value):
        return result_from_dict({field: value, 'title': 'Synthetic paper', 'provider': 'fixture'})

    def test_opaque_version_like_suffixes_remain_distinct(self):
        for field, stem in [('doi', '10.1234/re'), ('url', 'https://example.org/re'),
                            ('url', 'https://example.org/paper?revision='),
                            ('openalex_id', 'Wfixture'), ('s2_id', 'fixture')]:
            with self.subTest(field=field):
                rows = [self.result(field, stem + suffix) for suffix in ('v1', 'v2', '')]
                self.assertEqual(len({row.exact_key() for row in rows}), 3)
                self.assertEqual(len({row.id for row in rows}), 3)
                merged, reviews = dedupe_discovery_results(rows, [])
                self.assertEqual(len(merged), 3)
                self.assertEqual(reviews, [])
                self.assertTrue(all(row.duplicate_state == 'unique' for row in merged))

    def test_doi_resolver_and_case_variants_still_merge(self):
        rows = [self.result('doi', value) for value in
                ['10.1234/Rev1', 'https://doi.org/10.1234/rev1', ' HTTPS://DX.DOI.ORG/10.1234/REV1 ']]
        self.assertEqual({row.exact_key() for row in rows}, {'doi:10.1234/rev1'})
        merged, _ = dedupe_discovery_results(rows, [])
        self.assertEqual(len(merged), 1)
        self.assertEqual(len(merged[0].metadata_sources), 3)

    def test_arxiv_versions_still_share_identity(self):
        for stem in ['2401.12345', 'hep-th/9901001']:
            with self.subTest(stem=stem):
                rows = [self.result('arxiv_id', value) for value in
                        [stem, stem + 'v1', 'arXiv:' + stem + 'v12']]
                self.assertEqual({row.exact_key() for row in rows}, {'arxiv:' + stem})
                merged, _ = dedupe_discovery_results(rows, [])
                self.assertEqual(len(merged), 1)
                self.assertEqual(len(merged[0].metadata_sources), 3)

    def test_doi_takes_priority_over_arxiv(self):
        rows = [result_from_dict({'doi': f'10.1234/rev{i}', 'arxiv_id': '2401.12345v1'})
                for i in (1, 2)]
        self.assertEqual(len(dedupe_discovery_results(rows, [])[0]), 2)

    def test_generic_helper_preserves_suffix_unless_opted_in(self):
        self.assertEqual(normalize_identifier('10.1234/rev1'), '10.1234/rev1')
        self.assertEqual(normalize_identifier('2401.12345v1', strip_arxiv_version=True), '2401.12345')
        for value in (None, '', '   '):
            self.assertIsNone(normalize_identifier(value))

    def test_result_cache_retains_each_doi_after_restart(self):
        rows = [self.result('doi', f'10.1234/rev{i}') for i in (1, 2)]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'discovery.db'
            writer = DiscoveryCache(db_path=path)
            writer.set_query('fixture', 'papers', rows)
            reader = DiscoveryCache(db_path=path)
            for row in rows:
                cached, _ = reader.get_result(row.id)
                self.assertIsNotNone(cached)
                self.assertEqual(cached.doi, row.doi)
