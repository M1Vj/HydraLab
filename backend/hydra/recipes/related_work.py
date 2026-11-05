from __future__ import annotations

import html
import json
import re
from typing import Any

from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.agents.approvals import ApprovalService
from hydra.agents.policy import PASSIVE
from hydra.agents.runs import RunBudget, RunRepository
from hydra.database.models import Citation, Claim, EvidenceLink, Source
from hydra.orchestrator.run import RunConfig, RunStateMachine
from hydra.orchestrator.stages import StageContext, StageEnum, StageResult
from hydra.recipes.common import RecipeRunResult, recipe_config, recipe_result
from hydra.services.assistant.untrusted import assemble_untrusted_region

RELATED_WORK_RECIPE_ID = "related-work"
RELATED_WORK_STAGES = [StageEnum.GENERATE, StageEnum.VALIDATE]
MAX_RELATED_WORK_SOURCES = 3
EXCERPT_NOTICE = (
    "Local saved-evidence excerpts, not a synthesized literature review. "
    "Supported means the excerpt and trace match saved records, not that a research claim is proven. "
    "Review the original source and evidence status before accepting into a manuscript."
)


def related_work_recipe() -> dict[str, Any]:
    return recipe_config(
        recipe_id=RELATED_WORK_RECIPE_ID,
        name="Related Work",
        stages=RELATED_WORK_STAGES,
        output_artifact_type="related-work-draft",
    )


async def run_related_work_recipe(
    session: AsyncSession,
    inputs: dict[str, Any],
    *,
    project_id: str = "default",
    mode: str = PASSIVE,
    budget: RunBudget | None = None,
    privacy: dict[str, Any] | None = None,
) -> RecipeRunResult:
    # These two fixed stages only read local records and persist a run artifact.
    # Do not route local extraction through the provider-send preflight. Any
    # future provider-backed synthesis must use the normal consent-gated runner.
    config = RunConfig.resolve(stage_overrides={stage.value: True for stage in RELATED_WORK_STAGES})
    execution = await RunStateMachine(
        RunRepository(session),
        config,
        stages={
            StageEnum.GENERATE: RelatedWorkGenerateStage(session),
            StageEnum.VALIDATE: RelatedWorkValidateStage(session),
        },
        budget=budget,
    ).start(
        project_id=project_id,
        mode=mode,
        recipe=RELATED_WORK_RECIPE_ID,
        inputs=[inputs],
        data={"recipe_inputs": inputs},
    )
    return await recipe_result(session, execution)


class RelatedWorkGenerateStage:
    id = StageEnum.GENERATE

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def run(self, ctx: StageContext) -> StageResult:
        inputs = ctx.data["recipe_inputs"]
        draft = inputs.get("draft_or_source") or {}
        untrusted = assemble_untrusted_region(str(draft.get("text") or ""), provenance="untrusted-external")
        scope = inputs.get("source_scope", [])
        library = await _library_records(self.session, scope, project_id=ctx.project_id)
        paragraphs = _paragraphs_from_library(library)
        unsupported_notes = _unsupported_requested_claims(inputs.get("requested_claims") or [], paragraphs)
        ctx.data["related_work_draft"] = {
            "paragraphs": paragraphs,
            "unsupported_notes": unsupported_notes,
            "notices": _draft_notices(scope, library),
            "untrusted_region": {
                "begin_marker": untrusted["begin_marker"],
                "end_marker": untrusted["end_marker"],
                "trust_level": untrusted["trust_level"],
            },
        }
        return StageResult(
            stage=self.id,
            summary="generated related-work draft from saved source library",
            payload={
                "paragraph_count": len(paragraphs),
                "unsupported_note_count": len(unsupported_notes),
                "source_scope": inputs.get("source_scope") or [],
                "untrusted_region": ctx.data["related_work_draft"]["untrusted_region"],
            },
            tokens=10,
            trust_origin="untrusted-external",
        )


class RelatedWorkValidateStage:
    id = StageEnum.VALIDATE

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def run(self, ctx: StageContext) -> StageResult:
        draft = await validate_related_work_draft(
            self.session,
            ctx.data["related_work_draft"],
            project_id=ctx.project_id,
            source_scope=ctx.data["recipe_inputs"].get("source_scope", []),
        )
        ctx.data["related_work_draft"] = draft
        artifact = {
            "id": f"{ctx.run_id}:related-work:draft",
            "kind": "related-work-draft",
            "stage": self.id.value,
            "summary": "Related-work draft with source/citation trace links",
            "draft": draft,
            "write_gate": "inline_accept_reject",
        }
        return StageResult(
            stage=self.id,
            summary="validated every related-work paragraph trace link",
            payload={
                "paragraph_count": len(draft["paragraphs"]),
                "unsupported_note_count": len(draft["unsupported_notes"]),
            },
            artifacts=[artifact],
            tokens=8,
            trust_origin="untrusted-external",
        )


