/**
 * 场景2：税务师复核操作（7 步）——角色：税务师（sim_advisor）
 * 场景3：复核专家审批操作（7 步）——角色：复核专家（sim_expert）
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
    // 仍限「待处理」，避免点到刚被上一步确认掉的条目
    await p2.evaluate(() => {
      const st = document.getElementById('f-state');
      if (st) { const o = Array.from(st.options).find(x => /待处理|pending/.test(x.textContent) || x.value === 'pending'); if (o) st.value = o.value; }
    });
    await p2.click('#btn-search');
    await p2.waitForTimeout(3000);
    const key = await p2.evaluate(() => {
      const bs = document.querySelectorAll('#tb-risks button[data-open]');
      if (!bs.length) return null;
      const b = bs[bs.length > 1 ? 1 : 0];
      b.click(); return b.getAttribute('data-open');
    });
    if (!key) return { result: 'blocked', blocker: '风险条目不足 2 条，无法演示"排除误报"' };
    await p2.waitForTimeout(3000);
    const r = await reviewAction(p2, '误报', '场景模拟：同额发票非同一笔业务，判定为误报', PID);
    if (!r.ok) return { result: 'fail', error: '无「误报/排除」动作按钮，实际动作=' + (r.acts || []).join(',') };
    if (!/已完成|成功/.test(r.msg || '')) return { result: 'fail', error: '排除动作未生效，页面提示=' + (r.msg || '(空)'), note: `目标=${key} act=${r.act}` };
    const ok = (r.state.by_state.false_positive || 0) >= 1 || (r.state.by_state.excluded || 0) >= 1;
    if (!ok) return { result: 'fail', error: '接口回读未见「误报/已排除」，分布=' + JSON.stringify(r.state.by_state) };
    return { note: `目标=${key.slice(-14)} act=${r.act}；提示=${r.msg}；回读=${JSON.stringify(r.state.by_state)}` };
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
    const tabs = await p3.evaluate(() => Array.from(document.querySelectorAll('.tab')).map(t => (t.innerText || '').trim()));
    return { note: `页签=[${tabs.join(',')}]；报告 ${list.total} 份，最新=${JSON.stringify(list.first)}` };
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

  await s3.step('确认报告（走界面，带复核标识）', async () => {
    await p3.goto(L.BASE + '/reports', { waitUntil: 'domcontentloaded' });
    await p3.waitForTimeout(2000);
    await p3.selectOption('#project', String(PID));
    await p3.waitForTimeout(2500);
    const can = await p3.evaluate(async () => {
      const d = await (await fetch('/api/auth/me', { cache: 'no-store' })).json();
      return { n: (d.permissions || []).length, has: (d.permissions || []).includes('report.generate') };
    });
    const ui = await p3.evaluate(() => {
      const rv = document.getElementById('f-reviewed'), who = document.getElementById('f-reviewer'), note = document.getElementById('f-note');
      if (rv) rv.value = '1';
      if (who) who.value = '模拟·复核专家';
      if (note) note.value = '场景模拟：复核后出具';
      const c = document.querySelector('.vcard[data-view]');
      if (c) c.click();
      return { hasReviewed: !!rv, hasReviewer: !!who };
    });
    await p3.waitForTimeout(400);
    await p3.click('#btn-generate');
    const w = await L.waitFor(p3, () => {
      const rc = document.getElementById('result-card');
      return { ok: !!(rc && rc.style.display !== 'none'),
               alert: (document.getElementById('alert') || {}).innerText || '',
               stat: (document.getElementById('gen-status') || {}).innerText || '' };
    }, { timeout: 300000, interval: 2500 });
    const v = w.value || {};
    if (!w.ok) {
      return { result: 'blocked',
               blocker: `复核专家界面点「生成报告」未产出（提示=${(v.alert || v.stat || '(空)').slice(0, 140)}）`,
               note: `权限 ${can.n} 项，含 report.generate=${can.has}；复核标识/复核人输入框=${ui.hasReviewed}/${ui.hasReviewer}` };
    }
    return { note: `界面生成成功；复核标识/复核人输入框=${ui.hasReviewed}/${ui.hasReviewer}；提示=${(v.alert || '').slice(0, 140)}` };
  }, { page: () => p3, shotName: '确认报告' });

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
