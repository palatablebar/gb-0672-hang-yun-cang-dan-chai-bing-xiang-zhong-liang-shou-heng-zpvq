"""通知签收服务：把舱单批次结果转成通知发布、重试与签收动作。"""
import hashlib
import json
from datetime import datetime, timezone

from app.errors import BusinessError
from app.modules.notice import rules, store

DEFAULT_BATCH = 'batch-20261117'


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def payload_digest(run):
    """通知载荷指纹：同输入重试得到相同指纹，用于识别整批重发。"""
    raw = json.dumps(
        {'roots': run['graph']['roots'], 'children': run['graph']['children'],
         'records': [
             {k: r[k] for k in ('id', 'parent', 'pieces', 'net_kg', 'gross_kg')}
             for r in run['records']
         ]},
        sort_keys=True, ensure_ascii=False,
    ).encode()
    return hashlib.sha256(raw).hexdigest()


def snapshot_of(run):
    relation_fp, weight_fp = rules.fingerprints(
        run['records'], run['graph']['children'], run['graph']['roots']
    )
    return {
        'roots': list(run['graph']['roots']),
        'relation_fp': {k: [list(edge) for edge in v] for k, v in relation_fp.items()},
        'weight_fp': {k: list(v) for k, v in weight_fp.items()},
    }


def history_snapshot(notice):
    """把持久化通知还原成 diff_roots 所需结构。"""
    return {
        'roots': notice['roots'],
        'relation_fp': {k: [tuple(edge) for edge in v] for k, v in notice['relation_fp'].items()},
        'weight_fp': {k: tuple(v) for k, v in notice['weight_fp'].items()},
    }


def publish(db_path, batch_id, run, simulate_fail=False):
    """基于一个舱单批次发布通知。

    同载荷重发：生成新通知编号但判定为 RESEND，裁决整批统一签收且不新增第二套签收；
    新修订：按主单指纹比较拆并关系与件净毛重，逐张标注受影响范围；
    simulate_fail：通知落为发布失败，保留未送达记录，当前依据仍是上一版。
    """
    history = store.list_notices(db_path, batch_id)
    if any(n['state'] == '发布失败' for n in history):
        raise BusinessError(
            'PENDING_FAILURE',
            '存在发布失败通知，须先重试恢复或保留失败记录，不得再发布新修订',
            409,
        )
    digest = payload_digest(run)
    relation_fp, weight_fp = rules.fingerprints(
        run['records'], run['graph']['children'], run['graph']['roots']
    )
    current = {'roots': list(run['graph']['roots']),
               'relation_fp': relation_fp, 'weight_fp': weight_fp}
    identical = next((n for n in history if n['payload_digest'] == digest), None)
    if identical is not None:
        diff = {rules.RELATION: set(), rules.WEIGHT: set(), 'missing': set(), 'all': set()}
        kind, affected, changes = rules.RESEND, set(), {}
        is_resend = True
    else:
        previous = next((n for n in history if n['state'] == '已发布'), None)
        prev_snap = history_snapshot(previous) if previous else None
        diff = rules.diff_roots(prev_snap, current)
        kind, affected, changes = rules.classify(diff)
        is_resend = False
    diff['current_roots'] = current['roots']
    decision = rules.adjudicate(diff)
    version = max((n['notice_version'] for n in history), default=0) + 1
    notice_no = 'N-{}-V{}'.format(batch_id, version)
    notice = {
        'notice_no': notice_no,
        'batch_id': batch_id,
        'notice_version': version,
        'run_id': run['manifest']['run_id'],
        'state': '发布失败' if simulate_fail else '已发布',
        'kind': kind,
        'payload_digest': digest,
        'roots': current['roots'],
        'affected': sorted(affected),
        'changes': changes,
        'decision': decision,
        'snapshot': snapshot_of(run),
        'created_at': now_iso(),
    }
    delivery = {
        'notice_no': notice_no,
        'attempt': 1,
        'outcome': '未送达' if simulate_fail else '已送达',
        'detail': '模拟发布失败：网关超时，恢复旧版并保留未送达记录' if simulate_fail
                  else '整批通知已送达全部接收方',
        'created_at': now_iso(),
    }
    saved = store.create_notice(db_path, notice, delivery)
    saved['is_resend'] = is_resend
    return saved


