"""Safe OOXML reader + addressable structural model (HL-WRITE-30, HL-TRUST-31).

A DOCX is an OOXML zip. This module unpacks it through the shared Section-34.5
safe-zip path (:mod:`hydra.services.docx.security` — decompression-bomb / entry-
count / compression-ratio limits, path-traversal reject, macro skip) and then
builds an *inspectable* structural model whose nodes are addressable by a stable
locator (part + element index / ``w:id`` / style id) covering paragraph, run,
style, table cell, comment, tracked-change, header, footer and reference.

Two parsers are used, both permissive-licence:

- ``python-docx`` (MIT) for the object model it covers well: body paragraphs and
  runs, styles, tables (row/cell) and section headers/footers.
- ``lxml`` (BSD-3, already bundled) with a HARDENED parser (external-entity /
  remote-DTD resolution disabled — XXE off) for the parts python-docx does not
  model: comments, tracked changes (``w:ins``/``w:del``) and references
  (``w:hyperlink``).

Reading NEVER mutates the source file: the original is opened read-only and the
safe extraction lands in a caller-scoped temp directory inside the workspace.
Every extracted text span is tagged ``untrusted-external`` (DEC-11 / HL-TRUST-30)
so a downstream planner can never treat document text as instructions.
"""
from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .security import extract_docx_safely

# WordprocessingML main namespace.
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

TRUST_UNTRUSTED_EXTERNAL = "untrusted-external"

# Hardened lxml parser: XXE off, no remote/DTD fetch, no billion-laughs entities.
_SAFE_XML_KWARGS = dict(
    resolve_entities=False,
    no_network=True,
    load_dtd=False,
    dtd_validation=False,
    huge_tree=False,
)


def _safe_xml_parser():
    from lxml import etree

    return etree.XMLParser(**_SAFE_XML_KWARGS)


@dataclass
class DocxNode:
    """One addressable node in the structural model (text is untrusted-external)."""

    locator: str
    kind: str  # paragraph | run | style | table_cell | comment | tracked_change | header | footer | reference
    text: str = ""
    location_label: str = ""
    style_id: Optional[str] = None
    trust_level: str = TRUST_UNTRUSTED_EXTERNAL
    meta: dict[str, object] = field(default_factory=dict)


@dataclass
class StructuralModel:
    source_path: str
    nodes: list[DocxNode] = field(default_factory=list)
    flagged_active_content: list[str] = field(default_factory=list)
    parts: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._by_locator = {node.locator: node for node in self.nodes}

    def add(self, node: DocxNode) -> None:
        self.nodes.append(node)
        self._by_locator[node.locator] = node

    def find(self, locator: str) -> Optional[DocxNode]:
        return self._by_locator.get(locator)

    def locators(self) -> list[str]:
        return [node.locator for node in self.nodes]

    def of_kind(self, kind: str) -> list[DocxNode]:
        return [node for node in self.nodes if node.kind == kind]


def paragraph_locator(index: int) -> str:
    return f"body/p/{index}"


def run_locator(paragraph_index: int, run_index: int) -> str:
    return f"body/p/{paragraph_index}/r/{run_index}"


def style_locator(style_id: str) -> str:
    return f"styles/{style_id}"


def table_cell_locator(table: int, row: int, cell: int) -> str:
    return f"body/tbl/{table}/row/{row}/cell/{cell}"


def header_locator(section: int, index: int) -> str:
    return f"header/{section}/p/{index}"


def footer_locator(section: int, index: int) -> str:
    return f"footer/{section}/p/{index}"


def comment_locator(comment_id: str) -> str:
    return f"comments/{comment_id}"


def _snippet(text: str, limit: int = 160) -> str:
    collapsed = " ".join((text or "").split())
    return collapsed if len(collapsed) <= limit else collapsed[: limit - 1] + "…"


def read_structural_model(path: Path, workspace_root: Path) -> StructuralModel:
    """Safely unpack ``path`` and build the addressable structural model.

    ``extract_docx_safely`` runs FIRST so a hostile package (zip bomb, path
    traversal, bad magic) is rejected with :class:`DocxPackageError` before any
    parsing and without writing outside ``workspace_root``. The original file is
    only ever opened read-only.
    """
    path = Path(path)
    workspace_root = Path(workspace_root)

    temp_root = Path(tempfile.mkdtemp(prefix="hydralab-docx-read-", dir=_ensure_workspace_temp(workspace_root)))
    try:
        extraction = extract_docx_safely(path, temp_root)
        model = StructuralModel(
            source_path=str(path),
            flagged_active_content=list(extraction.flagged_active_content),
            parts=list(extraction.members),
        )
        _read_body_and_tables(path, model)
        _read_styles(path, model)
        _read_headers_footers(path, model)
        _read_comments(temp_root, model)
        _read_tracked_changes_and_references(temp_root, model)
        return model
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def _ensure_workspace_temp(workspace_root: Path) -> Path:
    temp_dir = Path(workspace_root) / ".hydralab" / "temp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    return temp_dir


