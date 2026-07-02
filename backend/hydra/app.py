from __future__ import annotations

import io
import json
import os
import secrets
import hashlib
import hmac
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from contextlib import asynccontextmanager
from typing import AsyncIterator, Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from sqlmodel import select
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
    BrowserCopilotActionRequest,
    BrowserHandshakeRequest,
    BrowserHistoryRequest,
    BrowserHostPermissionUpdateRequest,
    AutonomousBrowserRunStartRequest,
    AnnotationClaimRequest,
    AnnotationCreateRequest,
    EvidenceCreateRequest,
    CitationCreateRequest,
    CitationRenderRequest,
    ClaimCreateRequest,
    ClaimDetectRequest,
    ClaimPromoteRequest,
    SourceImportRequest,
    SourceMergeRequest,
    SourceTrashRequest,
    SourceUnmergeRequest,
    ManuscriptExportRequest,
    DocxEditPlanRequest,
    DocxOperationReviewRequest,
    NoteCreateRequest,
    NoteFileSaveRequest,
    NoteSuggestionRequest,
    NoteUpdateRequest,
    ProviderSettingsRequest,
    ProviderSecretRequest,
    McpServerRegisterRequest,
    McpServerEnableRequest,
    McpToolPermissionRequest,
    SettingsUpdateRequest,
    SourceDiscoveryRequest,
    SourceSaveRequest,
    ResearchRequest,
    SourceSearchRequest,
    TaskCreateRequest,
    TaskUpdateRequest,
    TaskLinkCreateRequest,
    TaskSuggestRequest,
    GitInitRequest,
    GitCommitRequest,
    GitRestoreRequest,
    GitDestructiveRequest,
    ConsoleRunRequest,
    CitationExportRequest,
    ProjectZipRequest,
    BackupRequest,
    RestoreRequest,
    WritingReviewRequest,
    ChatCompletionRequest,
    ChatCreateRequest,
    ChatUpdateRequest,
    ChatExportRequest,
    SendScopeRequest,
    AgentModeUpdateRequest,
    AutonomyPolicyRequest,
    AutopilotCancelRequest,
    AutopilotRunStartRequest,
    FullAccessUpdateRequest,
    SkillEnabledRequest,
    SkillEditRequest,
    ApprovalResolveRequest,
    OrchestratorRunStartRequest,
    LiteratureReviewRunStartRequest,
    LiteratureReviewSaveRequestModel,
    IdeaRunStartRequest,
    IdeaPromoteRequest,
    ContextFileSaveRequest,
    MemoryCandidateRequest,
)
from hydra.database.models import Annotation, Claim, IngestionJob, Task
from hydra.database.session import get_session, init_db, async_session_maker
from hydra.database.repository import Repository
from hydra.services.annotations import AnnotationIndexer, create_annotation_record, read_sidecar_records, write_sidecar_records
from hydra.services.notes import NoteFileService
from hydra.services.discovery import (
    DiscoveryCache,
    DiscoveryCoordinator,
    ProviderRateLimiter,
    SourceProviderConfig,
    author_string,
    evaluate_pdf_download_policy,
    result_from_dict,
)
from hydra.services.discovery.providers import default_providers
from hydra.services.citations import (
    CSL_PROCESSOR,
    DEFAULT_STYLE_ID,
    CitationParseError,
    CslRenderer,
    CslRenderError,
    resolve_manuscript_style,
)
from hydra.services.docx import DocxPackageError, DocxService, detect_latex_toolchain
from hydra.services.docx import (
    DocxApplyError,
    DocxPlanError,
    EditProposal,
    apply_operations,
    build_plan,
    read_structural_model,
    resolve_working_docx,
    rollback as rollback_docx_plan,
)
from hydra.services.writing import (
    global_defaults_from_settings,
    list_manuscripts,
    resolve_manuscript_format,
)
from hydra.services.ingestion import IngestionService
from hydra.services.ingestion.safety import validate_source_file
from hydra.services.ingestion.types import QuarantineError
from hydra.services.tasks import TaskProposal, propose_task
from hydra.services.git import GitError, GitService, suggest_grouped_commits
from hydra.services.console import ConsoleService
from hydra.services.browser import (
    BrowserActionRequest as BrowserServiceActionRequest,
    BrowserActionLogRepository,
    BrowserCopilotService,
    BrowserHostPermissionRepository,
)
from hydra.browser_automation.runner import (
    AutonomousBrowserResearchRunner,
    BrowserResearchStep,
    BrowserRunRequest,
    RECIPE_ID as AUTONOMOUS_BROWSER_RECIPE_ID,
)
from hydra.browser_automation.driver import PlaywrightBrowserResearchDriver
from hydra.services.export import (
    build_project_zip,
    export_options,
    restore_project,
    safe_sqlite_backup,
    to_bibtex,
    to_csl_json,
    to_ris,
)
from hydra.services.export.bundle import ExportOptions
from hydra.storage.project import evaluate_git_init, reindex_notes_from_canonical_files
from hydra.settings.toml_config import load_settings, save_settings
from hydra.settings.secrets import InMemorySecretStore, KeyringSecretStore, ProviderSecretService, SecretStore
from hydra.providers import MockProvider, ProviderRouter, RoutingPolicy, RunBudget, build_provider
from hydra.services.assistant import AssistantConfig, AssistantService, ProviderCache
from hydra.skills.registry import (
    PLUGIN_REJECTION_MESSAGE,
    edit_skill_text,
    load_skill_registry,
    restore_skill,
    set_skill_enabled,
)
from hydra.agents.policy import InvalidModeError, VALID_MODES, normalize_mode
from hydra.agents.runs import RunBudget as AgentRunBudget
from hydra.agents.runs import RunRepository
from hydra.agents.approvals import ApprovalService, to_contract
from hydra.database.models import AgentApproval, AgentModePolicy, AgentRun
from hydra.autonomy.audit import AuditLedger
from hydra.autonomy.loop import AutopilotLoop
from hydra.autonomy.policy import (
    AutonomyPolicy,
    AutonomyPolicyError,
    BudgetLimits,
    default_autonomy_policy,
    policy_to_json,
    resolve_autonomy_policy,
)
from hydra.orchestrator.run import OrchestratorConfigError, RunConfig, RunStateMachine
from hydra.orchestrator.stages import StageEnum
from hydra.recipes.literature_review import (
    LiteratureReviewInput,
    LiteratureReviewSaveRequest,
    execute_literature_review,
    literature_review_descriptor,
    resolve_literature_review_save_approval,
    save_literature_review_artifact,
    validate_literature_review_input,
)
from hydra.recipes.paper_critique import PAPER_CRITIQUE_RECIPE_ID, paper_critique_recipe, run_paper_critique_recipe
from hydra.recipes.related_work import RELATED_WORK_RECIPE_ID, related_work_recipe, run_related_work_recipe
from hydra.recipes.idea_generation import (
    DEFAULT_STAGE_TOGGLES as IDEA_DEFAULT_STAGE_TOGGLES,
    IDEA_SLASH_COMMANDS,
    IdeaPromotionService,
    IdeaRunInput,
    run_idea_recipe,
)
from hydra.database.models import IdeaCandidate as IdeaCandidateModel
from hydra.services.project_context import (
    ContextFileMemory,
    ensure_hydra_md,
    load_global_context,
    load_project_context,
)
from hydra.storage.app_data import app_data_root, init_app_data
from hydra.storage.runtime import DEFAULT_PORT, BackendRuntime, choose_bind_host
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
RAW_SECRET_PREFIXES = (
    "sk-",
    "ai-",
    "ghp_",
    "github_pat_",
    "xoxb-",
    "xoxp-",
    "AKIA",
    "ASIA",
)
BRIDGE_TOKEN_TTL_SECONDS = 3600
BRIDGE_NONCE_TTL_SECONDS = 300

_MEMORY_SECRET_STORE = InMemorySecretStore()
_PROVIDER_CACHE = ProviderCache()


def _assistant_privacy() -> dict[str, Any]:
    settings = load_settings(app_data_root() / "settings.toml").data
    privacy = settings.get("privacy", {})
    general = settings.get("general", {})
    assistant = settings.get("assistant", {})
    offline_only = bool(privacy.get("offline_only") or general.get("offline_only"))
    opt_ins = dict(privacy.get("provider_send_opt_ins") or {})
    # Browser page text to provider is a separate opt-in (HL-CONSENT-04).
    browser = settings.get("browser", {})
    if browser.get("browser_page_text_to_provider"):
        opt_ins["browser_page_text"] = True
    return {
        "offline_only": offline_only,
        "g3_enabled": bool(privacy.get("g3_provider_send")),
        "opt_ins": opt_ins,
        "ignored_paths": list(settings.get("indexing", {}).get("ignored_paths") or []),
        "default_mode": str(assistant.get("default_mode") or assistant.get("mode") or "passive"),
        "run_budget": int(assistant.get("run_budget", 60000)),
        "wall_clock_seconds": int(assistant.get("wall_clock_seconds", 120)),
        "max_parallel_calls": int(assistant.get("max_parallel_calls", 2)),
    }


def _build_assistant_service(secret_store: SecretStore) -> AssistantService:
    privacy = _assistant_privacy()
    config = AssistantConfig(
        g3_enabled=privacy["g3_enabled"],
        offline_only=privacy["offline_only"],
        opt_ins=privacy["opt_ins"],
        ignored_paths=privacy["ignored_paths"],
        default_mode=privacy["default_mode"],
        run_budget=privacy["run_budget"],
        wall_clock_seconds=privacy["wall_clock_seconds"],
        max_parallel_calls=privacy["max_parallel_calls"],
    )
    providers = _resolve_providers(secret_store)
    router = ProviderRouter(
        providers=providers,
        policy=RoutingPolicy(mode="single"),
        budget=RunBudget(
            run_budget_tokens=config.run_budget,
            wall_clock_seconds=config.wall_clock_seconds,
            max_parallel_calls=config.max_parallel_calls,
        ),
    )
    registry = load_skill_registry()
    return AssistantService(
        router=router,
        config=config,
        cache=_PROVIDER_CACHE,
        skill_descriptors=registry.enabled_descriptors(),
    )


def _resolve_providers(secret_store: SecretStore) -> list[Any]:
    """Build provider adapters from configured accounts; fall back to MockProvider.

    In test/dev with no resolvable BYO key we use MockProvider so no live API is hit.
    """
    settings = load_settings(app_data_root() / "settings.toml").data
    accounts = settings.get("providers", {}).get("accounts", {})
    providers: list[Any] = []
    service = ProviderSecretService(secret_store)
    for provider_id, account in accounts.items():
        if provider_id not in {"openai", "openrouter"}:
            continue
        secret = service.get_provider_secret(app_data_root() / "settings.toml", provider_id, "api_key")
        if not secret:
            continue
        model = str(account.get("model") or ("gpt-4.1-mini" if provider_id == "openai" else "openrouter/auto"))
        try:
            providers.append(build_provider(provider_id, secret, model))
        except Exception:
            continue
    if not providers:
        providers.append(MockProvider())
    return providers


def _agent_run_public(run: AgentRun) -> dict[str, object]:
    return {
        "id": run.id,
        "project_id": run.project_id,
        "recipe": run.recipe,
        "mode": run.mode,
        "status": run.status,
        "paused": bool(run.paused),
        "tokens_used": run.tokens_used,
        "created_at": run.created_at.timestamp(),
        "artifacts": json.loads(run.artifacts or "[]"),
    }


