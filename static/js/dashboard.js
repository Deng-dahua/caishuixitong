/* 数据大屏（P2-5）前端逻辑 —— 原生 JS + 手写 SVG 图表，无框架、无构建、无 CDN（离线可用）。
 *
 * 约定：
 *   · CSRF / 401 由全局拦截器处理（security.js）。
 *   · 所有数字**一律取后端**，前端**不做任何统计运算**（只做条形长度/坐标换算）。
 *   · `payload_unavailable` 必须与 `0 条风险` 分开显示（两者含义不同）。
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
  function kpi(n, t, warn) {
    return '<div class="kpi' + (warn ? " warn" : "") + '"><div class="n">' + esc(n) +
      '</div><div class="t">' + esc(t) + "</div></div>";
  }
  function bars(pairs, maxv) {
    if (!pairs || !pairs.length) { return '<div class="muted">（暂无数据）</div>'; }
    var mx = maxv || Math.max.apply(null, pairs.map(function (x) { return x.count; })) || 1;
    return pairs.map(function (x) {
      var w = Math.max(2, Math.round(x.count / mx * 100));
      return '<div class="bar-row"><span class="lb" title="' + esc(x.key) + '">' + esc(x.key) +
        '</span><span class="bar"><i style="width:' + w + '%"></i></span>' +
        '<span class="vv">' + esc(x.count) + "</span></div>";
    }).join("");
  }
  function lineChart(days) {
    if (!days || !days.length) { return '<div class="muted">（暂无留痕）</div>'; }
    var W = 560, H = 150, PAD = 26;
    var mx = Math.max.apply(null, days.map(function (d) { return d.count; })) || 1;
    var step = days.length > 1 ? (W - PAD * 2) / (days.length - 1) : 0;
    var pts = days.map(function (d, i) {
      var x = PAD + i * step;
      var y = H - PAD - (d.count / mx) * (H - PAD * 2);
      return [Math.round(x * 100) / 100, Math.round(y * 100) / 100];
    });
    var path = pts.map(function (p, i) { return (i ? "L" : "M") + p[0] + " " + p[1]; }).join(" ");
    var dots = pts.map(function (p, i) {
      return '<circle class="pt" cx="' + p[0] + '" cy="' + p[1] + '" r="2.6"><title>' +
        esc(days[i].day) + "：" + esc(days[i].count) + "</title></circle>";
    }).join("");
    var x0 = days[0].day, x1 = days[days.length - 1].day;
    return '<svg viewBox="0 0 ' + W + " " + H + '" width="100%" height="150" role="img">' +
      '<line class="axis" x1="' + PAD + '" y1="' + (H - PAD) + '" x2="' + (W - PAD) +
        '" y2="' + (H - PAD) + '"></line>' +
      '<line class="axis" x1="' + PAD + '" y1="' + PAD + '" x2="' + PAD + '" y2="' +
        (H - PAD) + '"></line>' +
      '<text x="' + PAD + '" y="14">峰值 ' + esc(mx) + "</text>" +
      '<path class="ln" d="' + path + '"></path>' + dots +
      '<text x="' + PAD + '" y="' + (H - 8) + '">' + esc(x0) + "</text>" +
      '<text x="' + (W - PAD) + '" y="' + (H - 8) + '" text-anchor="end">' + esc(x1) + "</text>" +
      "</svg>";
  }

  async function loadAll() {
    var meta, ov, act;
    try {
      meta = await api("GET", API + "/dashboard/meta");
      ov = await api("GET", API + "/dashboard/overview");
      act = await api("GET", API + "/dashboard/activity?days=14");
    } catch (e) {
      el("alert").innerHTML = '<div class="msg err">加载失败：' + esc(e.message) + "</div>";
      return;
    }
    var P = ov.projects || {}, D = ov.documents || {}, T = ov.tasks || {}, R = ov.risks || {};
    el("scope-note").textContent = "（数据来自：" +
      (meta.sources || []).map(function (s) { return s.name; }).join(" / ") + "）";
    el("kpis").innerHTML =
      kpi(P.total, "稽查项目" + (P.capped ? "（已扫 " + P.scanned + "）" : "")) +
      kpi(D.total, "财税资料") +
      kpi(T.total, "分析任务") +
      kpi(R.payload_available, "可读风险载荷账套") +
      kpi(R.payload_unavailable, "载荷不可得账套（非 0 风险）", R.payload_unavailable > 0) +
      kpi(act.total, "近 14 天留痕（已扫）");

    var w = [];
    if (P.capped) { w.push('<div class="msg warn">项目数超出扫描上限（' + meta.caps.projects +
      "），大屏只汇总前 " + P.scanned + " 个 —— 此处<b>如实标注</b>，未抽样估算。</div>"); }
    if (act.capped) { w.push('<div class="msg warn">留痕已达扫描上限（' + meta.caps.activity +
      "），按日计数为<b>已扫样本</b>的计数。</div>"); }
    if (R.payload_unavailable > 0) { w.push('<div class="msg warn">' + R.payload_unavailable +
      " 个账套读不到风险载荷（一键分析未跑或产物缺失）⇒ 风险分布未含这些账套。" +
      (R.unavailable_reasons && R.unavailable_reasons.length
        ? "<br>原因示例：" + esc(R.unavailable_reasons[0]) : "") + "</div>"); }
    el("alert").innerHTML = w.join("");

    el("c-proj").innerHTML = bars(P.by_status);
    el("c-doc").innerHTML = bars(D.by_category);
    el("c-task").innerHTML = bars(T.by_status);
    el("c-risk").innerHTML = bars((R.by_level || []).map(function (x) {
      // ★ 2026-10-15：等级展示唯一出处 = constants.js::LEVEL_DISPLAY
      //   （后端 risk_levels.DISPLAY_LABELS 的 JS 侧镜像）；数据键仍是权威等级名。
      return { key: (typeof levelDisplayOf === 'function' ? levelDisplayOf(x.key) : x.key),
               count: x.count };
    }));
    el("c-tax").innerHTML = bars((R.by_tax || []).slice(0, 10));
    el("risk-scope").textContent = "（" + R.payload_available + " / " + R.scanned_companies + " 个账套）";
    el("act-scope").textContent = "（近 " + (act.days || []).length + " 天有留痕）";
    el("c-act").innerHTML = lineChart(act.days) +
      '<div class="muted" style="margin-top:8px">' + esc(act.note || "") + "</div>";

    el("pp-note").textContent = "（共 " + (ov.per_project || []).length + " 个项目）";
    el("tb-pp").innerHTML = (ov.per_project || []).map(function (x) {
      var risk = x.risk_available
        ? ('<span class="tag ok">' + esc(x.risk_total === null ? "—" : x.risk_total) + " 条</span>")
        : '<span class="tag no">载荷不可得</span>';
      return "<tr><td>" + esc(x.name) + '</td><td class="muted">' + esc(x.code) + "</td>" +
        "<td>" + esc(x.status_cn) + "</td><td>" + esc(x.industry || "—") + "</td>" +
        '<td class="num">' + esc(x.documents === null ? "—" : x.documents) + "</td>" +
        '<td class="num">' + esc(x.tasks === null ? "—" : x.tasks) + "</td>" +
        "<td>" + risk + "</td></tr>";
    }).join("") || '<tr><td colspan="7" class="muted">（暂无项目）</td></tr>';
  }

  loadAll();
})();
