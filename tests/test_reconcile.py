from app.modules.reconcile.rules import reconcile
from copy import deepcopy

def test_input_conservation(sample):
    assert sample['balance']['input']==52;assert sample['balance']['row_balanced']
def test_roots_only_net(clean):
    assert clean['balance']['net_kg']=='2400'
def test_root_difference_real(sample):
    assert sample['balance']['declaration_differences']==['gross_kg']
def test_missing_input_detected(sample):
    state=deepcopy(sample);state['records'].pop();assert reconcile(state)['row_balanced'] is False
def test_declared_package_difference(clean):
    state=deepcopy(clean);state['context']['declaration']['pieces']=241;assert reconcile(state)['declaration_differences']==['pieces']
def test_clean_no_graph_errors(clean):
    assert clean['balance']['graph_errors']==0;assert clean['balance']['weight_errors']==0
def test_exact_gross_sum(clean):
    assert clean['balance']['gross_kg']=='2640'
