"""Nonfinite manuscript spacing must trigger the field-specific fallback."""
import math
import pytest
from hydra.services.writing import FormatValidationError, normalize_overrides, resolve_manuscript_format

@pytest.mark.parametrize('value', [float('nan'),float('inf'),-float('inf'),'nan','NaN','inf','-inf','1e999',10**400,0,-1,5.01,None,[],{}])
def test_spacing_rejects_invalid_values(value):
    with pytest.raises(FormatValidationError) as err:
        normalize_overrides({'line_spacing':value})
    assert err.value.key=='line_spacing'

@pytest.mark.parametrize('value', [1,2,5,0.001,math.nextafter(0,1),'1.5',' 2 ',True])
def test_spacing_preserves_existing_valid_coercions(value):
    assert normalize_overrides({'line_spacing':value})=={'line_spacing':float(value)}

@pytest.mark.parametrize('value', ['.nan','.inf','-.inf','"nan"','"inf"','1'+('0'*400)])
def test_invalid_yaml_spacing_falls_back(tmp_path,value):
    folder=tmp_path/'writing/manuscripts/paper';folder.mkdir(parents=True)
    (folder/'paper.yaml').write_text('line_spacing: '+value+'\nfont_size: 11pt\n',encoding='utf-8')
    result=resolve_manuscript_format(tmp_path,'paper',{'line_spacing':1.5,'font_size':'12pt'})
    assert result.source=='global'
    assert result.validation_error['key']=='line_spacing'
    assert result.format.line_spacing==1.5
    assert result.format.font_size=='12pt'
