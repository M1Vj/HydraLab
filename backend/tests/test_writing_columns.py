"""HL-WRITE-15: invalid column counts must not be silently truncated."""
import pytest

from hydra.services.writing import FormatValidationError, normalize_overrides, resolve_manuscript_format


@pytest.mark.parametrize("value", [True, False, 1.5, 1.999, 2.5, 2.999, float("nan"), float("inf"), -float("inf"), 0, 3, None, [], {}, "1.5", "2.5"])
def test_columns_reject_invalid_values_with_field_name(value):
    with pytest.raises(FormatValidationError) as error:
        normalize_overrides({"columns": value})
    assert error.value.key == "columns"


@pytest.mark.parametrize("value, expected", [(1, 1), (2, 2), (1.0, 1), (2.0, 2), ("1", 1), ("2", 2), (" 2 ", 2), ("+1", 1)])
def test_columns_preserve_valid_coercions(value, expected):
    assert normalize_overrides({"columns": value}) == {"columns": expected}


@pytest.mark.parametrize("value", ["true", "false", "1.5", "2.5", ".nan", ".inf", "-.inf"])
def test_invalid_yaml_columns_fall_back_without_losing_field_name(tmp_path, value):
    folder = tmp_path / "writing" / "manuscripts" / "paper"
    folder.mkdir(parents=True)
    (folder / "paper.yaml").write_text("columns: " + value + "\nfont_size: 11pt\n", encoding="utf-8")
    result = resolve_manuscript_format(tmp_path, "paper", {"columns": 2, "font_size": "12pt"})
    assert result.source == "global"
    assert result.validation_error["key"] == "columns"
    assert result.format.columns == 2
    assert result.format.font_size == "12pt"
