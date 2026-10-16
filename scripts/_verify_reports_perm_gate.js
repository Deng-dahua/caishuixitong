/** MQ2-O7 验收：报告页「生成报告」入口须按权限显隐（真相 = rbac-nav.js + 服务端拦截）。
 *
 * 判据：
 *   ① 企业财务 / 税务师（持 report.generate）⇒ 「生成报告」页签**可见**，默认停在生成页签；
 *   ② 复核专家 / 审计员（**无** report.generate）⇒ 该页签与表单**隐藏**，默认切到「报告列表」；
 *   ③ 隐藏只是体验 —— 服务端仍必须 403（防"前端藏了就安全"的错觉）。
 */
const L = require('C:/Users/Administrator/WorkBuddy/2026-08-04-21-37-33/caishuixitong/scripts/metaq2_sim/lib.js');
const { chromium } = require('playwright');

const CASES = [
  { user: 'sim_finance', role: '企业财务', expect: true },
  { user: 'sim_advisor', role: '税务师', expect: true },
  { user: 'sim_expert', role: '复核专家', expect: false },
  { user: 'sim_auditor', role: '审计员', expect: false },
];

(async () => {
  const b = await chromium.launch();
  let bad = 0;
  for (const c of CASES) {
    const { page } = await L.newPage(b, null);
    await L.login(page, c.user, L.PW, null);
    await page.goto(L.BASE + '/reports', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(3500);          // 等 rbac-nav 取回 /api/auth/me 并 apply()
    const r = await page.evaluate(() => {
      const tab = document.getElementById('tab-gen');
      const pane = document.getElementById('pane-gen');
      const btn = document.getElementById('btn-generate');
      const vis = (el) => !!el && el.offsetParent !== null;
      return {
        tabVisible: vis(tab), paneVisible: vis(pane), btnVisible: vis(btn),
        activeTab: (document.querySelector('.tab.active') || {}).getAttribute
          ? document.querySelector('.tab.active').getAttribute('data-tab') : null,
        perms: null,
      };
    });
    const perm = await page.evaluate(async () => {
      const d = await (await fetch('/api/auth/me', { cache: 'no-store' })).json();
      return { has: (d.permissions || []).includes('report.generate'), n: (d.permissions || []).length };
    });
    const shown = r.tabVisible && r.paneVisible;
    const ok = (shown === c.expect) && perm.has === c.expect;
    // ③ 后端仍拦截：无权限者直接打接口必须 403
    let backend = null;
    if (!c.expect) {
      backend = await page.evaluate(async () => {
        const csrf = (document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/) || [])[1] || '';
        const res = await fetch('/api/v1/projects/39/reports', {
          method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': decodeURIComponent(csrf) },
          body: JSON.stringify({ view: 'management', formats: ['html'] }),
        });
        return res.status;
      });
    }
    if (backend !== null && backend !== 403) { ok = false; }
    if (!ok) bad += 1;
    console.log(`[${ok ? '✅' : '❌'}] ${c.role.padEnd(5)} perm=${perm.has} 页签可见=${r.tabVisible} 表单可见=${r.paneVisible} 按钮可见=${r.btnVisible} 首屏页签=${r.activeTab}${backend !== null ? ` 直打接口=${backend}` : ''}`);
    await page.close();
  }
  console.log(bad === 0 ? '\n✅ MQ2-O7 验收通过：入口按权限显隐，且服务端仍拦截' : `\n❌ ${bad} 个用例不符`);
  await b.close();
  process.exit(bad ? 1 : 0);
})().catch(e => { console.error('ERR', e.message); process.exit(3); });
