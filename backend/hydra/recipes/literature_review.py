"""Literature-review recipe over the Phase-2 orchestrator stage engine."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.agents.approvals import ApprovalService
from hydra.agents.contracts import ApprovalStatus
from hydra.agents.policy import TRUST_UNTRUSTED
from hydra.agents.runs import RunBudget, RunRepository
from hydra.database.models import AgentApproval, AgentRun, LexicalIndexEntry
from hydra.database.repository import Repository
from hydra.orchestrator.run import RunConfig, RunExecutionResult, RunStateMachine
from hydra.orchestrator.stages import StageContext, StageEnum, StageResult
from hydra.recipes.retrieval import LiteratureHit, RetrievalOptions, RetrievalResult, retrieve_literature_hits
from hydra.services.assistant.untrusted import assemble_untrusted_region

EMPTY_QUESTION_MESSAGE = "Enter a research question to start the review."
RECIPE_ID = "literature-review"
ALLOWED_SAVE_DESTINATIONS = {"work/reviews", "knowledge/literature"}


@dataclass(frozen=True)
class RecipeDescriptor:
    id: str
    label: str
    enabled_stages: dict[StageEnum, bool]
    exposes_loop_controls: bool = False

    def public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "enabled_stages": {stage.value: enabled for stage, enabled in self.enabled_stages.items()},
            "exposes_loop_controls": self.exposes_loop_controls,
        }


@dataclass(frozen=True)
class LiteratureReviewInput:
    question: str
    source_scope: dict[str, Any]
    depth: str


@dataclass(frozen=True)
class InputValidationResult:
    allowed: bool
    message: str = ""
    inputs: LiteratureReviewInput | None = None


@dataclass(frozen=True)
class ArtifactStatement:
    text: str
    source_ids: list[str] = field(default_factory=list)
    citation_ids: list[str] = field(default_factory=list)
    locators: list[dict[str, Any]] = field(default_factory=list)
    marker: str = ""
    chunk_ids: list[str] = field(default_factory=list)

    def public_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "source_ids": self.source_ids,
            "citation_ids": self.citation_ids,
            "locators": self.locators,
            "marker": self.marker,
            "chunk_ids": self.chunk_ids,
        }


@dataclass(frozen=True)
class LiteratureReviewArtifact:
    run_id: str
    question: str
    sections: dict[str, list[ArtifactStatement]]
    retrieval_hits: list[LiteratureHit]
    notices: list[str] = field(default_factory=list)

    def markdown(self) -> str:
        lines = ["# Literature review", "", f"Question: {self.question}", ""]
        for section, statements in self.sections.items():
            lines.extend([f"## {section}", ""])
            if not statements:
                lines.extend(["- None.", ""])
                continue
            for statement in statements:
                marker = f"{statement.marker} " if statement.marker else ""
                refs = _format_refs(statement)
                lines.append(f"- {marker}{statement.text}{refs}")
            lines.append("")
        if self.notices:
            lines.extend(["## Run notices", ""])
            lines.extend([f"- {notice}" for notice in self.notices])
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    def public_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "question": self.question,
            "sections": {
                section: [statement.public_dict() for statement in statements]
                for section, statements in self.sections.items()
            },
            "retrieval_hits": [hit.public_dict() for hit in self.retrieval_hits],
            "notices": self.notices,
            "markdown": self.markdown(),
        }


@dataclass(frozen=True)
class LiteratureReviewResult:
    run_id: str
    state: str
    artifact: LiteratureReviewArtifact | None
    review_item_ids: list[str] = field(default_factory=list)
    completed_stages: list[StageEnum] = field(default_factory=list)


@dataclass(frozen=True)
class LiteratureReviewSaveRequest:
    run_id: str
    destination: str
    filename: str = ""


@dataclass(frozen=True)
class PendingArtifactSave:
    approval_id: str
    artifact_preview: str
    target_relative_path: str
    apply: Callable[[], Awaitable[Path]]


def literature_review_descriptor(*, engine_enabled: bool = True) -> RecipeDescriptor | None:
    if not engine_enabled:
        return None
    return RecipeDescriptor(
        id=RECIPE_ID,
        label="Literature review",
        enabled_stages=_recipe_enabled_stages(),
        exposes_loop_controls=False,
    )


def literature_review_run_config() -> RunConfig:
    return RunConfig.resolve(stage_overrides={stage.value: enabled for stage, enabled in _recipe_enabled_stages().items()})


def validate_literature_review_input(raw: dict[str, Any]) -> InputValidationResult:
    question = str(raw.get("question") or "").strip()
    if not question:
        return InputValidationResult(allowed=False, message=EMPTY_QUESTION_MESSAGE)
    source_scope = raw.get("source_scope")
    if not isinstance(source_scope, dict):
        source_scope = {"kind": "all-project"}
    depth = str(raw.get("depth") or "standard").strip() or "standard"
    if depth not in {"quick", "standard", "deep"}:
        depth = "standard"
    allowed_keys = {"question", "source_scope", "depth"}
    extra = sorted(set(raw) - allowed_keys)
    if extra:
        return InputValidationResult(allowed=False, message=f"Unsupported literature-review inputs: {', '.join(extra)}")
    return InputValidationResult(
        allowed=True,
        inputs=LiteratureReviewInput(question=question, source_scope=source_scope, depth=depth),
    )


async def execute_literature_review(
    *,
    session: AsyncSession,
    project_root: Path,
    inputs: LiteratureReviewInput,
    mode: str,
    semantic_enabled: bool = False,
    g3_enabled: bool = False,
    offline_only: bool = False,
    provider_metadata: list[dict[str, Any]] | None = None,
    unsupported_drafts: list[str] | None = None,
    synthesized_drafts: list[dict[str, Any]] | None = None,
    cancel_after_stage: StageEnum | None = None,
    budget: RunBudget | None = None,
) -> LiteratureReviewResult:
    repo = Repository(session)
    review_item_ids = await _route_untrusted_provider_metadata(
        repo,
        project_id="default",
        provider_metadata=provider_metadata or [],
    )
    retrieval_options = RetrievalOptions(
        semantic_enabled=semantic_enabled,
        offline_only=offline_only,
        g3_enabled=g3_enabled,
        depth=inputs.depth,
    )
    stages = {
        StageEnum.GENERATE: LiteratureGenerateStage(
            session, inputs, retrieval_options, unsupported_drafts or [], synthesized_drafts or []
        ),
        StageEnum.REVIEW: LiteratureReviewStage(),
        StageEnum.VALIDATE: LiteratureValidateStage(session),
        StageEnum.CACHE: LiteratureCacheStage(),
    }
    machine = RunStateMachine(
        RunRepository(session),
        literature_review_run_config(),
        stages=stages,
        budget=budget,
        cancel_after_stage=cancel_after_stage,
    )
    run_result = await machine.start(project_id="default", mode=mode, recipe=RECIPE_ID)
    artifact = None
    if run_result.state != "cancelled":
        artifact = await _artifact_from_run(session, run_result.run_id)
    return LiteratureReviewResult(
        run_id=run_result.run_id,
        state=run_result.state,
        artifact=artifact,
        review_item_ids=review_item_ids,
        completed_stages=run_result.completed_stages,
    )


async def save_literature_review_artifact(
    *,
    session: AsyncSession,
    project_root: Path,
    artifact: LiteratureReviewArtifact,
    request: LiteratureReviewSaveRequest,
    mode: str,
) -> PendingArtifactSave:
    relative = _safe_artifact_relative_path(request)
    markdown = artifact.markdown()
    service = ApprovalService(session)
    approval = await service.request(
        action_kind="literature_review.save_artifact",
        summary=f"Save literature review to {relative}",
        mode=mode,
        run_id=request.run_id,
        project_id="default",
        target_kind="file",
        target_ref=relative,
        trust_origin="user",
        reason="review artifacts are written only after explicit approval",
        payload={"relative_path": relative, "markdown": markdown},
    )

    async def apply() -> Path:
        return _write_artifact(project_root, relative, markdown)

    return PendingArtifactSave(
        approval_id=approval.id,
        artifact_preview=markdown,
        target_relative_path=relative,
        apply=apply,
    )


async def resolve_literature_review_save_approval(
    *,
    session: AsyncSession,
    project_root: Path,
    approval_id: str,
    decision: str,
) -> dict[str, Any]:
    approval = await session.get(AgentApproval, approval_id)
    if approval is None:
        return {"applied": False, "status": "missing", "reason": "approval not found"}
    payload = json.loads(approval.payload_json or "{}")
    relative = str(payload.get("relative_path") or "")
    markdown = str(payload.get("markdown") or "")

    async def apply() -> Path:
        return _write_artifact(project_root, relative, markdown)

    result = await ApprovalService(session).resolve(approval_id, decision=decision, apply_fn=apply)
    return {
        "applied": result.applied,
        "status": result.status,
        "reason": result.reason,
        "path": relative if result.applied else None,
    }


class LiteratureGenerateStage:
    id = StageEnum.GENERATE

    def __init__(
        self,
        session: AsyncSession,
        inputs: LiteratureReviewInput,
        retrieval_options: RetrievalOptions,
        unsupported_drafts: list[str],
        synthesized_drafts: list[dict[str, Any]] | None = None,
    ) -> None:
        self.session = session
        self.inputs = inputs
        self.retrieval_options = retrieval_options
        self.unsupported_drafts = unsupported_drafts
        self.synthesized_drafts = synthesized_drafts or []

    async def run(self, ctx: StageContext) -> StageResult:
        repo = Repository(self.session)
        await repo.list_claims()
        await repo.list_evidence()
        retrieval = await retrieve_literature_hits(
            self.session,
            query=self.inputs.question,
            source_scope=self.inputs.source_scope,
            options=self.retrieval_options,
        )
        statements = _draft_supported_statements(retrieval.hits)
        # Synthesized (non-verbatim) claims enter as candidate-supported and must
        # survive the Validate semantic-support gate against their cited chunk.
        statements.extend(_synthesized_statements(self.synthesized_drafts))
        ctx.data["literature_inputs"] = {
            "question": self.inputs.question,
            "source_scope": self.inputs.source_scope,
            "depth": self.inputs.depth,
        }
        ctx.data["retrieval"] = retrieval
        ctx.data["supported_statements"] = statements
        ctx.data["unsupported_drafts"] = list(self.unsupported_drafts)
        return StageResult(
            stage=self.id,
            summary=f"retrieved {len(retrieval.hits)} source-traceable literature hits",
            payload={
                "hit_count": len(retrieval.hits),
                "hits": [hit.public_dict() for hit in retrieval.hits],
                "notices": retrieval.notices,
            },
            tokens=12,
            trust_origin=TRUST_UNTRUSTED,
        )


class LiteratureReviewStage:
    id = StageEnum.REVIEW

    async def run(self, ctx: StageContext) -> StageResult:
        unsupported = [str(item) for item in ctx.data.get("unsupported_drafts") or [] if str(item).strip()]
        ctx.data["review_gaps"] = [
            ArtifactStatement(text=text, marker="[unsupported]") for text in unsupported
        ]
        return StageResult(
            stage=self.id,
            summary=f"reviewed literature draft and flagged {len(unsupported)} unsupported statements",
            payload={"unsupported_count": len(unsupported)},
            tokens=8,
        )


class LiteratureValidateStage:
    id = StageEnum.VALIDATE

    def __init__(self, session: AsyncSession | None = None) -> None:
        self.session = session

    async def run(self, ctx: StageContext) -> StageResult:
        candidates = list(ctx.data.get("supported_statements") or [])
        chunk_text = await self._chunk_text_by_source(candidates)
        supported: list[ArtifactStatement] = []
        rejected: list[ArtifactStatement] = []
        for item in candidates:
            if not item.source_ids:
                rejected.append(item)
                continue
            # Semantic support: statement text must be quote-contained-in /
            # entailed-by the cited chunk text; structural resolution alone is
            # not enough once real synthesis lands.
            support = "\n".join(chunk_text.get(source_id, "") for source_id in item.source_ids)
            if support and not _semantically_supported(item.text, support):
                rejected.append(item)
            else:
                supported.append(item)
        gaps = list(ctx.data.get("review_gaps") or [])
        gaps.extend(ArtifactStatement(text=item.text, marker="[unsupported]") for item in rejected)
        ctx.data["validated_supported"] = supported
        ctx.data["validated_gaps"] = gaps
        return StageResult(
            stage=self.id,
            summary=f"validated {len(supported)} supported statements and {len(gaps)} gaps",
            payload={"supported_count": len(supported), "gap_count": len(gaps)},
            tokens=8,
        )

    async def _chunk_text_by_source(self, statements: list[ArtifactStatement]) -> dict[str, str]:
        """Fetch cited chunk text by chunk_id (fallback source_id) for support checks."""

        if self.session is None:
            return {}
        chunk_ids = {cid for item in statements for cid in item.chunk_ids if cid}
        source_ids = {sid for item in statements for sid in item.source_ids if sid}
        if not chunk_ids and not source_ids:
            return {}
        rows = (await self.session.exec(select(LexicalIndexEntry))).all()
        by_source: dict[str, list[str]] = {}
        for row in rows:
            if not row.source_id:
                continue
            if row.chunk_id in chunk_ids or row.source_id in source_ids:
                by_source.setdefault(row.source_id, []).append(row.text or "")
        return {source_id: "\n".join(texts) for source_id, texts in by_source.items()}


class LiteratureCacheStage:
    id = StageEnum.CACHE

    async def run(self, ctx: StageContext) -> StageResult:
        inputs = ctx.data["literature_inputs"]
        artifact = _assemble_artifact(
            run_id=ctx.run_id,
            question=str(inputs["question"]),
            statements=list(ctx.data.get("validated_supported") or []),
            gaps=list(ctx.data.get("validated_gaps") or []),
            retrieval=ctx.data.get("retrieval"),
        )
        ctx.data["literature_artifact"] = artifact
        return StageResult(
            stage=self.id,
            summary="prepared literature-review artifact pending explicit save approval",
            payload={"artifact": artifact.public_dict(), "approval_required": True},
            artifacts=[
                {
                    "id": f"{ctx.run_id}:literature-review",
                    "kind": "literature-review",
                    "stage": self.id.value,
                    "ref": "agent-run:literature-review",
                    "summary": "Structured literature review pending save approval",
                    **artifact.public_dict(),
                }
            ],
            tokens=6,
            status="completed",
            stop_state="awaiting_approval",
        )


def _recipe_enabled_stages() -> dict[StageEnum, bool]:
    return {
        StageEnum.GENERATE: True,
        StageEnum.REVIEW: True,
        StageEnum.COMPARE: False,
        StageEnum.EVOLVE: False,
        StageEnum.VALIDATE: True,
        StageEnum.CACHE: True,
        StageEnum.LOOP_CONTROL: False,
    }


def _draft_supported_statements(hits: list[LiteratureHit]) -> list[ArtifactStatement]:
    statements: list[ArtifactStatement] = []
    for hit in hits:
        text = _sentence(hit.text)
        statements.append(
            ArtifactStatement(
                text=text,
                source_ids=[hit.source_id],
                citation_ids=[hit.citation_id] if hit.citation_id else [],
                locators=[hit.locator],
                chunk_ids=[hit.chunk_id] if hit.chunk_id else [],
            )
        )
    return statements


def _synthesized_statements(drafts: list[dict[str, Any]]) -> list[ArtifactStatement]:
    """Build candidate-supported statements from synthesized (non-verbatim) drafts.

    Each draft names the cited source/chunk it claims to rest on; the Validate
    stage then gates it against the real chunk text (demoting fabrications).
    """

    statements: list[ArtifactStatement] = []
    for draft in drafts:
        text = str(draft.get("text") or "").strip()
        source_id = str(draft.get("source_id") or "").strip()
        if not text or not source_id:
            continue
        chunk_id = str(draft.get("chunk_id") or "").strip()
        citation_id = str(draft.get("citation_id") or "").strip()
        statements.append(
            ArtifactStatement(
                text=text,
                source_ids=[source_id],
                citation_ids=[citation_id] if citation_id else [],
                locators=[dict(draft.get("locator") or {})] if draft.get("locator") else [],
                chunk_ids=[chunk_id] if chunk_id else [],
            )
        )
    return statements


def _semantically_supported(statement_text: str, chunk_text: str) -> bool:
    """Cheap entailment proxy: statement must be quote-contained-in / token-
    entailed-by the cited chunk text.

    Verbatim drafts (a sentence of the chunk) always pass; a synthesized claim
    passes only if most of its content tokens appear in the cited chunk.
    """

    statement = " ".join(str(statement_text or "").lower().split())
    chunk = " ".join(str(chunk_text or "").lower().split())
    if not statement or not chunk:
        return False
    if statement in chunk:
        return True
    statement_tokens = {token for token in re.findall(r"[a-z0-9]+", statement) if len(token) > 2}
    if not statement_tokens:
        return statement in chunk
    chunk_tokens = set(re.findall(r"[a-z0-9]+", chunk))
    overlap = len(statement_tokens & chunk_tokens) / len(statement_tokens)
    return overlap >= 0.6


def _assemble_artifact(
    *,
    run_id: str,
    question: str,
    statements: list[ArtifactStatement],
    gaps: list[ArtifactStatement],
    retrieval: RetrievalResult | None,
) -> LiteratureReviewArtifact:
    first_by_source: dict[str, ArtifactStatement] = {}
    for statement in statements:
        if statement.source_ids:
            first_by_source.setdefault(statement.source_ids[0], statement)
    notes = [
        ArtifactStatement(
            text=f"Evidence note: {statement.text}",
            source_ids=statement.source_ids,
            citation_ids=statement.citation_ids,
            locators=statement.locators,
        )
        for statement in statements
    ]
    sections = {
        "Themes": statements[:3],
        "Per-source summaries": [
            ArtifactStatement(
                text=f"{source_id}: {statement.text}",
                source_ids=statement.source_ids,
                citation_ids=statement.citation_ids,
                locators=statement.locators,
            )
            for source_id, statement in first_by_source.items()
        ],
        "Gaps": gaps,
        "Evidence-linked notes": notes,
    }
    retrieval = retrieval or RetrievalResult()
    return LiteratureReviewArtifact(
        run_id=run_id,
        question=question,
        sections=sections,
        retrieval_hits=retrieval.hits,
        notices=retrieval.notices,
    )


async def _artifact_from_run(session: AsyncSession, run_id: str) -> LiteratureReviewArtifact | None:
    run = await session.get(AgentRun, run_id)
    if run is None:
        return None
    for payload in json.loads(run.artifacts or "[]"):
        if payload.get("kind") == "literature-review":
            return _artifact_from_payload(payload)
    return None


def _artifact_from_payload(payload: dict[str, Any]) -> LiteratureReviewArtifact:
    raw_sections = dict(payload.get("sections") or {})
    sections = {
        section: [_statement_from_payload(item) for item in raw_sections.get(section) or []]
        for section in ["Themes", "Per-source summaries", "Gaps", "Evidence-linked notes"]
    }
    return LiteratureReviewArtifact(
        run_id=str(payload.get("run_id") or ""),
        question=str(payload.get("question") or ""),
        sections=sections,
        retrieval_hits=[_hit_from_payload(item) for item in payload.get("retrieval_hits") or []],
        notices=[str(item) for item in payload.get("notices") or []],
    )


def _statement_from_payload(payload: dict[str, Any]) -> ArtifactStatement:
    return ArtifactStatement(
        text=str(payload.get("text") or ""),
        source_ids=[str(item) for item in payload.get("source_ids") or []],
        citation_ids=[str(item) for item in payload.get("citation_ids") or []],
        locators=[dict(item) for item in payload.get("locators") or [] if isinstance(item, dict)],
        marker=str(payload.get("marker") or ""),
        chunk_ids=[str(item) for item in payload.get("chunk_ids") or []],
    )


def _hit_from_payload(payload: dict[str, Any]) -> LiteratureHit:
    return LiteratureHit(
        source_id=str(payload.get("source_id") or ""),
        citation_id=str(payload.get("citation_id") or "") or None,
        locator=dict(payload.get("locator") or {}),
        chunk_id=str(payload.get("chunk_id") or ""),
        extraction_version=int(payload.get("extraction_version") or 1),
        index_version=int(payload.get("index_version") or 1),
        confidence=float(payload.get("confidence") or 0.0),
        text=str(payload.get("text") or ""),
        source_title=str(payload.get("source_title") or ""),
        query_mode=str(payload.get("query_mode") or "lexical"),
    )


async def _route_untrusted_provider_metadata(
    repo: Repository,
    *,
    project_id: str,
    provider_metadata: list[dict[str, Any]],
) -> list[str]:
    review_item_ids: list[str] = []
    for item in provider_metadata:
        title = str(item.get("title") or "Provider source proposal")
        region = assemble_untrusted_region(str(item.get("text") or json.dumps(item, sort_keys=True)), provenance=TRUST_UNTRUSTED)
        review = await repo.create_review_item(
            {
                "project_id": project_id,
                "item_type": "provider-source-proposal",
                "title": "Review provider source proposal",
                "summary": f"Untrusted provider metadata proposed a source: {title}",
                "origin_type": "agent_run",
                "target_type": "source",
                "payload": {
                    "title": title,
                    "metadata": item,
                    "untrusted_region": region,
                    "reason": "untrusted provider metadata cannot auto-create a source",
                },
            }
        )
        review_item_ids.append(review["id"])
    return review_item_ids


def _safe_artifact_relative_path(request: LiteratureReviewSaveRequest) -> str:
    destination = request.destination.strip().strip("/")
    if destination not in ALLOWED_SAVE_DESTINATIONS:
        raise ValueError("literature review artifacts may only be saved under work/reviews/ or knowledge/literature/")
    filename = request.filename.strip() or f"{_slug(request.run_id)}-literature-review.md"
    path = Path(filename)
    if path.is_absolute() or ".." in path.parts or path.name != filename:
        raise ValueError("artifact filename must be a simple relative Markdown filename")
    if path.suffix.lower() != ".md":
        filename = f"{filename}.md"
    return f"{destination}/{filename}"


def _write_artifact(project_root: Path, relative_path: str, markdown: str) -> Path:
    path = project_root / relative_path
    resolved_root = project_root.resolve()
    resolved_path = path.resolve()
    if resolved_root not in (resolved_path, *resolved_path.parents):
        raise ValueError("artifact path escapes the project root")
    if not any(relative_path.startswith(f"{allowed}/") for allowed in ALLOWED_SAVE_DESTINATIONS):
        raise ValueError("artifact destination is not allowed")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown)
    return path


def _format_refs(statement: ArtifactStatement) -> str:
    if not statement.source_ids:
        return ""
    pieces = [f"source:{source_id}" for source_id in statement.source_ids]
    pieces.extend(f"citation:{citation_id}" for citation_id in statement.citation_ids)
    for locator in statement.locators:
        if locator:
            pieces.append(f"locator:{json.dumps(locator, sort_keys=True)}")
    return f" ({'; '.join(pieces)})"


def _sentence(text: str) -> str:
    cleaned = " ".join(str(text or "").split())
    match = re.match(r"(.+?[.!?])(?:\s|$)", cleaned)
    return (match.group(1) if match else cleaned[:240]).strip()


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-").lower()
    return slug or "review"
