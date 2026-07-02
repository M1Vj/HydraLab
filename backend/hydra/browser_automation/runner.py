"""Autonomous browser research runner wired through Phase-3 safety contracts."""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.agents.contracts import RunStatus, StepStatus
from hydra.agents.policy import normalize_mode
from hydra.agents.runs import RunRepository
from hydra.browser_automation.capture import BrowserCaptureService
from hydra.browser_automation.driver import BrowserResearchDriver, FakeBrowserResearchDriver
from hydra.browser_automation.policy import (
    BrowserAutomationContext,
    BrowserAutomationPolicy,
    HOST_PROMPT_CHOICES,
    host_for_url,
)
from hydra.database.models import AgentRun
from hydra.services.browser.repository import BrowserActionLogRepository

RECIPE_ID = "autonomous-browser-research"
SUCCEEDED = "succeeded"


@dataclass(frozen=True)
class BrowserResearchStep:
    url: str
    title: str = ""
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BrowserRunRequest:
    project_id: str
    mode: str
    task_id: str
    task_label: str
    steps: list[BrowserResearchStep]
    full_access_enabled: bool = False


@dataclass(frozen=True)
class BrowserResearchRunResult:
    run_id: str
    state: str
    host_prompt: dict[str, Any] | None = None
    budget_prompt: list[str] | None = None
    rate_limit_state: str | None = None


