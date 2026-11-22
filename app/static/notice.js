const cfg = JSON.parse(document.querySelector('#notice-context').textContent);
const BATCH = cfg.batch_id;
const message = document.querySelector('#message');

async function call(url, options) {
  const response = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  const data = await response.json();
  if (!response.ok) throw Error(data.detail || '请求失败');
  return data;
}

function flash(text, ok = true) {
  message.textContent = text;
  message.style.color = ok ? '' : '#a33';
}

async function refresh() {
  const data = await call(`/api/notice/${BATCH}?run_id=${document.body.dataset.runId}`);
  renderSheet(data);
  renderChain(data);
  renderDeliveries(data);
  renderRuling(data);
}

function renderSheet(data) {
  const tbody = document.querySelector('#signoff-table tbody');
  if (!data.rows.length) {
    tbody.innerHTML = '<tr><td colspan="10">尚无成功发布的通知，先发布或铺演示修订链。</td></tr>';
    return;
  }
  tbody.innerHTML = data.rows.map(row => `
    <tr data-root="${row.id}">
      <td>${row.id}</td><td>${row.notice_no || '—'}</td>
      <td class="num">${row.notice_version || '—'}</td><td>${row.receiver}</td>
      <td>${row.change}</td><td>${row.basis_notice || '无'}</td>
      <td class="replace-cell">${row.replaces}</td>
      <td class="signoff-cell">${row.signoff_status}</td>
      <td class="declare-cell ${row.can_declare !== '可申报' ? 'fail' : ''}">${row.can_declare}</td>
      <td><button class="mini sign-one" data-root="${row.id}" ${row.basis_notice ? '' : 'disabled'}>签收</button></td>
    </tr>`).join('');
  tbody.querySelectorAll('.sign-one').forEach(btn =>
    btn.addEventListener('click', () => signOne(btn.dataset.root)));
}

function renderChain(data) {
  const box = document.querySelector('#notice-chain');
  box.innerHTML = data.notices.length
    ? data.notices.map(n => `
      <div class="checkline"><b>${n.notice_no}</b>
        <span class="state-tag ${n.state === '发布失败' ? 'fail' : ''}">${n.state}</span>
        <span>${n.kind}</span>
        <small>受影响 ${n.affected.length ? n.affected.join('、') : '无（整批重发）'}</small>
      </div>`).join('')
    : '<div class="checkline"><span>暂无通知。</span></div>';
}

function renderDeliveries(data) {
  const box = document.querySelector('#delivery-log');
  const lines = data.notices.flatMap(n =>
    (n.deliveries || []).map(d => `
      <div class="checkline"><b>${n.notice_no}#${d.attempt}</b>
        <span class="state-tag ${d.outcome !== '已送达' ? 'fail' : ''}">${d.outcome}</span>
        <small>${d.detail || ''}</small></div>`));
  box.innerHTML = lines.length ? lines.join('') : '<div class="checkline"><span>暂无送达记录。</span></div>';
}

function renderRuling(data) {
  const ruling = document.querySelector('.ruling');
  const failed = data.failed_notice;
  const latest = data.latest_notice;
  let html = '<h3>签收裁决</h3>';
  if (latest) {
    html += `<div class="stamp" id="decision-stamp">${latest.decision.mode}</div>
      <p id="decision-reason">${latest.decision.reason}</p>
      <div class="toolbox">
        <button id="sign-batch" class="mini">按裁决整批统一签收</button>
        <button id="sign-affected" class="mini">受影响主单先行签收</button>
      </div>`;
  } else {
    html += '<div class="stamp">待发布</div><p>发布首版通知后形成裁决。</p>';
  }
  if (failed) {
    html += `<div class="stamp fail-stamp">发布失败 ${failed.notice_no}</div>
      <p>已恢复旧版依据，未送达记录保留；重试成功前不得发布新修订。</p>
      <button id="retry-failed" class="mini" data-notice="${failed.notice_no}">重试失败通知</button>`;
  }
  ruling.innerHTML = html;
  const batchBtn = ruling.querySelector('#sign-batch');
  const affectedBtn = ruling.querySelector('#sign-affected');
  if (batchBtn) batchBtn.addEventListener('click', () => signMode('整批统一签收'));
  if (affectedBtn) affectedBtn.addEventListener('click', () => signMode('受影响主单先行签收'));
  const retryBtn = ruling.querySelector('#retry-failed');
  if (retryBtn) retryBtn.addEventListener('click', () => retryNotice(retryBtn.dataset.notice));
}

async function signOne(root) {
  try {
    await call(`/api/notice/${BATCH}/signoff`, {
      method: 'POST',
      body: JSON.stringify({ root_id: root, run_id: document.body.dataset.runId, mode: '受影响主单先行签收' }),
    });
    flash(`${root} 已按当前依据签收`);
    refresh();
  } catch (e) { flash(e.message, false); }
}

async function signMode(mode) {
  try {
    const result = await call(`/api/notice/${BATCH}/signoff`, {
      method: 'POST',
      body: JSON.stringify({ mode, run_id: document.body.dataset.runId }),
    });
    flash(`${mode}完成，签收 ${result.count} 张主单`);
    refresh();
  } catch (e) { flash(e.message, false); }
}

async function retryNotice(noticeNo) {
  try {
    await call(`/api/notice/delivery/${noticeNo}/retry`, { method: 'POST', body: '{}' });
    flash(`${noticeNo} 重试成功，已恢复为已发布`);
    refresh();
  } catch (e) { flash(e.message, false); }
}

document.querySelector('#demo-chain').addEventListener('click', async () => {
  try {
    const data = await call(`/api/notice/${BATCH}/publish-demo`, { method: 'POST', body: '{}' });
    flash(`演示链已铺好：${data.chain.length} 个动作`);
    refresh();
  } catch (e) { flash(e.message, false); }
});

document.querySelector('#publish-base').addEventListener('click', async () => {
  try {
    const data = await call(`/api/notice/${BATCH}/publish`, {
      method: 'POST',
      body: JSON.stringify({ run_id: document.body.dataset.runId }),
    });
    flash(`${data.notice_no} 已发布（${data.state}）`);
    refresh();
  } catch (e) { flash(e.message, false); }
});

document.querySelector('#publish-scenario').addEventListener('click', async () => {
  const scenario = document.querySelector('#scenario-pick').value;
  try {
    const data = await call(`/api/notice/${BATCH}/publish`, {
      method: 'POST',
      body: JSON.stringify({ scenario }),
    });
    flash(`${data.notice_no} 已发布（${data.state}）`);
    refresh();
  } catch (e) { flash(e.message, false); }
});

document.querySelectorAll('.sign-one').forEach(btn =>
  btn.addEventListener('click', () => signOne(btn.dataset.root)));
