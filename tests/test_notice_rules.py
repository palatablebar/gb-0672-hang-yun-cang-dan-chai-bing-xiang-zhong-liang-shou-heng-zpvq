from app.modules.notice.rules import (
    RELATION, WEIGHT, RESEND, NO_CHANGE, CHANGE_TEXT,
    fingerprints, diff_roots, classify, adjudicate, current_basis,
    build_sheet, attach_signoffs,
)
from copy import deepcopy


def snap(state):
    rel, wgt = fingerprints(state['records'], state['graph']['children'], state['graph']['roots'])
    return {'roots': list(state['graph']['roots']), 'relation_fp': rel, 'weight_fp': wgt}


def change_root_gross(state, root, delta='8'):
    nxt = deepcopy(state)
    for row in nxt['records']:
        if row['id'] == root:
            from decimal import Decimal
            row['gross_kg'] = str(Decimal(row['gross_kg']) + Decimal(delta))
    return nxt


def add_child(state, root, new_id):
    nxt = deepcopy(state)
    parent_row = next(r for r in nxt['records'] if r['id'] == root)
    nxt['records'].append({
        'id': new_id, 'parent': root, 'pieces': 10,
        'net_kg': '100', 'gross_kg': '110',
        'hazard': 'none', 'un_code': '', 'container': parent_row['container'],
        'revision': 2,
    })
    nxt['graph']['children'].setdefault(root, []).append(new_id)
    return nxt


def test_weight_change_isolated_to_one_root(clean):
    base = snap(clean)
    nxt = snap(change_root_gross(clean, 'M002'))
    diff = diff_roots(base, nxt)
    assert diff[WEIGHT] == {'M002'}
    assert diff[RELATION] == set()
    kind, affected, changes = classify(diff)
    assert kind == WEIGHT and affected == {'M002'}
    assert changes['M002'] == CHANGE_TEXT[WEIGHT]


def test_relation_change_takes_priority_over_weight(clean):
    altered = add_child(change_root_gross(clean, 'M003'), 'M003', 'M003-P3')
    diff = diff_roots(snap(clean), snap(altered))
    assert diff[RELATION] == {'M003'}
    assert diff[WEIGHT] == set()


def test_first_publish_treats_every_root_as_relation(clean):
    diff = diff_roots(None, snap(clean))
    assert diff[RELATION] == set(clean['graph']['roots'])
    decision = adjudicate({**diff, 'current_roots': clean['graph']['roots']})
    assert decision['mode'] == '整批统一签收'


def test_partial_affected_allows_early_signoff(clean):
    nxt = snap(change_root_gross(clean, 'M002'))
    diff = diff_roots(snap(clean), nxt)
    decision = adjudicate({**diff, 'current_roots': nxt['roots']})
    assert decision['mode'] == '受影响主单先行签收'
    assert decision['partial'] is True
    assert decision['affected'] == ['M002']


def test_all_roots_changed_forces_batch_signoff(clean):
    altered = deepcopy(clean)
    from decimal import Decimal
    for row in altered['records']:
        if row['id'] in clean['graph']['roots']:
            row['gross_kg'] = str(Decimal(row['gross_kg']) + Decimal('5'))
    diff = diff_roots(snap(clean), snap(altered))
    decision = adjudicate({**diff, 'current_roots': altered['graph']['roots']})
    assert decision['mode'] == '整批统一签收'


def test_missing_root_forces_batch_signoff(clean):
    nxt = deepcopy(clean)
    nxt['graph']['roots'] = [r for r in nxt['graph']['roots'] if r != 'M006']
    diff = diff_roots(snap(clean), snap(nxt))
    assert diff['missing'] == {'M006'}
    decision = adjudicate({**diff, 'current_roots': nxt['graph']['roots']})
    assert decision['mode'] == '整批统一签收'


def test_identical_payload_is_resend_and_batch_decision(clean):
    diff = {RELATION: set(), WEIGHT: set(), 'missing': set(), 'all': set()}
    kind, affected, changes = classify(diff)
    assert kind == RESEND and affected == set() and changes == {}
    decision = adjudicate({**diff, 'current_roots': clean['graph']['roots']})
    assert decision['mode'] == '整批统一签收'
    assert '不新增第二套签收' in decision['reason']


def _notice(no, version, roots, affected, changes, state='已发布'):
    return {'notice_no': no, 'notice_version': version, 'state': state,
            'roots': roots, 'affected': affected, 'changes': changes}


def test_current_basis_resend_keeps_old_for_unaffected():
    v1 = _notice('N-V1', 1, ['M001', 'M002'], ['M001', 'M002'],
                 {'M001': CHANGE_TEXT[RELATION], 'M002': CHANGE_TEXT[RELATION]})
    v2 = _notice('N-V2', 2, ['M001', 'M002'], ['M002'], {'M002': CHANGE_TEXT[WEIGHT]})
    v3 = _notice('N-V3', 3, ['M001', 'M002'], [], {})
    history = [v3, v2, v1]
    # 重发不改变依据：M001 实质依据停留在首发 N-V1，M002 的实质依据是 N-V2
    assert current_basis(history, 'M001')['notice_no'] == 'N-V1'
    assert current_basis(history, 'M002')['notice_no'] == 'N-V2'


def test_failed_notice_never_basis():
    v1 = _notice('N-V1', 1, ['M001'], ['M001'], {})
    failed = _notice('N-V2', 2, ['M001'], ['M001'], {'M001': CHANGE_TEXT[WEIGHT]}, state='发布失败')
    assert current_basis([failed, v1], 'M001')['notice_no'] == 'N-V1'


def test_sheet_marks_superseded_signoff_undeclarable():
    v1 = _notice('N-V1', 1, ['M001', 'M002'], ['M001', 'M002'],
                 {'M001': CHANGE_TEXT[RELATION], 'M002': CHANGE_TEXT[RELATION]})
    v2 = _notice('N-V2', 2, ['M001', 'M002'], ['M002'], {'M002': CHANGE_TEXT[WEIGHT]})
    rows, latest = build_sheet([v2, v1], {'M001': '甲岗', 'M002': '乙岗'})
    assert latest['notice_no'] == 'N-V2'
    m2 = next(r for r in rows if r['id'] == 'M002')
    m1 = next(r for r in rows if r['id'] == 'M001')
    assert m2['basis_notice'] == 'N-V2' and '替代 N-V1' in m2['replaces']
    # M001 未受 V2 影响，继续沿用 N-V1
    assert m1['basis_notice'] == 'N-V1' and '继续沿用 N-V1' in m1['replaces']
    rows = attach_signoffs(rows, [
        {'root_id': 'M001', 'notice_no': 'N-V1'},
        {'root_id': 'M002', 'notice_no': 'N-V1'},
    ])
    m1 = next(r for r in rows if r['id'] == 'M001')
    m2 = next(r for r in rows if r['id'] == 'M002')
    assert m1['signoff_status'] == '已签收 N-V1' and m1['can_declare'] == '可申报'
    assert m2['signoff_status'].startswith('签收已失效')
    assert m2['can_declare'] == '不可申报'
