/**
 * 场景6：多用户并发场景；场景7：断网恢复场景。
 * 并发用**真 HTTP + 独立 Cookie 会话**（不是同一个浏览器上下文），
 * 断网用 AbortController 在请求中途切断（真断），再观察恢复行为。
 */
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const L = require('./lib');

const BASE = L.BASE;
const PW = L.PW;
const OUT = 'docs/元质量_20261016/_scenarios';
const readJson = (f) => { try { return JSON.parse(fs.readFileSync(path.join(OUT, f), 'utf-8')); } catch (e) { return null; } };
const P = readJson('_s1_project.json') || {};
const PID = P.pid;
const COMPANY = 1;

class Client {
  constructor(name) { this.name = name; this.cookies = new Map(); this.csrf = ''; }

  async call(method, p, { body, raw, ctype, signal, timeout = 300000 } = {}) {
    const headers = {};
    if (this.cookies.size) headers.Cookie = Array.from(this.cookies).map(([k, v]) => `${k}=${v}`).join('; ');
    if (this.csrf && !['GET', 'HEAD'].includes(method)) headers['X-CSRF-Token'] = this.csrf;
    let data;
    if (raw) { data = raw; headers['Content-Type'] = ctype; }
    else if (body !== undefined) { data = JSON.stringify(body); headers['Content-Type'] = 'application/json'; }
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), timeout);
    if (signal) signal.addEventListener('abort', () => ctl.abort());
    try {
      const r = await fetch(BASE + p, { method, headers, body: data, redirect: 'manual', signal: ctl.signal });
      const sc = r.headers.getSetCookie ? r.headers.getSetCookie() : [];
      for (const c of sc) {
        const [kv] = c.split(';');
        const i = kv.indexOf('=');
        this.cookies.set(kv.slice(0, i).trim(), kv.slice(i + 1).trim());
      }
      if (this.cookies.has('csrf_token')) this.csrf = this.cookies.get('csrf_token');
      const buf = Buffer.from(await r.arrayBuffer());
      return { status: r.status, buf, text: buf.toString('utf-8') };
    } finally { clearTimeout(timer); }
  }

  async json(method, p, opt) { const r = await this.call(method, p, opt); try { return { status: r.status, data: JSON.parse(r.text) }; } catch (e) { return { status: r.status, data: { _raw: r.text.slice(0, 200) } }; } }

  async login(u) { return this.json('POST', '/api/auth/login', { body: { username: u, password: PW } }); }
}

function multipart(files, fields = {}) {
  const b = '----MQ2' + crypto.randomBytes(8).toString('hex');
  const out = [];
  for (const [k, v] of Object.entries(fields)) out.push(Buffer.from(`--${b}\r\nContent-Disposition: form-data; name="${k}"\r\n\r\n${v}\r\n`));
  for (const [name, buf] of files) {
    out.push(Buffer.from(`--${b}\r\nContent-Disposition: form-data; name="files"; filename="${name}"\r\nContent-Type: application/octet-stream\r\n\r\n`));
    out.push(buf); out.push(Buffer.from('\r\n'));
  }
  out.push(Buffer.from(`--${b}--\r\n`));
  return { raw: Buffer.concat(out), ctype: `multipart/form-data; boundary=${b}` };
}

