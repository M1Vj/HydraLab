"""Experiment run lifecycle: propose -> approve -> checkpoint -> sandbox -> terminal.

The runner is the single writer for run records. It reuses the 03-01 contracts
verbatim — ``CheckpointService`` for the pre-run checkpoint and rollback,
``ApprovalService`` for the per-run approval, ``AuditLedger`` for a forensic
entry on every start/pause/cancel/rollback, and ``ActionGate`` (through
``ExperimentExecutionGate``) for the governed proposal. No run is ever
auto-started: execution requires the per-project first-use flag AND an approved
per-run approval; an assistant-initiated run with no approval stays
``awaiting_approval``.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Sequence

from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.agents.approvals import ApprovalService
from hydra.agents.contracts import ApprovalStatus
from hydra.autonomy.audit import AuditLedger
from hydra.autonomy.checkpoints import CheckpointService
from hydra.autonomy.gate import ActionGate
from hydra.compute.registry import BackendNotSelectableError, ComputeRegistry, ResolvedBackend
from hydra.compute.sandbox import LocalSandboxRunner, SandboxError, SandboxProcess, build_default_policy
from hydra.database.models import AgentApproval, AgentCheckpoint, ExperimentRun
from hydra.experiments import models as run_status
from hydra.experiments.approval import ExperimentExecutionGate
from hydra.experiments.logs import RunLogStore
from hydra.services.git.service import GitError, GitService

# Live sandboxed processes keyed by run id, so a concurrent cancel can reach and
# kill the whole process group. Cancelled ids are tracked so a kill-driven exit
# is reported as ``cancelled`` rather than a resource-kill status.
_ACTIVE: dict[str, SandboxProcess] = {}
_CANCELLED: set[str] = set()

METRIC_PREFIX = "##HYDRA_METRIC "


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RunLifecycleError(RuntimeError):
    pass


@dataclass
class ProposalResult:
    run: ExperimentRun
    status: str
    reason: str = ""
    approval_id: Optional[str] = None
    review_item_id: Optional[str] = None


def parse_metrics(stdout: str) -> dict:
    metrics: dict = {}
    for line in stdout.splitlines():
        if line.startswith(METRIC_PREFIX):
            try:
                payload = json.loads(line[len(METRIC_PREFIX):])
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                metrics.update(payload)
    return metrics


class ExperimentRunner:
    def __init__(
        self,
        session: AsyncSession,
        *,
        workspace_root: Optional[Path] = None,
        git: Optional[GitService] = None,
    ) -> None:
        self.session = session
        self.workspace_root = Path(workspace_root or Path.cwd()).resolve()
        self.registry = ComputeRegistry(session)
        self.gate = ExperimentExecutionGate(session)
        self.approvals = ApprovalService(session)
        self.audit = AuditLedger(session)
        self.git = git or GitService(self.workspace_root)
        self.checkpoints = CheckpointService(session, project_root=self.workspace_root, git=self.git)

    # -- proposal (HL-SAFE-17/18) -------------------------------------------
    async def create_run(
        self,
        *,
        project_id: str,
        backend_id: str,
        config: dict,
        label: str = "",
        trust_origin: str = "user",
        justification_trust: str = "user",
        requested_by: str = "user",
    ) -> ProposalResult:
        try:
            resolved = await self.registry.resolve(backend_id)
        except BackendNotSelectableError as exc:
            run = await self._persist_run(
                project_id=project_id,
                backend_id=backend_id,
                label=label,
                config=config,
                status=run_status.STATUS_AWAITING_APPROVAL,
                reason=f"backend disabled: {exc}",
                trust_origin=trust_origin,
                justification_trust=justification_trust,
                requested_by=requested_by,
            )
            await self._audit(run, action="run_code", state="rejected")
            return ProposalResult(run=run, status=run.status, reason=run.reason)

        # Cloud budget precheck BEFORE any gate/spawn (HL-SAFE-17).
        budget = await self.gate.check_cloud_budget(project_id, resolved)
        if not budget.ok:
            run = await self._persist_run(
                project_id=project_id,
                backend_id=backend_id,
                label=label,
                config=config,
                status=run_status.STATUS_AWAITING_APPROVAL,
                reason=budget.reason,
                trust_origin=trust_origin,
                justification_trust=justification_trust,
                requested_by=requested_by,
            )
            await self._audit(run, action="spend_money", state="awaiting_approval")
            return ProposalResult(run=run, status=run.status, reason=budget.reason)

        run = await self._persist_run(
            project_id=project_id,
            backend_id=backend_id,
            label=label,
            config=config,
            status=run_status.STATUS_AWAITING_APPROVAL,
            reason="awaiting per-run approval",
            trust_origin=trust_origin,
            justification_trust=justification_trust,
            requested_by=requested_by,
        )

        # Route the proposal through the shared ActionGate chokepoint. Untrusted
        # provenance lands in the Review Inbox; trusted lands on approval-required.
        action = self.gate.build_governed_action(run, mode="copilot")
        gate = ActionGate(self.session)
        result = await gate.govern(action)
        run.approval_id = result.approval_id
        run.review_item_id = result.review_item_id
        if result.review_item_id:
            run.reason = "untrusted provenance routed to Review Inbox"
        self.session.add(run)
        await self.session.commit()
        await self.session.refresh(run)
        return ProposalResult(
            run=run,
            status=run.status,
            reason=run.reason,
            approval_id=result.approval_id,
            review_item_id=result.review_item_id,
        )

    async def approve_run(self, run_id: str, decision: str = "approve") -> ExperimentRun:
        run = await self._get(run_id)
        if not run.approval_id:
            raise RunLifecycleError("run has no pending approval to resolve")
        await self.approvals.resolve(run.approval_id, decision=decision)
        return run

    # -- execution (HL-SAFE-11/12/13/14/16) ---------------------------------
    async def start_run(self, run_id: str, *, argv: Optional[Sequence[str]] = None) -> ExperimentRun:
        run = await self._get(run_id)
        if not await self.gate.is_execution_enabled(run.project_id):
            run.reason = "execution not enabled for this project"
            await self._save(run)
            raise RunLifecycleError(run.reason)
        if run.review_item_id:
            run.reason = "run is in the Review Inbox; not startable until approved"
            await self._save(run)
            raise RunLifecycleError(run.reason)

        approval = await self._require_approved(run)
        # Consume the approval so it can never authorise a second start (H1).
        approval.status = "consumed"
        approval.decision = "applied"
        self.session.add(approval)
        await self.session.commit()

        resolved = await self.registry.resolve(run.backend_id)

        # Pre-run checkpoint via the 03-01 service; pin its id on the run.
        checkpoint = await self.checkpoints.create(
            project_id=run.project_id,
            run_id=run.id,
            label=f"pre-run {run.label or run.id}",
            target=run.label or run.id,
        )
        run.checkpoint_ref = checkpoint.id
        await self._audit(run, action="run_code", state="applied")

        argv = list(argv) if argv is not None else self._argv_from_config(run)
        await self._execute(run, resolved, argv)
        return run

    async def _execute(self, run: ExperimentRun, resolved: ResolvedBackend, argv: Sequence[str]) -> None:
        scratch = self.workspace_root / ".hydra" / "experiments" / run.id
        scratch.mkdir(parents=True, exist_ok=True)
        policy = build_default_policy(
            workspace_root=self.workspace_root,
            scratch_dir=scratch,
            limits=resolved.limits,
        )
        run.enforcement = policy.filesystem_network_enforcement
        try:
            runner = LocalSandboxRunner(policy, accept_unconfined=self._accept_unconfined(run))
        except SandboxError as exc:
            run.reason = str(exc)
            await self._save(run)
            raise RunLifecycleError(run.reason) from exc
        run.status = run_status.STATUS_RUNNING
        run.started_at = _utcnow()
        await self._save(run)

        process = runner.spawn(argv)
        _ACTIVE[run.id] = process
        try:
            result = await asyncio.to_thread(process.wait)
        finally:
            _ACTIVE.pop(run.id, None)
            shutil.rmtree(scratch, ignore_errors=True)

        logs = RunLogStore(self.session, cap_bytes=policy.log_cap_bytes)
        await logs.append_stream(run.id, "stdout", result.stdout)
        await logs.append_stream(run.id, "stderr", result.stderr)
        metrics = parse_metrics(result.stdout)
        if metrics:
            await logs.record_metrics(run.id, metrics)
            run.metrics_json = json.dumps(metrics, sort_keys=True)

        if run.id in _CANCELLED:
            _CANCELLED.discard(run.id)
            run.status = run_status.STATUS_CANCELLED
            run.reason = "cancelled by user"
        else:
            run.status = result.status
            run.reason = "" if result.status == run_status.STATUS_SUCCEEDED else result.stderr[-500:]
        run.exit_code = result.exit_code
        run.ended_at = _utcnow()
        run.artifact_manifest_json = json.dumps(
            {"scratch": str(scratch), "metrics": metrics, "enforcement": run.enforcement}, sort_keys=True
        )
        await self._save(run)

    # -- pause / cancel (HL-SAFE-15) ----------------------------------------
    async def cancel_run(self, run_id: str) -> ExperimentRun:
        run = await self._get(run_id)
        _CANCELLED.add(run_id)
        process = _ACTIVE.get(run_id)
        if process is not None:
            process.terminate()  # killpg whole group + rmtree scratch: no orphans
            _ACTIVE.pop(run_id, None)
        if run.status not in run_status.TERMINAL_STATUSES:
            run.status = run_status.STATUS_CANCELLED
            run.reason = "cancelled by user"
            run.ended_at = _utcnow()
            await self._save(run)
        await self._audit(run, action="run_code", state="cancelled")
        return run

    async def pause_run(self, run_id: str) -> ExperimentRun:
        run = await self._get(run_id)
        process = _ACTIVE.get(run_id)
        if process is not None and process.is_alive():
            if sys.platform == "win32":
                run.reason = "pause is unsupported on Windows"
                await self._save(run)
                raise RunLifecycleError(run.reason)
            import os
            import signal

            try:
                os.killpg(os.getpgid(process.pid), signal.SIGSTOP)
            except ProcessLookupError:
                pass
        if run.status == run_status.STATUS_RUNNING:
            run.status = run_status.STATUS_PAUSED
            await self._save(run)
        await self._audit(run, action="run_code", state="paused")
        return run

    # -- rollback (HL-SAFE-16) ----------------------------------------------
    async def rollback_run(self, run_id: str) -> ExperimentRun:
        run = await self._get(run_id)
        if not run.checkpoint_ref:
            raise RunLifecycleError("run has no pre-run checkpoint to roll back to")
        checkpoint = await self.session.get(AgentCheckpoint, run.checkpoint_ref)
        if checkpoint is None or not checkpoint.commit:
            raise RunLifecycleError("checkpoint commit is missing; cannot roll back")
        try:
            self.git.destructive("reset", ["--hard", checkpoint.commit], approved=True)
        except GitError as exc:
            raise RunLifecycleError(f"rollback failed: {exc}") from exc
        run.reason = f"rolled back to checkpoint {checkpoint.commit[:12]}"
        await self._save(run)
        await self._audit(run, action="restore_file", state="applied")
        return run

    # -- helpers ------------------------------------------------------------
    async def _require_approved(self, run: ExperimentRun) -> AgentApproval:
        if not run.approval_id:
            raise RunLifecycleError("run has no approval; execution requires an approved per-run approval")
        approval = await self.session.get(AgentApproval, run.approval_id)
        if approval is None or approval.status != ApprovalStatus.APPROVED.value:
            raise RunLifecycleError("run is not approved; it stays awaiting_approval until a user approves it")
        return approval

    def _argv_from_config(self, run: ExperimentRun) -> list[str]:
        config = json.loads(run.config_json or "{}")
        argv = config.get("argv")
        if isinstance(argv, list) and argv and all(isinstance(part, str) for part in argv):
            return list(argv)
        raise RunLifecycleError("run config has no valid argv vector to execute")

    def _accept_unconfined(self, run: ExperimentRun) -> bool:
        config = json.loads(run.config_json or "{}")
        return bool(config.get("accept_unconfined"))

    async def _persist_run(self, **kwargs) -> ExperimentRun:
        config = kwargs.pop("config", {})
        run = ExperimentRun(config_json=json.dumps(config, sort_keys=True), **kwargs)
        self.session.add(run)
        await self.session.commit()
        await self.session.refresh(run)
        return run

    async def _get(self, run_id: str) -> ExperimentRun:
        run = await self.session.get(ExperimentRun, run_id)
        if run is None:
            raise RunLifecycleError(f"experiment run '{run_id}' not found")
        return run

    async def _save(self, run: ExperimentRun) -> None:
        self.session.add(run)
        await self.session.commit()
        await self.session.refresh(run)

    async def _audit(self, run: ExperimentRun, *, action: str, state: str) -> None:
        await self.audit.append(
            project_id=run.project_id,
            run_id=run.id,
            actor=run.requested_by,
            action=action,
            risk_level="high",
            target=run.label or run.id,
            approval_state=state,
        )
