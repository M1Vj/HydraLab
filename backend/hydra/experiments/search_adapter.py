"""MLEvolve-style bounded search adapter (HL-SAFE-13/17).

A small prototype of the propose -> run -> read-metric -> rank loop. It is
reference-inspired by MLEvolve (studied as a search *pattern*, never vendored),
reimplemented entirely through HydraLab-owned contracts: every candidate is
submitted as a real, gated ``ExperimentRun`` through :class:`ExperimentRunner`,
and the loop is bounded by a candidate budget so it can never run unbounded work
or exceed the configured ceiling.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from hydra.experiments import models as run_status
from hydra.experiments.runner import ExperimentRunner


@dataclass
class SearchBudget:
    max_candidates: int = 4
    metric_key: str = "score"
    direction: str = "max"  # "max" | "min"


@dataclass
class Candidate:
    candidate_id: str
    config: dict
    status: str = run_status.STATUS_PENDING
    metric: Optional[float] = None
    run_id: Optional[str] = None


@dataclass
class SearchResult:
    ranked: list[Candidate] = field(default_factory=list)
    submitted: int = 0
    budget: Optional[SearchBudget] = None

    @property
    def best(self) -> Optional[Candidate]:
        return self.ranked[0] if self.ranked else None


def default_proposer(base_config: dict, index: int) -> dict:
    """Vary one numeric parameter across candidates (no ML dependency needed)."""
    proposed = dict(base_config)
    seed = float(base_config.get("seed", 0.1))
    proposed["candidate_index"] = index
    proposed["param"] = round(seed * (index + 1), 4)
    return proposed


class SearchAdapter:
    def __init__(
        self,
        runner: ExperimentRunner,
        *,
        proposer: Callable[[dict, int], dict] = default_proposer,
    ) -> None:
        self.runner = runner
        self.proposer = proposer

    async def run_search(
        self,
        *,
        project_id: str,
        backend_id: str,
        base_config: dict,
        budget: SearchBudget,
        argv_builder: Callable[[dict], list[str]],
        trust_origin: str = "user",
        justification_trust: str = "user",
    ) -> SearchResult:
        # Trust provenance is threaded from the caller, never hardcoded: an
        # untrusted-origin caller (e.g. an agent-driven search) produces
        # candidates that ``create_run`` routes to the Review Inbox with no
        # ``approval_id``, so the auto-approve/auto-start path below is skipped
        # and a human must promote them. This prevents trust laundering.
        result = SearchResult(budget=budget)
        for index in range(max(1, budget.max_candidates)):
            config = self.proposer(base_config, index)
            argv = argv_builder(config)
            proposal = await self.runner.create_run(
                project_id=project_id,
                backend_id=backend_id,
                config={**config, "argv": argv, "metric_key": budget.metric_key},
                label=f"search-candidate-{index}",
                trust_origin=trust_origin,
                justification_trust=justification_trust,
            )
            candidate = Candidate(candidate_id=f"candidate-{index}", config=config, run_id=proposal.run.id)
            # Every candidate stays fully gated: approve the per-run approval, then
            # start. A run that cannot be approved (e.g. untrusted) is skipped.
            if proposal.approval_id:
                await self.runner.approve_run(proposal.run.id)
                run = await self.runner.start_run(proposal.run.id, argv=argv)
                candidate.status = run.status
                metrics = _load_metrics(run)
                candidate.metric = metrics.get(budget.metric_key)
            else:
                candidate.status = proposal.status
            result.ranked.append(candidate)
            result.submitted += 1
        result.ranked = _rank(result.ranked, budget)
        return result


def _load_metrics(run) -> dict:
    import json

    try:
        return json.loads(run.metrics_json or "{}")
    except json.JSONDecodeError:
        return {}


def _rank(candidates: list[Candidate], budget: SearchBudget) -> list[Candidate]:
    reverse = budget.direction != "min"

    def sort_key(candidate: Candidate) -> float:
        if candidate.metric is None:
            return float("-inf") if reverse else float("inf")
        return candidate.metric

    return sorted(candidates, key=sort_key, reverse=reverse)
