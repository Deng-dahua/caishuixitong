// verify_frontend_render.js — 在桩环境加载前端渲染函数，验证某段是否真的被网页画出（免开浏览器）。
// 用法：
//   node verify_frontend_render.js <report.json> "必须出现的子串1" "子串2" ... [--pyramid]
// report.json 为顶层含 enterprise_readable_report 的分析结果（如 _fresh_result.json）。
// 退出码 0 = 全部命中（ALL_FRONTEND_CHECKS_PASS）；非 0 = 有缺失。
const fs = require('fs');
const vm = require('vm');
const path = require('path');

const args = process.argv.slice(2);
let pyramid = false;
let dumpPath = '';
const posArgs = [];
for (let i = 0; i < args.length; i++) {
  const a = args[i];
  if (a === '--pyramid') { pyramid = true; continue; }
  // ★ 2026-10-05：`--dump <file>` 输出**完整渲染 HTML**。
  //   原因：只做"子串是否存在"是**同义反复**（页面由数据渲染，问"有没有"必然有），
  //   防不住任何真问题。要判断"页面上到底显示了什么/有没有空块/有没有重复章"，
  //   必须有 HTML 全文本可供切块分析（见 tools/verify_page_render.py）。
  if (a === '--dump') { dumpPath = args[i + 1] || ''; i++; continue; }
  posArgs.push(a);
}
if (posArgs.length < 1) {
  console.error('用法: node verify_frontend_render.js <report.json> ["子串1" ...] [--pyramid] [--dump <out.html>]');
  process.exit(2);
}
const reportPath = posArgs[0];
const needles = posArgs.slice(1);

const repoRoot = process.env.CAISHUI_ROOT
  || path.resolve(__dirname, '..', '..', '..', '..');
const jsPath = path.join(repoRoot, 'static', 'js', 'tax-doc-analysis.js');
if (!fs.existsSync(jsPath)) { console.error('找不到前端文件:', jsPath); process.exit(2); }
const js = fs.readFileSync(jsPath, 'utf-8');

// 桩：window / document 用 Proxy 兜底，任何属性/方法调用都不报错（前端函数在渲染期可能触碰它们）
function mkProxy() {
  return new Proxy(function () {}, {
    get(t, p) {
      if (p === 'length') return 0;
      if (p === Symbol.toPrimitive) return () => '';
      if (p === 'forEach' || p === 'map' || p === 'filter') return () => [];
      if (p === 'join') return () => '';
      return mkProxy();
    },
    apply() { return mkProxy(); },
    construct() { return mkProxy(); },
  });
}
const sandbox = {
  window: new Proxy({}, { get: (t, p) => (p in t ? t[p] : mkProxy()), set: (t, p, v) => { t[p] = v; return true; } }),
  document: mkProxy(),
  console, setTimeout, clearTimeout,
  JSON, Date, Math, String, Array, Object, RegExp, parseInt, parseFloat, isNaN,
  // ★ 2026-10-05（实测缺陷）：前端 `boot()` 用了浏览器的 `MutationObserver`，
  //   桩环境没提供 ⇒ 加载即抛 `ReferenceError: MutationObserver is not defined`，
  //   整个验证脚本跑不起来（"验证工具本身坏了"比"没验证"更危险 —— 会给出假通过）。
  //   补最小桩：只求不抛，不模拟真实行为（本脚本只验"某段是否被画出"）。
  MutationObserver: function MutationObserverStub() {
    return { observe() {}, disconnect() {}, takeRecords() { return []; } };
  },
  requestAnimationFrame: function (fn) { try { fn(Date.now()); } catch (e) {} return 0; },
  addEventListener() {}, removeEventListener() {},
  localStorage: { getItem() { return null; }, setItem() {}, removeItem() {} },
};
// ★ 2026-10-05：「企业检查报告版」（inspection_report）与其版本切换条已整体下线，
//   报告只渲染工作底稿版 ⇒ `_tdaReportEdition` 已从 tax-doc-analysis.js 删除，
//   此处不再需要预设该变量（预设在 script 里已无消费方，只会造成"以为还有版本切换"的误判）。
vm.createContext(sandbox);
vm.runInContext(js, sandbox, { filename: jsPath });

const data = JSON.parse(fs.readFileSync(reportPath, 'utf-8'));
const r = data.report || data; // 顶层结果（含 enterprise_readable_report）或本身就是 report

function checkFn(name, fn) {
  let html;
  try { html = fn(r, '2026-01-01'); }
  catch (e) { console.log('FAIL - ' + name + ' 渲染抛错: ' + e.message); return false; }
  // ★ 2026-10-05：`--dump` 时把完整 HTML 落盘（供结构级验收切块分析）
  if (dumpPath) {
    try { fs.writeFileSync(dumpPath, html, 'utf-8'); console.log('DUMPED - ' + dumpPath); }
    catch (e) { console.log('DUMP_FAIL - ' + e.message); }
  }
  let allOk = true;
  needles.forEach((n) => {
    const ok = html.indexOf(n) >= 0;
    console.log((ok ? 'PASS' : 'FAIL') + ' - [' + name + '] 含 "' + n + '"');
    if (!ok) allOk = false;
  });
  return allOk;
}

let ok = checkFn('工作底稿版(_buildEnterpriseReadableBody)', sandbox._buildEnterpriseReadableBody);
if (pyramid) {
  ok = checkFn('金字塔版(_buildPyramidBody)', sandbox._buildPyramidBody) && ok;
}
console.log(ok ? 'ALL_FRONTEND_CHECKS_PASS' : 'SOME_FRONTEND_CHECKS_FAIL');
process.exit(ok ? 0 : 1);
