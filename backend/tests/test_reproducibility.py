"""Phase-3 reproducibility & evaluation ledger tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.agents.contracts import ApprovalStatus
from hydra.agents.policy import COPILOT
from hydra.audit.ledger_export import export_run_ledger
from hydra.autonomy.audit import AuditLedger
from hydra.database.models import (
    AgentApproval,
    AgentCheckpoint,
    AgentRun,
    Citation,
    ExperimentRun,
    Source,
    SourceTombstone,
)
from hydra.reproducibility.builder import ReproducibilityBundleBuilder, export_final_report
from hydra.reproducibility.evaluation import EvaluationResult, list_evaluation_results, record_evaluation_result
from hydra.reproducibility.manifest import (
    MANIFEST_REQUIRED_FIELDS,
    ReproducibilityManifestDocument,
    ManifestValidationError,
)
from hydra.reproducibility.redaction import ReproducibilityRedactionFilter
from hydra.reproducibility.verifier import ManifestVerifier

SEEDED_SECRET = "sk-live-EXAMPLE-1234"


@pytest_asyncio.fixture
async def engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def session(engine):
    maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        yield session


def _seed_project(root: Path) -> None:
    (root / "outputs").mkdir()
    (root / "outputs" / "result.txt").write_text("replication result\n", encoding="utf-8")
    (root / "notes").mkdir()
    (root / "notes" / "summary.md").write_text("safe note\n", encoding="utf-8")
    (root / ".env").write_text(f"OPENAI_API_KEY={SEEDED_SECRET}\n", encoding="utf-8")
    (root / ".hydralab" / "cache" / "provider" / "openai").mkdir(parents=True)
    (root / ".hydralab" / "cache" / "provider" / "openai" / "payload.json").write_text(
        f'{{"token": "{SEEDED_SECRET}"}}\n',
        encoding="utf-8",
    )
    (root / ".hydralab" / "credentials").mkdir(parents=True)
    (root / ".hydralab" / "credentials" / "anthropic.keychain-ref").write_text(
        "keychain://hydralab/provider/anthropic/api-key\n",
        encoding="utf-8",
    )


async def _seed_records(session: AsyncSession, *, run_id: str = "run-2026-06-20-attention-replication") -> dict[str, str]:
    source = Source(
        id="source-attention",
        project_id="default",
        title="Attention Is All You Need",
        doi="10.48550/arXiv.1706.03762",
    )
    citation = Citation(
        id="citation-attention",
        source_id=source.id,
        project_id="default",
        text="Vaswani et al. Attention Is All You Need.",
        citation_key="attention2017",
        doi=source.doi,
    )
    agent_run = AgentRun(
        id=run_id,
        project_id="default",
        recipe="attention-replication",
        status="completed",
        artifacts=json.dumps([{"path": "outputs/result.txt"}], sort_keys=True),
        trust_decisions=json.dumps(
            [
                {
                    "decision": "blocked-auto-apply",
                    "source_trust": "untrusted-external",
                    "reason": "untrusted content requires review",
                }
            ],
            sort_keys=True,
        ),
    )
    experiment = ExperimentRun(
        id="experiment-attention",
        project_id="default",
        label="attention eval",
        status="succeeded",
        artifact_manifest_json=json.dumps({"artifacts": [{"path": "outputs/result.txt"}]}, sort_keys=True),
        metrics_json=json.dumps({"BLEU": 0.412}, sort_keys=True),
        trust_origin="untrusted-external",
    )
    checkpoint = AgentCheckpoint(
        id="checkpoint-attention",
        project_id="default",
        run_id=run_id,
        git_ref="abc123",
        commit="abc123",
        label="before export",
        target="outputs/result.txt",
    )
    approval = AgentApproval(
        id="approval-attention",
        run_id=run_id,
        project_id="default",
        mode=COPILOT,
        action_kind="provider_call",
        target_kind="model",
        target_ref="gpt-4.1-mini",
        summary="Provider call approved",
        status=ApprovalStatus.APPROVED.value,
    )
    session.add_all([source, citation, agent_run, experiment, checkpoint, approval])
    await session.commit()
    await AuditLedger(session).append(
        project_id="default",
        run_id=run_id,
        actor="autopilot",
        action="provider_call",
        risk_level="medium",
        target="gpt-4.1-mini",
        approval_state="approved",
    )
    return {"run_id": run_id, "source_id": source.id, "citation_id": citation.id}


async def _approve_bundle(session: AsyncSession, *, action_kind: str, target_ref: str) -> AgentApproval:
    row = AgentApproval(
        project_id="default",
        mode=COPILOT,
        action_kind=action_kind,
        target_kind="reproducibility_bundle",
        target_ref=target_ref,
        status=ApprovalStatus.APPROVED.value,
        payload_json="{}",
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


def test_hl_qual_30_manifest_validates_required_top_level_fields():
    payload = {field: [] for field in MANIFEST_REQUIRED_FIELDS}
    payload.update(
        {
            "id": "bundle-1",
            "project_id": "default",
            "package_version": "1.0.0",
            "schema_version": "reproducibility-manifest.v1",
            "hash_algorithm": "sha256",
            "source_ids": ["source-attention"],
            "code_version": {"git_ref": "abc123"},
            "environment_version": {"python": "3.x"},
            "created_at": "2026-06-20T00:00:00+00:00",
        }
    )

    document = ReproducibilityManifestDocument.from_payload(payload)

    assert set(MANIFEST_REQUIRED_FIELDS).issubset(document.public_dict().keys())
    missing = dict(payload)
    missing.pop("model_calls")
    with pytest.raises(ManifestValidationError, match="model_calls"):
        ReproducibilityManifestDocument.from_payload(missing)


@pytest.mark.asyncio
async def test_hl_qual_32_evaluation_records_are_written_and_read_by_run_id(session):
    row = await record_evaluation_result(
        session,
        run_id="experiment-attention",
        metric_name="BLEU",
        value=0.412,
        evaluated_artifact_hash="sha256:abc",
        created_at="2026-06-20T00:00:00+00:00",
    )

    rows = await list_evaluation_results(session, "experiment-attention")

    assert isinstance(row, EvaluationResult)
    assert [item.metric_name for item in rows] == ["BLEU"]
    assert rows[0].evaluated_artifact_hash == "sha256:abc"


def test_hl_qual_34_redaction_records_hard_blocks_and_refuses_reinclude(tmp_path):
    _seed_project(tmp_path)
    redaction = ReproducibilityRedactionFilter(tmp_path)

    decisions = redaction.scan_paths(
        [
            ".env",
            ".hydralab/cache/provider/openai/payload.json",
            ".hydralab/credentials/anthropic.keychain-ref",
            "notes/summary.md",
        ]
    )
    refusal = redaction.refuse_hard_blocked(".hydralab/credentials/anthropic.keychain-ref")

    by_path = {item.path_or_ref: item for item in decisions}
    assert by_path[".env"].decision == "exclude"
    assert by_path[".hydralab/cache/provider/openai/payload.json"].category == "provider-cache"
    assert by_path[".hydralab/credentials/anthropic.keychain-ref"].category == "credentials"
    assert ".hydralab/credentials/anthropic.keychain-ref" in refusal.reason
    assert refusal.decision == "refuse"


def test_hl_qual_34_redaction_catches_quoted_pem_and_nested_git_secrets(tmp_path):
    # Privacy audit H1/H2: strong content detection + any-depth .git exclusion so
    # quoted config keys, non-.pem private keys and nested-repo credential URLs
    # are never copied into the bundle.
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "app.json").write_text('{"api_key":"sk-proj-abcdefgh1234567890"}\n')
    (tmp_path / "deploy").mkdir()
    (tmp_path / "deploy" / "id_rsa").write_text(
        "-----BEGIN OPENSSH PRIVATE KEY-----\nMIIsecretbody000\n-----END OPENSSH PRIVATE KEY-----\n"
    )
    (tmp_path / "apps" / "web" / ".git").mkdir(parents=True)
    (tmp_path / "apps" / "web" / ".git" / "config").write_text(
        "[remote]\n url = https://x-access-token:ghp_abcdefghij0123456789abcd@github.com/o/r.git\n"
    )
    redaction = ReproducibilityRedactionFilter(tmp_path)

    decisions = {
        item.path_or_ref: item
        for item in redaction.scan_paths(
            ["config/app.json", "deploy/id_rsa", "apps/web/.git/config"]
        )
    }

    assert decisions["config/app.json"].category == "secrets"
    assert decisions["deploy/id_rsa"].category == "secrets"
    assert decisions["apps/web/.git/config"].category == "git-internals"


@pytest.mark.asyncio
async def test_hl_qual_33_ledger_export_matches_store_and_surfaces_trust_decisions(session):
    ids = await _seed_records(session)

    export = await export_run_ledger(session, project_id="default", run_ids=[ids["run_id"]])

    run_export = export.runs[0]
    assert [entry["action"] for entry in run_export.entries] == ["provider_call"]
    assert run_export.entries[0]["risk_level"] == "medium"
    assert [approval["id"] for approval in run_export.approvals] == ["approval-attention"]
    assert [checkpoint["id"] for checkpoint in run_export.checkpoints] == ["checkpoint-attention"]
    assert run_export.trust_decisions[0]["decision"] == "blocked-auto-apply"


@pytest.mark.asyncio
async def test_hl_qual_31_34_35_bundle_rebuild_is_deterministic_and_secret_free(session, tmp_path):
    _seed_project(tmp_path)
    ids = await _seed_records(session)
    await record_evaluation_result(
        session,
        run_id=ids["run_id"],
        metric_name="exact-match",
        value=0.78,
        evaluated_artifact_hash="sha256:result",
        created_at="2026-06-20T00:00:00+00:00",
    )
    target_ref = "default:run-2026-06-20-attention-replication"
    approval = await _approve_bundle(session, action_kind="reproducibility_bundle_build", target_ref=target_ref)
    builder = ReproducibilityBundleBuilder(session, clock=lambda: "2026-06-20T00:00:00+00:00")

    first = await builder.build(
        "default",
        [ids["run_id"]],
        tmp_path,
        approval_id=approval.id,
    )
    approval2 = await _approve_bundle(session, action_kind="reproducibility_bundle_build", target_ref=target_ref)
    second = await builder.build(
        "default",
        [ids["run_id"]],
        tmp_path,
        approval_id=approval2.id,
    )
    report_approval = await _approve_bundle(
        session,
        action_kind="reproducibility_report_export",
        target_ref=first.bundle_id,
    )
    report = await export_final_report(session, first.bundle_dir, approval_id=report_approval.id)

    assert first.status == "created"
    assert first.manifest_content_hash == second.manifest_content_hash
    manifest_text = (Path(first.bundle_dir) / "manifest.json").read_text(encoding="utf-8")
    report_text = Path(report.report_path).read_text(encoding="utf-8")
    assert SEEDED_SECRET not in manifest_text
    assert SEEDED_SECRET not in report_text
    assert ".hydralab/cache/provider/openai/payload.json" not in report_text
    assert any(item["path_or_ref"] == ".env" for item in first.manifest.public_dict()["redaction_decisions"])
    assert (Path(first.bundle_dir) / "evaluation.json").exists()
    assert (Path(first.bundle_dir) / "ledger.json").exists()


@pytest.mark.asyncio
async def test_hl_qual_36_verifier_passes_fails_dangling_and_resolves_tombstone(session, tmp_path):
    _seed_project(tmp_path)
    ids = await _seed_records(session)
    approval = await _approve_bundle(
        session,
        action_kind="reproducibility_bundle_build",
        target_ref="default:run-2026-06-20-attention-replication",
    )
    result = await ReproducibilityBundleBuilder(session, clock=lambda: "2026-06-20T00:00:00+00:00").build(
        "default",
        [ids["run_id"]],
        tmp_path,
        approval_id=approval.id,
    )
    verifier = ManifestVerifier(session)

    clean = await verifier.verify(result.bundle_dir)
    await session.delete(await session.get(Source, ids["source_id"]))
    await session.commit()
    dangling = await verifier.verify(result.bundle_dir)
    survivor = Source(id="source-survivor", project_id="default", title="Attention survivor")
    tombstone = SourceTombstone(
        old_id=ids["source_id"],
        survivor_id=survivor.id,
        merge_record_id="merge-1",
        reason="user_confirmed_fuzzy",
    )
    session.add_all([survivor, tombstone])
    await session.commit()
    resolved = await verifier.verify(result.bundle_dir)

    assert clean.ok is True
    assert clean.dangling_ids == []
    assert dangling.ok is False
    assert ids["source_id"] in dangling.dangling_ids
    assert resolved.ok is True
    assert resolved.dangling_ids == []
    assert resolved.resolved_soft_deleted_or_merged[0]["resolved_id"] == "source-survivor"


@pytest.mark.asyncio
async def test_untrusted_content_does_not_auto_promote_without_trust_decision_flag(session):
    run = AgentRun(
        id="untrusted-run",
        project_id="default",
        status="completed",
        trust_decisions=json.dumps(
            [{"decision": "blocked-auto-apply", "source_trust": "untrusted-external"}],
            sort_keys=True,
        ),
    )
    session.add(run)
    await session.commit()

    export = await export_run_ledger(session, project_id="default", run_ids=["untrusted-run"])

    assert export.runs[0].trust_decisions == [
        {"decision": "blocked-auto-apply", "source_trust": "untrusted-external"}
    ]
    assert not any(
        item.get("decision") == "auto-applied" and item.get("source_trust") == "untrusted-external"
        for item in export.runs[0].trust_decisions
    )
