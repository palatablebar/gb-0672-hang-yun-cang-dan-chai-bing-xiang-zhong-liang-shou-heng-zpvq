import pytest
from fastapi.testclient import TestClient

from app import main
from app.engine import evaluate
from app.modules.notice import scenarios, service, store
from app.modules.notice.rules import CHANGE_TEXT, NO_CHANGE, WEIGHT


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = str(tmp_path / 'notice.sqlite')
    monkeypatch.setattr(main, 'DB_PATH', path)
    return path


@pytest.fixture
def batch():
    return 'batch-test'


def test_first_publish_covers_all_roots(db, batch):
    notice = service.publish(db, batch, scenarios.base_run())
    assert notice['state'] == '已发布'
    assert set(notice['affected']) == set(scenarios.base_run()['graph']['roots'])
    assert notice['decision']['mode'] == '整批统一签收'
    assert len(store.list_deliveries(db, notice['notice_no'])) == 1


def test_resend_is_idempotent_no_second_signoff(db, batch):
    run = scenarios.base_run()
    n1 = service.publish(db, batch, run)
    service.sign_batch(db, batch, run, '整批统一签收')
    n2 = service.publish(db, batch, run)
    assert n2['kind'] == 'RESEND' and n2['is_resend'] is True
    assert n2['notice_no'] != n1['notice_no']
    signoffs = store.list_signoffs(db, batch)
    assert len(signoffs) == len(run['graph']['roots'])
    assert all(s['notice_no'] == n1['notice_no'] for s in signoffs)
    # 再重试一次同一通知，只追加送达记录
    retried = service.retry_delivery(db, n2['notice_no'])
    assert retried['recovered'] is False
    assert len(store.list_deliveries(db, n2['notice_no'])) == 2
    assert len(store.list_signoffs(db, batch)) == len(run['graph']['roots'])


def test_partial_revision_affected_root_signs_first(db, batch):
    service.publish(db, batch, scenarios.base_run())
    v2_run, _ = scenarios.scenario_run('v2_weight')
    n2 = service.publish(db, batch, v2_run)
    assert n2['affected'] == ['M002']
    assert n2['decision']['mode'] == '受影响主单先行签收'
    result = service.sign_batch(db, batch, v2_run, '受影响主单先行签收')
    assert result['count'] == 1 and result['signed'][0]['root_id'] == 'M002'
    data = service.sheet(db, batch, v2_run)
    m1 = next(r for r in data['rows'] if r['id'] == 'M001')
    m2 = next(r for r in data['rows'] if r['id'] == 'M002')
    assert m1['change'] == CHANGE_TEXT[NO_CHANGE] and m1['basis_notice'].endswith('V1')
    assert m2['change'] == CHANGE_TEXT[WEIGHT] and m2['basis_notice'].endswith('V2')
    assert m2['can_declare'] == '可申报'


def test_old_signoff_blocked_once_basis_superseded(db, batch):
    run = scenarios.base_run()
    service.publish(db, batch, run)
    service.sign(db, batch, run, 'M002', '整批统一签收')
    v2_run, _ = scenarios.scenario_run('v2_weight')
    service.publish(db, batch, v2_run)
    data = service.sheet(db, batch, v2_run)
    m2 = next(r for r in data['rows'] if r['id'] == 'M002')
    assert m2['signoff_status'].startswith('签收已失效')
    assert m2['can_declare'] == '不可申报'
    # 旧签收行保留为审计记录；按当前依据重新签收后恢复可申报，重试不新增第二套
    renewed = service.sign(db, batch, v2_run, 'M002', '受影响主单先行签收')
    assert renewed['notice_no'].endswith('V2')
    again = service.sign(db, batch, v2_run, 'M002', '受影响主单先行签收')
    assert again['notice_no'] == renewed['notice_no'] and again['created_at'] == renewed['created_at']
    data = service.sheet(db, batch, v2_run)
    m2 = next(r for r in data['rows'] if r['id'] == 'M002')
    assert m2['signoff_status'] == '已签收 ' + renewed['notice_no']
    assert m2['can_declare'] == '可申报'
    history = store.list_signoffs(db, batch)
    assert len([s for s in history if s['root_id'] == 'M002']) == 2


