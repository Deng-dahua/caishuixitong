/* 报告模板管理（P1-5）前端逻辑 —— 原生 JS，无框架、无构建（沿用现有技术栈）。
 *
 * 约定：
 *   · CSRF 由全局 fetch 拦截器自动附加（security.js）；401 由它跳 /login。
 *   · 章节白名单、模板来源、编码规则**一律取后端** /api/v1/report-templates/meta（不硬编码）。
 *   · 写操作需要 `template.manage`；无权限时后端 403，前端如实展示（不静默降级）。
 */
(function () {
  "use strict";

  var API = "/api/v1";
  var META = null, ROWS = [], EDITING = null, SECTION_PICK = [];

  function el(id) { return document.getElementById(id); }
  function esc(s) {
    return String(s === null || s === undefined ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function alertBox(kind, text) {
    el("alert").innerHTML = text
      ? '<div class="msg ' + kind + '">' + esc(text) + "</div>" : "";
    if (kind === "ok") { setTimeout(function () { el("alert").innerHTML = ""; }, 6000); }
  }
  async function api(method, url, body) {
    var opt = { method: method, headers: {} };
    if (body !== undefined) {
      opt.headers["Content-Type"] = "application/json";
      opt.body = JSON.stringify(body);
    }
    var res = await fetch(url, opt);
    var data = null;
    try { data = await res.json(); } catch (e) { data = null; }
    if (!res.ok) {
      var d = (data && (data.detail || data.message)) || ("HTTP " + res.status);
      var err = new Error(typeof d === "string" ? d : JSON.stringify(d));
      err.status = res.status;
      throw err;
    }
    return data;
  }

  function scopeTag(x) {
    var cls = x.disabled ? "off" : (x.scope === "builtin" ? "builtin" : "custom");
    var label = x.disabled ? "已停用"
      : (x.scope === "builtin"
          ? (x.overridden ? "内置（已被覆盖）" : "内置")
          : (x.was_builtin ? "自定义（覆盖内置）" : "自定义"));
    return '<span class="tag ' + cls + '">' + esc(label) + "</span>";
  }

  async function loadMeta() {
    META = await api("GET", API + "/report-templates/meta");
    el("edit-hint").textContent = "（章节必须落在白名单内，共 " + (META.base_sections || []).length + " 个）";
    renderSectionPicker();
  }

  function renderSectionPicker() {
    var host = el("t-sections");
    var base = (META && META.base_sections) || [];
    host.className = "chips";
    host.innerHTML = base.map(function (s) {
      var on = SECTION_PICK.indexOf(s) >= 0;
      return '<span class="chip' + (on ? " on" : "") + '" data-sec="' + esc(s) + '">'
        + esc(s) + (on ? " ✓" : "") + "</span>";
    }).join("");
    host.onclick = function (ev) {
      var t = ev.target;
      if (!t || !t.getAttribute || !t.getAttribute("data-sec")) return;
      var s = t.getAttribute("data-sec");
      var i = SECTION_PICK.indexOf(s);
      if (i >= 0) { SECTION_PICK.splice(i, 1); } else { SECTION_PICK.push(s); }
      renderSectionPicker();
    };
  }

  async function loadList() {
    var inc = el("inc-off").checked ? "?include_disabled=true" : "";
    var j;
    try { j = await api("GET", API + "/report-templates" + inc); }
    catch (e) {
      el("tb").innerHTML = '<tr><td colspan="7" class="muted">加载失败：' + esc(e.message) + "</td></tr>";
      return;
    }
    ROWS = j.items || [];
    el("list-hint").textContent = "（共 " + j.total + " 项；" + (j.note || "") + "）";
    el("tb").innerHTML = ROWS.map(function (x) {
      return "<tr>"
        + "<td>" + esc(x.template_id) + "</td>"
        + "<td>" + esc(x.label) + "</td>"
        + "<td>" + scopeTag(x) + "</td>"
        + "<td>" + esc(x.version || 0) + "</td>"
        + "<td class='muted'>" + esc((x.sections || []).join(" → ")) + "</td>"
        + "<td class='muted'>" + esc(x.emphasis || "—") + "</td>"
        + "<td>"
        + '<button class="btn ghost" data-edit="' + esc(x.template_id) + '">编辑</button> '
        + '<button class="btn ghost" data-hist="' + esc(x.template_id) + '">历史</button> '
        + (x.disabled ? '<button class="btn ghost" data-edit="' + esc(x.template_id) + '">重新启用</button>'
                      : '<button class="btn ghost" data-off="' + esc(x.template_id) + '">停用</button>')
        + "</td></tr>";
    }).join("") || '<tr><td colspan="7" class="muted">（无模板）</td></tr>';
  }

  function startEdit(tid) {
    var x = ROWS.filter(function (r) { return r.template_id === tid; })[0];
    EDITING = tid;
    el("t-id").value = tid;
    el("t-label").value = x ? (x.label || "") : "";
    el("t-emphasis").value = x ? (x.emphasis || "") : "";
    el("t-note").value = "";
    SECTION_PICK = x ? (x.sections || []).slice() : [];
    renderSectionPicker();
    el("save-hint").textContent = "正在编辑：" + tid
      + (x && x.disabled ? "（当前已停用；保存后将重新启用）" : "");
  }

  function clearForm() {
    EDITING = null; SECTION_PICK = [];
    el("t-id").value = ""; el("t-label").value = "";
    el("t-emphasis").value = ""; el("t-note").value = "";
    el("save-hint").textContent = "";
    renderSectionPicker();
  }

  async function save() {
    var tid = (el("t-id").value || "").trim();
    if (!tid) { alertBox("warn", "请填写模板编码"); return; }
    var body = {
      label: (el("t-label").value || "").trim(),
      sections: SECTION_PICK.slice(),
      emphasis: (el("t-emphasis").value || "").trim(),
      note: (el("t-note").value || "").trim()
    };
    try {
      var j = await api("POST", API + "/report-templates/" + encodeURIComponent(tid), body);
      alertBox("ok", j.message || "已保存");
      clearForm();
      await loadList();
    } catch (e) { alertBox("err", "保存失败：" + e.message); }
  }

  async function disable(tid) {
    if (!window.confirm("确认停用模板「" + tid + "」？\n（若它覆盖了内置模板，将回到内置出厂值）")) return;
    try {
      var j = await api("POST", API + "/report-templates/" + encodeURIComponent(tid) + "/disable", {});
      alertBox("ok", j.message || "已停用");
      await loadList();
    } catch (e) { alertBox("err", "停用失败：" + e.message); }
  }

  async function loadHistory(tid) {
    var j;
    try { j = await api("GET", API + "/report-templates/" + encodeURIComponent(tid) + "/versions"); }
    catch (e) {
      el("tb-hist").innerHTML = '<tr><td colspan="7" class="muted">加载失败：' + esc(e.message) + "</td></tr>";
      return;
    }
    el("hist-hint").textContent = "（模板：" + tid + "，共 " + j.total + " 条变更）";
    el("tb-hist").innerHTML = (j.items || []).map(function (x) {
      return "<tr><td>v" + esc(x.version) + "</td><td>" + esc(x.action) + "</td>"
        + "<td class='muted'>" + esc(x.at) + "</td><td>" + esc(x.actor || "—") + "</td>"
        + "<td>" + esc(x.label || "—") + "</td>"
        + "<td class='muted'>" + esc((x.sections || []).join(" → ") || "—") + "</td>"
        + "<td class='muted'>" + esc(x.note || "") + "</td></tr>";
    }).join("") || '<tr><td colspan="7" class="muted">（该模板尚无变更记录 —— '
      + '内置模板在未覆盖前历史为空，空历史不表示模板不存在）</td></tr>';
  }

  document.addEventListener("DOMContentLoaded", async function () {
    try {
      var me = await api("GET", "/api/me").catch(function () { return null; });
      if (me && me.username) { el("who").textContent = me.username; }
    } catch (e) { /* 未登录由全局 401 处理 */ }
    try { await loadMeta(); }
    catch (e) { alertBox("err", "字典加载失败：" + e.message); }
    await loadList();

    el("btn-refresh").onclick = loadList;
    el("inc-off").onchange = loadList;
    el("btn-save").onclick = save;
    el("btn-clear").onclick = clearForm;

    document.addEventListener("click", function (ev) {
      var t = ev.target;
      if (!t || !t.getAttribute) return;
      var e1 = t.getAttribute("data-edit");
      var h1 = t.getAttribute("data-hist");
      var o1 = t.getAttribute("data-off");
      if (e1) { startEdit(e1); return; }
      if (h1) { loadHistory(h1); return; }
      if (o1) { disable(o1); }
    });
  });
})();
