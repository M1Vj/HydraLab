"""Compare-stage ranking engine: methods must produce genuinely distinct results.

Guards the 03-02 fix: before it, every scoring method sorted identically by
base_score and only stamped a label. These tests assert the four methods are real
algorithms that diverge in order and score, and stay deterministic.
"""

from __future__ import annotations

import pytest

from hydra.orchestrator.ranking import RANKING_METHODS, rank_candidates

# Crafted so impact (base_score), feasibility (title length) and novelty (hash)
# conflict; a shared sort would collapse all four methods to one ordering.
_CANDIDATES = [
    {"id": "a", "title": "Short", "base_score": 50},
    {"id": "b", "title": "A considerably longer research direction title here", "base_score": 50},
    {"id": "c", "title": "Mid length title text", "base_score": 48},
    {"id": "d", "title": "Tiny", "base_score": 47},
]


def _order(method: str) -> list[str]:
    return [entry["id"] for entry in rank_candidates(_CANDIDATES, method)]


def test_methods_produce_more_than_one_distinct_ordering():
    orderings = {method: tuple(_order(method)) for method in RANKING_METHODS}
    assert len(set(orderings.values())) >= 2, orderings


def test_elo_separates_a_copeland_tie():
    # Copeland (pairwise) ties 'a' and 'b' at 0; Elo's sequential updates break it.
    pairwise = rank_candidates(_CANDIDATES, "pairwise")
    a_score = next(e["score"] for e in pairwise if e["id"] == "a")
    b_score = next(e["score"] for e in pairwise if e["id"] == "b")
    assert a_score == b_score
    elo = rank_candidates(_CANDIDATES, "elo")
    elo_a = next(e["score"] for e in elo if e["id"] == "a")
    elo_b = next(e["score"] for e in elo if e["id"] == "b")
    assert elo_a != elo_b


def test_methods_are_deterministic():
    for method in RANKING_METHODS:
        assert rank_candidates(_CANDIDATES, method) == rank_candidates(_CANDIDATES, method)


def test_score_scales_are_method_specific():
    elo = rank_candidates(_CANDIDATES, "elo")
    rubric = rank_candidates(_CANDIDATES, "rubric")
    # Elo ratings orbit the 1000 base; rubric weighted sums do not.
    assert all(900 < entry["score"] < 1100 for entry in elo)
    assert not all(900 < entry["score"] < 1100 for entry in rubric)


def test_every_candidate_is_ranked_exactly_once():
    for method in RANKING_METHODS:
        ids = _order(method)
        assert sorted(ids) == ["a", "b", "c", "d"]


def test_empty_input_returns_empty():
    assert rank_candidates([], "elo") == []


def test_unknown_method_raises():
    with pytest.raises(ValueError):
        rank_candidates(_CANDIDATES, "coin-flip")
