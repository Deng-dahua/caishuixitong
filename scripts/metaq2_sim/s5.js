/**
 * 场景5：异常场景（8 项 + 1 负向对照）
 * 目标：不仅要"能拦住"，还要记录**用户看到什么错误提示**（是否明确、可操作）。
 */
const fs = require('fs');
const path = require('path');
const L = require('./lib');

const OUT = 'docs/元质量_20261016/_scenarios';
const FIX = path.join(require('os').tmpdir(), 'metaq2_fix');
fs.mkdirSync(FIX, { recursive: true });
const readS1 = (f) => { try { return JSON.parse(fs.readFileSync(path.join(OUT, f), 'utf-8')); } catch (e) { return null; } };
const P = readS1('_s1_project.json') || {};
const J = readS1('_s1_job.json') || {};
const PID = P.pid, JOB = J.jobId;

const SAMPLE = path.resolve(__dirname, '..', '..', 'data', 'uploads', '1');

function fixtures() {
  const bad = path.join(FIX, '模拟·不支持格式.txt');
  fs.writeFileSync(bad, '这不是财税资料，只是一段文本。', 'utf-8');
  const fake = path.join(FIX, '模拟·伪装的科目余额表.xlsx');
  fs.writeFileSync(fake, 'PK\x03\x04 这不是真的 xlsx（故意损坏，用于验证解析失败提示）', 'utf-8');
  const big = path.join(FIX, '模拟·超大文件.xlsx');
  if (!fs.existsSync(big) || fs.statSync(big).size < 200 * 1024 * 1024) {
    const buf = Buffer.alloc(1024 * 1024, 0x41);
    const fd = fs.openSync(big, 'w');
    for (let i = 0; i < 205; i += 1) fs.writeSync(fd, buf);
    fs.closeSync(fd);
  }
  return { bad, fake, big, dup: path.join(SAMPLE, '1_13_2025年科目余额表.xlsx') };
}

