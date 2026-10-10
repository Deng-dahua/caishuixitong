// 复用前端真实渲染函数，离线产出「企业文书式」报告 HTML（与前端所见一致）。
// ★ 目的：把「前端应当渲染出的报告」落成可直接查看的实物，作为端到端证据。
//   渲染函数 `_buildEnterpriseReadableBody` 只做字符串拼接，唯一入参是
//   前端实际拿到的载荷（cache[company].report.report），故离线产物与前端一致。
const fs = require('fs');
const vm = require('vm');
const path = require('path');

const REPO = process.cwd();
const JS = path.join(REPO, 'static', 'js', 'tax-doc-analysis.js');
const CACHE = path.join(REPO, 'data', 'cache', 'last_analysis_cache.json');
const OUT = process.argv[2] || path.join(REPO, 'output', '报告_企业文书式.html');
const COMPANY = process.argv[3] || '1';

const src = fs.readFileSync(JS, 'utf8');
const cache = JSON.parse(fs.readFileSync(CACHE, 'utf8'));
const entry = cache[COMPANY];
if (!entry) throw new Error('缓存中找不到公司 ' + COMPANY);
const r = entry.report.report;            // 前端消费的那一层
console.log('[payload] 含 enterprise_readable_report:', !!r.enterprise_readable_report);
console.log('[payload] document_meta.name =', JSON.stringify(
  ((r.enterprise_readable_report || {}).document_meta || {}).name));

const noop = () => {};
const fakeEl = () => ({
  style: {}, innerHTML: '', textContent: '', classList: { add: noop, remove: noop, contains: () => false },
  setAttribute: noop, getAttribute: () => null, appendChild: noop, removeChild: noop,
  addEventListener: noop, querySelector: () => null, querySelectorAll: () => [], remove: noop,
  scrollIntoView: noop, focus: noop, insertAdjacentHTML: noop, cloneNode() { return fakeEl(); },
});
const sandbox = {
  console, setTimeout, clearTimeout, setInterval: noop, clearInterval: noop,
  encodeURIComponent, decodeURIComponent, JSON, Math, Date, String, Number, Boolean,
  Array, Object, RegExp, Error, Promise, Intl, isNaN, parseInt, parseFloat, escape, unescape,
  document: {
    getElementById: () => null, querySelector: () => null, querySelectorAll: () => [],
    addEventListener: noop, createElement: fakeEl, createDocumentFragment: fakeEl,
    body: fakeEl(), documentElement: fakeEl(), head: fakeEl(), cookie: '', readyState: 'complete',
    execCommand: noop, writeln: noop, write: noop, open: noop, close: noop,
  },
  localStorage: { getItem: () => null, setItem: noop, removeItem: noop, clear: noop },
  sessionStorage: { getItem: () => null, setItem: noop, removeItem: noop, clear: noop },
  location: { href: 'http://127.0.0.1:8001/', search: '', hash: '', reload: noop, assign: noop },
  navigator: { userAgent: 'node', clipboard: { writeText: () => Promise.resolve() } },
  fetch: () => Promise.reject(new Error('offline')),
  alert: noop, confirm: () => true, prompt: () => null,
  print: noop, getComputedStyle: () => ({ getPropertyValue: () => '' }),
  Blob: function () {}, URL: { createObjectURL: () => '', revokeObjectURL: noop },
  FileReader: function () {}, XMLHttpRequest: function () {},
  requestAnimationFrame: (cb) => setTimeout(cb, 0), cancelAnimationFrame: noop,
};
// 浏览器 API 桩（按报错逐个补齐；只求让模块顶层加载通过，渲染函数本身不需要它们）
const obs = function () { return { observe: noop, disconnect: noop, unobserve: noop, takeRecords: () => [] }; };
sandbox.MutationObserver = obs;
sandbox.IntersectionObserver = obs;
sandbox.ResizeObserver = obs;
sandbox.PerformanceObserver = obs;
sandbox.Event = function () {};
sandbox.CustomEvent = function () {};
sandbox.Node = function () {};
sandbox.Element = function () {};
sandbox.HTMLElement = function () {};
sandbox.HTMLDocument = function () {};
sandbox.History = function () {};
sandbox.DOMParser = function () { return { parseFromString: () => fakeEl() }; };
sandbox.XMLSerializer = function () { return { serializeToString: () => '' }; };
sandbox.XPathEvaluator = function () {};
sandbox.TextEncoder = function () { return { encode: () => new Uint8Array() }; };
sandbox.TextDecoder = function () { return { decode: () => '' }; };
sandbox.history = { pushState: noop, replaceState: noop, back: noop, forward: noop, go: noop, state: null, length: 1 };
sandbox.screen = { width: 1440, height: 900, availWidth: 1440, availHeight: 900 };
sandbox.performance = { now: () => Date.now(), mark: noop, measure: noop, getEntries: () => [] };
sandbox.crypto = { randomUUID: () => '0'.repeat(36), getRandomValues: (a) => a };
sandbox.queueMicrotask = (cb) => Promise.resolve().then(cb);
sandbox.structuredClone = (o) => JSON.parse(JSON.stringify(o));
sandbox.atob = (s) => Buffer.from(s, 'base64').toString('binary');
sandbox.btoa = (s) => Buffer.from(s, 'binary').toString('base64');
sandbox.URLSearchParams = URLSearchParams;
sandbox.AbortController = function () { return { abort: noop, signal: {} }; };
sandbox.matchMedia = () => ({ matches: false, addEventListener: noop, removeEventListener: noop, addListener: noop, removeListener: noop });
sandbox.NodeList = function () {};
sandbox.HTMLCollection = function () {};
sandbox.SVGElement = function () {};
sandbox.Image = function () {};
sandbox.WebSocket = function () { return { send: noop, close: noop, addEventListener: noop }; };
sandbox.EventSource = function () {};
sandbox.window = sandbox;
sandbox.self = sandbox;
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(src, sandbox, { filename: 'tax-doc-analysis.js' });

