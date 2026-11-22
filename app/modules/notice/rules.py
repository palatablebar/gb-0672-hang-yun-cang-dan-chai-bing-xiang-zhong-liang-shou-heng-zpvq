"""通知签收领域规则。

拆并方案连续修订时，报关行会收到整批重发通知。本模块只做可复核的纯计算：
- 以主单整棵拆并子树（关系指纹 + 件净毛重指纹）刻画通知所携带的依据；
- 逐张主单判定本次变化、适用版本、旧通知的替代关系与能否申报；
- 裁决整批统一签收，还是受影响主单凭当前依据先行签收。

新修订一旦改变拆并关系或件净毛重，旧通知对受影响主单不再是当前依据；
内容不变的重试只是重发，沿用既有签收，不新增第二套签收。
"""
from decimal import Decimal

RELATION = 'RELATION_CHANGE'
WEIGHT = 'WEIGHT_CHANGE'
RESEND = 'RESEND'
NO_CHANGE = 'NO_CHANGE'

CHANGE_TEXT = {
    RELATION: '拆并关系变化',
    WEIGHT: '件净毛重变化',
    NO_CHANGE: '内容无变化（整批重发）',
}


def subtree(root, children):
    """主单整棵拆并子树的节点集合，含主单自身。"""
    stack, seen = [root], set()
    while stack:
        node = stack.pop()
        if node in seen:
            continue
        seen.add(node)
        stack.extend(children.get(node, []))
    return seen


def fingerprints(records, children, roots):
    """关系指纹与重量指纹。任一变化都会使旧通知失效。"""
    nodes = {r['id']: r for r in records}
    relation_fp, weight_fp = {}, {}
    for root in roots:
        members = subtree(root, children)
        edges = sorted(
            (parent, child)
            for parent in members
            for child in children.get(parent, [])
        )
        relation_fp[root] = tuple(edges)
        totals = {'pieces': 0, 'net_kg': Decimal(0), 'gross_kg': Decimal(0)}
        for member in sorted(members):
            row = nodes[member]
            totals['pieces'] += row['pieces']
            totals['net_kg'] += Decimal(str(row['net_kg']))
            totals['gross_kg'] += Decimal(str(row['gross_kg']))
        weight_fp[root] = (totals['pieces'], str(totals['net_kg']), str(totals['gross_kg']))
    return relation_fp, weight_fp


def _norm(snapshot):
    """规整 JSON 往返后的 list 为 tuple，使两次指纹可比较。"""
    return {
        'roots': list(snapshot['roots']),
        'relation_fp': {
            root: [tuple(edge) for edge in edges]
            for root, edges in snapshot['relation_fp'].items()
        },
        'weight_fp': {root: tuple(values) for root, values in snapshot['weight_fp'].items()},
    }


def diff_roots(previous, current):
    """比较两次发布，返回各变化类型下的主单集合。

    previous 为 None 表示首次发布。关系变化与重量变化可能同时命中，
    按“拆并关系优先”归类，保证一张主单只归一个变化类型。
    """
    current = _norm(current)
    if previous is not None:
        previous = _norm(previous)
    cur_roots = set(current['roots'])
    prev_roots = set(previous['roots']) if previous else set()
    relation_changed, weight_changed, missing = set(), set(), set()
    for root in sorted(cur_roots):
        if previous is None or root not in prev_roots:
            relation_changed.add(root)
            continue
        if current['relation_fp'][root] != previous['relation_fp'][root]:
            relation_changed.add(root)
        elif current['weight_fp'][root] != previous['weight_fp'][root]:
            weight_changed.add(root)
    if previous is not None:
        missing = prev_roots - cur_roots
    return {
        RELATION: relation_changed,
        WEIGHT: weight_changed,
        'missing': missing,
        'all': relation_changed | weight_changed,
    }


def classify(diff):
    """把差异集合压成发布级别分类与逐主单变化标注。"""
    affected = diff[RELATION] | diff[WEIGHT]
    changes = {root: CHANGE_TEXT[RELATION] for root in diff[RELATION]}
    changes.update({root: CHANGE_TEXT[WEIGHT] for root in diff[WEIGHT]})
    if not affected and not diff['missing']:
        kind = RESEND
    elif affected == set() and diff['missing']:
        kind = RELATION
    else:
        kind = RELATION if diff[RELATION] or diff['missing'] else WEIGHT
    return kind, affected, changes


