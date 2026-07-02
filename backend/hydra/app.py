from __future__ import annotations

import io
import json
import secrets
import hashlib
from pathlib import Path
from contextlib import asynccontextmanager
from typing import AsyncIterator, Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.browser_bridge import (
    TRUST_LEVEL_UNTRUSTED,
    build_browser_working_set,
    detect_source_metadata,
    should_capture,
    source_id_from_metadata,
    source_should_promote,
)
from hydra.research import citation_for, compose_research_answer, search_academic_sources
from hydra.schemas import (
    BrowserCaptureRequest,
    BrowserHandshakeRequest,
    BrowserHistoryRequest,
    EvidenceCreateRequest,
    CitationCreateRequest,
    ClaimCreateRequest,
    ClaimDetectRequest,
    NoteCreateRequest,
    NoteUpdateRequest,
    ProviderSettingsRequest,
    SettingsUpdateRequest,
    SourceDiscoveryRequest,
    SourceSaveRequest,
    ResearchRequest,
    SourceSearchRequest,
    TaskCreateRequest,
    TaskUpdateRequest,
    WritingReviewRequest,
    ChatCompletionRequest,
)
from hydra.database.session import get_session, init_db, async_session_maker
from hydra.database.repository import Repository
from hydra.services.discovery import (
    DiscoveryCache,
    DiscoveryCoordinator,
    SourceProviderConfig,
    author_string,
    evaluate_pdf_download_policy,
    result_from_dict,
)
from hydra.services.discovery.providers import default_providers
from hydra.services.ingestion import IngestionService
from hydra.settings.toml_config import load_settings, save_settings
from hydra.storage.app_data import app_data_root
from hydra.storage.runtime import choose_bind_host
from hydra.writing import review_text

HYDRALAB_BIND_HOST = choose_bind_host()
HYDRALAB_EXTENSION_ORIGIN = "chrome-extension://hydralab-dev-extension"
HYDRALAB_FRONTEND_ORIGINS = {
    origin
    for port in range(5173, 5180)
    for origin in (f"http://localhost:{port}", f"http://127.0.0.1:{port}")
}
HYDRALAB_BRIDGE_ORIGINS = {HYDRALAB_EXTENSION_ORIGIN, *HYDRALAB_FRONTEND_ORIGINS}
EXTENSION_BRIDGE_PATHS = {
    "/api/browser/handshake",
    "/api/browser/capture",
    "/api/browser/selection",
    "/api/browser/propose-source",
}


