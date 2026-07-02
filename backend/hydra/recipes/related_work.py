from __future__ import annotations

import json
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.agents.approvals import ApprovalService
from hydra.agents.policy import PASSIVE
from hydra.agents.runs import RunBudget
from hydra.database.models import Citation, EvidenceLink, Source
from hydra.database.repository import Repository
from hydra.orchestrator.stages import StageContext, StageEnum, StageResult
from hydra.recipes.common import RecipeRunResult, recipe_config, run_recipe_machine
from hydra.services.assistant.untrusted import assemble_untrusted_region

RELATED_WORK_RECIPE_ID = "related-work"
RELATED_WORK_STAGES = [StageEnum.GENERATE, StageEnum.VALIDATE]


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
    return await run_recipe_machine(
        session,
        recipe_id=RELATED_WORK_RECIPE_ID,
        stages=RELATED_WORK_STAGES,
        stage_impls={
            StageEnum.GENERATE: RelatedWorkGenerateStage(session),
            StageEnum.VALIDATE: RelatedWorkValidateStage(session),
        },
        inputs=inputs,
        project_id=project_id,
        mode=mode,
        budget=budget,
        privacy=privacy,
    )


class RelatedWorkGenerateStage:
    id = StageEnum.GENERATE

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def run(self, ctx: StageContext) -> StageResult:
        inputs = ctx.data["recipe_inputs"]
        draft = inputs.get("draft_or_source") or {}
        untrusted = assemble_untrusted_region(str(draft.get("text") or ""), provenance="untrusted-external")
        library = await _library_records(self.session, inputs.get("source_scope") or [])
        paragraphs = _paragraphs_from_library(library)
        unsupported_notes = _unsupported_requested_claims(inputs.get("requested_claims") or [], paragraphs)
        ctx.data["related_work_draft"] = {
            "paragraphs": paragraphs,
            "unsupported_notes": unsupported_notes,
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
        draft = await validate_related_work_draft(self.session, ctx.data["related_work_draft"])
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


async def validate_related_work_draft(session: AsyncSession, draft: dict[str, Any]) -> dict[str, Any]:
    supported: list[dict[str, Any]] = []
    unsupported = list(draft.get("unsupported_notes") or [])
    for paragraph in draft.get("paragraphs") or []:
        links = list(paragraph.get("trace_links") or [])
        if links and all([await _trace_link_resolves(session, link) for link in links]):
            supported.append({**paragraph, "status": "supported"})
        else:
            unsupported.append(
                {
                    "id": paragraph.get("id"),
                    "text": paragraph.get("text", ""),
                    "status": "unsupported",
                    "reason": "unresolvable-trace-link",
                    "trace_links": links,
                }
            )
    return {
        **draft,
        "paragraphs": supported,
        "unsupported_notes": unsupported,
    }


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


async def _library_records(session: AsyncSession, source_scope: list[str]) -> list[dict[str, Any]]:
    repo = Repository(session)
    sources = await repo.list_sources()
    citations = await repo.list_citations()
    evidence = await repo.list_evidence()
    scoped = set(source_scope)
    if scoped:
        sources = [source for source in sources if source["id"] in scoped]
        citations = [citation for citation in citations if citation["source_id"] in scoped]
        evidence = [item for item in evidence if item["source_id"] in scoped]
    records: list[dict[str, Any]] = []
    for source in sources:
        source_citations = [citation for citation in citations if citation["source_id"] == source["id"]]
        source_evidence = [item for item in evidence if item["source_id"] == source["id"]]
        if not source_citations or not source_evidence:
            continue
        records.append({"source": source, "citation": source_citations[0], "evidence": source_evidence[0]})
    return records


def _paragraphs_from_library(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not records:
        return []
    text_bits = []
    trace_links = []
    for record in records[:3]:
        source = record["source"]
        citation = record["citation"]
        evidence = record["evidence"]
        text_bits.append(f"{source['title']} ({source.get('year') or 'n.d.'})")
        trace_links.append(
            {
                "source_id": source["id"],
                "citation_id": citation["id"],
                "evidence_id": evidence["id"],
                "locator": evidence.get("locator") or {},
            }
        )
    return [
        {
            "id": "related-work-p1",
            "text": f"Saved literature such as {', '.join(text_bits)} grounds the related-work synthesis.",
            "trace_links": trace_links,
            "status": "draft",
        }
    ]


def _unsupported_requested_claims(requested_claims: list[str], paragraphs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    emitted_text = " ".join(str(paragraph.get("text") or "").lower() for paragraph in paragraphs)
    unsupported = []
    for claim in requested_claims:
        if str(claim).lower() not in emitted_text:
            unsupported.append(
                {
                    "id": f"unsupported-{len(unsupported) + 1}",
                    "text": f"Unsupported requested point: {claim}",
                    "status": "unsupported",
                    "reason": "no-saved-source-evidence",
                }
            )
    return unsupported


async def _trace_link_resolves(session: AsyncSession, link: dict[str, Any]) -> bool:
    source_id = link.get("source_id")
    citation_id = link.get("citation_id")
    evidence_id = link.get("evidence_id")
    if not source_id or not citation_id:
        return False
    source = await session.get(Source, source_id)
    citation = await session.get(Citation, citation_id)
    if source is None or citation is None or citation.source_id != source_id:
        return False
    if evidence_id:
        evidence = await session.get(EvidenceLink, evidence_id)
        if evidence is None or evidence.source_id != source_id or evidence.citation_id != citation_id:
            return False
    return True
