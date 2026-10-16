/**
 * META-QUALITY 阶段2 · 场景模拟公共库（Playwright 真浏览器驱动）
 *
 * 设计要点：
 *  · 每步都记录「结果 / 耗时 / 错误文本 / 卡点 / 截图」，落 JSON 供报告生成；
 *  · 显式收集 **浏览器控制台错误** 与 **未捕获异常**（用户看得见的报错才是真报错）；
 *  · 不做"接口 200 即通过"的判定 —— 判定看**页面上真的出现了什么**。
 */
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const BASE = process.env.SIM_BASE || 'http://127.0.0.1:8023';
const PW = 'MetaQ2-Sim-2026!';
const SHOT_DIR = process.env.SHOT_DIR ||
  'docs/元质量_20261016/场景模拟_截图';
const OUT_DIR = process.env.OUT_DIR || 'docs/元质量_20261016/_scenarios';

fs.mkdirSync(SHOT_DIR, { recursive: true });
fs.mkdirSync(OUT_DIR, { recursive: true });

class Scenario {
  constructor(id, name, role, roleUser) {
    this.id = id; this.name = name; this.role = role; this.user = roleUser;
    this.steps = []; this.n = 0;
    this.consoleErrors = []; this.pageErrors = [];
    this.shots = [];
  }

  /** 单步执行：返回 {ok, value}；异常 ⇒ 记 fail 并把错误文本落到 error 字段 */
  async step(name, fn, opts = {}) {
    this.n += 1;
    const sid = `${this.id}-${String(this.n).padStart(2, '0')}`;
    const t0 = Date.now();
    const rec = { sid, step: this.n, name, result: 'fail', ms: 0, error: '', note: '',
                  blocker: '', shot: '' };
    try {
      const r = await fn(rec);
      rec.result = rec.result === 'fail' ? 'success' : rec.result;
      if (r && typeof r === 'object') {
        if (r.note) rec.note = r.note;
        if (r.result) rec.result = r.result;
        if (r.blocker) rec.blocker = r.blocker;
        if (r.error) rec.error = String(r.error).slice(0, 500);
        if (r.value !== undefined && r.note === undefined) rec.note = String(r.value).slice(0, 400);
      } else if (r !== undefined) {
        rec.note = String(r).slice(0, 400);
      }
    } catch (e) {
      rec.result = 'fail';
      rec.error = String((e && e.message) || e).slice(0, 500);
      rec.trace = String((e && e.stack) || '').split('\n').slice(0, 4).join(' | ').slice(0, 400);
    }
    rec.ms = Date.now() - t0;
    if (opts.shot !== false) {
      const f = path.join(SHOT_DIR, `${sid}_${(opts.shotName || name).replace(/[^\w\u4e00-\u9fa5]/g, '_').slice(0, 30)}.png`);
      try { await opts.page().screenshot({ path: f, fullPage: !!opts.fullPage }); rec.shot = f; this.shots.push(f); }
      catch (e) { /* 截图失败不影响步骤判定 */ }
    }
    this.steps.push(rec);
    const tag = rec.result === 'success' ? 'PASS' : (rec.result === 'blocked' ? 'BLOCK' : 'FAIL');
    console.log(`[${sid}] ${tag} ${name} (${rec.ms}ms)${rec.note ? ' | ' + rec.note.slice(0, 120) : ''}${rec.error ? ' | ERR: ' + rec.error.slice(0, 160) : ''}`);
    return rec;
  }

  async finish() {
    const worst = this.steps.some(s => s.result === 'fail') ? 'fail'
      : (this.steps.some(s => s.result === 'blocked') ? 'blocked' : 'success');
    const data = {
      scenario: this.id, name: this.name, role: this.role, user: this.user,
      steps: this.steps, conclusion: worst,
      step_count: this.steps.length,
      fail_count: this.steps.filter(s => s.result === 'fail').length,
      blocked_count: this.steps.filter(s => s.result === 'blocked').length,
      blockers: this.steps.filter(s => s.blocker).map(s => ({ sid: s.sid, name: s.name, blocker: s.blocker })),
      console_errors: this.consoleErrors.slice(0, 40),
      page_errors: this.pageErrors.slice(0, 40),
      shots: this.shots,
      total_ms: this.steps.reduce((a, s) => a + s.ms, 0),
    };
    fs.writeFileSync(path.join(OUT_DIR, `${this.id}.json`), JSON.stringify(data, null, 1), 'utf-8');
    return data;
  }
}