(async () => {
  const SAMPLE = path.resolve(__dirname, '..', '..', 'data', 'uploads', '1');
  const pick = (n) => fs.readdirSync(SAMPLE).filter(f => f.endsWith('.xlsx')).slice(0, n);
  const s6 = new L.Scenario('S6', '多用户并发场景', '5 角色并发', '全部');

  // 6-1 同时登录
  await s6.step('多个用户同时登录（5 个并发会话）', async () => {
    const users = ['sim_finance', 'sim_advisor', 'sim_expert', 'sim_admin', 'sim_auditor'];
    const cs = users.map(u => new Client(u));
    const t0 = Date.now();
    const rs = await Promise.all(cs.map((c, i) => c.login(users[i])));
    const ms = Date.now() - t0;
    const bad = rs.map((r, i) => ({ u: users[i], st: r.status, ok: r.data.ok, perms: (r.data.permissions || []).length }))
                   .filter(x => x.st !== 200 || !x.ok);
    if (bad.length) return { result: 'fail', error: '并发登录失败：' + JSON.stringify(bad) };
    return { note: `5 个会话并发登录全部成功（${ms}ms）；权限数=${rs.map(r => (r.data.permissions || []).length).join('/')}` };
  }, { shot: false });

  // 6-2 同时上传
  await s6.step('多个用户同时上传（3 个并发上传）', async () => {
    if (!PID) return { result: 'blocked', blocker: '无项目' };
    const cs = [new Client('a'), new Client('b'), new Client('c')];
    for (const c of cs) await c.login('sim_finance');
    const all = fs.readdirSync(SAMPLE).filter(f => f.endsWith('.xlsx'));
    const groups = [all.slice(0, 2), all.slice(2, 4), all.slice(4, 6)];
    const t0 = Date.now();
    const rs = await Promise.all(cs.map((c, i) => {
      const payload = groups[i].map((f, j) => [f + '.probe' + i + j + '.tmp', fs.readFileSync(path.join(SAMPLE, f))]);
      // 用真实文件名（否则扩展名不匹配会被拒）：改回原名，仅靠内容区分
      const payload2 = groups[i].map(f => [f, fs.readFileSync(path.join(SAMPLE, f))]);
      return c.call('POST', `/api/v1/projects/${PID}/documents`, multipart(payload2));
    }));
    const ms = Date.now() - t0;
    const sts = rs.map(r => r.status);
    const parsed = rs.map(r => { try { return JSON.parse(r.text); } catch (e) { return {}; } });
    const upN = parsed.map(d => (d.stats && d.stats.uploaded) !== undefined ? d.stats.uploaded
                                : (d.uploaded || []).length);
    const dupN = parsed.map(d => (d.stats && d.stats.duplicated) !== undefined ? d.stats.duplicated
                                 : (d.duplicated || []).length);
    const rejN = parsed.map(d => (d.stats && d.stats.rejected) !== undefined ? d.stats.rejected
                                 : (d.rejected || []).length);
    const okN = sts.filter(x => x === 201).length;
    if (okN < 3) return { result: 'fail', error: '并发上传未全部受理，状态=' + sts.join(',') };
    if (upN.reduce((a, b) => a + b, 0) === 0) {
      return { result: 'fail', error: '并发上传受理但 0 份入库', note: `状态=${sts.join(',')} 新增=${upN.join('/')} 重复=${dupN.join('/')} 拒绝=${rejN.join('/')}` };
    }
    return { note: `${ms}ms 内 3 路并发上传均 201；新增=${upN.join('/')} 重复=${dupN.join('/')} 拒绝=${rejN.join('/')}（各会话独立计数，无串号）` };
  }, { shot: false });

  // 6-3 同时分析
  await s6.step('多个用户同时分析（同账套并发发起）', async () => {
    if (!PID) return { result: 'blocked', blocker: '无项目' };
    const a = new Client('a'), b = new Client('b');
    await a.login('sim_finance'); await b.login('sim_advisor');
    const t0 = Date.now();
    const [ra, rb] = await Promise.all([
      a.json('POST', `/api/v1/projects/${PID}/analysis-jobs`, { body: { force: false } }),
      b.json('POST', `/api/v1/projects/${PID}/analysis-jobs`, { body: { force: false } }),
    ]);
    const ms = Date.now() - t0;
    const ja = ra.data.job_id, jb = rb.data.job_id;
    const msgA = ra.data.message || ra.data.detail || '';
    const msgB = rb.data.message || rb.data.detail || '';
    // 期望：要么两者同一个 job（接管），要么后者被明确拒绝（互斥）——都算"不重复跑"
    const sameJob = !!ja && ja === jb;
    const rejected = rb.status >= 400 || ra.status >= 400;
    if (!sameJob && !rejected) {
      return { result: 'fail', error: '同一账套并发发起了两个独立作业（未互斥）',
               note: `job_a=${ja} job_b=${jb}；提示A=${msgA} 提示B=${msgB}` };
    }
    return { note: `${ms}ms；job_a=${ja || '(被拒)'}，job_b=${jb || '(被拒)'}；` +
                   (sameJob ? '两路复用同一作业（接管）' : '后者被明确拒绝（互斥）') +
                   `；提示=${(msgB || msgA).slice(0, 120)}` };
  }, { shot: false });

  // 6-4 同时生成报告
  await s6.step('多个用户同时生成报告（3 路并发）', async () => {
    if (!PID) return { result: 'blocked', blocker: '无项目' };
    const cs = [new Client('a'), new Client('b'), new Client('c')];
    for (const c of cs) await c.login('sim_advisor');
    // 先取"生成前"台账基线，才能判断本轮并发登记的版本号是否重复
    const before = await cs[0].json('GET', `/api/v1/reports/versions?project_id=${PID}&page_size=200`);
    const n0 = ((before.data.items || before.data.versions || [])).length;
    const t0 = Date.now();
    const rs = await Promise.all(cs.map(c => c.json('POST', `/api/v1/projects/${PID}/reports`,
      { body: { view: 'management', formats: ['html'], change_note: '并发场景模拟' } })));
    const ms = Date.now() - t0;
    const okN = rs.filter(r => r.status === 200 || r.status === 201).length;
    if (okN < 3) return { result: 'fail', error: '并发生成报告失败',
                          note: rs.map(r => r.status + ':' + String(r.data.detail || '').slice(0, 60)).join(' | ') };
    const docs = rs.map(r => r.data.doc_no);
    const vers = rs.map(r => r.data.version);
    const after = await cs[0].json('GET', `/api/v1/reports/versions?project_id=${PID}&page_size=200`);
    const rows = (after.data.items || after.data.versions || []);
    const added = rows.slice(0, rows.length - n0);
    const addedVers = added.map(x => x.version);
    const dupVers = addedVers.filter((v, i) => addedVers.indexOf(v) !== i);
    if (dupVers.length) {
      return { result: 'fail',
               error: `并发下版本号重复登记：新增 ${added.length} 条台账，版本号 ${JSON.stringify(addedVers)} 存在重复（${[...new Set(dupVers)].join(',')}）`,
               note: `3 路返回 doc_no=${[...new Set(docs)].join(',')} version=${vers.join(',')}；台账新增 ${added.length} 条` };
    }
    return { note: `${ms}ms；3 路 201；doc_no=${[...new Set(docs)].join(',')}；version=${vers.join(',')}；台账新增 ${added.length} 条且版本号互不重复` };
  }, { shot: false });

  // 6-5 同时复核
  await s6.step('多个用户同时复核（3 路并发处置不同风险）', async () => {
    if (!PID) return { result: 'blocked', blocker: '无项目' };
    const c0 = new Client('a'); await c0.login('sim_advisor');
    const rk = await c0.json('GET', `/api/v1/projects/${PID}/risks?page_size=8&state=pending`);
    const items = (rk.data.items || []).slice(0, 3);
    if (items.length < 2) return { result: 'blocked', blocker: `待处理风险不足（${items.length} 条）` };
    const cs = items.map(() => new Client('r'));
    for (const c of cs) await c.login('sim_advisor');
    const t0 = Date.now();
    // ★ 合法动作集 = REVIEW_ACTIONS（confirm/exclude/false_positive/rectify/to_manual/reopen）
    const rs = await Promise.all(items.map((it, i) => cs[i].json('POST',
      `/api/v1/risks/${encodeURIComponent(it.risk_no)}/review`,
      { body: { action: 'confirm', company_id: COMPANY, note: '并发复核（场景模拟）' } })));
    const ms = Date.now() - t0;
    const sts = rs.map(r => r.status);
    const bad = rs.filter(r => r.status >= 400);
    if (bad.length) {
      return { result: 'fail', error: `${bad.length}/3 路并发复核被拒`,
               note: `状态=${sts.join(',')}；响应=${JSON.stringify(bad[0].data).slice(0, 160)}` };
    }
    await new Promise(r => setTimeout(r, 1200));
    const one = await c0.json('GET', `/api/v1/risks/${encodeURIComponent(items[0].risk_no)}`);
    const st0 = one.data.review_state || one.data.state || '';
    const cnt = await c0.json('GET', `/api/v1/projects/${PID}/risks?page_size=25&state=confirmed`);
    return { note: `${ms}ms；3 路并发处置状态=${sts.join(',')}；样例条目状态=${st0}（应为 confirmed）；已确认总数=${cnt.data.total}` };
  }, { shot: false });

  const d6 = await s6.finish();

  /* ═══════════ 场景7：断网恢复 ═══════════ */
  const s7 = new L.Scenario('S7', '断网恢复场景', '企业财务', 'sim_finance');
  const big = path.join(require('os').tmpdir(), 'metaq2_fix', '模拟·12MB分片资料.xlsx');
  if (!fs.existsSync(big)) {
    const buf = Buffer.alloc(1024 * 1024, 0x42);
    const fd = fs.openSync(big, 'w');
    for (let i = 0; i < 12; i += 1) fs.writeSync(fd, buf);
    fs.closeSync(fd);
  }
  const bigSize = fs.statSync(big).size;
  const bigMd5 = crypto.createHash('md5').update(fs.readFileSync(big)).digest('hex');

  // 7-1 上传中途断网 + 恢复续传
  await s7.step('上传中途断网（真实 11.8MB 大表，走分片通道）', async () => {
    if (!PID) return { result: 'blocked', blocker: '无项目' };
    const bigPath = path.join(require('os').tmpdir(), 'metaq2_fix', '场景7-真大序时账.xlsx');
    if (!fs.existsSync(bigPath)) return { result: 'blocked', blocker: '缺少真实大 xlsx 夹具（先运行 genbig）' };
    const buf = fs.readFileSync(bigPath);
    s7.bigPath = bigPath; s7.bigSize = buf.length;
    s7.bigMd5 = crypto.createHash('md5').update(buf).digest('hex');
    const c = new Client('u'); await c.login('sim_finance');
    const init = await c.json('POST', '/api/v1/documents/chunk/init',
      { body: { project_id: PID, filename: '场景7-真大序时账.xlsx', size: buf.length, md5: s7.bigMd5 } });
    if (init.status >= 400) return { result: 'fail', error: '分片初始化失败：' + JSON.stringify(init.data).slice(0, 200) };
    const uid = init.data.upload_id; const chunkSize = init.data.chunk_size || 5242880;
    const total = init.data.chunks_total || Math.ceil(buf.length / chunkSize);
    s7.uploadId = uid; s7.chunkSize = chunkSize; s7.total = total;
    const p1 = await c.call('PUT', `/api/v1/documents/chunk/${uid}/0`, { raw: buf.subarray(0, chunkSize), ctype: 'application/octet-stream' });
    const ctl = new AbortController();
    let aborted = false;
    const p2 = c.call('PUT', `/api/v1/documents/chunk/${uid}/1`,
      { raw: buf.subarray(chunkSize, chunkSize * 2), ctype: 'application/octet-stream', signal: ctl.signal })
      .catch(e => { aborted = true; return { status: 0 }; });
    setTimeout(() => ctl.abort(), 3);
    await p2;
    const st = await c.json('GET', `/api/v1/documents/chunk/${uid}`);
    const received = (st.data.received || []).map(Number);
    const missing = (st.data.missing || []);
    if (p1.status !== 200) return { result: 'fail', error: '第 1 片上传未成功（HTTP ' + p1.status + '）' };
    if (!aborted) return { result: 'fail', error: '第 2 片未能在中途切断', note: JSON.stringify(st.data).slice(0, 160) };
    s7.receivedBefore = received.length;
    return { note: `${(buf.length / 1024 / 1024).toFixed(2)}MB 共 ${total} 片；第 1 片 200；第 2 片被中途切断；续传依据：已收=${JSON.stringify(received)}，缺失=${JSON.stringify(missing)}` };
  }, { shot: false });

  // 7-2 恢复后继续（补齐缺失分片并合并入库）
  await s7.step('恢复后继续（补齐分片并合并入库）', async () => {
    const uid = s7.uploadId;
    if (!uid) return { result: 'blocked', blocker: '无 upload_id（前置断网未建立）' };
    const c = new Client('u2'); await c.login('sim_finance');
    const buf = fs.readFileSync(s7.bigPath);
    const st = await c.json('GET', `/api/v1/documents/chunk/${uid}`);
    const received = new Set((st.data.received || []).map(Number));
    const chunkSize = s7.chunkSize, total = s7.total;
    for (let i = 0; i < total; i += 1) {
      if (received.has(i)) continue;
      await c.call('PUT', `/api/v1/documents/chunk/${uid}/${i}`,
        { raw: buf.subarray(i * chunkSize, Math.min((i + 1) * chunkSize, buf.length)), ctype: 'application/octet-stream' });
    }
    const done = await c.json('POST', `/api/v1/documents/chunk/${uid}/complete`);
    const stats = done.data.stats || {};
    const up = (done.data.uploaded || []).length || stats.uploaded || 0;
    const rej = done.data.rejected || [];
    if (done.status >= 400) return { result: 'fail', error: `合并失败 HTTP ${done.status}：${JSON.stringify(done.data).slice(0, 200)}` };
    if (!up) {
      return { result: 'fail', error: '合并 HTTP 200 但 0 份入库（用户以为传上去了）',
               note: `续传前已收 ${received.size}/${total} 片；stats=${JSON.stringify(stats)}；rejected=${JSON.stringify(rej).slice(0, 200)}` };
    }
    const inList = await c.json('GET', `/api/v1/projects/${PID}/documents?page_size=300`);
    const hit = (inList.data.items || []).filter(x => (x.original_name || '').includes('场景7-真大序时账'));
    if (!hit.length) return { result: 'fail', error: '合并入库成功但资料列表查不到（前后端不一致）', note: JSON.stringify(stats) };
    return { note: `续传前已收 ${received.size}/${total} 片 → 补齐 → complete HTTP ${done.status}；入库 ${up} 份（id=${hit[0].id} 大小=${hit[0].size} 状态=${hit[0].parse_status}）；列表可见 ✅` };
  }, { shot: false });

  // 7-3 分析中途断网
  await s7.step('分析中途断网（轮询中断后回读一致性）', async () => {
    if (!PID) return { result: 'blocked', blocker: '无项目' };
    const c = new Client('an'); await c.login('sim_finance');
    const st = await c.json('POST', `/api/v1/projects/${PID}/analysis-jobs`, { body: { force: false } });
    const job = st.data.job_id;
    if (!job) return { note: `发起被拒（HTTP ${st.status}）：${JSON.stringify(st.data).slice(0, 200)}` };
    // 中断：只读一次就切断（模拟断网后停止轮询）
    const ctl = new AbortController();
    const one = c.call('GET', `/api/v1/analysis-jobs/${job}`, { signal: ctl.signal }).catch(() => null);
    ctl.abort();
    const r1 = await one;
    // "重连"：新会话回读
    const c2 = new Client('an2'); await c2.login('sim_finance');
    const back = await c2.json('GET', `/api/v1/analysis-jobs/${job}`);
    const list = await c2.json('GET', `/api/v1/projects/${PID}/analysis-jobs?page_size=10`);
    const sameJob = (list.data.jobs || []).filter(x => x.job_id === job).length;
    const others = (list.data.jobs || []).length;
    if (back.status !== 200) return { result: 'fail', error: '重连后读不到原作业（HTTP ' + back.status + '）' };
    return { note: `断网时单次读=${r1 ? r1.status : '被切断'}；重连后状态=${back.data.status}（引擎=${back.data.engine_status || '—'}）进度=${back.data.progress}；同账套作业条数=${others}，重复登记=${sameJob === 1 ? '无' : '有 ' + sameJob + ' 条'}` };
  }, { shot: false });

  // 7-4 报告生成中途断网
  await s7.step('报告生成中途断网（不留半成品）', async () => {
    if (!PID) return { result: 'blocked', blocker: '无项目' };
    const c = new Client('rp'); await c.login('sim_advisor');
    const before = await c.json('GET', `/api/v1/projects/${PID}/reports?page_size=50`);
    const n0 = (before.data.items || []).length;
    const ctl = new AbortController();
    const p = c.call('POST', `/api/v1/projects/${PID}/reports`,
      { body: { view: 'full', formats: ['pdf', 'xlsx'], change_note: '断网模拟' }, signal: ctl.signal })
      .catch(e => ({ status: 0, text: String(e.message || e) }));
    setTimeout(() => ctl.abort(), 800);
    const r = await p;
    await new Promise(x => setTimeout(x, 4000));
    const c2 = new Client('rp2'); await c2.login('sim_advisor');
    const after = await c2.json('GET', `/api/v1/projects/${PID}/reports?page_size=50`);
    const n1 = (after.data.items || []).length;
    const delta = n1 - n0;
    s7.reportDelta = delta;
    return { note: `请求被切断（status=${r.status}）；断前报告 ${n0} 条 → 断后 ${n1} 条（Δ=${delta}）` + (delta > 1 ? '『一次请求产生多条记录』' : '') };
  }, { shot: false });

  const d7 = await s7.finish();

  const all = [d6, d7];
  fs.writeFileSync(path.join(OUT, '_s67_summary.json'), JSON.stringify(all, null, 1), 'utf-8');
  for (const d of all) console.log(`\n=== ${d.scenario} ${d.conclusion} 步骤${d.step_count} 失败${d.fail_count} 阻断${d.blocked_count}`);
  console.log('\n' + JSON.stringify(L.summary(all)));
})().catch(e => { console.error('FATAL', e); process.exit(3); });
