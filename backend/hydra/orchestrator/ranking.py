"""Deterministic multi-criteria ranking engine for the Compare stage.

The four scoring methods are genuinely distinct algorithms, not a shared sort
with a relabelled artifact. Each derives three deterministic criteria from a
candidate (impact, feasibility, novelty) and aggregates them differently, so on
conflicting inputs the produced orderings diverge:

* ``rubric``     - transparent weighted sum of the three criteria.
* ``pairwise``   - Copeland method: rank by (wins - losses) of majority-criteria
                   duels over every unordered pair.
* ``elo``        - sequential Elo updates over those same duels; path/quantity
                   dependent, so it can separate candidates the Copeland tally
                   ties, and reorder non-transitive cycles.
* ``tournament`` - single-elimination bracket seeded by impact; upsets (a lower
                   seed winning the majority-criteria duel) reorder against a
                   pure impact sort.

Faithful to the AI co-scientist tournament/Elo ranking of hypotheses: ranking is
driven by pairwise comparison outcomes rather than a single absolute score.

Everything here is a pure function of the candidate list - no clocks, no RNG -
so a given (method, candidates) pair always yields the same ranking.
"""

from __future__ import annotations

import hashlib
from typing import Any

RANKING_METHODS = ("pairwise", "tournament", "elo", "rubric")

# Rubric weights over (impact, feasibility, novelty). Impact dominates but the
# secondary criteria carry enough weight to flip close contests.
_RUBRIC_WEIGHTS = (0.6, 0.25, 0.15)
_ELO_BASE = 1000.0
_ELO_K = 32.0


def _stable_unit(seed: str) -> float:
    """Deterministic value in [0, 100) derived from a string (no RNG)."""
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % 10_000 / 100.0


def _criteria(candidate: dict[str, Any]) -> dict[str, float]:
    """Three deterministic, intentionally non-collinear criteria in [0, 100]."""
    candidate_id = str(candidate.get("id") or "")
    title = str(candidate.get("title") or "")
    impact = float(candidate.get("base_score") or candidate.get("score") or 0)
    # Feasibility rewards concise, actionable titles; novelty is a stable hash so
    # it is uncorrelated with impact/feasibility, which is what lets the methods
    # disagree on order.
    feasibility = max(0.0, 100.0 - float(len(title)))
    novelty = _stable_unit(f"{candidate_id}:{title}")
    return {"impact": impact, "feasibility": feasibility, "novelty": novelty}


def _duel(a: dict[str, float], b: dict[str, float]) -> int:
    """Majority-of-criteria comparison: +1 if a beats b, -1 if b beats a, else 0."""
    wins = sum(1 for key in ("impact", "feasibility", "novelty") if a[key] > b[key])
    losses = sum(1 for key in ("impact", "feasibility", "novelty") if a[key] < b[key])
    if wins > losses:
        return 1
    if losses > wins:
        return -1
    return 0


def _entry(candidate: dict[str, Any], score: float) -> dict[str, Any]:
    return {
        "id": candidate.get("id"),
        "title": candidate.get("title"),
        "score": round(float(score), 4),
    }


def _rubric(candidates: list[dict[str, Any]], crit: dict[str, dict[str, float]]) -> list[dict[str, Any]]:
    wi, wf, wn = _RUBRIC_WEIGHTS
    scored = [
        _entry(c, wi * crit[cid]["impact"] + wf * crit[cid]["feasibility"] + wn * crit[cid]["novelty"])
        for c, cid in ((c, str(c.get("id") or "")) for c in candidates)
    ]
    return sorted(scored, key=lambda item: (-item["score"], str(item["id"])))


def _pairwise(candidates: list[dict[str, Any]], crit: dict[str, dict[str, float]]) -> list[dict[str, Any]]:
    ids = [str(c.get("id") or "") for c in candidates]
    copeland = {cid: 0 for cid in ids}
    for i, a_id in enumerate(ids):
        for b_id in ids[i + 1 :]:
            outcome = _duel(crit[a_id], crit[b_id])
            copeland[a_id] += outcome
            copeland[b_id] -= outcome
    scored = [_entry(c, copeland[str(c.get("id") or "")]) for c in candidates]
    return sorted(scored, key=lambda item: (-item["score"], str(item["id"])))


def _elo(candidates: list[dict[str, Any]], crit: dict[str, dict[str, float]]) -> list[dict[str, Any]]:
    ids = [str(c.get("id") or "") for c in candidates]
    rating = {cid: _ELO_BASE for cid in ids}
    for i, a_id in enumerate(ids):
        for b_id in ids[i + 1 :]:
            outcome = _duel(crit[a_id], crit[b_id])
            actual_a = 0.5 + 0.5 * outcome  # 1.0 win / 0.5 draw / 0.0 loss
            expected_a = 1.0 / (1.0 + 10 ** ((rating[b_id] - rating[a_id]) / 400.0))
            rating[a_id] += _ELO_K * (actual_a - expected_a)
            rating[b_id] += _ELO_K * ((1.0 - actual_a) - (1.0 - expected_a))
    scored = [_entry(c, rating[str(c.get("id") or "")]) for c in candidates]
    return sorted(scored, key=lambda item: (-item["score"], str(item["id"])))


def _tournament(candidates: list[dict[str, Any]], crit: dict[str, dict[str, float]]) -> list[dict[str, Any]]:
    by_id = {str(c.get("id") or ""): c for c in candidates}
    # Seed by impact (then id) so the bracket is deterministic; upsets come from
    # the majority-criteria duel, not the seeding.
    seeds = sorted(by_id, key=lambda cid: (-crit[cid]["impact"], cid))
    placement: dict[str, int] = {}  # higher = eliminated later / better
    round_no = 0
    field = list(seeds)
    while len(field) > 1:
        round_no += 1
        winners: list[str] = []
        losers: list[str] = []
        # Standard bracket pairing: top seed vs bottom seed inward.
        pairs = [(field[k], field[len(field) - 1 - k]) for k in range(len(field) // 2)]
        for high, low in pairs:
            outcome = _duel(crit[high], crit[low])
            winner, loser = (high, low) if outcome >= 0 else (low, high)
            winners.append(winner)
            losers.append(loser)
        if len(field) % 2 == 1:  # odd field: middle seed gets a bye
            winners.insert(len(winners) // 2, field[len(field) // 2])
        for loser in losers:
            placement.setdefault(loser, round_no)
        field = winners
    if field:
        placement[field[0]] = round_no + 1  # champion
    scored = [_entry(by_id[cid], placement.get(cid, 0)) for cid in seeds]
    # Break ties within a placement round by seed order (impact then id).
    seed_rank = {cid: index for index, cid in enumerate(seeds)}
    return sorted(scored, key=lambda item: (-item["score"], seed_rank[str(item["id"])]))


_ALGORITHMS = {
    "rubric": _rubric,
    "pairwise": _pairwise,
    "elo": _elo,
    "tournament": _tournament,
}


def rank_candidates(candidates: list[dict[str, Any]], method: str) -> list[dict[str, Any]]:
    """Rank ``candidates`` with ``method``; returns ``[{id, title, score}]`` best-first."""
    if method not in _ALGORITHMS:
        allowed = ", ".join(sorted(RANKING_METHODS))
        raise ValueError(f"unsupported ranking method {method!r}; must be one of {allowed}")
    materialized = [dict(candidate) for candidate in candidates]
    if not materialized:
        return []
    crit = {str(c.get("id") or ""): _criteria(c) for c in materialized}
    return _ALGORITHMS[method](materialized, crit)