async function newBrowser() {
  const b = await chromium.launch();
  return b;
}

async function newPage(browser, tag) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 },
                                         ignoreHTTPSErrors: true });
  const page = await ctx.newPage();
  const sc = tag;             // scenario 引用，由调用方注入
  page.on('console', m => { if (m.type() === 'error' && sc) sc.consoleErrors.push(m.text().slice(0, 300)); });
  page.on('pageerror', e => { if (sc) sc.pageErrors.push(String(e.message || e).slice(0, 300)); });
  // ★ 本系统多处用原生 window.confirm 做二次确认（如"取消作业"）。Playwright 默认**驳回**对话框，
  //   会导致"用户点了按钮但请求根本没发出"——这属于**测试驱动缺陷**，不是产品缺陷。
  //   此处按真人操作**接受**对话框，并把确认文本记进对话框台账以便报告引用。
  page.dialogs = [];
  page.on('dialog', async d => {
    page.dialogs.push({ type: d.type(), message: String(d.message()).slice(0, 200) });
    try { await d.accept(); } catch (e) { /* 已自动关闭 */ }
  });
  return { ctx, page };
}

/** 真浏览器登录（走 /login 表单）；等真正离开 /login 再返回，避免导航竞态。 */
async function login(page, username, password = PW, sc = null) {
  await page.goto(BASE + '/login', { waitUntil: 'domcontentloaded' });
  await page.fill('#username', username);
  await page.fill('#password', password);
  await page.click('#submit');
  try {
    await page.waitForURL(u => !String(u).includes('/login'), { timeout: 20000 });
  } catch (e) { /* 登录失败会停在 /login，错误文本由调用方读取 */ }
  await page.waitForLoadState('domcontentloaded');
  await page.waitForTimeout(600);
  return page.url();
}

/** 显式选择账套（若页面在 /select-company） */
async function ensureCompany(page, companyName) {
  if (!page.url().includes('select-company')) return false;
  const ok = await page.evaluate(async (nm) => {
    const r = await fetch('/api/companies', { cache: 'no-store' });
    const list = await r.json();
    const co = (list || []).find(c => c.name === nm) || (list || [])[0];
    if (!co) return false;
    const res = await fetch('/api/auth/select-company', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ company_id: co.id }),
    });
    return res.ok;
  }, companyName);
  if (ok) { await page.goto(BASE + '/', { waitUntil: 'domcontentloaded' }); await page.waitForTimeout(500); }
  return ok;
}

/** 等某条件成立（轮询求值），返回是否成立 + 实际值 */
async function waitFor(page, fn, { timeout = 120000, interval = 2000, arg = null } = {}) {
  const t0 = Date.now();
  let last;
  while (Date.now() - t0 < timeout) {
    last = await page.evaluate(fn, arg);
    if (last && last.ok) return { ok: true, value: last };
    await page.waitForTimeout(interval);
  }
  return { ok: false, value: last, waited: Date.now() - t0 };
}

/** 页面上可见文本（用于"用户看到了什么"的判定与留证） */
async function visibleText(page, sel, limit = 500) {
  const t = await page.evaluate(s => {
    const el = document.querySelector(s);
    return el ? (el.innerText || el.textContent || '') : null;
  }, sel);
  return t === null ? null : t.replace(/\s+/g, ' ').trim().slice(0, limit);
}

function summary(rows) {
  const n = rows.length;
  const pass = rows.filter(r => r.conclusion === 'success').length;
  const fail = rows.filter(r => r.conclusion === 'fail').length;
  const blocked = rows.filter(r => r.conclusion === 'blocked').length;
  const blockers = rows.reduce((a, r) => a + r.blockers.length, 0);
  return { scenarios: n, pass, fail, blocked, blockers };
}

module.exports = { BASE, PW, SHOT_DIR, OUT_DIR, Scenario, newBrowser, newPage, login,
                   ensureCompany, waitFor, visibleText, summary };
