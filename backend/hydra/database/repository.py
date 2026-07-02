import json
import uuid
import time
import re
from datetime import datetime, timezone
from typing import Any, Optional, List

from sqlmodel import select, or_, and_, delete
from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.database.models import (
    Workspace,
    Conversation,
    Message,
    Source,
    Note,
    Citation,
    Claim,
    EvidenceLink,
    IngestionArtifact,
    IngestionJob,
    ExtractedImage,
    ConversionWarning,
    IndexQueueItem,
    Task,
    Setting,
    ProviderSettings,
    ActivityEvent,
    NoteLink,
    AgentRun,
    Annotation,
    BrowserEvent,
    Chat,
    DocxArtifact,
    KgEdge,
    LexicalIndexEntry,
    McpArtifact,
    McpServer,
    McpTool,
    McpToolCallEvent,
    ReviewItem,
    SourceMergeRecord,
    SourceTombstone,
    TaskLink,
)
from hydra.browser_bridge import TRUST_LEVEL_UNTRUSTED
from hydra.services.citations import (
    CitationParseError,
    bibtex_to_csl_json,
    citation_key as compute_citation_key,
    csl_json_to_bibtex,
    csl_json_to_ris,
    find_duplicates,
    ris_to_csl_json,
)


def _safe_json(value: Any, fallback: Any) -> Any:
    if value is None:
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


CLAIM_SUPPORTED_STATUSES = {"supported", "weak", "contradicted"}
CLAIM_OPEN_STATUSES = {"draft", "needs_review", "rejected"}


SOURCE_DIRECT_REFERENCE_COLUMNS: set[tuple[str, str]] = {
    ("annotations", "source_id"),
    ("citations", "source_id"),
    ("conversion_warnings", "source_id"),
    ("evidence_links", "source_id"),
    ("extracted_images", "source_id"),
    ("ingestion_artifacts", "source_id"),
    ("ingestion_jobs", "source_id"),
    ("lexical_index_entries", "source_id"),
    ("notes", "source_id"),
    ("note_links", "target_source_id"),
}

# Convention: polymorphic source references use a sibling type column whose
# value is "source" and an id/path column carrying the stable source id.
SOURCE_POLYMORPHIC_REFERENCE_COLUMNS: set[tuple[str, str, str, str]] = {
    ("claims", "location_type", "source", "location_id"),
    ("index_queue_items", "target_type", "source", "target_id_or_path"),
    ("kg_edges", "dst_type", "source", "dst_id_or_path"),
    ("kg_edges", "src_type", "source", "src_id"),
    ("note_links", "source_type", "source", "source_id"),
    ("review_items", "origin_type", "source", "origin_id"),
    ("review_items", "target_type", "source", "target_id"),
    ("task_links", "target_type", "source", "target_id_or_path"),
}

_SOURCE_DIRECT_MODELS = {
    ("annotations", "source_id"): (Annotation, Annotation.source_id),
    ("citations", "source_id"): (Citation, Citation.source_id),
    ("conversion_warnings", "source_id"): (ConversionWarning, ConversionWarning.source_id),
    ("evidence_links", "source_id"): (EvidenceLink, EvidenceLink.source_id),
    ("extracted_images", "source_id"): (ExtractedImage, ExtractedImage.source_id),
    ("ingestion_artifacts", "source_id"): (IngestionArtifact, IngestionArtifact.source_id),
    ("ingestion_jobs", "source_id"): (IngestionJob, IngestionJob.source_id),
    ("lexical_index_entries", "source_id"): (LexicalIndexEntry, LexicalIndexEntry.source_id),
    ("notes", "source_id"): (Note, Note.source_id),
    ("note_links", "target_source_id"): (NoteLink, NoteLink.target_source_id),
}

_SOURCE_POLYMORPHIC_MODELS = {
    ("claims", "location_type", "source", "location_id"): (Claim, Claim.location_type, Claim.location_id),
    ("index_queue_items", "target_type", "source", "target_id_or_path"): (
        IndexQueueItem,
        IndexQueueItem.target_type,
        IndexQueueItem.target_id_or_path,
    ),
    ("kg_edges", "dst_type", "source", "dst_id_or_path"): (KgEdge, KgEdge.dst_type, KgEdge.dst_id_or_path),
    ("kg_edges", "src_type", "source", "src_id"): (KgEdge, KgEdge.src_type, KgEdge.src_id),
    ("note_links", "source_type", "source", "source_id"): (NoteLink, NoteLink.source_type, NoteLink.source_id),
    ("review_items", "origin_type", "source", "origin_id"): (ReviewItem, ReviewItem.origin_type, ReviewItem.origin_id),
    ("review_items", "target_type", "source", "target_id"): (ReviewItem, ReviewItem.target_type, ReviewItem.target_id),
    ("task_links", "target_type", "source", "target_id_or_path"): (
        TaskLink,
        TaskLink.target_type,
        TaskLink.target_id_or_path,
    ),
}


