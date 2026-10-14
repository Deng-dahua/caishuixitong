/* 多税种深度模型（P2-4）前端逻辑 —— 原生 JS，无框架、无构建（沿用现有技术栈）。
 *
 * 约定：
 *   · CSRF / 401 由全局拦截器处理（security.js）。
 *   · 税种清单、模型清单、税率口径**一律取后端**（后端转发 tax_impact / 读 config 表）——
 *     前端**不硬编码任何税种或模型**。
 *   · 未实现模型必须显示"待建"（不假装已实现）；未量化税种必须显示"未量化"。
 */
(function () {
  "use strict";

  var API = "/api/v1";

  function el(id) { return document.getElementById(id); }
  function esc(s) {
    return String(s === null || s === undefined ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  async function api(method, url) {
    var r = await fetch(url, { method: method });
    var t = await r.text();
    var j = null;
    try { j = t ? JSON.parse(t) : null; } catch (e) { j = { raw: t }; }
    if (!r.ok) { throw new Error((j && (j.detail || j.message)) || ("HTTP " + r.status)); }
    return j;
  }
  function sevTag(s, cn) {
    return '<span class="tag ' + esc(s) + '">' + esc(cn || s) + "</span>";
  }
  function implTag(m) {
    if (m.implemented) { return '<span class="tag ok">已实现</span> ' + esc(m.impl); }
    return '<span class="tag pend">待建</span> <span class="muted">' + esc(m.impl_note) + "</span>";
  }

  async function loadAll() {
    var m, ts, cx;
    try {
      ts = await api("GET", API + "/tax-models");
      cx = await api("GET", API + "/tax-models/cross-tax");
      m = await api("GET", API + "/tax-models/meta");
    } catch (e) {
      el("tb-taxes").innerHTML = '<tr><td colspan="5" class="muted">加载失败：' + esc(e.message) + "</td></tr>";
      return;
    }
    var nModels = 0, nImpl = 0, nPend = 0;
    (ts.items || []).forEach(function (x) {
      nModels += x.model_count; nImpl += x.implemented_count;
      nPend += (x.model_count - x.implemented_count);
    });
    nModels += (cx.items || []).length;
    nImpl += (cx.items || []).filter(function (x) { return x.implemented; }).length;

    el("kpis").innerHTML =
      '<div class="kpi"><div class="n">' + esc(ts.total) + '</div><div class="t">已登记税种</div></div>' +
      '<div class="kpi"><div class="n">' + esc(nModels) + '</div><div class="t">深度模型</div></div>' +
      '<div class="kpi"><div class="n">' + esc(nImpl) + '</div><div class="t">已实现</div></div>' +
      '<div class="kpi"><div class="n">' + esc(nPend) + '</div><div class="t">待建</div></div>' +
      '<div class="kpi"><div class="n">' + esc(cx.total) + '</div><div class="t">跨税种模型</div></div>';
    el("auth-note").innerHTML = esc((m && m.tax_authority) || "") + "<br>" +
      esc((m && m.rate_authority) || "") + "<br>" + esc((m && m.note) || "");

    el("tb-taxes").innerHTML = (ts.items || []).map(function (x) {
      var rate = x.quantifiable
        ? ("默认 " + esc(String(x.default_rate)))
        : '<span class="tag pend">未量化</span>';
      var ms = (x.models || []).map(function (mm) {
        return '<div style="margin-bottom:5px">' +
          '<span class="law-link" data-tax="' + esc(x.tax) + '">' + esc(mm.label) + "</span> " +
          sevTag(mm.severity, mm.severity_cn) + " " + implTag(mm) +
          '<div class="muted">' + esc(mm.focus) + "</div></div>";
      }).join("");
      return "<tr>" +
        '<td><span class="law-link" data-tax="' + esc(x.tax) + '">' + esc(x.tax) + "</span>" +
          (x.in_scope ? "" : ' <span class="tag pend">不在红线范围</span>') + "</td>" +
        '<td class="muted">' + rate + "</td>" +
        '<td class="num">' + esc(x.model_count) + "</td>" +
        '<td class="num">' + esc(x.implemented_count) + "/" + esc(x.model_count) + "</td>" +
        "<td>" + ms + "</td></tr>";
    }).join("") || '<tr><td colspan="5" class="muted">（无）</td></tr>';

    el("tb-cross").innerHTML = (cx.items || []).map(function (x) {
      return '<tr><td><span class="law-link" data-tax="(跨税种)">' + esc(x.label) + '</span><br>' +
        '<span class="muted">' + esc(x.code) + "</span></td>" +
        "<td>" + esc(x.focus) + '<div class="muted">数据：' + esc(x.data_required) + "</div></td>" +
        "<td>" + implTag(x) + "</td><td>" + sevTag(x.severity, x.severity_cn) + "</td></tr>";
    }).join("") || '<tr><td colspan="4" class="muted">（无）</td></tr>';

    // 覆盖缺口提示（如实展示，不用默认值掩盖）
    try {
      var cov = await api("GET", API + "/tax-models/coverage");
      var w = [];
      if (cov.taxes_without_models && cov.taxes_without_models.length) {
        w.push('<div class="msg warn">本系统分析但尚未登记深度模型的税种（' +
          cov.taxes_without_models.length + " 个）：" +
          esc(cov.taxes_without_models.join("、")) + "</div>");
      }
      if (cov.taxes_without_rate && cov.taxes_without_rate.length) {
        w.push('<div class="msg warn">税率未登记（未量化）的税种（' +
          cov.taxes_without_rate.length + " 个）：" +
          esc(cov.taxes_without_rate.join("、")) + "</div>");
      }
      el("alert").innerHTML = w.join("");
    } catch (e) { /* 覆盖信息失败不影响主表 */ }

    el("dlg-title");
  }

  async function openTax(tax) {
    if (tax === "(跨税种)") { return; }
    var d;
    try { d = await api("GET", API + "/tax-models/" + encodeURIComponent(tax)); }
    catch (e) { alert("详情加载失败：" + e.message); return; }
    el("dlg-title").textContent = tax + (d.in_scope ? "" : "（不在红线库税种范围内）");
    var rate = d.quantifiable ? ("默认税率 " + d.default_rate + "；" + (d.rate_note || ""))
      : ("未量化；" + (d.rate_note || ""));
    var rows = (d.models || []).map(function (m) {
      return '<div style="padding:9px 0;border-bottom:1px solid #f1f5f9">' +
        "<div><b>" + esc(m.label) + "</b> " + sevTag(m.severity, m.severity_cn) + " " + implTag(m) + "</div>" +
        '<div style="margin-top:3px">' + esc(m.focus) + "</div>" +
        '<div class="muted" style="font-size:12px">所需数据：' + esc(m.data_required) + "</div></div>";
    }).join("");
    el("dlg-body").innerHTML =
      '<div class="muted" style="margin-bottom:10px">' + esc(rate) + "</div>" +
      (rows || '<div class="muted">（该税种尚无已登记模型）</div>');
    el("dlg").showModal();
  }

  document.addEventListener("click", function (ev) {
    var t = ev.target.closest ? ev.target.closest("[data-tax]") : null;
    if (t) { openTax(t.getAttribute("data-tax")); }
  });
  document.addEventListener("DOMContentLoaded", function () {
    var c = el("dlg-close");
    if (c) { c.onclick = function () { el("dlg").close(); }; }
  });
  loadAll();
})();
