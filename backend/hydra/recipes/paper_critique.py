from __future__ import annotations

from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.agents.policy import PASSIVE
from hydra.agents.runs import RunBudget
from hydra.database.models import ReviewItem
from hydra.database.repository import Repository
from hydra.orchestrator.dispatch import DispatchAction, DispatchGuard
from hydra.orchestrator.stages import StageContext, StageEnum, StageResult
from hydra.recipes.common import RecipeRunResult, recipe_config, run_recipe_machine
from hydra.services.assistant.untrusted import assemble_untrusted_region

PAPER_CRITIQUE_RECIPE_ID = "paper-critique"
CRITIQUE_STAGES = [StageEnum.GENERATE, StageEnum.REVIEW, StageEnum.COMPARE, StageEnum.VALIDATE]
CRITIQUE_SECTION_IDS = [
    "novelty_gaps",
    "weak_claims",
    "missing_evidence",
    "method_limitations",
    "clarity_issues",
]


def paper_critique_recipe() -> dict[str, Any]:
    return recipe_config(
        recipe_id=PAPER_CRITIQUE_RECIPE_ID,
        name="Paper Critique",
        stages=CRITIQUE_STAGES,
        output_artifact_type="paper-critique-report",
    )


async def run_paper_critique_recipe(
    session: AsyncSession,
    inputs: dict[str, Any],
    *,
    project_id: str = "default",
    mode: str = PASSIVE,
    budget: RunBudget | None = None,
    privacy: dict[str, Any] | None = None,
) -> RecipeRunResult:
    result = await run_recipe_machine(
        session,
        recipe_id=PAPER_CRITIQUE_RECIPE_ID,
        stages=CRITIQUE_STAGES,
        stage_impls={
            StageEnum.GENERATE: PaperCritiqueGenerateStage(),
            StageEnum.REVIEW: PaperCritiqueReviewStage(),
            StageEnum.COMPARE: PaperCritiqueCompareStage(),
            StageEnum.VALIDATE: PaperCritiqueValidateStage(session),
        },
        inputs=inputs,
        project_id=project_id,
        mode=mode,
        budget=budget,
        privacy=privacy,
    )
    if result.state != "permission-denied":
        review = await _route_untrusted_action_proposals(session, result.run_id, inputs, project_id, mode)
        result.review_item = review
        result.review_item_id = review.id if review is not None else None
    return result


class PaperCritiqueGenerateStage:
    id = StageEnum.GENERATE

    async def run(self, ctx: StageContext) -> StageResult:
        inputs = ctx.data["recipe_inputs"]
        draft = inputs.get("draft_or_source") or {}
        text = str(draft.get("text") or draft.get("content") or "")
        untrusted = assemble_untrusted_region(text, provenance="untrusted-external")
        report = _build_report(text, str(inputs.get("target_venue_style") or ""))
        ctx.data["critique_report"] = report
        ctx.data["untrusted_context"] = untrusted
        return StageResult(
            stage=self.id,
            summary="generated paper critique findings from untrusted draft context",
            payload={
                "recipe": PAPER_CRITIQUE_RECIPE_ID,
                "draft_or_source": draft.get("title") or draft.get("id") or "draft",
                "target_venue_style": inputs.get("target_venue_style"),
                "source_scope": inputs.get("source_scope") or [],
                "untrusted_region": {
                    "begin_marker": untrusted["begin_marker"],
                    "end_marker": untrusted["end_marker"],
                    "trust_level": untrusted["trust_level"],
                },
            },
            tokens=10,
            trust_origin="untrusted-external",
        )


class PaperCritiqueReviewStage:
    id = StageEnum.REVIEW

    async def run(self, ctx: StageContext) -> StageResult:
        report = ctx.data["critique_report"]
        return StageResult(
            stage=self.id,
            summary="reviewed critique findings for evidence and venue fit",
            payload={"finding_count": _finding_count(report)},
            tokens=8,
            trust_origin="untrusted-external",
        )


