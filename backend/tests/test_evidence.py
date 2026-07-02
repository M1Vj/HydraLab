import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlmodel import SQLModel
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.orm import sessionmaker

from hydra.app import create_app
from hydra.database.models import Annotation, Claim, EvidenceLink, Source
from hydra.database.repository import Repository


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()

def test_claims_citations_and_evidence(tmp_path, monkeypatch):
    monkeypatch.setenv("HYDRA_HOME", str(tmp_path))
    client = TestClient(create_app())

    # Create a claim
    claim = client.post("/api/claims", json={"text": "This is a test claim."}).json()
    assert claim["text"] == "This is a test claim."

    # Create a source
    source = client.post("/api/sources/search", json={"query": "test source"}).json()["sources"][0]

    # Create a citation
    citation = client.post("/api/citations", json={"source_id": source["id"], "text": "This is a citation."}).json()
    assert citation["text"] == "This is a citation."
    assert citation["source_id"] == source["id"]

    # Link evidence
    evidence = client.post(
        "/api/evidence",
        json={
            "claim_id": claim["id"],
            "citation_id": citation["id"],
            "source_id": source["id"],
            "passage": "This passage supports the claim.",
            "support": "supported",
            "confidence": 0.95
        }
    ).json()

    assert evidence["claim_id"] == claim["id"]
    assert evidence["citation_id"] == citation["id"]
    assert evidence["support"] == "supported"

    # Test lists
    claims_list = client.get("/api/claims").json()["claims"]
    assert len(claims_list) == 1
    assert claims_list[0]["id"] == claim["id"]

    citations_list = client.get("/api/citations").json()["citations"]
    assert len(citations_list) == 1
    assert citations_list[0]["id"] == citation["id"]

    evidence_list = client.get("/api/evidence").json()["evidence"]
    assert len(evidence_list) == 1
    assert evidence_list[0]["id"] == evidence["id"]

def test_detect_claims_is_suggestion_only(tmp_path, monkeypatch):
    monkeypatch.setenv("HYDRA_HOME", str(tmp_path))
    client = TestClient(create_app())

    response = client.post(
        "/api/claims/detect",
        json={"text": "Self-attention scales sub-quadratically with sequence length."},
    )
    assert response.status_code == 200
    data = response.json()

    # HL-CITE-07: extraction is suggestion-only by default; nothing is committed.
    assert data["committed"] is False
    assert data["created_claims"] == []
    assert len(data["suggestions"]) >= 1
    assert data["suggestions"][0]["extraction_mode"] == "suggested"

    # No claim row was written to the project.
    assert client.get("/api/claims").json()["claims"] == []


# --- @HL-CITE-06: claim CRUD + location_id resolver ------------------------
@pytest.mark.asyncio
async def test_hl_cite_06_claim_location_resolver(session: AsyncSession):
    repo = Repository(session)
    await repo.upsert_source({"id": "src-loc", "title": "Attention Is All You Need"})
    claim = await repo.add_claim(text="Attention scales", location_type="source", location_id="src-loc")
    assert claim["claim_text"] == "Attention scales"
    assert claim["status"] == "draft"

    resolved = await repo.resolve_claim_location("source", "src-loc")
    assert resolved["resolved"] is True
    assert resolved["target"]["id"] == "src-loc"

    missing = await repo.resolve_claim_location("source", "does-not-exist")
    assert missing["resolved"] is False
    assert missing["reason"] == "not-found"


@pytest.mark.asyncio
async def test_hl_cite_06_claim_requires_matching_location_pair(session: AsyncSession):
    repo = Repository(session)
    with pytest.raises(ValueError):
        await repo.add_claim(text="dangling", location_type="source", location_id=None)


# --- @HL-CITE-08: opt-in auto-draft ----------------------------------------
def test_hl_cite_08_auto_draft_only_when_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("HYDRA_HOME", str(tmp_path))
    client = TestClient(create_app())

    off = client.post("/api/claims/detect", json={"text": "Softmax normalizes attention weights across the sequence."}).json()
    assert off["committed"] is False
    assert client.get("/api/claims").json()["claims"] == []

    on = client.post(
        "/api/claims/detect",
        json={"text": "Softmax normalizes attention weights across the sequence.", "auto_create": True},
    ).json()
    assert on["committed"] is True
    created = on["created_claims"][0]
    assert created["status"] == "draft"
    assert created["extraction_mode"] == "auto_draft"
    assert created["status"] != "supported"


# --- @HL-CITE-09: evidence-required promotion ------------------------------
def test_hl_cite_09_cannot_promote_without_evidence(tmp_path, monkeypatch):
    monkeypatch.setenv("HYDRA_HOME", str(tmp_path))
    client = TestClient(create_app())

    claim = client.post("/api/claims", json={"text": "Self-attention scales sub-quadratically with sequence length."}).json()
    response = client.patch(f"/api/claims/{claim['id']}", json={"status": "supported", "reviewed": True})
    assert response.status_code == 422
    assert "evidence" in response.json()["detail"].lower()
    assert client.get("/api/claims").json()["claims"][0]["status"] == "draft"


