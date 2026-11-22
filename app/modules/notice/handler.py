from fastapi import APIRouter, Body, Request

from app import store as run_store
from app.errors import BusinessError
from app.modules.notice import scenarios, service, store
from app.web import render

router = APIRouter()


@router.get('/notice')
def page(request: Request):
    return render(request, 'notice')


@router.post('/api/notice')
def calculate(payload: dict = Body(default={})):
    """模块统一入口：返回当前批次的通知签收单。"""
    from app.main import DB_PATH
    batch_id = payload.get('batch_id', 'batch-20261117')
    run = run_store.get(DB_PATH, payload['run_id']) if payload.get('run_id') else scenarios.base_run()
    result = service.sheet(DB_PATH, batch_id, run)
    for notice in result['notices']:
        notice['deliveries'] = store.list_deliveries(DB_PATH, notice['notice_no'])
    return result


@router.get('/api/notice/{batch_id}')
def get_sheet(batch_id: str, run_id: str = ''):
    from app.main import DB_PATH
    run = run_store.get(DB_PATH, run_id) if run_id else scenarios.base_run()
    result = service.sheet(DB_PATH, batch_id, run)
    for notice in result['notices']:
        notice['deliveries'] = store.list_deliveries(DB_PATH, notice['notice_no'])
    return result


@router.post('/api/notice/{batch_id}/publish')
def publish(batch_id: str, payload: dict = Body(default={})):
    """发布通知。run_id 缺省时按 scenario 取演示批次；simulate_fail 模拟发布失败。"""
    from app.main import DB_PATH
    scenario = payload.get('scenario', '')
    simulate_fail = bool(payload.get('simulate_fail', False))
    if payload.get('run_id'):
        run = run_store.get(DB_PATH, payload['run_id'])
    elif scenario:
        if scenario not in scenarios.SCENARIOS:
            raise BusinessError('BAD_SCENARIO', '演示场景不存在')
        run, spec = scenarios.scenario_run(scenario)
        simulate_fail = simulate_fail or spec['fail']
    else:
        run = scenarios.base_run()
    notice = service.publish(DB_PATH, batch_id, run, simulate_fail)
    notice['deliveries'] = store.list_deliveries(DB_PATH, notice['notice_no'])
    return notice


@router.post('/api/notice/{batch_id}/publish-demo')
def publish_demo(batch_id: str, payload: dict = Body(default={})):
    """一键铺出连续修订演示链：V1首发 → V2重量 → V3关系 → V4失败 → V4重试 → V4同版重发。"""
    from app.main import DB_PATH
    chain = []
    v1 = service.publish(DB_PATH, batch_id, scenarios.base_run())
    chain.append(v1['notice_no'])
    v2, _ = scenarios.scenario_run('v2_weight')
    n2 = service.publish(DB_PATH, batch_id, v2)
    chain.append(n2['notice_no'])
    v3, _ = scenarios.scenario_run('v3_relation')
    n3 = service.publish(DB_PATH, batch_id, v3)
    chain.append(n3['notice_no'])
    v4, _ = scenarios.scenario_run('v4_fail')
    n4 = service.publish(DB_PATH, batch_id, v4, simulate_fail=True)
    chain.append(n4['notice_no'])
    recovered = service.retry_delivery(DB_PATH, n4['notice_no'])
    chain.append('retry:' + recovered['notice_no'])
    v4_again, _ = scenarios.scenario_run('v4_weight')
    resend = service.publish(DB_PATH, batch_id, v4_again)
    chain.append(resend['notice_no'])
    return {'batch_id': batch_id, 'chain': chain,
            'scenarios': {k: v['label'] for k, v in scenarios.SCENARIOS.items()}}


@router.post('/api/notice/delivery/{notice_no}/retry')
def retry(notice_no: str):
    from app.main import DB_PATH
    return service.retry_delivery(DB_PATH, notice_no)


@router.post('/api/notice/{batch_id}/signoff')
def signoff(batch_id: str, payload: dict = Body(...)):
    from app.main import DB_PATH
    root_id = payload.get('root_id')
    run_id = payload.get('run_id', '')
    run = run_store.get(DB_PATH, run_id) if run_id else scenarios.base_run()
    mode = payload.get('mode', '受影响主单先行签收')
    if root_id:
        return service.sign(DB_PATH, batch_id, run, root_id, mode)
    return service.sign_batch(DB_PATH, batch_id, run, mode)
