from app.modules.weight.rules import check_weights
from app.modules.grouping.rules import graph

def test_clean_all_levels(clean):
    assert len(clean['weight_checks'])==54;assert all(x['code']=='BALANCED' for x in clean['weight_checks'])
def test_dirty_difference_real(sample):
    issue=next(x for x in sample['weight_checks'] if x['code']!='BALANCED');assert issue['id']=='M001';assert issue['difference']=='1'
def test_children_not_flat_sum(clean):
    root=next(x for x in clean['weight_checks'] if x['id']=='M001' and x['field']=='net_kg');assert root['children_sum']=='400'
def test_package_mismatch(clean):
    rows=[dict(x) for x in clean['records']];rows[0]['pieces']=41;checks=check_weights(rows,graph(rows));assert next(x for x in checks if x['id']=='M001' and x['field']=='pieces')['difference']=='1'
def test_zero_leaf_mass(clean):
    rows=[dict(x) for x in clean['records'][:1]];assert check_weights(rows,graph(rows))==[]
def test_nested_difference(clean):
    rows=[dict(x) for x in clean['records']];rows[2]['net_kg']='99';checks=check_weights(rows,graph(rows));assert next(x for x in checks if x['id']=='M001-P1' and x['field']=='net_kg')['difference']=='1.0'
def test_order_independent_checks(clean):
    rows=clean['records'];assert check_weights(rows,graph(rows))==check_weights(list(reversed(rows)),graph(rows))
