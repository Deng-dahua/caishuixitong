/* 记住上次选择（H-01，2026-10-17）
 *
 * 评估结论：「**17/21 模块不记住上次选择** —— 每次进页都要重选项目与筛选条件，
 * 这是最高频的重复劳动」。
 *
 * 做法：**一个通用脚本，不改任何页面逻辑**
 *   · 自动接管页面里所有 `<select id="...">`：变更即存，进入即回填（选项不存在则放弃回填）；
 *   · 只按「页面路径 + 元素 id」存，跨页不串味；
 *   · **绝不记忆**密码框、文件选择框、隐藏域；
 *   · 存储不可用（隐私模式/超额）时整段静默失效 —— 记忆是体验优化，不能变成故障源。
 *
 * ★ 为什么用"通用接管"而不是逐页改：新增一个筛选框不需要再改一行代码。
 */
(function () {
  'use strict';

  var KEY = 'pageMemory.v1';
  var skips = /(password|passwd|pwd|file|hidden|csrf|token)/i;

  function load() {
    try { return JSON.parse(localStorage.getItem(KEY) || '{}') || {}; } catch (e) { return {}; }
  }
  function save(all) {
    try { localStorage.setItem(KEY, JSON.stringify(all)); } catch (e) { /* 静默 */ }
  }
  function bucketKey() {
    return location.pathname || '/';
  }

  function candidates() {
    var out = [];
    var nodes = document.querySelectorAll('select[id], input[type="text"][id], input[type="search"][id]');
    for (var i = 0; i < nodes.length; i += 1) {
      var el = nodes[i];
      if (!el.id || skips.test(el.id) || el.disabled) { continue; }
      out.push(el);
    }
    return out;
  }

  function restore() {
    var all = load();
    var mine = all[bucketKey()] || {};
    candidates().forEach(function (el) {
      var v = mine[el.id];
      if (v == null || v === '') { return; }
      if (el.tagName === 'SELECT') {
        var hit = false;
        for (var i = 0; i < el.options.length; i += 1) {
          if (el.options[i].value === v) { hit = true; break; }
        }
        if (hit) { el.value = v; }
      } else if (!el.value) {
        el.value = v;
      }
    });
  }

  function remember(el) {
    if (!el || !el.id || skips.test(el.id)) { return; }
    // ★ 2026-10-19 修（真实隐患）：**按 `type` 排除敏感输入**，不能只靠 id 关键字。
    //   此前 `change` 监听（下方 bind）对 `type` **全不设防**，只靠 id 命中
    //   `password|pwd` 关键字来跳过 —— 那是**偶然**保护：只要 id 不叫 "password"
    //   （例如新增的 `pw-old` / `pw-new`），密码就被明文写进 localStorage。
    //   `blur` 分支虽有 type 判断，但 `change` 分支没有 —— 两条路径必须同口径。
    if (isSensitive(el)) { return; }
    var all = load();
    var k = bucketKey();
    all[k] = all[k] || {};
    all[k][el.id] = el.value;
    save(all);
  }

  /** 是否属于"绝不可持久化"的敏感输入（类型级判据，与 id 命名无关）。 */
  function isSensitive(el) {
    var t = String((el && el.type) || '').toLowerCase();
    if (t === 'password' || t === 'file' || t === 'hidden') { return true; }
    // 浏览器对未识别的 type 会回落成 text；`autocomplete` 的新旧密码提示一并排除
    var ac = String((el && el.getAttribute && el.getAttribute('autocomplete')) || '').toLowerCase();
    if (ac.indexOf('password') !== -1) { return true; }
    return false;
  }

  function bind() {
    restore();
    document.addEventListener('change', function (ev) {
      var t = ev.target;
      // ★ 与 blur 分支同口径：SELECT 全记；INPUT 先过 isSensitive（含 type=password）
      if (t && t.tagName === 'SELECT') { remember(t); return; }
      if (t && t.tagName === 'INPUT' && !isSensitive(t)) { remember(t); }
    }, true);
    // 输入框失焦也记（搜索框常常不触发 change）
    document.addEventListener('blur', function (ev) {
      var t = ev.target;
      if (t && t.tagName === 'INPUT' && !isSensitive(t)) {
        remember(t);
      }
    }, true);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bind);
  } else {
    bind();
  }
})();
