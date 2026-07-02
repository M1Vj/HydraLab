"""Capture, untrusted routing, and source promotion for browser automation."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.agents.policy import TRUST_UNTRUSTED
from hydra.autonomy.gate import ActionGate, GateResult, GovernedAction
from hydra.browser_automation.driver import DriverPage
from hydra.browser_bridge import TRUST_LEVEL_UNTRUSTED, detect_source_metadata, source_id_from_metadata
from hydra.database.models import BrowserEvent
from hydra.database.repository import Repository
from hydra.services.browser.trust import motivating_excerpt


@dataclass(frozen=True)
class SourcePromotionRequest:
    project_id: str
    title: str
    url: str
    origin_event_id: str | None
    abstract: str = ""


class BrowserCaptureService:
    def __init__(self, session: AsyncSession, *, artifact_root: Path | None = None, gate: ActionGate | None = None) -> None:
        self.session = session
        self.artifact_root = artifact_root or Path.cwd()
        self.repo = Repository(session)
        self.gate = gate or ActionGate(session)

    async def capture_page(
        self,
        *,
        project_id: str,
        run_id: str,
        mode: str,
        task_group_id: str,
        task_group_label: str,
        page: DriverPage,
    ) -> dict[str, Any]:
        snapshot_ref = self._write_snapshot(project_id, page)
        metadata = detect_source_metadata(page.url, page.title, page.text)
        metadata.update(
            {
                "trust_level": TRUST_LEVEL_UNTRUSTED,
                "originating_run_id": run_id,
                "snapshot_ref": snapshot_ref,
                "task_group_id": task_group_id,
                "task_group_label": task_group_label,
                "derived_trust_level": TRUST_LEVEL_UNTRUSTED,
            }
        )
        event = await self.repo.upsert_browser_event(
            {
                "project_id": project_id,
                "url": page.url,
                "title": page.title,
                "page_text": snapshot_ref,
                "selection": "",
                "event_type": "snapshot",
                "detected_metadata": metadata,
            }
        )
        metadata["origin_browser_event_id"] = event["id"]
        row = await self.session.get(BrowserEvent, event["id"])
        if row is not None:
            row.detected_metadata = json.dumps(metadata, sort_keys=True)
            self.session.add(row)
            await self.session.commit()
            await self.session.refresh(row)
            event = self.repo._to_dict(row)  # noqa: SLF001 - repository owns API conversion.
        return event

    async def record_host_blocked(
        self,
        *,
        project_id: str,
        run_id: str,
        url: str,
        host: str,
        reason: str,
    ) -> dict[str, Any]:
        return await self.repo.upsert_browser_event(
            {
                "project_id": project_id,
                "url": url,
                "title": f"Blocked host: {host}",
                "page_text": "",
                "selection": "",
                "event_type": "host-blocked",
                "detected_metadata": {
                    "trust_level": TRUST_LEVEL_UNTRUSTED,
                    "originating_run_id": run_id,
                    "host": host,
                    "reason": reason,
                },
            }
        )

    async def route_untrusted_promotion(
        self,
        *,
        project_id: str,
        run_id: str,
        mode: str,
        url: str,
        page_text: str,
        proposed_action: str,
        origin_event_id: str,
    ) -> GateResult:
        return await self.gate.govern(
            GovernedAction(
                mode=mode,
                action_kind=f"browser.{proposed_action}",
                target_kind="browser_page",
                target_ref=url,
                trust_origin=TRUST_UNTRUSTED,
                justification_trust=TRUST_UNTRUSTED,
                run_id=run_id,
                project_id=project_id,
                summary="Review untrusted browser page proposal",
                payload={
                    "origin_event_id": origin_event_id,
                    "origin_url": url,
                    "trust_level": TRUST_LEVEL_UNTRUSTED,
                    "motivating_excerpt": motivating_excerpt(page_text),
                },
            )
        )

    async def promote_source(self, request: SourcePromotionRequest) -> dict[str, Any]:
        if not request.origin_event_id:
            raise ValueError("source promotion requires an originating ledger event")
        event = await self.session.get(BrowserEvent, request.origin_event_id)
        if event is None or event.project_id != request.project_id:
            raise ValueError("source promotion requires an originating ledger event")
        metadata = detect_source_metadata(request.url, request.title, request.abstract)
        source_metadata = {
            **metadata,
            "origin_url": request.url,
            "origin_browser_event_id": event.id,
            "origin_snapshot_ref": event.captured_text_ref,
            "trust_level": TRUST_LEVEL_UNTRUSTED,
        }
        return await self.repo.upsert_source(
            {
                "id": source_id_from_metadata(metadata, request.url),
                "project_id": request.project_id,
                "title": request.title or request.url,
                "url": request.url,
                "abstract": request.abstract,
                "kind": "browser-source",
                "source_type": "web",
                "doi": metadata.get("doi"),
                "arxiv_id": metadata.get("arxiv_id"),
                "metadata_json": json.dumps(source_metadata, sort_keys=True),
                "trust_origin": TRUST_LEVEL_UNTRUSTED,
            }
        )

    def _write_snapshot(self, project_id: str, page: DriverPage) -> str:
        safe_project = re.sub(r"[^a-zA-Z0-9_.-]+", "_", project_id).strip("_") or "default"
        rel = Path(".hydralab") / "browser" / safe_project / f"{uuid.uuid4().hex}.html"
        path = self.artifact_root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        content = page.snapshot_bytes or page.text.encode()
        path.write_bytes(content)
        return rel.as_posix()