def create_app() -> FastAPI:
    bridge_tokens: set[str] = set()
    discovery_cache = DiscoveryCache()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await init_db()
        yield

    app = FastAPI(title="Hydra Phase 1 Research API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
            HYDRALAB_EXTENSION_ORIGIN,
        ],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def browser_bridge_boundary(request: Request, call_next):
        origin = request.headers.get("origin")
        path = request.url.path
        if origin and origin.startswith("chrome-extension://") and path not in EXTENSION_BRIDGE_PATHS:
            return JSONResponse({"detail": "Extension capability not allowed for this endpoint"}, status_code=403)
        if path.startswith("/api/browser") and request.method != "OPTIONS":
            if origin not in HYDRALAB_BRIDGE_ORIGINS:
                return JSONResponse({"detail": "Forbidden browser bridge origin"}, status_code=403)
        return await call_next(request)

    def require_bridge_auth(request: Request) -> dict[str, str]:
        origin = request.headers.get("origin")
        if origin not in HYDRALAB_BRIDGE_ORIGINS:
            raise HTTPException(status_code=403, detail="Forbidden browser bridge origin")
        authorization = request.headers.get("authorization", "")
        prefix = "Bearer "
        if not authorization.startswith(prefix):
            raise HTTPException(status_code=401, detail="Missing browser bridge token")
        token = authorization[len(prefix):]
        if token not in bridge_tokens:
            raise HTTPException(status_code=401, detail="Invalid browser bridge token")
        return {"origin": origin, "token": token}

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "phase": "1"}

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "host": HYDRALAB_BIND_HOST}

    @app.get("/readyz")
    def readyz() -> dict[str, object]:
        return {
            "status": "ready",
            "subsystems": {
                "sqlite": "ready",
                "migrations": "ready",
                "bind_host": HYDRALAB_BIND_HOST,
            },
        }

    @app.post("/api/browser/handshake")
    def browser_handshake(request: BrowserHandshakeRequest, raw_request: Request) -> dict[str, object]:
        origin = raw_request.headers.get("origin")
        if origin not in HYDRALAB_BRIDGE_ORIGINS:
            raise HTTPException(status_code=403, detail="Forbidden browser bridge origin")
        token = secrets.token_urlsafe(32)
        bridge_tokens.add(token)
        return {
            "status": "connected",
            "token": token,
            "origin": origin,
            "expires_in_seconds": 3600,
            "transport": "loopback-http",
        }

    @app.post("/api/browser/capture")
    async def browser_capture(
        request: BrowserCaptureRequest,
        _auth: dict[str, str] = Depends(require_bridge_auth),
        session: AsyncSession = Depends(get_session),
    ) -> dict[str, object]:
        return await persist_browser_capture(request, session, create_source=True)

    @app.post("/api/browser/selection")
    async def browser_selection(
        request: BrowserCaptureRequest,
        _auth: dict[str, str] = Depends(require_bridge_auth),
        session: AsyncSession = Depends(get_session),
    ) -> dict[str, object]:
        request.event_type = "selection"
        return await persist_browser_capture(request, session, create_source=False)

    @app.get("/api/browser/ledger")
    async def browser_ledger(
        project_id: str,
        _auth: dict[str, str] = Depends(require_bridge_auth),
        session: AsyncSession = Depends(get_session),
    ) -> dict[str, object]:
        repo = Repository(session)
        return {"events": await repo.list_browser_events(project_id)}

    @app.get("/api/browser/working-set")
    async def browser_working_set(
        project_id: str,
        budget_tokens: int = 8000,
        _auth: dict[str, str] = Depends(require_bridge_auth),
        session: AsyncSession = Depends(get_session),
    ) -> dict[str, object]:
        repo = Repository(session)
        events = await repo.list_browser_events(project_id)
        return build_browser_working_set(events, project_id=project_id, budget_tokens=budget_tokens)

    @app.post("/api/browser/propose-source")
    async def browser_propose_source(
        request: BrowserCaptureRequest,
        _auth: dict[str, str] = Depends(require_bridge_auth),
        session: AsyncSession = Depends(get_session),
    ) -> dict[str, object]:
        repo = Repository(session)
        metadata = detect_source_metadata(request.url, request.title, request.page_text)
        metadata.update(request.metadata)
        metadata["trust_level"] = TRUST_LEVEL_UNTRUSTED
        review_item = await repo.create_review_item(
            {
                "project_id": request.project_id,
                "item_type": "browser-source-proposal",
                "title": f"Review browser source: {request.title or request.url}",
                "summary": "Browser page content proposed a source save. User review is required.",
                "origin_type": "browser",
                "origin_id": request.url,
                "target_type": "source",
                "payload": {
                    "url": request.url,
                    "title": request.title,
                    "trust_level": TRUST_LEVEL_UNTRUSTED,
                    "detected_metadata": metadata,
                    "motivating_excerpt": motivating_excerpt(request.page_text),
                },
            }
        )
        return {"created_source": None, "review_item": review_item}

    @app.post("/api/browser/history/request")
    def browser_history_request(
        request: BrowserHistoryRequest,
        _auth: dict[str, str] = Depends(require_bridge_auth),
    ) -> dict[str, object]:
        return {
            "project_id": request.project_id,
            "scope": "single-request",
            "reason": request.reason,
            "choices": ["Allow for this request", "Decline"],
        }

    @app.get("/api/chat/conversations")
    async def list_conversations(session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        return {"conversations": await repo.list_conversations()}

    @app.get("/api/chat/conversations/{conversation_id}/messages")
    async def list_messages(conversation_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        return {"messages": await repo.list_messages(conversation_id)}

    @app.post("/api/chat/completions")
    async def chat_completions(request: ChatCompletionRequest, session: AsyncSession = Depends(get_session)) -> StreamingResponse:
        repo = Repository(session)
        conv_id = request.conversation_id
        if not conv_id:
            conv = await repo.create_conversation(request.message[:40] or "New Chat")
            conv_id = conv["id"]
        
        await repo.add_message(conv_id, "user", request.message)
        
        async def stream() -> AsyncIterator[str]:
            yield f"data: {json.dumps({'type': 'status', 'content': 'reading request...'})}\n\n"
            
            # Use isolated background session to avoid closed event loop or session access
            async with async_session_maker() as background_session:
                bg_repo = Repository(background_session)
                await bg_repo.add_event("chat.status", "Thinking about the user query...")
            
            yield f"data: {json.dumps({'type': 'status', 'content': 'searching memory...'})}\n\n"
            
            answer = f"I received your message: '{request.message}'. This is a mock response."
            
            async with async_session_maker() as background_session:
                bg_repo = Repository(background_session)
                await bg_repo.add_message(conv_id, "assistant", answer)
            
            # Stream the answer in chunks
            for word in answer.split(" "):
                yield f"data: {json.dumps({'type': 'message', 'content': word + ' '})}\n\n"
            
            yield f"data: {json.dumps({'type': 'done', 'conversation_id': conv_id})}\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.post("/api/chat/research")
    async def research_chat(request: ResearchRequest, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        await repo.add_event("research.started", f"Searching literature for {request.query}")
        sources = [await repo.upsert_source(source) for source in await search_academic_sources(request.query)]
        answer = compose_research_answer(request.query, sources)
        citations = [await repo.add_citation(**citation_for(request.query, sources[0]))]
        await repo.add_event("research.completed", f"Completed cited answer for {request.query}")
        return {"answer": answer, "citations": citations, "sources": sources, "status": "completed"}

    @app.post("/api/sources/search")
    async def source_search(request: SourceSearchRequest, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        sources = [await repo.upsert_source(source) for source in await search_academic_sources(request.query)]
        await repo.add_event("sources.search.completed", f"Found {len(sources)} source candidates")
        return {"sources": sources}

    @app.post("/api/sources/discovery/search")
    async def source_discovery_search(request: SourceDiscoveryRequest, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        coordinator = DiscoveryCoordinator(
            providers=default_providers(),
            cache=discovery_cache,
            config=SourceProviderConfig(contact_email=request.contact_email),
        )
        payload = await coordinator.search(
            request.query,
            offline_only=request.offline_only,
            scholarly_apis_enabled=request.scholarly_apis_enabled,
            existing_sources=await repo.list_sources(),
        )
        for item in payload["review_items"]:
            await repo.create_review_item(item)
        await repo.add_event("sources.discovery.completed", f"Discovery search for {request.query}: {payload['state']}")
        return payload

    @app.post("/api/sources/save")
    async def save_discovered_source(request: SourceSaveRequest, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        result = result_from_dict(request.result).with_query(request.query)
        metadata = result.to_dict()
        metadata["source_origin"] = request.source_origin
        metadata["trust_level"] = TRUST_LEVEL_UNTRUSTED
        metadata["metadata_provenance"] = metadata["metadata_sources"]
        if request.browser_context_event_id:
            metadata["browser_context_event_id"] = request.browser_context_event_id
        pdf_policy = evaluate_pdf_download_policy(
            pdf_url=result.pdf_url,
            expected_size_bytes=result.expected_size_bytes,
            automatic_download=request.automatic_pdf_download,
            explicit_save_with_pdf=request.save_pdf,
            allowed_domains=request.allowed_pdf_domains,
        )
        metadata["pdf_download_policy"] = pdf_policy

        if not request.user_initiated:
            review = await repo.create_review_item(
                {
                    "project_id": request.project_id,
                    "item_type": "source-save-proposal",
                    "title": f"Review source save: {result.title}",
                    "summary": "Untrusted provider or page text proposed a source save. User action is required.",
                    "origin_type": request.source_origin,
                    "target_type": "source",
                    "payload": metadata,
                }
            )
            raise HTTPException(status_code=403, detail={"reason": "user-initiated-save-required", "review_item_id": review["id"]})

        source = await repo.upsert_source(
            {
                "id": source_id_from_discovery_result(metadata),
                "project_id": request.project_id,
                "title": result.title,
                "authors": author_string(result.authors),
                "year": str(result.year or ""),
                "url": result.url or result.pdf_url or "",
                "abstract": result.abstract,
                "kind": "paper",
                "source_type": "paper",
                "doi": result.doi,
                "arxiv_id": result.arxiv_id,
                "metadata_json": json.dumps(metadata, sort_keys=True),
                "metadata_sources_json": json.dumps(metadata["metadata_provenance"], sort_keys=True),
                "trust_origin": "user-curated",
            }
        )
        await repo.add_event("sources.saved", f"Saved source {result.title}")
        return {"source": source, "pdf_policy": pdf_policy}

    @app.post("/api/sources/ingest")
    async def ingest_source(
        file: UploadFile | None = File(None),
        url: str | None = Form(None),
        doi: str | None = Form(None),
        title: str | None = Form(None),
        session: AsyncSession = Depends(get_session),
    ) -> dict[str, object]:
        repo = Repository(session)
        if file:
            raw = await file.read()
            final_title = title or file.filename or "Uploaded paper"
            project_root = hydra_project_root()
            original_path = write_uploaded_original(project_root, file.filename or "paper", raw)
            kind = "pdf"
            url_ref = url or doi or ""
        elif url or doi:
            final_title = title or f"Ingested {url or doi}"
            url_ref = url or doi or ""
            project_root = hydra_project_root()
            original_path = write_uploaded_original(project_root, f"{hashlib.sha256(url_ref.encode()).hexdigest()[:12]}.md", f"This is mocked extracted text from {url_ref}.".encode("utf-8"))
            kind = "url"
        else:
            raise HTTPException(status_code=400, detail="Must provide file, url, or doi")

        metadata = {
            "original_path": str(original_path.relative_to(project_root)),
            "original_content_hash": sha256_bytes(original_path.read_bytes()),
            "trust_level": TRUST_LEVEL_UNTRUSTED,
        }
        summary = f"Mocked summary for {final_title}. Ingestion queued."
        
        source = await repo.upsert_source(
            {
                "title": final_title,
                "authors": "Local ingestion",
                "abstract": summary,
                "url": url_ref,
                "kind": kind,
                "metadata_json": json.dumps(metadata, sort_keys=True),
                "trust_origin": "user-curated",
            }
        )
        ingestion = await IngestionService().ingest(
            session,
            source_id=source["id"],
            title=source["title"],
            source_path=original_path,
            project_root=project_root,
            declared_mime=file.content_type if file else "text/markdown",
        )
        note_body = f"Summary: {summary}\n\nIngestion state: {ingestion['state']}\nArtifacts: {len(ingestion.get('artifacts', []))}"
        note = await repo.add_note(f"Notes & Summary for {source['title']}", note_body, source["id"])
        await repo.add_event("source.ingested", f"Ingested {source['title']}")
        return {"source": source, "note": note, "ingestion": ingestion}

    @app.get("/api/sources/retrieve")
    async def retrieve_rag(query: str, source_id: str | None = None, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        await repo.add_event("rag.retrieval", f"Retrieving answers for query '{query}'")
        
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
    async def writing_review(request: WritingReviewRequest, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        result = review_text(request.text)
        await repo.add_event("writing.review.completed", "Reviewed draft text")
        return result

    @app.post("/api/evidence")
    async def create_evidence(request: EvidenceCreateRequest, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        evidence = await repo.add_evidence(**request.model_dump())
        await repo.add_event("evidence.linked", f"Linked evidence for claim: {request.claim_id}")
        return evidence

    @app.get("/api/evidence")
    async def list_evidence(session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        return {"evidence": await repo.list_evidence()}

    @app.post("/api/claims")
    async def create_claim(request: ClaimCreateRequest, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        claim = await repo.add_claim(**request.model_dump())
        await repo.add_event("claim.created", "Created new claim")
        return claim

    @app.get("/api/claims")
    async def list_claims(session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        return {"claims": await repo.list_claims()}

    @app.post("/api/claims/detect")
    async def detect_claims(request: ClaimDetectRequest, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        claim1 = await repo.add_claim("Hydra reduces hallucinated citations.")
        claim2 = await repo.add_claim("LLMs always tell the truth.")
        
        # Link some evidence mock
        sources = await repo.list_sources()
        source_id = sources[0]["id"] if sources else (await repo.upsert_source({"title": "Mock Source"}))["id"]
        
        await repo.add_evidence(
            claim_id=claim1["id"],
            source_id=source_id,
            passage="Hydra architecture aims to reduce hallucinations.",
            support="supported",
            confidence=0.9
        )
        await repo.add_evidence(
            claim_id=claim2["id"],
            source_id=source_id,
            passage="Some LLMs have hallucination problems.",
            support="unsupported",
            confidence=0.2
        )
        
        await repo.add_event("claims.detected", "Detected mock claims from draft text")
        
        return {
            "claims": [claim1, claim2],
            "evidence": await repo.list_evidence()
        }

    @app.post("/api/citations")
    async def create_citation(request: CitationCreateRequest, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        citation = await repo.add_citation(**request.model_dump())
        await repo.add_event("citation.created", "Created new citation")
        return citation

    @app.get("/api/citations")
    async def list_citations(session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        return {"citations": await repo.list_citations()}

    @app.post("/api/notes")
    async def create_note(request: NoteCreateRequest, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        note = await repo.add_note(request.title, request.body, request.source_id)
        await repo.add_event("note.created", f"Created note {request.title}")
        return note

    @app.get("/api/notes")
    async def list_notes(query: str | None = None, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        return {"notes": await repo.search_notes(query)}

    @app.get("/api/notes/graph")
    async def get_notes_graph(session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        return await repo.get_graph()

    @app.get("/api/notes/{note_id}")
    async def get_note(note_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        note = await repo.get_note(note_id)
        if not note:
            raise HTTPException(status_code=404, detail="Note not found")
        return note

    @app.put("/api/notes/{note_id}")
    async def update_note(note_id: str, request: NoteUpdateRequest, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        note = await repo.update_note(note_id, request.title, request.body, request.source_id)
        if not note:
            raise HTTPException(status_code=404, detail="Note not found")
        await repo.add_event("note.updated", f"Updated note {request.title}")
        return note

    @app.delete("/api/notes/{note_id}")
    async def delete_note(note_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        success = await repo.delete_note(note_id)
        if not success:
            raise HTTPException(status_code=404, detail="Note not found")
        await repo.add_event("note.deleted", f"Deleted note {note_id}")
        return {"status": "success"}

    @app.get("/api/notes/{note_id}/links")
    async def get_note_links(note_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        return await repo.get_note_links(note_id)

    @app.post("/api/tasks")
    async def create_task(request: TaskCreateRequest, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        task = await repo.add_task(
            title=request.title,
            column=request.column,
            detail=request.detail,
            progress=request.progress,
            phase_indicator=request.phase_indicator,
            position=request.position
        )
        await repo.add_event("task.created", f"Created task {request.title}")
        return task

    @app.get("/api/tasks")
    async def list_tasks(session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        return {"tasks": await repo.list_tasks()}

    @app.put("/api/tasks/{task_id}")
    async def update_task_put(task_id: str, request: TaskUpdateRequest, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        task = await repo.update_task(task_id, request.model_dump(exclude_unset=True))
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        await repo.add_event("task.updated", f"Updated task {task['title']}")
        return task

    @app.patch("/api/tasks/{task_id}")
    async def update_task_patch(task_id: str, request: TaskUpdateRequest, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        task = await repo.update_task(task_id, request.model_dump(exclude_unset=True))
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        await repo.add_event("task.updated", f"Updated task {task['title']}")
        return task

    @app.delete("/api/tasks/{task_id}")
    async def delete_task(task_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        success = await repo.delete_task(task_id)
        if not success:
            raise HTTPException(status_code=404, detail="Task not found")
        await repo.add_event("task.deleted", f"Deleted task {task_id}")
        return {"status": "success"}

    @app.get("/api/events")
    async def events(request: Request, session: AsyncSession = Depends(get_session)) -> object:
        repo = Repository(session)
        if "text/event-stream" in request.headers.get("accept", ""):
            async def stream() -> AsyncIterator[str]:
                events_list = await repo.list_events()
                for event in reversed(events_list):
                    yield f"event: {event['kind']}\ndata: {json.dumps(event)}\n\n"
            return StreamingResponse(stream(), media_type="text/event-stream")
        return {"events": await repo.list_events()}

    @app.get("/api/export/bibliography")
    async def bibliography(session: AsyncSession = Depends(get_session), style: str = "apa") -> PlainTextResponse:
        repo = Repository(session)
        sources = await repo.list_sources()
        text = format_bibliography(sources, style)
        return PlainTextResponse(text)

    @app.put("/api/settings/provider")
    async def save_provider_settings(request: ProviderSettingsRequest, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        settings = await repo.save_provider_settings(
            request.provider,
            request.model,
            request.api_key_ref,
        )
        await repo.add_event("settings.provider.saved", f"Saved settings for {request.provider}")
        return settings

    @app.get("/api/settings")
    async def get_settings(session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        settings_path = app_data_root() / "settings.toml"
        global_settings = load_settings(settings_path).data
        return {
            "provider_settings": await repo.list_provider_settings(),
            "workspace_preferences": await repo.list_settings(),
            "global_settings": global_settings,
        }

    @app.post("/api/settings")
    async def post_settings(request: SettingsUpdateRequest, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        settings_path = app_data_root() / "settings.toml"
        global_settings = load_settings(settings_path).data
        if request.provider_settings is not None:
            for p in request.provider_settings:
                await repo.save_provider_settings(p.provider, p.model, p.api_key_ref)
                account = global_settings.setdefault("providers", {}).setdefault("accounts", {}).setdefault(p.provider, {})
                account["provider_id"] = p.provider
                account["model"] = p.model
                account["secret_ref"] = p.api_key_ref
        if request.workspace_preferences is not None:
            for k, v in request.workspace_preferences.items():
                await repo.save_setting(k, v)
                global_settings.setdefault("workspace", {})[k] = v
        save_settings(settings_path, global_settings)
        await repo.add_event("settings.updated", "Saved settings and workspace preferences")
        return {
            "provider_settings": await repo.list_provider_settings(),
            "workspace_preferences": await repo.list_settings(),
            "global_settings": global_settings,
        }

    @app.get("/api/export/preview")
    async def export_preview(session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        notes = await repo.search_notes()
        citations = await repo.list_citations()
        tasks = await repo.list_tasks()
        sources = await repo.list_sources()
        
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
    async def export_workspace_zip(session: AsyncSession = Depends(get_session)) -> StreamingResponse:
        import zipfile
        import io
        import json
        
        repo = Repository(session)
        buffer = io.BytesIO()
        
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            # Notes
            notes = await repo.search_notes()
            for note in notes:
                safe_title = "".join(c for c in note["title"] if c.isalnum() or c in (" ", "_", "-")).rstrip()
                if not safe_title:
                    safe_title = f"note_{note['id']}"
                filename = f"notes/{safe_title}.md"
                content = f"# {note['title']}\n\n{note['body']}"
                zip_file.writestr(filename, content)

            # Citations
            citations = await repo.list_citations()
            sources = await repo.list_sources()
            sources_map = {s["id"]: s for s in sources}
            citations_md = ["# Citations\n"]
            for cit in citations:
                src = sources_map.get(cit["source_id"])
                src_title = src["title"] if src else "Unknown Source"
                citations_md.append(f"### Source: {src_title}\n> {cit['text']}\n")
            zip_file.writestr("citations.md", "\n".join(citations_md))

            # Tasks
            tasks = await repo.list_tasks()
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
                "evidence": await repo.list_evidence(),
                "events": await repo.list_events(),
                "settings": await repo.list_settings(),
                "provider_settings": await repo.list_provider_settings(),
            }
            zip_file.writestr("metadata.json", json.dumps(raw_data, indent=2))
            
        buffer.seek(0)
        await repo.add_event("workspace.exported", "Exported workspace as ZIP archive")
        return StreamingResponse(
            buffer,
            media_type="application/zip",
            headers={"Content-Disposition": "attachment; filename=hydra_export.zip"}
        )

    @app.get("/api/export/workspace")
    async def export_workspace(session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        return await repo.export_workspace()

    @app.post("/api/reviews/analyze")
    def analyze_review(request: WritingReviewRequest) -> dict[str, object]:
        from hydra.writing import review_text
        return review_text(request.text)

    return app

async def persist_browser_capture(request: BrowserCaptureRequest, session: AsyncSession, create_source: bool) -> dict[str, object]:
    repo = Repository(session)
    decision = should_capture(request)
    if not decision.captured:
        return {
            "captured": False,
            "state": decision.state,
            "reason": decision.reason,
            "provider_eligible": False,
            "event": None,
            "source": None,
        }

    metadata = detect_source_metadata(request.url, request.title, request.page_text)
    metadata.update(request.metadata)
    metadata["trust_level"] = TRUST_LEVEL_UNTRUSTED
    metadata["browser_page_text_to_provider"] = bool(request.browser_page_text_to_provider)
    event = await repo.upsert_browser_event(
        {
            "project_id": request.project_id,
            "url": request.url,
            "title": request.title,
            "page_text": request.page_text,
            "selection": request.selection,
            "event_type": request.event_type,
            "detected_metadata": metadata,
        }
    )

    source: dict[str, Any] | None = None
    if create_source and source_should_promote(metadata, request.source_policy):
        source_metadata = {
            **metadata,
            "origin_browser_event_id": event["id"],
            "origin_url": request.url,
            "trust_level": TRUST_LEVEL_UNTRUSTED,
        }
        source = await repo.upsert_source(
            {
                "id": source_id_from_metadata(metadata, request.url),
                "project_id": request.project_id,
                "title": request.title or request.url,
                "url": request.url,
                "abstract": request.page_text[:800],
                "kind": "browser-source",
                "source_type": "web",
                "doi": metadata.get("doi"),
                "arxiv_id": metadata.get("arxiv_id"),
                "metadata_json": json.dumps(source_metadata, sort_keys=True),
                "trust_origin": TRUST_LEVEL_UNTRUSTED,
            }
        )

    return {
        "captured": True,
        "state": "captured",
        "provider_eligible": decision.provider_eligible,
        "event": event,
        "source": source,
    }

def motivating_excerpt(text: str) -> str:
    normalized = " ".join(text.split())
    match = re_search_case_insensitive(r"[^.?!]*save this as a source[^.?!]*[.?!]?", normalized)
    return (match or normalized)[:500]

def re_search_case_insensitive(pattern: str, text: str) -> str | None:
    import re

    found = re.search(pattern, text, re.I)
    return found.group(0).strip() if found else None


def source_id_from_discovery_result(metadata: dict[str, Any]) -> str:
    for key in ("doi", "arxiv_id", "openalex_id", "s2_id", "url"):
        value = metadata.get(key)
        if value:
            digest = hashlib.sha256(str(value).lower().encode("utf-8")).hexdigest()[:16]
            return f"src_{key}_{digest}"
    digest = hashlib.sha256(str(metadata.get("title") or "source").lower().encode("utf-8")).hexdigest()[:16]
    return f"src_title_{digest}"


def extract_upload_text(raw: bytes, content_type: str, filename: str) -> str:
    if content_type == "application/pdf" or filename.lower().endswith(".pdf"):
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(raw))
            return "\n".join(page.extract_text() or "" for page in reader.pages).strip()
        except Exception:
            return ""
    return raw.decode("utf-8", errors="ignore").strip()


def hydra_project_root() -> Path:
    from hydra.database.session import get_db_url

    db_url = get_db_url()
    if db_url.startswith("sqlite+aiosqlite:///"):
        return Path(db_url.removeprefix("sqlite+aiosqlite:///")).parent
    return Path.cwd() / ".hydra"


def write_uploaded_original(project_root: Path, filename: str, raw: bytes) -> Path:
    safe_name = "".join(char for char in filename if char.isalnum() or char in {".", "-", "_"}).strip(".") or "source"
    digest = sha256_bytes(raw)[:12]
    target = project_root / "sources" / "originals" / f"{digest}-{safe_name}"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    return target


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


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
