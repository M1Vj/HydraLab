"""Reproducibility bundle builder and final report export (HL-QUAL-31/35)."""

from __future__ import annotations

import hashlib
import json
import platform
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.agents.policy import COPILOT
from hydra.audit.ledger_export import export_run_ledger
from hydra.autonomy.audit import AuditLedger
from hydra.autonomy.checkpoints import CheckpointService
from hydra.autonomy.gate import ActionGate, GateResult, GovernedAction
from hydra.database.models import (
    AgentApproval,
    AgentCheckpoint,
    AgentRun,
    Citation,
    ExperimentRun,
    ReproducibilityManifest,
    Source,
)
from hydra.reproducibility.evaluation import list_evaluation_results
from hydra.reproducibility.manifest import HASH_ALGORITHM, SCHEMA_VERSION, ReproducibilityManifestDocument
from hydra.reproducibility.redaction import ReproducibilityRedactionFilter
from hydra.services.git.service import GitService


Clock = Callable[[], str]


@dataclass(frozen=True)
class BundleResult:
    status: str
    bundle_id: str
    bundle_dir: str
    manifest: ReproducibilityManifestDocument
    manifest_content_hash: str
    evaluation_path: str = ""
    ledger_path: str = ""
    gate: GateResult | None = None

    def public_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "bundle_id": self.bundle_id,
            "bundle_dir": self.bundle_dir,
            "manifest": self.manifest.public_dict(),
            "manifest_content_hash": self.manifest_content_hash,
            "evaluation_path": self.evaluation_path,
            "ledger_path": self.ledger_path,
            "gate": self.gate.__dict__ if self.gate else None,
        }


@dataclass(frozen=True)
class ReportResult:
    status: str
    report_path: str
    gate: GateResult | None = None

    def public_dict(self) -> dict[str, Any]:
        return {"status": self.status, "report_path": self.report_path, "gate": self.gate.__dict__ if self.gate else None}


