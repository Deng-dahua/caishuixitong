/* -*- coding: utf-8 -*-
 * 首页总览（P0-2，2026-10-17）—— 阶段 3「用户视角评估」的 P0 建议落实。
 *
 * 背景：首页原先正文仅 0.4KB、说明性文案 0 字、无反馈区，登录后只有一个侧栏，
 *      用户不知道"该先做什么"（8 维度均分 3.38，全站最低）。
 *
 * 契约（**全部复用既有只读接口**，本文件不新增任何后端）：
 *   GET /api/v1/projects?page=1&page_size=5&sort=updated_at&order=desc
 *   GET /api/v1/risks/review-board?project_id=<最近项目>
 *   GET /api/v1/projects/<id>/documents?page=1&page_size=1      （只取 total）
 *   GET /api/v1/projects/<id>/analysis-jobs?limit=1              （只取最新一单；**返回键是 jobs**）
 *
 * 三条纪律：
 *   ① **口径如实**：风险指标取自"最近更新的项目"，不假装是全公司汇总；
 *   ② **缺失 ≠ 0**：取不到就显示"—"并写明原因，绝不用 0 顶替；
 *   ③ **不阻塞**：每块独立 try，单块失败不影响其它块，也绝不静默（页面上能看到原因）。
 */
'use strict';

