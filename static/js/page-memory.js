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
    var all = load();
    var k = bucketKey();
    all[k] = all[k] || {};
    all[k][el.id] = el.value;
    save(all);
  }

  function bind() {
    restore();
    document.addEventListener('change', function (ev) {
      var t = ev.target;
      if (t && (t.tagName === 'SELECT' || t.tagName === 'INPUT')) { remember(t); }
    }, true);
    // 输入框失焦也记（搜索框常常不触发 change）
    document.addEventListener('blur', function (ev) {
      var t = ev.target;
      if (t && t.tagName === 'INPUT' && t.type !== 'password' && t.type !== 'file') {
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
