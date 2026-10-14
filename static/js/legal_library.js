/* 法规库（P2-1）前端逻辑 —— 原生 JS，无框架、无构建（沿用现有技术栈）。
 *
 * 约定：
 *   · CSRF / 401 由全局拦截器处理（security.js）。
 *   · 状态枚举、来源文件、覆盖口径**一律取后端** /api/v1/legal-library/meta（不硬编码）。
 *   · **前端不硬编码任何条文** —— 全部来自后端（后端又全部来自数据文件）。
 *   · 无权限时后端 403，前端如实展示（不静默降级）。
 */
(function () {
  "use strict";

  var API = "/api/v1";
  var META = null;
  var PAGE = 1, SIZE = 50, LAST = null;

  function el(id) { return document.getElementById(id); }
  function esc(s) {
    return String(s === null || s === undefined ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function alertBox(kind, text) {
    el("alert").innerHTML = text ? '<div class="msg ' + kind + '">' + esc(text) + "</div>" : "";
  }
  async function api(method, url, body) {
    var opt = { method: method, headers: {} };
    if (body !== undefined) {
      opt.headers["Content-Type"] = "application/json";
      opt.body = JSON.stringify(body);
    }
    var r = await fetch(url, opt);
    var t = await r.text();
    var j = null;
    try { j = t ? JSON.parse(t) : null; } catch (e) { j = { raw: t }; }
    if (!r.ok) { throw new Error((j && (j.detail || j.message)) || ("HTTP " + r.status)); }
    return j;
  }
  function statusTag(v) {
    if (!v) { return ""; }
    return '<span class="tag ' + esc(v.status) + '">' + esc(v.status_cn || v.status) + "</span>";
  }

  async function loadMeta() {
    try {
      META = await api("GET", API + "/legal-library/meta");
      var fs = (META.sources || []).map(function (x) { return x.file; }).join("、");
      var w = META.warnings || [];
      el("src-note").textContent = "（来源：" + fs + "）";
      var cov = META.coverage || {};
      el("coverage-note").innerHTML =
        "覆盖口径：" + esc(cov.caveat || "") +
        (cov.coverage !== null && cov.coverage !== undefined
          ? "<br>登记覆盖率 <b>" + esc(String(Math.round(cov.coverage * 10000) / 100) + "%")
            + "</b>（匹配 " + esc(cov.matched_refs) + " / " + esc(cov.total_refs)
            + "；正文库 " + esc(cov.library_size) + " 条）"
          : "<br>覆盖率未登记。") +
        "<br>版本登记表：" + esc(META.version_registry || "");
    } catch (e) {
      el("src-note").textContent = "（字典加载失败：" + e.message + "）";
    }
  }

  async function loadStats() {
    var s;
    try { s = await api("GET", API + "/legal-library/stats"); }
    catch (e) { el("kpis").innerHTML = '<div class="muted">统计加载失败：' + esc(e.message) + "</div>"; return; }
    function k(n, t) { return '<div class="kpi"><div class="n">' + esc(n) + '</div><div class="t">' + esc(t) + "</div></div>"; }
    var statusKpis = (s.by_version_status || []).map(function (x) { return k(x.laws, x.label + "（部）"); }).join("");
    el("kpis").innerHTML =
      k(s.articles, "已收录条文") + k(s.laws, "涉及法数") + statusKpis +
      k(s.unregistered_laws.length, "版本未登记（部）") + k(s.blocking_laws.length, "已被取代/失效（部）");
    var w = [];
    if (s.blocking_laws && s.blocking_laws.length) {
      w.push('<div class="msg warn">已被取代/失效的法（引用即被闸门拦下）：' + esc(s.blocking_laws.join("、")) + "</div>");
    }
    el("alert").innerHTML = w.join("");
  }

  async function loadLaws() {
    var j;
    try { j = await api("GET", API + "/legal-library/laws"); }
    catch (e) { el("tb-laws").innerHTML = '<tr><td colspan="4" class="muted">加载失败：' + esc(e.message) + "</td></tr>"; return; }
    el("law-hint").textContent = "（共 " + j.total + " 部；条数为已收录条数，不代表该法全部条文）";
    var sel = el("law-sel");
    sel.innerHTML = '<option value="">全部法名</option>' + j.items.map(function (x) {
      return '<option value="' + esc(x.law) + '">' + esc(x.law) + "（" + x.articles + "）</option>";
    }).join("");
    el("tb-laws").innerHTML = j.items.map(function (x) {
      var v = x.version || {};
      return "<tr>" +
        '<td><span class="law-link" data-law="' + esc(x.law) + '">' + esc(x.law) + "</span></td>" +
        '<td class="num">' + esc(x.articles) + "</td>" +
        "<td>" + statusTag(v) + (v.blocking ? ' <span class="tag expired">阻断</span>' : "") + "</td>" +
        '<td class="muted">' + esc(v.current_version || "（版本未登记）") +
          (v.source ? "<br>" + esc(v.source) : "") + "</td>" +
        "</tr>";
    }).join("") || '<tr><td colspan="4" class="muted">（无）</td></tr>';
  }

  async function loadEntries() {
    var q = el("q").value.trim();
    var law = el("law-sel").value;
    var oc = el("only-current").checked;
    var url = API + "/legal-library?page=" + PAGE + "&page_size=" + SIZE +
      (q ? "&q=" + encodeURIComponent(q) : "") +
      (law ? "&law=" + encodeURIComponent(law) : "") +
      (oc ? "&only_current=true" : "");
    var j;
    try { j = await api("GET", url); }
    catch (e) { el("tb-entries").innerHTML = '<tr><td colspan="5" class="muted">检索失败：' + esc(e.message) + "</td></tr>"; return; }
    LAST = j;
    el("ent-hint").textContent = "共 " + j.total + " 条";
    el("pg-info").textContent = "第 " + j.page + " / " + (j.pages || 1) + " 页";
    el("pg-prev").disabled = j.page <= 1;
    el("pg-next").disabled = j.page >= (j.pages || 1);
    el("tb-entries").innerHTML = (j.items || []).map(function (x) {
      return "<tr>" +
        '<td><span class="law-link" data-law="' + esc(x.law) + '">' + esc(x.law) + "</span></td>" +
        '<td class="art">' + esc(x.article || "—") + "</td>" +
        '<td class="content">' + esc(x.content) + "</td>" +
        "<td>" + statusTag(x.version) + "</td>" +
        '<td class="muted">' + esc(x.source || x.from || "—") + "</td>" +
        "</tr>";
    }).join("") || '<tr><td colspan="5" class="muted">（无匹配条文）</td></tr>';
  }

  async function openLaw(law) {
    var d;
    try { d = await api("GET", API + "/legal-library/" + encodeURIComponent(law)); }
    catch (e) { alertBox("err", "详情加载失败：" + e.message); return; }
    el("dlg-title").textContent = law;
    var head = '<div class="muted" style="margin-bottom:10px">版本括注：' + esc(d.version_note || "") + "</div>";
    var rows = (d.articles || []).map(function (a) {
      return '<div style="padding:8px 0;border-bottom:1px solid #f1f5f9">' +
        '<div><b>' + esc(a.article || "(无条号)") + "</b> " + statusTag(a.version) + "</div>" +
        '<pre class="plain">' + esc(a.content) + "</pre>" +
        (a.source ? '<div class="muted" style="font-size:12px">' + esc(a.source) + "</div>" : "") +
        "</div>";
    }).join("");
    el("dlg-body").innerHTML = head + (rows || '<div class="muted">（该法无已收录条文）</div>');
    el("dlg").showModal();
  }

  function bind() {
    el("btn-search").onclick = function () { PAGE = 1; loadEntries(); };
    el("btn-reset").onclick = function () {
      el("q").value = ""; el("law-sel").value = ""; el("only-current").checked = false;
      PAGE = 1; loadEntries();
    };
    el("q").addEventListener("keydown", function (e) {
      if (e.key === "Enter") { PAGE = 1; loadEntries(); }
    });
    el("only-current").addEventListener("change", function () { PAGE = 1; loadEntries(); });
    el("law-sel").addEventListener("change", function () { PAGE = 1; loadEntries(); });
    el("pg-prev").onclick = function () { if (PAGE > 1) { PAGE--; loadEntries(); } };
    el("pg-next").onclick = function () { if (LAST && PAGE < (LAST.pages || 1)) { PAGE++; loadEntries(); } };
    el("dlg-close").onclick = function () { el("dlg").close(); };
    document.addEventListener("click", function (ev) {
      var t = ev.target.closest ? ev.target.closest("[data-law]") : null;
      if (t) { openLaw(t.getAttribute("data-law")); }
    });
  }

  (async function init() {
    bind();
    await loadMeta();
    await loadStats();
    await loadLaws();
    await loadEntries();
  })();
})();
