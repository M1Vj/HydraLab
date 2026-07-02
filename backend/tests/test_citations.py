"""Branch 01-09 citation tests. Each @HL-* scenario maps to one test."""
import importlib.util
import json

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlmodel import SQLModel
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.orm import sessionmaker

from hydra.app import create_app
from hydra.database.models import Annotation, Claim, EvidenceLink, Source, SourceTombstone
from hydra.database.repository import Repository
from hydra.services.citations import (
    CSL_PROCESSOR,
    DEFAULT_STYLE_ID,
    CitationParseError,
    CslRenderer,
    bibtex_to_csl_json,
    citation_key,
    csl_json_to_bibtex,
)


ATTENTION_BIBTEX = """@article{vaswani2017attention,
  title = {Attention Is All You Need},
  author = {Vaswani, Ashish and Shazeer, Noam and Parmar, Niki},
  year = {2017},
  journal = {NeurIPS},
  doi = {10.48550/arXiv.1706.03762}
}
"""


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


# --- @HL-CITE-01 -------------------------------------------------------------
def test_hl_cite_01_import_bibtex_creates_source_with_csl_json(tmp_path, monkeypatch):
    monkeypatch.setenv("HYDRA_HOME", str(tmp_path))
    client = TestClient(create_app())

    result = client.post("/api/sources/import", json={"format": "bibtex", "content": ATTENTION_BIBTEX})
    assert result.status_code == 200

    sources = client.get("/api/project/objects").json()["objects"]["sources"]
    match = next(s for s in sources if s["title"] == "Attention Is All You Need")
    assert match["csl_json"]
    assert match["csl_json"].get("title") == "Attention Is All You Need"
    assert match["doi"] == "10.48550/arXiv.1706.03762"

    exported = client.get("/api/sources/export?fmt=bibtex").text
    assert "Attention Is All You Need" in exported
    assert "10.48550/arXiv.1706.03762" in exported


# --- @HL-CITE-02 -------------------------------------------------------------
def test_hl_cite_02_import_without_zotero(tmp_path, monkeypatch):
    monkeypatch.setenv("HYDRA_HOME", str(tmp_path))
    # Zotero is neither installed nor importable in this environment.
    assert importlib.util.find_spec("zotero") is None
    client = TestClient(create_app())

    library = [
        {
            "id": f"ref-{i}",
            "type": "article-journal",
            "title": f"Reference number {i}",
            "author": [{"family": f"Author{i}", "given": "A."}],
            "issued": {"date-parts": [[2000 + (i % 25)]]},
            "DOI": f"10.1234/ref.{i}",
        }
        for i in range(50)
    ]
    result = client.post("/api/sources/import", json={"format": "csl-json", "content": json.dumps(library)})
    assert result.status_code == 200
    assert result.json()["count"] == 50
    assert result.json()["format"] == "csl-json"

    sources = client.get("/api/project/objects").json()["objects"]["sources"]
    assert len([s for s in sources if s["title"].startswith("Reference number")]) == 50


# --- @HL-CITE-04 (exact identifier) ------------------------------------------
@pytest.mark.asyncio
async def test_hl_cite_04_shared_doi_is_auto_merge_eligible(session: AsyncSession):
    repo = Repository(session)
    await repo.upsert_source({"id": "s-a", "title": "KG Embeddings", "doi": "10.1145/3292500.3330701"})
    await repo.upsert_source({"id": "s-b", "title": "KG Embeddings (v2)", "doi": "10.1145/3292500.3330701"})

    verdicts = await repo.detect_duplicates()
    pair = next(v for v in verdicts if {v["left_id"], v["right_id"]} == {"s-a", "s-b"})
    assert pair["status"] == "auto_merge"
    assert pair["reason"] == "exact_identifier"
    assert (await session.get(Source, "s-a")).duplicate_status != "needs_review"


# --- @HL-CITE-04 (fuzzy) -----------------------------------------------------
@pytest.mark.asyncio
async def test_hl_cite_04_fuzzy_duplicate_requires_review(session: AsyncSession):
    repo = Repository(session)
    await repo.upsert_source({"id": "f-a", "title": "Deep Residual Learning for Image Recognition", "year": "2016", "authors": "He, Kaiming"})
    await repo.upsert_source({"id": "f-b", "title": "Deep Residual Learning for Image Recognitions", "year": "2016", "authors": "He, Kaiming"})

    verdicts = await repo.detect_duplicates()
    pair = next(v for v in verdicts if {v["left_id"], v["right_id"]} == {"f-a", "f-b"})
    assert pair["status"] == "needs_review"
    assert (await session.get(Source, "f-a")).duplicate_status == "needs_review"
    # No merge occurred.
    assert (await session.get(Source, "f-a")).merged_into_source_id is None
    assert (await session.get(Source, "f-b")).merged_into_source_id is None


