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
const posArgs = [];
args.forEach((a) => { if (a === '--pyramid') pyramid = true; else posArgs.push(a); });
if (posArgs.length < 2) {
  console.error('用法: node verify_frontend_render.js <report.json> "子串1" ["子串2" ...] [--pyramid]');
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
};
sandbox.window._tdaReportEdition = 'workpaper';
vm.createContext(sandbox);
vm.runInContext(js, sandbox, { filename: jsPath });

const data = JSON.parse(fs.readFileSync(reportPath, 'utf-8'));
const r = data.report || data; // 顶层结果（含 enterprise_readable_report）或本身就是 report

function checkFn(name, fn) {
  let html;
  try { html = fn(r, '2026-01-01'); }
  catch (e) { console.log('FAIL - ' + name + ' 渲染抛错: ' + e.message); return false; }
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
