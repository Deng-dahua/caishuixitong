/*
 * 前端渲染**运行时对齐审计**（只读，不改任何文件）。
 *
 * 目的：用**真实后端产物**驱动**真实前端渲染函数**，直接抓：
 *   ① 未取到值的字段（渲染成 undefined / NaN）
 *   ② 字段名泄漏（键名被当正文渲染）
 *   ③ 各章节是否真的产出了内容（空章节 = 前端不显示后端算出来的东西）
 *
 * 为什么必须运行时：静态 grep 无法区分 `report.` 在**同一文件的两个作用域**
 *   里分别指向 `r.enterprise_readable_report`（报告层）与 `window._reportData`（引擎层）
 *   —— 本项目已因此误判过一次。运行时按"实际取到什么"判定才可靠。
 *
 * 用法：node scripts/_audit_frontend_render.js data/_audit_payload.json
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const ROOT = path.resolve(__dirname, '..');
const payloadPath = process.argv[2] || path.join(ROOT, 'data', '_audit_payload.json');
const payload = JSON.parse(fs.readFileSync(payloadPath, 'utf8'));

// ── DOM 桩：记录每个 id 最后一次 innerHTML ──
const store = {};
function el(id) {
  if (store[id]) return store[id];
  const e = {
    id, innerHTML: '', outerHTML: '', textContent: '', value: '',
    style: new Proxy({}, { get: () => '', set: () => true }),
    dataset: {}, children: [], _html: '',
    classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
    appendChild() {}, removeChild() {}, insertBefore() {},
    addEventListener() {}, removeEventListener() {}, dispatchEvent() {},
    setAttribute() {}, getAttribute() { return null; }, removeAttribute() {},
    querySelector() { return null; }, querySelectorAll() { return []; },
    focus() {}, blur() {}, click() {}, remove() {}, insertAdjacentHTML() {},
    scrollIntoView() {}, getBoundingClientRect() { return { top: 0, left: 0, width: 0, height: 0 }; },
  };
  Object.defineProperty(e, 'innerHTML', {
    get() { return e._html; },
    set(v) { e._html = String(v); },
  });
  store[id] = e;
  return e;
}

const documentStub = {
  getElementById: (id) => el(id),
  querySelector: () => null,
  querySelectorAll: () => [],
  createElement: (t) => el('__created_' + t + '_' + Math.random()),
  createDocumentFragment: () => el('__frag'),
  addEventListener: () => {},
  removeEventListener: () => {},
  head: el('__head'),
  body: el('__body'),
  documentElement: { style: {}, setAttribute() {}, getAttribute() { return null; } },
  cookie: '',
  readyState: 'complete',
  hidden: false,
  write() {},
};

const consoleStub = {
  log() {}, warn() {}, error() {}, info() {}, debug() {},
  group() {}, groupEnd() {}, table() {}, trace() {},
};

const ctx = {
  console: consoleStub,
  document: documentStub,
  navigator: { userAgent: 'node-audit', clipboard: { writeText: async () => {} } },
  location: { href: '', origin: 'http://127.0.0.1:8001', search: '', hash: '' },
  localStorage: { getItem: () => null, setItem() {}, removeItem() {}, clear() {} },
  sessionStorage: { getItem: () => null, setItem() {}, removeItem() {}, clear() {} },
  fetch: async () => ({ ok: false, status: 0, json: async () => ({}), text: async () => '', headers: { get: () => null } }),
  XMLHttpRequest: function () {
    this.open = () => {}; this.send = () => {}; this.setRequestHeader = () => {};
    this.addEventListener = () => {}; this.upload = { addEventListener() {} };
  },
  setTimeout: (fn) => 0, clearTimeout: () => {}, setInterval: () => 0, clearInterval: () => {},
  requestAnimationFrame: () => 0, cancelAnimationFrame: () => {},
  toast: () => {}, alert: () => {}, confirm: () => true, prompt: () => null,
  currentCompanyId: 1,
  Intl, Date, Math, JSON, RegExp, String, Number, Array, Object, Boolean, Error,
  Map, Set, WeakMap, Promise, Symbol, Proxy, Reflect, BigInt,
  parseInt, parseFloat, isNaN, isFinite, encodeURIComponent, decodeURIComponent,
  escape, unescape, URL, URLSearchParams, TextEncoder, TextDecoder, Buffer,
  Blob: function () {}, File: function () {}, FileReader: function () { this.readAsText = () => {}; },
  FormData: function () { this.append = () => {}; },
  Audio: function () { this.play = () => {}; this.pause = () => {}; },
  SpeechSynthesisUtterance: function () {},
  speechSynthesis: { speak() {}, cancel() {}, getVoices: () => [] },
  marked: { parse: (s) => String(s) },
  XLSX: undefined,
};
// ★ 观察器/多媒体桩：缺一个就会让整个脚本在**顶层语句**处抛错 ⇒ 只加载到一半，
//   后面的函数全部缺失（本项目实测：漏 MutationObserver ⇒ 报告渲染"看似正常"但覆盖不全）。
ctx.MutationObserver = function () { this.observe = () => {}; this.disconnect = () => {}; this.takeRecords = () => []; };
ctx.IntersectionObserver = function () { this.observe = () => {}; this.disconnect = () => {}; this.unobserve = () => {}; };
ctx.ResizeObserver = function () { this.observe = () => {}; this.disconnect = () => {}; this.unobserve = () => {}; };
ctx.PerformanceObserver = function () { this.observe = () => {}; this.disconnect = () => {}; };
ctx.CustomEvent = function (t, o) { this.type = t; this.detail = (o || {}).detail; };
ctx.Event = function (t) { this.type = t; };
ctx.matchMedia = () => ({ matches: false, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {} });
ctx.getComputedStyle = () => ({ getPropertyValue: () => '' });
ctx.atob = (s) => Buffer.from(s, 'base64').toString('binary');
ctx.btoa = (s) => Buffer.from(s, 'binary').toString('base64');
ctx.crypto = { randomUUID: () => '00000000-0000-4000-8000-000000000000' };
ctx.window = ctx;
ctx.self = ctx;
ctx.globalThis = ctx;
ctx.window.addEventListener = () => {};
ctx.window.matchMedia = () => ({ matches: false, addListener() {}, removeListener() {} });
ctx.window.getComputedStyle = () => ({ getPropertyValue: () => '' });

vm.createContext(ctx);

// ── 加载前端脚本（多文件按序：core 提供 api/esc 等） ──
const files = ['constants.js', 'core.js', 'tax-doc-analysis.js'];
const loaded = [];
for (const f of files) {
  const p = path.join(ROOT, 'static', 'js', f);
  if (!fs.existsSync(p)) continue;
  try {
    vm.runInContext(fs.readFileSync(p, 'utf8'), ctx, { filename: f });
    loaded.push(f);
  } catch (e) {
    console.log('  [load warn] ' + f + ' → ' + e.message.slice(0, 120));
  }
}
console.log('已加载脚本: ' + loaded.join(', '));
console.log('renderTaxDocReport 可用: ' + (typeof ctx.renderTaxDocReport === 'function'));

// ── 运行渲染 ──
let renderErr = '';
try {
  ctx.window._reportData = payload;
  ctx.taxDocReportData = payload;
  if (typeof ctx.renderTaxDocReport === 'function') ctx.renderTaxDocReport(payload);
} catch (e) {
  renderErr = e && e.stack ? e.stack.split('\n').slice(0, 3).join(' | ') : String(e);
}
console.log('渲染异常: ' + (renderErr || '（无）'));

const html = (store['tda-report-area'] || { innerHTML: '' }).innerHTML || '';
console.log('报告区 HTML 长度: ' + html.length);
// DUMP_HTML=1 时把渲染结果落盘，便于对"某段内容到底有没有渲染"做 grep 取证
if (process.env.DUMP_HTML) {
  const out = path.join(ROOT, 'data', '_audit_rendered.html');
  fs.writeFileSync(out, html, 'utf8');
  console.log('已落盘渲染结果: ' + out);
}

// ── 扫描 ──
const issues = [];
if (!html) issues.push('报告区 HTML 为空 —— 前端根本没有产出报告（渲染中断或提前 return）');
const patterns = [
  [/\bundefined\b/g, 'undefined 泄漏'],
  [/\bNaN\b/g, 'NaN 泄漏'],
  [/\[object Object\]/g, '[object Object] 泄漏'],
  [/\*\*[a-z_]+\*\*/g, 'markdown 字段名泄漏（**key**）'],
];
for (const [re, label] of patterns) {
  const m = html.match(re) || [];
  if (m.length) {
    const uniq = Array.from(new Set(m.map((s) => s.trim()))).slice(0, 12);
    issues.push(label + ' × ' + m.length + ' → ' + uniq.join(' , '));
  }
}

