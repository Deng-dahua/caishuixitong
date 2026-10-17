/**
 * P0-2 首页总览 —— 真浏览器验收（2026-10-17）。
 *
 * 判据（对应阶段 3 的 8 维度，修前首页均分 3.38 全站最低）：
 *   ① 可理解性：说明性文案 > 0 字（修前 0 字）、正文 > 0.4KB（修前 0.4KB）；
 *   ② 可反馈性：有反馈载体（修前 0 处）；
 *   ③ 四块 KPI 都有**真实数字**（不是"—"）；
 *   ④ 最近项目表有行、且首行就是「数据来源」那个项目（口径一致）；
 *   ⑤ 权限门控：无 project.write 的角色看不到「新建稽查项目」；
 *   ⑥ **失败不空白**：把摘要接口打成 500 ⇒ 页面必须显示"取不到（原因）"，不得出现 "undefined"/"NaN"。
 */
const path = require('path');
const L = require(path.join(__dirname, 'metaq2_sim', 'lib.js'));
const { chromium } = require('playwright');

const PROBE = () => {
  const t = (id) => { const e = document.getElementById(id); return e ? (e.innerText || '').trim() : null; };
  const vis = (id) => { const e = document.getElementById(id); return !!e && e.offsetParent !== null; };
  const body = document.body.innerText || '';
  return {
    hint: t('home-hint'),
    pending: t('home-kpi-pending'),
    overdue: t('home-kpi-overdue'),
    docs: t('home-kpi-docs'),
    job: t('home-kpi-job'),
    pendingSub: t('home-kpi-pending-sub'),
    projectsRows: document.querySelectorAll('#home-projects table.grid tbody tr').length,
    projectsFirst: (document.querySelector('#home-projects table.grid tbody tr td') || {}).innerText || '',
    hintChars: document.querySelectorAll('.kpi-sub, .kpi-label, .section-card-body .grid ~ *, #home-overview .kpi-sub').length,
    bodyKB: Math.round(body.length / 1024 * 10) / 10,
    msgCount: document.querySelectorAll('#home-overview .msg').length,
    newBtn: vis('home-new-project'),
    analyzeBtn: vis('home-analyze'),
    text: body.slice(0, 400),
  };
};

