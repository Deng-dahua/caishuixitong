/**
 * 前端权限门控 —— 真浏览器实测（A 项验收，2026-10-17）。
 *
 * 判据（与后端 `perm_matrix.js` 同思路：**声明 vs 实际**）：
 *   ① 先用**管理员**访问每页，记录每个受控入口的"基线可见性"（管理员持全部权限）；
 *   ② 再逐角色访问，对**基线可见**的入口断言：实际可见 === rbac.json 声明持有该权限；
 *   ③ `data-perm-admin` 入口：可见 === 该角色 is_admin；
 *   ④ 单独验证 O8：首请求 `/api/auth/me` 失败 ⇒ 先隐藏；重试成功后**恢复可见**。
 *
 * 运行：NODE_PATH=<工作区 node_modules> node scripts/_verify_frontend_perm_gate.js
 */
const fs = require('fs');
const path = require('path');
const L = require(path.join(__dirname, 'metaq2_sim', 'lib.js'));
const { chromium } = require('playwright');

const ROOT = path.join(__dirname, '..');
const CFG = JSON.parse(fs.readFileSync(path.join(ROOT, 'config', 'frontend_perms.json'), 'utf-8'));
const RBAC = JSON.parse(fs.readFileSync(path.join(ROOT, 'config', 'rbac.json'), 'utf-8'));

const ROLES = {
  system_admin: 'sim_admin',
  enterprise_finance: 'sim_finance',
  tax_advisor: 'sim_advisor',
  review_expert: 'sim_expert',
  auditor: 'sim_auditor',
};

/** 文件名 → 实际访问路径（名称不一致者必须显式登记，避免"测了个不存在的页面"）。 */
const ROUTE = {
  'index.html': '/',
  'documents.html': '/documents',
  'extract.html': '/extract',
  'analysis.html': '/analysis',
  'risks.html': '/risks',
  'projects.html': '/projects',
  'reports.html': '/reports',
  'rule_versions.html': '/rule-versions',
  'templates.html': '/report-templates',
  'users.html': '/users',
  'roles.html': '/roles',
  'audit_logs.html': '/audit-logs',
  'new-company.html': '/new-company',
  'select-company.html': '/select-company',
};

function declaredPublic(role, perm) {
  const rows = RBAC.role_permissions[role] || [];
  return rows.includes('*') || rows.includes(perm);
}

/** 元素是否"真的能被用户看到"（含 display:none / 祖先隐藏 / hidden 属性）。 */
async function visibility(page, ids) {
  return page.evaluate((list) => {
    const out = {};
    for (const id of list) {
      const el = document.getElementById(id);
      out[id] = !!el && el.offsetParent !== null;
    }
    return out;
  }, ids);
}

(async () => {
  const browser = await chromium.launch();
  const pages = Object.keys(CFG.pages);
  // 自检：表里每个页面都必须有明确路由（否则会"测了个不存在的页面"）
  const noRoute = pages.filter((p) => !ROUTE[p]);
  if (noRoute.length) { console.error('缺路由映射:', noRoute); process.exit(3); }

  // ① 管理员基线
  const base = {};
  {
    const { page, ctx } = await L.newPage(browser, null);
    await L.login(page, ROLES.system_admin, L.PW, null);
    for (const pg of pages) {
      await page.goto(L.BASE + (ROUTE[pg] || '/' + pg.replace(/\.html$/, '')), { waitUntil: 'domcontentloaded' });
      await page.waitForTimeout(2200);
      const ids = CFG.pages[pg].map((e) => e.id);
      base[pg] = await visibility(page, ids);
    }
    await ctx.close();
  }

  // ② 逐角色比对
  let checked = 0, bad = 0, skipped = 0;
  const failures = [];
  for (const [role, user] of Object.entries(ROLES)) {
    const { page, ctx } = await L.newPage(browser, null);
    await L.login(page, user, L.PW, null);
    const isAdmin = (await page.evaluate(async () => {
      const d = await (await fetch('/api/auth/me', { cache: 'no-store' })).json();
      return !!d.is_admin;
    }));
    for (const pg of pages) {
      await page.goto(L.BASE + (ROUTE[pg] || '/' + pg.replace(/\.html$/, '')), { waitUntil: 'domcontentloaded' });
      await page.waitForTimeout(1800);
      const ids = CFG.pages[pg].map((e) => e.id);
      const got = await visibility(page, ids);
      for (const e of CFG.pages[pg]) {
        if (!base[pg][e.id]) { skipped += 1; continue; }   // 管理员都看不到 ⇒ 该入口本身隐藏（如 #picker）
        const expect = e.admin ? isAdmin : declaredPublic(role, e.perm);
        checked += 1;
        if (got[e.id] !== expect) {
          bad += 1;
          failures.push(`${role} ${pg} #${e.id}: 声明可见=${expect} 实际=${got[e.id]}（${e.perm || 'admin-only'}）`);
        }
      }
    }
    await ctx.close();
  }

  console.log(`=== 逐角色比对：检查 ${checked} 项，不符 ${bad}，跳过 ${skipped}（管理员基线不可见）===`);
  failures.slice(0, 20).forEach((f) => console.log('  ❌ ' + f));

  // ④ O8：失败 ⇒ 隐藏；放行后重试成功 ⇒ 恢复
  //    ★ 探针用 `#nav-users`（只受门控控制）；不用 `#btn-del-selected`（自带 hidden + JS 显隐，混淆归因）。
  //    ★ 失败用**时间窗**控制（`!allow` ⇒ 一律 500），**不用计数**：按计数会让
  //      `L.login` 阶段提前消耗掉失败次数，导致 rbac-nav 的 3 次重试全部命中 500 后**耗尽**，
  //      于是"放行后永不恢复"（实测踩过）。采样点也要在重试耗尽之前（退避 400/1600/4600ms）。
  let o8 = '未知';
  {
    const { page, ctx } = await L.newPage(browser, null);
    await L.login(page, ROLES.system_admin, L.PW, null);
    let allow = false;
    const meCalls = [];
    await page.route('**/api/auth/me', async (route) => {
      if (!allow) {
        meCalls.push('500(注入)');
        return route.fulfill({ status: 500, contentType: 'application/json', body: '{}' });
      }
      meCalls.push('continue');
      return route.continue();
    });
    await page.goto(L.BASE + '/', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(700);            // 处于失败窗内（第 2 次重试在 ~400ms，第 3 次在 ~1600ms）
    const during = (await visibility(page, ['nav-users']))['nav-users'];
    allow = true;                              // 放行后续请求
    let after = null;
    for (let i = 0; i < 30; i += 1) {
      await page.waitForTimeout(500);
      after = (await visibility(page, ['nav-users']))['nav-users'];
      if (after === true) break;
    }
    o8 = (during === false && after === true)
      ? '✅ 通过（失败时隐藏 → 重试成功后恢复）'
      : `❌ 未通过（失败时=${during}，重试后=${after}；me=${meCalls.length} 次）`;
    console.log(`=== O8 重试/自愈：${o8} ===`);
    await ctx.close();
  }

  await browser.close();
  const ok = bad === 0 && o8.startsWith('✅');
  console.log(ok ? '\n✅ 前端门控实测通过（声明与实际一致，O8 自愈有效）'
                 : '\n❌ 存在不一致，需修');
  process.exit(ok ? 0 : 1);
})().catch((e) => { console.error('ERR', e.message); process.exit(3); });