@pytest.mark.asyncio
async def test_hl_cite_09_promotion_requires_review_even_with_evidence(session: AsyncSession):
    repo = Repository(session)
    await repo.upsert_source({"id": "s-prom", "title": "Attention"})
    claim = await repo.add_claim(text="attention", location_type="source", location_id="s-prom")
    await repo.add_evidence(claim_id=claim["id"], source_id="s-prom", passage="q", support="supported", confidence=0.9)

    with pytest.raises(ValueError, match="review"):
        await repo.promote_claim(claim["id"], "supported", reviewed=False)

    promoted = await repo.promote_claim(claim["id"], "supported", reviewed=True)
    assert promoted["status"] == "supported"


# --- @HL-CITE-10: evidence paragraph locator + support level + confidence ---
def test_hl_cite_10_evidence_records_paragraph_locator(tmp_path, monkeypatch):
    monkeypatch.setenv("HYDRA_HOME", str(tmp_path))
    client = TestClient(create_app())

    source = client.post("/api/sources/search", json={"query": "attention"}).json()["sources"][0]
    claim = client.post("/api/claims", json={"text": "Self-attention scales sub-quadratically with sequence length."}).json()
    evidence = client.post(
        "/api/evidence",
        json={
            "claim_id": claim["id"],
            "source_id": source["id"],
            "passage": "attention weights",
            "support": "supported",
            "support_level": "supports",
            "confidence": 0.85,
            "locator": {"type": "paragraph", "section": "3.2 Scaled Dot-Product Attention", "paragraph": 3},
        },
    ).json()

    assert evidence["support_level"] == "supports"
    assert evidence["confidence"] == 0.85
    assert evidence["locator"]["type"] == "paragraph"
    assert evidence["locator"]["paragraph"] == 3


# --- @HL-CITE-11: sidecar_record_id survives merge -------------------------
@pytest.mark.asyncio
async def test_hl_cite_11_sidecar_record_id_survives_merge(session: AsyncSession):
    repo = Repository(session)
    survivor = Source(id="00000000-0000-0000-0000-0000000000d1", title="Attention", doi="10.9/z")
    duplicate = Source(id="00000000-0000-0000-0000-0000000000d2", title="Attention dup", doi="10.9/z")
    claim = Claim(id="c-sidecar", text="from highlight", location_type="source", location_id=duplicate.id)
    annotation = Annotation(sidecar_record_id="sidecar-uuid-1", source_id=duplicate.id, page=3, text="highlight")
    evidence = EvidenceLink(
        claim_id=claim.id,
        source_id=duplicate.id,
        passage="highlight",
        support="supported",
        confidence=0.8,
        review_status="needs_review",
        annotation_id="sidecar-uuid-1",
        sidecar_record_id="sidecar-uuid-1",
        sidecar_path="sources/papers/annotations/dup.annotations.json",
    )
    session.add_all([survivor, duplicate, claim, annotation, evidence])
    await session.commit()

    await repo.merge_sources([survivor.id, duplicate.id], reason="exact_identifier")

    refreshed = await session.get(EvidenceLink, evidence.id)
    assert refreshed.sidecar_record_id == "sidecar-uuid-1"
    assert refreshed.annotation_id == "sidecar-uuid-1"
    assert refreshed.source_id == survivor.id


# --- @HL-REFINT-03: trash cited source --------------------------------------
@pytest.mark.asyncio
async def test_hl_refint_03_trash_cited_source_soft_marks_claim(session: AsyncSession):
    repo = Repository(session)
    source = Source(id="s-trash", title="Attention Is All You Need")
    claim = Claim(id="c-trash", text="attention", location_type="source", location_id=source.id)
    evidence = EvidenceLink(claim_id=claim.id, source_id=source.id, passage="q", support="supported", confidence=0.9, review_status="accepted")
    session.add_all([source, claim, evidence])
    await session.commit()

    warn = await repo.trash_source(source.id, confirmed=False)
    assert warn["requires_confirmation"] is True
    assert warn["dependent_counts"]["claims"] == 1

    done = await repo.trash_source(source.id, confirmed=True)
    assert done["trashed"] is True
    assert (await session.get(Claim, claim.id)).link_state == "target_trashed"

    # Not auto-promoted while its target is trashed.
    with pytest.raises(ValueError):
        await repo.promote_claim(claim.id, "supported", reviewed=True)
    assert (await session.get(Claim, claim.id)).status == "draft"


# --- @HL-REFINT-04: referential-integrity scan ------------------------------
@pytest.mark.asyncio
async def test_hl_refint_04_scan_surfaces_broken_links(session: AsyncSession):
    repo = Repository(session)
    claim = Claim(id="c-dangling", text="orphan", location_type="source", location_id="ghost-source")
    session.add(claim)
    await session.commit()

    findings = await repo.scan_referential_integrity()
    assert any(f["origin_id"] == "c-dangling" and f["target_id"] == "ghost-source" for f in findings)
    inbox = await repo.list_review_items(item_type="broken-link")
    assert any(item["origin_id"] == "c-dangling" for item in inbox)
