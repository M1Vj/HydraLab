"""Experiment execution approval gates (HL-SAFE-17/18/19).

Three gates compose here:

1. Per-project first-use enablement (``execution_enabled``, default OFF). The
   Experiments panel renders its permission-denied "Enable execution" state
   until this is set; no run controls are offered before it.
2. Cloud budget + spend approval — a ``cloud`` backend is rejected before any
   compute is requested unless a budget is configured AND spend is approved.
   This is checked BEFORE ``ActionGate.govern`` so no process/provider call
   happens on the rejected path.
3. The governed-action build that routes every run start through the shared
   ``ActionGate`` chokepoint with ``action_kind="run_code"`` and
   ``high_risk_category="experiment_execution"``. Untrusted-provenance runs set
   ``trust_origin="untrusted-external"`` so the gate routes them to the Review
   Inbox (DEC-11) instead of ever auto-starting.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.autonomy.gate import GovernedAction
from hydra.compute.registry import ResolvedBackend
from hydra.database.models import ExperimentExecutionSetting, ExperimentRun


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class BudgetCheck:
    ok: bool
    reason: str = ""


class ExperimentExecutionGate:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _setting(self, project_id: str) -> ExperimentExecutionSetting:
        row = await self.session.get(ExperimentExecutionSetting, project_id)
        if row is None:
            row = ExperimentExecutionSetting(project_id=project_id)
            self.session.add(row)
            await self.session.commit()
            await self.session.refresh(row)
        return row

    async def is_execution_enabled(self, project_id: str) -> bool:
        return (await self._setting(project_id)).execution_enabled

    async def get_setting(self, project_id: str) -> ExperimentExecutionSetting:
        return await self._setting(project_id)

    async def enable_execution(self, project_id: str, enabled: bool = True) -> ExperimentExecutionSetting:
        """Set the per-project first-use flag. This is an explicit user action."""
        row = await self._setting(project_id)
        row.execution_enabled = enabled
        row.updated_at = _utcnow()
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def set_cloud_budget(
        self, project_id: str, *, budget_usd: Optional[float], spend_approved: bool
    ) -> ExperimentExecutionSetting:
        row = await self._setting(project_id)
        row.cloud_budget_usd = budget_usd
        row.cloud_spend_approved = spend_approved
        row.updated_at = _utcnow()
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def check_cloud_budget(self, project_id: str, resolved: ResolvedBackend) -> BudgetCheck:
        """A cloud backend needs a configured budget AND explicit spend approval."""
        if not resolved.is_cloud:
            return BudgetCheck(ok=True)
        setting = await self._setting(project_id)
        if setting.cloud_budget_usd is None or setting.cloud_budget_usd <= 0:
            return BudgetCheck(ok=False, reason="budget required: no cloud budget configured for this project")
        if not setting.cloud_spend_approved:
            return BudgetCheck(ok=False, reason="budget required: cloud spend has not been approved")
        return BudgetCheck(ok=True)

    def build_governed_action(
        self,
        run: ExperimentRun,
        *,
        mode: str,
        full_access_enabled: bool = False,
    ) -> GovernedAction:
        """Route the run start through the shared ActionGate chokepoint.

        ``action_kind="run_code"`` is intentionally NOT a code-execution category
        (shell/code_execution/arbitrary_code) so it lands on approval-required
        rather than the DEC-6 hard block; ``experiment_execution`` keeps it in the
        every-mode high-risk set that can never auto-apply.
        """

        return GovernedAction(
            mode=mode,
            action_kind="run_code",
            target_kind="experiment_run",
            target_ref=run.id,
            trust_origin=run.trust_origin,
            justification_trust=run.justification_trust,
            high_risk_category="experiment_execution",
            full_access_enabled=full_access_enabled,
            run_id=run.id,
            project_id=run.project_id,
            summary=f"experiment run {run.label or run.id}",
            actor=run.requested_by,
            payload={"backend_id": run.backend_id, "label": run.label},
        )
