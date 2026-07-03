import asyncio

from fastapi.testclient import TestClient

from hydra.app import create_app, hydra_project_root
from hydra.database.session import get_session_maker
from hydra.services.ingestion.worker import process_next_job


def _drain_one() -> object:
    async def drain():
        maker = get_session_maker()
        async with maker() as session:
            return await process_next_job(session, project_root=hydra_project_root())

    return asyncio.run(drain())


def test_background_ingest_enqueues_then_worker_completes(tmp_path, monkeypatch):
    monkeypatch.setenv("HYDRA_HOME", str(tmp_path))
    client = TestClient(create_app())

    body = b"# Queued Paper\n\nRetrieval augmented generation notes for the queue.\n"
    resp = client.post(
        "/api/sources/ingest",
        files={"file": ("queued.md", body, "text/markdown")},
        data={"background": "true"},
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["ingestion"]["state"] == "queued"
    job_id = payload["ingestion"]["job_id"]
    source_id = payload["source"]["id"]

    queued = client.get("/api/ingestion/jobs").json()["jobs"]
    assert any(job["id"] == job_id and job["status"] == "queued" for job in queued)

    # The background loop is not started for a bare TestClient, so drive the
    # worker directly against the same database.
    result = _drain_one()
    assert result is not None
    assert result["state"] == "done"

    done = client.get("/api/ingestion/jobs").json()["jobs"]
    assert any(job["id"] == job_id and job["status"] == "done" for job in done)

    # The queued conversion actually indexed the source: retrieval now finds it.
    retrieved = client.get("/api/sources/retrieve", params={"query": "retrieval augmented generation"}).json()
    assert any(hit["source_id"] == source_id for hit in retrieved["hits"])

    # An empty queue is a no-op.
    assert _drain_one() is None


def test_ingestion_job_lifecycle_endpoints(tmp_path, monkeypatch):
    monkeypatch.setenv("HYDRA_HOME", str(tmp_path))
    client = TestClient(create_app())

    body = b"# Paper\n\nContent to convert.\n"
    resp = client.post(
        "/api/sources/ingest",
        files={"file": ("paper.md", body, "text/markdown")},
        data={"background": "true"},
    )
    job_id = resp.json()["ingestion"]["job_id"]

    assert client.post(f"/api/ingestion/jobs/{job_id}/pause").json()["job"]["status"] == "paused"
    assert client.post(f"/api/ingestion/jobs/{job_id}/resume").json()["job"]["status"] == "queued"
    assert client.patch(f"/api/ingestion/jobs/{job_id}/priority", params={"priority": 5}).json()["job"]["priority"] == 5
    cancelled = client.post(f"/api/ingestion/jobs/{job_id}/cancel").json()["job"]
    assert cancelled["status"] == "failed"
    assert cancelled["failure_reason"] == "cancelled"
    # Retry revives a cancelled job back into the queue.
    retried = client.post(f"/api/ingestion/jobs/{job_id}/retry").json()["job"]
    assert retried["status"] == "queued"
    assert retried["retry_count"] == 1

    assert client.post("/api/ingestion/jobs/does-not-exist/pause").status_code == 404


def test_resume_after_restart_requeues_interrupted_jobs(tmp_path, monkeypatch):
    monkeypatch.setenv("HYDRA_HOME", str(tmp_path))
    client = TestClient(create_app())
    body = b"# Paper\n\nContent.\n"
    job_id = client.post(
        "/api/sources/ingest",
        files={"file": ("paper.md", body, "text/markdown")},
        data={"background": "true"},
    ).json()["ingestion"]["job_id"]

    from hydra.database.models import IngestionJob
    from hydra.services.ingestion.queue import IngestionQueue

    async def crash_then_recover():
        maker = get_session_maker()
        async with maker() as session:
            job = await session.get(IngestionJob, job_id)
            job.status = "running"  # simulate a crash mid-conversion
            session.add(job)
            await session.commit()
        async with maker() as session:
            await IngestionQueue(session).resume_after_restart()

    asyncio.run(crash_then_recover())

    jobs = client.get("/api/ingestion/jobs").json()["jobs"]
    assert next(job for job in jobs if job["id"] == job_id)["status"] == "queued"
