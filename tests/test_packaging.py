from app.modules.packaging.rules import normalize
from app.errors import BusinessError
import pytest

def test_pallet_real(sample):
    # TRAP-15
    row=next(x for x in sample['records'] if x['id']=='M001-P1-1');assert row['pieces']==10;assert row['net_kg']=='100.0'
def test_sentinel_real(sample):
    # TRAP-07
    assert next(x for x in sample['quarantine'] if x['id']=='BAD')['code']=='MISSING_VALUE'
def test_mass_real(clean):
    assert clean['records'][0]['gross_kg']=='440'
def test_fullwidth_decimal(clean):
    # TRAP-06
    row=normalize(dict(clean['records'][0],net='１,０００',gross='１,１００'),clean['context']);assert row['net_kg']=='1000'
def test_fractional_piece_refused(clean):
    with pytest.raises(BusinessError):normalize(dict(clean['records'][0],packages='1.5'),clean['context'])
def test_bad_unit_refused(clean):
    with pytest.raises(BusinessError):normalize(dict(clean['records'][0],weight_unit='lb'),clean['context'])
def test_gross_below_net(clean):
    with pytest.raises(BusinessError):normalize(dict(clean['records'][0],gross='399'),clean['context'])