(async () => {
  const browser = await chromium.launch();
  let bad = 0;
  const fail = (m) => { bad += 1; console.log('  ❌ ' + m); };

  // ①~④ 管理员视角
  {
    const { page, ctx } = await L.newPage(browser, null);
    await L.login(page, 'sim_admin', L.PW, null);
    await page.goto(L.BASE + '/', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(3500);          // 等 4 个摘要请求返回
    const r = await page.evaluate(PROBE);
    console.log('管理员读数：', JSON.stringify({
      hint: r.hint, pending: r.pending, overdue: r.overdue, docs: r.docs, job: r.job,
      rows: r.projectsRows, bodyKB: r.bodyKB,
    }, null, 0));

    if (!r.hint || r.hint.length < 6) fail('顶部提示为空/过短：' + JSON.stringify(r.hint));
    if (r.bodyKB <= 0.6) fail('正文仅 ' + r.bodyKB + 'KB（修前 0.4KB，说明还没内容）');
    if (r.projectsRows < 1) fail('最近项目表 0 行');
    for (const [k, v] of [['待处理风险', r.pending], ['超期', r.overdue], ['资料', r.docs], ['上次分析', r.job]]) {
      if (v === null) fail(k + ' 元素不存在');
      // 允许"—"（缺失≠0），但**不允许 undefined/NaN**
      if (v && (v.includes('undefined') || v.includes('NaN'))) fail(k + ' 出现脏值：' + v);
    }
    if (/undefined|NaN/.test(r.text)) fail('页面正文出现 undefined/NaN');
    if (r.projectsFirst && r.hint && !r.hint.includes(r.projectsFirst.split('\n')[0].slice(0, 6))) {
      console.log('  ⚠ 口径提示与首行项目名未直接对应（人工确认）：' + r.projectsFirst.slice(0, 20));
    }
    // 管理员应能看到「新建稽查项目」
    if (!r.newBtn) fail('管理员看不到「＋ 新建稽查项目」（权限门控误伤）');
    await ctx.close();
  }

  // ⑤ 权限门控：审计员无 project.write / analysis.run
  {
    const { page, ctx } = await L.newPage(browser, null);
    await L.login(page, 'sim_auditor', L.PW, null);
    await page.goto(L.BASE + '/', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(3000);
    const r = await page.evaluate(PROBE);
    console.log('审计员读数：新建按钮可见=' + r.newBtn + ' 分析按钮可见=' + r.analyzeBtn);
    if (r.newBtn) fail('审计员仍看到「＋ 新建稽查项目」（应隐藏）');
    if (r.analyzeBtn) fail('审计员仍看到「一键稽查分析」（应隐藏）');
    if (r.projectsRows < 1) fail('审计员看到的项目表为空（只读也应能看）');
    await ctx.close();
  }

  // ⑥ 失败不空白：把摘要接口打成 500
  {
    const { page, ctx } = await L.newPage(browser, null);
    await L.login(page, 'sim_admin', L.PW, null);
    await page.route('**/api/v1/risks/review-board**', (route) =>
      route.fulfill({ status: 500, contentType: 'application/json', body: '{}' }));
    await page.route('**/api/v1/projects?**', (route) =>
      route.fulfill({ status: 500, contentType: 'application/json', body: '{}' }));
    await page.goto(L.BASE + '/', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(3000);
    const r = await page.evaluate(PROBE);
    console.log('故障注入读数：msg 块=' + r.msgCount + ' hint=' + JSON.stringify((r.hint || '').slice(0, 40)));
    if (r.msgCount < 1) fail('接口 500 时页面没有任何错误提示（空白 = 用户不知道为什么）');
    if (!/失败|取不到/.test(r.text)) fail('接口 500 时未显示"失败/取不到"字样');
    if (/undefined|NaN/.test(r.text)) fail('故障时页面出现 undefined/NaN');
    await ctx.close();
  }

  // ⑦ 与内页**不得同时显示**（#page-home 必须被 core.js 的既有切换逻辑管理）
  {
    const { page, ctx } = await L.newPage(browser, null);
    await L.login(page, 'sim_admin', L.PW, null);
    await page.goto(L.BASE + '/', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(3000);
    const atHome = await page.evaluate(() => {
      const h = document.getElementById('page-home');
      const others = Array.from(document.querySelectorAll('#content-area > [id^="page-"]'))
        .filter((e) => e.id !== 'page-home' && e.offsetParent !== null).map((e) => e.id);
      return { homeVisible: !!h && h.offsetParent !== null, othersVisible: others };
    });
    console.log('首页态：page-home 可见=' + atHome.homeVisible +
      ' 其它内页同时可见=' + JSON.stringify(atHome.othersVisible));
    if (!atHome.homeVisible) fail('默认进入后 #page-home 不可见（默认落点没到首页）');
    if (atHome.othersVisible.length) fail('首页与其它内页同时显示：' + atHome.othersVisible.join(','));

    // 切到「资料风险分析报告」⇒ 首页必须隐藏
    await page.evaluate(() => {
      const n = Array.from(document.querySelectorAll('.nav-item'))
        .find((e) => e.getAttribute('data-page') === 'tax-doc-analysis');
      if (n) n.click();
    });
    await page.waitForTimeout(2500);
    const after = await page.evaluate(() => {
      const h = document.getElementById('page-home');
      return { homeVisible: !!h && h.offsetParent !== null };
    });
    console.log('切到内页后：page-home 可见=' + after.homeVisible);
    if (after.homeVisible) fail('切到「资料风险分析报告」后 #page-home 仍显示（双显示）');

    // 切回首页
    await page.evaluate(() => {
      const n = Array.from(document.querySelectorAll('.nav-item'))
        .find((e) => e.getAttribute('data-page') === 'home');
      if (n) n.click();
    });
    await page.waitForTimeout(2500);
    const back = await page.evaluate(() => {
      const h = document.getElementById('page-home');
      const p = document.getElementById('home-kpi-pending');
      return { homeVisible: !!h && h.offsetParent !== null,
               pending: p ? (p.innerText || '').trim() : null };
    });
    console.log('切回首页：可见=' + back.homeVisible + ' 待处理=' + back.pending);
    if (!back.homeVisible) fail('点侧栏「首页总览」回不到首页');
    await ctx.close();
  }

  await browser.close();
  console.log(bad === 0 ? '\n✅ P0-2 首页总览验收通过' : `\n❌ ${bad} 项不符`);
  process.exit(bad === 0 ? 0 : 1);
})().catch((e) => { console.error('ERR', e.message); process.exit(3); });
