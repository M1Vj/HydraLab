from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlmodel import delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.database.models import Citation, KgEdge, Note, ReviewItem, Source
from hydra.settings.project_config import default_project_config, load_project_config


WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
CITATION_RE = re.compile(r"\[@([A-Za-z0-9_:.#/-]+)\]")
CALLOUT_RE = re.compile(r"^>\s*\[!([A-Za-z0-9_-]+)\](?:\s+(.+))?$")


def parse_markdown_tokens(markdown: str) -> list[dict[str, Any]]:
    tokens: list[dict[str, Any]] = []
    offset = 0
    for line_number, line in enumerate(markdown.splitlines(keepends=True), start=1):
        line_text = line.rstrip("\r\n")
        callout = CALLOUT_RE.match(line_text)
        if callout:
            tokens.append(
                {
                    "type": "callout",
                    "kind": callout.group(1).lower(),
                    "title": (callout.group(2) or "").strip(),
                    "from": offset,
                    "to": offset + len(line_text),
                    "line": line_number,
                }
            )
        for match in WIKILINK_RE.finditer(line_text):
            tokens.append(
                {
                    "type": "wikilink",
                    "target": match.group(1).strip(),
                    "alias": (match.group(2) or "").strip(),
                    "from": offset + match.start(),
                    "to": offset + match.end(),
                    "line": line_number,
                }
            )
        for match in CITATION_RE.finditer(line_text):
            tokens.append(
                {
                    "type": "citation",
                    "key": match.group(1).strip(),
                    "from": offset + match.start(),
                    "to": offset + match.end(),
                    "line": line_number,
                }
            )
        offset += len(line)
    return sorted(tokens, key=lambda token: (token["from"], token["to"]))


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_relative_path(path: str) -> str:
    normalized = Path(path)
    if normalized.is_absolute() or ".." in normalized.parts:
        raise ValueError("note path must be project-relative")
    return normalized.as_posix()


NOTE_EXTENSIONS = {".md", ".markdown"}
PROTECTED_PATHS = {
    "HYDRA.md",
    "AGENTS.md",
    "project.yaml",
    "SOUL.md",
    "USER.md",
    "MEMORY.md",
}
PROTECTED_PREFIXES = (".git/", ".hydralab/", ".agents/")


def _is_draft_path(relative_path: str) -> bool:
    return relative_path.startswith("writing/drafts/") or relative_path.startswith("writing/manuscripts/")


def _is_under_root(relative_path: str, root: str) -> bool:
    return relative_path == root.rstrip("/") or relative_path.startswith(root)


def _split_frontmatter(content: str) -> tuple[str | None, str, str]:
    if not content.startswith("---\n"):
        return None, "", content
    close = content.find("\n---", 4)
    if close == -1:
        return None, "", content
    delimiter_end = close + len("\n---")
    if content[delimiter_end:delimiter_end + 2] == "\r\n":
        delimiter_end += 2
    elif content[delimiter_end:delimiter_end + 1] == "\n":
        delimiter_end += 1
    return content[:delimiter_end], content[4:close], content[delimiter_end:]


def _frontmatter_scalar(frontmatter_body: str, key: str) -> str | None:
    pattern = re.compile(rf"^{re.escape(key)}:\s*(.+?)\s*$", re.MULTILINE)
    match = pattern.search(frontmatter_body)
    if not match:
        return None
    value = match.group(1).strip()
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    return value


