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
  // ★ 2026-10-18（用户要求）：列表勾选 + 删除选中。切换页/刷新即清空（避免"删了看不到的行"）。
  var PICKED = {};

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
  function fillDatalist(id, values) {
    var el = $(id);
    if (!el) return;
    el.innerHTML = values.map(function (v) {
      return '<option value="' + esc(v) + '"></option>';
    }).join("");
  }
  function fillSelect(id, values, emptyLabel) {
    var el = $(id);
    if (!el) return;
    el.innerHTML = '<option value="">' + esc(emptyLabel || "（未填）") + "</option>" +
      values.map(function (v) {
        return '<option value="' + esc(v) + '">' + esc(v) + "</option>";
      }).join("");
  }
  // 税种范围多选（选项来自后端 /meta 的 tax_types，前端不硬编码）
  var SCOPE = {};
  function renderTaxChips() {
    var box = $("pf-tax-scopes");
    if (!box) return;
    box.innerHTML = (META.tax_types || []).map(function (t) {
      var on = !!SCOPE[t.value];
      return '<label data-scope="' + esc(t.value) + '"' + (on ? ' class="on"' : "") + '>' +
        '<input type="checkbox" value="' + esc(t.value) + '"' + (on ? " checked" : "") + '>' +
        esc(t.label) + "</label>";
    }).join("");
  }

  async function loadMeta() {
    META = await api(API + "/meta");
    var sel = $("f-status");
    META.statuses.forEach(function (s) {
      var o = document.createElement("option");
      o.value = s.value; o.textContent = s.label;
      sel.appendChild(o);
    });
    // ★ 2026-10-18：企业画像/稽查要素字典 —— 全部取后端，前端不写死任何选项
    fillDatalist("dl-industry", (META.industries || []).map(function (x) { return x.value; }));
    fillDatalist("dl-region", META.regions || []);
    fillSelect("pf-registration_status", META.registration_statuses || [], "（未填）");
    fillSelect("pf-company_type", META.company_types || [], "（未填）");
    Array.prototype.forEach.call(document.querySelectorAll(".cap-unit"), function (e) {
      e.textContent = META.capital_unit || "万元";
    });
    renderTaxChips();
  }

  // ── 列表 ────────────────────────────────────────────────────────────
  async function loadList() {
    PICKED = {};            // 换页/搜索/刷新都重新开始勾选（不跨页累加）
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

  function fmtCapital(v) {
    if (v === null || v === undefined || v === "") return "—";
    var n = Number(v);
    if (isNaN(n)) return "—";
    return n.toLocaleString("zh-CN", { maximumFractionDigits: 2 }) + " " +
      ((META && META.capital_unit) || "万元");
  }
  function fmtPeriod(p) {
    return (p.period_start || p.period_end)
      ? esc(p.period_start || "—") + " ~ " + esc(p.period_end || "—") : "—";
  }

  function renderList() {
    var body = $("tbody");
    if (!state.items.length) {
      body.innerHTML = '<tr><td colspan="15" class="empty">暂无项目。点击右上角「＋ 新建项目」开始。</td></tr>';
    } else {
      body.innerHTML = state.items.map(function (p) {
        var period = fmtPeriod(p);
        var scopes = (p.tax_scopes && p.tax_scopes.length) ? p.tax_scopes.join("、") : "—";
        // ★ 缺项如实标注（不补默认值）：把「缺哪几项」放进 title，便于点编辑补录
        var miss = p.profile_missing || [];
        var pendingTag = miss.length
          ? ' <span class="tag pending" title="缺：' + esc(miss.join("、")) + '">待补全</span>' : "";
        return '<tr>' +
          '<td style="text-align:center"><input type="checkbox" class="proj-sel" data-pid="'
            + esc(p.id) + '"' + (PICKED[p.id] ? ' checked' : '') + '></td>' +
          '<td>' + esc(p.code || "—") + '</td>' +
          '<td class="wrap-cell"><b>' + esc(p.name) + '</b>' + pendingTag + '</td>' +
          '<td>' + esc(p.taxpayer_id || "—") + '</td>' +
          '<td>' + esc(p.legal_representative || "—") + '</td>' +
          '<td>' + fmtCapital(p.registered_capital) + '</td>' +
          '<td>' + esc(p.established_date || "—") + '</td>' +
          '<td>' + esc(p.registration_status || "—") + '</td>' +
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
    syncSel();
    $("count").textContent = "共 " + state.total + " 个项目";
    $("pageinfo").textContent = state.pages ? ("第 " + state.page + " / " + state.pages + " 页") : "";
    $("prev").disabled = state.page <= 1;
    $("next").disabled = state.pages === 0 || state.page >= state.pages;
  }

  // ── 表单（新建 / 编辑）──────────────────────────────────────────────
  // ★ 2026-10-18（用户要求）：行业/地区/稽查期间等**在建项目这一步收集**，
  //   并补录企业重点工商信息 ⇒ 表单分「第 1 步 企业基本信息」「第 2 步 稽查要素」。
  //   ⚠ 旧注释「只填名称+税号，其余由分析确定」已作废：实测项目行业/地区/期间长期为空。
  function pf(k) { return $("pf-" + k); }

  var FORM_TEXT_KEYS = ["legal_representative", "registration_status", "company_type",
                        "registered_address", "business_scope"];

  async function openForm(project) {
    state.editing = project || null;
    $("form-title").textContent = project ? "编辑项目" : "新建项目";
    $("form-msg").innerHTML = "";
    bizNote("");
    bizWarn("");
    pf("name").value = project ? (project.name || "") : "";
    pf("tid").value = project ? (project.taxpayer_id || "") : "";
    pf("industry").value = project ? (project.industry || "") : "";
    pf("region").value = project ? (project.region || "") : "";
    pf("ps").value = project ? (project.period_start || "") : "";
    pf("pe").value = project ? (project.period_end || "") : "";
    pf("remark").value = project ? (project.remark || "") : "";
    pf("registered_capital").value =
      (project && project.registered_capital !== null && project.registered_capital !== undefined)
        ? project.registered_capital : "";
    pf("established_date").value = project ? (project.established_date || "") : "";
    FORM_TEXT_KEYS.forEach(function (k) {
      var el = pf(k);
      if (el) el.value = project ? (project[k] || "") : "";
    });
    SCOPE = {};
    ((project && project.tax_scopes) || []).forEach(function (s) { SCOPE[s] = true; });
    renderTaxChips();
    openModal("m-form");
    pf("name").focus();
  }

  function collectScopes() {
    var out = [];
    Array.prototype.forEach.call(
      document.querySelectorAll("#pf-tax-scopes label"),
      function (lab) {
        if (lab.classList.contains("on")) out.push(lab.getAttribute("data-scope"));
      });
    return out;
  }

  function showFormError(msg) {
    $("form-msg").innerHTML = '<div class="msg err">' + esc(msg) + "</div>";
    $("form-msg").scrollIntoView({ block: "nearest" });
  }

  // ── 工商信息查询（【自动查填】，2026-10-18 新增）────────────────────
  // 接口：GET /api/v1/business/query（服务端负责 缓存→本地库→公示系统 的取数与清洗）
  // ★ 三条硬规矩：
  //   ① 只填**取到值**的字段：空值不覆盖用户已填内容，也不清空（缺失≠0）；
  //   ② 查询失败**只是提示**，不阻断保存（用户要求"不能阻断项目创建"）；
  //   ③ 登记状态为注销/吊销等时**弹红色警告**（后端 risk_status_warning 是唯一判据，前端不重判）。
  var BIZ_FIELDS = ["legal_representative", "registered_capital", "established_date",
                    "registration_status", "registered_address", "company_type",
                    "business_scope"];

  function bizNote(text, kind) {
    var el = $("bizinfo-note");
    if (!el) return;
    el.textContent = text || "";
    el.style.color = kind === "err" ? "#b91c1c" : (kind === "ok" ? "#047857" : "#64748b");
  }

  function bizWarn(html) {
    var el = $("bizinfo-warn");
    if (!el) return;
    if (!html) { el.hidden = true; el.innerHTML = ""; return; }
    el.innerHTML = html;
    el.hidden = false;
  }

  async function fetchBizInfo() {
    var btn = $("btn-fetch-bizinfo");
    var name = pf("name").value.trim();
    bizWarn("");
    if (name.length < 2) {
      bizNote("请先填写企业全称（至少 2 个字）再查填", "err");
      pf("name").focus();
      return;
    }
    var old = btn ? btn.textContent : "";
    if (btn) { btn.disabled = true; btn.textContent = "查询中…"; }
    bizNote("正在查询工商信息…");
    try {
      var url = "/api/v1/business/query?name=" + encodeURIComponent(name)
        + (state.editing && state.editing.id
           ? "&project_id=" + encodeURIComponent(state.editing.id) : "");
      var d = await api(url);
      if (!d || !d.ok || !d.profile) {
        bizNote((d && d.message ? d.message : "查询超时，请手动填写")
                + (d && d.detail ? "（" + d.detail + "）" : ""), "err");
        return;
      }
      var p = d.profile;
      var filled = 0;
      if (p.tax_id) { pf("tid").value = p.tax_id; filled += 1; }
      BIZ_FIELDS.forEach(function (k) {
        if (p[k] === null || p[k] === undefined || p[k] === "") return;
        var el = pf(k);
        if (!el) return;
        el.value = p[k];
        filled += 1;
      });
      var missing = (p.missing || []).length;
      bizNote("已查填 " + filled + " 项（来源：" + (d.source_detail || d.source || "—")
              + (d.cache_hit ? "，命中缓存" : "")
              + "）" + (missing ? "；" + missing + " 项未取得，请手工补齐" : ""),
              filled ? "ok" : "err");
      if (d.risk_status_warning) {
        bizWarn("<b>登记状态异常：</b>" + esc(d.risk_status_warning));
      }
    } catch (e) {
      bizNote("查询失败：" + (e && e.message ? e.message : "网络异常")
              + "；请手动填写，不影响项目创建", "err");
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = old; }
    }
  }

  async function saveForm() {
    var name = pf("name").value.trim();
    if (!name) { showFormError("企业名称不能为空"); return; }
    var tid = pf("tid").value.trim().toUpperCase();
    if (tid.length !== 18) { showFormError("统一社会信用代码必须为 18 位"); return; }
    // 第 2 步稽查要素：必填（这是稽查范围的起点，留空会让后续比对失去期间/行业口径）
    var industry = pf("industry").value.trim();
    var region = pf("region").value.trim();
    var ps = pf("ps").value, pe = pf("pe").value;
    var scopes = collectScopes();
    var lack = [];
    if (!industry) lack.push("行业");
    if (!region) lack.push("地区");
    if (!ps) lack.push("稽查期间起");
    if (!pe) lack.push("稽查期间止");
    if (!scopes.length) lack.push("税种范围");
    if (lack.length) { showFormError("请补全稽查要素（第 2 步）：" + lack.join("、")); return; }
    if (ps > pe) { showFormError("稽查期间起止颠倒：起 " + ps + " 晚于 止 " + pe); return; }

    var capRaw = pf("registered_capital").value.trim();
    var payload = {
      name: name,
      taxpayer_id: tid,
      industry: industry,
      region: region,
      period_start: ps,
      period_end: pe,
      tax_scopes: scopes,
      remark: pf("remark").value.trim(),
      legal_representative: pf("legal_representative").value.trim(),
      registered_capital: capRaw === "" ? null : Number(capRaw),
      established_date: pf("established_date").value || "",
      registration_status: pf("registration_status").value || "",
      registered_address: pf("registered_address").value.trim(),
      business_scope: pf("business_scope").value.trim(),
      company_type: pf("company_type").value || ""
    };
    if (payload.registered_capital !== null &&
        (isNaN(payload.registered_capital) || payload.registered_capital < 0)) {
      showFormError("注册资本必须是非负数字（单位：万元）");
      return;
    }
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
      showFormError(e.message);
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
      var period = fmtPeriod(p);   // 已转义，避免脏数据破坏 DOM
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

      var miss = p.profile_missing || [];
      body.innerHTML =
        (miss.length
          ? '<div class="msg warn">本项目缺少稽查要素：' + esc(miss.join("、")) +
            '。点右上角「编辑」补录后，比对期间与行业口径才会生效。</div>' : '') +
        '<div class="sect">企业基本信息（工商登记口径）</div>' +
        '<div class="kv">' +
          '<div class="k">项目编号</div><div>' + esc(p.code || "—") + '</div>' +
          '<div class="k">企业名称</div><div><b>' + esc(p.name) + '</b></div>' +
          '<div class="k">统一社会信用代码</div><div>' + esc(p.taxpayer_id || "—") + '</div>' +
          '<div class="k">法定代表人</div><div>' + esc(p.legal_representative || "—") + '</div>' +
          '<div class="k">注册资本</div><div>' + fmtCapital(p.registered_capital) + '</div>' +
          '<div class="k">成立日期</div><div>' + esc(p.established_date || "—") + '</div>' +
          '<div class="k">登记状态</div><div>' + esc(p.registration_status || "—") + '</div>' +
          '<div class="k">公司类型</div><div>' + esc(p.company_type || "—") + '</div>' +
          '<div class="k">注册地址</div><div>' + esc(p.registered_address || "—") + '</div>' +
          '<div class="k">经营范围</div><div class="wrap-cell">' + esc(p.business_scope || "—") + '</div>' +
        '</div>' +
        '<div class="sect">稽查要素</div>' +
        '<div class="kv">' +
          '<div class="k">行业</div><div>' + esc(p.industry || "—") + '</div>' +
          '<div class="k">地区</div><div>' + esc(p.region || "—") + '</div>' +
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

  // ── 勾选与「删除选中」（2026-10-18，用户要求）──────────────────────────
  // ★ 口径：
  //   · 只勾**本页可见**的行；翻页/搜索/刷新即清空（避免删掉自己没看到的项目）；
  //   · 删除走既有 `DELETE /api/v1/projects/{id}`（服务端唯一出口，文件进回收站）；
  //   · 项目下有资料时服务端返 **409**（要求显式确认）⇒ 这里**逐条**询问是否一并删除，
  //     不"一票全删"，避免一个项目的资料连带影响其它项目的判定；
  //   · 结果**逐条汇总**（成功/跳过/失败），不笼统说"已删除"。
  function pickedIds() {
    return Object.keys(PICKED).filter(function (k) { return PICKED[k]; });
  }

  function syncSel() {
    var n = pickedIds().length;
    var btn = $("btn-del-selected");
    if (btn) {
      btn.hidden = n === 0;
      btn.textContent = n ? ("删除选中（" + n + "）") : "删除选中";
    }
    var all = $("sel-all");
    if (all) {
      var boxes = document.querySelectorAll("#tbody input.proj-sel");
      var checked = 0;
      Array.prototype.forEach.call(boxes, function (b) { if (b.checked) checked++; });
      all.checked = boxes.length > 0 && checked === boxes.length;
      all.indeterminate = checked > 0 && checked < boxes.length;
    }
  }

  async function delSelected() {
    var ids = pickedIds();
    if (!ids.length) return;
    var names = ids.map(function (id) {
      var hit = state.items.filter(function (p) { return String(p.id) === String(id); })[0];
      return hit ? (hit.name + "（" + (hit.code || id) + "）") : ("#" + id);
    });
    if (!window.confirm("确定删除以下 " + ids.length + " 个稽查项目？\n\n"
                        + names.join("\n")
                        + "\n\n项目下的资料会一并移入回收站（可还原）。")) return;
    var okN = 0, skipN = 0, badN = 0, cascadeN = 0;
    var btn = $("btn-del-selected");
    if (btn) { btn.disabled = true; btn.textContent = "删除中…"; }
    try {
      for (var i = 0; i < ids.length; i++) {
        var id = ids[i];
        try {
          await api(API + "/" + id, { method: "DELETE" });
          okN++; delete PICKED[id];
        } catch (e) {
          // 409 = 项目下有资料 ⇒ 逐条确认后再删（服务端要求 cascade=true）
          if (e && e.status === 409) {
            var hit = state.items.filter(function (p) { return String(p.id) === String(id); })[0];
            var nm = hit ? hit.name : ("#" + id);
            if (window.confirm("「" + nm + "」项目下仍有资料。\n\n"
                               + "是否连同项目下资料一起删除？\n"
                               + "（资料记录删除，文件移入回收站，可在回收站还原）")) {
              try {
                await api(API + "/" + id + "?cascade=true", { method: "DELETE" });
                okN++; cascadeN++; delete PICKED[id];
              } catch (e2) {
                badN++;
                flash("「" + nm + "」删除失败：" + e2.message, "err");
              }
            } else {
              skipN++;
            }
          } else {
            badN++;
            flash("#" + id + " 删除失败：" + (e && e.message ? e.message : "未知错误"), "err");
          }
        }
      }
      flash("删除完成：成功 " + okN + " 个"
            + (cascadeN ? "（其中 " + cascadeN + " 个含资料已移入回收站）" : "")
            + "，跳过 " + skipN + " 个，失败 " + badN + " 个",
            badN ? "warn" : "ok");
      await loadList();
    } finally {
      if (btn) { btn.disabled = false; }
      syncSel();
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
    // 工商信息【自动查填】（按钮受 data-perm="project.write" 门控，无权限时隐藏）
    if ($("btn-fetch-bizinfo")) $("btn-fetch-bizinfo").onclick = fetchBizInfo;
    $("btn-del-confirm").onclick = doDelete;
    $("btn-del-selected").onclick = delSelected;
    $("sel-all").onchange = function () {
      var on = $("sel-all").checked;
      Array.prototype.forEach.call(document.querySelectorAll("#tbody input.proj-sel"),
        function (b) {
          b.checked = on;
          var id = b.getAttribute("data-pid");
          if (on) PICKED[id] = true; else delete PICKED[id];
        });
      syncSel();
    };
    $("tbody").addEventListener("change", function (e) {
      var t = e.target;
      if (!t || !t.classList || !t.classList.contains("proj-sel")) return;
      var id = t.getAttribute("data-pid");
      if (t.checked) PICKED[id] = true; else delete PICKED[id];
      syncSel();
    });
    $("prev").onclick = function () { if (state.page > 1) { state.page--; loadList(); } };
    $("next").onclick = function () { if (state.page < state.pages) { state.page++; loadList(); } };

    document.querySelectorAll("[data-close]").forEach(function (el) {
      el.onclick = function () { closeModal(el.getAttribute("data-close")); };
    });

    // 表格与详情内的委托事件
    document.addEventListener("click", function (e) {
      var t = e.target;
      if (!t || !t.getAttribute) return;
      // 税种范围 chips（点标签或复选框都能切换，状态以 class 为准）
      var lab = t.closest ? t.closest("#pf-tax-scopes label") : null;
      if (lab) {
        e.preventDefault();
        lab.classList.toggle("on");
        var cb = lab.querySelector("input[type=checkbox]");
        if (cb) cb.checked = lab.classList.contains("on");
        return;
      }
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
