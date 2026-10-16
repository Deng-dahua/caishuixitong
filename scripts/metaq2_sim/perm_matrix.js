/**
 * 权限矩阵实测：把 RBAC 声明的 permission 与**后端实际是否强制**逐项对照。
 * 动机：场景2/3 实测发现「复核专家生成报告 HTTP 200」，但 config/rbac.json 声明
 *       review_expert 无 report.generate、且"不导出报告" ⇒ 需系统性取证，不靠单点推断。
 *
 * 方法：每个角色用**真 HTTP + 独立会话**打同一个业务端点，记录 HTTP 码与 body；
 *       判定 = 「声明有权限 ⇒ 期望非 403」AND「声明无权限 ⇒ 期望 403」。
 * 只读探测为主；写操作选在**测试项目**上，且不做破坏性动作（不删除项目/资料）。
 */
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const L = require('./lib');

const OUT = 'docs/元质量_20261016/_scenarios';
const BASE = L.BASE, PW = L.PW;
const readJson = (f) => { try { return JSON.parse(fs.readFileSync(path.join(OUT, f), 'utf-8')); } catch (e) { return null; } };
const P = readJson('_s1_project.json') || {};
const PID = P.pid;

class Client {
  constructor() { this.cookies = new Map(); this.csrf = ''; }
  async call(method, p, { body, raw, ctype } = {}) {
    const headers = {};
    if (this.cookies.size) headers.Cookie = Array.from(this.cookies).map(([k, v]) => `${k}=${v}`).join('; ');
    if (this.csrf && !['GET', 'HEAD'].includes(method)) headers['X-CSRF-Token'] = this.csrf;
    let data;
    if (raw) { data = raw; headers['Content-Type'] = ctype; }
    else if (body !== undefined) { data = JSON.stringify(body); headers['Content-Type'] = 'application/json'; }
    const r = await fetch(BASE + p, { method, headers, body: data, redirect: 'manual' });
    const sc = r.headers.getSetCookie ? r.headers.getSetCookie() : [];
    for (const c of sc) {
      const [kv] = c.split(';'); const i = kv.indexOf('=');
      this.cookies.set(kv.slice(0, i).trim(), kv.slice(i + 1).trim());
    }
    if (this.cookies.has('csrf_token')) this.csrf = this.cookies.get('csrf_token');
    const buf = Buffer.from(await r.arrayBuffer());
    return { status: r.status, text: buf.toString('utf-8') };
  }
  async json(m, p, o) { const r = await this.call(m, p, o); try { return { status: r.status, data: JSON.parse(r.text) }; } catch (e) { return { status: r.status, data: { _raw: r.text } }; } }
  async login(u) { return this.json('POST', '/api/auth/login', { body: { username: u, password: PW } }); }
}

function mp(fields) {
  const b = '----PM' + crypto.randomBytes(6).toString('hex');
  const parts = [];
  for (const [k, v] of Object.entries(fields)) parts.push(Buffer.from(`--${b}\r\nContent-Disposition: form-data; name="${k}"\r\n\r\n${v}\r\n`));
  parts.push(Buffer.from(`--${b}\r\nContent-Disposition: form-data; name="files"; filename="权限矩阵探测.txt"\r\nContent-Type: application/octet-stream\r\n\r\nX\r\n`));
  parts.push(Buffer.from(`--${b}--\r\n`));
  return { raw: Buffer.concat(parts), ctype: `multipart/form-data; boundary=${b}` };
}

/** 被测端点：{ key, name, method, path, perm, kind }  kind: read/write */
const PROBES = [
  { key: 'project.list', name: '查看项目列表', method: 'GET', path: '/api/v1/projects?page_size=5', perm: 'project.view', kind: 'read' },
  { key: 'risk.list', name: '查看风险清单', method: 'GET', path: () => `/api/v1/projects/${PID}/risks?page_size=5`, perm: 'risk.view', kind: 'read' },
  { key: 'report.list', name: '查看报告列表', method: 'GET', path: () => `/api/v1/reports?project_id=${PID}&page_size=5`, perm: 'report.view', kind: 'read' },
  { key: 'doc.list', name: '查看资料清单', method: 'GET', path: () => `/api/v1/projects/${PID}/documents?page_size=5`, perm: 'document.view', kind: 'read' },
  { key: 'user.list', name: '查看用户名单', method: 'GET', path: '/api/v1/users?page_size=5', perm: 'user.view', kind: 'read' },
  { key: 'audit.list', name: '查看审计日志', method: 'GET', path: '/api/v1/audit-logs?page_size=5', perm: 'audit.view', kind: 'read' },
  { key: 'role.list', name: '查看角色字典', method: 'GET', path: '/api/v1/roles', perm: 'role.manage', anyOf: ['role.manage', 'user.view'], kind: 'read' },
  { key: 'risk.review', name: '提交复核意见（批注）', method: 'POST', path: () => `/api/v1/risks/${encodeURIComponent(RISK_NO)}/comment`, perm: 'risk.review', kind: 'write', body: () => ({ company_id: 1, note: '权限矩阵探测（只加批注、不改状态）' }) },
  { key: 'report.generate', name: '生成报告', method: 'POST', path: () => `/api/v1/projects/${PID}/reports`, perm: 'report.generate', kind: 'write', body: () => ({ view: 'self_check', formats: ['html'], change_note: '权限矩阵探测' }) },
  { key: 'analysis.run', name: '发起分析任务', method: 'POST', path: () => `/api/v1/projects/${PID}/analysis-jobs`, perm: 'analysis.run', kind: 'write', body: () => ({ force: false }) },
  { key: 'doc.upload', name: '上传资料', method: 'POST', path: () => `/api/v1/projects/${PID}/documents`, perm: 'document.write', kind: 'write', multipart: true },
  { key: 'project.write', name: '新建项目', method: 'POST', path: '/api/v1/projects', perm: 'project.write', kind: 'write', body: () => ({ name: '权限矩阵探测项目（可删）', taxpayer_id: '91440300MA5PB' + String(Date.now()).slice(-5) }) },
];