def _frontmatter_dict(frontmatter_body: str, id_key: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for key in {id_key, "title", "trust_origin"}:
        value = _frontmatter_scalar(frontmatter_body, key)
        if value is not None:
            values[key] = value
    return values


def _derive_title(relative_path: str, content: str, frontmatter_body: str) -> str:
    frontmatter_title = _frontmatter_scalar(frontmatter_body, "title")
    if frontmatter_title:
        return frontmatter_title
    for line in content.splitlines():
        if line.startswith("# "):
            return line[2:].strip() or Path(relative_path).stem
    return Path(relative_path).stem


def _ensure_frontmatter_id(content: str, id_key: str) -> tuple[str, str, bool]:
    frontmatter, body, rest = _split_frontmatter(content)
    existing = _frontmatter_scalar(body, id_key)
    if existing:
        return content, existing, False
    new_id = str(uuid.uuid4())
    if frontmatter is None:
        return f"---\n{id_key}: {new_id}\n---\n\n{content}", new_id, True
    closing = "\n---"
    close = frontmatter.rfind(closing)
    if close == -1:
        return content, new_id, False
    insertion = f"{id_key}: {new_id}\n"
    updated_frontmatter = f"{frontmatter[:close]}\n{insertion}{frontmatter[close + 1:]}"
    return f"{updated_frontmatter}{rest}", new_id, True


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    tmp_path.write_text(content)
    tmp_path.replace(path)


class NoteFileService:
    def __init__(self, session: AsyncSession, project_root: Path):
        self.session = session
        self.project_root = project_root

    async def open_note(self, relative_path: str, project_id: str = "default", trust_origin: str = "user") -> dict[str, Any]:
        rel_path = _safe_relative_path(relative_path)
        self._assert_note_path_allowed(rel_path)
        path = self.project_root / rel_path
        if not path.exists():
            raise FileNotFoundError(rel_path)
        content = path.read_text()
        object_type = "draft" if _is_draft_path(rel_path) else "note"
        id_key = "draft_id" if object_type == "draft" else "note_id"
        content_with_id, note_id, changed = _ensure_frontmatter_id(content, id_key)
        if changed:
            _atomic_write(path, content_with_id)
            content = content_with_id
        frontmatter, frontmatter_body, _rest = _split_frontmatter(content)
        frontmatter_json = json.dumps(_frontmatter_dict(frontmatter_body, id_key), sort_keys=True)
        title = _derive_title(rel_path, content, frontmatter_body)
        row = await self.session.get(Note, note_id)
        if row is None:
            row = Note(id=note_id, project_id=project_id, title=title)
        row.project_id = project_id
        row.relative_path = rel_path
        row.title = title
        row.body = content
        row.frontmatter = frontmatter_json
        row.content_hash = _sha256_text(content)
        row.trust_origin = trust_origin if trust_origin != "untrusted-external" else "untrusted"
        row.updated_at = _now()
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        await self.reindex_note(row.id)
        return self._note_payload(row, content, object_type)

    async def save_note(self, note_id: str, content: str) -> dict[str, Any]:
        row = await self.session.get(Note, note_id)
        if row is None:
            raise KeyError(note_id)
        rel_path = _safe_relative_path(row.relative_path)
        self._assert_note_path_allowed(rel_path)
        path = self.project_root / rel_path
        _atomic_write(path, content)
        frontmatter, frontmatter_body, _rest = _split_frontmatter(content)
        object_type = "draft" if _is_draft_path(row.relative_path) else "note"
        id_key = "draft_id" if object_type == "draft" else "note_id"
        row.body = content
        row.title = _derive_title(row.relative_path, content, frontmatter_body)
        row.frontmatter = json.dumps(_frontmatter_dict(frontmatter_body, id_key), sort_keys=True)
        row.content_hash = _sha256_text(content)
        row.updated_at = _now()
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        await self.reindex_note(row.id)
        return self._note_payload(row, content, object_type)

    async def reindex_note(self, note_id: str) -> list[KgEdge]:
        row = await self.session.get(Note, note_id)
        if row is None:
            raise KeyError(note_id)
        await self.session.exec(delete(KgEdge).where(KgEdge.src_id == note_id))
        tokens = parse_markdown_tokens(row.body)
        created: list[KgEdge] = []
        for token in tokens:
            if token["type"] == "wikilink":
                edge = await self._edge_for_wikilink(row, token)
            elif token["type"] == "citation":
                edge = await self._edge_for_citation(row, token)
            else:
                continue
            self.session.add(edge)
            created.append(edge)
            if edge.dangling:
                await self._create_broken_link_review(row, token, edge)
        await self.session.commit()
        return created

    async def list_backlinks(self, note_id: str) -> list[dict[str, str]]:
        result = await self.session.exec(
            select(KgEdge).where(
                KgEdge.dst_id_or_path == note_id,
                KgEdge.resolved == True,  # noqa: E712
                KgEdge.link_type == "wikilink",
            )
        )
        backlinks: list[dict[str, str]] = []
        seen: set[str] = set()
        for edge in result.all():
            source = await self.session.get(Note, edge.src_id)
            if source is None or source.id in seen:
                continue
            seen.add(source.id)
            backlinks.append({"id": source.id, "title": source.title, "type": edge.src_type, "relation": edge.link_type})
        return backlinks

    def write_recovery_journal(self, note_id: str, relative_path: str, content: str) -> Path:
        journal_id = uuid.uuid4().hex
        journal_path = self.project_root / ".hydralab" / "temp" / f"{journal_id}.note-recovery.json"
        journal_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "journal_id": journal_id,
            "note_id": note_id,
            "relative_path": _safe_relative_path(relative_path),
            "content": content,
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        journal_path.write_text(json.dumps(payload, indent=2, sort_keys=True))
        return journal_path

    def _assert_note_path_allowed(self, relative_path: str) -> None:
        path = Path(relative_path)
        if path.suffix.lower() not in NOTE_EXTENSIONS:
            raise PermissionError("note-file access is limited to Markdown files under configured note roots")
        if relative_path in PROTECTED_PATHS or any(relative_path.startswith(prefix) for prefix in PROTECTED_PREFIXES):
            raise PermissionError("protected project/context files cannot be opened through the note-file API")
        if not any(_is_under_root(relative_path, root) for root in self._note_roots()):
            raise PermissionError("note-file path is outside configured note roots")

    def _note_roots(self) -> list[str]:
        config_path = self.project_root / "project.yaml"
        if config_path.exists():
            folders = load_project_config(config_path).data.get("folders", {})
        else:
            folders = default_project_config("default", "HydraLab")["folders"]
        roots: list[str] = []
        for role in ("knowledge", "writing"):
            folder = folders.get(role, {})
            if isinstance(folder, dict) and folder.get("path"):
                roots.append(str(folder["path"]).strip("/"))
        return [f"{root}/" for root in roots if root]

    def list_recovery_journals(self) -> list[dict[str, Any]]:
        journal_dir = self.project_root / ".hydralab" / "temp"
        if not journal_dir.exists():
            return []
        journals = []
        for path in sorted(journal_dir.glob("*.note-recovery.json")):
            payload = json.loads(path.read_text())
            if payload.get("status") == "pending":
                journals.append(payload)
        return journals

    async def accept_recovery(self, journal_id: str) -> dict[str, Any]:
        journal_path = self.project_root / ".hydralab" / "temp" / f"{journal_id}.note-recovery.json"
        payload = json.loads(journal_path.read_text())
        _atomic_write(self.project_root / _safe_relative_path(payload["relative_path"]), payload["content"])
        payload["status"] = "accepted"
        journal_path.write_text(json.dumps(payload, indent=2, sort_keys=True))
        note = await self.session.get(Note, payload["note_id"])
        if note is not None:
            note.body = payload["content"]
            note.content_hash = _sha256_text(payload["content"])
            note.updated_at = _now()
            self.session.add(note)
            await self.session.commit()
            await self.reindex_note(note.id)
        return payload

    async def propose_inline_suggestion(
        self,
        note_id: str,
        suggestion_id: str,
        replacement: str,
        auto_apply: bool = False,
        origin_excerpt: str = "",
    ) -> dict[str, Any]:
        note = await self.session.get(Note, note_id)
        if note is None:
            raise KeyError(note_id)
        if note.trust_origin in {"untrusted", "untrusted-external"}:
            item = ReviewItem(
                project_id=note.project_id,
                item_type="untrusted-edit-suggestion",
                title=f"Review edit suggestion for {note.title}",
                summary="Untrusted-origin buffer proposed an edit. User review is required.",
                origin_type="note",
                origin_id=note.id,
                target_type="note",
                target_id=note.id,
                payload_json=json.dumps(
                    {
                        "suggestion_id": suggestion_id,
                        "replacement": replacement,
                        "trust_level": "untrusted-external",
                        "origin_excerpt": origin_excerpt,
                    },
                    sort_keys=True,
                ),
            )
            self.session.add(item)
            await self.session.commit()
            await self.session.refresh(item)
            return {"applied": False, "review_item_id": item.id}
        return {"applied": bool(auto_apply), "review_item_id": None}

    async def _edge_for_wikilink(self, row: Note, token: dict[str, Any]) -> KgEdge:
        target = token["target"]
        resolved = await self._resolve_note_target(target)
        dst = resolved.id if resolved is not None else target
        return self._edge(
            row,
            token,
            link_type="wikilink",
            dst_id_or_path=dst,
            dst_type="note" if resolved else "unresolved",
            resolved=resolved is not None,
        )

    async def _edge_for_citation(self, row: Note, token: dict[str, Any]) -> KgEdge:
        key = token["key"]
        resolved_id = await self._resolve_citation_key(key)
        return self._edge(
            row,
            token,
            link_type="citation",
            dst_id_or_path=resolved_id or key,
            dst_type="source" if resolved_id else "unresolved",
            resolved=resolved_id is not None,
        )

    def _edge(
        self,
        row: Note,
        token: dict[str, Any],
        link_type: str,
        dst_id_or_path: str,
        dst_type: str,
        resolved: bool,
    ) -> KgEdge:
        locator = {"from": token["from"], "to": token["to"], "line": token["line"], "raw": token.get("target") or token.get("key")}
        edge_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{row.id}:{link_type}:{token['from']}:{token['to']}:{locator['raw']}"))
        return KgEdge(
            id=edge_id,
            project_id=row.project_id or "default",
            src_id=row.id,
            src_type="draft" if _is_draft_path(row.relative_path) else "note",
            dst_id_or_path=dst_id_or_path,
            dst_type=dst_type,
            link_type=link_type,
            locator=json.dumps(locator, sort_keys=True),
            resolved=resolved,
            dangling=not resolved,
        )

    async def _resolve_note_target(self, target: str) -> Note | None:
        normalized = target.strip().lower()
        rows = (await self.session.exec(select(Note))).all()
        for note in rows:
            candidates = {note.id.lower(), note.title.lower(), Path(note.relative_path).stem.lower(), note.relative_path.lower()}
            if normalized in candidates:
                return note
        return None

    async def _resolve_citation_key(self, key: str) -> str | None:
        citations = (await self.session.exec(select(Citation).where(Citation.citation_key == key))).all()
        if citations:
            return citations[0].source_id
        sources = (await self.session.exec(select(Source))).all()
        for source in sources:
            metadata = json.loads(source.metadata_json or "{}")
            if metadata.get("citation_key") == key:
                return source.id
        return None

    async def _create_broken_link_review(self, row: Note, token: dict[str, Any], edge: KgEdge) -> None:
        target = token.get("target") or token.get("key")
        existing = (
            await self.session.exec(
                select(ReviewItem).where(
                    ReviewItem.item_type == "broken-link",
                    ReviewItem.origin_id == edge.id,
                )
            )
        ).first()
        if existing:
            return
        self.session.add(
            ReviewItem(
                project_id=row.project_id,
                item_type="broken-link",
                title=f"Unresolved {edge.link_type}: {target}",
                summary=f"{row.title} contains unresolved {edge.link_type} target {target}.",
                origin_type="kg_edge",
                origin_id=edge.id,
                target_type=edge.dst_type,
                target_id=edge.dst_id_or_path,
                payload_json=json.dumps({"locator": json.loads(edge.locator), "raw_target": target}, sort_keys=True),
            )
        )

    def _note_payload(self, row: Note, content: str, object_type: str) -> dict[str, Any]:
        return {
            "id": row.id,
            "project_id": row.project_id,
            "relative_path": row.relative_path,
            "title": row.title,
            "content": content,
            "body": content,
            "content_hash": row.content_hash,
            "trust_origin": row.trust_origin,
            "object_type": object_type,
        }