// 章节是否产出（按 h2 锚点）
const sections = [
  ['company-conclusion', '一、检查情况总述与总体结论'],
  ['company-problems', '二、本轮风险检查确认的具体问题'],
  ['company-scope-note', '三、覆盖范围声明'],
  ['company-recheck', '四、整改验收与下一轮复查标准'],
  ['company-statement', '五、报告性质和使用说明'],
];
const secReport = sections.map(([id, name]) => {
  const has = html.includes('id="' + id + '"');
  return (has ? '✓' : '✗') + ' ' + name;
});

// ── 第一章实际取到哪个字段 ──
const ocParas = ((payload.enterprise_readable_report || {}).overall_conclusion || {}).paragraphs || [];
const firstLine = ocParas.length
  ? 'oc.paragraphs 渲染（' + ocParas.length + ' 段 / ' + ocParas.join('').length + ' 字）'
  : 'oc.paragraphs 为空 ⇒ 走 headline+owner_message 兜底';

console.log('\n' + '='.repeat(76));
console.log('【运行时对齐审计结果】');
console.log('='.repeat(76));
console.log('\n第一章取值路径: ' + firstLine);
console.log('\n章节产出:');
secReport.forEach((s) => console.log('  ' + s));
console.log('\n渲染缺陷:');
if (!issues.length) console.log('  （无）');
issues.forEach((s) => console.log('  ⚠ ' + s));

// 第一章段落原文（供人工核验是否为"压缩版全文"）
if (ocParas.length) {
  console.log('\n第一章段落（前 3 段，各截 110 字）:');
  ocParas.slice(0, 3).forEach((t, i) => console.log('  [' + (i + 1) + '] ' + String(t).slice(0, 110)));
  console.log('  ... 共 ' + ocParas.length + ' 段');
}