let RISK_NO = '';
let PROBE_PID = null;   // 独立探测项目（无在跑任务，避免 409 干扰判定）

(async () => {
  const roles = [
    ['system_admin', 'sim_admin'], ['enterprise_finance', 'sim_finance'],
    ['tax_advisor', 'sim_advisor'], ['review_expert', 'sim_expert'], ['auditor', 'sim_auditor'],
  ];
  const cfg = JSON.parse(fs.readFileSync('config/rbac.json', 'utf-8'));
  const grants = cfg.role_permissions;
  const has = (role, perm) => (grants[role] || []).includes('*') || (grants[role] || []).includes(perm);

  // 取一条风险号用于复核探测
  const c0 = new Client(); await c0.login('sim_advisor');
  const rk = await c0.json('GET', `/api/v1/projects/${PID}/risks?page_size=1`);
  RISK_NO = ((rk.data.items || [])[0] || {}).risk_no || '';
  console.log('[准备] 复核探测用 risk_no=' + (RISK_NO || '(空 → 跳过该探测)') + ' HTTP=' + rk.status + ' total=' + (rk.data.total));

  // ★ 独立探测项目：由 admin 创建，供"发起分析/上传资料"取得干净信号（避免 409/无在跑任务差异）
  {
    const ca = new Client(); await ca.login('sim_admin');
    const r = await ca.json('POST', '/api/v1/projects',
      { body: { name: '权限矩阵探测项目（自动生成，可删）',
                taxpayer_id: '91440300MA5PB' + String(Date.now()).slice(-5) } });
    PROBE_PID = r.data && (r.data.id || (r.data.project && r.data.project.id)) || null;
    console.log('[准备] 独立探测项目 pid=' + PROBE_PID + ' HTTP=' + r.status);
  }

  const rows = [];
  for (const [role, user] of roles) {
    const c = new Client();
    const lg = await c.login(user);
    for (const probe of PROBES) {
      if (probe.key === 'risk.review' && !RISK_NO) continue;
      const p = typeof probe.path === 'function' ? probe.path() : probe.path;
      let res;
      try {
        res = probe.multipart
          ? await c.call(probe.method, p, mp({ project_id: String(PID) }))
          : await c.json(probe.method, p, probe.body ? { body: probe.body() } : undefined);
      } catch (e) { res = { status: -1, text: String(e.message || e) }; }
      const declared = has(role, probe.perm);
      const got403 = res.status === 403;
      const got401 = res.status === 401;
      const declaredAny = !!probe.anyOf && probe.anyOf.some(x => has(role, x));
      const effectiveDeclared = declared || declaredAny;
      let verdict;
      if (got401) verdict = '未登录(忽略)';
      else if (effectiveDeclared && got403) verdict = '❌ 声明有权限但被拒';
      else if (!effectiveDeclared && got403) verdict = '✅ 一致';
      else if (!effectiveDeclared && res.status === 404) verdict = '◻ 数据范围先行拦截(404)';
      else if (!effectiveDeclared) verdict = '⚠ 声明无权限却放行';
      else verdict = '✅ 一致';
      rows.push({ role, user, key: probe.key, name: probe.name, perm: probe.perm, kind: probe.kind,
                  declared: effectiveDeclared, declared_raw: declared, status: res.status, verdict,
                  detail: String(res.data ? JSON.stringify(res.data) : res.text).slice(0, 200) });
      console.log(`${role.padEnd(20)} ${probe.name.padEnd(16)} 声明=${declared ? '有' : '无'} 实测HTTP=${res.status} ${verdict}`);
    }
  }

  const report = {
    generated_at: new Date().toISOString(),
    project_id: PID,
    permission_source: 'config/rbac.json::role_permissions（唯一权威）',
    probes: PROBES.map(p => ({ key: p.key, name: p.name, perm: p.perm, kind: p.kind })),
    rows,
    summary: {
      total: rows.length,
      consistent: rows.filter(r => r.verdict === '✅ 一致').length,
      missing_enforcement: rows.filter(r => r.verdict === '⚠ 声明无权限却放行').length,
      scope_blocked: rows.filter(r => r.verdict.startsWith('◻')).length,
      over_denied: rows.filter(r => r.verdict === '❌ 声明有权限但被拒').length,
    },
  };
  fs.writeFileSync(path.join(OUT, 'PERM_MATRIX.json'), JSON.stringify(report, null, 1), 'utf-8');
  console.log('\n汇总:', JSON.stringify(report.summary));
  console.log('\n【声明无权限却放行】清单:');
  rows.filter(r => r.verdict.startsWith('⚠')).forEach(r => console.log(`  ${r.role} → ${r.name}（缺 ${r.perm}）HTTP ${r.status}`));
})().catch(e => { console.error('FATAL', e); process.exit(3); });
