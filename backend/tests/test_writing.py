"""Writing-formats tests (branch 01-12).

Covers HL-WRITE-15 (paper.yaml parse + malformed fallback), HL-WRITE-16 (global
defaults persist + unknown-key round-trip), HL-WRITE-17 (per-field merge) and
HL-WRITE-18 (full appearance fields beyond citation style).
"""
from pathlib import Path

import pytest

from hydra.services.writing import (
    FormatValidationError,
    global_defaults_from_settings,
    merge_format,
    normalize_overrides,
    resolve_manuscript_format,
)
from hydra.settings.toml_config import default_settings, load_settings, save_settings


def _make_manuscript(root: Path, name: str, paper_yaml: str) -> Path:
    manuscript_dir = root / "writing" / "manuscripts" / name
    manuscript_dir.mkdir(parents=True, exist_ok=True)
    (manuscript_dir / "paper.yaml").write_text(paper_yaml, encoding="utf-8")
    return manuscript_dir


def test_hl_write_15_paper_yaml_parsed_into_format_model(tmp_path):
    _make_manuscript(
        tmp_path,
        "transformer-survey",
        "font_size: 11pt\nmargins: 1in\n",
    )
    resolved = resolve_manuscript_format(tmp_path, "transformer-survey", global_defaults_from_settings(default_settings()))
    assert resolved.validation_error is None
    assert resolved.format.font_size == "11pt"
    assert resolved.format.margins == "1in"
    assert resolved.source == "merged"


def test_hl_write_15_malformed_paper_yaml_falls_back_with_validation_message(tmp_path):
    _make_manuscript(tmp_path, "bad-survey", "page_size: A99\n")
    defaults = global_defaults_from_settings(default_settings())
    resolved = resolve_manuscript_format(tmp_path, "bad-survey", defaults)

    assert resolved.validation_error is not None
    assert resolved.validation_error["key"] == "page_size"
    # Falls back to the global default page size; module stays usable.
    assert resolved.format.page_size == defaults["page_size"]


def test_hl_write_17_manuscript_override_wins_per_field(tmp_path):
    defaults = global_defaults_from_settings(default_settings())
    defaults["font_family"] = "Times New Roman"
    defaults["margins"] = "1in"
    _make_manuscript(tmp_path, "venue-paper", "margins: 0.75in\n")

    resolved = resolve_manuscript_format(tmp_path, "venue-paper", defaults)

    assert resolved.format.margins == "0.75in"
    assert resolved.format.font_family == "Times New Roman"


def test_hl_write_18_format_model_carries_full_output_appearance(tmp_path):
    _make_manuscript(
        tmp_path,
        "appearance",
        (
            'font_family: "Times New Roman"\n'
            "line_spacing: 2.0\n"
            "margins: 1in\n"
            "page_size: a4\n"
            "heading_numbering: true\n"
            "columns: 2\n"
            "figure_caption: below\n"
        ),
    )
    resolved = resolve_manuscript_format(tmp_path, "appearance", global_defaults_from_settings(default_settings()))
    fmt = resolved.format
    assert resolved.validation_error is None
    assert fmt.font_family == "Times New Roman"
    assert fmt.line_spacing == 2.0
    assert fmt.margins == "1in"
    assert fmt.page_size == "a4"
    assert fmt.heading_numbering is True
    assert fmt.columns == 2
    assert fmt.figure_caption == "below"
    # Appearance fields are independent of the citation style.
    assert hasattr(fmt, "citation_style")
    assert fmt.citation_style == "apa"


def test_hl_write_16_global_default_persists_and_preserves_unknown_keys(tmp_path):
    settings_path = tmp_path / "settings.toml"
    data = default_settings()
    data["writing"]["default_citation_style"] = "apa"
    data["writing"]["docx_template"] = "generic-academic"
    data["writing"]["experimental_grid"] = "on"  # unrecognized key
    save_settings(settings_path, data)

    reloaded = load_settings(settings_path).data
    reloaded["writing"]["default_citation_style"] = "ieee"
    save_settings(settings_path, reloaded)

    final = load_settings(settings_path).data
    assert final["writing"]["default_citation_style"] == "ieee"
    assert final["writing"]["docx_template"] == "generic-academic"
    assert final["writing"]["experimental_grid"] == "on"

    defaults = global_defaults_from_settings(final)
    assert defaults["citation_style"] == "ieee"
    assert defaults["docx_template"] == "generic-academic"


def test_normalize_overrides_rejects_bad_columns():
    with pytest.raises(FormatValidationError) as exc:
        normalize_overrides({"columns": 3})
    assert exc.value.key == "columns"


def test_missing_paper_yaml_uses_global_defaults(tmp_path):
    defaults = global_defaults_from_settings(default_settings())
    resolved = resolve_manuscript_format(tmp_path, "nonexistent", defaults)
    assert resolved.validation_error is None
    assert resolved.source == "global"
    assert resolved.format.page_size == defaults["page_size"]


def test_merge_format_defaults_when_empty():
    fmt = merge_format({}, {})
    assert fmt.citation_style == "apa"
    assert fmt.page_size == "letter"
