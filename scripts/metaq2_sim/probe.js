/** DOM 探测：确认登录落点、账套选择、各页可用性（只读，不写业务数据）。 */
const L = require('./lib');
const { chromium } = require('playwright');

(async () => {
  const b = await chromium.launch();
  const { page } = await L.newPage(b, null);
  const dump = async (label) => {
    const info = await page.evaluate(() => ({
      url: location.pathname,
      title: document.title,
      h1: (document.querySelector('h1,h2') || {}).innerText || '',
      msg: (document.querySelector('#msg,#alert,#error') || {}).innerText || '',
      who: (document.querySelector('#whoami,#who') || {}).innerText || '',
      has: Object.fromEntries(['#q', '#btn-new', '#tbody', '#picker', '#btn-start',
        '#project', '#btn-generate', '#lnav'].map(s => [s, !!document.querySelector(s)])),
      optProj: (() => { const e = document.querySelector('#project,#f-project,#proj');
        return e ? Array.from(e.options).slice(0, 4).map(o => o.textContent.trim()) : null; })(),
      bodyLen: (document.body.innerText || '').length,
    }));
    console.log(`\n== ${label} ==`);
    console.log(JSON.stringify(info, null, 1));
  };

  console.log('login:', await L.login(page, 'sim_finance', L.PW, null));
  await dump('after-login');
  const sel = await L.ensureCompany(page, '元质量模拟测试有限公司');
  console.log('ensureCompany ->', sel);
  await dump('after-company');

  for (const p of ['/projects', '/documents', '/extract', '/analysis', '/risks', '/reports']) {
    await page.goto(L.BASE + p, { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(2500);
    await dump(p);
  }
  await b.close();
})().catch(e => { console.error('ERR', e); process.exit(3); });
