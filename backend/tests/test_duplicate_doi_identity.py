"""Offline regressions for DOI identity in duplicate classification."""
import importlib.util
from pathlib import Path
import sys
import unittest

_PATH = Path(__file__).parents[1] / "hydra/services/citations/duplicates.py"
_SPEC = importlib.util.spec_from_file_location("_hydra_duplicate_identity_tests", _PATH)
duplicates = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = duplicates
_SPEC.loader.exec_module(duplicates)

class DoiIdentityTests(unittest.TestCase):
    def test_distinct_names_do_not_become_exact_matches(self):
        pairs = [
            ("10.1000/a-b", "10.1000/ab"),
            ("10.1000/a.b", "10.1000/ab"),
            ("10.1000/a_b", "10.1000/ab"),
            ("10.1000/a/b", "10.1000/ab"),
            ("10.1000/a(b)", "10.1000/ab"),
            ("10.1000/a:b", "10.1000/ab"),
            ("10.1000/a;b", "10.1000/ab"),
            ("10.1000/a+b", "10.1000/ab"),
            ("10.1000/é", "10.1000/e"),
            ("10.1000/É", "10.1000/é"),
            ("10.1000/α", "10.1000/β"),
            ("10.1000/ab", "101.000/ab"),
        ]
        for left, right in pairs:
            for nested in (False, True):
                with self.subTest(left=left, right=right, nested=nested):
                    a = {"identifiers": {"doi": left}} if nested else {"doi": left}
                    b = {"identifiers": {"doi": right}} if nested else {"doi": right}
                    self.assertEqual(duplicates.classify_pair(a, b).status, "none")

    def test_ascii_case_still_matches(self):
        for key in ("doi", "identifiers"):
            a = {"doi": "10.1000/A-b.É"}
            b = {"doi": "10.1000/a-B.É"}
            if key == "identifiers":
                a, b = {"identifiers": a}, {"identifiers": b}
            self.assertEqual(duplicates.classify_pair(a, b).status, "auto_merge")

    def test_top_level_and_nested_names_match(self):
        self.assertEqual(duplicates.classify_pair(
            {"doi": "10.1000/A-b"}, {"identifiers": {"doi": "10.1000/a-B"}}
        ).status, "auto_merge")

    def test_nested_doi_does_not_restore_lossy_matching(self):
        self.assertEqual(duplicates.classify_pair(
            {"doi": "10.1000/a-b", "identifiers": {"doi": "10.1000/a-b"}},
            {"doi": "10.1000/ab", "identifiers": {"doi": "10.1000/ab"}},
        ).status, "none")

    def test_distinct_names_allow_fuzzy_review_not_automatic_merge(self):
        self.assertEqual(duplicates.classify_pair(
            {"doi": "10.1000/a-b", "title": "Identical paper title"},
            {"doi": "10.1000/ab", "title": "Identical paper title"},
        ).status, "needs_review")

    def test_other_identifiers_keep_existing_behavior(self):
        for field, left, right in [
            ("arxiv_id", "arXiv:1706.03762v2", "1706.03762"),
            ("file_hash", "ABC123", "abc123"),
            ("content_hash", "ABC123", "abc123"),
        ]:
            self.assertEqual(duplicates.classify_pair({field: left}, {field: right}).status, "auto_merge")

    def test_missing_names_do_not_match(self):
        for value in ("", None, "---", "   ", "...", "αβ"):
            self.assertEqual(duplicates.classify_pair({"doi": value}, {"doi": value}).status, "none")

    def test_pair_scan_preserves_sources_and_filters_hidden(self):
        sources = [
            {"id": "a", "doi": "10.1000/A-b"},
            {"id": "b", "doi": "10.1000/ab"},
            {"id": "c", "doi": "10.1000/a-B"},
            {"id": "d", "doi": "10.1000/A-b", "trashed": True},
            {"id": "e", "doi": "10.1000/A-b", "merged_into_source_id": "a"},
        ]
        before = [dict(s) for s in sources]
        found = duplicates.find_duplicates(sources)
        self.assertEqual([(v["left_id"], v["right_id"]) for v in found], [("a", "c")])
        self.assertEqual(sources, before)

if __name__ == "__main__":
    unittest.main()

