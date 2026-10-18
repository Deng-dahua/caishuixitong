/* -*- coding: utf-8 -*-
 * 共享 DOM / 展示工具（唯一权威，2026-10-19）
 *
 * ## 为什么抽这个文件
 *
 * 用户要求「把资料风险分析报告模块融入报告生成与导出模块」。该报告的渲染由
 * `tax-doc-analysis.js::renderTaxDocReport` 完成（**报告级渲染的唯一实现**，
 * 不另写一份 —— 否则两条链会各出各的报告）。而它调用 4 个原本只在 `core.js`
 * 里定义的全局工具：
 *
 *   `normalizeDisplayValue` / `escapeHtml` / `escHtml` / `toast`
 *
 * 此前这 4 个函数**只存在于 `core.js`**。`core.js` 是 SPA 主控制器，加载即自启
 * `_startApp()`（拉账套数据、注册导航、切页）—— 引到独立页 `/reports` 会产生
 * 一堆与本页无关的请求与报错。而审计闸门 `check_js_undefined_calls` 按
 * **"每个 HTML 页面的脚本包"**求定义：`/reports` 一旦加载 `tax-doc-analysis.js`
 * 而没有这 4 个定义，会直接报「调用 `escHtml(...)` 但该页加载的全部脚本中查无此名」。
 *
 * ⇒ 正确做法不是"在 reports.js 里再抄一份"（那就是**多头维护**：两份转义实现
 *   迟早分叉，而转义分叉直接等于 XSS 风险或显示错乱），而是**抽成单一权威**：
 *   · 本文件 = 这 4 个函数的唯一实现；
 *   · `index.html` / `reports.html` 都加载它（`core.js` **不再自带实现**，改为引用本文件）。
 *
 * ## 加载顺序要求
 * 必须在 `core.js` 与 `tax-doc-analysis.js` **之前**加载（它们顶层即引用这些名字）。
 *
 * ## 为什么用 `var` 而非 `const/let`
 * 沿用本仓既有风格：这些名字是**全局函数声明**，与 `core.js` 原写法保持一致
 * （`core.js:176-177` 原本就是 `var esc = escapeHtml; var escHtml = escapeHtml;`）。
 */
'use strict';

/* 展示值归一化：把任意类型转成"能安全显示成文本"的字符串。
 * ★ 逻辑与 `core.js` 原实现逐字一致（Equal-to-before 迁移，不是重写）——
 *   它被报告正文大量使用（金额/日期/数组/对象混入），语义任何变化都会改报告内容。
 */
function normalizeDisplayValue(value) {
  if (value === undefined || value === null) return '';
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean' || typeof value === 'bigint') return String(value);
  if (value instanceof Date) return value.toISOString();
  if (Array.isArray(value)) return value.map(normalizeDisplayValue).filter(Boolean).join('、');
  if (typeof value === 'object') {
    try {
      var seen = typeof WeakSet === 'function' ? new WeakSet() : null;
      var json = JSON.stringify(value, function (key, item) {
        if (item && typeof item === 'object' && seen) {
          if (seen.has(item)) return '[循环引用]';
          seen.add(item);
        }
        return item;
      });
      if (!json || json === '{}') return '结构化数据（无可展示字段）';
      return json.length > 2000 ? json.slice(0, 2000) + '…' : json;
    } catch (error) {
      return '结构化数据（请展开详情查看）';
    }
  }
  return String(value);
}

/* 全局统一转义函数（全名）。报告正文/dashboard 等处大量拼 HTML 时用它防注入。 */
function escapeHtml(s) {
  var text = normalizeDisplayValue(s);
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

/* 转义的简写别名（既有代码两种写法都在用：`esc(...)` 与 `escHtml(...)`）。 */
var esc = escapeHtml;
var escHtml = escapeHtml;

/* 轻提示条（3 秒自动消失）。样式在 `static/css/app.css`（`.toast`），
 * 故所有加载了 app.css 的页面都能用 —— `/reports` 已引入 app.css。 */
function toast(msg, type = 'default') {
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 3000);
}