"""Gated manuscript package creation and external-submission approval flow."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.agents.contracts import ApprovalStatus
from hydra.agents.policy import COPILOT
from hydra.autonomy.audit import AuditLedger
from hydra.autonomy.checkpoints import CheckpointService
from hydra.autonomy.gate import ActionGate, GateResult, GovernedAction
from hydra.database.models import AgentApproval
from hydra.services.docx import detect_latex_toolchain

from .builder import ManuscriptBuilder
from .exporters import ExportedTarget, export_docx, export_html, export_latex, export_pdf, write_manifest
from .models import CitationValidation, ManuscriptDocument, RedactionReport
from .redaction import RedactionScanner
from .validation import validate_citations


@dataclass(frozen=True)
class PackageRequest:
    approval_id: str | None = None
    targets: list[str] = field(default_factory=lambda: ["docx", "latex", "html", "pdf"])
    acknowledge_citation_issues: bool = False
    acknowledged_redaction_item_ids: list[str] = field(default_factory=list)
    project_id: str = "default"
    actor: str = "user"


@dataclass(frozen=True)
class PackageResult:
    status: str
    document: ManuscriptDocument
    validation: CitationValidation
    redaction: RedactionReport
    outputs: dict[str, ExportedTarget] = field(default_factory=dict)
    package_dir: str | None = None
    manifest_path: str = ""
    gate: GateResult | None = None

    def public_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "document": self.document.public_dict(),
            "validation": self.validation.public_dict(),
            "redaction": self.redaction.public_dict(),
            "outputs": {key: value.public_dict() for key, value in self.outputs.items()},
            "package_dir": self.package_dir,
            "manifest_path": self.manifest_path,
            "gate": self.gate.__dict__ if self.gate else None,
        }


@dataclass(frozen=True)
class SubmissionResult:
    status: str
    gate: GateResult

    def public_dict(self) -> dict[str, Any]:
        return {"status": self.status, "gate": self.gate.__dict__}


class ManuscriptPackageService:
    def __init__(
        self,
        project_root: Path,
        session: AsyncSession,
        *,
        builder: ManuscriptBuilder | None = None,
        latex_detector: Callable[[], dict[str, Any]] = detect_latex_toolchain,
    ) -> None:
        self.project_root = Path(project_root)
        self.session = session
        self.builder = builder or ManuscriptBuilder(self.project_root)
        self.latex_detector = latex_detector

    async def preview(self, manuscript: str, *, project_id: str = "default") -> PackageResult:
        document = self.builder.build(manuscript)
        validation = validate_citations(document)
        redaction = RedactionScanner(self.project_root).scan(document)
        return PackageResult(status="preview", document=document, validation=validation, redaction=redaction)

    async def create_package(self, manuscript: str, request: PackageRequest | None = None) -> PackageResult:
        request = request or PackageRequest()
        document = self.builder.build(manuscript)
        validation = validate_citations(document)
        redaction = RedactionScanner(self.project_root).scan(document)
        if validation.has_issues and not request.acknowledge_citation_issues:
            return PackageResult(status="validation_blocked", document=document, validation=validation, redaction=redaction)

        # Redaction acknowledgements are only honoured when the human approval
        # itself authorised them. Item ids are deterministic sha256 digests a
        # client can precompute, so a request-supplied ack is never trusted on
        # its own: the effective set is the request acks intersected with the
        # ids baked into the APPROVED AgentApproval payload (03-04 fix).
        authorised_acks = await self._approved_redaction_acks(request.approval_id, request.project_id)
        effective_acks = set(request.acknowledged_redaction_item_ids) & authorised_acks
        unresolved_redactions = redaction.unresolved(effective_acks)
        if unresolved_redactions:
            return PackageResult(
                status="redaction_blocked",
                document=document,
                validation=validation,
                redaction=RedactionReport(unresolved_redactions),
            )

        package_id = f"{document.manuscript_id}-{int(time.time() * 1000)}"
        package_dir = self.project_root / "outputs" / "manuscripts" / document.manuscript_id / package_id

        async def apply_package() -> None:
            _create_outputs(document, package_dir, request.targets, self.latex_detector, validation)

        gate = await self._gate().govern(
            GovernedAction(
                mode=COPILOT,
                action_kind="manuscript_package_create",
                target_kind="manuscript",
                target_ref=document.manuscript_id,
                project_id=request.project_id,
                summary=f"Create manuscript export package for {document.manuscript_id}",
                payload={"targets": request.targets, "template": document.template_id},
                actor=request.actor,
                approval_id=request.approval_id,
                apply_fn=apply_package,
            )
        )
        if not gate.applied:
            return PackageResult(
                status=gate.status,
                document=document,
                validation=validation,
                redaction=redaction,
                gate=gate,
            )

        outputs = _read_outputs(package_dir)
        manifest = package_dir / "reproducibility-manifest.json"
        stable_manifest = (
            self.project_root
            / "outputs"
            / "manuscripts"
            / "reproducibility"
            / f"{document.manuscript_id}-{package_id}.json"
        )
        stable_manifest.parent.mkdir(parents=True, exist_ok=True)
        stable_manifest.write_text(manifest.read_text(encoding="utf-8"), encoding="utf-8")
        return PackageResult(
            status="created",
            document=document,
            validation=validation,
            redaction=redaction,
            outputs=outputs,
            package_dir=str(package_dir),
            manifest_path=str(manifest),
            gate=gate,
        )

    async def request_external_submission(
        self,
        manuscript: str,
        *,
        venue: str,
        approval_id: str | None = None,
        project_id: str = "default",
    ) -> SubmissionResult:
        document = self.builder.build(manuscript)
        gate = await self._gate().govern(
            GovernedAction(
                mode=COPILOT,
                action_kind="external_submission",
                target_kind="manuscript",
                target_ref=document.manuscript_id,
                project_id=project_id,
                summary=f"Submit manuscript {document.manuscript_id} to {venue}",
                payload={"venue": venue},
                actor="autopilot",
                approval_id=approval_id,
            )
        )
        return SubmissionResult(status=gate.status, gate=gate)

    async def _approved_redaction_acks(self, approval_id: str | None, project_id: str) -> set[str]:
        """Redaction ids the human approval authorised, from its APPROVED payload."""
        if not approval_id:
            return set()
        approval = await self.session.get(AgentApproval, approval_id)
        if approval is None or approval.status != ApprovalStatus.APPROVED.value:
            return set()
        if approval.action_kind != "manuscript_package_create":
            return set()
        if (approval.project_id or None) not in (None, project_id):
            return set()
        try:
            payload = json.loads(approval.payload_json or "{}")
        except json.JSONDecodeError:
            return set()
        acks = payload.get("acknowledged_redaction_item_ids")
        if not isinstance(acks, list):
            return set()
        return {str(item) for item in acks}

    def _gate(self) -> ActionGate:
        checkpoint = CheckpointService(self.session, project_root=self.project_root, git=_PackageCheckpointGit())
        return ActionGate(self.session, checkpoints=checkpoint, audit=AuditLedger(self.session))


def _create_outputs(
    document: ManuscriptDocument,
    package_dir: Path,
    targets: list[str],
    latex_detector,
    validation: CitationValidation,
) -> None:
    package_dir.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, ExportedTarget] = {}
    normalized = [target.lower() for target in targets]
    tex_path = package_dir / "manuscript.tex"
    if "docx" in normalized:
        outputs["docx"] = export_docx(document, package_dir / "manuscript.docx")
    if "latex" in normalized or "pdf" in normalized:
        outputs["latex"] = export_latex(document, tex_path)
    if "html" in normalized:
        outputs["html"] = export_html(document, package_dir / "manuscript.html")
    if "pdf" in normalized:
        outputs["pdf"] = export_pdf(document, tex_path, package_dir / "manuscript.pdf", latex_detector=latex_detector)
    _write_outputs_index(package_dir, outputs)
    write_manifest(document, validation, outputs, package_dir / "reproducibility-manifest.json")


def _write_outputs_index(package_dir: Path, outputs: dict[str, ExportedTarget]) -> None:
    import json

    (package_dir / "outputs.json").write_text(
        json.dumps({key: value.public_dict() for key, value in outputs.items()}, sort_keys=True, indent=2),
        encoding="utf-8",
    )


def _read_outputs(package_dir: Path) -> dict[str, ExportedTarget]:
    import json

    raw = json.loads((package_dir / "outputs.json").read_text(encoding="utf-8"))
    return {key: ExportedTarget(**value) for key, value in raw.items()}


class _PackageCheckpointGit:
    def checkpoint(self, label: str = "checkpoint") -> None:
        return None

    def head_commit(self) -> str:
        return "manuscript-package-checkpoint"