class Repository:
    def __init__(self, session: AsyncSession):
        self.session = session

    def _to_dict(self, model: Any) -> Optional[dict[str, Any]]:
        if model is None:
            return None
        d = model.model_dump()
        for k, v in d.items():
            if isinstance(v, datetime):
                # Convert datetime to float timestamp to match raw SQLite Store behavior
                d[k] = v.timestamp()
        
        # Table specific key transformations
        if hasattr(model, "__tablename__"):
            if model.__tablename__ == "tasks":
                if "column_name" in d:
                    d["column"] = d.pop("column_name")
                d["status"] = d.get("column")
                if isinstance(d.get("tags"), str):
                    try:
                        d["tags"] = json.loads(d["tags"] or "[]")
                    except json.JSONDecodeError:
                        d["tags"] = []
            if model.__tablename__ in {"browser_events", "sources"} and d.get("detected_metadata"):
                d["detected_metadata"] = json.loads(d["detected_metadata"] or "{}")
            if model.__tablename__ == "sources" and d.get("metadata_json"):
                d["metadata_json"] = json.loads(d["metadata_json"] or "{}")
            if model.__tablename__ == "sources" and d.get("metadata_sources_json"):
                d["metadata_sources"] = json.loads(d["metadata_sources_json"] or "[]")
            if model.__tablename__ == "sources":
                d["csl_json"] = _safe_json(d.get("csl_json"), {})
                d["keywords"] = _safe_json(d.get("keywords"), [])
                d["identifiers"] = _safe_json(d.get("identifiers"), {})
            if model.__tablename__ == "claims":
                d["claim_text"] = d.get("text")
            if model.__tablename__ == "evidence_links":
                d["locator"] = _safe_json(d.get("locator"), {})
                if not d.get("support_level"):
                    d["support_level"] = d.get("support")
            if model.__tablename__ == "review_items" and d.get("payload_json"):
                d["payload"] = json.loads(d["payload_json"] or "{}")
        return d

    def _to_dict_list(self, models: List[Any]) -> list[dict[str, Any]]:
        return [self._to_dict(m) for m in models if m is not None]

    # Workspace CRUD
    async def create_workspace(self, name: str) -> dict[str, Any]:
        workspace = Workspace(name=name)
        self.session.add(workspace)
        await self.session.commit()
        await self.session.refresh(workspace)
        return self._to_dict(workspace)

    async def get_workspace(self, workspace_id: str) -> Optional[dict[str, Any]]:
        workspace = await self.session.get(Workspace, workspace_id)
        return self._to_dict(workspace)

    async def get_workspaces(self) -> list[dict[str, Any]]:
        res = await self.session.exec(select(Workspace))
        return self._to_dict_list(res.all())

    # Conversation CRUD
    async def create_conversation(self, title: str, workspace_id: Optional[str] = None) -> dict[str, Any]:
        conv = Conversation(title=title, workspace_id=workspace_id)
        self.session.add(conv)
        await self.session.commit()
        await self.session.refresh(conv)
        return self._to_dict(conv)

    async def list_conversations(self, workspace_id: Optional[str] = None) -> list[dict[str, Any]]:
        q = select(Conversation)
        if workspace_id:
            q = q.where(Conversation.workspace_id == workspace_id)
        q = q.order_by(Conversation.created_at.desc())
        res = await self.session.exec(q)
        return self._to_dict_list(res.all())

    async def get_conversation(self, conversation_id: str) -> Optional[dict[str, Any]]:
        conv = await self.session.get(Conversation, conversation_id)
        return self._to_dict(conv)

    # Message CRUD
    async def add_message(self, conversation_id: str, role: str, content: str) -> dict[str, Any]:
        msg = Message(conversation_id=conversation_id, role=role, content=content)
        self.session.add(msg)
        await self.session.commit()
        await self.session.refresh(msg)
        return self._to_dict(msg)

    async def list_messages(self, conversation_id: str) -> list[dict[str, Any]]:
        q = select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at.asc())
        res = await self.session.exec(q)
        return self._to_dict_list(res.all())

    # Chat CRUD (Section 31.4 — SQLite canonical, project-scoped named chats)
    async def ensure_default_chat(self, project_id: str) -> dict[str, Any]:
        q = select(Chat).where(and_(Chat.project_id == project_id, Chat.soft_deleted == False))  # noqa: E712
        existing = (await self.session.exec(q.order_by(Chat.created_at.asc()))).first()
        if existing:
            return self._to_dict(existing)
        chat = Chat(project_id=project_id, name="default")
        self.session.add(chat)
        await self.session.commit()
        await self.session.refresh(chat)
        return self._to_dict(chat)

    async def create_chat(self, project_id: str, name: str) -> dict[str, Any]:
        chat = Chat(project_id=project_id, name=name or "New chat")
        self.session.add(chat)
        await self.session.commit()
        await self.session.refresh(chat)
        return self._to_dict(chat)

    async def list_chats(self, project_id: str, include_archived: bool = True) -> list[dict[str, Any]]:
        q = select(Chat).where(and_(Chat.project_id == project_id, Chat.soft_deleted == False))  # noqa: E712
        if not include_archived:
            q = q.where(Chat.archived == False)  # noqa: E712
        q = q.order_by(Chat.created_at.asc())
        res = await self.session.exec(q)
        return self._to_dict_list(res.all())

    async def get_chat(self, chat_id: str) -> Optional[dict[str, Any]]:
        return self._to_dict(await self.session.get(Chat, chat_id))

    async def update_chat(self, chat_id: str, *, name: Optional[str] = None, archived: Optional[bool] = None) -> Optional[dict[str, Any]]:
        chat = await self.session.get(Chat, chat_id)
        if not chat:
            return None
        if name is not None:
            chat.name = name
        if archived is not None:
            chat.archived = archived
        chat.updated_at = datetime.now(timezone.utc)
        self.session.add(chat)
        await self.session.commit()
        await self.session.refresh(chat)
        return self._to_dict(chat)

    async def search_chats(self, project_id: str, query: str) -> list[dict[str, Any]]:
        # Archived chats remain searchable (HL-ASSIST-02).
        q = select(Chat).where(and_(Chat.project_id == project_id, Chat.soft_deleted == False))  # noqa: E712
        if query:
            q = q.where(Chat.name.like(f"%{query}%"))
        q = q.order_by(Chat.updated_at.desc())
        res = await self.session.exec(q)
        return self._to_dict_list(res.all())

    async def add_chat_message(
        self,
        chat_id: str,
        role: str,
        content: str,
        *,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        context_refs: Optional[list[dict[str, Any]]] = None,
        trust_origin: str = "user",
    ) -> dict[str, Any]:
        msg = Message(
            chat_id=chat_id,
            role=role,
            content=content,
            model=model,
            provider=provider,
            context_refs=json.dumps(context_refs or [], sort_keys=True),
            trust_origin=trust_origin,
        )
        self.session.add(msg)
        await self.session.commit()
        await self.session.refresh(msg)
        return self._to_dict(msg)

    async def append_chat_message_content(self, message_id: str, delta: str) -> None:
        """Incremental persistence (HL-ASSIST-03): flush the streamed prefix each chunk."""
        msg = await self.session.get(Message, message_id)
        if not msg:
            return
        msg.content = (msg.content or "") + delta
        self.session.add(msg)
        await self.session.commit()

    async def list_chat_messages(self, chat_id: str) -> list[dict[str, Any]]:
        q = select(Message).where(Message.chat_id == chat_id).order_by(Message.created_at.asc())
        res = await self.session.exec(q)
        rows = self._to_dict_list(res.all())
        for row in rows:
            if isinstance(row.get("context_refs"), str):
                try:
                    row["context_refs"] = json.loads(row["context_refs"] or "[]")
                except json.JSONDecodeError:
                    row["context_refs"] = []
        return rows

    # Source CRUD
    async def upsert_source(self, source_data: dict[str, Any]) -> dict[str, Any]:
        source_id = source_data.get("id") or f"src_{uuid.uuid4().hex[:12]}"
        source = await self.session.get(Source, source_id)
        
        # Prepare fields
        title = source_data.get("title") or "Untitled source"
        authors = source_data.get("authors") or ""
        year = str(source_data.get("year") or "")
        url = source_data.get("url") or ""
        abstract = source_data.get("abstract") or ""
        kind = source_data.get("kind") or "article"
        metadata_json = source_data.get("metadata_json")
        metadata_sources_json = source_data.get("metadata_sources_json")
        workspace_id = source_data.get("workspace_id")
        project_id = source_data.get("project_id")
        trust_origin = source_data.get("trust_origin")
        doi = source_data.get("doi")
        arxiv_id = source_data.get("arxiv_id")
        source_type = source_data.get("source_type")

        extended_fields = {
            "venue": source_data.get("venue"),
            "publisher": source_data.get("publisher"),
            "confidence": source_data.get("confidence"),
            "duplicate_group_id": source_data.get("duplicate_group_id"),
            "duplicate_status": source_data.get("duplicate_status"),
            "merge_confidence": source_data.get("merge_confidence"),
        }
        json_fields = {
            "keywords": source_data.get("keywords"),
            "identifiers": source_data.get("identifiers"),
            "csl_json": source_data.get("csl_json"),
        }
        bibtex = source_data.get("bibtex")
        ris = source_data.get("ris")

        def _apply_extended(target: Source) -> None:
            for name, value in extended_fields.items():
                if value is not None:
                    setattr(target, name, value)
            for name, value in json_fields.items():
                if value is not None:
                    setattr(target, name, value if isinstance(value, str) else json.dumps(value, sort_keys=True))
            if bibtex is not None:
                target.bibtex = bibtex
            if ris is not None:
                target.ris = ris

        if source:
            source.title = title
            source.authors = authors
            source.year = year
            source.url = url
            source.abstract = abstract
            source.kind = kind
            if metadata_json is not None:
                source.metadata_json = metadata_json
            if metadata_sources_json is not None:
                source.metadata_sources_json = metadata_sources_json
            if workspace_id is not None:
                source.workspace_id = workspace_id
            if project_id is not None:
                source.project_id = project_id
            if trust_origin is not None:
                source.trust_origin = trust_origin
            if doi is not None:
                source.doi = doi
            if arxiv_id is not None:
                source.arxiv_id = arxiv_id
            if source_type is not None:
                source.source_type = source_type
            _apply_extended(source)
            source.updated_at = datetime.now(timezone.utc)
        else:
            source = Source(
                id=source_id,
                workspace_id=workspace_id,
                project_id=project_id,
                title=title,
                authors=authors,
                year=year,
                url=url,
                abstract=abstract,
                kind=kind,
                source_type=source_type or kind,
                metadata_json=metadata_json,
                metadata_sources_json=metadata_sources_json or "[]",
                trust_origin=trust_origin or "user",
                doi=doi,
                arxiv_id=arxiv_id,
            )
            _apply_extended(source)
            self.session.add(source)

        await self.session.commit()
        await self.session.refresh(source)
        return self._to_dict(source)

    async def list_sources(self) -> list[dict[str, Any]]:
        res = await self.session.exec(select(Source).order_by(Source.created_at.desc()))
        return self._to_dict_list(res.all())

    # Citation CRUD
    async def add_citation(
        self,
        source_id: str,
        text: str,
        citation_key: str = "",
        csl_json: Optional[str] = None,
        doi: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> dict[str, Any]:
        source = await self.session.get(Source, source_id)
        resolved_csl = csl_json
        resolved_key = citation_key
        if source is not None:
            if resolved_csl is None:
                resolved_csl = source.csl_json
            if not resolved_key:
                resolved_key = compute_citation_key(_safe_json(source.csl_json, {}))
            if doi is None:
                doi = source.doi
        cit = Citation(
            source_id=source_id,
            text=text,
            citation_key=resolved_key or "",
            csl_json=resolved_csl or "{}",
            doi=doi,
            project_id=project_id,
        )
        self.session.add(cit)
        await self.session.commit()
        await self.session.refresh(cit)
        return self._to_dict(cit)

    async def list_citations(self) -> list[dict[str, Any]]:
        res = await self.session.exec(select(Citation).order_by(Citation.created_at.desc()))
        return self._to_dict_list(res.all())

    # Claim CRUD
    async def add_claim(
        self,
        text: str,
        workspace_id: Optional[str] = None,
        project_id: Optional[str] = None,
        claim_type: str = "",
        location_type: Optional[str] = None,
        location_id: Optional[str] = None,
        location_range: Optional[str] = None,
        status: str = "draft",
        created_from: str = "manual",
        notes_path: Optional[str] = None,
        origin_ref: Optional[str] = None,
        origin_quote: str = "",
        extraction_confidence: float = 0.0,
        extraction_mode: str = "manual",
        trust_origin: str = "user",
    ) -> dict[str, Any]:
        if location_type is not None and location_id is None:
            raise ValueError("location_id is required when location_type is set")
        if extraction_mode == "auto_draft" and status not in {"draft", "needs_review"}:
            raise ValueError("auto_draft claims may only be created at draft/needs_review status")
        if status in CLAIM_SUPPORTED_STATUSES:
            raise ValueError("a new claim may not be created at a supported/weak/contradicted status")
        claim = Claim(
            text=text,
            workspace_id=workspace_id,
            project_id=project_id,
            claim_type=claim_type,
            location_type=location_type,
            location_id=location_id,
            location_range=location_range,
            status=status,
            created_from=created_from,
            notes_path=notes_path,
            origin_ref=origin_ref,
            origin_quote=origin_quote,
            extraction_confidence=extraction_confidence,
            extraction_mode=extraction_mode,
            trust_origin=trust_origin,
        )
        self.session.add(claim)
        await self.session.commit()
        await self.session.refresh(claim)
        return self._to_dict(claim)

    async def list_claims(self, workspace_id: Optional[str] = None) -> list[dict[str, Any]]:
        q = select(Claim)
        if workspace_id:
            q = q.where(Claim.workspace_id == workspace_id)
        q = q.order_by(Claim.created_at.desc())
        res = await self.session.exec(q)
        return self._to_dict_list(res.all())

    # Evidence CRUD
    async def add_evidence(
        self,
        claim_id: str,
        source_id: str,
        passage: str,
        support: str,
        confidence: float,
        review_status: str = "needs_review",
        citation_id: Optional[str] = None,
        asset_id: Optional[str] = None,
        annotation_id: Optional[str] = None,
        sidecar_path: Optional[str] = None,
        sidecar_record_id: Optional[str] = None,
        evidence_type: str = "quote",
        locator: Any = None,
        quote_text: str = "",
        summary: str = "",
        support_level: str = "",
        created_by: str = "user",
    ) -> dict[str, Any]:
        ev = EvidenceLink(
            claim_id=claim_id,
            source_id=source_id,
            passage=passage,
            support=support,
            support_level=support_level or support,
            confidence=confidence,
            review_status=review_status,
            citation_id=citation_id,
            asset_id=asset_id,
            annotation_id=annotation_id,
            sidecar_path=sidecar_path,
            sidecar_record_id=sidecar_record_id,
            evidence_type=evidence_type,
            locator=locator if isinstance(locator, str) else json.dumps(locator or {}, sort_keys=True),
            quote_text=quote_text or passage,
            summary=summary,
            created_by=created_by,
        )
        self.session.add(ev)
        await self.session.commit()
        await self.session.refresh(ev)
        return self._to_dict(ev)

    async def promote_claim(self, claim_id: str, status: str, reviewed: bool = False) -> dict[str, Any]:
        """Validate the evidence-required status-promotion rule (HL-CITE-09).

        A claim may only reach ``supported``/``weak``/``contradicted`` with at
        least one linked evidence record AND an explicit review; otherwise the
        claim keeps its prior status and a ``ValueError`` is raised.
        """
        claim = await self.session.get(Claim, claim_id)
        if claim is None:
            raise ValueError("claim not found")
        if status in CLAIM_SUPPORTED_STATUSES:
            evidence = (await self.session.exec(select(EvidenceLink).where(EvidenceLink.claim_id == claim_id))).all()
            if not evidence:
                raise ValueError("evidence and review are required before a claim can be supported/weak/contradicted")
            if not reviewed:
                raise ValueError("a review step is required before a claim can be supported/weak/contradicted")
            if claim.link_state == "target_trashed":
                raise ValueError("a claim referencing a trashed target cannot be promoted")
        claim.status = status
        claim.updated_at = datetime.now(timezone.utc)
        self.session.add(claim)
        await self.session.commit()
        await self.session.refresh(claim)
        return self._to_dict(claim)

    async def resolve_claim_location(self, location_type: Optional[str], location_id: Optional[str]) -> dict[str, Any]:
        """Section 32.2 resolver: return the live target or a typed not-found."""
        if not location_type or not location_id:
            return {"resolved": False, "reason": "unset", "location_type": location_type, "location_id": location_id}
        model_map = {
            "source": Source,
            "note": Note,
            "draft": Note,
            "chat": Chat,
            "manuscript": Note,
        }
        model = model_map.get(location_type)
        if model is None:
            return {"resolved": False, "reason": "unknown-location-type", "location_type": location_type, "location_id": location_id}
        target = await self.session.get(model, location_id)
        if target is None:
            return {"resolved": False, "reason": "not-found", "location_type": location_type, "location_id": location_id}
        return {"resolved": True, "location_type": location_type, "location_id": location_id, "target": self._to_dict(target)}

    async def list_evidence(self) -> list[dict[str, Any]]:
        # Fetch evidence links joined with sources and claims
        q = select(EvidenceLink, Source.title.label("source_title"), Source.url.label("source_url"), Claim.text.label("claim_text")).join(
            Source, Source.id == EvidenceLink.source_id
        ).join(
            Claim, Claim.id == EvidenceLink.claim_id
        ).order_by(EvidenceLink.created_at.desc())
        
        res = await self.session.exec(q)
        evidence_list = []
        for row in res.all():
            ev = row[0]
            d = self._to_dict(ev)
            d["source_title"] = row.source_title
            d["source_url"] = row.source_url
            d["claim_text"] = row.claim_text
            evidence_list.append(d)
        return evidence_list

    # Note CRUD with parse-on-write wiki-link sync
    async def add_note(self, title: str, body: str, source_id: Optional[str] = None, workspace_id: Optional[str] = None) -> dict[str, Any]:
        note = Note(title=title, body=body, source_id=source_id, workspace_id=workspace_id)
        self.session.add(note)
        await self.session.commit()
        await self.session.refresh(note)
        await self.sync_wiki_links(note)
        return self._to_dict(note)

    async def get_note(self, note_id: str) -> Optional[dict[str, Any]]:
        note = await self.session.get(Note, note_id)
        return self._to_dict(note)

    async def search_notes(self, query: Optional[str] = None, workspace_id: Optional[str] = None) -> list[dict[str, Any]]:
        q = select(Note)
        if workspace_id:
            q = q.where(Note.workspace_id == workspace_id)
        if query:
            q = q.where(or_(Note.title.like(f"%{query}%"), Note.body.like(f"%{query}%")))
        q = q.order_by(Note.updated_at.desc())
        res = await self.session.exec(q)
        return self._to_dict_list(res.all())

    async def update_note(self, note_id: str, title: str, body: str, source_id: Optional[str] = None) -> Optional[dict[str, Any]]:
        note = await self.session.get(Note, note_id)
        if not note:
            return None
        note.title = title
        note.body = body
        note.source_id = source_id
        note.updated_at = datetime.now(timezone.utc)
        self.session.add(note)
        await self.session.commit()
        await self.session.refresh(note)
        await self.sync_wiki_links(note)
        return self._to_dict(note)

    async def delete_note(self, note_id: str) -> bool:
        note = await self.session.get(Note, note_id)
        if not note:
            return False
        # Delete links associated with the note
        await self.session.exec(delete(NoteLink).where(or_(NoteLink.source_id == note_id, NoteLink.target_note_id == note_id)))
        await self.session.delete(note)
        await self.session.commit()
        return True

    # Parse-on-write wiki-link sync
    async def sync_wiki_links(self, note: Note):
        # 1. Delete existing outgoing links from this note
        await self.session.exec(
            delete(NoteLink).where(and_(NoteLink.source_id == note.id, NoteLink.source_type == "note"))
        )
        await self.session.commit()

        # 2. Extract [[Target Name]] from note body
        body = note.body or ""
        wiki_pattern = r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]"
        matches = re.findall(wiki_pattern, body)
        if not matches:
            return

        # 3. Resolve all target node IDs dynamically in one transaction
        notes_res = await self.session.exec(select(Note))
        sources_res = await self.session.exec(select(Source))
        tasks_res = await self.session.exec(select(Task))
        claims_res = await self.session.exec(select(Claim))

        id_map = {}
        for n in notes_res.all():
            id_map[n.id] = ("note", n.id)
            id_map[n.title.lower()] = ("note", n.id)

        for s in sources_res.all():
            id_map[s.id] = ("source", s.id)
            id_map[s.title.lower()] = ("source", s.id)

        for t in tasks_res.all():
            id_map[t.id] = ("task", t.id)
            id_map[t.title.lower()] = ("task", t.id)

        for c in claims_res.all():
            id_map[c.id] = ("claim", c.id)
            id_map[c.text.lower()] = ("claim", c.id)

        for match in matches:
            match_val = match.strip()
            match_lower = match_val.lower()

            target_type = None
            target_id = None

            if match_val in id_map:
                target_type, target_id = id_map[match_val]
            elif match_lower in id_map:
                target_type, target_id = id_map[match_lower]

            link = NoteLink(
                source_id=note.id,
                source_type="note",
                raw_target_name=match_val,
                link_type="wiki"
            )

            if target_type == "note":
                link.target_note_id = target_id
            elif target_type == "source":
                link.target_source_id = target_id
            elif target_type == "task":
                link.target_task_id = target_id
            elif target_type == "claim":
                link.target_claim_id = target_id

            self.session.add(link)

        await self.session.commit()

    # Fast get_note_links endpoint
    async def get_note_links(self, note_id: str) -> dict[str, Any]:
        # 1. Fetch outgoing links
        out_res = await self.session.exec(
            select(NoteLink).where(and_(NoteLink.source_id == note_id, NoteLink.source_type == "note"))
        )
        outgoing_links = out_res.all()

        # 2. Fetch incoming links
        inc_res = await self.session.exec(
            select(NoteLink).where(NoteLink.target_note_id == note_id)
        )
        incoming_links = inc_res.all()

        # Deduplicate forward links by target ID
        unique_forward = []
        seen_forward = set()
        for link in outgoing_links:
            target_id = None
            target_title = link.raw_target_name
            target_type = "note"

            if link.target_note_id:
                target_id = link.target_note_id
                target_type = "note"
                n = await self.session.get(Note, target_id)
                if n:
                    target_title = n.title
            elif link.target_source_id:
                target_id = link.target_source_id
                target_type = "source"
                s = await self.session.get(Source, target_id)
                if s:
                    target_title = s.title
            elif link.target_task_id:
                target_id = link.target_task_id
                target_type = "task"
                t = await self.session.get(Task, target_id)
                if t:
                    target_title = t.title
            elif link.target_claim_id:
                target_id = link.target_claim_id
                target_type = "claim"
                c = await self.session.get(Claim, target_id)
                if c:
                    target_title = c.text[:50]

            if target_id and target_id not in seen_forward:
                seen_forward.add(target_id)
                unique_forward.append({
                    "id": target_id,
                    "title": target_title,
                    "type": target_type,
                    "relation": link.link_type
                })

        # Deduplicate incoming links by source ID
        unique_backlinks = []
        seen_backlinks = set()
        for link in incoming_links:
            source_id = link.source_id
            source_type = link.source_type
            source_title = "Unknown"

            if source_type == "note":
                n = await self.session.get(Note, source_id)
                if n:
                    source_title = n.title
            elif source_type == "task":
                t = await self.session.get(Task, source_id)
                if t:
                    source_title = t.title

            if source_id not in seen_backlinks:
                seen_backlinks.add(source_id)
                unique_backlinks.append({
                    "id": source_id,
                    "title": source_title,
                    "type": source_type,
                    "relation": link.link_type
                })

        return {
            "forward": unique_forward,
            "backlinks": unique_backlinks
        }

    # Graph implementation
    async def get_graph(self) -> dict[str, Any]:
        notes = await self.session.exec(select(Note))
        sources = await self.session.exec(select(Source))
        tasks = await self.session.exec(select(Task))
        claims = await self.session.exec(select(Claim))
        conversations = await self.session.exec(select(Conversation))

        nodes = []
        for n in notes.all():
            nodes.append({"id": n.id, "title": n.title, "type": "note"})
        for s in sources.all():
            nodes.append({"id": s.id, "title": s.title, "type": "source"})
        for t in tasks.all():
            nodes.append({"id": t.id, "title": t.title, "type": "task"})
        for c in claims.all():
            nodes.append({"id": c.id, "title": c.text[:50], "type": "claim"})
        for conv in conversations.all():
            nodes.append({"id": conv.id, "title": conv.title, "type": "conversation"})

        links = []
        seen_links = set()

        def add_link(source_id: str, target_id: str, rel_type: str):
            if not source_id or not target_id:
                return
            if source_id == target_id:
                return
            link_key = (source_id, target_id, rel_type)
            if link_key not in seen_links:
                seen_links.add(link_key)
                links.append({"source": source_id, "target": target_id, "type": rel_type})

        # Base references from notes
        for n in await self.session.exec(select(Note)):
            if n.source_id:
                add_link(n.id, n.source_id, "references")

        # Evidence links
        evidence = await self.session.exec(select(EvidenceLink))
        for e in evidence.all():
            add_link(e.claim_id, e.source_id, "evidence")
            if e.citation_id:
                add_link(e.claim_id, e.citation_id, "citation")

        # Wiki links from NoteLinks
        note_links = await self.session.exec(select(NoteLink))
        for l in note_links.all():
            target_id = l.target_note_id or l.target_source_id or l.target_task_id or l.target_claim_id
            if target_id:
                add_link(l.source_id, target_id, l.link_type)

        return {"nodes": nodes, "links": links}

    # Task CRUD
    async def add_task(
        self,
        title: str,
        column: str,
        detail: str = "",
        progress: int = 0,
        phase_indicator: str = "",
        position: int = 0,
        workspace_id: Optional[str] = None,
        project_id: Optional[str] = None,
        due: Optional[str] = None,
        priority: str = "normal",
        tags: Optional[list[str]] = None,
        origin: str = "manual",
        assistant_created: bool = False,
        lifecycle_state: str = "active",
        review_category: Optional[str] = None,
        trust_origin: str = "user",
    ) -> dict[str, Any]:
        task = Task(
            title=title,
            column_name=column,
            detail=detail,
            progress=progress,
            phase_indicator=phase_indicator,
            position=position,
            workspace_id=workspace_id,
            project_id=project_id,
            due=due,
            priority=priority,
            tags=json.dumps(tags or []),
            origin=origin,
            assistant_created=assistant_created,
            lifecycle_state=lifecycle_state,
            review_category=review_category,
            trust_origin=trust_origin,
        )
        self.session.add(task)
        await self.session.commit()
        await self.session.refresh(task)
        return self._to_dict(task)

    async def create_task_link(
        self,
        task_id: str,
        target_type: str,
        target_id_or_path: str,
        link_role: str = "about",
    ) -> dict[str, Any]:
        link_state = "live"
        if await self._task_link_target_trashed(target_type, target_id_or_path):
            link_state = "source_trashed"
        link = TaskLink(
            task_id=task_id,
            target_type=target_type,
            target_id_or_path=self._resolve_task_link_target(target_type, target_id_or_path) or target_id_or_path,
            link_role=link_role,
            link_state=link_state,
        )
        self.session.add(link)
        await self.session.commit()
        await self.session.refresh(link)
        return self._to_dict(link)

    def _resolve_task_link_target(self, target_type: str, target_id_or_path: str) -> Optional[str]:
        # A path-backed target resolves to a stable id when one exists is handled
        # by the caller (app) which passes stable ids; here we pass-through.
        return target_id_or_path

    async def _task_link_target_trashed(self, target_type: str, target_id: str) -> bool:
        model = {
            "source": Source,
            "note": Note,
            "claim": Claim,
            "task": Task,
        }.get(target_type)
        if model is None:
            return False
        obj = await self.session.get(model, target_id)
        if obj is None:
            return False
        return bool(getattr(obj, "trashed", False) or getattr(obj, "soft_deleted", False))

    async def list_task_links(self, task_id: str) -> list[dict[str, Any]]:
        res = await self.session.exec(select(TaskLink).where(TaskLink.task_id == task_id))
        return self._to_dict_list(res.all())

    async def flag_task_links_for_trashed_target(self, target_type: str, target_id: str) -> int:
        res = await self.session.exec(
            select(TaskLink).where(and_(TaskLink.target_type == target_type, TaskLink.target_id_or_path == target_id))
        )
        rows = res.all()
        for link in rows:
            link.link_state = "source_trashed"
            self.session.add(link)
            self.session.add(
                ReviewItem(
                    item_type="broken-link",
                    title="Task link target trashed",
                    summary="A task link points to a trashed research object.",
                    origin_type="task_link",
                    origin_id=link.id,
                    target_type=target_type,
                    target_id=target_id,
                )
            )
        await self.session.commit()
        return len(rows)

    async def reattach_task_links_for_target(self, target_type: str, target_id: str) -> int:
        res = await self.session.exec(
            select(TaskLink).where(
                and_(
                    TaskLink.target_type == target_type,
                    TaskLink.target_id_or_path == target_id,
                    TaskLink.link_state == "source_trashed",
                )
            )
        )
        rows = res.all()
        for link in rows:
            link.link_state = "live"
            self.session.add(link)
        await self.session.commit()
        return len(rows)

    async def accept_task(self, task_id: str) -> Optional[dict[str, Any]]:
        task = await self.session.get(Task, task_id)
        if task is None:
            return None
        task.lifecycle_state = "active"
        task.updated_at = datetime.now(timezone.utc)
        self.session.add(task)
        await self._resolve_task_review_items(task_id, "accepted")
        await self.session.commit()
        await self.session.refresh(task)
        return self._to_dict(task)

    async def dismiss_task(self, task_id: str) -> Optional[dict[str, Any]]:
        task = await self.session.get(Task, task_id)
        if task is None:
            return None
        task.lifecycle_state = "dismissed"
        task.updated_at = datetime.now(timezone.utc)
        self.session.add(task)
        await self._resolve_task_review_items(task_id, "dismissed")
        await self.session.commit()
        await self.session.refresh(task)
        return self._to_dict(task)

    async def bulk_dismiss_draft_tasks(self, project_id: Optional[str] = None) -> int:
        q = select(Task).where(and_(Task.lifecycle_state == "draft", Task.assistant_created == True))  # noqa: E712
        if project_id:
            q = q.where(Task.project_id == project_id)
        rows = (await self.session.exec(q)).all()
        for task in rows:
            task.lifecycle_state = "dismissed"
            self.session.add(task)
            await self._resolve_task_review_items(task.id, "dismissed")
        await self.session.commit()
        return len(rows)

    async def _resolve_task_review_items(self, task_id: str, status: str) -> None:
        res = await self.session.exec(
            select(ReviewItem).where(and_(ReviewItem.item_type == "draft_task", ReviewItem.target_id == task_id))
        )
        for item in res.all():
            item.status = status
            item.updated_at = datetime.now(timezone.utc)
            self.session.add(item)

    async def update_task(self, task_id: str, updates: dict[str, Any]) -> Optional[dict[str, Any]]:
        task = await self.session.get(Task, task_id)
        if not task:
            return None
        
        # Map input key "column" back to database field "column_name"
        if "column" in updates:
            updates["column_name"] = updates.pop("column")

        for k, v in updates.items():
            if hasattr(task, k):
                setattr(task, k, v)
        task.updated_at = datetime.now(timezone.utc)
        self.session.add(task)
        await self.session.commit()
        await self.session.refresh(task)
        return self._to_dict(task)

    async def delete_task(self, task_id: str) -> bool:
        task = await self.session.get(Task, task_id)
        if not task:
            return False
        await self.session.delete(task)
        await self.session.commit()
        return True

    async def list_tasks(
        self,
        workspace_id: Optional[str] = None,
        state: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        q = select(Task)
        if workspace_id:
            q = q.where(Task.workspace_id == workspace_id)
        if project_id:
            q = q.where(Task.project_id == project_id)
        if state and state != "all":
            q = q.where(Task.lifecycle_state == state)
        q = q.order_by(Task.position.asc(), Task.created_at.asc())
        res = await self.session.exec(q)
        return self._to_dict_list(res.all())

    # ProviderSettings CRUD
    async def save_provider_settings(self, provider: str, model: str, api_key_ref: str = "") -> dict[str, Any]:
        q = select(ProviderSettings).where(ProviderSettings.provider == provider)
        res = await self.session.exec(q)
        existing = res.first()
        
        if existing:
            existing.model = model
            existing.api_key_ref = api_key_ref
            existing.secret_ref = api_key_ref or None
            existing.auth_status = "configured" if api_key_ref else "missing_secret_ref"
            existing.updated_at = datetime.now(timezone.utc)
            ps = existing
        else:
            ps = ProviderSettings(
                provider=provider,
                model=model,
                api_key_ref=api_key_ref,
                secret_ref=api_key_ref or None,
                auth_status="configured" if api_key_ref else "missing_secret_ref",
            )
            self.session.add(ps)
            
        await self.session.commit()
        await self.session.refresh(ps)
        return self._to_dict(ps)

    async def list_provider_settings(self) -> list[dict[str, Any]]:
        res = await self.session.exec(select(ProviderSettings).order_by(ProviderSettings.provider.asc()))
        return self._to_dict_list(res.all())

    # Setting CRUD
    async def save_setting(self, key: str, value: str, workspace_id: Optional[str] = None) -> dict[str, Any]:
        setting = await self.session.get(Setting, key)
        if setting:
            setting.value = value
            setting.updated_at = datetime.now(timezone.utc)
            if workspace_id is not None:
                setting.workspace_id = workspace_id
        else:
            setting = Setting(key=key, value=value, workspace_id=workspace_id)
            self.session.add(setting)
            
        await self.session.commit()
        await self.session.refresh(setting)
        return self._to_dict(setting)

    async def get_setting(self, key: str) -> Optional[dict[str, Any]]:
        setting = await self.session.get(Setting, key)
        return self._to_dict(setting)

    async def list_settings(self, workspace_id: Optional[str] = None) -> dict[str, str]:
        q = select(Setting)
        if workspace_id:
            q = q.where(Setting.workspace_id == workspace_id)
        res = await self.session.exec(q)
        return {s.key: s.value for s in res.all()}

    # ActivityEvents CRUD
    async def add_event(self, kind: str, message: str, payload: str = "{}") -> dict[str, Any]:
        event = ActivityEvent(kind=kind, message=message, payload=payload)
        self.session.add(event)
        await self.session.commit()
        await self.session.refresh(event)
        return self._to_dict(event)

    async def record_docx_artifact(self, **fields: Any) -> dict[str, Any]:
        artifact = DocxArtifact(**fields)
        self.session.add(artifact)
        await self.session.commit()
        await self.session.refresh(artifact)
        return self._to_dict(artifact)

    async def list_docx_artifacts(
        self, manuscript: Optional[str] = None, kind: Optional[str] = None
    ) -> list[dict[str, Any]]:
        q = select(DocxArtifact)
        if manuscript:
            q = q.where(DocxArtifact.manuscript == manuscript)
        if kind:
            q = q.where(DocxArtifact.kind == kind)
        q = q.order_by(DocxArtifact.created_at.desc())
        res = await self.session.exec(q)
        return self._to_dict_list(res.all())

    async def latest_docx_availability(self) -> Optional[dict[str, Any]]:
        q = select(DocxArtifact).where(DocxArtifact.kind == "availability").order_by(DocxArtifact.created_at.desc())
        res = await self.session.exec(q)
        return self._to_dict(res.first())

    async def upsert_browser_event(self, event_data: dict[str, Any]) -> dict[str, Any]:
        q = select(BrowserEvent).where(
            and_(
                BrowserEvent.project_id == event_data["project_id"],
                BrowserEvent.url == event_data["url"],
                BrowserEvent.soft_deleted == False,  # noqa: E712
            )
        )
        existing = (await self.session.exec(q)).first()
        metadata = dict(event_data.get("detected_metadata") or {})
        metadata.setdefault("trust_level", TRUST_LEVEL_UNTRUSTED)

        if existing:
            previous = json.loads(existing.detected_metadata or "{}")
            metadata["revisit_count"] = int(previous.get("revisit_count") or 1) + 1
            metadata["first_seen_at"] = previous.get("first_seen_at") or existing.created_at.timestamp()
            metadata["last_seen_at"] = time.time()
            existing.title = event_data.get("title") or existing.title
            existing.captured_text_ref = event_data.get("page_text") or existing.captured_text_ref
            existing.selection = event_data.get("selection") or existing.selection
            existing.event_type = event_data.get("event_type") or existing.event_type
            existing.detected_metadata = json.dumps(metadata, sort_keys=True)
            existing.trust_origin = TRUST_LEVEL_UNTRUSTED
            self.session.add(existing)
            await self.session.commit()
            await self.session.refresh(existing)
            return self._to_dict(existing)

        metadata["revisit_count"] = 1
        metadata["first_seen_at"] = time.time()
        metadata["last_seen_at"] = metadata["first_seen_at"]
        event = BrowserEvent(
            project_id=event_data["project_id"],
            url=event_data["url"],
            title=event_data.get("title") or "",
            captured_text_ref=event_data.get("page_text") or "",
            selection=event_data.get("selection") or "",
            detected_metadata=json.dumps(metadata, sort_keys=True),
            event_type=event_data.get("event_type") or "capture",
            trust_origin=TRUST_LEVEL_UNTRUSTED,
        )
        self.session.add(event)
        await self.session.commit()
        await self.session.refresh(event)
        return self._to_dict(event)

    async def list_browser_events(self, project_id: str) -> list[dict[str, Any]]:
        q = (
            select(BrowserEvent)
            .where(and_(BrowserEvent.project_id == project_id, BrowserEvent.soft_deleted == False))  # noqa: E712
            .order_by(BrowserEvent.created_at.desc())
        )
        res = await self.session.exec(q)
        return self._to_dict_list(res.all())

    async def create_review_item(self, item_data: dict[str, Any]) -> dict[str, Any]:
        item = ReviewItem(
            project_id=item_data.get("project_id"),
            item_type=item_data["item_type"],
            title=item_data["title"],
            summary=item_data.get("summary", ""),
            origin_type=item_data.get("origin_type"),
            origin_id=item_data.get("origin_id"),
            target_type=item_data.get("target_type"),
            target_id=item_data.get("target_id"),
            payload_json=json.dumps(item_data.get("payload") or {}, sort_keys=True),
        )
        self.session.add(item)
        await self.session.commit()
        await self.session.refresh(item)
        return self._to_dict(item)

    async def list_events(self, limit: int = 100) -> list[dict[str, Any]]:
        q = select(ActivityEvent).order_by(ActivityEvent.created_at.desc()).limit(limit)
        res = await self.session.exec(q)
        return self._to_dict_list(res.all())

    # Export Workspace
    async def export_workspace(self) -> dict[str, Any]:
        return {
            "sources": await self.list_sources(),
            "notes": await self.search_notes(),
            "tasks": await self.list_tasks(),
            "events": await self.list_events(),
            "evidence": await self.list_evidence(),
            "settings": await self.list_settings(),
            "provider_settings": await self.list_provider_settings(),
        }

    _section31_models = {
        "note": Note,
        "kg_edge": KgEdge,
        "task": Task,
        "task_link": TaskLink,
        "chat": Chat,
        "message": Message,
        "browser_event": BrowserEvent,
        "agent_run": AgentRun,
        "annotation": Annotation,
        "source": Source,
        "citation": Citation,
        "claim": Claim,
        "evidence": EvidenceLink,
    }

    async def create_section31_entity(self, entity: str, **data: Any) -> dict[str, Any]:
        model = self._section31_models[entity]
        normalized = self._normalize_section31_data(entity, data)
        obj = model(**normalized)
        self.session.add(obj)
        await self.session.commit()
        await self.session.refresh(obj)
        return self._to_dict(obj)

    async def get_section31_entity(self, entity: str, entity_id: str) -> Optional[dict[str, Any]]:
        model = self._section31_models[entity]
        obj = await self.session.get(model, entity_id)
        return self._to_dict(obj)

    async def list_section31_entities(self, entity: str) -> list[dict[str, Any]]:
        model = self._section31_models[entity]
        res = await self.session.exec(select(model))
        return self._to_dict_list(res.all())

    async def soft_delete_section31_entity(self, entity: str, entity_id: str) -> bool:
        model = self._section31_models[entity]
        obj = await self.session.get(model, entity_id)
        if obj is None:
            return False
        if hasattr(obj, "soft_deleted"):
            obj.soft_deleted = True
        elif hasattr(obj, "trashed"):
            obj.trashed = True
        elif hasattr(obj, "link_state"):
            obj.link_state = "target_trashed"
        else:
            return False
        if hasattr(obj, "updated_at"):
            obj.updated_at = datetime.now(timezone.utc)
        self.session.add(obj)
        await self.session.commit()
        return True

    def _normalize_section31_data(self, entity: str, data: dict[str, Any]) -> dict[str, Any]:
        if entity == "note":
            return {
                "id": data.get("id") or data.get("note_id") or str(uuid.uuid4()),
                "project_id": data.get("project_id"),
                "workspace_id": data.get("workspace_id") or data.get("project_id"),
                "relative_path": data.get("path") or data.get("relative_path") or "",
                "title": data.get("title") or "Untitled note",
                "body": data.get("body") or "",
                "frontmatter": json.dumps(data.get("frontmatter") or {}),
                "content_hash": data.get("content_hash") or "",
                "tags": json.dumps(data.get("tags") or []),
                "trust_origin": data.get("trust_origin") or "user",
            }
        if entity == "kg_edge":
            data.setdefault("id", str(uuid.uuid4()))
            data.setdefault("locator", "{}")
            return data
        if entity == "task":
            data.setdefault("column_name", data.pop("status", "To Do"))
            data.setdefault("title", "Untitled task")
            return data
        if entity == "chat":
            data.setdefault("id", str(uuid.uuid4()))
            data.setdefault("name", "Default")
            return data
        if entity == "message":
            data.setdefault("id", str(uuid.uuid4()))
            data.setdefault("role", "user")
            data.setdefault("content", "")
            return data
        if entity == "browser_event":
            data.setdefault("id", str(uuid.uuid4()))
            data.setdefault("trust_origin", "untrusted")
            return data
        if entity == "agent_run":
            data.setdefault("id", str(uuid.uuid4()))
            data.setdefault("mode", "passive")
            return data
        if entity == "annotation":
            data.setdefault("sidecar_record_id", str(uuid.uuid4()))
            data.setdefault("source_id", "")
            return data
        return data

    async def merge_sources(self, source_ids: list[str], reason: str, merge_confidence: float = 1.0) -> dict[str, Any]:
        sources = [await self.session.get(Source, sid) for sid in source_ids]
        live_sources = [s for s in sources if s is not None]
        if len(live_sources) < 2:
            raise ValueError("merge requires at least two existing sources")

        survivor = sorted(
            live_sources,
            key=lambda s: (
                s.added_at or s.created_at,
                -sum(bool(getattr(s, field, None)) for field in ("doi", "arxiv_id", "metadata_json", "abstract", "url")),
                s.id,
            ),
        )[0]
        merged = [s for s in live_sources if s.id != survivor.id]
        record = SourceMergeRecord(
            survivor_id=survivor.id,
            merged_ids_json=json.dumps([s.id for s in merged]),
            reason=reason,
        )
        self.session.add(record)
        await self.session.flush()

        self._merge_repoint_journal: list[dict[str, str]] = []
        for duplicate in merged:
            old_id = duplicate.id
            await self._repoint_source_references(old_id, survivor.id)
            duplicate.merged_into_source_id = survivor.id
            duplicate.trashed = True
            self.session.add(
                SourceTombstone(
                    old_id=old_id,
                    survivor_id=survivor.id,
                    merge_record_id=record.id,
                    reason=reason,
                    merge_confidence=merge_confidence,
                )
            )
            self.session.add(duplicate)

        await self.session.flush()
        for duplicate in merged:
            duplicate_id = duplicate.id
            if await self.count_references_to_source(duplicate_id) != 0:
                await self.session.rollback()
                raise RuntimeError(f"dangling references remain for {duplicate_id}")

        record.repoint_log_json = json.dumps(getattr(self, "_merge_repoint_journal", []))
        self.session.add(record)
        await self.session.commit()
        return {"survivor_id": survivor.id, "merged_ids": [s.id for s in merged], "merge_record_id": record.id}

    async def unmerge_sources(self, merge_record_id: str) -> dict[str, Any]:
        """Reverse a merge from its recoverable record (HL-REFINT-02).

        Restores merged source ids, re-splits every unioned reference back to
        its original owner using the repoint journal, and removes the
        tombstones for the reversed record.
        """
        record = await self.session.get(SourceMergeRecord, merge_record_id)
        if record is None:
            raise ValueError("merge record not found")
        if record.reversed:
            raise ValueError("merge already reversed")
        merged_ids = json.loads(record.merged_ids_json or "[]")
        journal = json.loads(record.repoint_log_json or "[]")

        # Restore references from the survivor back to each original merged id.
        for entry in journal:
            key_direct = (entry["table"], entry["column"])
            key_poly = tuple(entry.get("poly_key")) if entry.get("poly_key") else None
            if key_direct in _SOURCE_DIRECT_MODELS:
                model, _column = _SOURCE_DIRECT_MODELS[key_direct]
                row = await self.session.get(model, entry["pk"])
                if row is not None and getattr(row, entry["column"]) == record.survivor_id:
                    setattr(row, entry["column"], entry["old_id"])
                    self.session.add(row)
            elif key_poly in _SOURCE_POLYMORPHIC_MODELS:
                model, _type_column, _id_column = _SOURCE_POLYMORPHIC_MODELS[key_poly]
                row = await self.session.get(model, entry["pk"])
                if row is not None and getattr(row, entry["column"]) == record.survivor_id:
                    setattr(row, entry["column"], entry["old_id"])
                    self.session.add(row)

        for old_id in merged_ids:
            source = await self.session.get(Source, old_id)
            if source is not None:
                source.trashed = False
                source.merged_into_source_id = None
                source.link_state = "live"
                self.session.add(source)
            tombstone = await self.session.get(SourceTombstone, old_id)
            if tombstone is not None:
                await self.session.delete(tombstone)

        record.reversed = True
        self.session.add(record)
        await self.session.commit()
        return {"reversed": True, "restored_ids": merged_ids, "survivor_id": record.survivor_id}

    async def _repoint_source_references(self, old_id: str, survivor_id: str) -> None:
        journal = getattr(self, "_merge_repoint_journal", None)
        for table_name, column_name in SOURCE_DIRECT_REFERENCE_COLUMNS:
            model, column = _SOURCE_DIRECT_MODELS[(table_name, column_name)]
            rows = await self.session.exec(select(model).where(column == old_id))
            for row in rows.all():
                setattr(row, column_name, survivor_id)
                self.session.add(row)
                if journal is not None:
                    journal.append(
                        {
                            "table": table_name,
                            "column": column_name,
                            "pk": self._primary_key(row),
                            "old_id": old_id,
                        }
                    )

        for table_name, type_column_name, type_value, id_column_name in SOURCE_POLYMORPHIC_REFERENCE_COLUMNS:
            model, type_column, id_column = _SOURCE_POLYMORPHIC_MODELS[
                (table_name, type_column_name, type_value, id_column_name)
            ]
            rows = await self.session.exec(select(model).where(and_(type_column == type_value, id_column == old_id)))
            for row in rows.all():
                setattr(row, id_column_name, survivor_id)
                self.session.add(row)
                if journal is not None:
                    journal.append(
                        {
                            "table": table_name,
                            "column": id_column_name,
                            "pk": self._primary_key(row),
                            "old_id": old_id,
                            "poly_key": [table_name, type_column_name, type_value, id_column_name],
                        }
                    )

    @staticmethod
    def _primary_key(row: Any) -> str:
        return str(getattr(row, "id", None) or getattr(row, "sidecar_record_id", None))

    async def count_references_to_source(self, source_id: str) -> int:
        count = 0
        for table_name, column_name in SOURCE_DIRECT_REFERENCE_COLUMNS:
            model, column = _SOURCE_DIRECT_MODELS[(table_name, column_name)]
            rows = await self.session.exec(select(model).where(column == source_id))
            count += len(rows.all())
        for table_name, type_column_name, type_value, id_column_name in SOURCE_POLYMORPHIC_REFERENCE_COLUMNS:
            model, type_column, id_column = _SOURCE_POLYMORPHIC_MODELS[
                (table_name, type_column_name, type_value, id_column_name)
            ]
            rows = await self.session.exec(select(model).where(and_(type_column == type_value, id_column == source_id)))
            count += len(rows.all())
        return count

    async def trash_source(self, source_id: str, confirmed: bool) -> dict[str, Any]:
        source = await self.session.get(Source, source_id)
        if source is None:
            raise ValueError("source not found")

        claims = (await self.session.exec(select(Claim).where(and_(Claim.location_type == "source", Claim.location_id == source_id)))).all()
        annotations = (await self.session.exec(select(Annotation).where(Annotation.source_id == source_id))).all()
        evidence = (await self.session.exec(select(EvidenceLink).where(EvidenceLink.source_id == source_id))).all()
        counts = {"claims": len(claims), "annotations": len(annotations), "evidence": len(evidence)}
        if any(counts.values()) and not confirmed:
            return {"requires_confirmation": True, "dependent_counts": counts}

        source.trashed = True
        source.link_state = "target_trashed"
        self.session.add(source)

        for obj in [*claims, *annotations, *evidence]:
            obj.link_state = "target_trashed"
            self.session.add(obj)
            self.session.add(
                ReviewItem(
                    item_type="broken-link",
                    title="Source moved to Trash",
                    origin_type=obj.__tablename__,
                    origin_id=getattr(obj, "id", getattr(obj, "sidecar_record_id", None)),
                    target_type="source",
                    target_id=source_id,
                    summary=f"{obj.__tablename__} still references a trashed source.",
                )
            )

        await self.session.commit()
        await self.flag_task_links_for_trashed_target("source", source_id)
        return {"trashed": True, "dependent_counts": counts}

    async def trash_note(self, note_id: str) -> dict[str, Any]:
        note = await self.session.get(Note, note_id)
        if note is None:
            raise ValueError("note not found")
        note.soft_deleted = True
        note.link_state = "target_trashed"
        note.updated_at = datetime.now(timezone.utc)
        self.session.add(note)
        await self.session.commit()
        flagged = await self.flag_task_links_for_trashed_target("note", note_id)
        return {"trashed": True, "flagged_task_links": flagged}

    async def restore_note(self, note_id: str) -> dict[str, Any]:
        note = await self.session.get(Note, note_id)
        if note is None:
            raise ValueError("note not found")
        note.soft_deleted = False
        note.link_state = "live"
        note.updated_at = datetime.now(timezone.utc)
        self.session.add(note)
        await self.session.commit()
        reattached = await self.reattach_task_links_for_target("note", note_id)
        return {"restored": True, "reattached_task_links": reattached}

    async def restore_source(self, source_id: str) -> dict[str, Any]:
        source = await self.session.get(Source, source_id)
        if source is None:
            raise ValueError("source not found")
        source.trashed = False
        source.link_state = "live"
        self.session.add(source)

        for query in [
            select(Claim).where(and_(Claim.location_type == "source", Claim.location_id == source_id)),
            select(Annotation).where(Annotation.source_id == source_id),
            select(EvidenceLink).where(EvidenceLink.source_id == source_id),
        ]:
            rows = await self.session.exec(query)
            for row in rows.all():
                row.link_state = "live"
                self.session.add(row)

        await self.session.commit()
        await self.reattach_task_links_for_target("source", source_id)
        return {"restored": True}

    async def list_review_items(self, item_type: Optional[str] = None) -> list[dict[str, Any]]:
        query = select(ReviewItem)
        if item_type:
            query = query.where(ReviewItem.item_type == item_type)
        res = await self.session.exec(query)
        return self._to_dict_list(res.all())

    # --- MCP registry (feature 02-02, Section 25.7) -------------------------
    async def register_mcp_server(
        self,
        *,
        name: str,
        transport: str = "stdio",
        connection: Optional[dict[str, Any]] = None,
        auth_handle_ref: Optional[str] = None,
        connector: Optional[str] = None,
    ) -> dict[str, Any]:
        """Persist an MCP server disabled by default (HL-ASSIST-01).

        ``auth_handle_ref`` MUST be a keychain reference; a raw secret is
        rejected so credentials never land in SQLite.
        """
        if auth_handle_ref and not str(auth_handle_ref).startswith(("keychain:", "env:")):
            raise ValueError("auth_handle_ref must be a keychain:* or env:* reference, never a raw secret")
        server = McpServer(
            name=name,
            transport=transport,
            connection_json=json.dumps(connection or {}, sort_keys=True),
            auth_handle_ref=auth_handle_ref,
            connector=connector,
            enabled=False,
            status="registered",
        )
        self.session.add(server)
        await self.session.commit()
        await self.session.refresh(server)
        return self._to_dict(server)

    async def get_mcp_server(self, server_id: str) -> Optional[dict[str, Any]]:
        return self._to_dict(await self.session.get(McpServer, server_id))

    async def list_mcp_servers(self) -> list[dict[str, Any]]:
        res = await self.session.exec(select(McpServer).order_by(McpServer.created_at.asc()))
        return self._to_dict_list(res.all())

    async def set_mcp_server_enabled(self, server_id: str, enabled: bool) -> Optional[dict[str, Any]]:
        server = await self.session.get(McpServer, server_id)
        if server is None:
            return None
        server.enabled = enabled
        server.updated_at = datetime.now(timezone.utc)
        self.session.add(server)
        await self.session.commit()
        await self.session.refresh(server)
        return self._to_dict(server)

    async def set_mcp_server_status(self, server_id: str, status: str, connection_error: str = "") -> Optional[dict[str, Any]]:
        server = await self.session.get(McpServer, server_id)
        if server is None:
            return None
        server.status = status
        server.connection_error = connection_error
        server.updated_at = datetime.now(timezone.utc)
        self.session.add(server)
        await self.session.commit()
        await self.session.refresh(server)
        return self._to_dict(server)

    async def upsert_mcp_tool(
        self,
        *,
        server_id: str,
        name: str,
        description: str = "",
        input_schema: Optional[dict[str, Any]] = None,
        read_only: bool = False,
    ) -> dict[str, Any]:
        """Persist a discovered tool disabled + deny by default (HL-ASSIST-02).

        Re-discovery updates the schema/description but NEVER silently
        re-enables or re-allows a tool the researcher already configured.
        """
        existing = (
            await self.session.exec(
                select(McpTool).where(and_(McpTool.server_id == server_id, McpTool.name == name))
            )
        ).first()
        if existing is not None:
            existing.description = description
            existing.input_schema_json = json.dumps(input_schema or {}, sort_keys=True)
            existing.read_only = read_only
            existing.updated_at = datetime.now(timezone.utc)
            self.session.add(existing)
            await self.session.commit()
            await self.session.refresh(existing)
            return self._to_dict(existing)
        tool = McpTool(
            server_id=server_id,
            name=name,
            description=description,
            input_schema_json=json.dumps(input_schema or {}, sort_keys=True),
            enabled=False,
            permission="deny",
            read_only=read_only,
        )
        self.session.add(tool)
        await self.session.commit()
        await self.session.refresh(tool)
        return self._to_dict(tool)

    async def get_mcp_tool(self, tool_id: str) -> Optional[dict[str, Any]]:
        return self._to_dict(await self.session.get(McpTool, tool_id))

    async def list_mcp_tools(self, server_id: Optional[str] = None, enabled_only: bool = False) -> list[dict[str, Any]]:
        q = select(McpTool)
        if server_id:
            q = q.where(McpTool.server_id == server_id)
        if enabled_only:
            q = q.where(McpTool.enabled == True)  # noqa: E712
        q = q.order_by(McpTool.name.asc())
        res = await self.session.exec(q)
        return self._to_dict_list(res.all())

    async def set_mcp_tool_permission(
        self, tool_id: str, *, enabled: Optional[bool] = None, permission: Optional[str] = None
    ) -> Optional[dict[str, Any]]:
        tool = await self.session.get(McpTool, tool_id)
        if tool is None:
            return None
        if enabled is not None:
            tool.enabled = enabled
        if permission is not None:
            if permission not in {"allow", "deny"}:
                raise ValueError("permission must be 'allow' or 'deny'")
            tool.permission = permission
        tool.updated_at = datetime.now(timezone.utc)
        self.session.add(tool)
        await self.session.commit()
        await self.session.refresh(tool)
        return self._to_dict(tool)

    async def record_mcp_call_event(
        self,
        *,
        status: str,
        tool_id: Optional[str] = None,
        server_id: Optional[str] = None,
        tool_name: str = "",
        request_summary: str = "",
        output_summary: str = "",
        redaction: str = "none",
        content_exclusions: Optional[list[dict[str, Any]]] = None,
        detail: str = "",
    ) -> dict[str, Any]:
        event = McpToolCallEvent(
            status=status,
            tool_id=tool_id,
            server_id=server_id,
            tool_name=tool_name,
            request_summary=request_summary,
            output_summary=output_summary,
            redaction=redaction,
            content_exclusions_json=json.dumps(content_exclusions or [], sort_keys=True),
            detail=detail,
        )
        self.session.add(event)
        await self.session.commit()
        await self.session.refresh(event)
        return self._to_dict(event)

    async def store_mcp_artifact(self, *, event_id: str, tool_id: Optional[str], content: str) -> dict[str, Any]:
        artifact = McpArtifact(
            event_id=event_id,
            tool_id=tool_id,
            trust_level="untrusted-external",
            content=content,
        )
        self.session.add(artifact)
        await self.session.commit()
        await self.session.refresh(artifact)
        return self._to_dict(artifact)

    async def list_mcp_call_events(self, tool_id: Optional[str] = None) -> list[dict[str, Any]]:
        q = select(McpToolCallEvent)
        if tool_id:
            q = q.where(McpToolCallEvent.tool_id == tool_id)
        q = q.order_by(McpToolCallEvent.created_at.desc())
        res = await self.session.exec(q)
        return self._to_dict_list(res.all())

    async def list_mcp_artifacts(self, event_id: Optional[str] = None) -> list[dict[str, Any]]:
        q = select(McpArtifact)
        if event_id:
            q = q.where(McpArtifact.event_id == event_id)
        q = q.order_by(McpArtifact.created_at.desc())
        res = await self.session.exec(q)
        return self._to_dict_list(res.all())

    # --- Citation import/export (HL-CITE-01, HL-CITE-02) ---------------------
    def _source_from_csl(self, item: dict[str, Any], project_id: Optional[str]) -> dict[str, Any]:
        issued = item.get("issued") or {}
        parts = issued.get("date-parts") if isinstance(issued, dict) else None
        year = str(parts[0][0]) if parts and parts[0] else ""
        authors = []
        for person in item.get("author") or []:
            if isinstance(person, dict):
                authors.append(", ".join(part for part in (person.get("family"), person.get("given")) if part))
            else:
                authors.append(str(person))
        identifiers = {}
        if item.get("DOI"):
            identifiers["doi"] = item["DOI"]
        arxiv_id = None
        raw_ids = item.get("identifiers")
        if isinstance(raw_ids, dict):
            identifiers.update({str(k): str(v) for k, v in raw_ids.items()})
            arxiv_id = raw_ids.get("arxiv")
        stable_id = self._stable_source_id(item)
        return {
            "id": stable_id,
            "project_id": project_id,
            "title": item.get("title") or "Untitled source",
            "authors": "; ".join(a for a in authors if a),
            "year": year,
            "venue": item.get("container-title") or "",
            "publisher": item.get("publisher") or "",
            "url": item.get("URL") or "",
            "abstract": item.get("abstract") or "",
            "doi": item.get("DOI"),
            "arxiv_id": arxiv_id,
            "kind": "paper",
            "source_type": item.get("type") or "article-journal",
            "keywords": [k.strip() for k in str(item.get("keyword") or "").split(",") if k.strip()],
            "identifiers": identifiers,
            "csl_json": json.dumps({**item, "id": stable_id}, sort_keys=True),
            "bibtex": csl_json_to_bibtex([{**item, "id": stable_id}]),
            "ris": csl_json_to_ris([{**item, "id": stable_id}]),
            "trust_origin": "user",
        }

    @staticmethod
    def _stable_source_id(item: dict[str, Any]) -> str:
        for key in ("DOI", "URL"):
            if item.get(key):
                digest = uuid.uuid5(uuid.NAMESPACE_URL, str(item[key]).lower()).hex[:16]
                return f"src_{digest}"
        seed = (str(item.get("title") or "")).lower() + str(item.get("issued") or "")
        return f"src_{uuid.uuid5(uuid.NAMESPACE_URL, seed).hex[:16]}"

    async def import_sources(self, text: str, fmt: str, project_id: Optional[str] = None) -> dict[str, Any]:
        """Import BibTeX/RIS/CSL-JSON into sources. csl_json is canonical.

        Parsing happens before any DB write, so a malformed payload raises
        :class:`CitationParseError` and leaves existing records untouched
        (HL-CITE-01, HL-CITE-13). No Zotero/RDF path is used (HL-CITE-02).
        """
        fmt = fmt.lower()
        if fmt in {"bibtex", "bib"}:
            items = bibtex_to_csl_json(text)
        elif fmt == "ris":
            items = ris_to_csl_json(text)
        elif fmt in {"csl-json", "csl_json", "csljson", "json"}:
            parsed = _safe_json(text, None)
            if parsed is None:
                raise CitationParseError("CSL JSON payload could not be parsed.")
            items = parsed if isinstance(parsed, list) else [parsed]
        else:
            raise CitationParseError(f"Unsupported import format: {fmt}")

        imported: list[dict[str, Any]] = []
        for item in items:
            imported.append(await self.upsert_source(self._source_from_csl(item, project_id)))
        return {"imported": imported, "count": len(imported), "format": fmt}

    async def export_sources(self, fmt: str, source_ids: Optional[list[str]] = None) -> str:
        fmt = fmt.lower()
        sources = await self.list_sources()
        if source_ids is not None:
            wanted = set(source_ids)
            sources = [s for s in sources if s["id"] in wanted]
        items = []
        for source in sources:
            csl = source.get("csl_json")
            if isinstance(csl, dict) and csl:
                items.append(csl)
            else:
                items.append(
                    {
                        "id": source["id"],
                        "type": source.get("source_type") or "article-journal",
                        "title": source.get("title"),
                        "author": [{"family": a.strip()} for a in str(source.get("authors") or "").split(";") if a.strip()],
                    }
                )
        if fmt in {"bibtex", "bib"}:
            return csl_json_to_bibtex(items)
        if fmt == "ris":
            return csl_json_to_ris(items)
        if fmt in {"csl-json", "csl_json", "csljson", "json"}:
            return json.dumps(items, sort_keys=True, indent=2)
        raise CitationParseError(f"Unsupported export format: {fmt}")

    # --- Deterministic key dedupe (HL-CITE-03) ------------------------------
    async def dedupe_by_citation_key(self, project_id: Optional[str] = None) -> list[dict[str, Any]]:
        sources = await self.list_sources()
        live = [s for s in sources if not s.get("trashed") and not s.get("merged_into_source_id")]
        if project_id:
            live = [s for s in live if s.get("project_id") in (None, project_id)]
        groups: dict[str, list[dict[str, Any]]] = {}
        for source in live:
            csl = source.get("csl_json") if isinstance(source.get("csl_json"), dict) else {}
            if not csl:
                csl = {
                    "title": source.get("title"),
                    "issued": {"date-parts": [[int(str(source.get("year")))]]} if str(source.get("year") or "").isdigit() else {},
                    "author": [{"family": a.strip()} for a in str(source.get("authors") or "").split(";") if a.strip()],
                }
            key = compute_citation_key(csl)
            groups.setdefault(key, []).append(source)

        merges: list[dict[str, Any]] = []
        for key, members in groups.items():
            if len(members) < 2:
                continue
            union_sources: list[str] = []
            for member in members:
                union_sources.extend(member.get("metadata_sources") or [])
            result = await self.merge_sources([m["id"] for m in members], reason="exact_identifier")
            survivor = await self.session.get(Source, result["survivor_id"])
            if survivor is not None and union_sources:
                existing = json.loads(survivor.metadata_sources_json or "[]")
                merged_provenance = list(dict.fromkeys([*existing, *union_sources]))
                survivor.metadata_sources_json = json.dumps(merged_provenance, sort_keys=True)
                self.session.add(survivor)
                await self.session.commit()
            merges.append({"citation_key": key, **result})
        return merges

    # --- Confidence-based duplicate detection (HL-CITE-04, HL-CITE-12) -------
    async def detect_duplicates(self, project_id: Optional[str] = None) -> list[dict[str, Any]]:
        sources = await self.list_sources()
        if project_id:
            sources = [s for s in sources if s.get("project_id") in (None, project_id)]
        verdicts = find_duplicates(sources)
        for verdict in verdicts:
            group_id = f"dupgrp_{uuid.uuid5(uuid.NAMESPACE_URL, verdict['left_id'] + verdict['right_id']).hex[:12]}"
            left = await self.session.get(Source, verdict["left_id"])
            right = await self.session.get(Source, verdict["right_id"])
            for source in (left, right):
                if source is None:
                    continue
                source.duplicate_group_id = group_id
                source.duplicate_status = verdict["status"]
                source.merge_confidence = verdict["confidence"]
                self.session.add(source)
            if verdict["status"] == "needs_review":
                existing = (
                    await self.session.exec(
                        select(ReviewItem).where(
                            ReviewItem.item_type == "duplicate-merge-proposal",
                            ReviewItem.origin_id == verdict["left_id"],
                            ReviewItem.target_id == verdict["right_id"],
                        )
                    )
                ).first()
                if existing is None:
                    self.session.add(
                        ReviewItem(
                            project_id=project_id,
                            item_type="duplicate-merge-proposal",
                            title="Confirm possible duplicate sources",
                            summary=f"Two sources look like duplicates ({verdict['confidence']:.0%} similar). Confirm before merge.",
                            origin_type="source",
                            origin_id=verdict["left_id"],
                            target_type="source",
                            target_id=verdict["right_id"],
                            payload_json=json.dumps(verdict, sort_keys=True),
                        )
                    )
        await self.session.commit()
        return verdicts

    # --- Referential-integrity scan (HL-REFINT-04) --------------------------
    async def scan_referential_integrity(self, project_id: Optional[str] = None) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []

        claims = (await self.session.exec(select(Claim))).all()
        for claim in claims:
            if not claim.location_type or not claim.location_id:
                continue
            resolution = await self.resolve_claim_location(claim.location_type, claim.location_id)
            if not resolution["resolved"]:
                findings.append(await self._surface_broken_link("claim", claim.id, claim.location_type, claim.location_id, "unresolved claim.location_id"))

        evidence_rows = (await self.session.exec(select(EvidenceLink))).all()
        for evidence in evidence_rows:
            source = await self.session.get(Source, evidence.source_id)
            if source is None or source.trashed:
                findings.append(await self._surface_broken_link("evidence", evidence.id, "source", evidence.source_id, "evidence points at a missing/trashed source"))
            if evidence.citation_id and await self.session.get(Citation, evidence.citation_id) is None:
                findings.append(await self._surface_broken_link("evidence", evidence.id, "citation", evidence.citation_id, "evidence points at a missing citation"))

        citations = (await self.session.exec(select(Citation))).all()
        for citation in citations:
            if await self.session.get(Source, citation.source_id) is None:
                findings.append(await self._surface_broken_link("citation", citation.id, "source", citation.source_id, "citation points at a missing source"))

        return findings

    async def _surface_broken_link(self, origin_type: str, origin_id: str, target_type: str, target_id: str, summary: str) -> dict[str, Any]:
        existing = (
            await self.session.exec(
                select(ReviewItem).where(
                    ReviewItem.item_type == "broken-link",
                    ReviewItem.origin_type == origin_type,
                    ReviewItem.origin_id == origin_id,
                    ReviewItem.target_id == target_id,
                )
            )
        ).first()
        if existing is None:
            self.session.add(
                ReviewItem(
                    item_type="broken-link",
                    title=f"Broken {origin_type} link",
                    summary=summary,
                    origin_type=origin_type,
                    origin_id=origin_id,
                    target_type=target_type,
                    target_id=target_id,
                    payload_json=json.dumps({"origin_type": origin_type, "origin_id": origin_id, "target_type": target_type, "target_id": target_id}, sort_keys=True),
                )
            )
            await self.session.commit()
        return {"origin_type": origin_type, "origin_id": origin_id, "target_type": target_type, "target_id": target_id, "summary": summary}

    async def evaluate_index_versions(self, current_index_version: int, current_extraction_version: int) -> list[dict[str, str]]:
        entries = await self.session.exec(select(LexicalIndexEntry))
        mismatches: list[dict[str, str]] = []
        for entry in entries.all():
            reason = None
            if entry.index_version < current_index_version:
                reason = "index_version"
            elif entry.extraction_version < current_extraction_version:
                reason = "extraction_version"
            if reason:
                mismatches.append({"source_id": entry.source_id, "reason": reason})
        return mismatches
