/* 法规专题页（步骤 22）—— 原生 JS、无框架、无构建（沿用现有技术栈）。
 *
 * 约定（与 legal_library.js 同）：
 *   · CSRF / 401 由全局拦截器处理（security.js）。
 *   · **前端不硬编码任何条数或条文** —— 一律来自后端（后端又来自数据文件/引擎）。
 *   · 无权限时后端 403，前端如实展示（不静默降级）。
 *   · 缺口如实：专题**尚无已确证条款**时，材料区显示后端的 `reason`，
 *     不得渲染成"无相关材料"（两件事不同）。
 */
(function () {
  "use strict";

  var API = "/api/v1";
  var CUR = null;              // 当前专题 id
  var LAST_DOCS = null;

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
  function tag(text, cls) {
    return '<span class="tag ' + (cls || "") + '">' + esc(text) + "</span>";
  }
  function kpi(n, t) {
    return '<div class="kpi"><div class="n">' + esc(n) + '</div><div class="t">' + esc(t) + "</div></div>";
  }

  async function loadTopics() {
    var url = API + "/legal-topics?batch=" + encodeURIComponent(el("batch-sel").value) +
      "&q=" + encodeURIComponent(el("topic-q").value.trim());
    var j;
    try { j = await api("GET", url); }
    catch (e) {
      el("topic-list").innerHTML = '<div class="msg err">加载失败：' + esc(e.message) + "</div>";
      return;
    }
    if (!j.available) {
      el("topic-list").innerHTML = '<div class="msg warn">' + esc(j.note || "专题索引不可用") + "</div>";
      return;
    }
    el("topic-hint").textContent = "（共 " + j.total + " 个）";
    var ht = j.items.map(function (t) {
      var bcls = t.batch === "P0" ? "p0" : (t.batch === "P1" ? "p1" : "p2");
      return '<div class="topic-item' + (t.id === CUR ? " on" : "") + '" data-topic="' + esc(t.id) + '">' +
        '<div class="tn">' + esc(t.name) + " " + tag(t.id, "") + " " + tag(t.batch, bcls) + "</div>" +
        '<div class="tm">法规 ' + t.documents_total + "（核心 " + t.documents_core + "）· 条款 "
        + t.provisions_total + " · 规则 " + t.rules_total + " · 材料 " + t.materials_total + "</div>" +
        "</div>";
    }).join("");
    el("topic-list").innerHTML = ht || '<div class="muted">（无匹配专题）</div>';
  }

  function docsTable(j) {
    var rows = (j.items || []).map(function (x) {
      var bodyTag = x.has_body_in_library
        ? tag("正文已入库", "has-body") : tag("正文未入库", "no-body");
      return "<tr>" +
        '<td><span class="law-link" data-doc-idx="' + esc(x.index) + '">' + esc(x.title) + "</span>" +
        (x.doc_no ? '<div class="muted">' + esc(x.doc_no) + "</div>" : "") + "</td>" +
        "<td>" + esc(x.kind || "—") + "</td>" +
        '<td class="muted">' + esc(x.published_at || "—") + "</td>" +
        '<td class="muted">' + esc(x.issuer || "—") + "</td>" +
        "<td>" + bodyTag + "</td>" +
        '<td>' + (x.url ? '<a class="law-link" href="' + esc(x.url) + '" target="_blank" rel="noopener">官方原文</a>' : "—") + "</td>" +
        "</tr>";
    }).join("");
    return '<table class="grid"><thead><tr><th>法规标题</th><th style="width:130px">类型</th>' +
      '<th style="width:100px">发布日期</th><th style="width:150px">发文机关</th>' +
      '<th style="width:110px">正文状态</th><th style="width:90px">原文</th></tr></thead>' +
      "<tbody>" + (rows || '<tr><td colspan="6" class="muted">（无匹配条目）</td></tr>') + "</tbody></table>" +
      '<div class="toolbar" style="margin-top:10px">' +
      '<button class="btn ghost sm" id="d-prev">上一页</button>' +
      '<span class="muted">第 ' + j.page + " / " + (j.pages || 1) + " 页（共 " + j.total + " 条）</span>" +
      '<button class="btn ghost sm" id="d-next">下一页</button></div>' +
      '<div class="muted" style="margin-top:6px;font-size:12px">' + esc(j.note || "") + "</div>";
  }

  async function openTopic(tid) {
    CUR = tid;
    loadTopics();
    el("detail").innerHTML = '<div class="card"><div class="body muted">加载中…</div></div>';
    var d, docs, rules, provs, mats;
    try {
      d = await api("GET", API + "/legal-topics/" + encodeURIComponent(tid));
    } catch (e) {
      el("detail").innerHTML = '<div class="card"><div class="body"><div class="msg err">'
        + esc(e.message) + "</div></div></div>";
      return;
    }
    try {
      docs = await api("GET", API + "/legal-topics/" + encodeURIComponent(tid) +
        "/documents?page=1&page_size=20");
      rules = await api("GET", API + "/legal-topics/" + encodeURIComponent(tid) + "/rules");
      provs = await api("GET", API + "/legal-topics/" + encodeURIComponent(tid) + "/provisions");
      mats = await api("GET", API + "/legal-topics/" + encodeURIComponent(tid) + "/materials?limit=20");
    } catch (e) {
      el("detail").innerHTML = '<div class="card"><div class="body"><div class="msg err">明细加载失败：'
        + esc(e.message) + "</div></div></div>";
      return;
    }
    LAST_DOCS = docs;

    var g = d.documents_by_group || {};
    var kindSel = Object.keys(d.documents_by_kind || {}).map(function (k) {
      return '<option value="' + esc(k) + '">' + esc(k) + "（" + d.documents_by_kind[k] + "）</option>";
    }).join("");

    var H = "";
    H += '<div class="card"><h3>' + esc(d.name) + " " + tag(d.id, "") + " " + tag(d.batch, "p0") +
      " " + tag(d.status || "", "") + '<span class="muted">｜' + esc(d.batch) + " 批次</span></h3>" +
      '<div class="body"><div class="kpis">' +
      kpi(d.documents_total, "法规/文件（清单）") +
      kpi(d.documents_core, "其中核心法规") +
      kpi(d.provisions_total, "已核实条款") +
      kpi(d.rules_total, "关联规则") +
      kpi(d.materials_total, "相关官方材料") +
      "</div>" +
      '<div class="muted" style="margin-top:10px;line-height:1.7">覆盖范围：' + esc(d.scope || "—") + "</div>" +
      '<div class="muted" style="margin-top:6px;line-height:1.7">核心法规（' + (d.core_titles || []).length + "）：" +
      esc((d.core_titles || []).join("、")) + "</div>" +
      '<div class="muted" style="margin-top:6px;line-height:1.7">分组统计：' +
      esc(JSON.stringify(g)) + "</div>" +
      '<div class="muted" style="margin-top:6px;font-size:12px">清单口径：按专题核心法登记 + 清单筛选词命中目录' +
      "（含相关外围文件与解读/问答/案例）；**不代表全部现行有效**。</div>" +
      "</div></div>";

    H += '<div class="card"><h3>法规清单 <span class="muted">（可按类型筛选；点标题看详情与关系链）</span></h3>' +
      '<div class="body"><div class="toolbar">' +
      '<select id="kind-sel"><option value="">全部类型</option>' + kindSel + "</select>" +
      '<input type="text" id="doc-q" placeholder="标题/文号关键词">' +
      '<button class="btn sm" id="btn-doc-search">筛选</button></div>' +
      '<div id="docs-box">' + docsTable(docs) + "</div></div></div>";

    var rrows = (rules.items || []).map(function (r) {
      if (!r.found) {
        return '<tr><td>' + esc(r.rule_id) + '</td><td colspan="4" class="muted">'
          + esc(r.note || "") + "</td></tr>";
      }
      return "<tr>" +
        '<td><span class="law-link" data-rule="' + esc(r.rule_id) + '">' + esc(r.rule_id) + "</span></td>" +
        "<td>" + esc(r.name || "") + "</td>" +
        '<td class="muted">' + esc(r.layer || "—") + "</td>" +
        '<td class="muted">' + esc((r.taxes || []).join("、") || "—") + "</td>" +
        '<td>' + r.legal_provisions_n + " 条已确证" +
        (r.unresolved_n ? ' <span class="muted">（' + r.unresolved_n + " 条未确证）</span>" : "") + "</td>" +
        "</tr>";
    }).join("");
    H += '<div class="card"><h3>关联规则 <span class="muted">（' + rules.total + " 条）</span></h3>" +
      '<div class="body"><table class="grid"><thead><tr><th style="width:130px">规则号</th><th>名称</th>' +
      '<th style="width:120px">层级</th><th style="width:130px">税种</th><th style="width:170px">法规条款</th>' +
      "</tr></thead><tbody>" + (rrows || '<tr><td colspan="5" class="muted">（该专题暂无关联规则）</td></tr>') +
      "</tbody></table></div></div>";

    var prows = (provs.items || []).map(function (p) {
      return "<tr>" +
        '<td><span class="law-link" data-prov="' + esc(p.provision_id) + '">' + esc(p.provision_id) + "</span></td>" +
        "<td>" + esc(p.law || "—") + "</td>" +
        '<td class="muted">' + esc(p.article || "—") + "</td>" +
        '<td>' + (p.has_content ? esc(String(p.content).slice(0, 110)) + (String(p.content).length > 110 ? "…" : "")
          : '<span class="muted">正文未入库</span>') + "</td>" +
        '<td class="muted">' + esc((p.related_rules || []).join("、") || "—") + "</td>" +
        "</tr>";
    }).join("");
    H += '<div class="card"><h3>已核实条款 <span class="muted">（' + provs.total + " 条；点条款 ID 看正文与引用规则）</span></h3>" +
      '<div class="body"><table class="grid"><thead><tr><th style="width:210px">条款 ID</th><th style="width:200px">法规</th>' +
      '<th style="width:100px">条文</th><th>条款正文</th><th style="width:150px">引用该条款的规则</th>' +
      "</tr></thead><tbody>" + (prows || '<tr><td colspan="5" class="muted">（该专题暂无已核实条款）</td></tr>') +
      "</tbody></table></div></div>";

    // 材料：按法分列；无锚点时显示后端的 reason（**不等于"没有相关材料"**）
    var mbody;
    if (!mats.total && mats.reason) {
      mbody = '<div class="msg warn">' + esc(mats.reason) + "</div>";
    } else {
      mbody = '<table class="grid"><thead><tr><th style="width:280px">法规</th><th style="width:90px">材料数</th>' +
        "<th>示例（类型 · 标题 · 日期）</th></tr></thead><tbody>" +
        (mats.items || []).map(function (x) {
          var sm = (x.samples || []).map(function (s) {
            return '<div>' + tag(s.kind, "") + " " +
              (s.url ? '<a class="law-link" href="' + esc(s.url) + '" target="_blank" rel="noopener">'
                + esc(s.title) + "</a>" : esc(s.title)) +
              ' <span class="muted">' + esc(s.published_at || "") + "</span></div>";
          }).join("");
          return "<tr><td>" + esc(x.law_name || x.law_code) + "</td><td>" + x.count + "</td>" +
            "<td>" + (sm || '<span class="muted">—</span>') + "</td></tr>";
        }).join("") + "</tbody></table>" +
        '<div class="muted" style="margin-top:8px;font-size:12px">' + esc(mats.note || "") + "</div>";
    }
    H += '<div class="card"><h3>相关官方材料 <span class="muted">（按法分列，粒度=法规级）</span></h3>' +
      '<div class="body">' + mbody + "</div></div>";

    el("detail").innerHTML = H;
  }

  async function openDoc(idx) {
    var d;
    try { d = await api("GET", API + "/legal-catalog/item?index=" + encodeURIComponent(idx)); }
    catch (e) { alertBox("err", "详情加载失败：" + e.message); return; }
    el("dlg-title").textContent = d.title || "（无标题）";
    var H = '<div class="muted" style="line-height:1.8">' +
      "文号：" + esc(d.doc_no || "—") + "<br>类型：" + esc(d.kind || "—") +
      "<br>发文机关：" + esc(d.issuer || "—") + "<br>发布日期：" + esc(d.published_at || "—") +
      "<br>来源：" + esc(d.source || "—") +
      (d.url ? '<br>原文：<a class="law-link" href="' + esc(d.url) + '" target="_blank" rel="noopener">'
        + esc(d.url) + "</a>" : "") + "</div>";
    H += '<div class="msg ' + (d.has_body_in_library ? "info" : "warn") + '" style="margin-top:10px">'
      + esc(d.body_note || "") + "</div>";
    var rl = d.relations || {};
    if (rl.total) {
      H += '<div class="sec-title">法规关系（共 ' + rl.total + " 条）</div>";
      H += '<table class="grid"><thead><tr><th style="width:110px">关系</th><th>目标</th>' +
        '<th style="width:100px">日期</th><th>证据原文</th></tr></thead><tbody>' +
        rl.items.map(function (x) {
          return "<tr><td>" + esc(x.relation_cn || x.relation) + "</td><td>" + esc(x.target || "—") +
            "</td><td class=\"muted\">" + esc(x.date || "—") + "</td>" +
            '<td class="muted">' + esc(x.evidence || "") + "</td></tr>";
        }).join("") + "</tbody></table>";
    } else {
      H += '<div class="msg warn" style="margin-top:10px">' + esc(rl.reason || "未查到关系记录") + "</div>";
    }
    el("dlg-body").innerHTML = H;
    el("dlg").showModal();
  }

  async function openRule(rid) {
    var d;
    try { d = await api("GET", API + "/rules/" + encodeURIComponent(rid)); }
    catch (e) { alertBox("err", "规则详情加载失败：" + e.message); return; }
    el("dlg-title").textContent = rid + " · " + (d.name || "");
    var H = '<div class="muted" style="line-height:1.8">层级：' + esc(d.layer || "—") +
      "　税种：" + esc((d.taxes || []).join("、") || "—") +
      "<br>版本：" + esc(d.version || "未登记") + "　来源：" + esc(d.source_cn || "") +
      "<br>严重度：" + esc(d.severity || "—") +
      "<br>正当理由：" + esc((d.justifications || []).join("；") || "—") + "</div>";
    var lp = d.legal_provisions || [];
    H += '<div class="sec-title">已确证法规条款（' + lp.length + " 条，含条款原文）</div>";
    H += lp.length ? lp.map(function (p) {
      return '<div style="padding:8px 0;border-bottom:1px solid #f1f5f9">' +
        "<div><b>" + esc(p.provision_id || "") + "</b> " + esc(p.law || "") + " " + esc(p.article || "") +
        (p.verified ? " " + tag("已确证", "has-body") : "") + "</div>" +
        '<pre class="plain">' + esc(p.content || "（正文库无原文）") + "</pre></div>";
    }).join("") : '<div class="msg warn">该规则**无可确证条款**（关联表中未落到具体条款）——如实为空。</div>';
    var refs = d.legal_basis_ref || [];
    H += '<div class="sec-title">规则作者登记的法规依据（legal_basis_ref，原样）</div>';
    H += refs.length ? refs.map(function (x) {
      return '<div>' + esc(x.law || "（未解析出法名）") + (x.article ? " " + esc(x.article) : "") +
        (x.placeholder ? " " + tag("占位（未入库）", "no-body") : "") +
        '<div class="muted">' + esc(x.raw || "") + "</div></div>";
    }).join("") : '<div class="muted">（无登记依据）</div>';
    el("dlg-body").innerHTML = H;
    el("dlg").showModal();
  }

  async function openProvision(pid) {
    var d;
    try { d = await api("GET", API + "/legal-provisions/" + encodeURIComponent(pid)); }
    catch (e) { alertBox("err", "条款详情加载失败：" + e.message); return; }
    el("dlg-title").textContent = pid + " · " + (d.law || "") + " " + (d.article || "");
    el("dlg-body").innerHTML =
      '<div class="muted" style="line-height:1.8">类型：' + esc(d.kind || "—") +
      "　专题标签：" + esc((d.topic_tags || []).join("、") || "—") +
      "<br>正文来源：" + esc(d.content_source || "") + "</div>" +
      '<div class="sec-title">条款正文</div>' +
      '<pre class="plain">' + esc(d.content || "（正文库未收录该条，不编造）") + "</pre>" +
      '<div class="sec-title">引用该条款的规则（' + (d.related_rules || []).length + " 条）</div>" +
      ((d.related_rules || []).map(function (r) {
        return "<div>" + tag(r, "") + "</div>";
      }).join("") || '<div class="muted">（无规则引用该条款）</div>');
    el("dlg").showModal();
  }

  async function filterDocs() {
    if (!CUR) { return; }
    var kind = el("kind-sel").value, q = el("doc-q").value.trim();
    var j;
    try {
      j = await api("GET", API + "/legal-topics/" + encodeURIComponent(CUR) + "/documents?page=1&page_size=20"
        + "&kind=" + encodeURIComponent(kind) + "&q=" + encodeURIComponent(q));
    } catch (e) { alertBox("err", "筛选失败：" + e.message); return; }
    LAST_DOCS = j;
    el("docs-box").innerHTML = docsTable(j);
    bindDocPager();
  }

  async function pageDocs(delta) {
    if (!CUR || !LAST_DOCS) { return; }
    var p = (LAST_DOCS.page || 1) + delta;
    if (p < 1 || p > (LAST_DOCS.pages || 1)) { return; }
    var j;
    try {
      j = await api("GET", API + "/legal-topics/" + encodeURIComponent(CUR) + "/documents?page=" + p +
        "&page_size=20&kind=" + encodeURIComponent(el("kind-sel").value) +
        "&q=" + encodeURIComponent(el("doc-q").value.trim()));
    } catch (e) { alertBox("err", "翻页失败：" + e.message); return; }
    LAST_DOCS = j;
    el("docs-box").innerHTML = docsTable(j);
    bindDocPager();
  }

  function bindDocPager() {
    var a = el("d-prev"), b = el("d-next");
    if (a) { a.onclick = function () { pageDocs(-1); }; }
    if (b) { b.onclick = function () { pageDocs(1); }; }
  }

  function bind() {
    el("batch-sel").onchange = loadTopics;
    el("topic-q").addEventListener("keydown", function (e) {
      if (e.key === "Enter") { loadTopics(); }
    });
    el("dlg-close").onclick = function () { el("dlg").close(); };
    document.addEventListener("click", function (ev) {
      var t = ev.target.closest ? ev.target : null;
      if (!t) { return; }
      var a = t.closest("[data-topic]");
      if (a) { openTopic(a.getAttribute("data-topic")); return; }
      var b = t.closest("[data-doc-idx]");
      if (b) { openDoc(b.getAttribute("data-doc-idx")); return; }
      var c = t.closest("[data-rule]");
      if (c) { openRule(c.getAttribute("data-rule")); return; }
      var d = t.closest("[data-prov]");
      if (d) { openProvision(d.getAttribute("data-prov")); return; }
      if (t.closest("#btn-doc-search")) { filterDocs(); }
    });
  }

  (async function init() {
    bind();
    await loadTopics();
    // 支持深链：/legal-topics?topic=TOPIC-001
    var m = location.search.match(/[?&]topic=([^&]+)/);
    if (m) { openTopic(decodeURIComponent(m[1])); }
  })();
})();
