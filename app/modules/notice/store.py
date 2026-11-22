"""通知签收持久化。

三张表：
- notices  通知主档，含成功发布与发布失败（恢复旧版）两种状态；
- deliveries 每次发布/重试的送达记录，失败记录永久保留；
- signoffs 签收记录，(批次,主单) 唯一，重试同一通知不新增第二套签收。
"""
import json
import sqlite3
from pathlib import Path

from app.errors import BusinessError


def connect(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA journal_mode=WAL')
    con.execute(
        'CREATE TABLE IF NOT EXISTS notices ('
        'notice_no TEXT PRIMARY KEY, batch_id TEXT NOT NULL, notice_version INTEGER NOT NULL,'
        'run_id TEXT, state TEXT NOT NULL, kind TEXT NOT NULL,'
        'payload_digest TEXT NOT NULL, roots TEXT NOT NULL, affected TEXT NOT NULL,'
        'changes TEXT NOT NULL, decision TEXT NOT NULL, snapshot TEXT NOT NULL,'
        'created_at TEXT NOT NULL)'
    )
    con.execute(
        'CREATE TABLE IF NOT EXISTS deliveries ('
        'id INTEGER PRIMARY KEY AUTOINCREMENT, notice_no TEXT NOT NULL,'
        'attempt INTEGER NOT NULL, outcome TEXT NOT NULL, detail TEXT,'
        'created_at TEXT NOT NULL)'
    )
    con.execute(
        'CREATE TABLE IF NOT EXISTS signoffs ('
        'id INTEGER PRIMARY KEY AUTOINCREMENT, batch_id TEXT NOT NULL, root_id TEXT NOT NULL,'
        'notice_no TEXT NOT NULL, mode TEXT NOT NULL, created_at TEXT NOT NULL,'
        'UNIQUE(batch_id, root_id, notice_no))'
    )
    return con


def _notice(row):
    data = dict(row)
    data['roots'] = json.loads(data['roots'])
    data['affected'] = json.loads(data['affected'])
    data['changes'] = json.loads(data['changes'])
    data['decision'] = json.loads(data['decision'])
    snap = json.loads(data.pop('snapshot'))
    # JSON 往返后 tuple 退化为 list，这里恢复成 tuple，保证跨修订指纹可直接比较
    data['relation_fp'] = {k: [tuple(edge) for edge in v] for k, v in snap['relation_fp'].items()}
    data['weight_fp'] = {k: tuple(v) for k, v in snap['weight_fp'].items()}
    return data

def list_notices(path, batch_id):
    with connect(path) as con:
        rows = con.execute(
            'SELECT * FROM notices WHERE batch_id=? ORDER BY rowid DESC', (batch_id,)
        ).fetchall()
    return [_notice(r) for r in rows]


def get_notice(path, notice_no):
    with connect(path) as con:
        row = con.execute('SELECT * FROM notices WHERE notice_no=?', (notice_no,)).fetchone()
    if not row:
        raise BusinessError('NOTICE_NOT_FOUND', '通知不存在', 404)
    return _notice(row)


def latest_published(path, batch_id):
    with connect(path) as con:
        row = con.execute(
            "SELECT * FROM notices WHERE batch_id=? AND state='已发布' ORDER BY rowid DESC LIMIT 1",
            (batch_id,),
        ).fetchone()
    return _notice(row) if row else None


def create_notice(path, notice, delivery):
    """写入通知与首条送达记录。失败通知保留未送达记录且不改变当前依据。"""
    with connect(path) as con:
        con.execute(
            'INSERT INTO notices(notice_no,batch_id,notice_version,run_id,state,kind,payload_digest,'
            'roots,affected,changes,decision,snapshot,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (
                notice['notice_no'], notice['batch_id'], notice['notice_version'],
                notice.get('run_id'), notice['state'], notice['kind'], notice['payload_digest'],
                json.dumps(notice['roots'], ensure_ascii=False),
                json.dumps(notice['affected'], ensure_ascii=False),
                json.dumps(notice['changes'], ensure_ascii=False),
                json.dumps(notice['decision'], ensure_ascii=False),
                json.dumps(notice['snapshot'], ensure_ascii=False),
                notice['created_at'],
            ),
        )
        con.execute(
            'INSERT INTO deliveries(notice_no,attempt,outcome,detail,created_at) VALUES(?,?,?,?,?)',
            (delivery['notice_no'], delivery['attempt'], delivery['outcome'],
             delivery.get('detail'), delivery['created_at']),
        )
    return get_notice(path, notice['notice_no'])


def next_attempt(path, notice_no):
    with connect(path) as con:
        row = con.execute(
            'SELECT COALESCE(MAX(attempt),0)+1 AS n FROM deliveries WHERE notice_no=?',
            (notice_no,),
        ).fetchone()
    return row['n']


def add_delivery(path, delivery):
    with connect(path) as con:
        con.execute(
            'INSERT INTO deliveries(notice_no,attempt,outcome,detail,created_at) VALUES(?,?,?,?,?)',
            (delivery['notice_no'], delivery['attempt'], delivery['outcome'],
             delivery.get('detail'), delivery['created_at']),
        )


def mark_published(path, notice_no, created_at):
    """发布失败后重试成功：恢复为已发布，旧版依据重新生效。"""
    with connect(path) as con:
        cur = con.execute(
            "UPDATE notices SET state='已发布' WHERE notice_no=? AND state='发布失败'",
            (notice_no,),
        )
        if cur.rowcount != 1:
            raise BusinessError('NOTICE_NOT_RETRYABLE', '该通知不是发布失败状态，无需重试', 409)
    return get_notice(path, notice_no)


def list_deliveries(path, notice_no):
    with connect(path) as con:
        rows = con.execute(
            'SELECT attempt,outcome,detail,created_at FROM deliveries WHERE notice_no=? ORDER BY id',
            (notice_no,),
        ).fetchall()
    return [dict(r) for r in rows]


def list_signoffs(path, batch_id):
    with connect(path) as con:
        rows = con.execute(
            'SELECT root_id,notice_no,mode,created_at FROM signoffs WHERE batch_id=? ORDER BY id',
            (batch_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def add_signoff(path, batch_id, root_id, notice_no, mode, created_at):
    """同一通知重试不能新增第二套签收：(批次,主单,依据通知) 唯一，重复签收幂等返回。

    依据被新修订替代后，旧签收行保留为失效审计记录，允许按新通知再签一套。
    """
    with connect(path) as con:
        existing = con.execute(
            'SELECT * FROM signoffs WHERE batch_id=? AND root_id=? AND notice_no=?',
            (batch_id, root_id, notice_no),
        ).fetchone()
        if existing:
            return dict(existing)
        con.execute(
            'INSERT INTO signoffs(batch_id,root_id,notice_no,mode,created_at) VALUES(?,?,?,?,?)',
            (batch_id, root_id, notice_no, mode, created_at),
        )
        row = con.execute(
            'SELECT root_id,notice_no,mode,created_at FROM signoffs '
            'WHERE batch_id=? AND root_id=? AND notice_no=?',
            (batch_id, root_id, notice_no),
        ).fetchone()
    return dict(row)
