/* 解析与标准化（P0-3）前端逻辑 —— 原生 JS，无框架、无构建（沿用现有技术栈）。
 *
 * 约定（与既有前端一致）：
 *   · CSRF 由全局 fetch 拦截器自动附加（security.js）；401 由它跳 /login。
 *   · 域/规则中文名**一律取后端** /api/v1/extract/meta（不硬编码）。
 *   · 校正按标准字段类型校验在后端做（金额/期间非法 ⇒ 400），前端只做展示与提交。
 */
(function () {
  "use strict";

  var API = "/api/v1";
  var META = null, PROJECT = null, DOC = null;

  function $(id) { return document.getElementById(id); }
  function esc(s) {
    return String(s === null || s === undefined ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function flash(text, kind) {
    $("msg").innerHTML = text ? '<div class="msg ' + (kind || "ok") + '">' + esc(text) + "</div>" : "";
    if (text) { window.clearTimeout(flash._t); flash._t = window.setTimeout(function () { $("msg").innerHTML = ""; }, 5000); }
  }
  async function api(path, options) {
    var res = await fetch(path, options);
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
  function cnDomain(code) {
    if (!META) return code || "";
    var hit = (META.standard_fields.domains || []).filter(function (d) { return d.value === code; })[0];
    return hit ? hit.label : (code || "");
  }
  function cnField(name) {
    if (!META) return name || "";
    var hit = (META.standard_fields.fields || []).filter(function (f) { return f.name === name; })[0];
    return hit ? hit.cn : (name || "");
  }

  async function loadMeta() { META = await api(API + "/extract/meta"); }

  async function loadProjects() {
    var d = await api(API + "/projects?page_size=200");
    var sel = $("proj");
    sel.innerHTML = "";
    if (!d.items.length) {
      var o = document.createElement("option");
      o.value = ""; o.textContent = "（暂无项目）"; sel.appendChild(o);
      return null;
    }
    d.items.forEach(function (p) {
      var op = document.createElement("option");
      op.value = p.id; op.textContent = (p.code ? p.code + " " : "") + p.name;
      sel.appendChild(op);
    });
    var saved = localStorage.getItem("extractProjectId");
    var pick = d.items.filter(function (p) { return String(p.id) === String(saved); })[0];
    sel.value = pick ? pick.id : d.items[0].id;
    return Number(sel.value);
  }

  async function loadDocs() {
    var sel = $("doc");
    sel.innerHTML = '<option value="">（请选择资料）</option>';
    if (!PROJECT) return;
    try {
      var d = await api(API + "/projects/" + PROJECT + "/documents?page_size=200");
      (d.items || []).forEach(function (x) {
        var o = document.createElement("option");
        o.value = x.id;
        o.textContent = x.original_name + "（" + (x.category_cn || "") + " / " +
                        (x.parse_status_cn || "") + "）";
        sel.appendChild(o);
      });
      if (!(d.items || []).length) {
        flash("该项目下暂无资料，请先在「资料管理」上传", "warn");
      }
    } catch (e) {
      flash("加载资料失败：" + e.message, "err");
    }
  }

  // ── 解析 ──────────────────────────────────────────────────────────
  async function runParse() {
    DOC = Number($("doc").value) || null;
    if (!DOC) { flash("请先选择资料", "err"); return; }
    $("btn-parse").disabled = true;
    $("parse-hint").textContent = "解析中…";
    try {
      var r = await api(API + "/documents/" + DOC + "/extract", { method: "POST" });
      $("parse-hint").textContent = "解析完成（作业 " + (r.job_id || "-") + "）";
      if (r.parse_error) flash("解析提示：" + r.parse_error, "warn");
      else flash("解析完成：表 " + (r.tables || []).length + " 张、" +
                 (r.fields || []).length + " 个标准字段、" +
                 (r.issues || []).length + " 条校验异常");
      await loadExtracted();
    } catch (e) {
      $("parse-hint").textContent = "";
      flash("解析失败：" + e.message, "err");
    } finally {
      $("btn-parse").disabled = false;
    }
  }

  async function loadExtracted() {
    if (!DOC) { $("doc").value = ""; return; }
    try {
      var d = await api(API + "/documents/" + DOC + "/extracted");
      renderStats(d);
      renderFields(d);
      renderIssues(d);
      renderTables(d);
    } catch (e) {
      flash("加载解析结果失败：" + e.message, "err");
    }
  }

  function renderStats(d) {
    var s = d.issue_summary || {};
    var errs = (s.by_severity || {}).error || 0;
    var warns = (s.by_severity || {}).warning || 0;
    $("stats").innerHTML =
      '<div><b>' + (d.tables || []).length + '</b>解析表格</div>' +
      '<div><b>' + (d.fields || []).length + '</b>标准字段</div>' +
      '<div><b>' + (d.issues || []).length + '</b>校验异常</div>' +
      '<div><b style="color:' + (errs ? "#b91c1c" : "#1e293b") + '">' + errs + '</b>严重(error)</div>' +
      '<div><b style="color:' + (warns ? "#b45309" : "#1e293b") + '">' + warns + '</b>提示(warning)</div>' +
      '<div><b>' + (d.fields || []).filter(function (f) { return f.corrected; }).length + '</b>已人工校正</div>';
  }

  function renderFields(d) {
    var tb = $("tb-fields");
    var fs = d.fields || [];
    if (!fs.length) {
      tb.innerHTML = '<tr><td colspan="6" class="empty">未登记到标准字段（可能该格式暂不支持结构化解析，或字段名未在字典中）</td></tr>';
      return;
    }
    tb.innerHTML = fs.map(function (f) {
      var src = f.source || {};
      var shown = f.value_amount !== null && f.value_amount !== undefined
        ? f.value_amount : (f.value_period || f.value_text || "");
      return '<tr class="edit-row">' +
        '<td>' + esc(cnDomain(f.domain)) + '</td>' +
        '<td><b>' + esc(f.field_cn || cnField(f.standard_field)) + '</b>' +
          '<br><span class="muted" style="font-size:11px">' + esc(f.standard_field) + '</span></td>' +
        '<td class="val">' + esc(src.raw === undefined ? "" : src.raw) + '</td>' +
        '<td class="val' + (f.corrected ? " fixed" : "") + '">' + esc(shown) +
          (f.corrected ? '<br><span class="fixed">已校正（原值 ' + esc(f.original_value || "") + '）</span>' : '') + '</td>' +
        '<td class="muted" style="font-size:11px">' +
          esc((src.sheet ? src.sheet + " / " : "") + "第 " + (src.row || "?") + " 行") + '</td>' +
        '<td><input type="text" data-fid="' + f.id + '" value="' + esc(shown) + '"> ' +
          '<button class="btn ghost" data-save="' + f.id + '">保存</button></td>' +
      '</tr>';
    }).join("");
  }

  function renderIssues(d) {
    var tb = $("tb-issues");
    var is = d.issues || [];
    if (!is.length) {
      tb.innerHTML = '<tr><td colspan="5" class="empty">未发现校验异常</td></tr>';
      return;
    }
    tb.innerHTML = is.map(function (x) {
      var st = x.status || "open";
      var stCn = st === "open" ? "待处理" : (st === "resolved" ? "已处理" : "确认非问题");
      return '<tr>' +
        '<td><b>' + esc(x.rule_cn || x.rule) + '</b></td>' +
        '<td><span class="tag sev-' + esc(x.severity) + '">' +
          (x.severity === "error" ? "严重" : "提示") + '</span></td>' +
        '<td>' + esc(x.message || "") + '</td>' +
        '<td><span class="tag st-' + esc(st) + '">' + esc(stCn) + '</span></td>' +
        '<td>' + (st === "open"
          ? '<button class="btn ghost" data-resolve="' + x.id + '" data-to="resolved">标记已处理</button> ' +
            '<button class="btn ghost" data-resolve="' + x.id + '" data-to="ignored">确认非问题</button>'
          : '<span class="muted">—</span>') + '</td>' +
      '</tr>';
    }).join("");
  }

  function renderTables(d) {
    var box = $("tables");
    var ts = d.tables || [];
    if (!ts.length) { box.innerHTML = '<div class="empty">暂无解析产物</div>'; return; }
    box.innerHTML = ts.map(function (t) {
      var rows = t.rows_preview || [];
      var cols = rows.length ? Object.keys(rows[0]) : [];
      var head = '<tr>' + cols.map(function (c) { return '<th>' + esc(c) + '</th>'; }).join("") + '</tr>';
      var body = rows.map(function (r) {
        return '<tr>' + cols.map(function (c) { return '<td>' + esc(r[c]) + '</td>'; }).join("") + '</tr>';
      }).join("");
      return '<div style="margin-bottom:16px">' +
        '<div style="font-size:13px;font-weight:700;margin-bottom:6px">' +
          '表' + (t.sheet_name ? '「' + esc(t.sheet_name) + '」' : '') +
          '　<span class="muted" style="font-weight:400;font-size:12px">' +
          '识别类型 ' + esc(t.doc_type || "(未识别)") + '　置信度 ' + esc(t.confidence) +
          '　共 ' + t.row_count + ' 行 × ' + t.col_count + ' 列　解析状态 ' + esc(t.parse_status) +
          '（仅预览前 ' + rows.length + ' 行）</span></div>' +
        '<table class="grid"><thead>' + head + '</thead><tbody>' + body + '</tbody></table>' +
      '</div>';
    }).join("");
  }

  async function saveField(fid) {
    var input = document.querySelector('input[data-fid="' + fid + '"]');
    if (!input) return;
    try {
      var r = await api(API + "/extracted/" + fid, {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ value: input.value })
      });
      flash("已校正「" + (r.field_cn || r.standard_field) + "」：" +
            r.previous_value + " → " + r.value);
      await loadExtracted();
    } catch (e) {
      flash("校正失败：" + e.message, "err");
    }
  }

  async function resolveIssue(iid, to) {
    try {
      var r = await api(API + "/extract/issues/" + iid + "/resolve", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: to })
      });
      flash(r.status === "resolved" ? "已标记为已处理" : "已确认非问题");
      await loadExtracted();
    } catch (e) {
      flash("操作失败：" + e.message, "err");
    }
  }

  function bind() {
    $("btn-parse").onclick = runParse;
    $("btn-refresh").onclick = loadExtracted;
    $("proj").onchange = async function () {
      PROJECT = Number($("proj").value) || null;
      localStorage.setItem("extractProjectId", String(PROJECT || ""));
      DOC = null;
      await loadDocs();
      $("tb-fields").innerHTML = '<tr><td colspan="6" class="empty">请选择资料并解析</td></tr>';
      $("tb-issues").innerHTML = '<tr><td colspan="5" class="empty">暂无校验异常</td></tr>';
      $("tables").innerHTML = "";
      $("stats").innerHTML = "";
    };
    $("doc").onchange = function () {
      DOC = Number($("doc").value) || null;
      if (DOC) loadExtracted();
    };
    document.querySelectorAll(".tab").forEach(function (t) {
      t.onclick = function () {
        document.querySelectorAll(".tab").forEach(function (x) { x.classList.remove("active"); });
        t.classList.add("active");
        document.querySelectorAll(".pane").forEach(function (p) { p.hidden = true; });
        $(t.getAttribute("data-pane")).hidden = false;
      };
    });
    document.addEventListener("click", function (e) {
      var t = e.target;
      if (!t || !t.getAttribute) return;
      var s = t.getAttribute("data-save");
      if (s) { saveField(Number(s)); return; }
      var rid = t.getAttribute("data-resolve");
      if (rid) { resolveIssue(Number(rid), t.getAttribute("data-to")); }
    });
  }

  /* P1-1 解析能力面板：字段数 / 行数上限档位 / 上限登记一致性（**全部取后端**，不硬编码）。*/
  async function loadCapability() {
    try {
      var m = await api(API + "/parse/meta");
      var fields = (((m.standard_fields || {}).fields) || []).length;
      var caps = m.row_caps || [];
      var ruleN = Object.keys(m.validation || {}).length;
      $("cap-stats").innerHTML =
        "<div><b>" + fields + "</b>标准字段</div>" +
        "<div><b>" + ruleN + "</b>校验规则</div>" +
        "<div><b>" + caps.length + "</b>行数上限档位</div>" +
        "<div><b>" + (m.row_cap_consistent ? "一致" : "不一致") + "</b>上限登记</div>";
      var notes = m.parse_notes || {};
      $("cap-caps").innerHTML =
        "上限档位：" + caps.map(function (c) {
          return c.cap + "（" + esc(c.note) + "）";
        }).join("；") +
        "<br>" + esc(notes.cursor || "") +
        "<br>" + esc(notes.truncation || "");
      await loadOcr();
    } catch (e) {
      $("cap-stats").innerHTML =
        '<div class="muted">解析能力信息不可用：' + esc(e.message) + "</div>";
    }
  }

  /* P1-2 OCR 引擎状态：可用性 / 首选 / 阈值 / 最近一次运行（**全部取后端**）。*/
  async function loadOcr() {
    var box = $("ocr-status");
    if (!box) return;
    try {
      var o = await api(API + "/ocr/meta");
      var engines = (o.engines || []).map(function (e) {
        return e.name + (e.available ? "✅" : "⛔");
      }).join("　");
      var last = o.last;
      box.innerHTML = "<b>OCR 引擎</b>（P1-2）：" + engines +
        "　首选：" + esc(o.preferred || "无") +
        "　低置信阈值：" + esc(String(o.conf_floor)) +
        (last ? "<br>最近一次：" + esc(last.engine) + "，" + last.segments + " 段，" +
                last.chars + " 字" + (last.reason ? "（" + esc(last.reason) + "）" : "")
              : "<br>本进程尚未执行过 OCR") +
        "<br>" + esc(o.note || "");
    } catch (e) {
      box.innerHTML = '<span class="muted">OCR 引擎状态不可用：' + esc(e.message) + "</span>";
    }
  }

  (async function init() {
    try {
      // R-4（2026-10-14）：原为 "/api/me" —— 该路径**后端并不存在**（实测 404），
      //   唯一权威是 `/api/auth/me`。原写法被 .catch 静默吞掉 ⇒ 右侧用户名不显示。
      var me = await api("/api/auth/me").catch(function () { return null; });
      if (me && me.username) $("whoami").textContent = me.username;
    } catch (e) { /* 未登录由全局 401 处理 */ }
    try {
      await loadMeta();
      PROJECT = await loadProjects();
    } catch (e) {
      flash("初始化失败：" + e.message, "err");
    }
    bind();
    await loadCapability();
    await loadDocs();
  })();
})();
