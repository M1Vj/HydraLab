"""Render manuscript packages from the shared document model."""

from __future__ import annotations

import html
import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hydra.services.docx.adapters import PythonDocxAdapter

from .models import CitationValidation, ManuscriptDocument

PDF_COMPILER_MISSING_MESSAGE = "PDF export needs a LaTeX compiler; download the LaTeX source instead."


@dataclass(frozen=True)
class ExportedTarget:
    target: str
    status: str
    path: str | None = None
    message: str = ""
    download_path: str | None = None

    def public_dict(self) -> dict[str, str | None]:
        return {
            "target": self.target,
            "status": self.status,
            "path": self.path,
            "message": self.message,
            "download_path": self.download_path,
        }


def render_plain_text(document: ManuscriptDocument) -> str:
    parts: list[str] = [f"# {document.manuscript_id}", ""]
    for section in document.sections:
        parts.extend([f"# {section.title}", "", _resolve_section_content(section.content, document), ""])
    parts.extend(_reference_lines(document))
    parts.extend(_ledger_lines(document))
    return "\n".join(parts).strip() + "\n"


def export_docx(document: ManuscriptDocument, out_path: Path) -> ExportedTarget:
    PythonDocxAdapter().export(render_plain_text(document), out_path, document.format)
    return ExportedTarget(target="docx", status="created", path=str(out_path))


def export_latex(document: ManuscriptDocument, out_path: Path) -> ExportedTarget:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_latex(document), encoding="utf-8")
    return ExportedTarget(target="latex", status="created", path=str(out_path))


def export_html(document: ManuscriptDocument, out_path: Path) -> ExportedTarget:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_html(document), encoding="utf-8")
    return ExportedTarget(target="html", status="created", path=str(out_path))


def export_pdf(
    document: ManuscriptDocument,
    tex_path: Path,
    out_path: Path,
    *,
    latex_detector,
) -> ExportedTarget:
    availability = latex_detector()
    if not availability.get("available"):
        return ExportedTarget(
            target="pdf",
            status="compiler-missing",
            message=PDF_COMPILER_MISSING_MESSAGE,
            download_path=str(tex_path),
        )
    toolchain = str(availability.get("toolchain") or "")
    binary = str(availability.get("path") or shutil.which(toolchain) or "")
    if not binary:
        return ExportedTarget(
            target="pdf",
            status="compiler-missing",
            message=PDF_COMPILER_MISSING_MESSAGE,
            download_path=str(tex_path),
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    command = _latex_command(binary, toolchain, tex_path, out_path.parent)
    proc = subprocess.run(command, cwd=str(out_path.parent), capture_output=True, text=True, timeout=120, check=False)
    produced = out_path.parent / f"{tex_path.stem}.pdf"
    if proc.returncode != 0 or not produced.exists():
        return ExportedTarget(target="pdf", status="failed", message=(proc.stderr or proc.stdout or "PDF compile failed")[:1000])
    if produced != out_path:
        produced.replace(out_path)
    return ExportedTarget(target="pdf", status="created", path=str(out_path))


def render_latex(document: ManuscriptDocument) -> str:
    lines = [
        r"\documentclass{article}",
        r"\usepackage{graphicx}",
        r"\usepackage{hyperref}",
        "% Authorship and AI-contribution ledger",
    ]
    lines.extend([f"% {entry['section']}: {entry['authorship']}" for entry in document.authorship_ledger])
    lines.extend([r"\begin{document}", f"\\title{{{_tex(document.manuscript_id)}}}", r"\maketitle"])
    for section in document.sections:
        lines.append(f"\\section{{{_tex(section.title)}}}")
        lines.append(_tex(_resolve_section_content(section.content, document)))
    if document.references:
        lines.append(r"\section*{References}")
        for line in _reference_lines(document):
            if line and not line.startswith("#"):
                lines.append(_tex(line) + r"\\")
    lines.append(r"\section*{Authorship and AI-contribution ledger}")
    for entry in document.authorship_ledger:
        lines.append(f"{_tex(entry['section'])}: {_tex(entry['authorship'])}" + r"\\")
    lines.append(r"\end{document}")
    return "\n".join(lines) + "\n"


def render_html(document: ManuscriptDocument) -> str:
    body: list[str] = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        f"<title>{html.escape(document.manuscript_id)}</title>",
        "</head>",
        "<body>",
        f"<h1>{html.escape(document.manuscript_id)}</h1>",
    ]
    for section in document.sections:
        body.append(f"<section><h2>{html.escape(section.title)}</h2>")
        for paragraph in _resolve_section_content(section.content, document).split("\n"):
            if paragraph.strip():
                body.append(f"<p>{html.escape(paragraph)}</p>")
        body.append("</section>")
    if document.references:
        body.append("<section><h2>References</h2><ul>")
        for line in _reference_lines(document):
            if line and not line.startswith("#"):
                body.append(f"<li>{html.escape(line)}</li>")
        body.append("</ul></section>")
    body.append("<section><h2>Authorship and AI-contribution ledger</h2><ul>")
    for entry in document.authorship_ledger:
        body.append(f"<li>{html.escape(entry['section'])}: {html.escape(entry['authorship'])}</li>")
    body.extend(["</ul></section>", "</body>", "</html>"])
    return "\n".join(body) + "\n"