class AutonomousBrowserResearchRunner:
    def __init__(
        self,
        session: AsyncSession,
        *,
        driver: BrowserResearchDriver | None = None,
        artifact_root: Path | None = None,
        token_budget: int = 60_000,
        wall_clock_seconds: int = 120,
    ) -> None:
        self.session = session
        self.repo = RunRepository(session)
        self.policy = BrowserAutomationPolicy(session)
        self.logs = BrowserActionLogRepository(session)
        self.capture = BrowserCaptureService(session, artifact_root=artifact_root)
        self.driver = driver or FakeBrowserResearchDriver({})
        self.token_budget = token_budget
        self.wall_clock_seconds = wall_clock_seconds
        self._cancel_requested = False

    async def start(self, request: BrowserRunRequest) -> BrowserResearchRunResult:
        mode = normalize_mode(request.mode)
        run = await self._create_queued_run(request, mode)
        started = time.monotonic()
        await self._mark_running(run)
        await self.repo.append_step(
            run.id,
            kind="browser.run-started",
            status=StepStatus.RUNNING.value,
            summary=f"Started autonomous browser research for {request.task_label}",
            payload={"task_group_id": request.task_id, "task_group_label": request.task_label},
        )
        await self.driver.open_task_group(task_group_id=request.task_id, task_group_label=request.task_label)

        try:
            for step in request.steps:
                if await self._cancelled(run.id):
                    return BrowserResearchRunResult(run_id=run.id, state=RunStatus.CANCELLED.value)
                decision = await self.policy.evaluate_navigation(
                    BrowserAutomationContext(
                        project_id=request.project_id,
                        url=step.url,
                        task_group_id=request.task_id,
                        **step.context,
                    )
                )
                if decision.status == "needs-approval":
                    await self._pause_for_host(run.id, decision.host)
                    return BrowserResearchRunResult(
                        run_id=run.id,
                        state=RunStatus.PAUSED.value,
                        host_prompt={"host": decision.host, "choices": list(HOST_PROMPT_CHOICES)},
                    )
                if decision.status == "blocked":
                    await self.capture.record_host_blocked(
                        project_id=request.project_id,
                        run_id=run.id,
                        url=step.url,
                        host=decision.host,
                        reason=decision.reason,
                    )
                    await self.logs.append(
                        project_id=request.project_id,
                        action="host-blocked",
                        host=decision.host,
                        mode=mode,
                        approval_result="blocked",
                        target_url=step.url,
                        task_group_id=request.task_id,
                        trust_level="untrusted-external",
                        payload={"reason": decision.reason, "run_id": run.id},
                    )
                    await self.repo.append_step(
                        run.id,
                        kind="browser.host-blocked",
                        status=StepStatus.DENIED.value,
                        summary=f"host-blocked: {decision.host}",
                        trust_origin="untrusted-external",
                        payload={"host": decision.host, "url": step.url, "reason": decision.reason},
                    )
                    continue
                if decision.status == "hard-blocked":
                    await self.repo.append_step(
                        run.id,
                        kind="browser.hard-blocked",
                        status=StepStatus.DENIED.value,
                        summary=decision.reason,
                        trust_origin="untrusted-external",
                        payload={"url": step.url, "host": decision.host},
                    )
                    continue
                if decision.status == "site-blocks-automation":
                    await self.repo.append_step(
                        run.id,
                        kind="browser.official-api-fallback",
                        status=StepStatus.COMPLETED.value,
                        summary=decision.reason,
                        payload={"provider": decision.fallback_provider, "url": step.url},
                    )
                    continue

                page = await self.driver.navigate(step.url, task_group_id=request.task_id)
                if getattr(self.driver, "cancel_after_navigation", False):
                    await self.cancel(run.id)
                if await self._cancelled(run.id):
                    return BrowserResearchRunResult(run_id=run.id, state=RunStatus.CANCELLED.value)
                # Re-evaluate the LANDED page (post-redirect host + sensitive DOM
                # fields) before any capture. The pre-navigation decision only
                # covered the declared step.url; a 302 to a blocked/unapproved
                # host, or a login/payment page, must never reach capture or the
                # provider promotion path (03-06 fix).
                if await self._discard_if_landing_blocked(request, run.id, mode, step, page, decision.host):
                    continue
                if await self._budget_blocked(run.id, started, page.text):
                    return BrowserResearchRunResult(
                        run_id=run.id,
                        state="budget_blocked",
                        budget_prompt=["continue", "raise", "stop"],
                    )
                event = await self.capture.capture_page(
                    project_id=request.project_id,
                    run_id=run.id,
                    mode=mode,
                    task_group_id=request.task_id,
                    task_group_label=request.task_label,
                    page=page,
                )
                await self.logs.append(
                    project_id=request.project_id,
                    action="capture",
                    host=decision.host,
                    mode=mode,
                    approval_result="approved",
                    target_url=page.url,
                    task_group_id=request.task_id,
                    trust_level="untrusted-external",
                    payload={
                        "run_id": run.id,
                        "origin_event_id": event["id"],
                        "task_group_label": request.task_label,
                    },
                )
                await self.capture.route_untrusted_promotion(
                    project_id=request.project_id,
                    run_id=run.id,
                    mode=mode,
                    url=page.url,
                    page_text=page.text,
                    proposed_action="save-source",
                    origin_event_id=event["id"],
                )
                await self.repo.append_step(
                    run.id,
                    kind="browser.capture",
                    status=StepStatus.COMPLETED.value,
                    summary=f"Captured {page.url}",
                    tokens=_estimate_tokens(page.text),
                    trust_origin="untrusted-external",
                    payload={"origin_event_id": event["id"], "captured_text_ref": event["captured_text_ref"]},
                )
            await self._succeed(run.id, request)
            return BrowserResearchRunResult(run_id=run.id, state=SUCCEEDED)
        except Exception as exc:
            await self.repo.append_step(
                run.id,
                kind="browser.failed",
                status=StepStatus.FAILED.value,
                summary=str(exc),
            )
            await self.repo.complete_run(run.id, status=RunStatus.FAILED.value)
            return BrowserResearchRunResult(run_id=run.id, state=RunStatus.FAILED.value)
        finally:
            await self.driver.close_task_group(request.task_id)

    async def _discard_if_landing_blocked(
        self,
        request: BrowserRunRequest,
        run_id: str,
        mode: str,
        step: BrowserResearchStep,
        page: Any,
        declared_host: str,
    ) -> bool:
        """Re-check the landed page; discard (never capture) if it is not allowed."""
        landed_url = getattr(page, "url", "")
        if not landed_url:
            # Fail closed: without a verifiable landed URL we cannot confirm the
            # host is allowed, so discard rather than fall back to the (approved)
            # declared URL and capture unknown content (03-06 hardening).
            await self._record_landing_block(
                request, run_id, mode, step, host=host_for_url(step.url), landed_url=step.url,
                reason="landed page reported no URL; cannot verify host", redirected=True,
            )
            return True
        decision = await self.policy.evaluate_navigation(
            BrowserAutomationContext(
                project_id=request.project_id,
                url=landed_url,
                task_group_id=request.task_id,
                has_password_field=bool(getattr(page, "has_password_field", False)),
                has_payment_field=bool(getattr(page, "has_payment_field", False)),
            )
        )
        if decision.allowed:
            return False
        redirected = host_for_url(landed_url) != declared_host
        if decision.status == "needs-approval":
            reason = f"post-redirect host {decision.host} was not pre-approved for this run"
        else:
            reason = decision.reason
        await self._record_landing_block(
            request,
            run_id,
            mode,
            step,
            host=decision.host,
            landed_url=landed_url,
            reason=reason,
            redirected=redirected,
            status=decision.status,
        )
        return True

    async def _record_landing_block(
        self,
        request: BrowserRunRequest,
        run_id: str,
        mode: str,
        step: BrowserResearchStep,
        *,
        host: str,
        landed_url: str,
        reason: str,
        redirected: bool,
        status: str = "blocked",
    ) -> None:
        kind = "browser.redirect-blocked" if redirected else "browser.landing-blocked"
        action = "redirect-blocked" if redirected else "landing-blocked"
        await self.capture.record_host_blocked(
            project_id=request.project_id,
            run_id=run_id,
            url=landed_url,
            host=host,
            reason=reason,
        )
        await self.logs.append(
            project_id=request.project_id,
            action=action,
            host=host,
            mode=mode,
            approval_result="blocked",
            target_url=landed_url,
            task_group_id=request.task_id,
            trust_level="untrusted-external",
            payload={
                "reason": reason,
                "run_id": run_id,
                "declared_host": host_for_url(step.url),
                "declared_url": step.url,
                "status": status,
            },
        )
        await self.repo.append_step(
            run_id,
            kind=kind,
            status=StepStatus.DENIED.value,
            summary=f"discarded landed page: {reason}",
            trust_origin="untrusted-external",
            payload={
                "host": host,
                "landed_url": landed_url,
                "declared_url": step.url,
                "reason": reason,
                "status": status,
            },
        )

    async def cancel(self, run_id: str) -> None:
        self._cancel_requested = True
        await self.repo.cancel_run(run_id, stop_reason="cancelled by user")

    async def _create_queued_run(self, request: BrowserRunRequest, mode: str) -> AgentRun:
        run = AgentRun(
            project_id=request.project_id,
            mode=mode,
            recipe=RECIPE_ID,
            inputs_ref=json.dumps(
                {
                    "task_id": request.task_id,
                    "task_label": request.task_label,
                    "step_count": len(request.steps),
                },
                sort_keys=True,
            ),
            status=RunStatus.QUEUED.value,
        )
        self.session.add(run)
        await self.session.commit()
        await self.session.refresh(run)
        await self.repo.append_step(
            run.id,
            kind="browser.run-queued",
            status=StepStatus.PENDING.value,
            summary="queued autonomous browser research",
        )
        return run

    async def _mark_running(self, run: AgentRun) -> None:
        run.status = RunStatus.RUNNING.value
        run.started_at = datetime.now(timezone.utc)
        run.updated_at = run.started_at
        self.session.add(run)
        await self.session.commit()

    async def _pause_for_host(self, run_id: str, host: str) -> None:
        await self.repo.append_step(
            run_id,
            kind="browser.host-approval-required",
            status=StepStatus.PENDING.value,
            summary=f"Host {host} requires first-use approval",
            payload={"host": host, "choices": list(HOST_PROMPT_CHOICES)},
        )
        await self.repo.pause_run(run_id, True)

    async def _budget_blocked(self, run_id: str, started: float, text: str) -> bool:
        elapsed = time.monotonic() - started
        tokens = _estimate_tokens(text)
        if tokens < self.token_budget and elapsed < self.wall_clock_seconds:
            return False
        await self.repo.append_step(
            run_id,
            kind="budget.blocked",
            status=RunStatus.BLOCKED.value,
            summary="budget ceiling reached; choose continue, raise the ceiling, or stop",
            payload={"state": "budget_blocked", "choices": ["continue", "raise", "stop"]},
        )
        await self.repo.block_on_budget(run_id)
        return True

    async def _cancelled(self, run_id: str) -> bool:
        if self._cancel_requested:
            return True
        current = await self.session.get(AgentRun, run_id, populate_existing=True)
        return bool(current and current.status == RunStatus.CANCELLED.value)

    async def _succeed(self, run_id: str, request: BrowserRunRequest) -> None:
        run = await self.session.get(AgentRun, run_id)
        if run is None or run.status == RunStatus.CANCELLED.value:
            return
        run.status = SUCCEEDED
        run.ended_at = datetime.now(timezone.utc)
        run.updated_at = run.ended_at
        run.artifacts = json.dumps(
            [
                {
                    "id": f"{run_id}:task-group",
                    "kind": "browser-task-group",
                    "ref": request.task_id,
                    "summary": request.task_label,
                }
            ],
            sort_keys=True,
        )
        self.session.add(run)
        await self.session.commit()


def _estimate_tokens(text: str) -> int:
    return max(1, math.ceil(len(text or "") / 4))