def _read_body_and_tables(path: Path, model: StructuralModel) -> None:
    import docx

    document = docx.Document(str(path))
    for p_index, paragraph in enumerate(document.paragraphs):
        model.add(
            DocxNode(
                locator=paragraph_locator(p_index),
                kind="paragraph",
                text=paragraph.text,
                location_label=f"Body ¶{p_index + 1}",
                style_id=getattr(paragraph.style, "style_id", None),
                meta={"style_name": getattr(paragraph.style, "name", None)},
            )
        )
        for r_index, run in enumerate(paragraph.runs):
            model.add(
                DocxNode(
                    locator=run_locator(p_index, r_index),
                    kind="run",
                    text=run.text,
                    location_label=f"Body ¶{p_index + 1}, run {r_index + 1}",
                )
            )
    for t_index, table in enumerate(document.tables):
        for r_index, row in enumerate(table.rows):
            for c_index, cell in enumerate(row.cells):
                model.add(
                    DocxNode(
                        locator=table_cell_locator(t_index, r_index, c_index),
                        kind="table_cell",
                        text=cell.text,
                        location_label=f"Table {t_index + 1}, row {r_index + 1}, cell {c_index + 1}",
                    )
                )


def _read_styles(path: Path, model: StructuralModel) -> None:
    import docx

    document = docx.Document(str(path))
    for style in document.styles:
        style_id = getattr(style, "style_id", None)
        if not style_id:
            continue
        model.add(
            DocxNode(
                locator=style_locator(style_id),
                kind="style",
                text=getattr(style, "name", "") or "",
                location_label=f"Style {getattr(style, 'name', style_id)}",
                style_id=style_id,
                meta={"builtin": bool(getattr(style, "builtin", False))},
            )
        )


def _read_headers_footers(path: Path, model: StructuralModel) -> None:
    import docx

    document = docx.Document(str(path))
    for s_index, section in enumerate(document.sections):
        for kind, part, locator_fn, label in (
            ("header", section.header, header_locator, "Header"),
            ("footer", section.footer, footer_locator, "Footer"),
        ):
            if getattr(part, "is_linked_to_previous", False):
                continue
            for p_index, paragraph in enumerate(part.paragraphs):
                model.add(
                    DocxNode(
                        locator=locator_fn(s_index, p_index),
                        kind=kind,
                        text=paragraph.text,
                        location_label=f"{label} (section {s_index + 1}) ¶{p_index + 1}",
                    )
                )


def _read_comments(temp_root: Path, model: StructuralModel) -> None:
    comments_path = temp_root / "word" / "comments.xml"
    if not comments_path.exists():
        return
    from lxml import etree

    tree = etree.parse(str(comments_path), _safe_xml_parser())
    for comment in tree.getroot().findall(f"{{{W_NS}}}comment"):
        comment_id = comment.get(f"{{{W_NS}}}id", "")
        author = comment.get(f"{{{W_NS}}}author", "")
        text = "".join(comment.itertext())
        model.add(
            DocxNode(
                locator=comment_locator(comment_id),
                kind="comment",
                text=text,
                location_label=f"Comment #{comment_id}" + (f" ({author})" if author else ""),
                meta={"author": author},
            )
        )


def _read_tracked_changes_and_references(temp_root: Path, model: StructuralModel) -> None:
    document_path = temp_root / "word" / "document.xml"
    if not document_path.exists():
        return
    from lxml import etree

    tree = etree.parse(str(document_path), _safe_xml_parser())
    root = tree.getroot()

    tc_index = 0
    for tag in ("ins", "del"):
        for element in root.iter(f"{{{W_NS}}}{tag}"):
            model.add(
                DocxNode(
                    locator=f"body/{tag}/{tc_index}",
                    kind="tracked_change",
                    text=_snippet("".join(element.itertext())),
                    location_label=f"Tracked change ({tag}) #{tc_index}",
                    meta={"change_type": tag, "author": element.get(f"{{{W_NS}}}author", "")},
                )
            )
            tc_index += 1

    ref_index = 0
    for element in root.iter(f"{{{W_NS}}}hyperlink"):
        model.add(
            DocxNode(
                locator=f"body/ref/{ref_index}",
                kind="reference",
                text=_snippet("".join(element.itertext())),
                location_label=f"Reference #{ref_index}",
                meta={"anchor": element.get(f"{{{W_NS}}}anchor", "")},
            )
        )
        ref_index += 1