def retry_delivery(db_path, notice_no):
    """同一通知重试：幂等，不新增第二套签收；失败通知重试成功后恢复为已发布。"""
    notice = store.get_notice(db_path, notice_no)
    attempt = store.next_attempt(db_path, notice_no)
    if notice['state'] == '发布失败':
        store.add_delivery(db_path, {
            'notice_no': notice_no, 'attempt': attempt,
            'outcome': '已送达', 'detail': '重试成功，恢复旧版依据',
            'created_at': now_iso(),
        })
        notice = store.mark_published(db_path, notice_no, now_iso())
        notice['recovered'] = True
    else:
        store.add_delivery(db_path, {
            'notice_no': notice_no, 'attempt': attempt,
            'outcome': '已送达', 'detail': '整批重发：内容无变化，沿用既有签收，不新增第二套签收',
            'created_at': now_iso(),
        })
        notice['recovered'] = False
    notice['deliveries'] = store.list_deliveries(db_path, notice_no)
    return notice


def receivers_of(run):
    return run.get('context', {}).get('receivers', {})


def sheet(db_path, batch_id, run):
    """装配通知签收单：逐张主单写清变化、版本、接收方、能否申报与替代关系。"""
    history = store.list_notices(db_path, batch_id)
    rows, latest = rules.build_sheet(history, receivers_of(run))
    signoffs = store.list_signoffs(db_path, batch_id)
    rows = rules.attach_signoffs(rows, signoffs)
    failed = next((n for n in history if n['state'] == '发布失败'), None)
    return {
        'batch_id': batch_id,
        'rows': rows,
        'latest_notice': latest,
        'failed_notice': failed,
        'notices': history,
        'signoffs': signoffs,
        'receivers': receivers_of(run),
    }


def sign(db_path, batch_id, run, root_id, mode):
    """单张主单签收。只允许签收当前依据通知，旧通知签收会被拒。"""
    current = sheet(db_path, batch_id, run)
    if current['failed_notice'] is not None:
        raise BusinessError('PENDING_FAILURE', '存在发布失败通知，须先重试恢复后再签收', 409)
    row = next((r for r in current['rows'] if r['id'] == root_id), None)
    if row is None:
        raise BusinessError('ROOT_UNKNOWN', '主单不在当前通知范围内', 404)
    if not row['basis_notice']:
        raise BusinessError('NO_BASIS_NOTICE', '该主单没有在效通知，不能签收', 409)
    return store.add_signoff(db_path, batch_id, root_id, row['basis_notice'], mode, now_iso())


def sign_batch(db_path, batch_id, run, mode):
    """按裁决整批或受影响范围签收。"""
    current = sheet(db_path, batch_id, run)
    if current['latest_notice'] is None:
        raise BusinessError('NO_NOTICE', '尚无成功发布的通知', 409)
    if current['failed_notice'] is not None:
        raise BusinessError('PENDING_FAILURE', '存在发布失败通知，须先重试恢复后再签收', 409)
    if mode == '整批统一签收':
        targets = [r['id'] for r in current['rows']]
    elif mode == '受影响主单先行签收':
        targets = [r['id'] for r in current['rows']
                   if r['change'] != rules.CHANGE_TEXT[rules.NO_CHANGE]]
        if not targets:
            raise BusinessError('NO_AFFECTED_ROOT', '本次重发无受影响主单，应整批统一签收', 409)
    else:
        raise BusinessError('BAD_SIGN_MODE', '签收模式须为整批统一签收或受影响主单先行签收')
    results = []
    for root_id in targets:
        row = next(r for r in current['rows'] if r['id'] == root_id)
        if row['basis_notice']:
            results.append(store.add_signoff(
                db_path, batch_id, root_id, row['basis_notice'], mode, now_iso()
            ))
    return {'mode': mode, 'signed': results, 'count': len(results)}
