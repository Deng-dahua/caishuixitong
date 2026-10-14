/* 规则版本管理（P1-6）前端逻辑 —— 原生 JS，无框架、无构建（沿用现有技术栈）。
 *
 * 约定：
 *   · CSRF 由全局 fetch 拦截器自动附加（security.js）；401 由它跳 /login。
 *   · 版本号规则、当前版本、配置版本**一律取后端**（不硬编码）。
 *   · 写操作需要 `ruleversion.manage`；无权限后端 403，前端如实展示（不静默降级）。
 */
(function () {
  "use strict";

  var API = "/api/v1";
  var META = null, ROWS = [];

  function el(id) { return document.getElementById(id); }
  function esc(s) {
    return String(s === null || s === undefined ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function alertBox(kind, text) {
    el("alert").innerHTML = text ? '<div class="msg ' + kind + '">' + esc(text) + "</div>" : "";
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

  function srcTag(x) {
    var cls = x.source === "ledger" ? "led" : "cfg";
    return '<span class="tag ' + cls + '">' + (x.source === "ledger" ? "运行期事件" : "出厂历史") + "</span>";
  }

  async function loadMeta() {
    META = await api("GET", API + "/rule-versions/meta");
    el("kpis").innerHTML =
      "<div><b>" + esc(META.current_version || "未登记") + "</b>当前生效版本</div>"
      + "<div><b>" + esc(META.config_version || "未登记") + "</b>配置基线版本</div>"
      + "<div><b>" + esc(META.registered_rule_count) + "</b>已登记规则</div>";
    el("meta-note").textContent = META.note || "";
    el("v-hint").innerHTML = "版本号规则：<code>" + esc(META.version_pattern) + "</code>"
      + "　存储：" + esc(META.storage || "");
  }

  async function loadList() {
    var j;
    try { j = await api("GET", API + "/rule-versions"); }
    catch (e) {
      el("tb").innerHTML = '<tr><td colspan="8" class="muted">加载失败：' + esc(e.message) + "</td></tr>";
      return;
    }
    ROWS = j.items || [];
    el("tb").innerHTML = ROWS.map(function (x) {
      return "<tr>"
        + "<td>" + (x.is_current
            ? '<span class="tag cur">' + esc(x.version) + "（当前）</span>"
            : esc(x.version)) + "</td>"
        + "<td>" + srcTag(x) + "</td>"
        + "<td>" + esc(x.action || "—") + "</td>"
        + "<td class='muted'>" + esc(x.date || "—") + "</td>"
        + "<td class='muted'>" + esc(x.actor || "—") + "</td>"
        + "<td>" + (x.has_snapshot ? '<span class="tag">有</span>'
                                   : '<span class="muted">无</span>') + "</td>"
        + "<td class='muted'>" + esc(x.note || "") + "</td>"
        + '<td><button class="btn ghost" data-use="' + esc(x.version) + '">填入表单</button></td>'
        + "</tr>";
    }).join("") || '<tr><td colspan="8" class="muted">（无版本记录）</td></tr>';
    if (ROWS.length) {
      el("d-from").value = ROWS.length > 1 ? ROWS[1].version : ROWS[0].version;
      el("d-to").value = ROWS[0].version;
    }
  }

  async function publish() {
    var v = (el("v-version").value || "").trim();
    if (!v) { alertBox("warn", "请填写版本号（格式 YYYY.NN）"); return; }
    try {
      var j = await api("POST", API + "/rule-versions/publish",
                        { version: v, note: (el("v-note").value || "").trim() });
      alertBox("ok", j.message || "已发布");
      await loadMeta(); await loadList();
    } catch (e) { alertBox("err", "发布失败：" + e.message); }
  }

  async function rollback() {
    var v = (el("v-version").value || "").trim();
    if (!v) { alertBox("warn", "请填写要回滚到的版本号"); return; }
    if (!window.confirm("确认回滚到版本「" + v + "」？\n（回滚会变更『当前生效版本』，并留痕）")) return;
    try {
      var j = await api("POST", API + "/rule-versions/rollback",
                        { version: v, note: (el("v-note").value || "").trim() });
      alertBox("ok", j.message || "已回滚");
      await loadMeta(); await loadList();
    } catch (e) { alertBox("err", "回滚失败：" + e.message); }
  }

  async function doDiff() {
    var a = (el("d-from").value || "").trim();
    var b = (el("d-to").value || "").trim();
    if (!a || !b) { alertBox("warn", "请填写两个版本号"); return; }
    var j;
    try { j = await api("GET", API + "/rule-versions/diff?from=" + encodeURIComponent(a)
                        + "&to=" + encodeURIComponent(b)); }
    catch (e) { alertBox("err", "比对失败：" + e.message); return; }
    if (!j.comparable) {
      el("d-hint").textContent = "";
      el("d-result").innerHTML = '<span style="color:#b45309">' + esc(j.reason || "无法比对") + "</span>";
      return;
    }
    var c = j.counts || {};
    el("d-hint").textContent = "规则数 " + c.from + " → " + c.to;
    el("d-result").innerHTML =
        "新增 " + c.added + " 条" + (j.added.length ? "：" + esc(j.added.join("、")) : "")
      + "<br>移除 " + c.removed + " 条" + (j.removed.length ? "：" + esc(j.removed.join("、")) : "")
      + "<br>版本变更 " + c.changed + " 条"
      + (j.changed.length ? "：" + esc(j.changed.slice(0, 20).map(function (x) {
          return x.rule_id + " " + x.from + "→" + x.to; }).join("；")) : "")
      + (j.truncated ? "<br><b>结果已截断（仅显示前 200 条）</b>" : "");
  }

  document.addEventListener("DOMContentLoaded", async function () {
    try {
      // R-4（2026-10-14）：原为 "/api/me"（后端不存在 ⇒ 404 被 .catch 静默吞掉）⇒ 改唯一权威路径
      var me = await api("GET", "/api/auth/me").catch(function () { return null; });
      if (me && me.username) { el("who").textContent = me.username; }
    } catch (e) { /* 未登录由全局 401 处理 */ }
    try { await loadMeta(); }
    catch (e) { alertBox("err", "字典加载失败：" + e.message); }
    await loadList();

    el("btn-refresh").onclick = loadList;
    el("btn-publish").onclick = publish;
    el("btn-rollback").onclick = rollback;
    el("btn-diff").onclick = doDiff;
    document.addEventListener("click", function (ev) {
      var t = ev.target;
      if (t && t.getAttribute && t.getAttribute("data-use")) {
        el("v-version").value = t.getAttribute("data-use");
      }
    });
  });
})();
