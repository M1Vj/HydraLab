from __future__ import annotations

import io
import json
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, StreamingResponse

from hydra.research import citation_for, compose_research_answer, search_academic_sources
from hydra.schemas import (
    EvidenceCreateRequest,
    CitationCreateRequest,
    ClaimCreateRequest,
    ClaimDetectRequest,
    NoteCreateRequest,
    NoteUpdateRequest,
    ProviderSettingsRequest,
    SettingsUpdateRequest,
    ResearchRequest,
    SourceSearchRequest,
    TaskCreateRequest,
    TaskUpdateRequest,
    WritingReviewRequest,
    ChatCompletionRequest,
    ConversationResponse,
    ChatMessageResponse,
)
from hydra.storage import Store
from hydra.writing import review_text


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.store = Store()
        yield
        app.state.store.close()

    app = FastAPI(title="Hydra Phase 1 Research API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "phase": "1"}

    @app.get("/api/chat/conversations")
    def list_conversations(http_request: Request) -> dict[str, object]:
        return {"conversations": _store(http_request).list_conversations()}

    @app.get("/api/chat/conversations/{conversation_id}/messages")
    def list_messages(conversation_id: str, http_request: Request) -> dict[str, object]:
        return {"messages": _store(http_request).list_messages(conversation_id)}

    @app.post("/api/chat/completions")
    async def chat_completions(request: ChatCompletionRequest, http_request: Request) -> StreamingResponse:
        store = _store(http_request)
        conv_id = request.conversation_id
        if not conv_id:
            conv = store.create_conversation(request.message[:40] or "New Chat")
            conv_id = conv["id"]
        
        store.add_message(conv_id, "user", request.message)
        
        async def stream() -> AsyncIterator[str]:
            yield f"data: {json.dumps({'type': 'status', 'content': 'reading request...'})}\n\n"
            
            # Simulated dummy response for this branch since no real LLM call is required yet 
            # (as per branch directions, we model status as events and stream them)
            # We'll just stream a simulated status, then stream a response.
            store.add_event("chat.status", "Thinking about the user query...")
            yield f"data: {json.dumps({'type': 'status', 'content': 'searching memory...'})}\n\n"
            
            answer = f"I received your message: '{request.message}'. This is a mock response."
            
            store.add_message(conv_id, "assistant", answer)
            
            # Stream the answer in chunks
            for word in answer.split(" "):
                yield f"data: {json.dumps({'type': 'message', 'content': word + ' '})}\n\n"
            
            yield f"data: {json.dumps({'type': 'done', 'conversation_id': conv_id})}\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.post("/api/chat/research")
    async def research_chat(request: ResearchRequest, http_request: Request) -> dict[str, object]:
        store = _store(http_request)
        store.add_event("research.started", f"Searching literature for {request.query}")
        sources = [store.upsert_source(source) for source in await search_academic_sources(request.query)]
        answer = compose_research_answer(request.query, sources)
        citations = [store.add_citation(**citation_for(request.query, sources[0]))]
        store.add_event("research.completed", f"Completed cited answer for {request.query}")
        return {"answer": answer, "citations": citations, "sources": sources, "status": "completed"}

    @app.post("/api/sources/search")
    async def source_search(request: SourceSearchRequest, http_request: Request) -> dict[str, object]:
        store = _store(http_request)
        sources = [store.upsert_source(source) for source in await search_academic_sources(request.query)]
        store.add_event("sources.search.completed", f"Found {len(sources)} source candidates")
        return {"sources": sources}

    from fastapi import Form

    @app.post("/api/sources/ingest")
    async def ingest_source(
        http_request: Request,
        file: UploadFile | None = File(None),
        url: str | None = Form(None),
        doi: str | None = Form(None),
        title: str | None = Form(None),
    ) -> dict[str, object]:
        store = _store(http_request)
        if file:
            raw = await file.read()
            text = extract_upload_text(raw, file.content_type or "", file.filename or "paper")
            final_title = title or file.filename or "Uploaded paper"
            kind = "pdf"
            url_ref = url or doi or ""
        elif url or doi:
            final_title = title or f"Ingested {url or doi}"
            url_ref = url or doi or ""
            text = f"This is mocked extracted text from {url_ref}."
            kind = "url"
        else:
            raise HTTPException(status_code=400, detail="Must provide file, url, or doi")
        
        summary = f"Mocked summary for {final_title}. Text length: {len(text)} characters."
        
        source = store.upsert_source(
            {
                "title": final_title,
                "authors": "Local ingestion",
                "abstract": summary,
                "url": url_ref,
                "kind": kind,
            }
        )
        note = store.add_note(f"Notes & Summary for {source['title']}", f"Summary: {summary}\n\nFull text: {text[:3800]}", source["id"])
        store.add_event("source.ingested", f"Ingested {source['title']}")
        return {"source": source, "note": note}

    @app.get("/api/sources/retrieve")
    async def retrieve_rag(query: str, source_id: str | None = None, http_request: Request = None) -> dict[str, object]:
        store = _store(http_request)
        store.add_event("rag.retrieval", f"Retrieving answers for query '{query}'")
        
        # Mock simple RAG chunking and summarization
        chunks = [f"Mocked relevant passage for '{query}'"]
        if source_id:
            chunks.append(f"Passage specifically from source_id={source_id}")
            
        answer = f"Based on the ingested sources, here is a synthesized answer for '{query}'. This is a mock RAG generation."
        
        return {
            "query": query,
            "answer": answer,
            "chunks": chunks,
            "source_id": source_id
        }

    @app.post("/api/writing/review")
    def writing_review(request: WritingReviewRequest, http_request: Request) -> dict[str, object]:
        result = review_text(request.text)
        _store(http_request).add_event("writing.review.completed", "Reviewed draft text")
        return result

    @app.post("/api/evidence")
    def create_evidence(request: EvidenceCreateRequest, http_request: Request) -> dict[str, object]:
        evidence = _store(http_request).add_evidence(**request.model_dump())
        _store(http_request).add_event("evidence.linked", f"Linked evidence for claim: {request.claim_id}")
        return evidence

    @app.get("/api/evidence")
    def list_evidence(http_request: Request) -> dict[str, object]:
        return {"evidence": _store(http_request).list_evidence()}

    @app.post("/api/claims")
    def create_claim(request: ClaimCreateRequest, http_request: Request) -> dict[str, object]:
        claim = _store(http_request).add_claim(**request.model_dump())
        _store(http_request).add_event("claim.created", "Created new claim")
        return claim

    @app.get("/api/claims")
    def list_claims(http_request: Request) -> dict[str, object]:
        return {"claims": _store(http_request).list_claims()}

    @app.post("/api/claims/detect")
    def detect_claims(request: ClaimDetectRequest, http_request: Request) -> dict[str, object]:
        # Mock endpoint
        store = _store(http_request)
        claim1 = store.add_claim("Hydra reduces hallucinated citations.")
        claim2 = store.add_claim("LLMs always tell the truth.")
        
        # Link some evidence mock
        sources = store.list_sources()
        source_id = sources[0]["id"] if sources else store.upsert_source({"title": "Mock Source"})["id"]
        
        store.add_evidence(
            claim_id=claim1["id"],
            source_id=source_id,
            passage="Hydra architecture aims to reduce hallucinations.",
            support="supported",
            confidence=0.9
        )
        store.add_evidence(
            claim_id=claim2["id"],
            source_id=source_id,
            passage="Some LLMs have hallucination problems.",
            support="unsupported",
            confidence=0.2
        )
        
        store.add_event("claims.detected", "Detected mock claims from draft text")
        
        return {
            "claims": [claim1, claim2],
            "evidence": store.list_evidence()
        }

    @app.post("/api/citations")
    def create_citation(request: CitationCreateRequest, http_request: Request) -> dict[str, object]:
        citation = _store(http_request).add_citation(**request.model_dump())
        _store(http_request).add_event("citation.created", "Created new citation")
        return citation

    @app.get("/api/citations")
    def list_citations(http_request: Request) -> dict[str, object]:
        return {"citations": _store(http_request).list_citations()}

    @app.post("/api/notes")
    def create_note(request: NoteCreateRequest, http_request: Request) -> dict[str, object]:
        note = _store(http_request).add_note(request.title, request.body, request.source_id)
        _store(http_request).add_event("note.created", f"Created note {request.title}")
        return note

    @app.get("/api/notes")
    def list_notes(http_request: Request, query: str | None = None) -> dict[str, object]:
        return {"notes": _store(http_request).search_notes(query)}

    @app.get("/api/notes/graph")
    def get_notes_graph(http_request: Request) -> dict[str, object]:
        return _store(http_request).get_graph()

    @app.get("/api/notes/{note_id}")
    def get_note(note_id: str, http_request: Request) -> dict[str, object]:
        note = _store(http_request).get_note(note_id)
        if not note:
            raise HTTPException(status_code=404, detail="Note not found")
        return note

    @app.put("/api/notes/{note_id}")
    def update_note(note_id: str, request: NoteUpdateRequest, http_request: Request) -> dict[str, object]:
        note = _store(http_request).update_note(note_id, request.title, request.body, request.source_id)
        if not note:
            raise HTTPException(status_code=404, detail="Note not found")
        _store(http_request).add_event("note.updated", f"Updated note {request.title}")
        return note

    @app.delete("/api/notes/{note_id}")
    def delete_note(note_id: str, http_request: Request) -> dict[str, object]:
        success = _store(http_request).delete_note(note_id)
        if not success:
            raise HTTPException(status_code=404, detail="Note not found")
        _store(http_request).add_event("note.deleted", f"Deleted note {note_id}")
        return {"status": "success"}

    @app.get("/api/notes/{note_id}/links")
    def get_note_links(note_id: str, http_request: Request) -> dict[str, object]:
        return _store(http_request).get_note_links(note_id)


    @app.post("/api/tasks")
    def create_task(request: TaskCreateRequest, http_request: Request) -> dict[str, object]:
        task = _store(http_request).add_task(
            title=request.title,
            column=request.column,
            detail=request.detail,
            progress=request.progress,
            phase_indicator=request.phase_indicator,
            position=request.position
        )
        _store(http_request).add_event("task.created", f"Created task {request.title}")
        return task

    @app.get("/api/tasks")
    def list_tasks(http_request: Request) -> dict[str, object]:
        return {"tasks": _store(http_request).list_tasks()}

    @app.put("/api/tasks/{task_id}")
    def update_task_put(task_id: str, request: TaskUpdateRequest, http_request: Request) -> dict[str, object]:
        task = _store(http_request).update_task(task_id, request.model_dump(exclude_unset=True))
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        _store(http_request).add_event("task.updated", f"Updated task {task['title']}")
        return task

    @app.patch("/api/tasks/{task_id}")
    def update_task_patch(task_id: str, request: TaskUpdateRequest, http_request: Request) -> dict[str, object]:
        task = _store(http_request).update_task(task_id, request.model_dump(exclude_unset=True))
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        _store(http_request).add_event("task.updated", f"Updated task {task['title']}")
        return task

    @app.delete("/api/tasks/{task_id}")
    def delete_task(task_id: str, http_request: Request) -> dict[str, object]:
        success = _store(http_request).delete_task(task_id)
        if not success:
            raise HTTPException(status_code=404, detail="Task not found")
        _store(http_request).add_event("task.deleted", f"Deleted task {task_id}")
        return {"status": "success"}

    @app.get("/api/events")
    def events(http_request: Request) -> object:
        store = _store(http_request)
        if "text/event-stream" in http_request.headers.get("accept", ""):
            async def stream() -> AsyncIterator[str]:
                for event in reversed(store.list_events()):
                    yield f"event: {event['kind']}\ndata: {json.dumps(event)}\n\n"
            return StreamingResponse(stream(), media_type="text/event-stream")
        return {"events": store.list_events()}

    @app.get("/api/export/bibliography")
    def bibliography(http_request: Request, style: str = "apa") -> PlainTextResponse:
        sources = _store(http_request).list_sources()
        text = format_bibliography(sources, style)
        return PlainTextResponse(text)

    @app.put("/api/settings/provider")
    def save_provider_settings(request: ProviderSettingsRequest, http_request: Request) -> dict[str, object]:
        settings = _store(http_request).save_provider_settings(
            request.provider,
            request.model,
            request.api_key_ref,
        )
        _store(http_request).add_event("settings.provider.saved", f"Saved settings for {request.provider}")
        return settings

    @app.get("/api/settings")
    def get_settings(http_request: Request) -> dict[str, object]:
        store = _store(http_request)
        return {
            "provider_settings": store.list_provider_settings(),
            "workspace_preferences": store.list_settings(),
        }

    @app.post("/api/settings")
    def post_settings(request: SettingsUpdateRequest, http_request: Request) -> dict[str, object]:
        store = _store(http_request)
        if request.provider_settings is not None:
            for p in request.provider_settings:
                store.save_provider_settings(p.provider, p.model, p.api_key_ref)
        if request.workspace_preferences is not None:
            for k, v in request.workspace_preferences.items():
                store.save_setting(k, v)
        store.add_event("settings.updated", "Saved settings and workspace preferences")
        return {
            "provider_settings": store.list_provider_settings(),
            "workspace_preferences": store.list_settings(),
        }

    @app.get("/api/export/preview")
    def export_preview(http_request: Request) -> dict[str, object]:
        store = _store(http_request)
        notes = store.search_notes()
        citations = store.list_citations()
        tasks = store.list_tasks()
        sources = store.list_sources()
        
        # Build file list
        files = []
        for n in notes:
            safe_title = "".join(c for c in n["title"] if c.isalnum() or c in (" ", "_", "-")).rstrip() or f"note_{n['id']}"
            files.append(f"notes/{safe_title}.md")
        files.append("citations.md")
        files.append("tasks.md")
        files.append("metadata.json")
        
        return {
            "files": files,
            "counts": {
                "notes": len(notes),
                "citations": len(citations),
                "tasks": len(tasks),
                "sources": len(sources)
            },
            "notes_preview": [{"id": n["id"], "title": n["title"]} for n in notes[:5]],
            "tasks_preview": [{"id": t["id"], "title": t["title"]} for t in tasks[:5]]
        }

    @app.post("/api/export")
    def export_workspace_zip(http_request: Request) -> StreamingResponse:
        import zipfile
        import io
        import json
        
        store = _store(http_request)
        buffer = io.BytesIO()
        
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            # Notes
            notes = store.search_notes()
            for note in notes:
                safe_title = "".join(c for c in note["title"] if c.isalnum() or c in (" ", "_", "-")).rstrip()
                if not safe_title:
                    safe_title = f"note_{note['id']}"
                filename = f"notes/{safe_title}.md"
                content = f"# {note['title']}\n\n{note['body']}"
                zip_file.writestr(filename, content)

            # Citations
            citations = store.list_citations()
            sources = store.list_sources()
            sources_map = {s["id"]: s for s in sources}
            citations_md = ["# Citations\n"]
            for cit in citations:
                src = sources_map.get(cit["source_id"])
                src_title = src["title"] if src else "Unknown Source"
                citations_md.append(f"### Source: {src_title}\n> {cit['text']}\n")
            zip_file.writestr("citations.md", "\n".join(citations_md))

            # Tasks
            tasks = store.list_tasks()
            tasks_md = ["# Kanban Tasks\n", "| Column | Position | Progress | Title | Detail | Phase |", "| --- | --- | --- | --- | --- | --- |"]
            for t in tasks:
                col = t.get("column") or "to_do"
                pos = t.get("position") or 0
                prog = t.get("progress") or 0
                title = t.get("title") or ""
                detail = t.get("detail") or ""
                phase = t.get("phase_indicator") or ""
                tasks_md.append(f"| {col} | {pos} | {prog}% | {title} | {detail} | {phase} |")
            zip_file.writestr("tasks.md", "\n".join(tasks_md))

            # Raw scrubbed JSON
            raw_data = {
                "sources": sources,
                "notes": notes,
                "tasks": tasks,
                "citations": citations,
                "evidence": store.list_evidence(),
                "events": store.list_events(),
                "settings": store.list_settings(),
                "provider_settings": store.list_provider_settings(),
            }
            zip_file.writestr("metadata.json", json.dumps(raw_data, indent=2))
            
        buffer.seek(0)
        store.add_event("workspace.exported", "Exported workspace as ZIP archive")
        return StreamingResponse(
            buffer,
            media_type="application/zip",
            headers={"Content-Disposition": "attachment; filename=hydra_export.zip"}
        )

    @app.get("/api/export/workspace")
    def export_workspace(http_request: Request) -> dict[str, object]:
        return _store(http_request).export_workspace()

    @app.post("/api/reviews/analyze")
    def analyze_review(request: WritingReviewRequest) -> dict[str, object]:
        from hydra.writing import review_text
        return review_text(request.text)

    return app


def _store(request: Request) -> Store:
    if not hasattr(request.app.state, "store"):
        request.app.state.store = Store()
    return request.app.state.store


def extract_upload_text(raw: bytes, content_type: str, filename: str) -> str:
    if content_type == "application/pdf" or filename.lower().endswith(".pdf"):
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(raw))
            return "\n".join(page.extract_text() or "" for page in reader.pages).strip()
        except Exception:
            return ""
    return raw.decode("utf-8", errors="ignore").strip()


def format_bibliography(sources: list[dict[str, object]], style: str) -> str:
    if style.lower() == "bibtex":
        entries = []
        for source in sources:
            key = str(source["id"]).replace("_", "")
            entries.append(
                "@article{"
                f"{key},\n"
                f"  title = {{{source['title']}}},\n"
                f"  author = {{{source.get('authors') or 'Unknown'}}},\n"
                f"  year = {{{source.get('year') or 'n.d.'}}},\n"
                f"  url = {{{source.get('url') or ''}}}\n"
                "}"
            )
        return "\n\n".join(entries)
    lines = []
    for source in sources:
        authors = source.get("authors") or "Unknown author"
        year = source.get("year") or "n.d."
        lines.append(f"{authors} ({year}). {source['title']}. {source.get('url') or 'Local Hydra source'}.")
    return "\n".join(lines)


app = create_app()
