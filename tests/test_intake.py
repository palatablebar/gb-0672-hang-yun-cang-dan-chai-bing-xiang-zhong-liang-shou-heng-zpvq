from app.engine import evaluate
from app.errors import BusinessError
from app.config import ROOT
import pytest

def test_bom_source(sample):
    # TRAP-02
    assert sample['records'][0]['id']=='M001'
def test_legacy_source():
    # TRAP-01
    assert evaluate({'dataset':'legacy'})['encoding']=='gb18030'
def test_segment_header(sample):
    # TRAP-04
    assert sample['counts']['repeated_header']==1
def test_column_isolation(sample):
    # TRAP-05
    assert next(x for x in sample['quarantine'] if x['id']=='COLUMN')['code']=='COLUMN_COUNT'
def test_conflict_all_isolated(sample):
    # TRAP-14
    assert len([x for x in sample['quarantine'] if x['id']=='CONFLICT'])==2
def test_exact_duplicate(sample):
    assert sample['counts']['duplicate']==1
def test_three_empty_states():
    # TRAP-18
    for text,code in [('', 'EMPTY_FILE'),('\n\n','BLANK_FILE'),((ROOT/'sample_data/clean.csv').read_text().splitlines()[0]+'\n','HEADER_ONLY')]:
        with pytest.raises(BusinessError) as e:evaluate({'csv_text':text})
        assert e.value.code==code
