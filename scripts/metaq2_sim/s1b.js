/**
 * S1 续跑：用已完成的作业，只重跑「⑧查看风险清单 → ⑫退出系统」5 步，
 * 再与已记录的 ①–⑦ 合并回 S1.json（避免重复触发 3 分钟全量分析）。
 */
const fs = require('fs');
const path = require('path');
const L = require('./lib');

const OUT = 'docs/元质量_20261016/_scenarios';
const S1 = JSON.parse(fs.readFileSync(path.join(OUT, 'S1.json'), 'utf-8'));
const P = JSON.parse(fs.readFileSync(path.join(OUT, '_s1_project.json'), 'utf-8'));
const J = JSON.parse(fs.readFileSync(path.join(OUT, '_s1_job.json'), 'utf-8'));
const PID = P.pid;

(async () => {
  const sc = new L.Scenario('S1', '企业财务完整操作', '企业财务', 'sim_finance');
  sc.n = 7;                       // 与既有 ①–⑦ 对齐编号
  const browser = await L.newBrowser();
  const { page } = await L.newPage(browser, sc);
  let docNo = null;
  await L.login(page, 'sim_finance', L.PW, sc);

  await sc.step('查看风险清单', async () => {
    await page.goto(L.BASE + '/risks', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(1500);
    await page.selectOption('#project', String(PID));
    await page.waitForTimeout(4000);
    const kpi = await L.visibleText(page, '#kpi-box', 300);
    const tbl = await L.visibleText(page, '#tb-risks', 500);
    const n = await page.evaluate(() => document.querySelectorAll('#tb-risks tr').length);
    if (!tbl || n === 0) return { result: 'fail', error: '风险清单表为空', note: 'kpi=' + (kpi || '(空)') };
    const st = await page.evaluate(async (p) => {
      const d = await (await fetch(`/api/v1/projects/${p}/risks?page_size=5`, { cache: 'no-store' })).json();
      return { total: d.total, available: d.available };
    }, PID);
    return { note: `KPI=${(kpi || '').slice(0, 120)}；表格 ${n} 行；接口 total=${st.total} available=${st.available}；首行=${(tbl || '').slice(0, 110)}` };
  }, { page: () => page, shotName: '风险清单' });

  await sc.step('查看风险详情', async () => {
    const opened = await page.evaluate(() => {
      const b = document.querySelector('#tb-risks button[data-open]');
      if (!b) return { ok: false };
      b.click();
      return { ok: true, key: b.getAttribute('data-open') };
    });
    if (!opened.ok) return { result: 'fail', error: '列表无「详情/复核」按钮' };
    await page.waitForTimeout(4000);
    const body = await page.evaluate(() => {
      const el = document.querySelector('#d-body,#detail-body,.drawer,.modal.wide');
      return el ? (el.innerText || '').replace(/\s+/g, ' ').slice(0, 600) : '';
    });
    const acts = await page.evaluate(() => Array.from(document.querySelectorAll('#d-actions button')).map(b => b.innerText.trim()));
    if (!body) return { result: 'fail', error: '详情面板无内容' };
    return { note: `条目 ${opened.key}；详情 ${body.length} 字；复核动作=[${acts.join('/')}]；正文=${body.slice(0, 240)}` };
  }, { page: () => page, shotName: '风险详情' });

  await sc.step('生成风险分析报告', async () => {
    await page.goto(L.BASE + '/reports', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(1800);
    await page.selectOption('#project', String(PID));
    await page.waitForTimeout(2500);
    const t0 = Date.now();
    await page.click('#btn-generate');
    const w = await L.waitFor(page, () => {
      const rc = document.getElementById('result-card');
      const vis = rc && rc.style.display !== 'none';
      return { ok: !!vis, stat: (document.getElementById('gen-status') || {}).innerText || '' };
    }, { timeout: 600000, interval: 3000 });
    const ms = Date.now() - t0;
    if (!w.ok) { const al = await L.visibleText(page, '#alert', 300); return { result: 'fail', error: '报告未生成，提示=' + (al || (w.value || {}).stat || '(空)') }; }
    const txt = await L.visibleText(page, '#result-body', 500);
    docNo = await page.evaluate(() => { const b = document.querySelector('[data-dl]'); return b ? b.getAttribute('data-dl') : null; });
    return { note: `耗时 ${(ms / 1000).toFixed(1)}s；文档号=${docNo}；结果区=${(txt || '').slice(0, 180)}` };
  }, { page: () => page, shotName: '报告生成' });

  await sc.step('导出 PDF', async () => {
    if (!docNo) return { result: 'blocked', blocker: '无报告文档号' };
    const [dl] = await Promise.all([
      page.waitForEvent('download', { timeout: 300000 }).catch(() => null),
      page.evaluate(() => { const b = document.querySelector('[data-dl]'); if (b) b.click(); }),
    ]);
    if (!dl) return { result: 'fail', error: '点击下载未触发下载事件' };
    const out = path.join(OUT, 'S1_导出_' + dl.suggestedFilename());
    await dl.saveAs(out);
    const size = fs.statSync(out).size;
    const head = fs.readFileSync(out).slice(0, 4).toString('latin1');
    if (head !== '%PDF') return { result: 'fail', error: '导出文件非 PDF（魔数=' + JSON.stringify(head) + '）' };
    return { note: `下载 ${path.basename(out)}，${(size / 1024).toFixed(0)} KB，魔数 %PDF 通过` };
  }, { page: () => page, shotName: '导出PDF' });

  await sc.step('退出系统', async () => {
    const ok = await page.evaluate(async () => (await fetch('/api/auth/logout', { method: 'POST' })).ok);
    await page.waitForTimeout(800);
    await page.goto(L.BASE + '/projects', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(1500);
    const url = page.url();
    if (!url.includes('/login')) return { result: 'fail', error: '退出后仍可访问受保护页，当前=' + url };
    return { note: `退出 ok=${ok}；再访问 /projects 被重定向至 ${url}` };
  }, { page: () => page, shotName: '退出系统' });

  // 合并：①–⑦ 取原记录，⑧–⑫ 取本次
  const merged = S1.steps.slice(0, 7).concat(sc.steps);
  const data = {
    ...S1, steps: merged, shots: S1.shots.concat(sc.shots),
    console_errors: S1.console_errors.concat(sc.consoleErrors),
    page_errors: S1.page_errors.concat(sc.pageErrors),
    step_count: merged.length,
    fail_count: merged.filter(s => s.result === 'fail').length,
    blocked_count: merged.filter(s => s.result === 'blocked').length,
    blockers: merged.filter(s => s.blocker).map(s => ({ sid: s.sid, name: s.name, blocker: s.blocker })),
    total_ms: merged.reduce((a, s) => a + s.ms, 0),
    conclusion: merged.some(s => s.result === 'fail') ? 'fail' : (merged.some(s => s.result === 'blocked') ? 'blocked' : 'success'),
  };
  fs.writeFileSync(path.join(OUT, 'S1.json'), JSON.stringify(data, null, 1), 'utf-8');
  console.log(`\n=== S1(合并) ${data.conclusion} 步骤${data.step_count} 失败${data.fail_count} 阻断${data.blocked_count}`);
  merged.forEach(s => console.log(`  ${s.sid} ${s.result} ${s.name} ${s.ms}ms ${(s.note || s.error || '').slice(0, 80)}`));
  await browser.close();
})().catch(e => { console.error('FATAL', e); process.exit(3); });
