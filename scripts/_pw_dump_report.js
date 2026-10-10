// 用真实 Chromium 打开本系统前端，导出「报告区」的真实渲染结果（文本 + HTML）。
// 目的：前端到底渲染成什么样，必须以**浏览器实际输出**为准（不靠推断）。
// 依赖：playwright-core + 已安装的 ms-playwright/chromium。
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright-core');

const CHROME = process.env.LOCALAPPDATA +
  '\\ms-playwright\\chromium-1243\\chrome-win64\\chrome.exe';
const BASE = 'http://127.0.0.1:8001';
const USER = process.env.PW_USER || '';
const PW = process.env.PW_PASS || '';
const OUT = process.argv[2] || 'C:/tmp/frontend_dump';

(async () => {
  const browser = await chromium.launch({
    executablePath: CHROME, headless: true,
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--ignore-certificate-errors'],
  });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await ctx.newPage();

  const consoleMsgs = [], pageErrors = [], failedReqs = [];
  page.on('console', m => consoleMsgs.push(`[${m.type()}] ${m.text()}`));
  page.on('pageerror', e => pageErrors.push(String(e && e.message || e)));
  page.on('requestfailed', r => failedReqs.push(`${r.method()} ${r.url()} :: ${r.failure() && r.failure().errorText}`));

  // ── 1) 登录（走页面表单，保证 UA/指纹一致）──
  await page.goto(BASE + '/login', { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.fill('#username', USER);
  await page.fill('#password', PW);
  await page.click('#submit');
  await page.waitForLoadState('domcontentloaded', { timeout: 60000 }).catch(() => {});
  await page.waitForTimeout(2500);
  console.log('[login] URL =', page.url());

  // ── 2) 选账套（若被重定向）──
  if (page.url().includes('select-company')) {
    const csrf = (await ctx.cookies()).find(c => c.name === 'csrf_token');
    const resp = await ctx.request.post(BASE + '/api/auth/select-company', {
      data: { company_id: 1 },
      headers: csrf ? { 'X-CSRF-Token': csrf.value } : {},
    });
    console.log('[select-company] HTTP', resp.status(), (await resp.text()).slice(0, 200));
    await page.goto(BASE + '/', { waitUntil: 'domcontentloaded', timeout: 60000 });
    await page.waitForTimeout(2000);
  }

  // ── 3) 打开「资料风险分析报告」页 ──
  await page.waitForSelector('[data-page="tax-doc-analysis"]', { timeout: 60000 });
  await page.click('[data-page="tax-doc-analysis"]');
  // 等报告区出现且有内容（后端恢复渲染）
  await page.waitForFunction(() => {
    const el = document.getElementById('tda-report-area');
    return el && el.innerHTML && el.innerHTML.length > 200;
  }, { timeout: 120000 }).catch(() => {});
  await page.waitForTimeout(4000);

  // ── 4) 采集现场事实 ──
  const probe = await page.evaluate(() => {
    const el = document.getElementById('tda-report-area');
    const r = window.__wbLastReport || null;
    const er = (r && r.enterprise_readable_report) || null;
    const dm = (er && er.document_meta) || null;
    const txt = el ? el.innerText : '';
    const heads = el ? Array.from(el.querySelectorAll('h1,h2,h3'))
      .map(h => (h.textContent || '').replace(/\s+/g, ' ').trim()).filter(Boolean) : [];
    return {
      hasReportArea: !!el,
      areaLen: el ? el.innerHTML.length : 0,
      textLen: txt.length,
      heads: heads.slice(0, 40),
      hasErr: /ReferenceError|is not defined|无法渲染|加载失败|分析异常/.test(txt),
      isEnt: (typeof window._isEnterpriseEdition === 'function' && r) ? window._isEnterpriseEdition(r) : 'n/a',
      docName: (typeof window._reportDocName === 'function' && r) ? window._reportDocName(r) : 'n/a',
      erPresent: !!er,
      metaName: dm && dm.name,
      overallLevel: r && r.overall_level,
      totalRisks: r && r.total_risks,
      fbBanner: /报告版式回退说明/.test(txt),
      sevenChap: /您的权利|签字页|附件证据清单/.test(txt),
      html: el ? el.innerHTML : '',
      text: txt.slice(0, 12000),
    };
  });

  fs.mkdirSync(OUT, { recursive: true });
  fs.writeFileSync(path.join(OUT, 'report_area.html'), probe.html || '', 'utf8');
  fs.writeFileSync(path.join(OUT, 'report_text.txt'), probe.text || '', 'utf8');
  await page.screenshot({ path: path.join(OUT, 'page.png'), fullPage: false });

  console.log('===== 现场事实 =====');
  for (const k of ['hasReportArea', 'areaLen', 'textLen', 'isEnt', 'docName', 'erPresent',
                   'metaName', 'overallLevel', 'totalRisks', 'fbBanner', 'sevenChap', 'hasErr']) {
    console.log(`  ${k} = ${JSON.stringify(probe[k])}`);
  }
  console.log('  章节标题:', JSON.stringify(probe.heads, null, 0));
  console.log('===== pageerror =====');
  pageErrors.slice(0, 10).forEach(e => console.log('  !', e.slice(0, 300)));
  console.log('===== console(error/warn) =====');
  consoleMsgs.filter(m => /error|warn|ReferenceError|not defined/i.test(m)).slice(0, 15)
    .forEach(m => console.log('  ', m.slice(0, 300)));
  console.log('===== 请求失败 =====');
  failedReqs.slice(0, 10).forEach(m => console.log('  ', m.slice(0, 200)));
  console.log('===== 报告区文本（前 3500 字）=====');
  console.log((probe.text || '').slice(0, 3500));
  await browser.close();
})().catch(e => { console.error('FATAL', e); process.exit(1); });
