/* AI 辅助分析（P2-3）前端逻辑 —— 原生 JS，无框架、无构建（沿用现有技术栈）。
 *
 * 约定：
 *   · CSRF / 401 由全局拦截器处理（security.js）。
 *   · 能力清单、免责声明、可用性**一律取后端** /api/v1/ai-assist/meta（不硬编码）。
 *   · 结果区**必须**展示"AI 辅助·不替代规则"标识与 `engine`（llm / rule_hint / unavailable），
 *     让使用者一眼看出"这是不是 AI 生成的"（不混淆、不冒充）。
 */
(function () {
  "use strict";

  var API = "/api/v1";
  var META = null;

  function el(id) { return document.getElementById(id); }
  function esc(s) {
    return String(s === null || s === undefined ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
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
  function engineTag(e) {
    if (e === "llm") { return '<span class="tag ai">AI 生成</span>'; }
    if (e === "rule_hint") { return '<span class="tag hint">规则侧线索（非 AI）</span>'; }
    return '<span class="tag no">未产出</span>';
  }

  var SAMPLE = {
    explain_finding: { finding: { title: "进销倒挂", level: "高",
                                  policy_ref: "《增值税暂行条例》第六条" } },
    suggest_materials: { findings: [{ title: "进销倒挂", level: "高" }] },
    draft_inquiry: { findings: [{ title: "进销倒挂", level: "高" }] },
    summarize_risks: { findings: [{ title: "进销倒挂", level: "高" },
                                  { title: "费用与收入不配比", level: "中" }] }
  };

  async function loadMeta() {
    try {
      META = await api("GET", API + "/ai-assist/meta");
      el("disclaimer").innerHTML = "⚠️ " + esc(META.disclaimer) +
        '<br><span class="muted">本页所有产出均带 advisory_only 标识，不替代规则引擎判定。</span>';
      var st = META.status || {};
      el("kpis").innerHTML =
        '<div class="kpi"><div class="n">' + (st.available ? "可用" : "不可用") +
          '</div><div class="t">AI 大模型</div></div>' +
        '<div class="kpi"><div class="n">' + esc(st.backend || "none") +
          '</div><div class="t">当前后端</div></div>' +
        '<div class="kpi"><div class="n">' + esc((META.capabilities || {}).total) +
          '</div><div class="t">辅助能力</div></div>';
      el("status-note").textContent = (st.reason || "") + " " + (st.note || "");
      var caps = (META.capabilities || {}).items || [];
      el("tb-caps").innerHTML = caps.map(function (c) {
        return "<tr><td>" + esc(c.label) + '</td><td class="muted">' + esc(c.code) + "</td>" +
          "<td>" + esc(c.desc) + "</td><td class=\"muted\">" + esc(c.input) + "</td></tr>";
      }).join("");
      var sel = el("code");
      sel.innerHTML = caps.map(function (c) {
        return '<option value="' + esc(c.code) + '">' + esc(c.label) + "</option>";
      }).join("");
      fillSample();
    } catch (e) {
      el("disclaimer").outerHTML = '<div class="banner err">字典加载失败：' + esc(e.message) + "</div>";
    }
  }

  function fillSample() {
    var code = el("code").value;
    el("payload").value = JSON.stringify(SAMPLE[code] || {}, null, 2);
    var c = ((META && META.capabilities && META.capabilities.items) || [])
      .filter(function (x) { return x.code === code; })[0];
    el("hint").textContent = c ? ("输入：" + c.input) : "";
  }

  async function run() {
    var code = el("code").value;
    var raw = el("payload").value.trim();
    var body = {};
    if (raw) {
      try { body = JSON.parse(raw); }
      catch (e) { el("result").innerHTML = '<div class="banner err">JSON 解析失败：' + esc(e.message) + "</div>"; return; }
    }
    el("result").innerHTML = '<div class="muted">生成中…</div>';
    var r;
    try { r = await api("POST", API + "/ai-assist/" + encodeURIComponent(code), body); }
    catch (e) { el("result").innerHTML = '<div class="banner err">生成失败：' + esc(e.message) + "</div>"; return; }
    var head = engineTag(r.engine) +
      ' <span class="tag ' + (r.replaces_rules ? "no" : "ok") + '">不替代规则：' +
      (r.replaces_rules ? "否（异常）" : "是") + "</span>" +
      ' <span class="muted">advisory_only=' + esc(String(r.advisory_only)) + "</span>";
    var why = r.reason ? '<div class="muted" style="margin:8px 0">' + esc(r.reason) + "</div>" : "";
    var san = (r.sanitized_terms && r.sanitized_terms.length)
      ? '<div class="banner">已改写定性用语：' + esc(r.sanitized_terms.join("、")) + "</div>" : "";
    var bodyHtml = r.output
      ? '<pre class="plain">' + esc(JSON.stringify(r.output, null, 2)) + "</pre>"
      : '<div class="muted">（未产出内容）</div>';
    el("result").innerHTML = '<div class="banner">' + esc(r.disclaimer) + "</div>" +
      '<div style="margin-bottom:8px">' + head + "</div>" + why + san + bodyHtml;
  }

  function bind() {
    el("code").addEventListener("change", fillSample);
    el("btn-sample").onclick = fillSample;
    el("btn-run").onclick = run;
  }

  (async function init() {
    bind();
    await loadMeta();
  })();
})();