def test_publish_failure_keeps_old_basis_and_undelivered(db, batch):
    service.publish(db, batch, scenarios.base_run())
    v4_run, _ = scenarios.scenario_run('v4_fail')
    failed = service.publish(db, batch, v4_run, simulate_fail=True)
    assert failed['state'] == '发布失败'
    deliveries = store.list_deliveries(db, failed['notice_no'])
    assert deliveries[0]['outcome'] == '未送达'
    data = service.sheet(db, batch, v4_run)
    assert data['failed_notice']['notice_no'] == failed['notice_no']
    assert data['latest_notice']['notice_no'].endswith('V1')
    m4 = next(r for r in data['rows'] if r['id'] == 'M004')
    assert m4['basis_notice'].endswith('V1')
    # 失败未恢复前，禁止发布新修订、禁止签收
    from app.errors import BusinessError
    with pytest.raises(BusinessError) as exc:
        service.publish(db, batch, scenarios.base_run())
    assert exc.value.code == 'PENDING_FAILURE'
    with pytest.raises(BusinessError):
        service.sign(db, batch, v4_run, 'M001', '整批统一签收')
    # 重试恢复：状态转已发布，未送达记录保留
    recovered = service.retry_delivery(db, failed['notice_no'])
    assert recovered['state'] == '已发布' and recovered['recovered'] is True
    outcomes = [d['outcome'] for d in store.list_deliveries(db, failed['notice_no'])]
    assert outcomes == ['未送达', '已送达']


def test_retry_non_failed_notice_is_idempotent(db, batch):
    n1 = service.publish(db, batch, scenarios.base_run())
    again = service.retry_delivery(db, n1['notice_no'])
    assert again['state'] == '已发布'
    assert len(store.list_deliveries(db, n1['notice_no'])) == 2


def test_full_demo_chain_end_to_end(db, batch):
    client = TestClient(main.app)
    r = client.post(f'/api/notice/{batch}/publish-demo', json={})
    assert r.status_code == 200
    chain = r.json()['chain']
    assert len(chain) == 6
    sheet = client.get(f'/api/notice/{batch}').json()
    notices = sheet['notices']
    assert notices[0]['kind'] == 'RESEND'
    assert any(n['state'] == '发布失败' for n in notices) is False
    # 失败通知已被重试恢复，送达记录里保留一条未送达
    undelivered = [d for n in notices for d in n['deliveries'] if d['outcome'] == '未送达']
    assert len(undelivered) == 1
    # 页面可渲染
    page = client.get(f'/notice?batch_id={batch}')
    assert page.status_code == 200 and '通知签收单' in page.text


def test_api_signoff_and_404_root(db, batch):
    client = TestClient(main.app)
    client.post(f'/api/notice/{batch}/publish', json={})
    ok = client.post(f'/api/notice/{batch}/signoff', json={'root_id': 'M001', 'mode': '整批统一签收'})
    assert ok.status_code == 200
    bad = client.post(f'/api/notice/{batch}/signoff', json={'root_id': 'NOPE'})
    assert bad.status_code == 404
    # 模块统一入口
    assert client.post('/api/notice', json={'batch_id': batch}).status_code == 200


def test_scenario_fail_flag_propagates(db, batch):
    client = TestClient(main.app)
    r = client.post(f'/api/notice/{batch}/publish', json={'scenario': 'v4_fail'})
    body = r.json()
    assert body['state'] == '发布失败'
    assert body['deliveries'][0]['outcome'] == '未送达'
    # 显式 simulate_fail 同样生效
    r2 = client.post(f'/api/notice/{batch}-2/publish', json={'simulate_fail': True})
    assert r2.json()['state'] == '发布失败'
