/**
 * 场景1：企业财务完整操作（12 步）——真浏览器逐步执行。
 * 角色：企业财务（sim_finance）
 */
const fs = require('fs');
const path = require('path');
const L = require('./lib');

const ROOT = path.resolve(__dirname, '..', '..');
const SAMPLE = path.join(ROOT, 'data', 'uploads', '1');
const FILES = [
  '1_13_2025年科目余额表.xlsx',
  '1_14_2025年序时账.xlsx',
  '1_1_增值税及附加税费申报表_一般纳税人适用_2025-01-01-2025-01-31_.pdf',
  '1_6_增值税及附加税费申报表_一般纳税人适用_2025-06-01-2025-06-30_.pdf',
  '1_12_增值税及附加税费申报表_一般纳税人适用_2025-12-01-2025-12-31_.pdf',
  '1_15_AI账务系统202501工资薪金所得.xls',
  '1_20_AI账务系统202506工资薪金所得.xls',
  '1_26_AI账务系统202512工资薪金所得.xls',
  '1_91_AI账务系统银行1.xlsx',
  '1_96_AI账务系统银行6.xlsx',
  '1_102_AI账务系统银行12.xlsx',
].filter(f => fs.existsSync(path.join(SAMPLE, f)));

const PID_FILE = path.join(__dirname, '..', '..', 'docs', '元质量_20261016', '_scenarios', '_s1_project.json');