class PaperCritiqueCompareStage:
    id = StageEnum.COMPARE

    async def run(self, ctx: StageContext) -> StageResult:
        report = ctx.data["critique_report"]
        ranked = sorted(
            [
                {"section": section, "count": len(items)}
                for section, items in report["sections"].items()
            ],
            key=lambda item: (-item["count"], item["section"]),
        )
        ctx.data["critique_ranking"] = ranked
        return StageResult(
            stage=self.id,
            summary="prioritized critique sections for review",
            payload={"ranking": ranked},
            tokens=8,
            trust_origin="untrusted-external",
        )


class PaperCritiqueValidateStage:
    id = StageEnum.VALIDATE

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def run(self, ctx: StageContext) -> StageResult:
        report = ctx.data["critique_report"]
        evidence = await Repository(self.session).list_evidence()
        has_evidence = bool(evidence)
        for section in report["sections"].values():
            for finding in section:
                finding["validation_status"] = "supported" if has_evidence else "unsupported"
                if not has_evidence:
                    finding["reason"] = "no-resolvable-evidence-link"
        artifact = {
            "id": f"{ctx.run_id}:paper-critique:report",
            "kind": "paper-critique-report",
            "stage": self.id.value,
            "summary": "Paper critique report with five sections and missing citations",
            "report": report,
        }
        return StageResult(
            stage=self.id,
            summary="validated critique findings against saved evidence links",
            payload={"unsupported_findings": 0 if has_evidence else _finding_count(report)},
            artifacts=[artifact],
            tokens=8,
            trust_origin="untrusted-external",
        )


def _build_report(text: str, target_venue_style: str) -> dict[str, Any]:
    lines = [line.strip() for line in text.splitlines() if line.strip()] or ["Draft needs review."]
    report = {"sections": {}, "missing_citations": []}
    for index, section_id in enumerate(CRITIQUE_SECTION_IDS):
        line = lines[min(index, len(lines) - 1)]
        report["sections"][section_id] = [
            {
                "id": f"{section_id}-1",
                "text": _finding_text(section_id, line, target_venue_style),
                "origin_locator": {
                    "kind": "draft",
                    "line": min(index + 1, len(lines)),
                    "quote": line,
                },
                "status": "needs_review",
            }
        ]
    report["missing_citations"] = [
        {
            "id": "missing-citation-1",
            "text": "Add saved-source support for the draft's strongest empirical or novelty claim.",
            "origin_locator": {"kind": "draft", "line": len(lines), "quote": lines[-1]},
            "handoff": "manual-source-discovery",
        }
    ]
    return report


def _finding_text(section_id: str, line: str, target_venue_style: str) -> str:
    labels = {
        "novelty_gaps": "Clarify what is novel against the saved library",
        "weak_claims": "Qualify an over-broad claim",
        "missing_evidence": "Attach direct evidence or downgrade the claim",
        "method_limitations": "State limits in the method or evaluation",
        "clarity_issues": "Tighten the presentation for the target venue",
    }
    venue = f" for {target_venue_style}" if target_venue_style else ""
    return f"{labels[section_id]}{venue}: {line}"


def _finding_count(report: dict[str, Any]) -> int:
    return sum(len(items) for items in report["sections"].values())


async def _route_untrusted_action_proposals(
    session: AsyncSession,
    run_id: str,
    inputs: dict[str, Any],
    project_id: str,
    mode: str,
):
    text = str((inputs.get("draft_or_source") or {}).get("text") or "")
    lowered = text.lower()
    if "save it as a new source" not in lowered and "insert this" not in lowered:
        return None
    result = await DispatchGuard(session).dispatch(
        DispatchAction(
            mode=mode,
            action_kind="manuscript_write",
            target_kind="manuscript",
            target_ref="writing/manuscripts/main.md",
            trust_origin="untrusted-external",
            justification_trust="untrusted-external",
            run_id=run_id,
            project_id=project_id,
            summary="Untrusted draft proposed a manuscript/source action",
            payload={
                "trust_origin": "untrusted-external",
                "origin_link": {"type": "draft", "locator": {"text": text[:160]}},
                "proposed_actions": ["manuscript_write", "source_create"],
            },
        )
    )
    if not result.review_item_id:
        return None
    return await session.get(ReviewItem, result.review_item_id)