if (typeof sandbox._buildEnterpriseReadableBody !== 'function') {
  throw new Error('渲染函数未导出：_buildEnterpriseReadableBody');
}
for (const n of ['_reportDocName', '_isEnterpriseEdition', '_capabilityStyles',
                 '_resetMaterialClaims', 'esc', 'escHtml']) {
  console.log('  [scope]', n, '=>', typeof sandbox[n]);
}
const body = sandbox._buildEnterpriseReadableBody(r, '2026年10月07日');
if (!body || body.length < 500) throw new Error('渲染结果过短，疑似失败: ' + (body || '').length);

const docName = (typeof sandbox._reportDocName === 'function')
  ? sandbox._reportDocName(r) : '税务风险扫描工作底稿';
const isEnt = (typeof sandbox._isEnterpriseEdition === 'function')
  ? sandbox._isEnterpriseEdition(r) : null;
console.log('[render] 前端判据 _isEnterpriseEdition =', isEnt);
console.log('[render] 报告名称 =', docName, '| 正文长度 =', body.length);

const page = '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
  + '<title>' + docName + '</title>'
  + '<style>body{font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;'
  + 'max-width:960px;margin:0 auto;padding:40px 44px;line-height:1.85;color:#1a1a1a;}'
  + 'h1{font-size:24px;text-align:center;} h2{font-size:17px;margin:28px 0 10px;}'
  + 'h3{font-size:15px;margin:20px 0 8px;} table{width:100%;border-collapse:collapse;font-size:13px;margin:8px 0;}'
  + 'th,td{border:1px solid #ddd;padding:6px 8px;vertical-align:top;} th{background:#f4f6f8;}'
  + 'a{color:#185FA5;text-decoration:none;} .toc{background:#f8fafc;border:1px solid #e2e8f0;'
  + 'border-radius:6px;padding:12px 16px;margin:0 0 20px;font-size:13px;line-height:2;}</style>'
  + '</head><body>' + body + '</body></html>';

fs.mkdirSync(path.dirname(OUT), { recursive: true });
fs.writeFileSync(OUT, page, 'utf8');
console.log('[done] 已生成:', OUT, fs.statSync(OUT).size, 'bytes');