(function () {
  var API = '/api/v1';

  function el(id) { return document.getElementById(id); }
  function esc(s) {
    return String(s === null || s === undefined ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }
  function setText(id, text) { var n = el(id); if (n) n.textContent = text; }
  function setHtml(id, html) { var n = el(id); if (n) n.innerHTML = html; }

  async function getJSON(path) {
    var res = await fetch(API + path, { credentials: 'same-origin', cache: 'no-store' });
    if (!res.ok) {
      // 4xx/5xx 一律如实抛出，由调用方显示"取不到 + 原因"
      throw new Error('HTTP ' + res.status);
    }
    return res.json();
  }

  /** 数字渲染：取不到写"—"（缺失 ≠ 0）。 */
  function num(v) {
    if (v === null || v === undefined || v === '') return '—';
    var n = Number(v);
    return Number.isFinite(n) ? String(n) : '—';
  }

  var state = { projects: [], active: null };

  async function loadProjects() {
    try {
      var d = await getJSON('/projects?page=1&page_size=5&sort=updated_at&order=desc');
      state.projects = d.items || [];
    } catch (e) {
      setHtml('home-projects', '<div class="msg err">读取项目列表失败（' + esc(e.message) +
        '）。这不影响其它功能，可稍后<a href="/projects">直接进入项目页</a>。</div>');
      setText('home-hint', '部分数据读取失败，见下方提示');
      return;
    }
    renderProjects();
    state.active = state.projects[0] || null;
    if (!state.active) {
      setText('home-hint', '还没有项目 —— 请到「稽查项目管理」创建');
      setText('home-kpi-pending-sub', '无项目');
      setText('home-kpi-docs-sub', '无项目');
      setText('home-kpi-job-sub', '无项目');
      return;
    }
    // ★ 2026-10-20（用户裁定）：「数据来源：最近更新的项目…」提示行已删除；
    //   成功加载时清空提示位（否则初始文案会一直挂着）。
    setText('home-hint', '');
    await Promise.all([
      loadBoard(state.active.id),
      loadDocs(state.active.id),
      loadJob(state.active.id),
    ]);
  }

  function renderProjects() {
    if (!state.projects.length) {
      setHtml('home-projects',
        '<div class="kpi-sub">还没有项目。到「稽查项目管理」创建第一个项目后，' +
        '这里会显示最近更新的项目。</div>');
      return;
    }
    var rows = state.projects.map(function (p) {
      var status = p.status_cn || p.status || '—';
      return '<tr>' +
        '<td><a href="/projects" style="text-decoration:none">' + esc(p.name || p.code || '—') + '</a></td>' +
        '<td class="kpi-sub">' + esc(p.code || '—') + '</td>' +
        '<td class="kpi-sub">' + esc(status) + '</td>' +
        '<td class="kpi-sub">' + esc((p.updated_at || '').replace('T', ' ').slice(0, 16) || '—') + '</td>' +
        '</tr>';
    }).join('');
    setHtml('home-projects',
      '<table class="grid"><thead><tr>' +
      '<th>项目名称</th><th>项目编号</th><th>状态</th><th>最近更新</th>' +
      '</tr></thead><tbody>' + rows + '</tbody></table>');
  }

  async function loadBoard(pid) {
    try {
      var d = await getJSON('/risks/review-board?project_id=' + encodeURIComponent(pid));
      var byState = d.by_state || {};
      // 「待处理」= state 为 pending 的数量；取不到就"—"
      var pending = Object.prototype.hasOwnProperty.call(byState, 'pending')
        ? byState.pending : null;
      setText('home-kpi-pending', num(pending));
      setText('home-kpi-pending-sub', '来源：' + (state.active.name || '') +
        '（共 ' + num(d.total) + ' 条风险）');
      setText('home-kpi-overdue', num(d.overdue_count));
      setText('home-kpi-overdue-sub', '阈值 ' + num(d.stale_days) + ' 天自最近一次处置起算' +
        '；从未处置 ' + num(d.never_reviewed_count) + ' 条单列');
    } catch (e) {
      setText('home-kpi-pending', '—');
      setText('home-kpi-pending-sub', '取不到（' + e.message + '）');
      setText('home-kpi-overdue', '—');
      setText('home-kpi-overdue-sub', '取不到（' + e.message + '）');
    }
  }

  async function loadDocs(pid) {
    try {
      var d = await getJSON('/projects/' + encodeURIComponent(pid) +
        '/documents?page=1&page_size=1');
      setText('home-kpi-docs', num(d.total));
      setText('home-kpi-docs-sub', '来源：' + (state.active.name || ''));
    } catch (e) {
      setText('home-kpi-docs', '—');
      setText('home-kpi-docs-sub', '取不到（' + e.message + '）');
    }
  }

  async function loadJob(pid) {
    try {
      // ★ 契约更正（2026-10-17 实测）：本端点返回 `jobs`（**不是** `items`），
      //   且**只接受 `limit`**（没有 page/page_size —— 传了会被忽略但不报错）。
      //   第一版按 `items` + `page_size` 写 ⇒ 永远取空 ⇒ 首页错误显示"未分析"，
      //   而该项目其实跑过分析（SUCCESS）。这类"看起来正常、其实是假数据"最难发现，
      //   故此处保留注释，并把契约写在文件头。
      var d = await getJSON('/projects/' + encodeURIComponent(pid) + '/analysis-jobs?limit=1');
      var items = d.jobs || [];
      var one = items[0] || null;
      if (!one) {
        setText('home-kpi-job', '未分析');
        setText('home-kpi-job-sub', '该项目还没有分析任务');
        return;
      }
      setText('home-kpi-job', one.status_cn || one.status || '—');
      var when = String(one.finished_at || one.started_at || '').replace('T', ' ').slice(0, 16);
      var extra = (one.status === 'SUCCESS' && one.findings_count !== undefined
        ? ' · 发现 ' + num(one.findings_count) + ' 条' : '');
      setText('home-kpi-job-sub', '进度 ' + num(one.progress) + '%' + extra +
        (when ? ' · ' + when : ''));
    } catch (e) {
      setText('home-kpi-job', '—');
      setText('home-kpi-job-sub', '取不到（' + e.message + '）');
    }
  }

  function boot() {
    if (!el('home-overview')) return;      // 不是首页（或已切走）⇒ 不执行
    loadProjects();
    // 从其它内页切回首页时刷新一次（否则显示的是首次加载时的旧值）。
    // 用**事件委托**挂在侧栏，不改 core.js 的 navigateTo。
    document.addEventListener('click', function (ev) {
      var node = ev.target && ev.target.closest
        ? ev.target.closest('.nav-item[data-page="home"]') : null;
      if (node) { loadProjects(); }
    });
    // 动态节点（快捷操作按钮）也要走既有门控（rbac-nav 的 data-perm）
    if (window.RBAC && window.RBAC.reapply) { window.RBAC.reapply(); }
    if (window.RBAC && window.RBAC.ready) {
      window.RBAC.ready(function () {
        if (window.RBAC.reapply) { window.RBAC.reapply(); }
      });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
