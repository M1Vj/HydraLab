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
    Task,
    Setting,
    ProviderSettings,
    ActivityEvent,
    NoteLink,
    AgentRun,
    Annotation,
    BrowserEvent,
    Chat,
    KgEdge,
    LexicalIndexEntry,
    ReviewItem,
    SourceMergeRecord,
    SourceTombstone,
    TaskLink,
)
from hydra.browser_bridge import TRUST_LEVEL_UNTRUSTED


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
            if model.__tablename__ in {"browser_events", "sources"} and d.get("detected_metadata"):
                d["detected_metadata"] = json.loads(d["detected_metadata"] or "{}")
            if model.__tablename__ == "sources" and d.get("metadata_json"):
                d["metadata_json"] = json.loads(d["metadata_json"] or "{}")
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
        workspace_id = source_data.get("workspace_id")
        project_id = source_data.get("project_id")
        trust_origin = source_data.get("trust_origin")
        doi = source_data.get("doi")
        arxiv_id = source_data.get("arxiv_id")

        if source:
            source.title = title
            source.authors = authors
            source.year = year
            source.url = url
            source.abstract = abstract
            source.kind = kind
            if metadata_json is not None:
                source.metadata_json = metadata_json
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
                metadata_json=metadata_json,
                trust_origin=trust_origin or "user",
                doi=doi,
                arxiv_id=arxiv_id,
            )
            self.session.add(source)
            
        await self.session.commit()
        await self.session.refresh(source)
        return self._to_dict(source)

    async def list_sources(self) -> list[dict[str, Any]]:
        res = await self.session.exec(select(Source).order_by(Source.created_at.desc()))
        return self._to_dict_list(res.all())

    # Citation CRUD
    async def add_citation(self, source_id: str, text: str) -> dict[str, Any]:
        cit = Citation(source_id=source_id, text=text)
        self.session.add(cit)
        await self.session.commit()
        await self.session.refresh(cit)
        return self._to_dict(cit)

    async def list_citations(self) -> list[dict[str, Any]]:
        res = await self.session.exec(select(Citation).order_by(Citation.created_at.desc()))
        return self._to_dict_list(res.all())

    # Claim CRUD
    async def add_claim(self, text: str, workspace_id: Optional[str] = None) -> dict[str, Any]:
        claim = Claim(text=text, workspace_id=workspace_id)
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
    ) -> dict[str, Any]:
        ev = EvidenceLink(
            claim_id=claim_id,
            source_id=source_id,
            passage=passage,
            support=support,
            confidence=confidence,
            review_status=review_status,
            citation_id=citation_id,
        )
        self.session.add(ev)
        await self.session.commit()
        await self.session.refresh(ev)
        return self._to_dict(ev)

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
    ) -> dict[str, Any]:
        task = Task(
            title=title,
            column_name=column,
            detail=detail,
            progress=progress,
            phase_indicator=phase_indicator,
            position=position,
            workspace_id=workspace_id,
        )
        self.session.add(task)
        await self.session.commit()
        await self.session.refresh(task)
        return self._to_dict(task)

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

    async def list_tasks(self, workspace_id: Optional[str] = None) -> list[dict[str, Any]]:
        q = select(Task)
        if workspace_id:
            q = q.where(Task.workspace_id == workspace_id)
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
            existing.updated_at = datetime.now(timezone.utc)
            ps = existing
        else:
            ps = ProviderSettings(provider=provider, model=model, api_key_ref=api_key_ref)
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
            if await self.count_references_to_source(duplicate.id) != 0:
                await self.session.rollback()
                raise RuntimeError(f"dangling references remain for {duplicate.id}")

        await self.session.commit()
        return {"survivor_id": survivor.id, "merged_ids": [s.id for s in merged], "merge_record_id": record.id}

    async def _repoint_source_references(self, old_id: str, survivor_id: str) -> None:
        evidence = await self.session.exec(select(EvidenceLink).where(EvidenceLink.source_id == old_id))
        for row in evidence.all():
            row.source_id = survivor_id
            self.session.add(row)

        claims = await self.session.exec(select(Claim).where(and_(Claim.location_type == "source", Claim.location_id == old_id)))
        for row in claims.all():
            row.location_id = survivor_id
            self.session.add(row)

        task_links = await self.session.exec(select(TaskLink).where(and_(TaskLink.target_type == "source", TaskLink.target_id_or_path == old_id)))
        for row in task_links.all():
            row.target_id_or_path = survivor_id
            self.session.add(row)

        annotations = await self.session.exec(select(Annotation).where(Annotation.source_id == old_id))
        for row in annotations.all():
            row.source_id = survivor_id
            self.session.add(row)

        citations = await self.session.exec(select(Citation).where(Citation.source_id == old_id))
        for row in citations.all():
            row.source_id = survivor_id
            self.session.add(row)

    async def count_references_to_source(self, source_id: str) -> int:
        count = 0
        queries = [
            select(EvidenceLink).where(EvidenceLink.source_id == source_id),
            select(Claim).where(and_(Claim.location_type == "source", Claim.location_id == source_id)),
            select(TaskLink).where(and_(TaskLink.target_type == "source", TaskLink.target_id_or_path == source_id)),
            select(Annotation).where(Annotation.source_id == source_id),
            select(Citation).where(Citation.source_id == source_id),
        ]
        for query in queries:
            rows = await self.session.exec(query)
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
        return {"trashed": True, "dependent_counts": counts}

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
        return {"restored": True}

    async def list_review_items(self, item_type: Optional[str] = None) -> list[dict[str, Any]]:
        query = select(ReviewItem)
        if item_type:
            query = query.where(ReviewItem.item_type == item_type)
        res = await self.session.exec(query)
        return self._to_dict_list(res.all())

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