def adjudicate(diff):
    """签收裁决。

    - 无受影响主单：整批重发，整批统一签收，重发不新增第二套签收；
    - 部分主单受影响：受影响主单凭当前依据先行签收，未受影响主单沿用原签收不重签；
    - 全部主单受影响或有主单被拆并删除：整批统一签收。
    """
    affected = diff[RELATION] | diff[WEIGHT]
    current_roots = set(diff.get('current_roots', ()))
    if not affected and not diff['missing']:
        return {
            'mode': '整批统一签收',
            'reason': '整批重发且内容无变化，沿用既有签收，重试不新增第二套签收',
            'partial': False,
        }
    if diff['missing'] or not current_roots or affected == current_roots:
        return {
            'mode': '整批统一签收',
            'reason': '新修订改变全部主单或存在主单被拆并删除，旧依据无法逐张沿用，整批统一签收',
            'partial': False,
        }
    return {
        'mode': '受影响主单先行签收',
        'reason': '仅部分主单的拆并关系或件净毛重变化，受影响主单凭当前依据先行签收，未受影响主单不重签',
        'partial': True,
        'affected': sorted(affected),
    }


def current_basis(history, root):
    """一张主单当前依据的通知：最近一次实质覆盖该主单的成功发布。

    重发（受影响为空）只刷新送达、承载整批重发记录，不替代任何主单的依据；
    受影响主单以修订后的新通知为依据，未受影响主单继续沿用旧通知。
    """
    for notice in history:
        if notice['state'] != '已发布':
            continue
        affected = set(notice['affected'])
        if not affected:
            continue
        if root in affected:
            return notice
    return None


def build_sheet(history, receivers):
    """逐张主单生成通知签收单行。history 按发布时间倒序。"""
    published = [n for n in history if n['state'] == '已发布']
    if not published:
        return [], None
    latest = published[0]
    is_resend = not set(latest['affected'])
    rows = []
    for root in latest['roots']:
        basis = current_basis(published, root)
        change = latest['changes'].get(root, CHANGE_TEXT[NO_CHANGE])
        if basis is None:
            replaces, basis_no, can_declare = '无在效通知', '', False
        else:
            basis_no = basis['notice_no']
            prior = next((n for n in published if n['notice_no'] != basis_no
                          and (not set(n['affected']) or root in set(n['affected']))), None)
            if is_resend:
                # 整批重发：依据不变，沿用既有签收，不新增第二套签收
                replaces = '重发沿用 {}，不新增第二套签收'.format(basis_no)
            elif basis['notice_no'] == latest['notice_no']:
                replaces = ('替代 {}（旧通知对该主单失效，不得继续作为依据）'.format(prior['notice_no'])
                            if prior else '首次发布，无旧通知')
            else:
                replaces = '继续沿用 {}（本次修订未影响该主单）'.format(basis_no)
            can_declare = bool(basis)
        rows.append({
            'id': root,
            'notice_no': latest['notice_no'],
            'notice_version': latest['notice_version'],
            'receiver': receivers.get(root, '报关行-默认签收岗'),
            'change': change,
            'basis_notice': basis_no,
            'replaces': replaces,
            'can_declare': '可申报' if can_declare else '不可申报',
            'signoff_status': '待签收',
        })
    return rows, latest


def attach_signoffs(rows, signoffs):
    """把持久化签收结果合并进签收单，并据当前依据判定能否申报。

    一张主单可能留下多套历史签收（依据被替代后重签），只取最近一套判断。
    """
    index = {}
    for signed in signoffs:
        index[signed['root_id']] = signed
    for row in rows:
        signed = index.get(row['id'])
        if signed is None:
            row['signoff_status'] = '待签收'
            row['can_declare'] = '不可申报'
        elif signed['notice_no'] != row['basis_notice']:
            row['signoff_status'] = '签收已失效（依据被新修订替代）'
            row['can_declare'] = '不可申报'
        else:
            row['signoff_status'] = '已签收 {}'.format(signed['notice_no'])
            row['can_declare'] = '可申报' if row['basis_notice'] else '不可申报'
    return rows