class ReproducibilityBundleBuilder:
    def __init__(self, session: AsyncSession, *, clock: Clock | None = None) -> None:
        self.session = session
        self.clock = clock or _now_iso

    async def preview(self, project_id: str, run_ids: list[str], project_root: Path) -> dict[str, Any]:
        plan = await self._build_plan(project_id, run_ids, Path(project_root))
        return {
            "status": "preview",
            "project_id": project_id,
            "run_ids": list(run_ids),
            "included_categories": [
                {"id": "sources", "label": "Sources", "count": len(plan["sources"])},
                {"id": "artifacts", "label": "Artifacts", "count": len(plan["artifacts"])},
                {"id": "evaluation", "label": "Evaluation", "count": len(plan["evaluation"])},
                {"id": "ledger", "label": "Ledger", "count": len(plan["ledger"].get("runs", []))},
            ],
            "redacted_item_count": len(plan["redaction_decisions"]),
            "redaction_decisions": list(plan["redaction_decisions"]),
        }

    async def build(
        self,
        project_id: str,
        run_ids: list[str],
        project_root: Path,
        *,
        approval_id: str | None = None,
        actor: str = "user",
    ) -> BundleResult:
        project_root = Path(project_root)
        plan = await self._build_plan(project_id, run_ids, project_root)
        manifest = _manifest_from_plan(
            project_id=project_id,
            run_ids=run_ids,
            created_at=self.clock(),
            plan=plan,
            bundle_id="pending",
        )
        manifest_hash = manifest.stable_content_hash()
        bundle_id = f"bundle-{manifest_hash.split(':', 1)[1][:12]}"
        manifest = _manifest_from_plan(
            project_id=project_id,
            run_ids=run_ids,
            created_at=self.clock(),
            plan=plan,
            bundle_id=bundle_id,
        )
        bundle_dir = project_root / "outputs" / "reproducibility" / project_id / bundle_id
        target_ref = _target_ref(project_id, run_ids)

        async def apply_bundle() -> None:
            await self._write_bundle(bundle_dir, manifest, manifest_hash, plan)

        gate = await self._gate(project_root).govern(
            GovernedAction(
                mode=COPILOT,
                action_kind="reproducibility_bundle_build",
                target_kind="reproducibility_bundle",
                target_ref=target_ref,
                project_id=project_id,
                summary=f"Build reproducibility bundle for {project_id}",
                payload={"run_ids": list(run_ids), "bundle_id": bundle_id},
                actor=actor,
                approval_id=approval_id,
                apply_fn=apply_bundle,
            )
        )
        if not gate.applied:
            return BundleResult(
                status=gate.status,
                bundle_id=bundle_id,
                bundle_dir=str(bundle_dir),
                manifest=manifest,
                manifest_content_hash=manifest_hash,
                gate=gate,
            )
        return BundleResult(
            status="created",
            bundle_id=bundle_id,
            bundle_dir=str(bundle_dir),
            manifest=manifest,
            manifest_content_hash=manifest_hash,
            evaluation_path=str(bundle_dir / "evaluation.json"),
            ledger_path=str(bundle_dir / "ledger.json"),
            gate=gate,
        )

    async def _build_plan(self, project_id: str, run_ids: list[str], project_root: Path) -> dict[str, Any]:
        await _resolve_runs(self.session, run_ids)
        redaction = ReproducibilityRedactionFilter(project_root)
        paths = _iter_project_files(project_root)
        decisions_by_path = {item.path_or_ref: item for item in redaction.scan_paths(paths)}
        artifacts = []
        for relpath in paths:
            if relpath in decisions_by_path:
                continue
            absolute = project_root / relpath
            artifacts.append({"path": relpath, "content_hash": _file_hash(absolute), "size": absolute.stat().st_size})
        sources, source_ids = await _collect_sources(self.session, project_id)
        approvals = await _collect_approval_ids(self.session, project_id, run_ids)
        checkpoints = await _collect_checkpoint_ids(self.session, project_id, run_ids)
        evaluation = await _collect_evaluation(self.session, run_ids)
        ledger = (await export_run_ledger(self.session, project_id=project_id, run_ids=run_ids)).public_dict()
        return {
            "project_root": str(project_root),
            "source_ids": source_ids,
            "sources": sources,
            "artifacts": sorted(artifacts, key=lambda item: item["path"]),
            "prompts": [],
            "model_calls": _model_calls_from_ledger(ledger),
            "tool_calls": _tool_calls_from_ledger(ledger),
            "code_version": _code_version(project_root),
            "environment_version": _environment_version(project_root),
            "approvals": approvals,
            "checkpoints": checkpoints,
            "redaction_decisions": [item.public_dict() for item in decisions_by_path.values()],
            "evaluation": evaluation,
            "ledger": ledger,
        }

    async def _write_bundle(
        self,
        bundle_dir: Path,
        manifest: ReproducibilityManifestDocument,
        manifest_hash: str,
        plan: dict[str, Any],
    ) -> None:
        if bundle_dir.exists():
            shutil.rmtree(bundle_dir)
        bundle_dir.mkdir(parents=True, exist_ok=True)
        artifact_root = bundle_dir / "artifacts"
        for artifact in plan["artifacts"]:
            source = Path(plan["project_root"]) / artifact["path"]
            if not source.exists():
                continue
            dest = artifact_root / artifact["path"]
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
        (bundle_dir / "manifest.json").write_text(manifest.canonical_json(), encoding="utf-8")
        (bundle_dir / "evaluation.json").write_text(
            json.dumps({"evaluation_results": plan["evaluation"]}, sort_keys=True, indent=2),
            encoding="utf-8",
        )
        (bundle_dir / "ledger.json").write_text(json.dumps(plan["ledger"], sort_keys=True, indent=2), encoding="utf-8")
        await _upsert_manifest_row(self.session, manifest.to_row(manifest_hash))

    def _gate(self, project_root: Path) -> ActionGate:
        return ActionGate(
            self.session,
            checkpoints=CheckpointService(self.session, project_root=project_root, git=_BundleCheckpointGit()),
            audit=AuditLedger(self.session),
        )