async def validate_related_work_draft(
    session: AsyncSession,
    draft: dict[str, Any],
    *,
    project_id: str = "default",
    source_scope: list[str] | None = None,
) -> dict[str, Any]:
    """Recheck exact saved excerpts, not merely that their identifiers exist."""
    records = await _library_records(
        session, [] if source_scope is None else source_scope, project_id=project_id
    )
    expected = {record["evidence"]["id"]: _evidence_excerpt(record) for record in records}
    supported: list[dict[str, Any]] = []
    unsupported = list(draft.get("unsupported_notes") or [])
    for paragraph in draft.get("paragraphs") or []:
        if not isinstance(paragraph, dict):
            continue
        excerpts = paragraph.get("evidence_excerpts")
        canonical = []
        reason = "unresolvable-trace-link"
        if isinstance(excerpts, list) and 0 < len(excerpts) <= MAX_RELATED_WORK_SOURCES:
            for excerpt in excerpts:
                if not isinstance(excerpt, dict):
                    break
                evidence_id = excerpt.get("evidence_id")
                saved = expected.get(evidence_id) if isinstance(evidence_id, str) else None
                if saved is None:
                    break
                canonical.append(saved)
            if len(canonical) == len(excerpts):
                candidate = _bundle_excerpts(canonical)
                # The entire prose, raw excerpts, evidence state and locators
                # must still match. Real identifiers cannot bless invented text.
                if (
                    len({item["source_id"] for item in canonical}) == len(canonical)
                    and all(paragraph.get(key) == candidate[key] for key in (
                        "text", "evidence_excerpts", "trace_links"
                    ))
                ):
                    supported.append({**candidate, "status": "supported"})
                    continue
                reason = "saved-evidence-mismatch"
        unsupported.append({
            "id": paragraph.get("id"),
            "text": paragraph.get("text", ""),
            "status": "unsupported",
            "reason": reason,
            "trace_links": paragraph.get("trace_links") or [],
        })
    return {**draft, "paragraphs": supported, "unsupported_notes": unsupported}


async def insert_related_work_suggestion(
    session: AsyncSession,
    *,
    manuscript_ref: str,
    paragraph: dict[str, Any],
    workspace: dict[str, str],
    decision: str | None = None,
):
    if decision in {"approved", "approve", "accepted", "accept"}:
        trace_json = json.dumps(paragraph.get("trace_links") or [], sort_keys=True)
        workspace[manuscript_ref] = (
            workspace.get(manuscript_ref, "")
            + "\n"
            + str(paragraph.get("text") or "")
            + f"\n<!-- hydralab-trace:{trace_json} -->\n"
        )
        return None
    return await ApprovalService(session).request(
        action_kind="manuscript_write",
        mode=PASSIVE,
        project_id="default",
        target_kind="manuscript",
        target_ref=manuscript_ref,
        trust_origin="untrusted-external",
        reason="related-work insertion requires explicit inline accept/reject",
        summary="Insert related-work paragraph",
        payload={"paragraph": paragraph, "trace_links": paragraph.get("trace_links") or []},
    )


def _valid_scope(source_scope: Any) -> bool:
    return isinstance(source_scope, list) and all(isinstance(item, str) and item.strip() for item in source_scope)


async def _library_records(
    session: AsyncSession, source_scope: list[str], *, project_id: str = "default"
) -> list[dict[str, Any]]:
    if not isinstance(project_id, str) or not project_id.strip() or not _valid_scope(source_scope):
        return []
    # One SELECT is one SQLite snapshot. Separate scoped reads could mix an
    # old A-owned source with new evidence after a concurrent move to project B.
    query = (
        select(Source, Citation, EvidenceLink)
        .join(EvidenceLink, EvidenceLink.source_id == Source.id)
        .join(Citation, Citation.id == EvidenceLink.citation_id)
        .join(Claim, Claim.id == EvidenceLink.claim_id)
        .where(
            func.coalesce(Source.project_id, "default") == project_id,
            func.coalesce(Citation.project_id, "default") == project_id,
            func.coalesce(Claim.project_id, "default") == project_id,
            Citation.source_id == Source.id,
            Source.trashed == False,  # noqa: E712
            (Source.merged_into_source_id.is_(None)) | (Source.merged_into_source_id == ""),
            Source.link_state == "live",
            Citation.link_state == "live",
            Claim.link_state == "live",
            EvidenceLink.link_state == "live",
            EvidenceLink.evidence_type == "quote",
        )
        # Validation must observe committed edits, not old ORM identity-map
        # values left over from Generate or a previous request in this session.
        .execution_options(populate_existing=True)
    )
    if source_scope:
        query = query.where(Source.id.in_(set(source_scope)))
    rows = (await session.exec(query)).all()
    records: list[dict[str, Any]] = []
    for source, citation, evidence in rows:
        quote = evidence.quote_text or evidence.passage or ""
        try:
            locator = json.loads(evidence.locator)
        except (ValueError, TypeError):
            continue
        if not isinstance(quote, str) or not quote.strip() or not isinstance(locator, dict) or not locator:
            continue
        records.append({
            "source": {"id": source.id, "title": source.title, "year": source.year},
            "citation": {"id": citation.id},
            "evidence": {
                "id": evidence.id, "claim_id": evidence.claim_id, "locator": locator,
                "support": evidence.support, "support_level": evidence.support_level,
                "review_status": evidence.review_status, "created_at": evidence.created_at.timestamp(),
            },
            "quote": quote,
        })
    # Stable source order; the newest eligible saved excerpt wins per source.
    return sorted(records, key=lambda record: (
        record["source"]["title"].casefold(), record["source"]["id"],
        -record["evidence"]["created_at"], record["evidence"]["id"],
    ))