def write_manifest(
    document: ManuscriptDocument,
    validation: CitationValidation,
    outputs: dict[str, ExportedTarget],
    path: Path,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cited_sources = [document.references[key] for key in document.citation_keys if key in document.references]
    payload: dict[str, Any] = {
        "schema": "hydralab.manuscript-reproducibility.v1",
        "manuscript_id": document.manuscript_id,
        "export_targets": [target for target, output in outputs.items() if output.status in {"created", "compiler-missing"}],
        "template": document.template_id,
        "citation_style": document.format.citation_style,
        "cited_sources": cited_sources,
        "validation": validation.public_dict(),
    }
    path.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")


def _resolve_section_content(content: str, document: ManuscriptDocument) -> str:
    text = content
    for figure in document.figures:
        text = text.replace(f"@{figure.id}", figure.label)
    for table in document.tables:
        text = text.replace(f"@{table.id}", table.label)
    text = _FIGURE_RE.sub(lambda match: _figure_replacement(match, document), text)
    text = _TABLE_CAPTION_RE.sub(lambda match: _table_replacement(match, document), text)
    return text


def _figure_replacement(match: re.Match[str], document: ManuscriptDocument) -> str:
    figure = next((item for item in document.figures if item.id == match.group("id")), None)
    label = figure.label if figure else "Figure ??"
    return f"{label}. {match.group('caption').strip()}"


def _table_replacement(match: re.Match[str], document: ManuscriptDocument) -> str:
    table = next((item for item in document.tables if item.id == match.group("id")), None)
    label = table.label if table else "Table ??"
    return f"{label}. {match.group('caption').strip()}"


def _reference_lines(document: ManuscriptDocument) -> list[str]:
    if not document.references:
        return []
    lines = ["", "# References", ""]
    for key in document.citation_keys:
        source = document.references.get(key)
        if not source:
            continue
        authors = source.get("authors") or "Unknown author"
        year = source.get("year") or "n.d."
        title = source.get("title") or key
        lines.append(f"{authors} ({year}). {title}.")
    return lines


def _ledger_lines(document: ManuscriptDocument) -> list[str]:
    lines = ["", "# Authorship and AI-contribution ledger", ""]
    for entry in document.authorship_ledger:
        lines.append(f"{entry['section']}: {entry['authorship']}")
    return lines


def _latex_command(binary: str, toolchain: str, tex_path: Path, out_dir: Path) -> list[str]:
    if toolchain == "tectonic":
        return [binary, "--keep-logs", "--outdir", str(out_dir), str(tex_path)]
    if toolchain == "latexmk":
        return [binary, "-pdf", "-interaction=nonstopmode", "-halt-on-error", "-no-shell-escape", str(tex_path)]
    return [binary, "-interaction=nonstopmode", "-halt-on-error", "-no-shell-escape", str(tex_path)]


def _tex(value: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
    }
    return "".join(replacements.get(char, char) for char in value)


_FIGURE_RE = re.compile(r"!\[(?P<caption>[^\]]+)\]\((?P<path>[^)]+)\)\{#(?P<id>fig:[A-Za-z0-9_.:-]+)\}")
_TABLE_CAPTION_RE = re.compile(r"^Table:\s*(?P<caption>.+?)\s*\{#(?P<id>tbl:[A-Za-z0-9_.:-]+)\}\s*$", re.MULTILINE)
