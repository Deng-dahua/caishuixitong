/**
 * 场景4（独立）：系统管理员配置操作（5 步）——角色：系统管理员（sim_admin）
 *
 * 与 s234.js 的差别：本文件**单独跑**，且针对实测暴露的三处可操作性坑做了防御：
 *  ① `#overlay` 用 `classList.add('show')` 控制显隐（不是 `hidden`）——弹层不关会挡住后续点击；
 *  ② 新建用户后**必须等列表真的渲染出该行**再找「编辑」按钮（否则 querySelector 返回 null）；
 *  ③ 跨页面前先关弹层，避免"元素存在但不可点击（30s 超时）"。
 */
const fs = require('fs');
const path = require('path');
const L = require('./lib');

const OUT = 'docs/元质量_20261016/_scenarios';

(async () => {
  const sc = new L.Scenario('S4', '系统管理员配置操作', '系统管理员', 'sim_admin');
  const browser = await L.newBrowser();
  const { page: p4 } = await L.newPage(browser, sc);
  const newUser = 'sim_created_' + Date.now().toString().slice(-6);

  const closeOverlays = () => p4.evaluate(() => {
    document.querySelectorAll('.overlay,.mask').forEach(e => {
      e.classList.remove('show'); e.hidden = true;
    });
  });

  await sc.step('登录系统', async () => {
    const url = await L.login(p4, 'sim_admin', L.PW, sc);
    if (url.includes('/login')) { const e = await L.visibleText(p4, '#error', 200); return { result: 'fail', error: '登录失败：' + (e || '') }; }
    return { note: `落点 ${new URL(url).pathname}（管理员登录后按设计先进入角色页）` };
  }, { page: () => p4, shotName: '管理员登录' });

  await sc.step('打开用户管理（列表默认加载）', async () => {
    await p4.goto(L.BASE + '/users', { waitUntil: 'domcontentloaded' });
    await p4.waitForTimeout(4000);
    const r = await p4.evaluate(() => {
      const t = document.getElementById('f-tenant');
      return { tenant: t ? t.value : null,
               rows: document.querySelectorAll('#tbody tr').length,
               tbody: (document.getElementById('tbody') || {}).innerText || '',
               msg: (document.getElementById('msg') || {}).innerText || '' };
    });
    const loaded = r.rows > 1 && !/加载失败/.test(r.msg);
    if (!loaded) {
      return { result: 'fail',
               error: `用户管理列表未加载：默认组织筛选项值为空（tenant_id=""）⇒ 接口 422；页面提示「${r.msg}」，表格停在「${(r.tbody || '').slice(0, 20)}」`,
               note: `#f-tenant 当前值=${JSON.stringify(r.tenant)}；修复前需手动选择一个组织才能看到用户列表` };
    }
    return { note: `列表加载正常（${r.rows} 行）；组织筛选值=${JSON.stringify(r.tenant)}` };
  }, { page: () => p4, shotName: '用户管理列表' });

  await sc.step('创建用户', async () => {
    await p4.goto(L.BASE + '/users', { waitUntil: 'domcontentloaded' });
    await p4.waitForTimeout(2500);
    await closeOverlays();
    // 绕开"全部组织"的 422：按真人做法先选一个组织，使列表可见
    const picked0 = await p4.evaluate(() => {
      const t = document.getElementById('f-tenant');
      if (!t) return null;
      const o = Array.from(t.options).find(x => x.value);
      if (!o) return null;
      t.value = o.value;
      const b = document.getElementById('btn-search');
      if (b) b.click();
      return o.value;
    });
    await p4.waitForTimeout(2500);
    const listOk = await p4.evaluate(() => document.querySelectorAll('#tbody tr').length);
    if (!listOk) return { result: 'fail', error: `选择组织(${picked0})后列表仍为空`, note: '见上一步的 422 缺陷' };
    const opened = await p4.evaluate(() => {
      const b = document.getElementById('btn-new');
      if (!b) return false;
      b.click();
      const ov = document.getElementById('overlay');
      return !!ov && (ov.classList.contains('show') || !ov.hidden);
    });
    if (!opened) return { result: 'fail', error: '「＋ 新建用户」点击后表单未打开' };
    await p4.waitForTimeout(700);
    await p4.fill('#f-username', newUser);
    await p4.fill('#f-display', '模拟·新建财务');
    const pwOk = await p4.evaluate(() => {
      const f = document.getElementById('f-password');
      if (!f) return false; f.value = 'SimCreated-2026!'; return true;
    });
    // ★ 前端护栏：不选角色会被拒（"请至少选择一个角色"）——正向防呆，按真人操作先勾角色
    const rolePicked = await p4.evaluate(() => {
      const c = document.querySelector('#roles-box input[value="enterprise_finance"]');
      if (!c) return false; c.checked = true; return true;
    });
    await p4.evaluate(() => { const f = document.getElementById('f-companies'); if (f) f.value = '1,2'; });
    await p4.click('#btn-save');
    const w = await L.waitFor(p4, (u) => {
      const tb = document.getElementById('tbody');
      return { ok: !!tb && (tb.innerText || '').includes(u),
               msg: (document.getElementById('msg') || {}).innerText || '' };
    }, { timeout: 30000, interval: 1000, arg: newUser });
    if (!w.ok) {
      return { result: 'fail', error: '新建用户未出现在列表，页面提示=' + ((w.value || {}).msg || '(空)'),
               note: `口令框=${pwOk} 角色勾选=${rolePicked}` };
    }
    return { note: `用户 ${newUser} 创建成功且列表可见（口令框=${pwOk}，角色已勾选=${rolePicked}）；工作绕过：需先选组织（见上一步缺陷）` };
  }, { page: () => p4, shotName: '创建用户' });

  await sc.step('分配角色', async () => {
    const row = await p4.evaluate(async (u) => {
      const d = await (await fetch('/api/v1/users?q=' + encodeURIComponent(u) + '&page_size=10', { cache: 'no-store' })).json();
      const it = (d.items || []).find(x => x.username === u);
      return it ? it.id : null;
    }, newUser);
    if (!row) return { result: 'blocked', blocker: '未找到刚建用户' };
    await closeOverlays();
    const opened = await p4.evaluate((id) => {
      const b = document.querySelector(`[data-edit="${id}"]`);
      if (!b) return false;
      b.click();
      const ov = document.getElementById('overlay');
      return !!ov && (ov.classList.contains('show') || !ov.hidden);
    }, row);
    if (!opened) return { result: 'fail', error: '用户列表未渲染出「编辑」按钮（或点击后表单未打开）' };
    await p4.waitForTimeout(1200);
    const picked = await p4.evaluate(() => {
      const c = document.querySelector('#roles-box input[value="tax_advisor"]');
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
    if (!got || !got.includes('tax_advisor')) return { result: 'fail', error: '角色未写入，实际=' + JSON.stringify(got) };
    return { note: `${newUser} 角色已改为 ${JSON.stringify(got)}（勾选 ${picked}）` };
  }, { page: () => p4, shotName: '分配角色' });

  await sc.step('配置权限（角色-权限矩阵 + 新建自定义角色）', async () => {
    await p4.goto(L.BASE + '/roles', { waitUntil: 'domcontentloaded' });
    await p4.waitForTimeout(2500);
    await closeOverlays();
    const matrix = await p4.evaluate(() => ({ rows: document.querySelectorAll('#matrix tr').length,
                                              roles: document.querySelectorAll('#tbody tr').length }));
    const opened = await p4.evaluate(() => {
      const b = document.getElementById('btn-new');
      if (!b) return false; b.click();
      const ov = document.getElementById('overlay');
      return !!ov && (ov.classList.contains('show') || !ov.hidden);
    });
    if (!opened) return { result: 'fail', error: '「＋ 新建自定义角色」点击后表单未打开' };
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

  await sc.step('查看审计日志', async () => {
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
    const txt = await p4.evaluate(() => document.body.innerText.replace(/\s+/g, ' ').slice(0, 220));
    return { note: `${n} 行；动作样本=${acts.join(',')}；页面=${txt.slice(0, 130)}` };
  }, { page: () => p4, shotName: '审计日志' });

  const d = await sc.finish();
  fs.writeFileSync(path.join(OUT, 'S4.json'), JSON.stringify(d, null, 1), 'utf-8');
  console.log(`\n=== S4 ${d.conclusion} 步骤${d.step_count} 失败${d.fail_count} 阻断${d.blocked_count}`);
  await browser.close();
})().catch(e => { console.error('FATAL', e); process.exit(3); });
