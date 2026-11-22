from app.modules.hazard.rules import inspect

def test_missing_un_real(sample):
    assert any(x['code']=='MISSING_UN' for x in sample['hazard_issues'])
def test_incompatible_real(sample):
    assert next(x for x in sample['hazard_issues'] if x['code']=='INCOMPATIBLE')['id']=='C001'
def test_clean_hazards(clean):
    assert clean['hazard_issues']==[]
def test_supported_un(clean):
    row=dict(clean['records'][0],hazard='3',un_code='UN1203');assert inspect([row],clean['context'])==[]
def test_unknown_category(clean):
    row=dict(clean['records'][0],hazard='9',un_code='UN1203');assert inspect([row],clean['context'])[0]['code']=='UNKNOWN_HAZARD'
def test_different_containers(clean):
    a=dict(clean['records'][0],hazard='3',un_code='UN1203',container='A');b=dict(a,id='B',hazard='5.1',un_code='UN1479',container='B');assert inspect([a,b],clean['context'])==[]
def test_order_independent_hazards(clean):
    a=dict(clean['records'][0],hazard='3',un_code='UN1203');b=dict(a,id='B',hazard='5.1',un_code='UN1479');assert inspect([a,b],clean['context'])==inspect([b,a],clean['context'])
