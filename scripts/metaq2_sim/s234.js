/**
 * 场景2：税务师复核操作（7 步）——角色：税务师（sim_advisor）
 * 场景3：复核专家审批操作（8 步）——角色：复核专家（sim_expert）
 * 场景4：系统管理员配置操作（5 步）——角色：系统管理员（sim_admin）
 *
 * ★ 复核动作铁律（实测得出）：标 `*` 的动作（排除/误报/已整改/重新打开）**点击即提交**，
 *   必须先填理由再点动作按钮；点「提交复核」(doReview(null)) 会覆盖回执，
 *   造成"看起来提交了、其实没生效"的假通过。判定一律以**接口回读的状态分布**为准。
 */
const fs = require('fs');
const path = require('path');
const L = require('./lib');

const OUT = 'docs/元质量_20261016/_scenarios';
const readJson = (f) => { try { return JSON.parse(fs.readFileSync(path.join(OUT, f), 'utf-8')); } catch (e) { return null; } };
const P = readJson('_s1_project.json') || {};
const PID = P.pid;

async function reviewAction(page, actText, note, pid) {
  const set = await page.evaluate((n) => {
    const el = document.getElementById('d-note');
    if (!el) return { ok: false };
    el.value = n; return { ok: true };
  }, note);
  if (!set.ok) return { ok: false, why: '无理由输入框' };
  const clicked = await page.evaluate((t) => {
    const bs = Array.from(document.querySelectorAll('#d-actions button'));
    const b = bs.find(x => (x.innerText || '').includes(t));
    if (!b) return { ok: false, acts: bs.map(x => x.innerText.trim().replace(/\s*\*$/, '')) };
    b.click();
    return { ok: true, act: b.getAttribute('data-act') };
  }, actText);
  await page.waitForTimeout(3200);
  const msg = await page.evaluate(() => {
    const a = document.getElementById('d-flow-msg');
    const b = document.getElementById('alert');
    return [a && a.innerText, b && b.innerText].filter(Boolean).join(' | ').replace(/\s+/g, ' ');
  });
  const state = await page.evaluate(async (p) => {
    const d = await (await fetch(`/api/v1/projects/${p}/risks?page_size=25&reviewed=1`, { cache: 'no-store' })).json();
    const d2 = await (await fetch(`/api/v1/projects/${p}/risks?page_size=25`, { cache: 'no-store' })).json();
    const cnt = {};
    (d2.items || []).forEach(x => { const k = x.review_state || x.state || 'pending'; cnt[k] = (cnt[k] || 0) + 1; });
    return { reviewed: d.total, total: d2.total, by_state: cnt };
  }, pid);
  return { ok: clicked.ok, act: clicked.act, acts: clicked.acts, msg, state };
}

/** 数据准备：保证该项目至少有 `need` 条「待处理」风险。
 *
 * ★ 为什么需要（2026-10-17）：复核状态按 `risk_no` 在 events.jsonl 里**累积**，
 *   每跑一轮 S2/S3 就会消耗掉若干 pending ⇒ 多轮之后无粮，S2-05 / S3-05 恒 blocked
 *   （实测：S1 之后只剩 1 条待处理，S2-04 用掉即归零）。
 * ★ 为什么用 `reopen`：这是**产品自带的合法动作**（状态机允许回到 pending，且必留痕），
 *   用它恢复数据 ≠ 伪造数据；绝不直接改 events.jsonl。
 */
async function ensurePending(page, pid, need) {
  return page.evaluate(async (args) => {
    const [projectId, want] = args;
    const j = async (u) => (await fetch(u, { cache: 'no-store' })).json();
    const board = await j('/api/v1/risks/review-board?project_id=' + projectId);
    const pending = (board.by_state || {}).pending || 0;
    if (pending >= want) return { pending, done: 0, after: pending };
    const list = await j('/api/v1/projects/' + projectId + '/risks?page=1&page_size=60');
    const items = list.items || list.risks || [];
    const csrf = decodeURIComponent((document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/) || [])[1] || '');
    let done = 0;
    for (const it of items) {
      if (pending + done >= want) break;
      const rn = it.risk_no || it.id;
      if (!rn) continue;
      const r = await fetch('/api/v1/risks/' + encodeURIComponent(rn) + '/review', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
        body: JSON.stringify({ project_id: projectId, action: 'reopen',
          note: '场景模拟数据准备：将已处置条目重新打开以便演示复核动作（会留痕）' }),
      });
      if (r.ok) done += 1;
    }
    const after = await j('/api/v1/risks/review-board?project_id=' + projectId);
    return { pending, done, after: (after.by_state || {}).pending || 0 };
  }, [pid, need]);
}