(async () => {
  const sc = new L.Scenario('S1', '企业财务完整操作', '企业财务', 'sim_finance');
  const browser = await L.newBrowser();
  const { page } = await L.newPage(browser, sc);
  const projName = '元质量模拟·2025年度自查';
  // ★ 主体一致性：样例资料归属「深圳海更数字传媒有限公司」（本仓库指定样例
  //   WB-TRISK-SAMPLE-001），故项目必须落在**同一主体**的账套下，否则会被
  //   主体一致性闸门正确拦截（第一轮实测已复现，见报告"负向对照"）。
  const SAMPLE_USCC = '91440300MA5H824G7M';
  let pid = null, jobId = null, docNo = null;

  // ① 登录系统
  await sc.step('登录系统', async () => {
    const url = await L.login(page, 'sim_finance', L.PW, sc);
    if (url.includes('/login')) {
      const err = await L.visibleText(page, '#error', 200);
      return { result: 'fail', error: '登录未通过，页面错误=' + (err || '(空)') };
    }
    const who = await L.visibleText(page, '#sidebar-user-name', 60);
    sc.next = { url };
    return { note: `落点 ${new URL(url).pathname}，侧栏用户名=${who}` };
  }, { page: () => page, shotName: '登录后主页' });

  // ② 创建稽查项目
  await sc.step('创建稽查项目', async () => {
    await page.goto(L.BASE + '/projects', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(1500);
    const before = await page.evaluate(() => document.querySelectorAll('#tbody tr').length);
    await page.click('#btn-new');
    await page.waitForTimeout(300);
    await page.fill('#f-name', projName);
    await page.fill('#f-tid', SAMPLE_USCC);
    await page.click('#btn-save');
    // ★ 判据：保存必须**收尾**（弹窗关闭）或**给出错误**；不能只凭"列表出现同名串"（旧项目名含同串会假通过）
    const w = await L.waitFor(page, () => {
      const open = !document.getElementById('m-form').hidden;
      const fm = (document.getElementById('form-msg') || {}).innerText || '';
      return { ok: !open || !!fm.trim(), open, fm };
    }, { timeout: 30000, interval: 500 });
    const v = w.value || {};
    if (v.open) {
      return { result: 'fail', error: '保存后弹窗未关闭，表单提示=' + (v.fm || '(空)') };
    }
    const r = await page.evaluate(async (nm) => {
      const res = await fetch('/api/v1/projects?page_size=200', { cache: 'no-store' });
      const d = await res.json();
      const it = (d.items || []).filter(x => x.name === nm).sort((a, b) => b.id - a.id)[0];
      return it ? { id: it.id, status: it.status, status_cn: it.status_cn, code: it.code,
                    company_id: it.company_id } : null;
    }, projName);
    if (!r) return { result: 'fail', error: '保存已收尾但项目未落库（名称=' + projName + '）' };
    pid = r.id;
    fs.mkdirSync(path.dirname(PID_FILE), { recursive: true });
    fs.writeFileSync(PID_FILE, JSON.stringify({ pid, name: projName }), 'utf-8');
    const after = await page.evaluate(() => document.querySelectorAll('#tbody tr').length);
    return { note: `id=${pid} 编号=${r.code} 状态=${r.status_cn}；company_id=${r.company_id === null ? 'NULL（懒绑定，上传/分析时回填）' : r.company_id}；列表 ${before}→${after} 行` };
  }, { page: () => page, shotName: '项目创建成功' });

  // ③ 上传财税资料
  await sc.step('上传财税资料', async () => {
    if (!pid) return { result: 'blocked', blocker: '项目未创建成功，无法上传' };
    await page.goto(L.BASE + '/documents', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(1800);
    await page.selectOption('#proj', String(pid));
    await page.waitForTimeout(1200);
    await page.setInputFiles('#picker', FILES.map(f => path.join(SAMPLE, f)));
    const up = await L.waitFor(page, () => {
      const m = (document.getElementById('msg') || {}).innerText || '';
      if (m.includes('本次上传')) return { ok: true, msg: m };
      return { ok: false, msg: m };
    }, { timeout: 180000, interval: 1500 });
    const msg = up.value && up.value.msg ? up.value.msg : await L.visibleText(page, '#msg', 300);
    const cnt = await L.visibleText(page, '#count', 80);
    if (!up.ok) return { result: 'fail', error: '未出现上传完成提示，当前提示=' + (msg || '(空)') };
    return { note: `${FILES.length} 份 → ${msg}；${cnt || ''}` };
  }, { page: () => page, shotName: '资料上传完成' });

  // ④ 等待解析完成
  await sc.step('等待解析完成', async () => {
    if (!pid) return { result: 'blocked', blocker: '无项目' };
    const w = await L.waitFor(page, async (p) => {
      const r = await fetch(`/api/v1/projects/${p}/documents?page_size=100`, { cache: 'no-store' });
      const d = await r.json();
      const items = d.items || [];
      const parsing = items.filter(x => x.parse_status === 'parsing' || x.parse_status === 'pending');
      return { ok: items.length > 0 && parsing.length === 0, total: items.length,
               parsing: parsing.length,
               counts: d.status_counts || {} };
    }, { timeout: 420000, interval: 4000, arg: pid });
    const v = w.value || {};
    if (!w.ok) return { result: 'fail', error: '解析超时未收敛', note: JSON.stringify(v) };
    const bad = (v.counts && v.counts.failed) || 0;
    return { note: `${v.total} 份解析收敛（状态计数 ${JSON.stringify(v.counts)}）` + (bad ? `，其中失败 ${bad} 份` : '') };
  }, { page: () => page, shotName: '解析完成' });

  // ⑤ 查看解析结果，人工校正错误
  await sc.step('查看解析结果并人工校正', async () => {
    if (!pid) return { result: 'blocked', blocker: '无项目' };
    await page.goto(L.BASE + '/extract', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(1500);
    await page.selectOption('#proj', String(pid));
    await page.waitForTimeout(1200);
    const docId = await page.evaluate(() => {
      const s = document.getElementById('doc');
      const o = Array.from(s.options).find(x => x.value);
      return o ? o.value : null;
    });
    if (!docId) return { result: 'fail', error: '解析页资料下拉为空（上传的 11 份资料未进入解析清单）' };
    await page.selectOption('#doc', String(docId));
    await page.waitForTimeout(500);
    await page.click('#btn-parse');
    const w = await L.waitFor(page, async (d) => {
      const r = await fetch(`/api/v1/documents/${d}/extracted`, { cache: 'no-store' });
      if (!r.ok) return { ok: false, code: r.status };
      const j = await r.json();
      const f = j.fields || [];
      return { ok: f.length > 0, n: f.length, tables: (j.tables || []).length };
    }, { timeout: 180000, interval: 3000, arg: docId });
    const v = w.value || {};
    await page.reload({ waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(1500);
    await page.selectOption('#proj', String(pid));
    await page.waitForTimeout(1200);
    await page.selectOption('#doc', String(docId));
    await page.waitForTimeout(2500);
    // 人工校正：改第一个可编辑字段并保存（按 value_text 校验真落库）
    const picked = await page.evaluate(() => {
      const inp = document.querySelector('input[data-fid]');
      if (!inp) return null;
      const fid = inp.getAttribute('data-fid');
      const old = inp.value;
      const target = /^-?\d+(\.\d+)?$/.test(old.trim()) ? '188888.88' : '场景模拟校正值';
      inp.value = target;
      const btn = document.querySelector(`button[data-save="${fid}"]`);
      if (!btn) return { fid, old, target, noBtn: true };
      btn.click();
      return { fid, old, target };
    });
    if (!picked) return { result: 'fail', error: '无可校正输入框（字段表为空）', note: `解析出字段 ${v.n || 0}` };
    if (picked.noBtn) return { result: 'fail', error: '无对应保存按钮' };
    await page.waitForTimeout(2800);
    const r = await page.evaluate(async (fid) => {
      const res = await fetch(`/api/v1/documents/${document.getElementById('doc').value}/extracted`, { cache: 'no-store' });
      const j = await res.json();
      const f = (j.fields || []).find(x => String(x.id) === String(fid));
      return f ? { corrected: Number(f.corrected) === 1, value_text: f.value_text,
                   original: f.original_value, by: f.corrected_by } : null;
    }, picked.fid);
    if (!r || !r.corrected) {
      return { result: 'fail', error: '校正已提交但未落库（corrected 未置位）',
               note: `原值=${picked.old} 提交值=${picked.target}` };
    }
    if (String(r.value_text) !== String(picked.target)) {
      return { result: 'fail', error: `校正后 value_text 未变为提交值：${r.value_text} ≠ ${picked.target}`,
               note: `original=${r.original} by=${r.by}` };
    }
    return { note: `解析字段 ${v.n} 个；校正 id=${picked.fid} ${r.original} → ${r.value_text}（corrected=1, by=${r.by}）` };
  }, { page: () => page, shotName: '解析与人工校正' });

  // ⑥ 点击「开始稽查分析」
  await sc.step('点击开始稽查分析', async () => {
    if (!pid) return { result: 'blocked', blocker: '无项目' };
    await page.goto(L.BASE + '/analysis', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(1800);
    await page.selectOption('#f-project', String(pid));
    await page.waitForTimeout(1000);
    await page.click('#btn-start');
    // 页面回执（真·用户视角）：#cur-id 显示「作业号 xxx」
    const w = await L.waitFor(page, () => {
      const t = (document.getElementById('cur-id') || {}).innerText || '';
      return { ok: /作业号\s*\S+/.test(t), raw: t };
    }, { timeout: 40000, interval: 800 });
    const al = await L.visibleText(page, '#alert', 300);
    jobId = await page.evaluate(async (p) => {
      const r = await fetch(`/api/v1/projects/${p}/analysis-jobs?page_size=5`, { cache: 'no-store' });
      const d = await r.json();
      const it = (d.jobs || d.items || [])[0];
      return it ? it.job_id : null;
    }, pid);
    fs.writeFileSync(path.join(path.dirname(PID_FILE), '_s1_job.json'),
                     JSON.stringify({ pid, jobId }), 'utf-8');
    if (!jobId) {
      return { result: 'fail', error: '点击后未产生作业记录', note: `页面回执=${w.value.raw}；提示=${al || '(空)'}` };
    }
    if (!w.ok) {
      return { result: 'fail', error: '作业已创建但页面未显示作业号（用户看不到任务）',
               note: `页面 #cur-id="${w.value.raw}"，实际 job_id=${jobId}，提示=${al || '(空)'}` };
    }
    return { note: `页面回执"${w.value.raw}"；job_id=${jobId}；提示=${(al || '').slice(0, 120)}` };
  }, { page: () => page, shotName: '发起分析' });

  // ⑦ 等待分析完成
  await sc.step('等待分析完成', async () => {
    if (!jobId) return { result: 'blocked', blocker: '未取得任务号' };
    const w = await L.waitFor(page, async (j) => {
      const r = await fetch(`/api/v1/analysis-jobs/${j}`, { cache: 'no-store' });
      const d = await r.json();
      const steps = d.steps || [];
      return { ok: ['SUCCESS', 'FAILED', 'CANCELLED'].includes(d.status),
               status: d.status, engine: d.engine_status, engine_cn: d.engine_status_cn,
               error: d.error, progress: d.progress,
               done: steps.filter(s => ['done', 'success', 'ok'].includes(String(s.status))).length,
               steps: steps.length, findings: d.findings_count, level: d.overall_level };
    }, { timeout: 900000, interval: 5000, arg: jobId });
    const v = w.value || {};
    if (v.status !== 'SUCCESS') {
      return { result: 'fail', error: `任务终态=${v.status}（引擎=${v.engine_cn || v.engine}）`,
               note: `进度 ${v.progress}，${v.done}/${v.steps} 步；错误=${(v.error || '(空)').slice(0, 200)}` };
    }
    // 页面也要真的显示"完成"（用户视角）
    await page.click('button[onclick="refreshCurrent()"]').catch(() => {});
    await page.waitForTimeout(2500);
    const shown = await L.visibleText(page, '#cur-status', 60);
    const stepsTxt = await L.visibleText(page, '#step-list', 400);
    return { note: `终态 SUCCESS，进度 ${v.progress}，${v.done}/${v.steps} 步；发现 ${v.findings} 条、总体 ${v.level}；页面状态标签="${shown}"；步骤区=${(stepsTxt || '').slice(0, 120)}` };
  }, { page: () => page, shotName: '分析完成' });

  // ⑧ 查看风险清单
  await sc.step('查看风险清单', async () => {
    if (!pid) return { result: 'blocked', blocker: '无项目' };
    await page.goto(L.BASE + '/risks', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(1500);
    await page.selectOption('#project', String(pid));
    await page.waitForTimeout(3500);
    const kpi = await L.visibleText(page, '#kpi-box', 300);
    const tbl = await L.visibleText(page, '#tb-risks', 400);
    const n = await page.evaluate(() => document.querySelectorAll('#tb-risks tr').length);
    if (!tbl) return { result: 'fail', error: '风险清单区为空', note: 'kpi=' + (kpi || '(空)') };
    return { note: `KPI=${kpi}；列表 ${n} 行，首行=${tbl.slice(0, 120)}` };
  }, { page: () => page, shotName: '风险清单' });

  // ⑨ 查看风险详情
  await sc.step('查看风险详情', async () => {
    const opened = await page.evaluate(() => {
      const b = document.querySelector('#tb-risks button[data-open]');
      if (!b) return { ok: false };
      b.click();
      return { ok: true, key: b.getAttribute('data-open') };
    });
    if (!opened.ok) return { result: 'fail', error: '列表无「详情/复核」按钮' };
    await page.waitForTimeout(3500);
    const body = await page.evaluate(() => {
      const el = document.querySelector('#d-body,#detail-body,.drawer,.modal.wide');
      return el ? (el.innerText || '').replace(/\s+/g, ' ').slice(0, 500) : '';
    });
    if (!body) return { result: 'fail', error: '详情面板无内容' };
    return { note: body.slice(0, 260) };
  }, { page: () => page, shotName: '风险详情', fullPage: false });

  // ⑩ 生成风险分析报告
  await sc.step('生成风险分析报告', async () => {
    if (!pid) return { result: 'blocked', blocker: '无项目' };
    await page.goto(L.BASE + '/reports', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(1800);
    await page.selectOption('#project', String(pid));
    await page.waitForTimeout(2500);
    const view = await page.evaluate(() => {
      const c = document.querySelector('.vcard[data-view]');
      if (c) c.click();
      return c ? c.getAttribute('data-view') : null;
    });
    await page.waitForTimeout(500);
    const t0 = Date.now();
    await page.click('#btn-generate');
    const w = await L.waitFor(page, () => {
      const rc = document.getElementById('result-card');
      const vis = rc && rc.style.display !== 'none';
      const stat = (document.getElementById('gen-status') || {}).innerText || '';
      return { ok: !!vis, stat };
    }, { timeout: 600000, interval: 3000 });
    const ms = Date.now() - t0;
    sc.reportMs = ms;
    if (!w.ok) {
      const al = await L.visibleText(page, '#alert', 300);
      return { result: 'fail', error: '报告未生成，提示=' + (al || (w.value || {}).stat || '(空)'), note: `耗时 ${(ms / 1000).toFixed(1)}s` };
    }
    const txt = await L.visibleText(page, '#result-body', 500);
    docNo = await page.evaluate(() => {
      const b = document.querySelector('[data-dl]');
      return b ? b.getAttribute('data-dl') : null;
    });
    return { note: `视图=${view || 'full'} 耗时 ${(ms / 1000).toFixed(1)}s；文档号=${docNo}；结果区=${(txt || '').slice(0, 160)}` };
  }, { page: () => page, shotName: '报告生成' });

  // ⑪ 导出 PDF
  await sc.step('导出 PDF', async () => {
    if (!docNo) return { result: 'blocked', blocker: '无报告文档号' };
    const [dl] = await Promise.all([
      page.waitForEvent('download', { timeout: 300000 }).catch(() => null),
      page.evaluate(() => { const b = document.querySelector('[data-dl]'); if (b) b.click(); }),
    ]);
    if (!dl) return { result: 'fail', error: '点击下载未触发浏览器下载事件' };
    const out = path.join(__dirname, '..', '..', 'docs', '元质量_20261016', '_scenarios',
                          'S1_导出_' + dl.suggestedFilename());
    await dl.saveAs(out);
    const size = fs.statSync(out).size;
    const head = fs.readFileSync(out).slice(0, 4).toString('latin1');
    if (head !== '%PDF') return { result: 'fail', error: '导出文件非 PDF（魔数=' + JSON.stringify(head) + '）' };
    return { note: `下载文件 ${path.basename(out)}，${(size / 1024).toFixed(0)} KB，魔数 %PDF 校验通过` };
  }, { page: () => page, shotName: '导出PDF' });

  // ⑫ 退出系统
  await sc.step('退出系统', async () => {
    const ok = await page.evaluate(async () => {
      const r = await fetch('/api/auth/logout', { method: 'POST' });
      return r.ok;
    });
    await page.waitForTimeout(800);
    await page.goto(L.BASE + '/projects', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(1500);
    const url = page.url();
    if (!url.includes('/login')) return { result: 'fail', error: '退出后仍可访问受保护页（未拦截到登录页），当前=' + url };
    return { note: `退出接口 ok=${ok}；再访问 /projects 被重定向至 ${url}` };
  }, { page: () => page, shotName: '退出系统' });

  const data = await sc.finish();
  console.log('\n=== S1 结论:', data.conclusion,
              `| 步骤 ${data.step_count} 失败 ${data.fail_count} 阻断 ${data.blocked_count} 卡点 ${data.blockers.length}`);
  await browser.close();
})().catch(e => { console.error('FATAL', e); process.exit(3); });