# --- @HL-CITE-12 -------------------------------------------------------------
@pytest.mark.asyncio
async def test_hl_cite_12_fuzzy_proposal_in_review_inbox_and_inline(session: AsyncSession):
    repo = Repository(session)
    await repo.upsert_source({"id": "p-a", "title": "Attention Is All You Need", "year": "2017", "authors": "Vaswani, Ashish"})
    await repo.upsert_source({"id": "p-b", "title": "Attention Is All You Needed", "year": "2017", "authors": "Vaswani, Ashish"})

    await repo.detect_duplicates()
    proposals = await repo.list_review_items(item_type="duplicate-merge-proposal")
    assert proposals
    assert {proposals[0]["origin_id"], proposals[0]["target_id"]} == {"p-a", "p-b"}
    # Inline badge data: the source carries a duplicate_status the panel renders.
    assert (await session.get(Source, "p-a")).duplicate_status == "needs_review"


# --- @HL-REFINT-01 -----------------------------------------------------------
@pytest.mark.asyncio
async def test_hl_refint_01_merge_repoints_evidence_to_survivor(session: AsyncSession):
    repo = Repository(session)
    survivor = Source(id="00000000-0000-0000-0000-0000000000a1", title="Attention", doi="10.1145/3292500.3330701")
    duplicate = Source(id="00000000-0000-0000-0000-0000000000a2", title="Attention dup", doi="10.1145/3292500.3330701")
    claim = Claim(id="c-refint-1", text="Transformers use attention.")
    evidence = EvidenceLink(claim_id=claim.id, source_id=duplicate.id, passage="q", support="supported", confidence=0.9, review_status="accepted")
    session.add_all([survivor, duplicate, claim, evidence])
    await session.commit()

    result = await repo.merge_sources([survivor.id, duplicate.id], reason="exact_identifier")

    assert result["survivor_id"] == survivor.id
    assert (await session.get(EvidenceLink, evidence.id)).source_id == survivor.id
    assert await session.get(SourceTombstone, duplicate.id)
    assert await repo.count_references_to_source(duplicate.id) == 0


# --- @HL-REFINT-02 (rollback) ------------------------------------------------
@pytest.mark.asyncio
async def test_hl_refint_02_merge_rolls_back_on_dangling(session: AsyncSession, monkeypatch):
    repo = Repository(session)
    survivor = Source(id="00000000-0000-0000-0000-0000000000b1", title="Attention", doi="10.1/x")
    duplicate = Source(id="00000000-0000-0000-0000-0000000000b2", title="Attention dup", doi="10.1/x")
    ev = EvidenceLink(claim_id="c-x", source_id=duplicate.id, passage="q", support="supported", confidence=0.9, review_status="accepted")
    session.add_all([survivor, duplicate, Claim(id="c-x", text="x"), ev])
    await session.commit()
    survivor_id, duplicate_id, ev_id = survivor.id, duplicate.id, ev.id

    async def missed(_old, _new):
        return None

    monkeypatch.setattr(repo, "_repoint_source_references", missed)
    with pytest.raises(RuntimeError, match="dangling references remain"):
        await repo.merge_sources([survivor_id, duplicate_id], reason="exact_identifier")

    assert (await session.get(Source, duplicate_id)).trashed is False
    assert (await session.get(EvidenceLink, ev_id)).source_id == duplicate_id


# --- @HL-REFINT-02 (reversible) ----------------------------------------------
@pytest.mark.asyncio
async def test_hl_refint_02_merge_is_reversible(session: AsyncSession):
    repo = Repository(session)
    survivor = Source(id="00000000-0000-0000-0000-0000000000c1", title="Attention", doi="10.2/y")
    duplicate = Source(id="00000000-0000-0000-0000-0000000000c2", title="Attention dup", doi="10.2/y")
    claim = Claim(id="c-rev", text="reversible")
    evidence = EvidenceLink(claim_id=claim.id, source_id=duplicate.id, passage="q", support="supported", confidence=0.9, review_status="accepted")
    session.add_all([survivor, duplicate, claim, evidence])
    await session.commit()

    result = await repo.merge_sources([survivor.id, duplicate.id], reason="exact_identifier")
    assert (await session.get(EvidenceLink, evidence.id)).source_id == survivor.id

    undo = await repo.unmerge_sources(result["merge_record_id"])
    assert undo["reversed"] is True
    assert (await session.get(Source, duplicate.id)).trashed is False
    assert (await session.get(EvidenceLink, evidence.id)).source_id == duplicate.id
    assert await session.get(SourceTombstone, duplicate.id) is None