(async () => {
  const browser = await L.newBrowser();
  const results = [];

  /* ══════════ 场景2：税务师复核 ══════════ */
  const s2 = new L.Scenario('S2', '税务师复核操作', '税务师', 'sim_advisor');
  const { page: p2 } = await L.newPage(browser, s2);

  await s2.step('登录系统', async () => {
    const url = await L.login(p2, 'sim_advisor', L.PW, s2);
    if (url.includes('/login')) { const e = await L.visibleText(p2, '#error', 200); return { result: 'fail', error: '登录失败：' + (e || '(空)') }; }
    return { note: '落点 ' + new URL(url).pathname + '；侧栏=' + ((await L.visibleText(p2, '#sidebar-user-name', 60)) || '未渲染') };
  }, { page: () => p2, shotName: '税务师登录' });

  await s2.step('打开待复核项目', async () => {
    if (!PID) return { result: 'blocked', blocker: 'S1 未产出项目 id' };
    // ★ 数据准备（2026-10-17）：pending 会逐轮被消耗光 ⇒ 先确保有 2 条可复核。
    const healed = await ensurePending(p2, PID, 2);
    if (healed.done) {
      console.log('     （数据准备：reopen ' + healed.done + ' 条，待处理 ' + healed.pending + ' → ' + healed.after + '）');
    }
    await p2.goto(L.BASE + '/risks', { waitUntil: 'domcontentloaded' });
    await p2.waitForTimeout(1600);
    await p2.evaluate(async () => (await fetch('/api/v1/risks/meta', { cache: 'no-store' })).json());
    const opts = await p2.evaluate(() => Array.from(document.getElementById('project').options).map(o => [o.value, o.textContent.trim()]));
    if (!opts.length) return { result: 'fail', error: '项目下拉为空' };
    if (!opts.some(o => o[0] === String(PID))) return { result: 'fail', error: '税务师看不到目标项目，可选=' + JSON.stringify(opts) };
    await p2.selectOption('#project', String(PID));
    await p2.waitForTimeout(3500);
    const kpi = await L.visibleText(p2, '#kpi-box', 250);
    return { note: `可选 ${opts.length} 个；KPI=${kpi}` };
  }, { page: () => p2, shotName: '待复核项目' });

  await s2.step('逐条查看风险（详情 + 证据链）', async () => {
    const n = await p2.evaluate(() => document.querySelectorAll('#tb-risks tr').length);
    if (!n) return { result: 'fail', error: '风险列表 0 行，无法逐条查看' };
    const seen = [];
    for (let i = 0; i < Math.min(3, n); i += 1) {
      const key = await p2.evaluate((idx) => {
        const b = document.querySelectorAll('#tb-risks button[data-open]')[idx];
        if (!b) return null; b.click(); return b.getAttribute('data-open');
      }, i);
      if (!key) break;
      await p2.waitForTimeout(2500);
      const len = await p2.evaluate(() => {
        const el = document.querySelector('#d-body,#detail-body');
        return el ? (el.innerText || '').replace(/\s+/g, '').length : 0;
      });
      seen.push(`${key.slice(-14)}=${len}字`);
      await p2.evaluate(() => {
        const b = Array.from(document.querySelectorAll('button')).find(x => (x.innerText || '').includes('关闭'));
        if (b) b.click();
      });
      await p2.waitForTimeout(600);
    }
    if (!seen.length) return { result: 'fail', error: '无法打开任何详情' };
    return { note: seen.join('；') };
  }, { page: () => p2, shotName: '逐条查看风险' });

  await s2.step('确认高风险', async () => {
    // ★ 必须取「待处理」条目：已复核条目再次处置会被**正确幂等拒绝**（"本次未产生变更"），
    //   那不是缺陷；用默认顺序取行会点到已复核条目 ⇒ 假失败。
    const pre = await p2.evaluate(() => {
      const st = document.getElementById('f-state');
      if (st) { const o = Array.from(st.options).find(x => /待处理|pending/.test(x.textContent) || x.value === 'pending'); if (o) st.value = o.value; }
      return st ? st.value : null;
    });
    await p2.click('#btn-search');
    await p2.waitForTimeout(3500);
    const rowInfo = await p2.evaluate(() => {
      const bs = Array.from(document.querySelectorAll('#tb-risks button[data-open]'));
      return { n: bs.length, first: bs[0] ? bs[0].getAttribute('data-open') : null };
    });
    const opened = await p2.evaluate(() => {
      const b = document.querySelector('#tb-risks button[data-open]');
      if (!b) return false; b.click(); return true;
    });
    if (!opened) return { result: 'fail', error: '列表无详情按钮', note: `state筛选=${pre} 行数=${rowInfo.n}` };
    await p2.waitForTimeout(3000);
    const acts = await p2.evaluate(() => Array.from(document.querySelectorAll('#d-actions button'))
      .map(b => b.getAttribute('data-act') + (b.getAttribute('data-note') === '1' ? '*' : '')));
    const r = await reviewAction(p2, '确认成立', '场景模拟：账证核对一致，予以确认成立', PID);
    if (!r.ok) return { result: 'fail', error: '无「确认成立」动作按钮，实际动作=' + (r.acts || []).join(',') };
    if (!/已完成|成功/.test(r.msg || '')) return { result: 'fail', error: '动作未生效，页面提示=' + (r.msg || '(空)'), note: JSON.stringify(r.state) };
    if (!((r.state.by_state.confirmed || 0) >= 1)) return { result: 'fail', error: '接口回读未见「已确认」，分布=' + JSON.stringify(r.state.by_state), note: `筛选=${pre} 首行=${rowInfo.first}` };
    return { note: `动作集=[${acts.join(',')}]；提示=${r.msg}；回读=${JSON.stringify(r.state.by_state)} 已复核 ${r.state.reviewed}/${r.state.total}` };
  }, { page: () => p2, shotName: '确认高风险' });

  await s2.step('排除误报', async () => {
    // ★ 先关闭详情抽屉：抽屉覆盖工具栏，直接点 #btn-search 会被判为不可点击（30s 超时）
    await p2.evaluate(() => {
      const b = Array.from(document.querySelectorAll('button')).find(x => (x.innerText || '').includes('关闭'));
      if (b) b.click();
      const mk = document.querySelector('.mask'); if (mk) mk.hidden = true;
      const dr = document.querySelector('.drawer'); if (dr) dr.classList.remove('open');
    });
    await p2.waitForTimeout(600);
    // ★ 判据修正（2026-10-17）：原实现**强制筛「待处理」**再取第 2 条，
    //   但上一步刚把 pending 用掉、且 pending 会逐轮耗尽 ⇒ 恒 blocked（假失败）。
    //   现改为**两路**，且都遵守状态机（`engine/risk_review.STATE_FLOW`）：
    //     · pending  → `false_positive`（误报）；
    //     · confirmed → `exclude`（排除）—— `confirmed` 的合法目标只有
    //       rectified/excluded/pending，**不含 false_positive**（已确认不能再判误报）。
    //   两路验证的是同一能力：把一条不利状态的风险**改判为非风险状态**。
    const pick = async (wantState) => {
      await p2.evaluate((st8) => {
        const st = document.getElementById('f-state');
        if (st) {
          const o = Array.from(st.options).find(x => x.value === st8)
            || Array.from(st.options).find(x => new RegExp(st8 === 'pending' ? '待处理' : '已确认').test(x.textContent));
          if (o) st.value = o.value;
        }
      }, wantState);
      await p2.click('#btn-search');
      await p2.waitForTimeout(2800);
      return p2.evaluate(() => {
        const bs = document.querySelectorAll('#tb-risks button[data-open]');
        if (!bs.length) return null;
        bs[0].click();
        return bs[0].getAttribute('data-open');
      });
    };
    let key = await pick('pending');
    let actLabel = '误报';
    let note = '场景模拟：同额发票非同一笔业务，判定为误报';
    let expectState = 'false_positive';
    if (!key) {
      // 兜底：已确认 → 排除（状态机允许）
      await p2.evaluate(() => {
        const b = Array.from(document.querySelectorAll('button')).find(x => (x.innerText || '').includes('关闭'));
        if (b) b.click();
      });
      await p2.waitForTimeout(500);
      key = await pick('confirmed');
      actLabel = '排除';
      note = '场景模拟：取得合理解释，排除该项风险';
      expectState = 'excluded';
    }
    if (!key) return { result: 'blocked', blocker: '两种状态（待处理/已确认）均无可处置条目，无法演示排除误报' };
    await p2.waitForTimeout(3000);
    const r = await reviewAction(p2, actLabel, note, PID);
    if (!r.ok) return { result: 'fail', error: `无「${actLabel}」动作按钮，实际动作=` + (r.acts || []).join(',') };
    if (!/已完成|成功/.test(r.msg || '')) return { result: 'fail', error: '排除动作未生效，页面提示=' + (r.msg || '(空)'), note: `目标=${key} act=${r.act}` };
    const got = (r.state.by_state[expectState] || 0) >= 1
      || (r.state.by_state.false_positive || 0) >= 1 || (r.state.by_state.excluded || 0) >= 1;
    if (!got) return { result: 'fail', error: '接口回读未见「误报/已排除」，分布=' + JSON.stringify(r.state.by_state) };
    return { note: `目标=${key.slice(-14)} 动作=${actLabel}(→${expectState})；提示=${r.msg}；回读=${JSON.stringify(r.state.by_state)}` };
  }, { page: () => p2, shotName: '排除误报' });

  await s2.step('添加批注', async () => {
    await p2.evaluate(() => { const t = document.getElementById('d-note'); if (t) t.value = '场景模拟批注：建议补充该期间银行流水与合同。'; });
    await p2.click('#d-cmt');
    await p2.waitForTimeout(2500);
    const cmts = await L.visibleText(p2, '#d-cmts', 300);
    if (!cmts) return { result: 'fail', error: '批注后未见批注列表内容' };
    return { note: cmts.slice(0, 200) };
  }, { page: () => p2, shotName: '添加批注' });

  await s2.step('提交复核结果（复核看板核对）', async () => {
    await p2.evaluate(() => { const t = Array.from(document.querySelectorAll('.tab')).find(x => (x.innerText || '').includes('复核看板')); if (t) t.click(); });
    await p2.waitForTimeout(4000);
    const txt = await p2.evaluate(() => {
      const a = document.getElementById('board-kpis'), b = document.getElementById('board-hint'), c = document.getElementById('board-note');
      return [a && a.innerText, b && b.innerText, c && c.innerText].filter(Boolean).join(' | ').replace(/\s+/g, ' ');
    });
    const stats = await p2.evaluate(async (p) => {
      const r = await fetch(`/api/v1/projects/${p}/risks/stats`, { cache: 'no-store' });
      return r.ok ? await r.json() : null;
    }, PID);
    if (!txt && !stats) return { result: 'fail', error: '复核看板与统计均无内容' };
    return { note: (txt || '').slice(0, 200) + ' || stats keys=' + JSON.stringify(stats ? Object.keys(stats).slice(0, 8) : null) };
  }, { page: () => p2, shotName: '复核看板' });

  results.push(await s2.finish());

  /* ══════════ 场景3：复核专家审批 ══════════ */
  const s3 = new L.Scenario('S3', '复核专家审批操作', '复核专家', 'sim_expert');
  const { page: p3 } = await L.newPage(browser, s3);

  await s3.step('登录系统', async () => {
    const url = await L.login(p3, 'sim_expert', L.PW, s3);
    if (url.includes('/login')) { const e = await L.visibleText(p3, '#error', 200); return { result: 'fail', error: '登录失败：' + (e || '') }; }
    await p3.goto(L.BASE + '/', { waitUntil: 'domcontentloaded' });
    await p3.waitForTimeout(2500);
    // ★ 数据准备（同 S2）：S3-05 需要至少 1 条待处理风险才能演示「复核落处置记录」。
    if (PID) {
      const h3 = await ensurePending(p3, PID, 1);
      if (h3.done) console.log('     （数据准备：reopen ' + h3.done + ' 条，待处理 → ' + h3.after + '）');
    }
    const nav = await p3.evaluate(() => {
      const all = Array.from(document.querySelectorAll('.nav-item'));
      const vis = all.filter(n => n.offsetParent !== null).map(n => (n.innerText || '').trim().replace(/\s+/g, ''));
      return { all: all.length, vis };
    });
    return { note: `落点 ${new URL(url).pathname}；导航 DOM ${nav.all} 项，**实际可见 ${nav.vis.length} 项**：${nav.vis.join('/')}` };
  }, { page: () => p3, shotName: '复核专家登录' });

  await s3.step('打开待审批报告', async () => {
    if (!PID) return { result: 'blocked', blocker: '无项目' };
    await p3.goto(L.BASE + '/reports', { waitUntil: 'domcontentloaded' });
    await p3.waitForTimeout(2000);
    const opts = await p3.evaluate(() => {
      const s = document.getElementById('project');
      return s ? Array.from(s.options).map(o => [o.value, o.textContent.trim()]) : [];
    });
    if (!opts.length) return { result: 'fail', error: '报告页项目下拉为空' };
    if (!opts.some(o => o[0] === String(PID))) return { result: 'fail', error: '复核专家看不到该项目，可选=' + JSON.stringify(opts) };
    await p3.selectOption('#project', String(PID));
    await p3.waitForTimeout(3000);
    const list = await p3.evaluate(async (p) => {
      const d = await (await fetch(`/api/v1/reports?project_id=${p}&page_size=5`, { cache: 'no-store' })).json();
      const it = (d.items || [])[0];
      return { total: d.total, first: it ? { doc_no: it.doc_no || it.id, view: it.view, reviewed: it.reviewed } : null };
    }, PID);
    // ★ 记录**可见**页签（2026-10-17 起「生成报告」页签按 report.generate 门控，
    //   复核专家不可见 —— 这本身就是前端门控生效的证据，不应再用全量 DOM 掩盖）
    const tabs = await p3.evaluate(() => {
      const all = Array.from(document.querySelectorAll('.tab'));
      return { all: all.map(t => (t.innerText || '').trim()),
               visible: all.filter(t => t.offsetParent !== null).map(t => (t.innerText || '').trim()) };
    });
    return { note: `页签：DOM ${tabs.all.length} 项 / **可见 ${tabs.visible.length} 项**=[${tabs.visible.join(',')}]；报告 ${list.total} 份，最新=${JSON.stringify(list.first)}` };
  }, { page: () => p3, shotName: '待审批报告' });

  await s3.step('查看风险汇总', async () => {
    await p3.goto(L.BASE + '/risks', { waitUntil: 'domcontentloaded' });
    await p3.waitForTimeout(1600);
    await p3.selectOption('#project', String(PID));
    await p3.waitForTimeout(3000);
    await p3.evaluate(() => { const t = document.getElementById('tab-stats'); if (t) t.click(); });
    await p3.waitForTimeout(3500);
    const pane = await L.visibleText(p3, '#pane-stats', 400);
    if (!pane) return { result: 'fail', error: '风险统计页签为空' };
    return { note: pane.slice(0, 260) };
  }, { page: () => p3, shotName: '风险汇总' });

  await s3.step('查看证据链', async () => {
    await p3.evaluate(() => { const t = document.getElementById('tab-list'); if (t) t.click(); });
    await p3.waitForTimeout(2500);
    const opened = await p3.evaluate(() => {
      const b = document.querySelector('#tb-risks button[data-open]');
      if (!b) return false; b.click(); return true;
    });
    if (!opened) return { result: 'fail', error: '无风险行可打开' };
    // ★ 详情面板为大 DOM（5000+ 字，含明细表/证据链/法规），渲染需轮询等待
    const gw = await L.waitFor(p3, () => {
      const t = (document.querySelector('#d-body,#detail-body') || {}).innerText || '';
      return { ok: t.length > 500 && /证据|条款|依据|原文/.test(t), len: t.length };
    }, { timeout: 40000, interval: 1500 });
    const has = { len: (gw.value || {}).len || 0, links: !!gw.ok };
    if (!has.links) return { result: 'fail', error: '详情内未出现证据链/条款区' };
    return { note: `详情正文 ${has.len} 字，含证据/条款区` };
  }, { page: () => p3, shotName: '证据链' });

  // ★ 裁定（2026-10-17，MQ2-O4）：复核专家**不导出报告**是**刻意设计**（角色描述明写）。
  //   而 `report_service.build_document` 已实现「reviewed 省略 ⇒ 按账套实际处置记录推断，
  //   复核人取处置记录的 updated_by」⇒ 正确链路 = 复核专家处置 → 持 report.generate 的
  //   角色生成报告（**不勾标识**）→ 复核标识与复核人由后端推断。原判据写错了。
  await s3.step('复核风险（落处置记录）', async () => {
    if (!PID) return { result: 'blocked', blocker: '无项目' };
    await p3.goto(L.BASE + '/risks', { waitUntil: 'domcontentloaded' });
    await p3.waitForTimeout(1800);
    await p3.selectOption('#project', String(PID));
    await p3.waitForTimeout(3000);
    // 限「待处理」：已复核条目再次处置会被服务端**正确幂等拒绝**（"本次未产生变更"）
    await p3.evaluate(() => {
      const st = document.getElementById('f-state');
      if (st) { const o = Array.from(st.options).find(x => /待处理|pending/.test(x.textContent) || x.value === 'pending'); if (o) st.value = o.value; }
    });
    await p3.click('#btn-search');
    await p3.waitForTimeout(3200);
    const key = await p3.evaluate(() => {
      const b = document.querySelector('#tb-risks button[data-open]');
      if (!b) return null;
      const k = b.getAttribute('data-open'); b.click(); return k;
    });
    if (!key) return { result: 'fail', error: '无待处理风险可复核' };
    await p3.waitForTimeout(3000);
    const r = await reviewAction(p3, '确认成立', '场景模拟：复核专家确认该条风险成立（供报告标识推断）', PID);
    if (!r.ok) return { result: 'fail', error: '无「确认成立」动作按钮，实际动作=' + (r.acts || []).join(',') };
    if (!/已完成|成功/.test(r.msg || '')) return { result: 'fail', error: '复核动作未生效，页面提示=' + (r.msg || '(空)') };
    // ★ 判据：处置留痕的复核人必须**取自会话**（= 本场景用户 sim_expert，非客户端传入）
    const h = await p3.evaluate(async (a) => {
      const q = await (await fetch(`/api/v1/risks/${encodeURIComponent(a[0])}/history?project_id=${a[1]}`, { cache: 'no-store' })).json();
      return { reviewed: q.reviewed, state_cn: q.state_cn || '', updated_by: q.updated_by || '',
               events: (q.events || []).length };
    }, [key, PID]);
    if (!h.reviewed) return { result: 'fail', error: '处置后 reviewed 仍为假', note: JSON.stringify(h) };
    if (h.updated_by !== 'sim_expert') {
      return { result: 'fail', error: `处置留痕复核人应为会话用户 sim_expert，实际=${h.updated_by || '(空)'}`, note: JSON.stringify(h) };
    }
    return { note: `目标=${String(key).slice(-14)}；动作=${r.act}；提示=${r.msg}；留痕 reviewed=${h.reviewed} 状态=${h.state_cn} 复核人=${h.updated_by}（取自会话）·事件 ${h.events} 条` };
  }, { page: () => p3, shotName: '复核专家处置' });

  await s3.step('确认报告（复核标识由处置记录推断）', async () => {
    if (!PID) return { result: 'blocked', blocker: '无项目' };
    const { page: pa } = await L.newPage(browser, s3);
    const url = await L.login(pa, 'sim_advisor', L.PW, s3);
    if (url.includes('/login')) return { result: 'fail', error: '税务师登录失败' };
    const perm = await pa.evaluate(async () => {
      const d = await (await fetch('/api/auth/me', { cache: 'no-store' })).json();
      return { has: (d.permissions || []).includes('report.generate'), n: (d.permissions || []).length };
    });
    if (!perm.has) return { result: 'fail', error: `税务师应持 report.generate（实际 ${perm.n} 项不含）` };
    await pa.goto(L.BASE + '/reports', { waitUntil: 'domcontentloaded' });
    await pa.waitForTimeout(2200);
    await pa.selectOption('#project', String(PID));
    await pa.waitForTimeout(2500);
    const ui = await pa.evaluate(() => {
      const rv = document.getElementById('f-reviewed');
      const who = document.getElementById('f-reviewer');
      if (who) who.value = '';                 // ★ 复核人**留空** ⇒ 由后端从处置记录推断
      const c = document.querySelector('.vcard[data-view]');
      if (c) c.click();
      return { rvValue: rv ? rv.value : null, options: rv ? Array.from(rv.options).map(o => o.value) : [] };
    });
    // ★ 判据 1：默认必须走「按实际处置记录推断」（空值）—— 否则本用例证明不了推断
    if (ui.rvValue !== '') {
      return { result: 'fail', error: `「人工复核标识」默认值应为空（走推断），实际=${JSON.stringify(ui.rvValue)}`, note: JSON.stringify(ui.options) };
    }
    await pa.waitForTimeout(400);
    await pa.click('#btn-generate');
    const w = await L.waitFor(pa, () => {
      const rc = document.getElementById('result-card');
      return { ok: !!(rc && rc.style.display !== 'none'),
               alert: (document.getElementById('alert') || {}).innerText || '',
               stat: (document.getElementById('gen-status') || {}).innerText || '' };
    }, { timeout: 300000, interval: 2500 });
    const v = w.value || {};
    if (!w.ok) return { result: 'fail', error: `税务师（持 report.generate）生成报告失败：${(v.alert || v.stat || '(空)').slice(0, 140)}` };
    // ★ 判据 2：报告须带**推断出来的**复核标识与复核人
    const rep = await pa.evaluate(async (p) => {
      const list = await (await fetch(`/api/v1/reports?project_id=${p}&page_size=1`, { cache: 'no-store' })).json();
      const it = (list.items || [])[0];
      if (!it) return null;
      const one = await (await fetch(`/api/v1/reports/${encodeURIComponent(it.doc_no || it.id)}`, { cache: 'no-store' })).json();
      return { doc_no: it.doc_no || it.id, reviewed: one.reviewed, reviewed_by: one.reviewed_by || '',
               version: one.version };
    }, PID);
    if (!rep) return { result: 'fail', error: '生成成功但报告列表为空（前后端不一致）' };
    if (rep.reviewed !== true) {
      return { result: 'fail', error: '复核标识未按处置记录推断为真（本用例已先由复核专家处置）', note: JSON.stringify(rep) };
    }
    if (!rep.reviewed_by) {
      return { result: 'fail', error: '复核标识为真但复核人为空（未从处置记录带出）', note: JSON.stringify(rep) };
    }
    // 复核人须是**本账套实际做过处置**的用户（表单该字段留空 ⇒ 必来自处置记录）
    const KNOWN_REVIEWERS = ['sim_expert', 'sim_advisor', 'sim_finance', 'sim_admin'];
    if (!KNOWN_REVIEWERS.includes(rep.reviewed_by)) {
      return { result: 'fail', error: `复核人不在实际处置用户集合内：${rep.reviewed_by}`, note: JSON.stringify(rep) };
    }
    return { note: `报告 ${rep.doc_no}（${rep.version}）：reviewed=${rep.reviewed}，复核人=${rep.reviewed_by}（表单留空 ⇒ **由处置记录推断**）。` +
                   `注：推断取「序遍历中第一条有处置记录的发现」，故本账套多角色均处置过时，复核人可能是先处置者（非缺陷，见裁定 §取证 3）` };
  }, { page: () => p3, shotName: '确认报告（推断复核标识）' });

  await s3.step('签字（复核人落款核验）', async () => {
    const r = await p3.evaluate(async (p) => {
      const list = await (await fetch(`/api/v1/reports?project_id=${p}&page_size=5`, { cache: 'no-store' })).json();
      const it = (list.items || [])[0];
      if (!it) return null;
      const one = await (await fetch(`/api/v1/reports/${encodeURIComponent(it.doc_no || it.id)}`, { cache: 'no-store' })).json();
      return { doc_no: it.doc_no || it.id, reviewed: one.reviewed, reviewed_by: one.reviewed_by, view: one.view,
               keys: Object.keys(one).slice(0, 20) };
    }, PID);
    if (!r) return { result: 'blocked', blocker: '报告列表中无记录可核验签字（前置未产出记录）' };
    if (!r.reviewed) return { result: 'fail', error: '报告 reviewed 标识为假，签字未生效', note: JSON.stringify(r) };
    return { note: `报告 ${r.doc_no}：reviewed=${r.reviewed}，reviewed_by=${r.reviewed_by || '(空)'}，view=${r.view}` };
  }, { page: () => p3, shotName: '签字落款' });

  await s3.step('归档（报告版本台账）', async () => {
    if (!PID) return { result: 'blocked', blocker: '无项目' };
    await p3.goto(L.BASE + '/reports', { waitUntil: 'domcontentloaded' });
    await p3.waitForTimeout(2000);
    await p3.selectOption('#project', String(PID));
    await p3.waitForTimeout(2500);
    await p3.evaluate(() => { const t = document.getElementById('tab-versions'); if (t) t.click(); });
    await p3.waitForTimeout(3500);
    const txt = await L.visibleText(p3, '#pane-versions', 400);
    if (!txt) return { result: 'fail', error: '版本台账页签为空（归档留痕不可见）' };
    return { note: txt.slice(0, 260) };
  }, { page: () => p3, shotName: '归档版本台账' });

  results.push(await s3.finish());

  /* ══════════ 场景4：系统管理员配置 ══════════ */
  const s4 = new L.Scenario('S4', '系统管理员配置操作', '系统管理员', 'sim_admin');
  const { page: p4 } = await L.newPage(browser, s4);
  const newUser = 'sim_created_' + Date.now().toString().slice(-6);

  await s4.step('登录系统', async () => {
    const url = await L.login(p4, 'sim_admin', L.PW, s4);
    if (url.includes('/login')) { const e = await L.visibleText(p4, '#error', 200); return { result: 'fail', error: '登录失败：' + (e || '') }; }
    return { note: `落点 ${new URL(url).pathname}（管理员登录后按设计先进入角色页）` };
  }, { page: () => p4, shotName: '管理员登录' });

  await s4.step('创建用户', async () => {
    await p4.goto(L.BASE + '/users', { waitUntil: 'domcontentloaded' });
    await p4.waitForTimeout(2500);
    // 关闭可能残留的弹层（上一步 /roles 的遮罩会挡住点击）
    await p4.evaluate(() => {
      document.querySelectorAll('.overlay,.mask').forEach(e => {
        e.classList.remove('show'); e.hidden = true;
      });
    });
    await p4.waitForTimeout(300);
    const newOpened = await p4.evaluate(() => {
      const b = document.getElementById('btn-new');
      if (!b) return false;
      b.click();
      const ov = document.getElementById('overlay');
      return !!ov && (ov.classList.contains('show') || !ov.hidden);
    });
    if (!newOpened) return { result: 'fail', error: '「＋ 新建用户」点击后表单未打开' };
    await p4.waitForTimeout(700);
    await p4.fill('#f-username', newUser);
    await p4.fill('#f-display', '模拟·新建财务');
    const pwOk = await p4.evaluate(() => {
      const f = document.getElementById('f-password');
      if (!f) return false;
      f.value = 'SimCreated-2026!'; return true;
    });
    await p4.fill('#f-companies', '1,2');
    // ★ 前端护栏：不选角色会被拒（"请至少选择一个角色"）——这是**正向**防呆，必须按真人操作先勾角色
    const rolePicked = await p4.evaluate(() => {
      const c = document.querySelector('#roles-box input[value="enterprise_finance"]');
      if (!c) return false;
      c.checked = true; return true;
    });
    await p4.click('#btn-save');
    const w = await L.waitFor(p4, async (u) => {
      const r = await fetch('/api/v1/users?q=' + encodeURIComponent(u) + '&page_size=10', { cache: 'no-store' });
      const d = await r.json();
      return { ok: (d.items || []).some(x => x.username === u), n: (d.items || []).length };
    }, { timeout: 25000, interval: 1000, arg: newUser });
    if (!w.ok) {
      const m = await L.visibleText(p4, '#msg', 250);
      return { result: 'fail', error: '新建用户未落库，页面提示=' + (m || '(空)') + `（口令框存在=${pwOk}）` };
    }
    return { note: `用户 ${newUser} 创建成功（口令框=${pwOk}，角色已勾选=${rolePicked}）；护栏：不选角色会被前端拒绝` };
  }, { page: () => p4, shotName: '创建用户' });

  await s4.step('分配角色', async () => {
    const row = await p4.evaluate(async (u) => {
      const d = await (await fetch('/api/v1/users?q=' + encodeURIComponent(u) + '&page_size=10', { cache: 'no-store' })).json();
      const it = (d.items || []).find(x => x.username === u);
      return it ? it.id : null;
    }, newUser);
    if (!row) return { result: 'blocked', blocker: '未找到刚建用户' };
    const opened = await p4.evaluate((id) => {
      const b = document.querySelector(`[data-edit="${id}"]`);
      if (!b) return false; b.click(); return true;
    }, row);
    if (!opened) return { result: 'fail', error: '用户列表无「编辑」按钮（权限未下发或列表未渲染）' };
    await p4.waitForTimeout(1800);
    const picked = await p4.evaluate(() => {
      const c = document.querySelector('#roles-box input[value="enterprise_finance"]');
      if (!c) return null; c.checked = true; return c.value;
    });
    if (!picked) return { result: 'fail', error: '角色复选框未渲染（roles-box 为空）' };
    await p4.click('#btn-save');
    await p4.waitForTimeout(3000);
    const got = await p4.evaluate(async (u) => {
      const d = await (await fetch('/api/v1/users?q=' + encodeURIComponent(u) + '&page_size=10', { cache: 'no-store' })).json();
      const it = (d.items || []).find(x => x.username === u);
      return it ? it.role_codes : null;
    }, newUser);
    if (!got || !got.includes('enterprise_finance')) return { result: 'fail', error: '角色未写入，实际=' + JSON.stringify(got) };
    return { note: `${newUser} 角色=${JSON.stringify(got)}` };
  }, { page: () => p4, shotName: '分配角色' });

  await s4.step('配置权限（角色-权限矩阵 + 新建自定义角色）', async () => {
    await p4.goto(L.BASE + '/roles', { waitUntil: 'domcontentloaded' });
    await p4.waitForTimeout(2500);
    const matrix = await p4.evaluate(() => ({ rows: document.querySelectorAll('#matrix tr').length,
                                              roles: document.querySelectorAll('#tbody tr').length }));
    await p4.click('#btn-new');
    await p4.waitForTimeout(800);
    const code = 'sim_role_' + Date.now().toString().slice(-5);
    await p4.fill('#f-code', code);
    await p4.fill('#f-name', '模拟·只读查看岗');
    await p4.fill('#f-desc', '场景模拟：仅查看权限');
    const np = await p4.evaluate(() => {
      const bs = document.querySelectorAll('#perm-box input[type=checkbox]');
      if (bs[0]) bs[0].checked = true;
      return bs.length;
    });
    await p4.click('#btn-save');
    await p4.waitForTimeout(2500);
    const got = await p4.evaluate(async (c) => {
      const d = await (await fetch('/api/v1/roles', { cache: 'no-store' })).json();
      const arr = Array.isArray(d) ? d : (d.items || d.roles || []);
      return arr.some(x => (x.code || x.role_code) === c);
    }, code);
    if (!got) {
      const m = await L.visibleText(p4, '#msg', 250);
      return { result: 'fail', error: '自定义角色未落库，提示=' + (m || '(空)') + `（权限点 ${np} 个）` };
    }
    return { note: `权限矩阵 ${matrix.rows} 行 / 角色列表 ${matrix.roles} 行；自定义角色 ${code} 创建成功（权限点 ${np} 个）` };
  }, { page: () => p4, shotName: '配置权限' });

  await s4.step('查看审计日志', async () => {
    await p4.goto(L.BASE + '/audit-logs', { waitUntil: 'domcontentloaded' });
    await p4.waitForTimeout(4000);
    const n = await p4.evaluate(() => document.querySelectorAll('table tbody tr').length);
    if (!n || n <= 1) return { result: 'fail', error: '审计日志列表为空' };
    const acts = await p4.evaluate(() => {
      const out = new Set();
      document.querySelectorAll('table tbody tr').forEach(r => {
        const c = r.querySelectorAll('td');
        if (c.length > 2) out.add((c[2].innerText || '').trim());
      });
      return Array.from(out).slice(0, 12);
    });
    const txt = await p4.evaluate(() => document.body.innerText.replace(/\s+/g, ' ').slice(0, 200));
    return { note: `${n} 行；动作样本=${acts.join(',')}；页面=${txt.slice(0, 120)}` };
  }, { page: () => p4, shotName: '审计日志' });

  results.push(await s4.finish());

  fs.writeFileSync(path.join(OUT, '_s234_summary.json'), JSON.stringify(results, null, 1), 'utf-8');
  for (const d of results) console.log(`\n=== ${d.scenario} ${d.conclusion} 步骤${d.step_count} 失败${d.fail_count} 阻断${d.blocked_count}`);
  console.log('\n' + JSON.stringify(L.summary(results)));
  await browser.close();
})().catch(e => { console.error('FATAL', e); process.exit(3); });