def _evidence_excerpt(record: dict[str, Any]) -> dict[str, Any]:
    source, citation, evidence = record["source"], record["citation"], record["evidence"]
    return {
        "source_id": source["id"],
        "source_title": source["title"],
        "source_year": source.get("year") or "n.d.",
        "citation_id": citation["id"],
        "evidence_id": evidence["id"],
        "claim_id": evidence["claim_id"],
        "locator": evidence["locator"],
        "quote": record["quote"],
        "support": evidence.get("support_level") or evidence.get("support") or "",
        "review_status": evidence.get("review_status") or "",
    }


def _markdown_text(value: str) -> str:
    # The original quote remains untouched in evidence_excerpts. Escape its
    # presentation so accepting an excerpt cannot insert an active Markdown
    # image, link or raw HTML copied from untrusted source text.
    return re.sub(r"([\\`*_{}\[\]()#+\-.!|>~])", r"\\\1", html.escape(value, quote=False))


def _bundle_excerpts(excerpts: list[dict[str, Any]]) -> dict[str, Any]:
    # Keep the single-paragraph envelope used by the existing writing handoff,
    # which forwards paragraphs[0]. Every selected source travels with it.
    sections = ["Saved evidence excerpts for review (not a synthesized conclusion):"]
    for excerpt in excerpts:
        title = _markdown_text(excerpt["source_title"])
        year = _markdown_text(excerpt["source_year"])
        support = _markdown_text(excerpt["support"] or "unspecified")
        review = _markdown_text(excerpt["review_status"] or "unspecified")
        quote = _markdown_text(excerpt["quote"])
        sections.append(f"{title} ({year}); evidence relation: {support}; saved review status: {review}:\n“{quote}”")
    return {
        "id": "related-work-excerpts",
        "text": "\n\n".join(sections),
        "evidence_excerpts": excerpts,
        "trace_links": [{key: excerpt[key] for key in (
            "source_id", "citation_id", "evidence_id", "claim_id", "locator"
        )} for excerpt in excerpts],
        "status": "draft",
    }


def _paragraphs_from_library(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    excerpts = []
    seen = set()
    for record in records:
        source_id = record["source"]["id"]
        if source_id in seen:
            continue
        seen.add(source_id)
        excerpts.append(_evidence_excerpt(record))
        if len(excerpts) == MAX_RELATED_WORK_SOURCES:
            break
    return [_bundle_excerpts(excerpts)] if excerpts else []


def _draft_notices(source_scope: Any, records: list[dict[str, Any]]) -> list[str]:
    notices = [EXCERPT_NOTICE]
    if not _valid_scope(source_scope):
        notices.append("Invalid source scope: provide a list of source IDs; an empty list selects the current project.")
    elif not records:
        notices.append("No eligible saved quotations with a live citation and locator in this source scope.")
    source_count = len({record["source"]["id"] for record in records})
    if source_count > MAX_RELATED_WORK_SOURCES:
        notices.append(
            f"Showing {MAX_RELATED_WORK_SOURCES} of {source_count} eligible sources in title order. "
            "Narrow the source scope to inspect the remaining sources."
        )
    return notices


def _unsupported_requested_claims(requested_claims: list[str], paragraphs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Literal overlap (including overlap inside a negation) cannot establish
    # semantic support. Requested research claims remain review tasks even when
    # they occur in an excerpt; only the saved quotation itself is validated.
    return [
        {
            "id": f"unsupported-{index + 1}",
            "text": f"Requested point needs review: {claim}",
            "status": "unsupported",
            "reason": "requires-researcher-review",
        }
        for index, claim in enumerate(requested_claims)
        if str(claim).strip()
    ]