async def export_final_report(
    session: AsyncSession,
    bundle_dir: str | Path,
    *,
    approval_id: str | None = None,
    actor: str = "user",
) -> ReportResult:
    bundle_dir = Path(bundle_dir)
    manifest = json.loads((bundle_dir / "manifest.json").read_text(encoding="utf-8"))
    bundle_id = str(manifest.get("id") or bundle_dir.name)
    project_id = str(manifest.get("project_id") or "default")
    report_path = bundle_dir / "final-report.json"

    async def apply_report() -> None:
        payload = {
            "schema": "reproducibility-final-report.v1",
            "manifest": _report_safe_manifest(manifest),
            "evaluation": json.loads((bundle_dir / "evaluation.json").read_text(encoding="utf-8")),
            "ledger": json.loads((bundle_dir / "ledger.json").read_text(encoding="utf-8")),
        }
        text = json.dumps(payload, sort_keys=True, indent=2)
        text = ReproducibilityRedactionFilter(bundle_dir).scrub_text(text)
        report_path.write_text(text, encoding="utf-8")

    gate = await ActionGate(
        session,
        checkpoints=CheckpointService(session, project_root=bundle_dir, git=_BundleCheckpointGit()),
        audit=AuditLedger(session),
    ).govern(
        GovernedAction(
            mode=COPILOT,
            action_kind="reproducibility_report_export",
            target_kind="reproducibility_bundle",
            target_ref=bundle_id,
            project_id=project_id,
            summary=f"Export final reproducibility report for {bundle_id}",
            payload={"bundle_id": bundle_id},
            actor=actor,
            approval_id=approval_id,
            apply_fn=apply_report,
        )
    )
    return ReportResult(status="created" if gate.applied else gate.status, report_path=str(report_path), gate=gate)


async def _resolve_runs(session: AsyncSession, run_ids: list[str]) -> None:
    for run_id in run_ids:
        if await session.get(AgentRun, run_id):
            continue
        if await session.get(ExperimentRun, run_id):
            continue
        raise ValueError(f"run id does not resolve: {run_id}")


async def _collect_sources(session: AsyncSession, project_id: str) -> tuple[list[dict[str, Any]], list[str]]:
    citations = (
        await session.exec(select(Citation).where(Citation.project_id == project_id).order_by(Citation.created_at.asc()))
    ).all()
    source_ids = sorted({citation.source_id for citation in citations})
    source_rows = []
    for source_id in source_ids:
        source = await session.get(Source, source_id)
        if source is None:
            continue
        source_rows.append(
            {
                "source_id": source.id,
                "title": source.title,
                "doi": source.doi,
                "trashed": bool(source.trashed),
                "citations": [
                    {
                        "citation_id": citation.id,
                        "source_id": citation.source_id,
                        "text": citation.text,
                        "citation_key": citation.citation_key,
                        "csl_json": _json_or_text(citation.csl_json),
                        "doi": citation.doi,
                        "link_state": citation.link_state,
                        "trust_origin": citation.trust_origin,
                    }
                    for citation in citations
                    if citation.source_id == source_id
                ],
            }
        )
    return source_rows, source_ids


async def _collect_approval_ids(session: AsyncSession, project_id: str, run_ids: list[str]) -> list[str]:
    result = await session.exec(
        select(AgentApproval)
        .where(AgentApproval.project_id == project_id)
        .where(AgentApproval.run_id.in_(run_ids))
        .order_by(AgentApproval.created_at.asc())
    )
    return [row.id for row in result.all()]


async def _collect_checkpoint_ids(session: AsyncSession, project_id: str, run_ids: list[str]) -> list[str]:
    result = await session.exec(
        select(AgentCheckpoint)
        .where(AgentCheckpoint.project_id == project_id)
        .where(AgentCheckpoint.run_id.in_(run_ids))
        .order_by(AgentCheckpoint.created_at.asc())
    )
    return [row.id for row in result.all()]


async def _collect_evaluation(session: AsyncSession, run_ids: list[str]) -> list[dict[str, Any]]:
    rows = []
    for run_id in run_ids:
        for row in await list_evaluation_results(session, run_id):
            rows.append(
                {
                    "id": row.id,
                    "run_id": row.run_id,
                    "metric_name": row.metric_name,
                    "value": row.value,
                    "evaluated_artifact_hash": row.evaluated_artifact_hash,
                    "created_at": row.created_at.isoformat(),
                }
            )
    return rows