def create_app() -> FastAPI:
    bridge_tokens: dict[str, float] = {}
    discovery_cache = DiscoveryCache(persist=True)
    secret_store = _secret_store()
    _ensure_runtime_nonce(app_data_root())

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        runtime: BackendRuntime | None = None
        runtime_managed = os.environ.get("HYDRALAB_RUNTIME_MANAGED") == "1"
        if not runtime_managed:
            port = int(os.environ.get("HYDRALAB_PORT", str(DEFAULT_PORT)))
            runtime = BackendRuntime(app_data_root=app_data_root(), host=HYDRALAB_BIND_HOST, port=port)
            acquired = runtime.acquire()
            if not acquired.acquired:
                message = f"HydraLab backend is already running (pid {acquired.running_pid}); refusing to start a second writer."
                print(message, file=sys.stderr)
                raise RuntimeError(message)
            project_root = os.environ.get("HYDRALAB_PROJECT_ROOT")
            runtime.write_port_file(project_root=Path(project_root) if project_root else None)
        await init_db()
        try:
            yield
        finally:
            if runtime is not None:
                runtime.release()

    app = FastAPI(title="Hydra Phase 1 Research API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:8765",
            "http://127.0.0.1:8765",
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
        token_hash = _hash_bridge_token(token)
        now = time.time()
        for stored_hash, issued_at in list(bridge_tokens.items()):
            if now - issued_at > BRIDGE_TOKEN_TTL_SECONDS:
                bridge_tokens.pop(stored_hash, None)
        if not any(hmac.compare_digest(token_hash, stored_hash) for stored_hash in bridge_tokens):
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
        if not _consume_runtime_nonce(app_data_root(), request.handshake_nonce):
            raise HTTPException(status_code=401, detail="Invalid browser bridge nonce")
        token = secrets.token_urlsafe(32)
        bridge_tokens.clear()
        bridge_tokens[_hash_bridge_token(token)] = time.time()
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

    @app.get("/api/browser/modes")
    async def browser_modes(session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        return {"modes": BrowserCopilotService(session).browser_modes()}

    @app.get("/api/browser/actions")
    async def browser_actions(host: str = "") -> dict[str, object]:
        from hydra.services.browser import browser_copilot_tool_descriptors

        return {"actions": browser_copilot_tool_descriptors(host)}

    @app.get("/api/browser/permissions")
    async def browser_host_permission(
        project_id: str,
        host: str,
        session: AsyncSession = Depends(get_session),
    ) -> dict[str, object]:
        permission = await BrowserHostPermissionRepository(session).get(project_id, host)
        return {"permission": permission}

    @app.post("/api/browser/permissions")
    async def set_browser_host_permission(
        request: BrowserHostPermissionUpdateRequest,
        session: AsyncSession = Depends(get_session),
    ) -> dict[str, object]:
        permission = await BrowserHostPermissionRepository(session).set(
            request.project_id,
            request.host,
            request.state,
            task_group_id=request.task_group_id,
        )
        return {"permission": permission}

    @app.get("/api/browser/action-log")
    async def browser_action_log(
        project_id: str = "default",
        session: AsyncSession = Depends(get_session),
    ) -> dict[str, object]:
        return {"actions": await BrowserActionLogRepository(session).list(project_id=project_id)}

    @app.get("/api/browser/autonomous-runs")
    async def list_autonomous_browser_runs(
        project_id: str = "default",
        session: AsyncSession = Depends(get_session),
    ) -> dict[str, object]:
        rows = (
            await session.exec(
                select(AgentRun)
                .where(
                    AgentRun.project_id == project_id,
                    AgentRun.recipe == AUTONOMOUS_BROWSER_RECIPE_ID,
                )
                .order_by(AgentRun.created_at.desc())
            )
        ).all()
        return {"runs": [_agent_run_public(row) for row in rows]}

    @app.post("/api/browser/autonomous-runs")
    async def start_autonomous_browser_run(
        request: AutonomousBrowserRunStartRequest,
        session: AsyncSession = Depends(get_session),
    ) -> dict[str, object]:
        policy = await _mode_policy(session, request.project_id)
        privacy = _assistant_privacy()
        mode = policy.default_mode or privacy["default_mode"]
        runner = AutonomousBrowserResearchRunner(
            session,
            driver=PlaywrightBrowserResearchDriver(headless=False),
            artifact_root=hydra_project_root(),
            token_budget=int(privacy["run_budget"]),
            wall_clock_seconds=int(privacy["wall_clock_seconds"]),
        )
        result = await runner.start(
            BrowserRunRequest(
                project_id=request.project_id,
                mode=mode,
                task_id=request.task_id,
                task_label=request.task_label,
                steps=[BrowserResearchStep(url=url) for url in request.start_urls],
                full_access_enabled=bool(policy.full_access_enabled),
            )
        )
        run = await session.get(AgentRun, result.run_id)
        return {
            "run": _agent_run_public(run) if run is not None else {"id": result.run_id, "status": result.state},
            "state": result.state,
            "host_prompt": result.host_prompt,
            "budget_prompt": result.budget_prompt,
            "rate_limit_state": result.rate_limit_state,
        }

    @app.post("/api/browser/autonomous-runs/{run_id}/cancel")
    async def cancel_autonomous_browser_run(
        run_id: str,
        session: AsyncSession = Depends(get_session),
    ) -> dict[str, object]:
        await AutonomousBrowserResearchRunner(session).cancel(run_id)
        run = await session.get(AgentRun, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Run not found")
        return {"run": _agent_run_public(run)}

    @app.post("/api/browser/copilot/actions")
    async def propose_browser_action(
        request: BrowserCopilotActionRequest,
        session: AsyncSession = Depends(get_session),
    ) -> dict[str, object]:
        result = await BrowserCopilotService(session).propose(
            BrowserServiceActionRequest(
                project_id=request.project_id,
                action=request.action,
                url=request.url,
                title=request.title,
                page_text=request.page_text,
                host=request.host,
                mode=request.mode,
                task_group_id=request.task_group_id,
                task_group_label=request.task_group_label,
                user_triggered=request.user_triggered,
            )
        )
        return result.__dict__

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

    # ---------------------------------------------------------------- chats
    @app.get("/api/chats")
    async def list_chats(project_id: str = "default", session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        await repo.ensure_default_chat(project_id)
        return {"chats": await repo.list_chats(project_id)}

    @app.post("/api/chats")
    async def create_chat(request: ChatCreateRequest, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        return {"chat": await repo.create_chat(request.project_id, request.name)}

    @app.patch("/api/chats/{chat_id}")
    async def update_chat(chat_id: str, request: ChatUpdateRequest, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        chat = await repo.update_chat(chat_id, name=request.name, archived=request.archived)
        if chat is None:
            raise HTTPException(status_code=404, detail="Chat not found")
        return {"chat": chat}

    @app.get("/api/chats/search")
    async def search_chats(project_id: str = "default", q: str = "", session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        return {"chats": await repo.search_chats(project_id, q)}

    @app.get("/api/chats/{chat_id}/messages")
    async def list_chat_messages(chat_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        return {"messages": await repo.list_chat_messages(chat_id)}

    @app.post("/api/chats/{chat_id}/export")
    async def export_chat(chat_id: str, request: ChatExportRequest, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        chat = await repo.get_chat(chat_id)
        if chat is None:
            raise HTTPException(status_code=404, detail="Chat not found")
        messages = await repo.list_chat_messages(chat_id)
        if request.message_ids:
            selected = [m for m in messages if m["id"] in set(request.message_ids)]
        else:
            selected = messages
        path = write_chat_artifact(hydra_project_root(), chat, selected)
        await repo.add_event("chat.exported", f"Exported chat {chat['name']} to {path.name}")
        return {"path": str(path.relative_to(hydra_project_root())), "message_count": len(selected)}

    @app.post("/api/chat/completions")
    async def chat_completions(request: ChatCompletionRequest, session: AsyncSession = Depends(get_session)) -> StreamingResponse:
        repo = Repository(session)
        chat_id = request.chat_id
        if chat_id:
            chat = await repo.get_chat(chat_id)
            if chat is None:
                raise HTTPException(status_code=404, detail="Chat not found")
        else:
            chat = await repo.ensure_default_chat(request.project_id)
            chat_id = chat["id"]

        context_refs = [ref.model_dump() for ref in request.context_refs]
        await repo.add_chat_message(chat_id, "user", request.message, context_refs=context_refs)
        assistant_row = await repo.add_chat_message(chat_id, "assistant", "", trust_origin="assistant")
        assistant_message_id = assistant_row["id"]
        service = _build_assistant_service(secret_store)

        async def persist_delta(delta: str) -> None:
            async with async_session_maker() as bg_session:
                await Repository(bg_session).append_chat_message_content(assistant_message_id, delta)

        async def stream() -> AsyncIterator[str]:
            async for event in service.stream_reply(request.message, context_refs=context_refs, on_delta=persist_delta):
                payload = dict(event)
                if event.get("type") == "done":
                    payload["chat_id"] = chat_id
                    payload["message_id"] = assistant_message_id
                yield f"data: {json.dumps(payload)}\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.post("/api/assistant/send-scope")
    async def preview_send_scope(request: SendScopeRequest) -> dict[str, object]:
        service = _build_assistant_service(secret_store)
        scope = service.resolve_scope([ref.model_dump() for ref in request.context_refs])
        if scope.has_hard_block:
            raise HTTPException(
                status_code=403,
                detail={"reason": scope.blocked[0]["reason"], "blocked": scope.blocked, "kind": "hard-blocked"},
            )
        return {"included": scope.included, "excluded": scope.excluded, "blocked": scope.blocked}

    async def _mode_policy(session: AsyncSession, project_id: str) -> AgentModePolicy:
        policy = await session.get(AgentModePolicy, project_id)
        if policy is None:
            # Full Access defaults OFF on a fresh project (HL-MODE-03).
            policy = AgentModePolicy(project_id=project_id, default_mode="passive", full_access_enabled=False)
        return policy

    @app.get("/api/assistant/modes")
    async def assistant_modes(project_id: str = "default", session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        privacy = _assistant_privacy()
        policy = await _mode_policy(session, project_id)
        return {
            "default_mode": policy.default_mode or privacy["default_mode"],
            "full_access_enabled": bool(policy.full_access_enabled),
            "modes": [
                {"id": "passive", "label": "Passive (Suggest-only)", "enabled": True, "phase": 1},
                {"id": "copilot", "label": "Co-pilot (Approve-to-apply)", "enabled": True, "phase": 2},
                {"id": "full_access", "label": "Full Access (YOLO)", "enabled": bool(policy.full_access_enabled), "phase": 2},
            ],
            "offline_only": privacy["offline_only"],
            "g3_provider_send": privacy["g3_enabled"],
        }

    @app.post("/api/assistant/mode")
    async def set_assistant_mode(request: AgentModeUpdateRequest, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        try:
            mode = normalize_mode(request.mode)
        except InvalidModeError as exc:
            raise HTTPException(status_code=400, detail={"reason": str(exc), "valid_modes": list(VALID_MODES)}) from exc
        settings_path = app_data_root() / "settings.toml"
        settings = load_settings(settings_path).data
        settings.setdefault("assistant", {})["default_mode"] = mode
        save_settings(settings_path, settings)
        policy = await _mode_policy(session, request.project_id)
        policy.default_mode = mode
        # Selecting a higher mode never itself enables Full Access; that is a
        # separate per-project opt-in (HL-MODE-03).
        policy.updated_at = datetime.now(timezone.utc)
        session.add(policy)
        await session.commit()
        await session.refresh(policy)
        return {"default_mode": policy.default_mode, "full_access_enabled": bool(policy.full_access_enabled)}

    @app.post("/api/assistant/full-access")
    async def set_full_access(request: FullAccessUpdateRequest, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        policy = await _mode_policy(session, request.project_id)
        policy.full_access_enabled = bool(request.enabled)
        if not request.enabled and policy.default_mode == "full_access":
            policy.default_mode = "passive"
        policy.updated_at = datetime.now(timezone.utc)
        session.add(policy)
        await session.commit()
        await session.refresh(policy)
        return {"full_access_enabled": bool(policy.full_access_enabled), "default_mode": policy.default_mode}

    @app.post("/api/assistant/offline")
    async def set_offline_only(enabled: bool = True) -> dict[str, object]:
        settings_path = app_data_root() / "settings.toml"
        settings = load_settings(settings_path).data
        settings.setdefault("privacy", {})["offline_only"] = bool(enabled)
        settings.setdefault("general", {})["offline_only"] = bool(enabled)
        save_settings(settings_path, settings)
        if enabled:
            _PROVIDER_CACHE.purge()
        return {"offline_only": bool(enabled), "cache_purged": bool(enabled), "status": "offline-blocked" if enabled else "online"}

    # ---------------------------------------------------------------- skills
    def _skill_project_dir() -> Path:
        return hydra_project_root() / ".hydralab" / "skills"

    def _skill_state_dir() -> Path:
        # Kept separate from the scope folders so the state JSON is never mistaken
        # for a plugin manifest during discovery.
        return hydra_project_root() / ".hydralab" / "skill-state"

    def _load_skills():
        return load_skill_registry(project_dir=_skill_project_dir(), state_dir=_skill_state_dir())

    @app.get("/api/skills")
    async def list_skills() -> dict[str, object]:
        registry = _load_skills()
        return {
            "skills": [s.to_api() for s in registry.skills],
            "rejected_plugins": registry.rejected_plugins,
        }

    @app.post("/api/skills/{skill_id}/enabled")
    async def toggle_skill(skill_id: str, request: SkillEnabledRequest) -> dict[str, object]:
        registry = _load_skills()
        skill = registry.get(skill_id)
        if skill is None:
            raise HTTPException(status_code=404, detail="skill not found")
        try:
            set_skill_enabled(_skill_state_dir(), skill, request.enabled)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _load_skills().get(skill_id).to_api()

    @app.put("/api/skills/{skill_id}")
    async def edit_skill(skill_id: str, request: SkillEditRequest) -> dict[str, object]:
        registry = _load_skills()
        if registry.get(skill_id) is None:
            raise HTTPException(status_code=404, detail="skill not found")
        reason = edit_skill_text(_skill_state_dir(), skill_id, request.text)
        return {"skill": _load_skills().get(skill_id).to_api(), "validation_error": reason}

    @app.post("/api/skills/{skill_id}/restore")
    async def restore_skill_default(skill_id: str) -> dict[str, object]:
        registry = _load_skills()
        skill = registry.get(skill_id)
        if skill is None:
            raise HTTPException(status_code=404, detail="skill not found")
        if skill.scope != "builtin":
            raise HTTPException(status_code=400, detail="only built-in skills restore to factory text")
        restore_skill(_skill_state_dir(), skill_id)
        return _load_skills().get(skill_id).to_api()

    # ----------------------------------------------------- orchestrator / agent runs
    @app.get("/api/orchestrator/stages")
    async def list_orchestrator_stages() -> dict[str, object]:
        return {
            "stages": [
                {"id": stage.value, "label": stage.value.replace("_", " ").title(), "enabled": True}
                for stage in StageEnum
            ]
        }

    @app.get("/api/orchestrator/recipes")
    async def list_orchestrator_recipes() -> dict[str, object]:
        descriptor = literature_review_descriptor(engine_enabled=True)
        recipes: list[dict[str, object]] = [] if descriptor is None else [descriptor.public_dict()]
        recipes.extend([paper_critique_recipe(), related_work_recipe()])
        return {"recipes": recipes}

    @app.get("/api/orchestrator/runs")
    async def list_orchestrator_runs(project_id: str = "default", session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        rows = (
            await session.exec(
                select(AgentRun)
                .where(
                    AgentRun.project_id == project_id,
                    AgentRun.recipe.in_(["bounded-stage-pass", PAPER_CRITIQUE_RECIPE_ID, RELATED_WORK_RECIPE_ID]),
                )
                .order_by(AgentRun.created_at.desc())
            )
        ).all()
        return {
            "runs": [
                {
                    "id": run.id,
                    "project_id": run.project_id,
                    "mode": run.mode,
                    "status": run.status,
                    "paused": run.paused,
                    "tokens_used": run.tokens_used,
                    "created_at": run.created_at.timestamp(),
                }
                for run in rows
            ]
        }

    @app.post("/api/orchestrator/runs")
    async def start_orchestrator_run(
        request: OrchestratorRunStartRequest,
        session: AsyncSession = Depends(get_session),
    ) -> dict[str, object]:
        policy = await _mode_policy(session, request.project_id)
        privacy = _assistant_privacy()
        mode = policy.default_mode or privacy["default_mode"]
        recipe_privacy = {
            "g3_enabled": privacy["g3_enabled"],
            "offline_only": privacy["offline_only"],
            "opt_ins": privacy["opt_ins"],
        }
        if request.recipe_id in {PAPER_CRITIQUE_RECIPE_ID, RELATED_WORK_RECIPE_ID}:
            runner = run_paper_critique_recipe if request.recipe_id == PAPER_CRITIQUE_RECIPE_ID else run_related_work_recipe
            result = await runner(
                session,
                request.recipe_inputs,
                project_id=request.project_id,
                mode=mode,
                budget=AgentRunBudget(
                    run_budget_tokens=int(privacy["run_budget"]),
                    wall_clock_seconds=int(privacy["wall_clock_seconds"]),
                ),
                privacy=recipe_privacy,
            )
            run = await session.get(AgentRun, result.run_id)
            return {
                "run": {
                    "id": result.run_id,
                    "project_id": request.project_id,
                    "mode": run.mode if run else mode,
                    "status": run.status if run else result.state,
                    "state": result.state,
                    "paused": bool(run.paused) if run else False,
                },
                "trace": result.trace.public_dict(),
                "artifacts": result.artifacts,
            }
        try:
            config = RunConfig.resolve(
                stage_overrides=request.enabled_stages or {stage.value: True for stage in StageEnum},
                scoring_method=request.scoring_method,
            )
        except OrchestratorConfigError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        result = await RunStateMachine(
            RunRepository(session),
            config,
            budget=AgentRunBudget(
                run_budget_tokens=int(privacy["run_budget"]),
                wall_clock_seconds=int(privacy["wall_clock_seconds"]),
            ),
        ).start(project_id=request.project_id, mode=policy.default_mode or privacy["default_mode"])
        run = await session.get(AgentRun, result.run_id)
        trace = await RunRepository(session).get_trace(result.run_id)
        return {
            "run": {
                "id": result.run_id,
                "project_id": request.project_id,
                "mode": run.mode if run else policy.default_mode,
                "status": run.status if run else result.state,
                "state": result.state,
                "paused": bool(run.paused) if run else False,
            },
            "trace": trace.public_dict(),
            "artifacts": json.loads((run.artifacts if run else "[]") or "[]"),
        }

    @app.post("/api/recipes/literature-review/runs")
    async def start_literature_review_run(
        request: LiteratureReviewRunStartRequest,
        session: AsyncSession = Depends(get_session),
    ) -> dict[str, object]:
        validation = validate_literature_review_input(
            {
                "question": request.question,
                "source_scope": request.source_scope,
                "depth": request.depth,
            }
        )
        if not validation.allowed or validation.inputs is None:
            raise HTTPException(status_code=400, detail=validation.message)
        policy = await _mode_policy(session, request.project_id)
        privacy = _assistant_privacy()
        result = await execute_literature_review(
            session=session,
            project_root=hydra_project_root(),
            inputs=LiteratureReviewInput(
                question=validation.inputs.question,
                source_scope=validation.inputs.source_scope,
                depth=validation.inputs.depth,
            ),
            mode=policy.default_mode or privacy["default_mode"],
            semantic_enabled=request.semantic_search,
            g3_enabled=bool(privacy["g3_enabled"]),
            offline_only=bool(privacy["offline_only"]),
            budget=AgentRunBudget(
                run_budget_tokens=int(privacy["run_budget"]),
                wall_clock_seconds=int(privacy["wall_clock_seconds"]),
            ),
        )
        run = await session.get(AgentRun, result.run_id)
        trace = await RunRepository(session).get_trace(result.run_id)
        return {
            "run": {
                "id": result.run_id,
                "project_id": request.project_id,
                "mode": run.mode if run else policy.default_mode,
                "status": run.status if run else result.state,
                "state": result.state,
                "paused": bool(run.paused) if run else False,
            },
            "trace": trace.public_dict(),
            "artifacts": json.loads((run.artifacts if run else "[]") or "[]"),
            "review_item_ids": result.review_item_ids,
        }

    @app.post("/api/recipes/literature-review/artifacts/save")
    async def request_literature_review_save(
        request: LiteratureReviewSaveRequestModel,
        session: AsyncSession = Depends(get_session),
    ) -> dict[str, object]:
        run = await session.get(AgentRun, request.run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        artifacts = json.loads(run.artifacts or "[]")
        payload = next((item for item in artifacts if item.get("kind") == "literature-review"), None)
        if payload is None:
            raise HTTPException(status_code=404, detail="literature review artifact not found")
        from hydra.recipes.literature_review import _artifact_from_payload

        pending = await save_literature_review_artifact(
            session=session,
            project_root=hydra_project_root(),
            artifact=_artifact_from_payload(payload),
            request=LiteratureReviewSaveRequest(
                run_id=request.run_id,
                destination=request.destination,
                filename=request.filename,
            ),
            mode=run.mode,
        )
        return {
            "approval_id": pending.approval_id,
            "artifact_preview": pending.artifact_preview,
            "target_relative_path": pending.target_relative_path,
        }

    @app.post("/api/recipes/literature-review/saves/{approval_id}/resolve")
    async def resolve_literature_review_save(
        approval_id: str,
        request: ApprovalResolveRequest,
        session: AsyncSession = Depends(get_session),
    ) -> dict[str, object]:
        return await resolve_literature_review_save_approval(
            session=session,
            project_root=hydra_project_root(),
            approval_id=approval_id,
            decision=request.decision,
        )

    @app.get("/api/agent/runs/{run_id}")
    async def get_agent_run(run_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        runs = RunRepository(session)
        run = await session.get(AgentRun, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        trace = await runs.get_trace(run_id)
        return {
            "run": {
                "id": run.id,
                "project_id": run.project_id,
                "mode": run.mode,
                "status": run.status,
                "paused": run.paused,
                "stop_reason": run.stop_reason,
            },
            "trace": trace.public_dict(),
            "artifacts": json.loads(run.artifacts or "[]"),
        }

    @app.post("/api/agent/runs/{run_id}/pause")
    async def pause_agent_run(run_id: str, paused: bool = True, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        run = await RunRepository(session).pause_run(run_id, paused)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        return {"id": run.id, "status": run.status, "paused": run.paused}

    @app.post("/api/agent/runs/{run_id}/cancel")
    async def cancel_agent_run(run_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        run = await RunRepository(session).cancel_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        return {"id": run.id, "status": run.status, "paused": run.paused, "stop_reason": run.stop_reason}

    @app.get("/api/agent/approvals")
    async def list_agent_approvals(project_id: str = "default", session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        service = ApprovalService(session)
        pending = await service.list_pending(project_id)
        return {"approvals": [to_contract(row).public_dict() for row in pending]}

    @app.post("/api/agent/approvals/{approval_id}/resolve")
    async def resolve_agent_approval(approval_id: str, request: ApprovalResolveRequest, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        service = ApprovalService(session)
        approval = await service.get(approval_id)
        if approval is None:
            raise HTTPException(status_code=404, detail="approval not found")
        if approval.action_kind.startswith("browser."):
            result = await BrowserCopilotService(session).resolve_approval(approval_id, decision=request.decision)
            return {
                "applied": result.outcome == "applied",
                "status": result.outcome,
                "reason": result.reason,
                "log": result.log,
                "artifact": result.artifact,
            }
        result = await service.resolve(approval_id, decision=request.decision)
        return {"applied": result.applied, "status": result.status, "reason": result.reason}

    # ------------------------------------------- autonomy safety shell
    @app.get("/api/autonomy/policy")
    async def get_autonomy_policy(project_id: str = "default", session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        stored = await _mode_policy(session, project_id)
        if stored.autonomy_policy_json:
            try:
                resolved = resolve_autonomy_policy(stored, require_enabled=False)
            except AutonomyPolicyError:
                resolved = default_autonomy_policy(stored.default_mode, autopilot_enabled=bool(stored.autopilot_enabled))
        else:
            resolved = default_autonomy_policy(stored.default_mode, autopilot_enabled=bool(stored.autopilot_enabled))
        return {"project_id": project_id, "policy": resolved.public_dict()}

    @app.post("/api/autonomy/policy")
    async def set_autonomy_policy(request: AutonomyPolicyRequest, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        stored = await _mode_policy(session, request.project_id)
        resolved = AutonomyPolicy(
            mode=request.mode,
            allowed_action_types=request.allowed_action_types,
            blocked_action_types=request.blocked_action_types,
            budget_limits=BudgetLimits(
                tokens=int(request.budget_limits.get("tokens", 60000)),
                wall_clock_seconds=int(request.budget_limits.get("wall_clock_seconds", 120)),
            ),
            max_loop_count=request.max_loop_count,
            stop_conditions=request.stop_conditions,
            checkpoint_required=request.checkpoint_required,
            approval_required=request.approval_required,
            rollback_behavior=request.rollback_behavior,
            autopilot_enabled=request.autopilot_enabled,
        )
        stored.default_mode = request.mode
        stored.autopilot_enabled = request.autopilot_enabled
        stored.autonomy_policy_json = policy_to_json(resolved)
        stored.updated_at = datetime.now(timezone.utc)
        session.add(stored)
        await session.commit()
        await session.refresh(stored)
        return {"project_id": request.project_id, "policy": resolved.public_dict()}

    @app.post("/api/autonomy/runs")
    async def start_autopilot_run(
        request: AutopilotRunStartRequest,
        session: AsyncSession = Depends(get_session),
    ) -> dict[str, object]:
        stored = await _mode_policy(session, request.project_id)
        try:
            policy = resolve_autonomy_policy(stored)
            config = RunConfig.resolve(
                stage_overrides=request.enabled_stages or {stage.value: True for stage in StageEnum},
                scoring_method=request.scoring_method,
            )
        except (AutonomyPolicyError, OrchestratorConfigError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        result = await AutopilotLoop(
            session, policy, config, full_access_enabled=bool(stored.full_access_enabled)
        ).start(project_id=request.project_id, inputs=request.inputs)
        return await _autonomy_run_response(session, result.run_id, state=result.state)

    @app.post("/api/autonomy/runs/{run_id}/pause")
    async def pause_autopilot_run(run_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        run = await RunRepository(session).pause_run(run_id, True)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        return {"id": run.id, "status": run.status, "paused": run.paused, "stop_reason": run.stop_reason}

    @app.post("/api/autonomy/runs/{run_id}/resume")
    async def resume_autopilot_run(run_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        run = await session.get(AgentRun, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        stored = await _mode_policy(session, run.project_id)
        try:
            policy = resolve_autonomy_policy(stored)
        except AutonomyPolicyError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        result = await AutopilotLoop(
            session, policy, RunConfig.all_enabled(), full_access_enabled=bool(stored.full_access_enabled)
        ).resume(run_id=run_id, project_id=run.project_id)
        return await _autonomy_run_response(session, result.run_id, state=result.state)

    @app.post("/api/autonomy/runs/{run_id}/cancel")
    async def cancel_autopilot_run(
        run_id: str,
        request: AutopilotCancelRequest,
        session: AsyncSession = Depends(get_session),
    ) -> dict[str, object]:
        run = await RunRepository(session).cancel_run(run_id, stop_reason=request.stop_reason)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        return {"id": run.id, "status": run.status, "paused": run.paused, "stop_reason": run.stop_reason}

    @app.post("/api/autonomy/runs/{run_id}/retry")
    async def retry_autopilot_run(run_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        run = await session.get(AgentRun, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        stored = await _mode_policy(session, run.project_id)
        try:
            policy = resolve_autonomy_policy(stored)
        except AutonomyPolicyError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        result = await AutopilotLoop(
            session, policy, RunConfig.all_enabled(), full_access_enabled=bool(stored.full_access_enabled)
        ).retry(project_id=run.project_id)
        return await _autonomy_run_response(session, result.run_id, state=result.state)

    @app.get("/api/autonomy/pending-actions")
    async def list_pending_governed_actions(project_id: str = "default", session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        review_items = [
            item
            for item in await Repository(session).list_review_items("agent-stage-proposal")
            if item.get("project_id") in (None, project_id)
        ]
        approvals = await ApprovalService(session).list_pending(project_id)
        pending: list[dict[str, object]] = []
        for item in review_items:
            payload = item.get("payload") or {}
            pending.append(
                {
                    "id": item["id"],
                    "kind": "review_item",
                    "action_kind": payload.get("action_kind", item.get("item_type")),
                    "summary": item.get("summary") or item.get("title"),
                    "target_ref": item.get("target_id"),
                    "risk_level": payload.get("risk_level", "high"),
                    "status": item.get("status", "pending"),
                    "reason": item.get("summary", ""),
                    "payload": payload,
                }
            )
        for approval in approvals:
            payload = json.loads(approval.payload_json or "{}")
            pending.append(
                {
                    "id": approval.id,
                    "kind": "approval",
                    "action_kind": approval.action_kind,
                    "summary": approval.summary,
                    "target_ref": approval.target_ref,
                    "risk_level": payload.get("risk_level", "medium"),
                    "status": approval.status,
                    "reason": approval.reason,
                    "payload": payload,
                }
            )
        return {"pending_actions": pending}

    @app.post("/api/autonomy/pending-actions/{approval_id}/resolve")
    async def resolve_pending_governed_action(
        approval_id: str,
        request: ApprovalResolveRequest,
        session: AsyncSession = Depends(get_session),
    ) -> dict[str, object]:
        result = await ApprovalService(session).resolve(approval_id, decision=request.decision)
        return {"applied": result.applied, "status": result.status, "reason": result.reason}

    @app.get("/api/autonomy/audit-ledger")
    async def read_autonomy_audit_ledger(
        project_id: str = "default",
        run_id: str | None = None,
        session: AsyncSession = Depends(get_session),
    ) -> dict[str, object]:
        rows = await AuditLedger(session).list(project_id=project_id, run_id=run_id)
        return {
            "entries": [
                {
                    "id": row.id,
                    "project_id": row.project_id,
                    "run_id": row.run_id,
                    "actor": row.actor,
                    "action": row.action,
                    "risk_level": row.risk_level,
                    "target": row.target,
                    "approval_state": row.approval_state,
                    "created_at": row.created_at.timestamp(),
                }
                for row in rows
            ]
        }

    async def _autonomy_run_response(session: AsyncSession, run_id: str, *, state: str) -> dict[str, object]:
        run = await session.get(AgentRun, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        trace = await RunRepository(session).get_trace(run_id)
        return {
            "run": {
                "id": run.id,
                "project_id": run.project_id,
                "mode": run.mode,
                "status": run.status,
                "state": state,
                "paused": bool(run.paused),
                "stop_reason": run.stop_reason,
            },
            "trace": trace.public_dict(),
            "artifacts": json.loads(run.artifacts or "[]"),
        }

    # ------------------------------------------- idea recipe (02-06, HL-ASSIST-*)
    def _idea_candidate_public(candidate: IdeaCandidateModel) -> dict[str, object]:
        return {
            "id": candidate.id,
            "run_id": candidate.run_id,
            "title": candidate.title,
            "short_hypothesis": candidate.short_hypothesis,
            "research_question": candidate.research_question,
            "motivation": candidate.motivation,
            "method_sketch": candidate.method_sketch,
            "expected_contribution": candidate.expected_contribution,
            "required_sources": json.loads(candidate.required_sources or "[]"),
            "evidence_links": json.loads(candidate.evidence_links or "[]"),
            "novelty_claim": candidate.novelty_claim,
            "feasibility_notes": candidate.feasibility_notes,
            "risks": candidate.risks,
            "estimated_effort": candidate.estimated_effort,
            "generated_by_stage": candidate.generated_by_stage,
            "parent_candidate_id": candidate.parent_candidate_id,
            "status": candidate.status,
            "critique": json.loads(candidate.critique or "{}"),
            "rubric_results": json.loads(candidate.rubric_results or "[]"),
            "rank": candidate.rank,
            "trust_origin": candidate.trust_origin,
        }

    @app.get("/api/recipes/idea/commands")
    async def list_idea_commands() -> dict[str, object]:
        return {"commands": list(IDEA_SLASH_COMMANDS), "default_stages": dict(IDEA_DEFAULT_STAGE_TOGGLES)}

    @app.post("/api/recipes/idea/runs")
    async def start_idea_run(
        request: IdeaRunStartRequest,
        session: AsyncSession = Depends(get_session),
    ) -> dict[str, object]:
        policy = await _mode_policy(session, request.project_id)
        privacy = _assistant_privacy()
        result = await run_idea_recipe(
            session,
            project_id=request.project_id,
            run_input=IdeaRunInput(
                topic=request.topic,
                source_scope=request.source_scope,
                constraints=request.constraints,
                novelty_target=request.novelty_target,
            ),
            mode=policy.default_mode or privacy["default_mode"],
            stage_toggles=request.enabled_stages or None,
            offline_only=bool(privacy["offline_only"]),
            g3_enabled=bool(privacy["g3_enabled"]),
            budget=AgentRunBudget(
                run_budget_tokens=int(privacy["run_budget"]),
                wall_clock_seconds=int(privacy["wall_clock_seconds"]),
            ),
            scoring_method=request.scoring_method,
        )
        return await _idea_run_payload(session, result.run_id, state=result.state)

    async def _idea_run_payload(session: AsyncSession, run_id: str, *, state: str | None = None) -> dict[str, object]:
        run = await session.get(AgentRun, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="idea run not found")
        trace = await RunRepository(session).get_trace(run_id)
        candidates = (
            await session.exec(
                select(IdeaCandidateModel).where(IdeaCandidateModel.run_id == run_id)
            )
        ).all()
        return {
            "run": {
                "id": run.id,
                "project_id": run.project_id,
                "mode": run.mode,
                "status": run.status,
                "state": state or run.status,
                "paused": bool(run.paused),
                "recipe": run.recipe,
                "inputs": json.loads(run.inputs_ref or "[]"),
            },
            "trace": trace.public_dict(),
            "artifacts": json.loads(run.artifacts or "[]"),
            "candidates": [_idea_candidate_public(c) for c in candidates],
        }

    @app.get("/api/recipes/idea/runs/{run_id}")
    async def get_idea_run(run_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        return await _idea_run_payload(session, run_id)

    @app.post("/api/recipes/idea/promote")
    async def promote_idea_candidate(
        request: IdeaPromoteRequest,
        session: AsyncSession = Depends(get_session),
    ) -> dict[str, object]:
        policy = await _mode_policy(session, request.project_id)
        try:
            return await IdeaPromotionService(session).propose(
                candidate_id=request.candidate_id,
                target_kind=request.target_kind,
                project_id=request.project_id,
                mode=policy.default_mode,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/recipes/idea/promotions/{review_item_id}/resolve")
    async def resolve_idea_promotion(
        review_item_id: str,
        request: ApprovalResolveRequest,
        session: AsyncSession = Depends(get_session),
    ) -> dict[str, object]:
        service = IdeaPromotionService(session)
        decision = str(request.decision or "").strip().lower()
        try:
            if decision in {"approve", "approved", "accept", "accepted"}:
                return await service.approve(review_item_id)
            return await service.reject(review_item_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    # ----------------------------------------------------------- MCP (02-02)
    def _mcp_transport_for(server: dict[str, Any]):
        from hydra.tools.mcp.client import HttpMCPTransport

        connection = json.loads(server.get("connection_json") or "{}") if isinstance(server.get("connection_json"), str) else (server.get("connection_json") or {})
        return HttpMCPTransport(url=str(connection.get("url") or ""))

    def _mcp_server_view(server: dict[str, Any], tools: list[dict[str, Any]]) -> dict[str, Any]:
        # Derive the Settings state (HL-ASSIST-07): failure > permission-denied > ready.
        if server.get("status") == "failed":
            state = "failure"
        elif tools and all(not (t.get("enabled") and t.get("permission") == "allow") for t in tools):
            state = "permission-denied"
        else:
            state = "ready"
        return {
            "id": server["id"],
            "name": server["name"],
            "transport": server.get("transport"),
            "enabled": server.get("enabled"),
            "connector": server.get("connector"),
            "status": server.get("status"),
            "connection_error": server.get("connection_error") or "",
            "auth_handle_ref": server.get("auth_handle_ref"),
            "state": state,
            "tools": [
                {
                    "id": t["id"],
                    "name": t["name"],
                    "description": t.get("description") or "",
                    "enabled": t.get("enabled"),
                    "permission": t.get("permission"),
                    "read_only": t.get("read_only"),
                    "status": "allowed" if (t.get("enabled") and t.get("permission") == "allow") else "disabled",
                }
                for t in tools
            ],
        }

    @app.get("/api/mcp/servers")
    async def list_mcp_servers(session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        servers = await repo.list_mcp_servers()
        views = []
        for server in servers:
            tools = await repo.list_mcp_tools(server_id=server["id"])
            views.append(_mcp_server_view(server, tools))
        # Empty state (HL-ASSIST-07) is derived by the client when servers == [].
        return {"servers": views}

    @app.post("/api/mcp/servers")
    async def register_mcp_server(request: McpServerRegisterRequest, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        from hydra.tools.mcp import MCPService

        service = MCPService(Repository(session))
        try:
            if request.connector:
                server = await service.register_connector(request.connector, name=request.name)
            else:
                server = await service.register_server(
                    name=request.name,
                    transport=request.transport,
                    connection=request.connection,
                    auth_handle_ref=request.auth_handle_ref,
                )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        repo = Repository(session)
        tools = await repo.list_mcp_tools(server_id=server["id"])
        return {"server": _mcp_server_view(server, tools)}

    @app.post("/api/mcp/servers/{server_id}/enable")
    async def enable_mcp_server(server_id: str, request: McpServerEnableRequest, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        server = await repo.set_mcp_server_enabled(server_id, request.enabled)
        if server is None:
            raise HTTPException(status_code=404, detail="MCP server not found")
        tools = await repo.list_mcp_tools(server_id=server_id)
        return {"server": _mcp_server_view(server, tools)}

    @app.post("/api/mcp/servers/{server_id}/discover")
    async def discover_mcp_tools(server_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        from hydra.tools.mcp import MCPService

        repo = Repository(session)
        server = await repo.get_mcp_server(server_id)
        if server is None:
            raise HTTPException(status_code=404, detail="MCP server not found")
        service = MCPService(repo)
        try:
            result = await service.connect_and_discover(server_id, _mcp_transport_for(server))
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        server = await repo.get_mcp_server(server_id)
        tools = await repo.list_mcp_tools(server_id=server_id)
        return {"result_status": result["status"], "server": _mcp_server_view(server, tools)}

    @app.patch("/api/mcp/tools/{tool_id}")
    async def set_mcp_tool_permission(tool_id: str, request: McpToolPermissionRequest, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        try:
            tool = await repo.set_mcp_tool_permission(tool_id, enabled=request.enabled, permission=request.permission)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if tool is None:
            raise HTTPException(status_code=404, detail="MCP tool not found")
        return {"tool": tool}

    @app.get("/api/mcp/events")
    async def list_mcp_events(session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        return {"events": await repo.list_mcp_call_events()}

    # ------------------------------------------------------ context files / memory
    @app.get("/api/context-files")
    async def get_context_files(project_id: str = "default") -> dict[str, object]:
        profile = init_app_data("default")
        ensure_hydra_md(hydra_project_root())
        global_files = load_global_context(profile.profile_root, profile.profile_id)
        project_file = load_project_context(hydra_project_root())
        return {
            "profile_id": profile.profile_id,
            "global_files": [vars(f) for f in global_files],
            "project_file": vars(project_file),
        }

    @app.put("/api/context-files/{file_name}")
    async def save_context_file(file_name: str, request: ContextFileSaveRequest, project_id: str = "default", session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        profile = init_app_data("default")
        memory = ContextFileMemory(session, hydra_project_root(), profile.profile_root, profile.profile_id)
        try:
            result = await memory.manual_edit(file=file_name, new_content=request.content, project_id=project_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"written": result.written, "file": result.file, "change_id": result.change_id}

    @app.get("/api/context-files/changes")
    async def context_file_changes(project_id: str = "default", session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        profile = init_app_data("default")
        memory = ContextFileMemory(session, hydra_project_root(), profile.profile_root, profile.profile_id)
        return {"changes": await memory.list_changes(project_id=project_id)}

    @app.post("/api/memory/candidates")
    async def create_memory_candidate(request: MemoryCandidateRequest, project_id: str = "default", session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        profile = init_app_data("default")
        memory = ContextFileMemory(session, hydra_project_root(), profile.profile_root, profile.profile_id)
        candidate = await memory.route_memory_candidate(
            fact=request.fact,
            destination=request.destination,
            category=request.category,
            confidence=request.confidence,
            source_ref=request.source_ref,
            trust_origin=request.trust_origin,
            project_id=project_id,
        )
        return {"candidate": candidate}

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

    @app.get("/api/project/objects")
    async def project_objects(project_id: str | None = None, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        sources = await repo.list_sources()
        notes = await repo.search_notes()
        claims = await repo.list_claims()
        tasks = await repo.list_tasks()
        citations = await repo.list_citations()
        evidence = await repo.list_evidence()

        if project_id:
            sources = [item for item in sources if item.get("project_id") in (None, project_id)]
            notes = [item for item in notes if item.get("project_id") in (None, project_id)]
            claims = [item for item in claims if item.get("project_id") in (None, project_id)]
            tasks = [item for item in tasks if item.get("project_id") in (None, project_id)]
            citations = [item for item in citations if item.get("project_id") in (None, project_id)]

        return {
            "project_id": project_id or "default",
            "objects": {
                "notes": notes,
                "sources": sources,
                "claims": claims,
                "tasks": tasks,
                "citations": citations,
                "evidence": evidence,
            },
            "counts": {
                "notes": len(notes),
                "sources": len(sources),
                "claims": len(claims),
                "tasks": len(tasks),
                "citations": len(citations),
                "evidence": len(evidence),
            },
        }

    @app.get("/api/project/tree")
    async def project_tree() -> dict[str, object]:
        root = hydra_project_root().resolve()
        nodes = []
        for path in sorted(root.rglob("*"), key=lambda item: str(item.relative_to(root)).lower()):
            relative = path.relative_to(root)
            if is_project_tree_excluded(relative):
                continue
            stat = path.stat()
            nodes.append(
                {
                    "id": str(relative),
                    "path": str(relative),
                    "name": path.name,
                    "type": "directory" if path.is_dir() else "file",
                    "parent": str(relative.parent) if str(relative.parent) != "." else "",
                    "depth": len(relative.parts) - 1,
                    "size": stat.st_size if path.is_file() else 0,
                    "modified_at": stat.st_mtime,
                    "index_status": project_tree_index_status(relative, is_dir=path.is_dir()),
                }
            )
        return {"root": str(root), "nodes": nodes, "excluded": [".git", ".hydralab/temp", ".hydralab/cache"]}

    @app.get("/api/review-inbox")
    async def review_inbox(project_id: str | None = None, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        review_items = await repo.list_review_items()
        if project_id:
            review_items = [item for item in review_items if item.get("project_id") in (None, project_id)]

        recovery_items = []
        for journal in NoteFileService(session, hydra_project_root()).list_recovery_journals():
            recovery_items.append(
                {
                    "id": f"recovery:{journal['id']}",
                    "item_type": "note-recovery",
                    "title": f"Recovery draft: {journal.get('note_id') or journal['id']}",
                    "summary": "Unsaved note recovery journal is pending review.",
                    "origin_type": "note-files",
                    "origin_id": journal["id"],
                    "target_type": "note",
                    "target_id": journal.get("note_id"),
                    "status": "pending",
                    "payload": journal,
                    "created_at": journal.get("updated_at") or 0,
                }
            )

        pending = [item for item in [*review_items, *recovery_items] if item.get("status", "pending") == "pending"]
        return {"items": pending, "counts": {"pending": len(pending), "review_items": len(review_items), "recovery": len(recovery_items)}}

    @app.post("/api/sources/discovery/search")
    async def source_discovery_search(request: SourceDiscoveryRequest, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        posture = _resolve_discovery_posture(request)
        coordinator = DiscoveryCoordinator(
            providers=default_providers(),
            cache=discovery_cache,
            limiter=_discovery_limiter_from_settings(),
            config=SourceProviderConfig(contact_email=request.contact_email),
        )
        payload = await coordinator.search(
            request.query,
            offline_only=posture["offline_only"],
            scholarly_apis_enabled=posture["scholarly_apis_enabled"],
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
            declared_mime = file.content_type or ""
            try:
                validate_source_file(original_path, declared_mime=declared_mime)
            except QuarantineError as exc:
                job = IngestionJob(
                    source_id=f"quarantine:{sha256_bytes(raw)[:16]}",
                    source_path=str(original_path),
                    status="quarantined",
                    progress=0,
                    original_content_hash=sha256_bytes(raw),
                    failure_reason=str(exc),
                )
                session.add(job)
                await session.commit()
                await session.refresh(job)
                return JSONResponse(
                    {
                        "state": "quarantined",
                        "job_id": job.id,
                        "reason": str(exc),
                        "source": None,
                        "artifacts": [],
                    },
                    status_code=422,
                )
        elif url or doi:
            raise HTTPException(
                status_code=501,
                detail="url/doi ingestion arrives with discovery auto-download; no artifacts are created by this endpoint yet",
            )
        else:
            raise HTTPException(status_code=400, detail="Must provide file, url, or doi")

        metadata = {
            "original_path": str(original_path.relative_to(project_root)),
            "original_content_hash": sha256_bytes(original_path.read_bytes()),
            "trust_level": TRUST_LEVEL_UNTRUSTED,
        }
        summary = f"Ingestion accepted for {final_title}."
        
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
            declared_mime=declared_mime,
        )
        note_body = f"Summary: {summary}\n\nIngestion state: {ingestion['state']}\nArtifacts: {len(ingestion.get('artifacts', []))}"
        note = await repo.add_note(f"Notes & Summary for {source['title']}", note_body, source["id"])
        await repo.add_event("source.ingested", f"Ingested {source['title']}")
        return {"source": source, "note": note, "ingestion": ingestion}

    @app.get("/api/sources/retrieve")
    async def retrieve_rag(query: str, source_id: str | None = None, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        await repo.add_event("rag.retrieval", f"Retrieving answers for query '{query}'")
        
        # Placeholder until the real retrieval branch replaces this endpoint.
        chunks = [f"Placeholder relevant passage for '{query}'"]
        if source_id:
            chunks.append(f"Passage specifically from source_id={source_id}")
            
        answer = f"Placeholder retrieval response for '{query}'."
        
        return {
            "query": query,
            "answer": answer,
            "chunks": chunks,
            "source_id": source_id,
            "placeholder": True,
        }

    @app.post("/api/writing/review")
    async def writing_review(request: WritingReviewRequest, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        result = review_text(request.text)
        await repo.add_event("writing.review.completed", "Reviewed draft text")
        return result

    @app.get("/api/writing/format-defaults")
    async def get_format_defaults() -> dict[str, object]:
        return {"defaults": _writing_global_defaults()}

    @app.get("/api/writing/manuscripts")
    async def get_manuscripts() -> dict[str, object]:
        return {"manuscripts": list_manuscripts(hydra_project_root())}

    @app.get("/api/writing/manuscripts/{manuscript}/format")
    async def get_manuscript_format(manuscript: str) -> dict[str, object]:
        resolved = resolve_manuscript_format(hydra_project_root(), manuscript, _writing_global_defaults())
        return {
            "manuscript": manuscript,
            "format": resolved.format.model_dump(),
            "validation_error": resolved.validation_error,
            "source": resolved.source,
        }

    @app.get("/api/writing/latex/availability")
    async def get_latex_availability() -> dict[str, object]:
        return detect_latex_toolchain()

    @app.get("/api/writing/docx/availability")
    async def get_docx_availability(session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        availability = DocxService().detect()
        await repo.record_docx_artifact(
            kind="availability",
            converter_adapter=availability.adapter,
            converter_version=availability.version,
            availability_status=availability.status,
            setup_error=availability.setup_error,
            status=availability.status,
        )
        return {
            "adapter": availability.adapter,
            "version": availability.version,
            "availability_status": availability.status,
            "available": availability.available,
            "setup_error": availability.setup_error,
        }

    @app.post("/api/writing/docx/import")
    async def import_docx(
        file: UploadFile = File(...),
        session: AsyncSession = Depends(get_session),
    ) -> dict[str, object]:
        repo = Repository(session)
        project_root = hydra_project_root()
        temp_dir = project_root / ".hydralab" / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        safe_name = "".join(c for c in (file.filename or "import.docx") if c.isalnum() or c in {".", "-", "_"}) or "import.docx"
        staged = temp_dir / f"{secrets.token_hex(6)}-{safe_name}"
        staged.write_bytes(await file.read())
        try:
            result = DocxService().import_docx(staged)
        finally:
            staged.unlink(missing_ok=True)
        await repo.record_docx_artifact(
            kind="import",
            converter_adapter=result.converter.adapter if result.converter else "none",
            converter_version=result.converter.version if result.converter else "",
            availability_status=result.converter.status if result.converter else "unavailable",
            setup_error=result.converter.setup_error if result.converter else "",
            status=result.status,
            source_path=file.filename,
            error_detail=result.error_detail,
            flags_json=json.dumps(result.flagged_active_content),
            metadata_json=json.dumps(result.metadata),
        )
        if result.status == "unavailable":
            raise HTTPException(status_code=503, detail={"reason": "converter-unavailable", "message": result.error_detail})
        if result.status == "rejected":
            raise HTTPException(status_code=422, detail={"reason": "package-validation", "message": result.error_detail})
        if result.status == "failed":
            raise HTTPException(status_code=422, detail={"reason": "import-failed", "message": result.error_detail})
        return {
            "status": result.status,
            "content": result.content,
            "metadata": result.metadata,
            "flagged_active_content": result.flagged_active_content,
        }

    @app.post("/api/writing/manuscripts/{manuscript}/export")
    async def export_manuscript(
        manuscript: str,
        request: ManuscriptExportRequest,
        session: AsyncSession = Depends(get_session),
    ) -> dict[str, object]:
        repo = Repository(session)
        project_root = hydra_project_root()
        resolved = resolve_manuscript_format(project_root, manuscript, _writing_global_defaults())

        bibliography: list[str] | None = None
        if request.include_bibliography:
            sources = await repo.list_sources()
            items = [s["csl_json"] for s in sources if isinstance(s.get("csl_json"), dict) and s.get("csl_json")]
            if items:
                renderer = CslRenderer(default_style=_resolve_default_citation_style())
                try:
                    bibliography = renderer.render_bibliography(items, resolved.format.citation_style)
                except CslRenderError:
                    bibliography = None

        result = DocxService().export_manuscript(
            project_root,
            manuscript,
            request.source_file,
            resolved.format,
            bibliography=bibliography,
            output_name=request.output_name,
        )
        await repo.record_docx_artifact(
            kind="export",
            manuscript=manuscript,
            project_id=request.project_id,
            converter_adapter=result.converter.adapter if result.converter else "none",
            converter_version=result.converter.version if result.converter else "",
            availability_status=result.converter.status if result.converter else "unavailable",
            setup_error=result.converter.setup_error if result.converter else "",
            status=result.status,
            source_path=request.source_file,
            output_path=result.output_path,
            error_detail=result.error_detail,
        )
        if result.status == "unavailable":
            raise HTTPException(status_code=503, detail={"reason": "converter-unavailable", "message": result.error_detail})
        if result.status == "failed":
            raise HTTPException(status_code=422, detail={"reason": "export-failed", "message": result.error_detail})
        await repo.add_event("writing.docx.exported", f"Exported manuscript {manuscript} to DOCX")
        return {"status": result.status, "output_path": result.output_path, "format": resolved.format.model_dump()}

    # --- DOCX OpenXML assisted edits (branch 02-08, Phase 2) -----------------
    @app.post("/api/writing/docx/edit-plan")
    async def create_docx_edit_plan(
        request: DocxEditPlanRequest, session: AsyncSession = Depends(get_session)
    ) -> dict[str, object]:
        repo = Repository(session)
        project_root = hydra_project_root()
        try:
            working_path = resolve_working_docx(project_root, request.manuscript, request.source_file)
        except DocxApplyError as exc:
            raise HTTPException(status_code=422, detail={"reason": "unsafe-path", "message": str(exc)}) from exc
        if not working_path.exists():
            raise HTTPException(
                status_code=404,
                detail={"reason": "manuscript-missing", "message": f"working DOCX not found: {request.source_file}"},
            )
        try:
            model = read_structural_model(working_path, project_root)
        except DocxPackageError as exc:
            raise HTTPException(status_code=422, detail={"reason": "package-validation", "message": str(exc)}) from exc

        proposals = [
            EditProposal(
                op_type=p.op_type,
                target_locator=p.target_locator,
                payload=dict(p.payload),
                justification=p.justification,
                justification_source=p.justification_source,
                motivating_excerpt=p.motivating_excerpt,
            )
            for p in request.proposals
        ]
        try:
            plan = build_plan(
                model,
                proposals,
                manuscript=request.manuscript,
                target_relpath=request.source_file,
                mode=request.mode,
                project_id=request.project_id,
            )
        except DocxPlanError as exc:
            raise HTTPException(status_code=422, detail={"reason": "unsupported-op", "message": str(exc)}) from exc

        plan_row = await repo.create_docx_edit_plan(
            manuscript=request.manuscript,
            target_relpath=request.source_file,
            mode=request.mode,
            trust_level=plan.trust_level,
            project_id=request.project_id,
        )
        operations: list[dict[str, object]] = []
        for op in plan.operations:
            operations.append(
                await repo.add_docx_edit_operation(
                    plan_id=plan_row["id"],
                    op_type=op.op_type,
                    target_locator=op.target_locator,
                    location_label=op.location_label,
                    before_summary=op.before_summary,
                    after_summary=op.after_summary,
                    payload=op.payload,
                    risk_label=op.risk_label,
                    trust_level=op.trust_level,
                    justification=op.justification,
                    motivating_excerpt=op.motivating_excerpt,
                )
            )
        for item in plan.review_inbox_items:
            await repo.create_review_item(item)
        for entry in plan.downgrade_log:
            await repo.add_event("writing.docx.mode_downgrade", json.dumps(entry, sort_keys=True))
        await repo.add_event("writing.docx.plan_created", f"Built DOCX edit plan for {request.manuscript}")
        return {
            "plan": plan_row,
            "operations": operations,
            "review_inbox": plan.review_inbox_items,
            "downgrade_log": plan.downgrade_log,
        }

    @app.get("/api/writing/docx/edit-plan/{plan_id}")
    async def get_docx_edit_plan(plan_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        plan = await repo.get_docx_edit_plan(plan_id)
        if plan is None:
            raise HTTPException(status_code=404, detail={"reason": "not-found", "message": "edit plan not found"})
        return {"plan": plan, "operations": await repo.list_docx_edit_operations(plan_id)}

    @app.post("/api/writing/docx/edit-plan/{plan_id}/operations/{op_id}/review")
    async def review_docx_operation(
        plan_id: str,
        op_id: str,
        request: DocxOperationReviewRequest,
        session: AsyncSession = Depends(get_session),
    ) -> dict[str, object]:
        repo = Repository(session)
        op = await repo.get_docx_edit_operation(op_id)
        if op is None or op.get("plan_id") != plan_id:
            raise HTTPException(status_code=404, detail={"reason": "not-found", "message": "operation not found"})
        updated = await repo.review_docx_operation(op_id, request.decision)
        return {"operation": updated}

    @app.post("/api/writing/docx/edit-plan/{plan_id}/apply")
    async def apply_docx_edit_plan(plan_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        project_root = hydra_project_root()
        plan = await repo.get_docx_edit_plan(plan_id)
        if plan is None:
            raise HTTPException(status_code=404, detail={"reason": "not-found", "message": "edit plan not found"})
        operations = await repo.list_docx_edit_operations(plan_id)
        # HL-WRITE-35: only operations with review_status == "approved" may apply.
        approved = [op for op in operations if op.get("review_status") == "approved"]
        if not approved:
            raise HTTPException(
                status_code=422,
                detail={"reason": "no-approved-operations", "message": "no approved operations to apply"},
            )
        try:
            working_path = resolve_working_docx(project_root, plan["manuscript"], plan["target_relpath"])
        except DocxApplyError as exc:
            raise HTTPException(status_code=422, detail={"reason": "unsafe-path", "message": str(exc)}) from exc

        result = apply_operations(
            project_root,
            plan_id,
            working_path,
            [{"op_type": op["op_type"], "target_locator": op["target_locator"], "payload": op["payload"]} for op in approved],
        )
        by_index = {outcome.index: outcome for outcome in result.outcomes}
        for position, op in enumerate(approved):
            outcome = by_index.get(position)
            validation = outcome.validation_status if outcome else "unvalidated"
            await repo.record_docx_operation_result(
                op["id"],
                validation_status=validation,
                applied=(result.status == "applied" and validation == "valid"),
                rollback_ref=result.checkpoint_ref if result.status == "applied" else None,
            )
        await repo.update_docx_plan_status(
            plan_id,
            status="applied" if result.status == "applied" else "failed",
            checkpoint_ref=result.checkpoint_ref,
        )
        if result.status != "applied":
            await repo.add_event("writing.docx.apply_failed", result.error_detail)
            raise HTTPException(
                status_code=422,
                detail={
                    "reason": "apply-failed",
                    "message": result.error_detail,
                    "outcomes": [outcome.__dict__ for outcome in result.outcomes],
                },
            )
        await repo.add_event("writing.docx.applied", f"Applied DOCX edit plan {plan_id}")
        return {
            "status": result.status,
            "plan": await repo.get_docx_edit_plan(plan_id),
            "operations": await repo.list_docx_edit_operations(plan_id),
            "outcomes": [outcome.__dict__ for outcome in result.outcomes],
        }

    @app.post("/api/writing/docx/edit-plan/{plan_id}/rollback")
    async def rollback_docx_edit_plan(plan_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        project_root = hydra_project_root()
        plan = await repo.get_docx_edit_plan(plan_id)
        if plan is None:
            raise HTTPException(status_code=404, detail={"reason": "not-found", "message": "edit plan not found"})
        if not plan.get("checkpoint_ref"):
            raise HTTPException(
                status_code=422, detail={"reason": "no-checkpoint", "message": "plan has no pre-apply checkpoint"}
            )
        try:
            working_path = resolve_working_docx(project_root, plan["manuscript"], plan["target_relpath"])
            rollback_docx_plan(project_root, working_path, plan["checkpoint_ref"])
        except DocxApplyError as exc:
            raise HTTPException(status_code=422, detail={"reason": "rollback-failed", "message": str(exc)}) from exc
        updated = await repo.rollback_docx_plan(plan_id)
        await repo.add_event("writing.docx.rolled_back", f"Rolled back DOCX edit plan {plan_id}")
        return {"status": "rolled_back", "plan": updated, "operations": await repo.list_docx_edit_operations(plan_id)}

    @app.post("/api/evidence")
    async def create_evidence(request: EvidenceCreateRequest, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        evidence = await repo.add_evidence(**request.model_dump())
        await repo.add_event("evidence.linked", f"Linked evidence for claim: {request.claim_id}")
        return evidence

    @app.post("/api/sources/import")
    async def import_sources(request: SourceImportRequest, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        try:
            result = await repo.import_sources(request.content, request.format, request.project_id)
        except CitationParseError as exc:
            raise HTTPException(status_code=422, detail={"reason": "parse-error", "entry": exc.entry, "message": str(exc)}) from exc
        await repo.add_event("sources.imported", f"Imported {result['count']} source(s) from {result['format']}")
        return result

    @app.get("/api/sources/export")
    async def export_sources(fmt: str = "bibtex", session: AsyncSession = Depends(get_session)) -> PlainTextResponse:
        repo = Repository(session)
        try:
            text = await repo.export_sources(fmt)
        except CitationParseError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return PlainTextResponse(text)

    @app.post("/api/sources/merge")
    async def merge_sources(request: SourceMergeRequest, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        try:
            result = await repo.merge_sources(request.source_ids, reason=request.reason, merge_confidence=request.merge_confidence)
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        await repo.add_event("sources.merged", f"Merged into survivor {result['survivor_id']}")
        return result

    @app.post("/api/sources/unmerge")
    async def unmerge_sources(request: SourceUnmergeRequest, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        try:
            result = await repo.unmerge_sources(request.merge_record_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        await repo.add_event("sources.unmerged", f"Reversed merge {request.merge_record_id}")
        return result

    @app.post("/api/sources/duplicates")
    async def detect_source_duplicates(project_id: str | None = None, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        verdicts = await repo.detect_duplicates(project_id)
        return {"duplicates": verdicts}

    @app.post("/api/sources/dedupe")
    async def dedupe_sources(project_id: str | None = None, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        merges = await repo.dedupe_by_citation_key(project_id)
        return {"merges": merges}

    @app.post("/api/sources/{source_id}/trash")
    async def trash_source(source_id: str, request: SourceTrashRequest, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        try:
            return await repo.trash_source(source_id, confirmed=request.confirmed)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/sources/{source_id}/restore")
    async def restore_source(source_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        try:
            return await repo.restore_source(source_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/refint/scan")
    async def refint_scan(project_id: str | None = None, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        findings = await repo.scan_referential_integrity(project_id)
        return {"findings": findings, "count": len(findings)}

    @app.post("/api/citations/render")
    async def render_citations(request: CitationRenderRequest, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        sources = await repo.list_sources()
        wanted = set(request.source_ids) if request.source_ids else None
        items = []
        for source in sources:
            if wanted is not None and source["id"] not in wanted:
                continue
            csl = source.get("csl_json")
            if isinstance(csl, dict) and csl:
                items.append(csl)
        global_default = _resolve_default_citation_style()
        style = resolve_manuscript_style(hydra_project_root(), request.manuscript, request.style or global_default)
        renderer = CslRenderer(default_style=global_default)
        try:
            entries = renderer.render_bibliography_html(items, style) if request.html else renderer.render_bibliography(items, style)
        except CslRenderError as exc:
            raise HTTPException(status_code=422, detail={"reason": "render-error", "message": str(exc)}) from exc
        return {"style": style, "processor": CSL_PROCESSOR, "entries": entries}

    @app.get("/api/evidence")
    async def list_evidence(session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        return {"evidence": await repo.list_evidence()}

    @app.post("/api/claims")
    async def create_claim(request: ClaimCreateRequest, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        try:
            claim = await repo.add_claim(**request.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        await repo.add_event("claim.created", "Created new claim")
        return claim

    @app.get("/api/claims")
    async def list_claims(session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        return {"claims": await repo.list_claims()}

    @app.patch("/api/claims/{claim_id}")
    async def promote_claim(claim_id: str, request: ClaimPromoteRequest, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        try:
            claim = await repo.promote_claim(claim_id, request.status, reviewed=request.reviewed)
        except ValueError as exc:
            message = str(exc)
            if message == "claim not found":
                raise HTTPException(status_code=404, detail=message) from exc
            raise HTTPException(status_code=422, detail=message) from exc
        await repo.add_event("claim.status.changed", f"Claim {claim_id} -> {request.status}")
        return claim

    @app.get("/api/claims/{claim_id}/location")
    async def resolve_claim_location(claim_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        claim = await session.get(Claim, claim_id)
        if claim is None:
            raise HTTPException(status_code=404, detail="Claim not found")
        return await repo.resolve_claim_location(claim.location_type, claim.location_id)

    @app.post("/api/claims/detect")
    async def detect_claims(request: ClaimDetectRequest, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        """Suggestion-only claim extraction (HL-CITE-07/08).

        By default no claim row is committed; the passage is returned as a
        suggestion for the researcher to accept/reject. When the opt-in
        ``auto_create`` flag is on, a single ``draft`` claim is created with
        ``extraction_mode=auto_draft`` (never a supported status, HL-CITE-08).
        """
        repo = Repository(session)
        suggestions = extract_claim_suggestions(request.text, request)
        created: list[dict[str, object]] = []
        if request.auto_create and suggestions:
            top = suggestions[0]
            claim = await repo.add_claim(
                text=top["claim_text"],
                project_id=None,
                location_type=request.location_type,
                location_id=request.location_id,
                status="draft",
                created_from="extraction",
                origin_ref=request.origin_ref,
                origin_quote=top["origin_quote"],
                extraction_confidence=top["extraction_confidence"],
                extraction_mode="auto_draft",
                trust_origin="user",
            )
            created.append(claim)
            await repo.add_event("claims.auto_draft", "Auto-created draft claim from opt-in extraction")
        else:
            await repo.add_event("claims.suggested", f"Suggested {len(suggestions)} claim candidate(s) (no commit)")
        return {"suggestions": suggestions, "created_claims": created, "committed": bool(created)}

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

    @app.get("/api/note-files")
    async def open_note_file(
        path: str,
        project_id: str = "default",
        trust_origin: str = "user",
        session: AsyncSession = Depends(get_session),
    ) -> dict[str, object]:
        try:
            return await NoteFileService(session, hydra_project_root()).open_note(
                path,
                project_id=project_id,
                trust_origin=trust_origin,
            )
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Note file not found") from None
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.put("/api/note-files/{note_id}")
    async def save_note_file(
        note_id: str,
        request: NoteFileSaveRequest,
        session: AsyncSession = Depends(get_session),
    ) -> dict[str, object]:
        try:
            return await NoteFileService(session, hydra_project_root()).save_note(note_id, request.content)
        except KeyError:
            raise HTTPException(status_code=404, detail="Note file not indexed") from None
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/note-files/{note_id}/backlinks")
    async def list_note_file_backlinks(note_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        return {"backlinks": await NoteFileService(session, hydra_project_root()).list_backlinks(note_id)}

    @app.post("/api/note-files/{note_id}/suggestions")
    async def propose_note_file_suggestion(
        note_id: str,
        request: NoteSuggestionRequest,
        session: AsyncSession = Depends(get_session),
    ) -> dict[str, object]:
        try:
            return await NoteFileService(session, hydra_project_root()).propose_inline_suggestion(
                note_id,
                suggestion_id=request.suggestion_id,
                replacement=request.replacement,
                auto_apply=request.auto_apply,
                origin_excerpt=request.origin_excerpt,
            )
        except KeyError:
            raise HTTPException(status_code=404, detail="Note file not indexed") from None

    @app.get("/api/note-files/recovery/pending")
    async def list_note_recovery_journals(session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        return {"journals": NoteFileService(session, hydra_project_root()).list_recovery_journals()}

    @app.post("/api/note-files/recovery/{journal_id}/accept")
    async def accept_note_recovery(journal_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        journal_path = hydra_project_root() / ".hydralab" / "temp" / f"{journal_id}.note-recovery.json"
        if not journal_path.exists():
            raise HTTPException(status_code=404, detail="Recovery journal not found")
        return await NoteFileService(session, hydra_project_root()).accept_recovery(journal_id)

    @app.get("/api/annotations/{source_id}")
    async def list_annotations(source_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        annotations = (
            await session.exec(
                select(Annotation).where(Annotation.source_id == source_id).order_by(Annotation.page.asc(), Annotation.created_at.asc())
            )
        ).all()
        indexer = AnnotationIndexer(session, hydra_project_root())
        if read_sidecar_records(hydra_project_root(), source_id) and (not annotations or await indexer.sidecar_index_stale(source_id)):
            annotations = await indexer.rebuild_from_sidecars(source_id)
        return {"annotations": [annotation_to_api(row) for row in annotations]}

    @app.post("/api/annotations/{source_id}")
    async def create_annotation(source_id: str, request: AnnotationCreateRequest, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        project_root = hydra_project_root()
        records = read_sidecar_records(project_root, source_id)
        record = create_annotation_record(
            source_id=source_id,
            page=request.page,
            text=request.text,
            quad_points=request.quad_points,
            annotation_type=request.type,
            linked_claim_ids=request.linked_claim_ids,
            linked_note_ids=request.linked_note_ids,
            color=request.color,
        )
        records.append(record)
        write_sidecar_records(project_root, source_id, records)
        await AnnotationIndexer(session, project_root).rebuild_from_sidecars(source_id)
        row = await session.get(Annotation, record["sidecar_record_id"])
        if row is None:
            raise HTTPException(status_code=500, detail="Annotation was written but not indexed")
        return {"annotation": annotation_to_api(row), "sidecar_record_id": record["sidecar_record_id"]}

    @app.post("/api/annotations/{sidecar_record_id}/claim")
    async def create_annotation_claim(
        sidecar_record_id: str,
        request: AnnotationClaimRequest,
        session: AsyncSession = Depends(get_session),
    ) -> dict[str, object]:
        return await AnnotationIndexer(session, hydra_project_root()).create_or_suggest_claim(
            sidecar_record_id,
            auto_create=request.auto_create,
        )

    @app.post("/api/tasks")
    async def create_task(request: TaskCreateRequest, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        task = await repo.add_task(
            title=request.title,
            column=request.column,
            detail=request.detail,
            progress=request.progress,
            phase_indicator=request.phase_indicator,
            position=request.position,
            project_id=request.project_id,
            due=request.due,
            priority=request.priority,
            tags=request.tags,
        )
        await repo.add_event("task.created", f"Created task {request.title}")
        return task

    @app.get("/api/tasks")
    async def list_tasks(
        state: str | None = None,
        project_id: str | None = None,
        session: AsyncSession = Depends(get_session),
    ) -> dict[str, object]:
        repo = Repository(session)
        return {"tasks": await repo.list_tasks(state=state, project_id=project_id)}

    def _task_updates(request: TaskUpdateRequest) -> dict[str, object]:
        updates = request.model_dump(exclude_unset=True)
        if "tags" in updates and updates["tags"] is not None:
            updates["tags"] = json.dumps(updates["tags"])
        return updates

    @app.put("/api/tasks/{task_id}")
    async def update_task_put(task_id: str, request: TaskUpdateRequest, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        task = await repo.update_task(task_id, _task_updates(request))
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        await repo.add_event("task.updated", f"Updated task {task['title']}")
        return task

    @app.patch("/api/tasks/{task_id}")
    async def update_task_patch(task_id: str, request: TaskUpdateRequest, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        task = await repo.update_task(task_id, _task_updates(request))
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

    @app.post("/api/tasks/{task_id}/links")
    async def create_task_link(task_id: str, request: TaskLinkCreateRequest, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        if await session.get(Task, task_id) is None:
            raise HTTPException(status_code=404, detail="Task not found")
        link = await repo.create_task_link(
            task_id=task_id,
            target_type=request.target_type,
            target_id_or_path=request.target_id_or_path,
            link_role=request.link_role,
        )
        return link

    @app.get("/api/tasks/{task_id}/links")
    async def list_task_links(task_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        return {"links": await repo.list_task_links(task_id)}

    @app.post("/api/tasks/suggest")
    async def suggest_task(request: TaskSuggestRequest, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        settings = await repo.list_settings()
        auto_draft_enabled = str(settings.get("auto_draft_tasks", "false")).lower() == "true"
        result = await propose_task(
            repo,
            TaskProposal(
                title=request.title,
                project_id=request.project_id,
                origin=request.origin,
                category=request.category,
                trust_origin=request.trust_origin,
                summary=request.summary,
                detail=request.detail,
                origin_type=request.origin_type,
                origin_id=request.origin_id,
                link=request.link,
                tags=request.tags,
            ),
            auto_draft_enabled=auto_draft_enabled,
        )
        await repo.add_event("task.suggested", f"Task proposal processed: {request.title}")
        return result

    @app.post("/api/tasks/{task_id}/accept")
    async def accept_task(task_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        task = await repo.accept_task(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        await repo.add_event("task.accepted", f"Accepted task {task['title']}")
        return task

    @app.post("/api/tasks/{task_id}/dismiss")
    async def dismiss_task(task_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        task = await repo.dismiss_task(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        await repo.add_event("task.dismissed", f"Dismissed task {task['title']}")
        return task

    @app.post("/api/tasks/dismiss-drafts")
    async def dismiss_draft_tasks(project_id: str | None = None, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        count = await repo.bulk_dismiss_draft_tasks(project_id)
        await repo.add_event("task.drafts.dismissed", f"Bulk-dismissed {count} draft tasks")
        return {"dismissed": count}

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
        _validate_secret_ref(request.provider, request.api_key_ref)
        repo = Repository(session)
        settings = await repo.save_provider_settings(
            request.provider,
            request.model,
            request.api_key_ref,
        )
        await repo.add_event("settings.provider.saved", f"Saved settings for {request.provider}")
        return settings

    @app.post("/api/settings/provider/secret")
    async def save_provider_secret(request: ProviderSecretRequest) -> dict[str, object]:
        service = ProviderSecretService(secret_store)
        settings_path = app_data_root() / "settings.toml"
        service.save_provider_secret(settings_path, request.provider, "api_key", request.secret)
        return {"secret_ref": f"keychain:hydralab/{request.provider}"}

    @app.get("/api/settings")
    async def get_settings(session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        settings_path = app_data_root() / "settings.toml"
        global_settings = load_settings(settings_path).data
        return {
            "provider_settings": _provider_settings_with_resolution(
                await repo.list_provider_settings(),
                secret_store,
            ),
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
                _validate_secret_ref(p.provider, p.api_key_ref)
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
            "provider_settings": _provider_settings_with_resolution(
                await repo.list_provider_settings(),
                secret_store,
            ),
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

    # -- Notes trash/restore (task-link referential integrity, HL-UX-08) -----
    @app.post("/api/notes/{note_id}/trash")
    async def trash_note_endpoint(note_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        try:
            return await repo.trash_note(note_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/notes/{note_id}/restore")
    async def restore_note_endpoint(note_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        try:
            return await repo.restore_note(note_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    # -- Git panel (HL-GIT-01..05) -------------------------------------------
    @app.get("/api/git/status")
    async def git_status() -> dict[str, object]:
        service = GitService(hydra_project_root())
        if not service.is_repo():
            return {"is_repo": False, "branch": None, "changed_files": [], "clean": True}
        status = service.status()
        status["is_repo"] = True
        return status

    @app.get("/api/git/diff")
    async def git_diff(path: str | None = None) -> dict[str, object]:
        service = GitService(hydra_project_root())
        if not service.is_repo():
            return {"is_repo": False, "diff": ""}
        return {"is_repo": True, "diff": service.diff(path)}

    @app.get("/api/git/log")
    async def git_log(limit: int = 50) -> dict[str, object]:
        service = GitService(hydra_project_root())
        if not service.is_repo():
            return {"is_repo": False, "commits": []}
        return {"is_repo": True, "commits": service.log(limit=limit), "branch": service.current_branch()}

    @app.get("/api/git/suggest-commits")
    async def git_suggest_commits() -> dict[str, object]:
        service = GitService(hydra_project_root())
        if not service.is_repo():
            return {"is_repo": False, "suggestions": []}
        status = service.status()
        return {"is_repo": True, "suggestions": suggest_grouped_commits(status["changed_files"])}

    @app.post("/api/git/init")
    async def git_init(request: GitInitRequest, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        root = hydra_project_root()
        service = GitService(root)
        if service.is_repo():
            return {"action": "reuse", "reason": "Existing Git repository detected.", "branch": service.current_branch()}
        # Existing non-Git folder: never silently init; require explicit confirm.
        decision = evaluate_git_init(root, created_by_hydralab=False, git_enabled=True)
        if decision.action == "ask" and not request.confirm:
            return {"action": "ask", "reason": decision.reason, "initialized": False}
        service._run(["init"])
        repo = Repository(session)
        await repo.add_event("git.init", "Initialized Git repository after explicit confirmation")
        return {"action": "init", "initialized": True, "branch": service.current_branch()}

    @app.post("/api/git/commit")
    async def git_commit(request: GitCommitRequest, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        service = GitService(hydra_project_root())
        try:
            result = service.commit(request.message, request.paths)
        except GitError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        repo = Repository(session)
        await repo.add_event("git.commit", f"Committed: {request.message}")
        return result

    @app.post("/api/git/restore")
    async def git_restore(request: GitRestoreRequest, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        settings = await repo.list_settings()
        auto_checkpoint = str(settings.get("auto_checkpoint", "false")).lower() == "true"
        service = GitService(hydra_project_root())
        try:
            result = service.restore_previous_version(request.path, ref=request.ref, auto_checkpoint=auto_checkpoint)
        except GitError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        await repo.add_event("git.restore", f"Restored {request.path} to {request.ref}")
        return result

    @app.post("/api/git/destructive")
    async def git_destructive(request: GitDestructiveRequest, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        service = GitService(hydra_project_root())
        try:
            result = service.destructive(request.subcommand, request.args, approved=request.approved)
        except GitError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        repo = Repository(session)
        await repo.add_event("git.destructive", f"Ran approved destructive op: {request.subcommand}")
        return result

    # -- Safe command console (HL-SAFE-02 / HL-SAFE-03) ----------------------
    @app.post("/api/console/run")
    async def console_run(request: ConsoleRunRequest, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        repo = Repository(session)
        service = ConsoleService(hydra_project_root(), offline=_offline_posture())
        approved_setting = (await repo.get_setting("console_verify_approved")) or {}
        approved = set(filter(None, str(approved_setting.get("value", "")).split(","))) if approved_setting else set()
        result = service.run(
            request.command,
            trigger=request.trigger,
            approve=request.approve,
            approved_commands=approved,
        )
        if result.get("approved_now"):
            approved.add(str(result["approved_now"]))
            await repo.save_setting("console_verify_approved", ",".join(sorted(approved)))
        await repo.add_event("console.run", f"Console command '{result.get('command')}' -> {result.get('status')}")
        return result

    @app.get("/api/console/allowlist")
    async def console_allowlist() -> dict[str, object]:
        from hydra.services.console import GIT_CONSOLE_COMMANDS, VERIFICATION_COMMANDS
        return {
            "git_inspection": sorted(GIT_CONSOLE_COMMANDS.keys()),
            "verification": sorted(VERIFICATION_COMMANDS),
            "offline": _offline_posture(),
        }

    # -- Exports & backup (HL-EXPORT-01..06) ---------------------------------
    @app.get("/api/export/options")
    async def export_options_endpoint() -> dict[str, object]:
        return export_options()

    @app.post("/api/export/citations")
    async def export_citations(request: CitationExportRequest, session: AsyncSession = Depends(get_session)) -> PlainTextResponse:
        repo = Repository(session)
        sources = await repo.list_sources()
        if request.source_ids:
            wanted = set(request.source_ids)
            sources = [s for s in sources if s["id"] in wanted]
        serializer = {"bibtex": to_bibtex, "csl": to_csl_json, "ris": to_ris}[request.format]
        media = "application/json" if request.format == "csl" else "text/plain"
        return PlainTextResponse(serializer(sources), media_type=media)

    @app.post("/api/export/project-zip")
    async def export_project_zip(request: ProjectZipRequest, session: AsyncSession = Depends(get_session)) -> StreamingResponse:
        options = ExportOptions(
            include_chats=request.include_chats,
            include_agent_logs=request.include_agent_logs,
            include_browser_snapshots=request.include_browser_snapshots,
            include_annotations=request.include_annotations,
        )
        data = build_project_zip(hydra_project_root(), selected_files=request.selected_files, options=options)
        repo = Repository(session)
        await repo.add_event("export.project-zip", "Exported clean project ZIP")
        return StreamingResponse(
            io.BytesIO(data),
            media_type="application/zip",
            headers={"Content-Disposition": "attachment; filename=hydralab_project.zip"},
        )

    @app.post("/api/backup/sqlite")
    async def backup_sqlite(request: BackupRequest, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        from hydra.database.session import get_db_url

        db_url = get_db_url()
        source_db = Path(db_url.removeprefix("sqlite+aiosqlite:///"))
        dest = hydra_project_root() / ".hydralab" / "backups" / f"backup-{int(time.time())}.db"
        result = safe_sqlite_backup(source_db, dest)
        repo = Repository(session)
        await repo.add_event("backup.sqlite", f"SQLite backup created (integrity_ok={result['integrity_ok']})")
        return result

    @app.post("/api/restore")
    async def restore_endpoint(request: RestoreRequest, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        root = hydra_project_root()

        async def _reindex() -> list[str]:
            return await reindex_notes_from_canonical_files(root, session, request.project_id)

        result = await restore_project(root, reindex=_reindex if request.reindex else None)
        repo = Repository(session)
        await repo.add_event("restore.project", f"Restored project reindexed={request.reindex}")
        return result

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

def write_chat_artifact(project_root: Path, chat: dict[str, Any], messages: list[dict[str, Any]]) -> Path:
    """Write a readable Markdown snapshot under work/chats/ (non-authoritative export).

    Editing this file MUST NOT mutate SQLite (HL-ASSIST-04); it embeds chat id, message
    range, timestamp and model/provider for traceability only.
    """
    chats_dir = project_root / "work" / "chats"
    chats_dir.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(c for c in str(chat.get("name") or "chat") if c.isalnum() or c in (" ", "_", "-")).strip() or "chat"
    stamp = int(time.time())
    path = chats_dir / f"{safe_name}-{stamp}.md"
    ids = [m["id"] for m in messages]
    model = next((m.get("model") for m in messages if m.get("model")), "")
    provider = next((m.get("provider") for m in messages if m.get("provider")), "")
    lines = [
        "---",
        f"chat_id: {chat.get('id')}",
        f"chat_name: {chat.get('name')}",
        f"message_range: {ids[0] if ids else ''}..{ids[-1] if ids else ''}",
        f"message_count: {len(messages)}",
        f"exported_at: {stamp}",
        f"model: {model}",
        f"provider: {provider}",
        "authoritative: false",
        "note: Snapshot only. Editing this file does not change the canonical SQLite chat.",
        "---",
        "",
        f"# {chat.get('name')}",
        "",
    ]
    for message in messages:
        lines.append(f"## {message.get('role')}")
        lines.append("")
        lines.append(str(message.get("content") or ""))
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def motivating_excerpt(text: str) -> str:
    normalized = " ".join(text.split())
    match = re_search_case_insensitive(r"[^.?!]*save this as a source[^.?!]*[.?!]?", normalized)
    return (match or normalized)[:500]


def _secret_store() -> SecretStore:
    if os.environ.get("HYDRALAB_SECRET_STORE") == "memory" or os.environ.get("PYTEST_CURRENT_TEST"):
        return _MEMORY_SECRET_STORE
    return KeyringSecretStore()


def _validate_secret_ref(provider: str, value: str) -> None:
    if not _is_secret_ref(value):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Provider '{provider}' credentials must be saved as keychain:* or env:* references. "
                "Send raw secrets to POST /api/settings/provider/secret first."
            ),
        )


def _is_secret_ref(value: str) -> bool:
    if not value:
        return False
    if value.startswith(RAW_SECRET_PREFIXES):
        return False
    if value.startswith("keychain:"):
        suffix = value.removeprefix("keychain:")
        return suffix.startswith("hydralab/") and bool(suffix.removeprefix("hydralab/"))
    if value.startswith("env:"):
        name = value.removeprefix("env:")
        return name.replace("_", "").isalnum() and name[0].isalpha()
    return False


def _provider_settings_with_resolution(settings: list[dict[str, Any]], store: SecretStore) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in settings:
        provider = str(row.get("provider") or "")
        ref = str(row.get("api_key_ref") or row.get("secret_ref") or "")
        copied = dict(row)
        copied["api_key_ref"] = ref
        copied["secret_ref"] = ref or None
        copied["resolved"] = _secret_ref_resolved(ref, provider, store)
        result.append(copied)
    return result


def _resolve_discovery_posture(request: SourceDiscoveryRequest) -> dict[str, bool]:
    settings = load_settings(app_data_root() / "settings.toml").data
    privacy = settings.get("privacy", {})
    general = settings.get("general", {})
    offline_only = bool(privacy.get("offline_only") or general.get("offline_only") or request.offline_only)
    stored_scholarly = bool(privacy.get("scholarly_apis_enabled", True))
    scholarly_apis_enabled = bool(stored_scholarly and request.scholarly_apis_enabled and not offline_only)
    return {"offline_only": offline_only, "scholarly_apis_enabled": scholarly_apis_enabled}


def _offline_posture() -> bool:
    settings = load_settings(app_data_root() / "settings.toml").data
    privacy = settings.get("privacy", {})
    general = settings.get("general", {})
    return bool(privacy.get("offline_only") or general.get("offline_only"))


def _discovery_limiter_from_settings() -> ProviderRateLimiter:
    settings = load_settings(app_data_root() / "settings.toml").data
    providers = settings.get("providers", {})
    aggregate = int(providers.get("aggregate_rate", providers.get("aggregate_requests_per_second", 3)) or 3)
    rates: dict[str, float] = {}
    configured_rates = providers.get("rates", {})
    if isinstance(configured_rates, dict):
        for provider, rate in configured_rates.items():
            try:
                rates[str(provider)] = float(rate)
            except (TypeError, ValueError):
                continue
    accounts = providers.get("accounts", {})
    if isinstance(accounts, dict):
        for provider, account in accounts.items():
            if isinstance(account, dict) and "rate" in account:
                try:
                    rates[str(provider)] = float(account["rate"])
                except (TypeError, ValueError):
                    continue
    return ProviderRateLimiter(aggregate_requests_per_second=aggregate, provider_requests_per_second=rates)


def _secret_ref_resolved(ref: str, provider: str, store: SecretStore) -> bool:
    if ref.startswith("env:"):
        return os.environ.get(ref.removeprefix("env:")) is not None
    if ref == f"keychain:hydralab/{provider}":
        return ProviderSecretService(store).has_provider_secret(provider, "api_key")
    return False


def _hash_bridge_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _runtime_descriptor_path(root: Path) -> Path:
    return Path(root) / "runtime" / "backend.json"


def _ensure_runtime_nonce(root: Path) -> dict[str, Any]:
    path = _runtime_descriptor_path(root)
    try:
        descriptor = json.loads(path.read_text()) if path.exists() else {}
    except json.JSONDecodeError:
        descriptor = {}
    now = time.time()
    if not descriptor.get("handshake_nonce"):
        descriptor["handshake_nonce"] = secrets.token_urlsafe(32)
        descriptor["handshake_nonce_issued_at"] = now
    descriptor.setdefault("host", HYDRALAB_BIND_HOST)
    descriptor.setdefault("port", int(os.environ.get("HYDRALAB_PORT", str(DEFAULT_PORT))))
    descriptor.setdefault("scheme", "http")
    descriptor.setdefault("base_url", f"http://{descriptor['host']}:{descriptor['port']}")
    descriptor.setdefault("api_version", "v1")
    descriptor.setdefault("started_at", now)
    descriptor.setdefault("health_url", f"{descriptor['base_url']}/healthz")
    _write_owner_only_json(path, descriptor)
    return descriptor


def _consume_runtime_nonce(root: Path, presented_nonce: str) -> bool:
    descriptor = _ensure_runtime_nonce(root)
    expected = str(descriptor.get("handshake_nonce") or "")
    issued_at = float(descriptor.get("handshake_nonce_issued_at") or 0)
    if not expected or time.time() - issued_at > BRIDGE_NONCE_TTL_SECONDS:
        _rotate_runtime_nonce(root, descriptor)
        return False
    if not hmac.compare_digest(expected, presented_nonce):
        return False
    _rotate_runtime_nonce(root, descriptor)
    return True


def _rotate_runtime_nonce(root: Path, descriptor: dict[str, Any] | None = None) -> str:
    descriptor = descriptor or _ensure_runtime_nonce(root)
    nonce = secrets.token_urlsafe(32)
    descriptor["handshake_nonce"] = nonce
    descriptor["handshake_nonce_issued_at"] = time.time()
    _write_owner_only_json(_runtime_descriptor_path(root), descriptor)
    return nonce


def _write_owner_only_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(payload, handle, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        os.chmod(path, 0o600)

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


def is_project_tree_excluded(relative_path: Path) -> bool:
    parts = relative_path.parts
    if not parts:
        return False
    if parts[0] in {".git", "__pycache__", ".pytest_cache", ".mypy_cache", "node_modules", ".venv"}:
        return True
    if parts[0] == ".hydralab" and len(parts) > 1 and parts[1] in {"cache", "temp", "runtime"}:
        return True
    return False


def project_tree_index_status(relative_path: Path, *, is_dir: bool) -> str:
    parts = relative_path.parts
    suffix = relative_path.suffix.lower()
    if parts and parts[0] == ".hydralab":
        return "excluded"
    if any(part in {"code", "browser", "chats"} for part in parts):
        return "needs-consent" if is_dir else "excluded"
    if suffix in {".md", ".markdown", ".pdf", ".docx", ".bib", ".ris", ".json", ".yaml", ".yml", ".txt"}:
        return "indexed"
    return "needs-consent" if is_dir else "excluded"


def write_uploaded_original(project_root: Path, filename: str, raw: bytes) -> Path:
    safe_name = "".join(char for char in filename if char.isalnum() or char in {".", "-", "_"}).strip(".") or "source"
    digest = sha256_bytes(raw)[:12]
    target = project_root / "sources" / "originals" / f"{digest}-{safe_name}"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    return target


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def annotation_to_api(annotation: Annotation) -> dict[str, object]:
    return {
        "sidecar_record_id": annotation.sidecar_record_id,
        "source_id": annotation.source_id,
        "page": annotation.page,
        "text": annotation.text,
        "quad_points": json.loads(annotation.quad_points or "[]"),
        "bbox": json.loads(annotation.bbox or "{}"),
        "type": annotation.type,
        "linked_claim_ids": json.loads(annotation.linked_claim_ids or "[]"),
        "linked_note_ids": json.loads(annotation.linked_note_ids or "[]"),
        "color": annotation.color,
        "rev": annotation.rev,
        "content_hash": annotation.content_hash,
        "link_state": annotation.link_state,
        "trust_origin": annotation.trust_origin,
    }


def extract_claim_suggestions(text: str, request: "ClaimDetectRequest") -> list[dict[str, object]]:
    """Heuristic, suggestion-only claim candidate extraction.

    Untrusted text is treated as data, not instructions (DEC-11): this only ever
    proposes candidates and never commits a claim by itself.
    """
    import re as _re

    sentences = [segment.strip() for segment in _re.split(r"(?<=[.!?])\s+", text) if segment.strip()]
    suggestions: list[dict[str, object]] = []
    for sentence in sentences:
        words = sentence.split()
        if len(words) < 4:
            continue
        confidence = min(0.9, 0.4 + 0.02 * len(words))
        suggestions.append(
            {
                "claim_text": sentence,
                "origin_quote": sentence,
                "origin_ref": request.origin_ref,
                "location_type": request.location_type,
                "location_id": request.location_id,
                "extraction_confidence": round(confidence, 3),
                "extraction_mode": "suggested",
                "user_selected": False,
            }
        )
    return suggestions


def _resolve_default_citation_style() -> str:
    try:
        settings = load_settings(app_data_root() / "settings.toml").data
    except Exception:
        return DEFAULT_STYLE_ID
    citation = settings.get("citation", {}) if isinstance(settings, dict) else {}
    workspace = settings.get("workspace", {}) if isinstance(settings, dict) else {}
    for source in (citation, workspace):
        if isinstance(source, dict):
            value = source.get("default_citation_style") or source.get("citation_style")
            if isinstance(value, str) and value.strip():
                return value.strip().lower()
    return DEFAULT_STYLE_ID


def _writing_global_defaults() -> dict[str, object]:
    try:
        settings = load_settings(app_data_root() / "settings.toml").data
    except Exception:
        settings = None
    return global_defaults_from_settings(settings)


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
