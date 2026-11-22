from app.modules.grouping.rules import graph

def test_roots_real(clean):
    assert clean['graph']['roots']==['M001','M002','M003','M004','M005','M006']
def test_nested_real(clean):
    assert clean['graph']['children']['M001-P1']==['M001-P1-1','M001-P1-2']
def test_cycle_real(sample):
    # TRAP-20
    issue=next(x for x in sample['graph']['errors'] if x['code']=='DEPENDENCY_CYCLE');assert issue['path']==['LOOP-A','LOOP-B','LOOP-A']
def test_missing_parent_real(sample):
    # TRAP-21
    assert next(x for x in sample['graph']['errors'] if x['id']=='ORPHAN')['path']==['UNKNOWN']
def test_self_reference(clean):
    g=graph([dict(clean['records'][0],parent='M001')]);assert g['errors'][0]['path']==['M001','M001']
def test_order_invariant(clean):
    a=graph(clean['records']);b=graph(list(reversed(clean['records'])));assert a['roots']==b['roots'];assert a['errors']==b['errors']
def test_leaf_root(clean):
    g=graph([dict(clean['records'][0],parent='')]);assert g['roots']==['M001'];assert g['errors']==[]