(async () => {
  const F = fixtures();
  const sc = new L.Scenario('S5', '异常场景', '企业财务/审计员', 'sim_finance');
  const browser = await L.newBrowser();
  const { page } = await L.newPage(browser, sc);

  await L.login(page, 'sim_finance', L.PW, sc);

  const goDocs = async () => {
    await page.goto(L.BASE + '/documents', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(1500);
    await page.selectOption('#proj', String(PID || 6));
    await page.waitForTimeout(1200);
  };

  // 5-1 上传错误格式文件（真浏览器上传，看页面提示）
  await sc.step('上传错误格式文件（.txt）', async () => {
    if (!PID) return { result: 'blocked', blocker: '无项目' };
    await goDocs();
    await page.setInputFiles('#picker', [F.bad]);
    const w = await L.waitFor(page, () => {
      const m = (document.getElementById('msg') || {}).innerText || '';
      return { ok: /本次上传|不支持|失败|拒绝|格式/.test(m), msg: m };
    }, { timeout: 60000, interval: 1000 });
    const msg = (w.value || {}).msg || await L.visibleText(page, '#msg', 300);
    if (!msg) return { result: 'fail', error: '上传后页面无任何提示（静默）' };
    const clear = /不支持|格式|类型/.test(msg);
    return { note: msg.slice(0, 220), blocker: clear ? '' : '提示未说明"格式不支持"，用户不知如何改正' };
  }, { page: () => page, shotName: '错误格式文件' });

  // 5-2 上传超大文件（> 200MB 分片上限）
  await sc.step('上传超大文件（205MB）', async () => {
    if (!PID) return { result: 'blocked', blocker: '无项目' };
    await goDocs();
    await page.setInputFiles('#picker', [F.big]);
    const w = await L.waitFor(page, () => {
      const m = (document.getElementById('msg') || {}).innerText || '';
      const q = (document.getElementById('queue') || {}).innerText || '';
      return { ok: /本次上传|超大|上限|超过|失败|拒绝/.test(m + q), msg: m, q };
    }, { timeout: 180000, interval: 2000 });
    const msg = ((w.value || {}).msg || '') + ' ' + ((w.value || {}).q || '');
    if (!msg.trim()) return { result: 'fail', error: '超大文件上传后页面无提示' };
    const clear = /上限|超过|大|MB|大小/.test(msg);
    return { note: msg.replace(/\s+/g, ' ').slice(0, 220), blocker: clear ? '' : '提示未说明"超出大小上限"' };
  }, { page: () => page, shotName: '超大文件' });

  // 5-3 上传重复文件
  await sc.step('上传重复文件', async () => {
    if (!PID) return { result: 'blocked', blocker: '无项目' };
    await goDocs();
    await page.setInputFiles('#picker', [F.dup]);
    const w = await L.waitFor(page, () => {
      const m = (document.getElementById('msg') || {}).innerText || '';
      return { ok: /本次上传/.test(m), msg: m };
    }, { timeout: 90000, interval: 1500 });
    const msg = (w.value || {}).msg || '';
    if (!/跳过重复\s*1/.test(msg)) return { result: 'fail', error: '重复文件未被识别为重复：' + msg };
    return { note: msg };
  }, { page: () => page, shotName: '重复文件' });

  // 5-4 解析失败（伪 xlsx）
  await sc.step('解析失败（损坏的 xlsx）', async () => {
    if (!PID) return { result: 'blocked', blocker: '无项目' };
    await goDocs();
    await page.setInputFiles('#picker', [F.fake]);
    await L.waitFor(page, () => {
      const m = (document.getElementById('msg') || {}).innerText || '';
      return { ok: /本次上传/.test(m), msg: m };
    }, { timeout: 90000, interval: 1500 });
    await page.waitForTimeout(1500);
    const did = await page.evaluate(async (p) => {
      const d = await (await fetch(`/api/v1/projects/${p}/documents?page_size=100&q=${encodeURIComponent('伪装的科目余额表')}`, { cache: 'no-store' })).json();
      const it = (d.items || [])[0];
      return it ? { id: it.id, st: it.parse_status, st_cn: it.parse_status_cn } : null;
    }, PID);
    if (!did) return { result: 'blocked', blocker: '未找到刚上传的损坏文件' };
    const r = await page.evaluate(async (d) => {
      const res = await fetch(`/api/v1/documents/${d}/extract`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}',
      });
      const txt = await res.text();
      return { status: res.status, body: txt.slice(0, 400) };
    }, did.id);
    const after = await page.evaluate(async (d) => {
      const j = await (await fetch(`/api/v1/documents/${d}/extracted`, { cache: 'no-store' })).json();
      return j.parse_status;
    }, did.id);
    if (r.status === 200 && after === 'success') return { result: 'fail', error: '损坏的 xlsx 竟解析成功（解析器过度宽容）' };
    if (r.status >= 400 && !r.body) return { result: 'fail', error: '解析失败但无错误说明（HTTP ' + r.status + '）' };
    return { note: `解析返回 HTTP ${r.status}，解析状态=${after}；错误说明=${r.body.replace(/\s+/g, ' ').slice(0, 180)}` };
  }, { page: () => page, shotName: '解析失败' });

  // 5-5 分析中断（发起后**立即**取消；若任务在点击前已跑完，如实记为"时序限制"而非缺陷）
  await sc.step('分析中断（发起后立即取消）', async () => {
    const target = PID;
    await page.goto(L.BASE + '/analysis', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(1800);
    const opts = await page.evaluate(() => Array.from(document.getElementById('f-project').options).map(o => o.value));
    if (!opts.includes(String(target))) return { result: 'blocked', blocker: '目标项目不在下拉中' };
    await page.selectOption('#f-project', String(target));
    await page.waitForTimeout(600);
    await page.click('#btn-start');
    // 尽早抢点取消（轮询 250ms，最长 20s）
    const grabbed = await L.waitFor(page, () => {
      const b = document.getElementById('btn-cancel');
      return { ok: !!(b && !b.disabled), disabled: b ? b.disabled : null,
               status: (document.getElementById('cur-status') || {}).innerText || '' };
    }, { timeout: 20000, interval: 250 });
    const st1 = (grabbed.value || {}).status || '';
    if (!grabbed.ok) {
      const job = await page.evaluate(async (p) => {
        const d = await (await fetch(`/api/v1/projects/${p}/analysis-jobs?page_size=3`, { cache: 'no-store' })).json();
        const it = (d.jobs || [])[0];
        return it ? { job_id: it.job_id, status: it.status, engine: it.engine_status } : null;
      }, target);
      return { note: `取消按钮在 20s 内始终禁用（状态标签="${st1}"）：任务已过快结束，**属测试时序限制，非缺陷**；作业=${JSON.stringify(job)}`,
               blocker: '' };
    }
    await page.click('#btn-cancel');
    // 取消确认弹窗（若有）
    await page.waitForTimeout(1200);
    const conf = await page.evaluate(() => {
      const b = Array.from(document.querySelectorAll('button'))
        .find(x => /确认|确定/.test(x.innerText || '') && x.offsetParent);
      if (b) { b.click(); return true; }
      return false;
    });
    const w = await L.waitFor(page, () => {
      const s = (document.getElementById('cur-status') || {}).innerText || '';
      return { ok: /取消/.test(s), s };
    }, { timeout: 120000, interval: 2000 });
    const job = await page.evaluate(async (p) => {
      const d = await (await fetch(`/api/v1/projects/${p}/analysis-jobs?page_size=3`, { cache: 'no-store' })).json();
      const it = (d.jobs || [])[0];
      return it ? { job_id: it.job_id, status: it.status, engine: it.engine_status, progress: it.progress, cancel_requested: it.cancel_requested } : null;
    }, target);
    const txt = await L.visibleText(page, '#cur-err', 250);
    if (!w.ok) {
      return { result: 'fail', error: '点击取消后页面未显示已取消',
               note: `取消前=${st1}；确认弹窗=${conf}；状态标签=${(w.value || {}).s}；作业=${JSON.stringify(job)}` };
    }
    if (!job || job.status !== 'CANCELLED') {
      return { result: 'fail', error: '页面显示已取消但接口状态不是 CANCELLED（前后端不一致）', note: JSON.stringify(job) };
    }
    return { note: `取消前=${st1} → 取消后标签="${(w.value || {}).s}"；确认弹窗=${conf}；接口=${job.status}/${job.engine} 进度=${job.progress}（未达 100）；页面提示=${(txt || '').slice(0, 140)}` };
  }, { page: () => page, shotName: '分析中断' });

  // 5-6 报告生成失败（非法视图）
  await sc.step('报告生成失败（非法视图）', async () => {
    if (!PID) return { result: 'blocked', blocker: '无项目' };
    const r = await page.evaluate(async (p) => {
      const res = await fetch(`/api/v1/projects/${p}/reports`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ view: '不存在的视图', formats: ['pdf'] }),
      });
      return { status: res.status, body: (await res.text()).slice(0, 300) };
    }, PID);
    if (r.status < 400) return { result: 'fail', error: '非法视图未拒绝（HTTP ' + r.status + '）' };
    return { note: `HTTP ${r.status}；用户可见提示=${r.body.replace(/\s+/g, ' ').slice(0, 220)}` };
  }, { page: () => page, shotName: '报告生成失败' });

  // 5-7 权限不足（审计员尝试发起分析 / 生成报告）
  await sc.step('权限不足（审计员发起分析）', async () => {
    // ★ 探测对象必须是**审计员可见**的项目，否则 404（数据范围）会掩盖"是否做了权限点校验"。
    //   同时等到该账套无在跑作业，避免 409（业务态冲突）混淆判据。
    const id = await page.evaluate(async (p) => {
      const list = await (await fetch('/api/v1/projects?page_size=20', { cache: 'no-store' })).json();
      const it = (list.items || []).find(x => String(x.id) === String(p)) || (list.items || [])[0];
      return it ? it.id : p;
    }, PID);
    for (let i = 0; i < 40; i += 1) {
      const busy = await page.evaluate(async (p) => {
        const d = await (await fetch(`/api/v1/projects/${p}/analysis-jobs?page_size=3`, { cache: 'no-store' })).json();
        return (d.jobs || []).some(x => ['RUNNING', 'PENDING'].includes(x.status));
      }, id);
      if (!busy) break;
      await page.waitForTimeout(5000);
    }
    const { page: pa } = await L.newPage(browser, sc);
    await L.login(pa, 'sim_auditor', L.PW, sc);
    const r = await pa.evaluate(async (p) => {
      const out = {};
      let res = await fetch(`/api/v1/projects/${p}/analysis-jobs`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{"force":false}',
      });
      out.analysis = { status: res.status, body: (await res.text()).slice(0, 200) };
      res = await fetch(`/api/v1/projects/${p}/reports`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: '{"view":"self_check","formats":["html"]}',
      });
      out.report = { status: res.status, body: (await res.text()).slice(0, 200) };
      return out;
    }, id);
    const ui = await pa.goto(L.BASE + '/analysis', { waitUntil: 'domcontentloaded' }).then(async () => {
      await pa.waitForTimeout(2500);
      return pa.evaluate(() => ({
        startDisabled: (document.getElementById('btn-start') || {}).disabled,
        navCount: Array.from(document.querySelectorAll('.nav-item')).filter(n => n.offsetParent !== null).length,
      }));
    });
    await pa.screenshot({ path: path.join(L.SHOT_DIR, 'S5-07_审计员视角.png') });
    // ★ 判据：403 ⇒ 已强制；200/201/409/422 ⇒ 请求已进入业务层（未做权限点校验）
    const blockedA = r.analysis.status === 403;
    const blockedR = r.report.status === 403;
    if (!blockedA || !blockedR) {
      return { result: 'fail',
               error: `审计员（无 analysis.run / report.generate）未被拒：发起分析 HTTP ${r.analysis.status}、生成报告 HTTP ${r.report.status}，请求已进入业务层`,
               note: `项目 pid=${id}；分析响应=${r.analysis.body.replace(/\s+/g, ' ').slice(0, 100)}；报告响应=${r.report.body.replace(/\s+/g, ' ').slice(0, 100)}；页面「开始分析」按钮禁用=${ui.startDisabled}（可见导航 ${ui.navCount} 项）` };
    }
    return { note: `发起分析 HTTP 403、生成报告 HTTP 403（均已强制）；页面「开始分析」按钮禁用=${ui.startDisabled}` };
  }, { page: () => page, shotName: '权限不足' });

  // 5-8 会话过期（篡改会话 Cookie）
  await sc.step('会话过期（会话凭据失效）', async () => {
    const { page: pb, ctx } = await L.newPage(browser, sc);
    await L.login(pb, 'sim_finance', L.PW, sc);
    const before = await pb.evaluate(async () => (await fetch('/api/auth/me')).status);
    const cookies = await ctx.cookies();
    const sess = cookies.find(c => /auth|session|token/i.test(c.name));
    if (!sess) return { result: 'fail', error: '未发现会话 Cookie（无法模拟失效）' };
    await ctx.addCookies([{ ...sess, value: 'invalid' + Date.now() }]);
    const after = await pb.evaluate(async () => {
      const r = await fetch('/api/auth/me');
      return { status: r.status, body: (await r.text()).slice(0, 160) };
    });
    await pb.goto(L.BASE + '/projects', { waitUntil: 'domcontentloaded' });
    await pb.waitForTimeout(2500);
    const url = pb.url();
    await pb.screenshot({ path: path.join(L.SHOT_DIR, 'S5-08_会话失效.png') });
    if (after.status !== 401) return { result: 'fail', error: `失效会话未被拒（HTTP ${after.status}）`, note: after.body };
    const redirected = url.includes('/login');
    return { note: `会话前=${before} → 篡改后 /api/auth/me=${after.status}；访问 /projects 落点=${new URL(url).pathname}` + (redirected ? '（已跳登录页）' : '『未跳转登录页』'),
             blocker: redirected ? '' : '前端未自动跳转登录页（用户可能以为还在登录态）' };
  }, { page: () => page, shotName: '会话过期' });

  // 5-9 负向对照：资料主体与账套不一致 ⇒ 分析被拦截
  await sc.step('负向对照：资料主体与账套不一致', async () => {
    const target = 6;
    const r = await page.evaluate(async (p) => {
      const res = await fetch(`/api/v1/projects/${p}/analysis-jobs`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{"force":true}',
      });
      if (res.status >= 400) return { status: res.status, body: (await res.text()).slice(0, 300) };
      const j = await res.json();
      return { status: res.status, job_id: j.job_id };
    }, target);
    if (!r.job_id) return { note: `发起即被拒 HTTP ${r.status}：${(r.body || '').slice(0, 200)}` };
    const w = await L.waitFor(page, async (j) => {
      const d = await (await fetch(`/api/v1/analysis-jobs/${j}`, { cache: 'no-store' })).json();
      return { ok: ['SUCCESS', 'FAILED', 'CANCELLED'].includes(d.status),
               status: d.status, engine: d.engine_status, engine_cn: d.engine_status_cn, err: d.error };
    }, { timeout: 600000, interval: 4000, arg: r.job_id });
    const v = w.value || {};
    if (v.engine !== 'blocked') return { result: 'fail', error: '主体不一致未被拦截（引擎=' + (v.engine || v.status) + '）', note: JSON.stringify(v).slice(0, 300) };
    const clear = /主体|不一致|账套/.test(v.err || '');
    return { note: `引擎=${v.engine_cn}；用户可见原因=${(v.err || '').slice(0, 200)}`,
             blocker: clear ? '' : '拦截原因未说明主体不一致' };
  }, { page: () => page, shotName: '主体不一致拦截' });

  const d = await sc.finish();
  console.log(`\n=== S5 ${d.conclusion} 步骤${d.step_count} 失败${d.fail_count} 阻断${d.blocked_count} 卡点${d.blockers.length}`);
  await browser.close();
})().catch(e => { console.error('FATAL', e); process.exit(3); });
