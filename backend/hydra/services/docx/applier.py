"""Checkpointed apply / validate / rollback for DOCX edit plans.

Guarantees (HL-WRITE-33/34/36):

- **Original byte-immutable until replace.** Edits are applied to a *copy* under a
  temp path inside the project workspace; the user-facing DOCX is only ever
  changed by a single atomic ``os.replace`` after validation passes.
- **Checkpoint before apply.** A byte-identical copy of the pre-apply DOCX is
  saved so rollback restores the exact original bytes.
- **Validate before replace.** The rebuilt package must pass the safe OOXML
  reader AND still contain ``word/document.xml``, ``[Content_Types].xml`` and
  package relationships; otherwise nothing is replaced.
- **Typed structural ops only.** Each approved op mutates the ``python-docx``
  element tree for its locator. An op that cannot be applied as a valid
  structural edit is recorded ``validation_status='invalid'`` and aborts the
  apply — the original file is left untouched.
- **Never writes to ``outputs/manuscripts/``** (DEC-7): only the working DOCX
  under ``writing/manuscripts/`` is edited.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .security import DocxPackageError, validate_ooxml_package

_REQUIRED_PARTS = ("[Content_Types].xml", "word/document.xml")


class DocxApplyError(RuntimeError):
    """Raised when apply/rollback cannot proceed (bad path, missing checkpoint)."""


@dataclass
class OperationOutcome:
    index: int
    op_type: str
    target_locator: str
    validation_status: str  # valid | invalid
    detail: str = ""


@dataclass
class ApplyResult:
    status: str  # applied | failed
    working_path: str
    checkpoint_ref: Optional[str] = None
    outcomes: list[OperationOutcome] = field(default_factory=list)
    error_detail: str = ""


def resolve_working_docx(project_root: Path, manuscript: str, relpath: str) -> Path:
    """Resolve + guard the working DOCX path under ``writing/manuscripts/``.

    Rejects traversal, absolute paths and any target outside
    ``writing/manuscripts/`` (never ``outputs/manuscripts/``).
    """
    project_root = Path(project_root).resolve()
    for value in (manuscript, relpath):
        if not value or ".." in value or value.startswith("/") or "\\" in value or "\x00" in value:
            raise DocxApplyError(f"unsafe DOCX path component: {value!r}")
    base = (project_root / "writing" / "manuscripts").resolve()
    target = (base / manuscript / relpath).resolve()
    if os.path.commonpath([str(base), str(target)]) != str(base):
        raise DocxApplyError("DOCX target escapes writing/manuscripts/")
    return target


def _workspace_temp(project_root: Path) -> Path:
    temp_dir = Path(project_root) / ".hydralab" / "temp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    return temp_dir


def create_checkpoint(project_root: Path, plan_id: str, working_path: Path) -> Path:
    """Save a byte-identical pre-apply copy; return its path (the rollback ref)."""
    checkpoint_dir = Path(project_root) / ".hydralab" / "checkpoints" / "docx" / plan_id
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = checkpoint_dir / "original.docx"
    shutil.copyfile(working_path, checkpoint)
    return checkpoint


def validate_docx_package(path: Path) -> tuple[bool, str]:
    """Confirm the package opens and required parts + relationships still exist."""
    try:
        validate_ooxml_package(path)
    except DocxPackageError as exc:
        return False, str(exc)
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
    except zipfile.BadZipFile as exc:
        return False, f"rebuilt package is not a valid zip: {exc}"
    for part in _REQUIRED_PARTS:
        if part not in names:
            return False, f"rebuilt package is missing required part: {part}"
    if not any(name.endswith("_rels/.rels") or name.endswith(".rels") for name in names):
        return False, "rebuilt package is missing relationships"
    try:
        import docx

        docx.Document(str(path))
    except Exception as exc:  # noqa: BLE001 - any open failure means invalid package
        return False, f"rebuilt package does not open via the OOXML reader: {exc}"
    return True, ""


def apply_operations(
    project_root: Path,
    plan_id: str,
    working_path: Path,
    operations: list[dict],
) -> ApplyResult:
    """Checkpoint → apply approved ops to a copy → validate → atomic replace.

    ``operations`` are the APPROVED operations only. Each dict carries
    ``op_type``, ``target_locator`` and ``payload``. On any invalid op the
    original file is left byte-identical and no replace happens.
    """
    working_path = Path(working_path)
    if not working_path.exists():
        raise DocxApplyError(f"working DOCX not found: {working_path}")

    checkpoint = create_checkpoint(project_root, plan_id, working_path)

    temp_fd = tempfile.NamedTemporaryFile(
        prefix="hydralab-docx-apply-", suffix=".docx", dir=_workspace_temp(project_root), delete=False
    )
    temp_path = Path(temp_fd.name)
    temp_fd.close()
    shutil.copyfile(working_path, temp_path)

    outcomes: list[OperationOutcome] = []
    try:
        import docx

        document = docx.Document(str(temp_path))
        for index, operation in enumerate(operations):
            op_type = operation.get("op_type", "other")
            locator = operation.get("target_locator", "")
            payload = operation.get("payload") or {}
            try:
                _apply_one(document, op_type, locator, payload)
                outcomes.append(OperationOutcome(index, op_type, locator, "valid"))
            except _UnsupportedEdit as exc:
                outcomes.append(OperationOutcome(index, op_type, locator, "invalid", str(exc)))
                return ApplyResult(
                    status="failed",
                    working_path=str(working_path),
                    checkpoint_ref=str(checkpoint),
                    outcomes=outcomes,
                    error_detail=f"unsupported operation {op_type} @ {locator}: {exc}",
                )

        document.save(str(temp_path))
        ok, reason = validate_docx_package(temp_path)
        if not ok:
            if outcomes:
                outcomes[-1] = OperationOutcome(
                    outcomes[-1].index, outcomes[-1].op_type, outcomes[-1].target_locator, "invalid", reason
                )
            return ApplyResult(
                status="failed",
                working_path=str(working_path),
                checkpoint_ref=str(checkpoint),
                outcomes=outcomes,
                error_detail=f"validation failed: {reason}",
            )

        # Atomic replace: original untouched until this single call.
        os.replace(temp_path, working_path)
        temp_path = None  # consumed by os.replace
        return ApplyResult(
            status="applied",
            working_path=str(working_path),
            checkpoint_ref=str(checkpoint),
            outcomes=outcomes,
        )
    finally:
        if temp_path is not None:
            Path(temp_path).unlink(missing_ok=True)


def rollback(project_root: Path, working_path: Path, checkpoint_ref: str) -> None:
    """Restore the byte-identical pre-apply DOCX from the checkpoint."""
    checkpoint = Path(checkpoint_ref)
    if not checkpoint.exists():
        raise DocxApplyError(f"checkpoint not found: {checkpoint_ref}")
    temp_fd = tempfile.NamedTemporaryFile(
        prefix="hydralab-docx-rollback-", suffix=".docx", dir=_workspace_temp(project_root), delete=False
    )
    temp_path = Path(temp_fd.name)
    temp_fd.close()
    shutil.copyfile(checkpoint, temp_path)
    os.replace(temp_path, Path(working_path))


# --- typed structural-edit application ---------------------------------------


class _UnsupportedEdit(Exception):
    """Internal: an operation cannot be applied as a valid structural edit."""


def _set_paragraph_text(paragraph, text: str) -> None:
    if paragraph.runs:
        paragraph.runs[0].text = text
        for run in paragraph.runs[1:]:
            run.text = ""
    else:
        paragraph.add_run(text)


def _resolve_body_paragraph(document, locator: str):
    parts = locator.split("/")
    if len(parts) == 3 and parts[0] == "body" and parts[1] == "p":
        paragraphs = document.paragraphs
        idx = _to_int(parts[2])
        if 0 <= idx < len(paragraphs):
            return paragraphs[idx]
    return None


def _resolve_section_paragraph(document, locator: str):
    parts = locator.split("/")
    if len(parts) == 4 and parts[0] in {"header", "footer"} and parts[2] == "p":
        s_idx = _to_int(parts[1])
        p_idx = _to_int(parts[3])
        sections = document.sections
        if 0 <= s_idx < len(sections):
            part = sections[s_idx].header if parts[0] == "header" else sections[s_idx].footer
            paragraphs = part.paragraphs
            if 0 <= p_idx < len(paragraphs):
                return paragraphs[p_idx]
    return None


def _resolve_table_cell(document, locator: str):
    parts = locator.split("/")
    if len(parts) == 7 and parts[0] == "body" and parts[1] == "tbl" and parts[3] == "row" and parts[5] == "cell":
        t_idx, r_idx, c_idx = _to_int(parts[2]), _to_int(parts[4]), _to_int(parts[6])
        tables = document.tables
        if 0 <= t_idx < len(tables):
            table = tables[t_idx]
            if 0 <= r_idx < len(table.rows):
                row = table.rows[r_idx]
                if 0 <= c_idx < len(row.cells):
                    return row.cells[c_idx]
    return None


def _to_int(value: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1


def _any_paragraph(document, locator: str):
    return _resolve_body_paragraph(document, locator) or _resolve_section_paragraph(document, locator)


def _apply_one(document, op_type: str, locator: str, payload: dict) -> None:
    if op_type in {"replace_text", "update_citation"}:
        paragraph = _any_paragraph(document, locator)
        if paragraph is None:
            raise _UnsupportedEdit(f"no paragraph at locator {locator}")
        _set_paragraph_text(paragraph, str(payload.get("text", "")))
        return

    if op_type == "update_table":
        cell = _resolve_table_cell(document, locator)
        if cell is None:
            raise _UnsupportedEdit(f"no table cell at locator {locator}")
        cell.text = str(payload.get("text", ""))
        return

    if op_type == "apply_style":
        paragraph = _any_paragraph(document, locator)
        if paragraph is None:
            raise _UnsupportedEdit(f"no paragraph at locator {locator}")
        style_name = str(payload.get("style", ""))
        try:
            paragraph.style = style_name
        except Exception as exc:  # noqa: BLE001 - unknown style is an invalid edit
            raise _UnsupportedEdit(f"unknown style {style_name!r}: {exc}") from exc
        return

    if op_type == "insert_paragraph":
        text = str(payload.get("text", ""))
        anchor = _resolve_body_paragraph(document, locator)
        if anchor is not None:
            anchor.insert_paragraph_before(text)
        else:
            document.add_paragraph(text)
        return

    if op_type == "comment":
        paragraph = _any_paragraph(document, locator)
        if paragraph is None:
            raise _UnsupportedEdit(f"no paragraph at locator {locator}")
        runs = paragraph.runs or [paragraph.add_run(paragraph.text)]
        try:
            document.add_comment(
                runs=runs,
                text=str(payload.get("text", "")),
                author=str(payload.get("author", "HydraLab")),
                initials=str(payload.get("initials", "HL")),
            )
        except Exception as exc:  # noqa: BLE001
            raise _UnsupportedEdit(f"comment could not be added: {exc}") from exc
        return

    if op_type == "delete":
        paragraph = _any_paragraph(document, locator)
        if paragraph is not None:
            element = paragraph._element
            element.getparent().remove(element)
            return
        cell = _resolve_table_cell(document, locator)
        if cell is not None:
            cell.text = ""
            return
        raise _UnsupportedEdit(f"nothing deletable at locator {locator}")

    # "other" (and any unmodelled structural edit) cannot be applied safely.
    raise _UnsupportedEdit(f"unsupported structural op_type: {op_type}")
