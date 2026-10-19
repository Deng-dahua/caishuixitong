/* 行业指标库（P2-2）前端逻辑 —— 原生 JS，无框架、无构建（沿用现有技术栈）。
 *
 * 约定：
 *   · CSRF / 401 由全局拦截器处理（security.js）。
 *   · 口径警示、来源清单、解析优先级**一律取后端** /api/v1/industry-indicators/meta（不硬编码）。
 *   · 区间一律来自后端（后端转发 industry_benchmark）；前端不做任何区间换算。
 *   · 无权限时后端 403，前端如实展示（不静默降级）。
 */
(function () {
  "use strict";

  var API = "/api/v1";
  var META = null, UNITS = {};

  function el(id) { return document.getElementById(id); }
  function esc(s) {
    return String(s === null || s === undefined ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function alertBox(kind, text) {
    el("alert").innerHTML = text ? '<div class="msg ' + kind + '">' + esc(text) + "</div>" : "";
  }
  async function api(method, url) {
    var r = await fetch(url, { method: method });
    var t = await r.text();
    var j = null;
    try { j = t ? JSON.parse(t) : null; } catch (e) { j = { raw: t }; }
    if (!r.ok) { throw new Error((j && (j.detail || j.message)) || ("HTTP " + r.status)); }
    return j;
  }
  function fmt(v, unit) {
    if (v === null || v === undefined) { return "—"; }
    return esc(v) + (unit || "");
  }

  async function loadMeta() {
    try {
      META = await api("GET", API + "/industry-indicators/meta");
      (META.indicator_keys || []).forEach(function (k) { UNITS[k.key] = k.unit; });
      el("caution").textContent = "（口径：" + (META.caution || "") + "）";
      el("src-note").innerHTML = "数据来源：" + (META.sources || []).map(function (s) {
        return esc(s.name) + "（" + esc(s.file) + "）" + (s.exists ? "✔" : "✘ 缺失");
      }).join("　|　");
      el("prio-note").textContent = "解析优先级（先命中先用）：" + (META.resolve_priority || []).join(" → ");
    } catch (e) {
      el("caution").textContent = "（字典加载失败：" + e.message + "）";
    }
  }

  async function loadStats() {
    var s;
    try { s = await api("GET", API + "/industry-indicators/stats"); }
    catch (e) { el("kpis").innerHTML = '<div class="muted">统计加载失败：' + esc(e.message) + "</div>"; return; }
    function k(n, t) { return '<div class="kpi"><div class="n">' + esc(n) + '</div><div class="t">' + esc(t) + "</div></div>"; }
    el("kpis").innerHTML =
      k(s.industries, "已登记行业") +
      k(s.indicator_keys, "指标键") +
      (s.by_benchmark_source || []).map(function (x) { return k(x.industries, x.value + "（行业）"); }).join("");
    var w = [];
    if (s.uncovered_keys && s.uncovered_keys.length) {
      w.push('<div class="msg warn">在所有行业中均无区间的指标键：' + esc(s.uncovered_keys.join("、")) + "</div>");
    }
    if (s.industries_without_indicators && s.industries_without_indicators.length) {
      w.push('<div class="msg warn">无任何区间的行业：' + esc(s.industries_without_indicators.join("、")) + "</div>");
    }
    el("alert").innerHTML = w.join("");
    el("cov-hint").textContent = "（共 " + (s.key_coverage || []).length + " 个指标键）";
    el("tb-keys").innerHTML = (s.key_coverage || []).map(function (x) {
      return "<tr><td>" + esc(x.label) + '</td><td class="muted">' + esc(x.key) + "</td>" +
        "<td>" + esc(UNITS[x.key] || "比值") + "</td>" +
        '<td class="num">' + esc(x.industries) + "/" + esc(s.industries) + "</td>" +
        '<td class="muted">' + (x.industries ? "已在部分行业登记区间" : "<b>所有行业均无区间，需核对</b>") + "</td></tr>";
    }).join("");
  }

  function rangeCell(inds) {
    if (!inds || !inds.length) { return '<span class="muted">（无区间）</span>'; }
    return inds.map(function (i) {
      var u = i.unit || "";
      return '<div class="barcell">' + esc(i.label) + "：" +
        '<span class="barlab">' + fmt(i.low, u) + " ~ " + fmt(i.high, u) + "</span></div>";
    }).join("");
  }

  async function loadList() {
    var q = el("q").value.trim();
    var j;
    try { j = await api("GET", API + "/industry-indicators" + (q ? "?q=" + encodeURIComponent(q) : "")); }
    catch (e) { el("tb-inds").innerHTML = '<tr><td colspan="5" class="muted">加载失败：' + esc(e.message) + "</td></tr>"; return; }
    el("ind-hint").textContent = "（共 " + j.total + " 个行业；点行业名看登记项原文）";
    el("tb-inds").innerHTML = (j.items || []).map(function (x) {
      var cls = x.benchmark_source === "实测校准" ? "tag cal" : "tag gen";
      return "<tr>" +
        '<td><span class="law-link" data-ind="' + esc(x.industry_id) + '">' + esc(x.label) + "</span></td>" +
        '<td class="muted">' + esc(x.industry_id) + "</td>" +
        '<td><span class="' + cls + '">' + esc(x.benchmark_source) + "</span></td>" +
        '<td class="num">' + esc(x.indicator_count) + "</td>" +
        "<td>" + rangeCell(x.indicators) + "</td>" +
        "</tr>";
    }).join("") || '<tr><td colspan="5" class="muted">（无匹配行业）</td></tr>';
  }

  async function loadGeneric() {
    var g;
    try { g = await api("GET", API + "/industry-indicators/generic"); }
    catch (e) { el("tb-gen").innerHTML = '<tr><td colspan="4" class="muted">加载失败：' + esc(e.message) + "</td></tr>"; return; }
    el("gen-note").textContent = g.source + "；" + (g.note || "");
    el("tb-gen").innerHTML = (g.indicators || []).map(function (i) {
      var u = i.unit || "";
      return "<tr><td>" + esc(i.label) + '</td><td class="num">' + fmt(i.low, u) +
        '</td><td class="num">' + fmt(i.high, u) + "</td><td>" + esc(u || "比值") + "</td></tr>";
    }).join("");
  }

  async function openIndustry(iid) {
    var d;
    try { d = await api("GET", API + "/industry-indicators/" + encodeURIComponent(iid)); }
    catch (e) { alertBox("err", "详情加载失败：" + e.message); return; }
    el("dlg-title").textContent = d.label + "（" + d.industry_id + "）";
    var head = '<div class="muted" style="margin-bottom:10px">基准来源：' + esc(d.benchmark_source) +
      "；解析：" + esc(d.resolve_source) + "<br>口径：" + esc(d.caution) + "</div>";
    var inds = (d.indicators || []).map(function (i) {
      var u = i.unit || "";
      return "<tr><td>" + esc(i.label) + '</td><td class="num">' + fmt(i.low, u) +
        '</td><td class="num">' + fmt(i.high, u) + "</td></tr>";
    }).join("");
    var raw = esc(JSON.stringify(d.raw || {}, null, 2));
    el("dlg-body").innerHTML = head +
      '<table class="grid"><thead><tr><th>指标</th><th>下沿</th><th>上沿</th></tr></thead><tbody>' +
      (inds || '<tr><td colspan="3" class="muted">（无区间）</td></tr>') + "</tbody></table>" +
      '<h4 style="margin:14px 0 6px;font-size:13px">登记项原文（config/industry_params.json）</h4>' +
      '<pre class="plain">' + raw + "</pre>";
    el("dlg").showModal();
  }

  function bind() {
    el("btn-search").onclick = loadList;
    el("btn-reset").onclick = function () { el("q").value = ""; loadList(); };
    el("q").addEventListener("keydown", function (e) { if (e.key === "Enter") { loadList(); } });
    el("dlg-close").onclick = function () { el("dlg").close(); };
    document.addEventListener("click", function (ev) {
      var t = ev.target.closest ? ev.target.closest("[data-ind]") : null;
      if (t) { openIndustry(t.getAttribute("data-ind")); }
    });
  }

  (async function init() {
    bind();
    await loadMeta();
    await loadStats();
    await loadList();
    await loadGeneric();
  })();
})();
