/* 稽查项目管理（P0-1）前端逻辑 —— 原生 JS，无框架、无构建（沿用现有技术栈）。
 *
 * 约定（与既有前端一致，勿另立一套）：
 *   · CSRF 由全局 fetch 拦截器自动附加（`security.js`，经 `_read_html` 注入）；
 *     401 亦由它自动跳 `/login` ⇒ 本文件**不重复处理**。
 *   · 接口前缀 `/api/v1/projects`（新增端点专用；现有端点未改动）。
 *   · 状态/角色中文名**不在前端硬编码字典**，一律取后端 `/meta`
 *     —— 避免"前端一份、后端一份"的多头维护。
 */
(function () {
  "use strict";

  var API = "/api/v1/projects";
  var META = { statuses: [], roles: [], status_flow: {} };
  var state = { page: 1, page_size: 20, total: 0, pages: 0, items: [], editing: null, deleting: null };

  // ── 小工具 ──────────────────────────────────────────────────────────
  function $(id) { return document.getElementById(id); }
  function esc(s) {
    return String(s === null || s === undefined ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function statusLabel(v) {
    var hit = (META.statuses || []).filter(function (s) { return s.value === v; })[0];
    return hit ? hit.label : (v || "");
  }
  function roleLabel(v) {
    var hit = (META.roles || []).filter(function (r) { return r.value === v; })[0];
    return hit ? hit.label : (v || "");
  }
  function flash(text, kind) {
    var el = $("msg");
    el.innerHTML = text ? '<div class="msg ' + (kind || "ok") + '">' + esc(text) + "</div>" : "";
    if (text) { window.clearTimeout(flash._t); flash._t = window.setTimeout(function () { el.innerHTML = ""; }, 4000); }
  }
  function openModal(id) { $(id).hidden = false; }
  function closeModal(id) { $(id).hidden = true; }

  async function api(path, options) {
    var res = await fetch(path, options);
    var data = null;
    try { data = await res.json(); } catch (e) { data = null; }
    if (!res.ok) {
      var detail = (data && (data.detail || data.message)) || ("HTTP " + res.status);
      var err = new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
      err.status = res.status;
      throw err;
    }
    return data;
  }

  // ── 元数据（字典唯一来源 = 后端）────────────────────────────────────
  async function loadMeta() {
    META = await api(API + "/meta");
    var sel = $("f-status");
    META.statuses.forEach(function (s) {
      var o = document.createElement("option");
      o.value = s.value; o.textContent = s.label;
      sel.appendChild(o);
    });
  }

  // ── 列表 ────────────────────────────────────────────────────────────
  async function loadList() {
    var params = new URLSearchParams();
    var q = $("q").value.trim();
    if (q) params.set("q", q);
    var st = $("f-status").value;
    if (st) params.set("status", st);
    var ind = $("f-industry").value.trim();
    if (ind) params.set("industry", ind);
    params.set("page", state.page);
    params.set("page_size", $("f-size").value);
    params.set("sort", "updated_at");
    params.set("order", "desc");

    var body = $("tbody");
    body.innerHTML = '<tr><td colspan="10" class="empty">加载中…</td></tr>';
    try {
      var data = await api(API + "?" + params.toString());
      state.items = data.items || [];
      state.total = data.total || 0;
      state.pages = data.pages || 0;
      state.page = data.page || 1;
      renderList();
    } catch (e) {
      body.innerHTML = '<tr><td colspan="10" class="empty">加载失败：' + esc(e.message) + "</td></tr>";
    }
  }

  function renderList() {
    var body = $("tbody");
    if (!state.items.length) {
      body.innerHTML = '<tr><td colspan="10" class="empty">暂无项目。点击右上角「＋ 新建项目」开始。</td></tr>';
    } else {
      body.innerHTML = state.items.map(function (p) {
        var period = (p.period_start || p.period_end)
          ? esc(p.period_start || "—") + " ~ " + esc(p.period_end || "—") : "—";
        var scopes = (p.tax_scopes && p.tax_scopes.length) ? p.tax_scopes.join("、") : "—";
        return '<tr>' +
          '<td>' + esc(p.code || "—") + '</td>' +
          '<td class="wrap-cell"><b>' + esc(p.name) + '</b></td>' +
          '<td>' + esc(p.taxpayer_id || "—") + '</td>' +
          '<td>' + esc(p.industry || "—") + '</td>' +
          '<td>' + esc(p.region || "—") + '</td>' +
          '<td>' + period + '</td>' +
          '<td class="wrap-cell">' + esc(scopes) + '</td>' +
          '<td><span class="tag st-' + esc(p.status) + '">' + esc(p.status_cn || statusLabel(p.status)) + '</span></td>' +
          '<td>' + esc(String(p.updated_at || "").slice(0, 19).replace("T", " ")) + '</td>' +
          '<td>' +
            '<button class="btn ghost" data-act="view" data-id="' + p.id + '">详情</button> ' +
            '<button class="btn ghost" data-act="edit" data-id="' + p.id + '">编辑</button> ' +
            '<button class="btn danger" data-act="del" data-id="' + p.id + '">删除</button>' +
          '</td></tr>';
      }).join("");
    }
    $("count").textContent = "共 " + state.total + " 个项目";
    $("pageinfo").textContent = state.pages ? ("第 " + state.page + " / " + state.pages + " 页") : "";
    $("prev").disabled = state.page <= 1;
    $("next").disabled = state.pages === 0 || state.page >= state.pages;
  }

  // ── 表单（新建 / 编辑）──────────────────────────────────────────────
  // ★ 2026-10-14 入口归一：企业身份（名称/税号/行业）以账套为单一权威，
  // 建项目必须选账套，三件套只读带出、后端再次以账套回填兜底。
  async function loadCompanyOptions(selectedId) {
    var sel = $("f-company");
    sel.innerHTML = '<option value="">加载中…</option>';
    try {
      var data = await api("/api/companies");
      var list = Array.isArray(data) ? data : (data.companies || data.data || []);
      if (!list.length) {
        sel.innerHTML = '<option value="">（暂无可用账套）</option>';
        $("form-msg").innerHTML = '<div class="msg err">还没有可用账套：请先到 ' +
          '<a href="/select-company">选择账套</a> 页新建，再回来创建项目。</div>';
        return;
      }
      sel.innerHTML = '<option value="">— 请选择账套 —</option>' + list.map(function (c) {
        var nm = c.name || c.company_name || "";
        var u = c.uscc ? "（" + c.uscc + "）" : "";
        return '<option value="' + c.id + '" data-name="' + esc(nm) + '"' +
          ' data-uscc="' + esc(c.uscc || "") + '"' +
          ' data-ind="' + esc(c.industry_resolved || c.industry_registered || c.industry || "") + '">' +
          esc(nm) + esc(u) + '</option>';
      }).join("");
      if (selectedId) sel.value = String(selectedId);
      if (sel.value) syncCompanyFields();   // 挂有账套 ⇒ 以账套为准回填
      // 未挂账套的历史项目：保留其原有显示值，由用户选择账套后覆盖
    } catch (e) {
      sel.innerHTML = '<option value="">（账套加载失败）</option>';
    }
  }
  function syncCompanyFields() {
    var sel = $("f-company");
    var opt = sel.selectedOptions && sel.selectedOptions[0];
    if (!opt || !opt.value) return;
    $("f-name").value = opt.getAttribute("data-name") || "";
    $("f-tid").value = opt.getAttribute("data-uscc") || "";
    $("f-ind").value = opt.getAttribute("data-ind") || "";
  }
  async function openForm(project) {
    state.editing = project || null;
    $("form-title").textContent = project ? "编辑项目" : "新建项目";
    $("form-msg").innerHTML = "";
    $("f-name").value = project ? (project.name || "") : "";
    $("f-tid").value = project ? (project.taxpayer_id || "") : "";
    $("f-ind").value = project ? (project.industry || "") : "";
    $("f-reg").value = project ? (project.region || "") : "";
    $("f-ps").value = project ? (project.period_start || "") : "";
    $("f-pe").value = project ? (project.period_end || "") : "";
    $("f-scopes").value = project && project.tax_scopes ? project.tax_scopes.join(",") : "";
    $("f-remark").value = project ? (project.remark || "") : "";
    await loadCompanyOptions(project ? (project.company_id || "") : "");
    openModal("m-form");
    $("f-company").focus();
  }

  async function saveForm() {
    var companyId = $("f-company").value;
    if (!companyId) {
      $("form-msg").innerHTML = '<div class="msg err">请先选择所属账套（企业信息统一由账套管理）</div>';
      return;
    }
    var name = $("f-name").value.trim();
    if (!name) { $("form-msg").innerHTML = '<div class="msg err">所属账套缺少企业名称，请先补全账套信息</div>'; return; }
    var scopes = $("f-scopes").value.split(/[,，]/).map(function (s) { return s.trim(); })
      .filter(function (s) { return s; });
    var payload = {
      company_id: Number(companyId),
      name: name,
      taxpayer_id: $("f-tid").value.trim(),
      industry: $("f-ind").value.trim(),
      region: $("f-reg").value.trim(),
      period_start: $("f-ps").value,
      period_end: $("f-pe").value,
      tax_scopes: scopes,
      remark: $("f-remark").value.trim()
    };
    try {
      if (state.editing) {
        await api(API + "/" + state.editing.id, {
          method: "PUT", headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        flash("项目已保存");
      } else {
        await api(API, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        flash("项目已创建");
      }
      closeModal("m-form");
      await loadList();
    } catch (e) {
      $("form-msg").innerHTML = '<div class="msg err">' + esc(e.message) + "</div>";
    }
  }

  // ── 详情（基本信息 + 成员 + 状态 + 操作日志）────────────────────────
  async function openDetail(id) {
    var body = $("detail-body");
    body.innerHTML = "加载中…";
    openModal("m-detail");
    try {
      var p = await api(API + "/" + id);
      $("detail-title").textContent = "项目详情：" + (p.name || "");
      var period = (p.period_start || p.period_end)
        ? (p.period_start || "—") + " ~ " + (p.period_end || "—") : "—";
      var nextBtns = (p.allowed_next_status_cn || []).map(function (label, i) {
        var v = p.allowed_next_status[i];
        return '<button class="btn ghost" data-mv="' + esc(v) + '" data-id="' + p.id + '">→ ' + esc(label) + '</button>';
      }).join(" ") || '<span class="muted">已归档（终态，不可再变更）</span>';

      var members = (p.members || []).map(function (m) {
        return '<tr><td>' + esc(m.user_name || m.user_id || "—") + '</td><td>' +
          esc(m.role_cn || roleLabel(m.role)) + '</td><td class="muted">' +
          esc(String(m.created_at || "").slice(0, 19).replace("T", " ")) + '</td></tr>';
      }).join("") || '<tr><td colspan="3" class="muted">暂无成员</td></tr>';

      var logs = (p.logs || []).map(function (l) {
        return '<div class="logline"><span class="t">' +
          esc(String(l.at || "").slice(0, 19).replace("T", " ")) + '</span>' +
          esc(l.by || "") + '　<b>' + esc(l.action_cn || l.action) + '</b>　' + esc(l.detail || "") +
          '</div>';
      }).join("") || '<div class="muted">暂无操作日志</div>';

      body.innerHTML =
        '<div class="kv">' +
          '<div class="k">项目编号</div><div>' + esc(p.code || "—") + '</div>' +
          '<div class="k">企业名称</div><div><b>' + esc(p.name) + '</b></div>' +
          '<div class="k">纳税人识别号</div><div>' + esc(p.taxpayer_id || "—") + '</div>' +
          '<div class="k">行业 / 地区</div><div>' + esc(p.industry || "—") + ' / ' + esc(p.region || "—") + '</div>' +
          '<div class="k">稽查期间</div><div>' + esc(period) + '</div>' +
          '<div class="k">税种范围</div><div>' + esc((p.tax_scopes || []).join("、") || "—") + '</div>' +
          '<div class="k">备注</div><div>' + esc(p.remark || "—") + '</div>' +
          '<div class="k">创建</div><div class="muted">' + esc(p.owner_name || "—") + '　' +
            esc(String(p.created_at || "").slice(0, 19).replace("T", " ")) + '</div>' +
        '</div>' +
        '<div class="sect">状态</div>' +
        '<div class="statustrack">当前：<span class="tag st-' + esc(p.status) + '">' +
          esc(p.status_cn || statusLabel(p.status)) + '</span>' +
          (p.can_write ? '　<span class="muted">可迁移到：</span>' + nextBtns
                       : '　<span class="muted">（无写权限，仅可查看）</span>') + '</div>' +
        '<div class="sect">成员（' + (p.members || []).length + '）</div>' +
        '<table class="grid"><thead><tr><th>成员</th><th>角色</th><th>加入时间</th></tr></thead>' +
          '<tbody>' + members + '</tbody></table>' +
        (p.can_write ?
          '<div class="form-row" style="margin-top:10px">' +
            '<label>成员姓名<input type="text" id="nm-name" placeholder="姓名"></label>' +
            '<label>用户 ID<input type="text" id="nm-uid" placeholder="可空"></label>' +
            '<label>角色<select id="nm-role"></select></label>' +
            '<label style="justify-content:flex-end"><span>&nbsp;</span>' +
              '<button class="btn" id="btn-addmember" data-id="' + p.id + '">添加成员</button></label>' +
          '</div>' : '') +
        '<div class="sect">操作日志（最近 50 条）</div>' + logs;

      var rsel = $("nm-role");
      if (rsel) {
        META.roles.forEach(function (r) {
          var o = document.createElement("option");
          o.value = r.value; o.textContent = r.label;
          if (r.value === "member") o.selected = true;
          rsel.appendChild(o);
        });
      }
    } catch (e) {
      body.innerHTML = '<div class="msg err">' + esc(e.message) + "</div>";
    }
  }

  async function moveStatus(id, status) {
    try {
      var p = await api(API + "/" + id, {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: status })
      });
      flash("状态已更新为「" + (p.status_cn || statusLabel(p.status)) + "」");
      await loadList();
      await openDetail(id);
    } catch (e) {
      flash("状态更新失败：" + e.message, "err");
    }
  }

  async function addMember(id) {
    var name = ($("nm-name") || {}).value || "";
    var uid = ($("nm-uid") || {}).value || "";
    var role = ($("nm-role") || {}).value || "member";
    var payload = { role: role };
    if (name.trim()) payload.user_name = name.trim();
    if (uid.trim()) payload.user_id = Number(uid.trim());
    if (!payload.user_name && !payload.user_id) { flash("请填写成员姓名或用户 ID", "err"); return; }
    try {
      await api(API + "/" + id + "/members", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      flash("成员已保存");
      await openDetail(id);
    } catch (e) {
      flash("添加成员失败：" + e.message, "err");
    }
  }

  // ── 删除（二次确认）────────────────────────────────────────────────
  function askDelete(p) {
    state.deleting = p;
    $("del-name").textContent = (p.code ? p.code + " " : "") + p.name;
    openModal("m-del");
  }
  async function doDelete() {
    if (!state.deleting) return;
    try {
      await api(API + "/" + state.deleting.id, { method: "DELETE" });
      closeModal("m-del");
      flash("项目已删除");
      state.deleting = null;
      await loadList();
    } catch (e) {
      closeModal("m-del");
      flash("删除失败：" + e.message, "err");
    }
  }

  // ── 事件绑定 ────────────────────────────────────────────────────────
  function bind() {
    $("btn-search").onclick = function () { state.page = 1; loadList(); };
    $("btn-reset").onclick = function () {
      $("q").value = ""; $("f-status").value = ""; $("f-industry").value = ""; state.page = 1; loadList();
    };
    $("q").addEventListener("keydown", function (e) {
      if (e.key === "Enter") { state.page = 1; loadList(); }
    });
    $("f-size").onchange = function () { state.page = 1; loadList(); };
    $("btn-new").onclick = function () { openForm(null); };
    $("btn-save").onclick = saveForm;
    $("f-company").onchange = syncCompanyFields;   // 换选账套 ⇒ 企业字段联动回填
    $("btn-del-confirm").onclick = doDelete;
    $("prev").onclick = function () { if (state.page > 1) { state.page--; loadList(); } };
    $("next").onclick = function () { if (state.page < state.pages) { state.page++; loadList(); } };

    document.querySelectorAll("[data-close]").forEach(function (el) {
      el.onclick = function () { closeModal(el.getAttribute("data-close")); };
    });

    // 表格与详情内的委托事件
    document.addEventListener("click", function (e) {
      var t = e.target;
      if (!t || !t.getAttribute) return;
      var act = t.getAttribute("data-act");
      if (act) {
        var id = Number(t.getAttribute("data-id"));
        var p = state.items.filter(function (x) { return x.id === id; })[0];
        if (act === "view") openDetail(id);
        else if (act === "edit" && p) openForm(p);
        else if (act === "del" && p) askDelete(p);
        return;
      }
      var mv = t.getAttribute("data-mv");
      if (mv) { moveStatus(Number(t.getAttribute("data-id")), mv); return; }
      if (t.id === "btn-addmember") { addMember(Number(t.getAttribute("data-id"))); }
    });

    // 点遮罩关闭（表单/详情/删除确认）
    ["m-form", "m-detail", "m-del"].forEach(function (id) {
      $(id).addEventListener("click", function (e) { if (e.target === $(id)) $(id).hidden = true; });
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") ["m-form", "m-detail", "m-del"].forEach(function (i) { $(i).hidden = true; });
    });
  }

  // ── 启动 ────────────────────────────────────────────────────────────
  (async function init() {
    try {
      // R-4（2026-10-14）：原为 "/api/me" —— 该路径**后端并不存在**（实测 404），
      //   唯一权威是 `/api/auth/me`。原写法被 .catch 静默吞掉 ⇒ 右侧用户名不显示。
      var me = await api("/api/auth/me").catch(function () { return null; });
      if (me && me.username) $("whoami").textContent = me.username;
    } catch (e) { /* 未登录由全局 401 拦截跳转，无需处理 */ }
    try {
      await loadMeta();
    } catch (e) {
      flash("字典加载失败：" + e.message, "err");
    }
    bind();
    await loadList();
  })();
})();
