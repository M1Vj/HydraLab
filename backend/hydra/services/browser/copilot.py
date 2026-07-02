from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.agents.approvals import ApprovalService
from hydra.agents.contracts import ApprovalStatus
from hydra.agents.policy import COPILOT, Outcome, WriteRequest, evaluate_write, normalize_mode
from hydra.browser_bridge import detect_source_metadata, source_id_from_metadata
from hydra.database.repository import Repository
from hydra.services.browser.actions import (
    ACTION_BY_NAME,
    BROWSER_COPILOT_ACTIONS,
    TRUST_LEVEL_UNTRUSTED,
    BrowserActionRequest,
    browser_copilot_tool_descriptors,
)
from hydra.services.browser.repository import BrowserActionLogRepository, BrowserHostPermissionRepository


@dataclass
class BrowserActionResult:
    outcome: str
    reason: str = ""
    prompt: str = ""
    approval_id: str | None = None
    action: str = ""
    host: str = ""
    log: dict[str, Any] | None = None
    review_item: dict[str, Any] | None = None
    artifact: dict[str, Any] | None = None
    public_log_text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


def motivating_excerpt(text: str, limit: int = 280) -> str:
    compact = re.sub(r"\s+", " ", text or "").strip()
    return compact[:limit]


class BrowserCopilotService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = Repository(session)
        self.permissions = BrowserHostPermissionRepository(session)
        self.logs = BrowserActionLogRepository(session)
        self.approvals = ApprovalService(session)

    def browser_modes(self) -> list[dict[str, Any]]:
        return [
            {"id": "passive", "label": "Passive", "enabled": True},
            {"id": "copilot", "label": "Co-pilot", "enabled": True},
        ]

    def action_descriptors(self, host: str) -> list[dict[str, Any]]:
        return browser_copilot_tool_descriptors(host)

    def task_groups(self, tabs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[str, dict[str, Any]] = {}
        for tab in tabs:
            group_id = str(tab.get("task_group_id") or "ungrouped")
            label = str(tab.get("task_group_label") or "Ungrouped")
            grouped.setdefault(group_id, {"id": group_id, "label": label, "tabs": []})["tabs"].append(tab)
        return list(grouped.values())

    async def propose(self, request: BrowserActionRequest) -> BrowserActionResult:
        mode = normalize_mode(request.mode)
        action = request.action_descriptor()
        host = request.resolved_host()

        if mode != COPILOT:
            return BrowserActionResult(
                outcome="refused",
                reason="browser co-pilot actions run only under copilot mode",
                action=request.action,
                host=host,
                public_log_text="browser action refused",
            )

        if request.context and request.context.excluded():
            return BrowserActionResult(
                outcome="refused",
                reason="excluded browser context cannot be captured or logged",
                action=request.action,
                host=host,
                public_log_text="excluded browser context refused",
            )

        if not request.user_triggered:
            routed = await self.handle_untrusted_page_proposal(
                project_id=request.project_id,
                url=request.url,
                page_text=request.page_text,
                proposed_action=request.action,
                mode=mode,
            )
            return routed

        decision = evaluate_write(
            WriteRequest(
                mode=mode,
                action_kind=f"browser.{request.action}",
                target_kind="browser_host",
                target_ref=host,
                trust_origin="user",
                justification_trust="user",
            )
        )
        if decision.outcome == Outcome.BLOCKED.value:
            return BrowserActionResult(outcome="refused", reason=decision.reason, action=request.action, host=host)

        permission = await self.permissions.get(request.project_id, host)
        if permission["state"] == "blocked":
            return BrowserActionResult(
                outcome="refused",
                reason=f"host {host} is blocked",
                action=request.action,
                host=host,
                public_log_text="host blocked",
            )

        if permission["state"] == "always_allow_host":
            artifact = await self._execute(request)
            log = await self.logs.append(
                project_id=request.project_id,
                action=request.action,
                host=host,
                mode=mode,
                approval_result="always_allow_host",
                target_url=request.url,
                task_group_id=request.task_group_id,
                payload={"task_group_label": request.task_group_label},
            )
            return BrowserActionResult(outcome="applied", action=request.action, host=host, log=log, artifact=artifact)

        approval = await self.approvals.request(
            action_kind=f"browser.{request.action}",
            mode=mode,
            project_id=request.project_id,
            target_kind="browser_host",
            target_ref=host,
            trust_origin="user",
            summary=f"{action.verb} from {host}?",
            reason="co-pilot browser action requires per-item approval",
            payload={
                "project_id": request.project_id,
                "action": request.action,
                "url": request.url,
                "title": request.title,
                "page_text": request.page_text,
                "host": host,
                "task_group_id": request.task_group_id,
                "task_group_label": request.task_group_label,
            },
        )
        return BrowserActionResult(
            outcome="approval_required",
            prompt=f"{action.verb} from {host}?",
            approval_id=approval.id,
            action=request.action,
            host=host,
        )

    async def resolve_approval(self, approval_id: str, *, decision: str) -> BrowserActionResult:
        approval = await self.approvals.get(approval_id)
        if approval is None:
            return BrowserActionResult(outcome="missing", reason="approval not found")
        if not approval.action_kind.startswith("browser."):
            return BrowserActionResult(outcome="refused", reason="not a browser approval")

        normalized = str(decision or "").strip().lower()
        payload = json.loads(approval.payload_json or "{}")
        request = BrowserActionRequest(
            project_id=payload["project_id"],
            action=payload["action"],
            url=payload["url"],
            title=payload.get("title") or "",
            page_text=payload.get("page_text") or "",
            host=payload.get("host") or approval.target_ref or "",
            mode=approval.mode,
            task_group_id=payload.get("task_group_id"),
            task_group_label=payload.get("task_group_label") or "",
            user_triggered=True,
        )

        if normalized not in {"approve", "approved", "accept", "accepted"}:
            await self.approvals.resolve(approval_id, decision="rejected")
            return BrowserActionResult(outcome="rejected", reason="approval rejected", approval_id=approval_id)

        artifact: dict[str, Any] = {}

        async def apply_fn() -> None:
            nonlocal artifact
            artifact = await self._execute(request)

        result = await self.approvals.resolve(approval_id, decision="approved", apply_fn=apply_fn)
        if not result.applied:
            return BrowserActionResult(outcome=result.status, reason=result.reason, approval_id=approval_id)

        log = await self.logs.append(
            project_id=request.project_id,
            action=request.action,
            host=request.resolved_host(),
            mode=request.mode,
            approval_result=ApprovalStatus.APPROVED.value,
            target_url=request.url,
            task_group_id=request.task_group_id,
            payload={"task_group_label": request.task_group_label},
        )
        return BrowserActionResult(outcome="applied", approval_id=approval_id, action=request.action, host=request.resolved_host(), log=log, artifact=artifact)

    async def handle_untrusted_page_proposal(
        self,
        *,
        project_id: str,
        url: str,
        page_text: str,
        proposed_action: str,
        mode: str,
    ) -> BrowserActionResult:
        decision = evaluate_write(
            WriteRequest(
                mode=mode,
                action_kind=f"browser.{proposed_action}",
                target_kind="browser_page",
                target_ref=url,
                trust_origin=TRUST_LEVEL_UNTRUSTED,
                justification_trust=TRUST_LEVEL_UNTRUSTED,
            )
        )
        item = await self.repo.create_review_item(
            {
                "project_id": project_id,
                "item_type": "browser-untrusted-proposal",
                "title": "Review browser page proposal",
                "summary": decision.reason,
                "origin_type": "browser",
                "origin_id": url,
                "target_type": "browser-action",
                "payload": {
                    "proposed_action": proposed_action,
                    "origin_url": url,
                    "trust_level": TRUST_LEVEL_UNTRUSTED,
                    "motivating_excerpt": motivating_excerpt(page_text),
                },
            }
        )
        return BrowserActionResult(outcome="review_inbox", reason=decision.reason, review_item=item)

    async def _execute(self, request: BrowserActionRequest) -> dict[str, Any]:
        if request.action not in ACTION_BY_NAME:
            raise ValueError(f"unknown browser action: {request.action}")
        metadata = detect_source_metadata(request.url, request.title, request.page_text)
        metadata["trust_level"] = TRUST_LEVEL_UNTRUSTED
        if request.action == "save-source":
            source_metadata = {
                **metadata,
                "origin_url": request.url,
                "trust_level": TRUST_LEVEL_UNTRUSTED,
                "copilot_action": request.action,
            }
            source = await self.repo.upsert_source(
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
            return {"source": source}
        if request.action == "create-note":
            note = await self.repo.add_note(request.title or request.url, request.page_text[:20000])
            return {"note": note}
        if request.action in {"save-snapshot", "extract-metadata", "search"}:
            return {"metadata": metadata, "url": request.url, "title": request.title}
        raise ValueError(f"unsupported browser action: {request.action}")
