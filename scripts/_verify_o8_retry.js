/** O8 单独验证：`/api/auth/me` 首请求失败 ⇒ 从严隐藏；退避重试成功后 ⇒ **恢复可见**。
 *
 * 探针用 `#nav-users`（index.html 侧栏项，data-perm="user.view"，**除门控外无其他显隐逻辑**）——
 * 不能用 `#btn-del-selected` 一类"本身带 hidden + JS 逻辑"的元素做探针（会混淆归因）。
 */
const L = require('C:/Users/Administrator/WorkBuddy/2026-08-04-21-37-33/caishuixitong/scripts/metaq2_sim/lib.js');
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch();
  const { page } = await L.newPage(browser, null);
  await L.login(page, 'sim_admin', L.PW, null);      // 管理员 ⇒ nav-users 应可见

  const meCalls = [];
  // ★ 失败用**时间窗**控制（`!allow` 一律 500），不用计数 ——
  //   按计数会被 login 阶段提前消耗，导致 rbac-nav 重试耗尽后"放行也不恢复"。
  //   采样点须在重试耗尽之前（退避 400/1600/4600ms）。
  let allow = false;
  await page.route('**/api/auth/me', async (route) => {
    if (!allow) {
      meCalls.push('500(注入)');
      return route.fulfill({ status: 500, contentType: 'application/json', body: '{}' });
    }
    meCalls.push('continue');
    return route.continue();
  });

  await page.goto(L.BASE + '/', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(700);                    // 处于失败窗内
  const vis = () => page.evaluate(() => {
    const el = document.getElementById('nav-users');
    return el ? el.offsetParent !== null : null;
  });
  const during = await vis();

  allow = true;                                      // 放行后续请求（等退避重试打上门）
  // 轮询直到 me 成功且元素恢复（最多 15s）
  let after = null;
  for (let i = 0; i < 30; i += 1) {
    await page.waitForTimeout(500);
    after = await vis();
    if (after === true) break;
  }
  const loaded = await page.evaluate(() => !!(window.RBAC && window.RBAC.state && window.RBAC.state.loaded));
  const isAdmin = await page.evaluate(() => !!(window.RBAC && window.RBAC.isAdmin && window.RBAC.isAdmin()));

  console.log('me 请求序列 :', JSON.stringify(meCalls));
  console.log('失败瞬间 nav-users 可见 :', during, '（期望 false —— fail-closed）');
  console.log('重试后   nav-users 可见 :', after, '（期望 true  —— 自愈）');
  console.log('RBAC.state.loaded :', loaded, '| RBAC.isAdmin() :', isAdmin);
  const ok = during === false && after === true;
  console.log(ok ?'\n✅ O8 通过：失败从严隐藏 → 重试成功恢复' : '\n❌ O8 未通过');
  await browser.close();
  process.exit(ok ? 0 : 1);
})().catch((e) => { console.error('ERR', e.message); process.exit(3); });
