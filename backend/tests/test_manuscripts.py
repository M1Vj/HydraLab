"""Phase-3 manuscript publishing pipeline tests."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.agents.contracts import ApprovalStatus
from hydra.agents.policy import FULL_ACCESS
from hydra.database.models import AgentApproval, AgentAuditLedgerEntry
from hydra.manuscripts import (
    ManuscriptBuilder,
    ManuscriptPackageService,
    PackageRequest,
    TemplateSpec,
    bundled_export_dependencies,
    default_template_registry,
)


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


def _write_manuscript(root: Path, *, missing_citation: bool = False, hazards: bool = False) -> Path:
    manuscript = root / "writing" / "manuscripts" / "attention-survey"
    (manuscript / "figures").mkdir(parents=True)
    (manuscript / "figures" / "flow.png").write_bytes(b"fake-png")
    (manuscript / "figures" / "architecture.png").write_bytes(b"fake-png")
    include_paths = ""
    if hazards:
        (root / ".hydralab" / "logs").mkdir(parents=True)
        (root / ".hydralab" / "logs" / "run.log").write_text("internal log\n", encoding="utf-8")
        (root / "work" / "reviews").mkdir(parents=True)
        (root / "work" / "reviews" / "private.md").write_text("private reviewer note\n", encoding="utf-8")
        include_paths = 'include_paths: [".hydralab/logs/run.log", "work/reviews/private.md"]\n'
    (manuscript / "paper.yaml").write_text(
        "citation_style: IEEE\nmanuscript_template: generic-academic\n" + include_paths,
        encoding="utf-8",
    )
    citation = "missingkey" if missing_citation else "attention2017"
    (manuscript / "main.md").write_text(
        "\n".join(
            [
                "# Introduction",
                "Transformers changed sequence modeling [@attention2017].",
                "![System flow](figures/flow.png){#fig:flow}",
                "",
                "# Related Work",
                f"Figure @fig:architecture compares the pipeline [@{citation}].",
                "![Architecture](figures/architecture.png){#fig:architecture}",
                "",
                "Table: Baseline results {#tbl:baseline}",
                "| Metric | Value |",
                "| --- | --- |",
                "| F1 | 0.90 |",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (manuscript / "references.json").write_text(
        json.dumps(
            [
                {
                    "id": "attention2017",
                    "title": "Attention Is All You Need",
                    "authors": "Ashish Vaswani; Noam Shazeer",
                    "year": "2017",
                    "url": "https://arxiv.org/abs/1706.03762",
                }
            ]
        ),
        encoding="utf-8",
    )
    (manuscript / "authorship.yaml").write_text(
        "Introduction: human\nRelated Work: assistant\n",
        encoding="utf-8",
    )
    return manuscript


async def _approved(session: AsyncSession, target: str) -> AgentApproval:
    row = AgentApproval(
        project_id="default",
        mode=FULL_ACCESS,
        action_kind="manuscript_package_create",
        target_kind="manuscript",
        target_ref=target,
        status=ApprovalStatus.APPROVED.value,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


def test_hl_write_31_template_registry_accepts_later_venues_without_builder_changes():
    registry = default_template_registry()
    registry.register(TemplateSpec(id="ieee", label="IEEE", venue_type="conference", citation_style="ieee"))

    assert "generic-academic" in registry.ids()
    assert "ieee" in registry.ids()
    assert registry.get("ieee").citation_style == "ieee"


def test_hl_write_30_hl_write_31_builder_assembles_model_and_does_not_write_sources(tmp_path):
    manuscript_dir = _write_manuscript(tmp_path)
    before = sorted(path.relative_to(manuscript_dir) for path in manuscript_dir.rglob("*"))

    document = ManuscriptBuilder(tmp_path).build("attention-survey")

    after = sorted(path.relative_to(manuscript_dir) for path in manuscript_dir.rglob("*"))
    assert after == before
    assert document.manuscript_id == "attention-survey"
    assert document.format.citation_style == "IEEE"
    assert [section.title for section in document.sections] == ["Introduction", "Related Work"]
    assert len(document.figures) == 2
    assert document.figures[1].number == 2
    assert document.tables[0].number == 1
    assert document.citation_keys == ["attention2017"]
    assert "attention2017" in document.references


@pytest.mark.asyncio
async def test_hl_write_32_exports_without_compiler_keep_tex_download(session, tmp_path):
    _write_manuscript(tmp_path)
    approval = await _approved(session, "attention-survey")
    service = ManuscriptPackageService(
        tmp_path,
        session,
        latex_detector=lambda: {"available": False, "toolchain": "", "path": "", "setup_error": "missing"},
    )

    result = await service.create_package(
        "attention-survey",
        PackageRequest(approval_id=approval.id, targets=["docx", "latex", "html", "pdf"]),
    )

    assert result.status == "created"
    assert result.outputs["docx"].status == "created"
    assert result.outputs["latex"].status == "created"
    assert result.outputs["html"].status == "created"
    assert result.outputs["pdf"].status == "compiler-missing"
    assert result.outputs["pdf"].message == "PDF export needs a LaTeX compiler; download the LaTeX source instead."
    assert result.outputs["pdf"].download_path == result.outputs["latex"].path


@pytest.mark.asyncio
async def test_hl_write_33_cross_references_are_consistent_across_targets(session, tmp_path):
    _write_manuscript(tmp_path)
    approval = await _approved(session, "attention-survey")
    service = ManuscriptPackageService(
        tmp_path,
        session,
        latex_detector=lambda: {"available": False, "toolchain": "", "path": "", "setup_error": "missing"},
    )

    result = await service.create_package("attention-survey", PackageRequest(approval_id=approval.id))

    html = Path(result.outputs["html"].path).read_text(encoding="utf-8")
    tex = Path(result.outputs["latex"].path).read_text(encoding="utf-8")
    docx_text = _docx_text(Path(result.outputs["docx"].path))
    for rendered in (html, tex, docx_text):
        assert "Figure 2" in rendered
        assert "@fig:" not in rendered
        assert "??" not in rendered


@pytest.mark.asyncio
async def test_hl_write_34_unresolved_citations_block_until_acknowledged(session, tmp_path):
    _write_manuscript(tmp_path, missing_citation=True)
    approval = await _approved(session, "attention-survey")
    service = ManuscriptPackageService(
        tmp_path,
        session,
        latex_detector=lambda: {"available": False, "toolchain": "", "path": "", "setup_error": "missing"},
    )

    blocked = await service.create_package("attention-survey", PackageRequest(approval_id=approval.id))
    assert blocked.status == "validation_blocked"
    assert blocked.validation.unresolved_citation_keys == ["missingkey"]

    approval2 = await _approved(session, "attention-survey")
    created = await service.create_package(
        "attention-survey",
        PackageRequest(approval_id=approval2.id, acknowledge_citation_issues=True),
    )
    assert created.status == "created"


@pytest.mark.asyncio
async def test_hl_write_35_hl_write_36_package_embeds_ledger_and_manifest(session, tmp_path):
    _write_manuscript(tmp_path)
    approval = await _approved(session, "attention-survey")
    service = ManuscriptPackageService(
        tmp_path,
        session,
        latex_detector=lambda: {"available": False, "toolchain": "", "path": "", "setup_error": "missing"},
    )

    result = await service.create_package("attention-survey", PackageRequest(approval_id=approval.id, targets=["docx", "html"]))

    assert result.status == "created"
    html = Path(result.outputs["html"].path).read_text(encoding="utf-8")
    assert "Authorship and AI-contribution ledger" in html
    assert "Introduction: human" in html
    assert "Related Work: assistant" in html
    manifest = json.loads(Path(result.manifest_path).read_text(encoding="utf-8"))
    assert manifest["manuscript_id"] == "attention-survey"
    assert manifest["export_targets"] == ["docx", "html"]
    assert manifest["template"] == "generic-academic"
    assert manifest["cited_sources"][0]["title"] == "Attention Is All You Need"


@pytest.mark.asyncio
async def test_hl_write_37_package_and_external_submission_require_approval_and_audit(session, tmp_path):
    _write_manuscript(tmp_path)
    service = ManuscriptPackageService(
        tmp_path,
        session,
        latex_detector=lambda: {"available": False, "toolchain": "", "path": "", "setup_error": "missing"},
    )

    package = await service.create_package("attention-survey", PackageRequest())
    submission = await service.request_external_submission("attention-survey", venue="preprint")

    assert package.status == "approval_required"
    assert package.gate is not None
    assert submission.status == "approval_required"
    audit = (await session.exec(select(AgentAuditLedgerEntry))).all()
    assert {row.action for row in audit} >= {"manuscript_package_create", "external_submission"}
    assert all(row.target == "attention-survey" for row in audit)


@pytest.mark.asyncio
async def test_hl_write_38_redaction_blocks_until_hazards_acknowledged(session, tmp_path):
    _write_manuscript(tmp_path, hazards=True)
    approval = await _approved(session, "attention-survey")
    service = ManuscriptPackageService(
        tmp_path,
        session,
        latex_detector=lambda: {"available": False, "toolchain": "", "path": "", "setup_error": "missing"},
    )

    blocked = await service.create_package("attention-survey", PackageRequest(approval_id=approval.id))

    assert blocked.status == "redaction_blocked"
    categories = {item.category for item in blocked.redaction.items}
    assert {"internal_logs", "private_notes"} <= categories

    approval2 = await _approved(session, "attention-survey")
    created = await service.create_package(
        "attention-survey",
        PackageRequest(
            approval_id=approval2.id,
            acknowledged_redaction_item_ids=[item.id for item in blocked.redaction.items],
        ),
    )
    assert created.status == "created"


def test_hl_lic_30_export_path_bundles_no_strong_copyleft_dependency():
    deps = bundled_export_dependencies()
    assert any(dep["name"] == "citeproc-py" and dep["spdx"].startswith("BSD") for dep in deps)
    assert not any("GPL" in dep["spdx"] or "AGPL" in dep["spdx"] for dep in deps if dep["scope"] == "bundled-dependency")


def _docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        xml = archive.read("word/document.xml").decode("utf-8")
    return xml
