from app.modules.archive.rules import decide
from app.archive import serialize
from copy import deepcopy
import zipfile,io,json

def test_clean_ready(clean):
    assert clean['archive']['status']=='可封存'
def test_dirty_blocked(sample):
    assert sample['archive']['status']=='待处理';assert sample['archive']['blocked']==10
def test_evidence_bundle(sample):
    z=zipfile.ZipFile(io.BytesIO(serialize(sample)));e=json.loads(z.read('evidence.json'));assert e['counts']['input']==52
def test_graph_failure_blocks(clean):
    state=deepcopy(clean);state['balance']['graph_errors']=1;assert decide(state)['status']=='待处理'
def test_hazard_failure_blocks(clean):
    state=deepcopy(clean);state['hazard_issues']=[{'code':'INCOMPATIBLE'}];assert decide(state)['blocked']==1
def test_weight_seal_changes(clean):
    state=deepcopy(clean);state['weight_checks'][0]['difference']='9';assert decide(state)['seal']!=clean['archive']['seal']
def test_bundle_manifest(clean):
    z=zipfile.ZipFile(io.BytesIO(serialize(clean)));assert json.loads(z.read('manifest.json'))['sha256']==clean['manifest']['sha256']