def _manifest_from_plan(
    *,
    project_id: str,
    run_ids: list[str],
    created_at: str,
    plan: dict[str, Any],
    bundle_id: str,
) -> ReproducibilityManifestDocument:
    return ReproducibilityManifestDocument.from_payload(
        {
            "id": bundle_id,
            "project_id": project_id,
            "package_version": "1.0.0",
            "schema_version": SCHEMA_VERSION,
            "hash_algorithm": HASH_ALGORITHM,
            "source_ids": plan["source_ids"],
            "sources": plan["sources"],
            "artifacts": plan["artifacts"],
            "prompts": plan["prompts"],
            "model_calls": plan["model_calls"],
            "tool_calls": plan["tool_calls"],
            "code_version": plan["code_version"],
            "environment_version": plan["environment_version"],
            "approvals": plan["approvals"],
            "checkpoints": plan["checkpoints"],
            "redaction_decisions": plan["redaction_decisions"],
            "run_ids": list(run_ids),
            "created_at": created_at,
        }
    )


def _iter_project_files(project_root: Path) -> list[str]:
    paths = []
    for path in sorted(project_root.rglob("*")):
        # Skip symlinks: a file symlink is is_file()-true and would sweep an
        # out-of-tree target (e.g. ``notes/key -> ~/.ssh/id_rsa``) into the
        # bundle plan and get copied verbatim (HL privacy audit M1).
        if path.is_symlink():
            continue
        if not path.is_file():
            continue
        relpath = path.relative_to(project_root).as_posix()
        if relpath.startswith("outputs/reproducibility/"):
            continue
        paths.append(relpath)
    return paths


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _code_version(project_root: Path) -> dict[str, Any]:
    try:
        return {"git_ref": GitService(project_root).head_commit() or "unavailable"}
    except Exception:
        return {"git_ref": "unavailable"}


def _environment_version(project_root: Path) -> dict[str, Any]:
    lockfiles = ["backend/uv.lock", "uv.lock", "apps/web/bun.lock", "apps/web/package.json"]
    fingerprints: dict[str, str] = {}
    for relpath in lockfiles:
        path = project_root / relpath
        fingerprints[relpath] = _file_hash(path) if path.exists() else "unavailable"
    return {"python": platform.python_version(), "lockfiles": fingerprints}


def _model_calls_from_ledger(ledger: dict[str, Any]) -> list[dict[str, Any]]:
    calls = []
    for run in ledger.get("runs", []):
        for entry in run.get("entries", []):
            if "provider" in str(entry.get("action", "")) or "model" in str(entry.get("target", "")):
                calls.append({"model": str(entry.get("target") or ""), "provider": "", "version": ""})
    return calls


def _tool_calls_from_ledger(ledger: dict[str, Any]) -> list[dict[str, Any]]:
    calls = []
    for run in ledger.get("runs", []):
        for entry in run.get("entries", []):
            if "tool" in str(entry.get("action", "")):
                calls.append(dict(entry))
    return calls


def _target_ref(project_id: str, run_ids: list[str]) -> str:
    return f"{project_id}:{','.join(sorted(run_ids))}"


def _json_or_text(value: str) -> Any:
    try:
        return json.loads(value or "{}")
    except json.JSONDecodeError:
        return value


async def _upsert_manifest_row(session: AsyncSession, row: ReproducibilityManifest) -> None:
    existing = await session.get(ReproducibilityManifest, row.id)
    if existing is None:
        session.add(row)
    else:
        for name, value in row.model_dump().items():
            setattr(existing, name, value)
        session.add(existing)
    await session.commit()


def _report_safe_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    clone = json.loads(json.dumps(manifest))
    for decision in clone.get("redaction_decisions", []):
        if decision.get("category") == "provider-cache":
            decision["path_or_ref"] = "[REDACTED-PROVIDER-CACHE]"
    return clone


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


class _BundleCheckpointGit:
    def checkpoint(self, label: str = "checkpoint") -> None:
        return None

    def head_commit(self) -> str:
        return "reproducibility-bundle-checkpoint"
