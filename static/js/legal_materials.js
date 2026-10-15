/* 案例 · 解读 · 问答 页（步骤 22）—— 原生 JS、无框架、无构建。
 *
 * 约定：
 *   · **前端不硬编码任何条数** —— 类型分布（`by_kind`）由后端给（且与当前筛选一致）。
 *   · **不硬编码任何材料内容/条文**。
 *   · 粒度如实：材料与法规的关联**只到法规级**，页面上明确标注，**不得**说成"适用某条款"。
 *   · 无权限 403 如实展示。
 */
(function () {
  "use strict";

  var API = "/api/v1";
  var PAGE = 1, SIZE = 20, LAST = null, KIND = "";

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
    return '<span class="tag ' + esc(cls || "") + '">' + esc(text) + "</span>";
  }
  function kpi(n, t, on) {
    return '<div class="kpi' + (on ? " on" : "") + '" data-kind="' + esc(t === "全部" ? "" : t) + '">' +
      '<div class="n">' + esc(n) + '</div><div class="t">' + esc(t) + "</div></div>";
  }

  async function loadStats() {
    var s;
    try { s = await api("GET", API + "/legal-materials/stats"); }
    catch (e) { el("kpis").innerHTML = '<div class="muted">统计加载失败：' + esc(e.message) + "</div>"; return; }
    el("src-note").textContent = "（来源：" + (s.source || "") + "）";
    el("note").innerHTML = "关联口径：材料与法规的关联**只到法规级**（由官方摘要里的**显式引用**确证：" +
      "书名号引用 / 带法规后缀全名），**不做**关键词或相似度匹配；" +
      "未匹配到法规的材料 <b>照样保留</b>（" + (s.unlinked || 0) + " 条），不丢数据。";
    var bk = s.by_kind || {};
    var H = kpi(s.total, "全部", !KIND);
    Object.keys(bk).forEach(function (k) {
      H += kpi(bk[k], k, KIND === k);
    });
    H += kpi(s.linked_to_law, "已关联法规", false);
    H += kpi(s.unlinked, "未关联", false);
    el("kpis").innerHTML = H;
    var sel = el("kind-sel");
    sel.innerHTML = '<option value="">全部类型</option>' + Object.keys(bk).map(function (k) {
      return '<option value="' + esc(k) + '"' + (KIND === k ? " selected" : "") + ">" + esc(k) +
        "（" + bk[k] + "）</option>";
    }).join("");
  }

  async function loadList() {
    var url = API + "/legal-materials?page=" + PAGE + "&page_size=" + SIZE +
      "&kind=" + encodeURIComponent(el("kind-sel").value) +
      "&q=" + encodeURIComponent(el("q").value.trim()) +
      "&linked=" + encodeURIComponent(el("linked-sel").value);
    var j;
    try { j = await api("GET", url); }
    catch (e) {
      el("tb").innerHTML = '<tr><td colspan="4" class="muted">检索失败：' + esc(e.message) + "</td></tr>";
      return;
    }
    LAST = j;
    el("hint").textContent = "共 " + j.total + " 条";
    el("pg-info").textContent = "第 " + j.page + " / " + (j.pages || 1) + " 页";
    el("pg-prev").disabled = j.page <= 1;
    el("pg-next").disabled = j.page >= (j.pages || 1);
    el("tb").innerHTML = (j.items || []).map(function (m) {
      var laws = (m.matched_refs || []).map(function (h) {
        return tag(h.matched_ref || h.law_code, "") + " <span class=\"muted\">" + esc(h.matched_by || "") + "</span>";
      }).join("<br>");
      return "<tr>" +
        "<td>" + tag(m.kind || "", m.kind || "") + "</td>" +
        '<td><span class="law-link" data-mat="' + esc(m.material_id) + '">' + esc(m.title) + "</span>" +
        (m.snippet ? '<div class="muted" style="margin-top:4px">' + esc(String(m.snippet).slice(0, 160))
          + (String(m.snippet).length > 160 ? "…" : "") + "</div>" : "") +
        (m.url ? '<div style="margin-top:4px"><a class="law-link" href="' + esc(m.url)
          + '" target="_blank" rel="noopener">官方原文</a></div>' : "") + "</td>" +
        '<td class="muted">' + esc(m.published_at || "—") + "</td>" +
        "<td>" + (laws || '<span class="muted">未关联法规</span>') + "</td>" +
        "</tr>";
    }).join("") || '<tr><td colspan="4" class="muted">（无匹配材料）</td></tr>';
  }

  async function openMaterial(mid) {
    var d;
    try { d = await api("GET", API + "/legal-materials/" + encodeURIComponent(mid)); }
    catch (e) { alertBox("err", "详情加载失败：" + e.message); return; }
    el("dlg-title").textContent = d.title || "（无标题）";
    var H = '<div class="muted" style="line-height:1.8">类型：' + esc(d.kind || "—") +
      "　发布日期：" + esc(d.published_at || "—") +
      "<br>发布机关：" + esc(d.publisher || "—") +
      (d.doc_no ? "　文号：" + esc(d.doc_no) : "") +
      (d.url ? '<br>原文：<a class="law-link" href="' + esc(d.url) + '" target="_blank" rel="noopener">'
        + esc(d.url) + "</a>" : "") + "</div>";
    H += '<div class="sec-title">摘要原文</div><pre class="plain">' + esc(d.snippet || "（无摘要）") + "</pre>";
    var laws = d.related_laws || [];
    H += '<div class="sec-title">显式引用的法规（' + laws.length + "）</div>";
    if (laws.length) {
      H += '<table class="grid"><thead><tr><th style="width:240px">法规</th><th style="width:110px">匹配方式</th>' +
        "<th>引用该法的规则（经已确证条款反查）</th></tr></thead><tbody>" +
        laws.map(function (l) {
          var ru = (l.rules_using || []).map(function (r) {
            return tag(r.rule_id, "") + '<div class="muted" style="font-size:12px">' + esc(r.provision_id || "")
              + " " + esc(r.article || "") + "</div>";
          }).join("");
          return "<tr><td>" + esc(l.law_name || l.law_code) + "</td>" +
            '<td class="muted">' + esc(l.matched_by || "—") + "</td>" +
            "<td>" + (ru || '<span class="muted">（暂无规则经已确证条款引用该法）</span>') + "</td></tr>";
        }).join("") + "</tbody></table>";
    } else {
      H += '<div class="msg warn">该材料**未显式引用任何法规**（官方摘要里没有书名号引用或完整法名）' +
        "⇒ 如实为空，<b>不能</b>据此推断它涉及某部法。</div>";
    }
    H += '<div class="msg info" style="margin-top:10px">' + esc(d.granularity_note || "") + "</div>";
    el("dlg-body").innerHTML = H;
    el("dlg").showModal();
  }

  function bind() {
    el("btn-search").onclick = function () { PAGE = 1; loadList(); };
    el("btn-reset").onclick = function () {
      el("q").value = ""; el("kind-sel").value = ""; el("linked-sel").value = "";
      PAGE = 1; KIND = ""; loadStats(); loadList();
    };
    el("q").addEventListener("keydown", function (e) {
      if (e.key === "Enter") { PAGE = 1; loadList(); }
    });
    el("kind-sel").addEventListener("change", function () {
      PAGE = 1; KIND = el("kind-sel").value; loadStats(); loadList();
    });
    el("linked-sel").addEventListener("change", function () { PAGE = 1; loadList(); });
    el("pg-prev").onclick = function () { if (PAGE > 1) { PAGE--; loadList(); } };
    el("pg-next").onclick = function () { if (LAST && PAGE < (LAST.pages || 1)) { PAGE++; loadList(); } };
    el("dlg-close").onclick = function () { el("dlg").close(); };
    document.addEventListener("click", function (ev) {
      var t = ev.target.closest ? ev.target : null;
      if (!t) { return; }
      var k = t.closest("[data-kind]");
      if (k) {
        KIND = k.getAttribute("data-kind") || "";
        PAGE = 1; el("kind-sel").value = KIND; loadStats(); loadList(); return;
      }
      var m = t.closest("[data-mat]");
      if (m) { openMaterial(m.getAttribute("data-mat")); }
    });
  }

  (async function init() {
    bind();
    // 支持深链：/legal-materials?law_code=INVOICE-MEASURE&kind=案例
    var m = location.search.match(/[?&]kind=([^&]+)/);
    if (m) { KIND = decodeURIComponent(m[1]); }
    var lc = location.search.match(/[?&]law_code=([^&]+)/);
    await loadStats();
    if (lc) {
      var j2;
      try {
        j2 = await api("GET", API + "/legal-materials?law_code=" +
          encodeURIComponent(decodeURIComponent(lc[1])) + "&page=1&page_size=" + SIZE);
        LAST = j2;
        el("hint").textContent = "（按法规筛选：" + decodeURIComponent(lc[1]) + "，共 " + j2.total + " 条）";
        el("tb").innerHTML = (j2.items || []).map(function (x) {
          return "<tr><td>" + tag(x.kind || "", x.kind || "") + "</td>" +
            '<td><span class="law-link" data-mat="' + esc(x.material_id) + '">' + esc(x.title) + "</span></td>" +
            '<td class="muted">' + esc(x.published_at || "—") + "</td><td>"
            + (x.matched_refs || []).map(function (h) { return tag(h.matched_ref || "", ""); }).join(" ")
            + "</td></tr>";
        }).join("") || '<tr><td colspan="4" class="muted">（无）</td></tr>';
        return;
      } catch (e) {
        alertBox("err", "按法规筛选失败：" + e.message);
      }
    }
    await loadList();
  })();
})();