# --- @HL-CITE-03 -------------------------------------------------------------
@pytest.mark.asyncio
async def test_hl_cite_03_key_dedupe_keeps_all_links(session: AsyncSession):
    repo = Repository(session)
    csl = {"title": "Attention Is All You Need", "issued": {"date-parts": [[2017]]}, "author": [{"family": "Vaswani", "given": "Ashish"}]}
    key = citation_key(csl)
    assert key == "vaswani2017attention"

    await repo.upsert_source({"id": "k-a", "title": "Attention Is All You Need", "csl_json": csl, "metadata_sources_json": json.dumps(["openalex"])})
    await repo.upsert_source({"id": "k-b", "title": "Attention Is All You Need", "csl_json": csl, "metadata_sources_json": json.dumps(["crossref"])})
    claim = Claim(id="k-claim", text="attention")
    evidence = EvidenceLink(claim_id=claim.id, source_id="k-b", passage="quote", support="supported", confidence=0.9, review_status="accepted")
    annotation = Annotation(sidecar_record_id="k-ann", source_id="k-b", page=1, text="provenance note")
    session.add_all([claim, evidence, annotation])
    await session.commit()

    merges = await repo.dedupe_by_citation_key()
    assert merges and merges[0]["citation_key"] == "vaswani2017attention"
    survivor_id = merges[0]["survivor_id"]

    assert (await session.get(EvidenceLink, evidence.id)).source_id == survivor_id
    assert (await session.get(Annotation, "k-ann")).source_id == survivor_id
    survivor = await repo.list_sources()
    survivor_row = next(s for s in survivor if s["id"] == survivor_id)
    assert set(survivor_row["metadata_sources"]) >= {"openalex", "crossref"}


# --- @HL-CITE-05 -------------------------------------------------------------
def test_hl_cite_05_style_switch_changes_bibliography():
    item = {
        "id": "vaswani",
        "type": "article-journal",
        "title": "Attention Is All You Need",
        "author": [{"family": "Vaswani", "given": "Ashish"}],
        "issued": {"date-parts": [[2017]]},
        "container-title": "NeurIPS",
    }
    renderer = CslRenderer()
    apa = renderer.render_bibliography([item], "apa")
    ieee = renderer.render_bibliography([item], "ieee")
    assert apa and ieee
    assert apa[0] != ieee[0]


def test_hl_cite_05_render_escapes_hostile_metadata():
    item = {
        "id": "x",
        "type": "article-journal",
        "title": "<script>alert('xss')</script> Attention",
        "author": [{"family": "Vaswani", "given": "Ashish"}],
        "issued": {"date-parts": [[2017]]},
    }
    html = CslRenderer().render_bibliography_html([item], "apa")
    assert "<script>" not in html[0]
    assert "&lt;script&gt;" in html[0]


# --- @HL-CITE-13 -------------------------------------------------------------
def test_hl_cite_13_malformed_bibtex_is_contained(tmp_path, monkeypatch):
    monkeypatch.setenv("HYDRA_HOME", str(tmp_path))
    client = TestClient(create_app())
    client.post("/api/sources/import", json={"format": "bibtex", "content": ATTENTION_BIBTEX})
    before = client.get("/api/project/objects").json()["counts"]["sources"]

    malformed = "@article{broken2020,\n  title = {Unterminated entry,\n  author = {No Close Brace}\n"
    response = client.post("/api/sources/import", json={"format": "bibtex", "content": malformed})
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["reason"] == "parse-error"
    assert detail["entry"] == "broken2020"

    after = client.get("/api/project/objects").json()["counts"]["sources"]
    assert after == before  # existing sources untouched


def test_malformed_bibtex_raises_named_entry():
    with pytest.raises(CitationParseError) as exc:
        bibtex_to_csl_json("@article{broken2020,\n  title = {Unterminated,\n")
    assert exc.value.entry == "broken2020"


# --- @HL-LIC-01 (backend half; JS-bundle grep is the build gate) -------------
def test_hl_lic_01_permissive_processor_and_no_citeproc_js():
    assert CSL_PROCESSOR == "citeproc-py"
    assert DEFAULT_STYLE_ID == "apa"
    # citeproc-py is importable; citeproc-js has no Python module and is not a dep.
    assert importlib.util.find_spec("citeproc") is not None
    # No Python binding for citeproc-js is installed as a dependency.
    assert importlib.util.find_spec("citeproc_js") is None
    render_source = __import__("hydra.services.citations.render", fromlist=["__file__"]).__file__
    with open(render_source, "r", encoding="utf-8") as handle:
        code_lines = [line for line in handle if line.lstrip().startswith(("import ", "from "))]
    assert not any("citeproc_js" in line or "citeprocjs" in line for line in code_lines)


def test_bibtex_roundtrip_equivalent():
    items = bibtex_to_csl_json(ATTENTION_BIBTEX)
    assert items[0]["title"] == "Attention Is All You Need"
    exported = csl_json_to_bibtex(items)
    reparsed = bibtex_to_csl_json(exported)
    assert reparsed[0]["title"] == "Attention Is All You Need"
    assert reparsed[0]["DOI"] == "10.48550/arXiv.1706.03762"
