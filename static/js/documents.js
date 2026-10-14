/* 资料上传与管理（P0-2）前端逻辑 —— 原生 JS，无框架、无构建（沿用现有技术栈）。
 *
 * 约定（与既有前端一致，勿另立一套）：
 *   · CSRF 由全局 fetch 拦截器自动附加（`security.js`）；401 亦由它跳 /login。
 *   · 分类/解析状态/上限等字典**一律取后端 /api/v1/documents/meta**（不硬编码）。
 *   · 断点续传：> 单请求上限（10MB）的文件自动走分片通道，刷新后可按 upload_id 续传
 *     （upload_id 存 localStorage，恢复时用 GET /chunk/{id} 查缺失分片）。
 */
(function () {
  "use strict";

  var API = "/api/v1";
  var META = null;
  var PROJECT = null;
  var state = { page: 1, page_size: 20, total: 0, pages: 0, items: [],
                deleting: null, classifying: null,
                selected: {},   // ★ 2026-10-15 批量删除：id -> true（翻页/刷新即清空）
                exDoc: null };  // ★ 2026-10-15 详情弹窗当前解析的资料 id

  function $(id) { return document.getElementById(id); }
  function esc(s) {
    return String(s === null || s === undefined ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function fmtSize(n) {
    n = Number(n || 0);
    if (n < 1024) return n + " B";
    if (n < 1024 * 1024) return (n / 1024).toFixed(1) + " KB";
    return (n / 1024 / 1024).toFixed(2) + " MB";
  }
  function flash(text, kind) {
    $("msg").innerHTML = text ? '<div class="msg ' + (kind || "ok") + '">' + esc(text) + "</div>" : "";
    if (text) { window.clearTimeout(flash._t); flash._t = window.setTimeout(function () { $("msg").innerHTML = ""; }, 5000); }
  }
  function openModal(id) { $(id).hidden = false; }
  function closeModal(id) { $(id).hidden = true; }

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

  // ── 项目下拉（资料归属项目）────────────────────────────────────────
  async function loadProjects() {
    var data = await api(API + "/projects?page_size=200");
    var sel = $("proj");
    sel.innerHTML = "";
    if (!data.items.length) {
      var o = document.createElement("option");
      o.value = ""; o.textContent = "（暂无项目，请先新建项目）";
      sel.appendChild(o);
      return null;
    }
    data.items.forEach(function (p) {
      var op = document.createElement("option");
      op.value = p.id; op.textContent = (p.code ? p.code + " " : "") + p.name;
      sel.appendChild(op);
    });
    var saved = localStorage.getItem("docProjectId");
    var pick = data.items.filter(function (p) { return String(p.id) === String(saved); })[0];
    sel.value = pick ? pick.id : data.items[0].id;
    return Number(sel.value);
  }

  // ── 字典 ───────────────────────────────────────────────────────────
  async function loadMeta() {
    META = await api(API + "/documents/meta");
    var cats = $("f-cat"), pss = $("f-status");
    META.categories.forEach(function (c) {
      var o = document.createElement("option"); o.value = c.value; o.textContent = c.label;
      cats.appendChild(o);
    });
    META.parse_statuses.forEach(function (s) {
      var o = document.createElement("option"); o.value = s.value; o.textContent = s.label;
      pss.appendChild(o);
    });
    var exts = META.extensions.map(function (e) { return e.value; }).join(" ");
    $("ext-hint").innerHTML = "支持格式：" + esc(exts)
      + "<br>单文件上限 " + fmtSize(META.limits.max_size)
      + "（更大文件自动走分片上传，上限 " + fmtSize(META.limits.resumable_max_size) + "）"
      + "<br>存储：" + esc(META.storage) + " ｜ 下载自动加水印";
  }

  // ── 上传（含分片/断点续传）─────────────────────────────────────────
  function qItem(name, size) {
    var el = document.createElement("div");
    el.className = "qitem";
    el.innerHTML = '<span class="nm">' + esc(name) + '</span>'
      + '<span class="sz">' + fmtSize(size) + '</span>'
      + '<span class="bar"><i></i></span><span class="st st-run">准备中</span>';
    $("queue").appendChild(el);
    return el;
  }
  function setQ(el, pct, text, cls) {
    el.querySelector(".bar > i").style.width = Math.max(0, Math.min(100, pct)) + "%";
    var st = el.querySelector(".st");
    st.className = "st " + (cls || "st-run");
    st.textContent = text;
  }

  /** 单请求上传（≤ 上限） */
  async function uploadOne(projectId, file) {
    var el = qItem(file.name, file.size);
    try {
      var fd = new FormData();
      fd.append("files", file, file.name);
      setQ(el, 30, "上传中");
      var res = await fetch(API + "/projects/" + projectId + "/documents",
                            { method: "POST", body: fd });
      var data = await res.json();
      if (!res.ok) throw new Error((data && data.detail) || ("HTTP " + res.status));
      if (data.uploaded && data.uploaded.length) {
        setQ(el, 100, "已完成", "st-ok");
        return { ok: true, item: data.uploaded[0] };
      }
      if (data.duplicated && data.duplicated.length) {
        var d = data.duplicated[0];
        setQ(el, 100, "重复跳过", "st-dup");
        return { ok: true, duplicated: true, detail: d };
      }
      var r = (data.rejected && data.rejected[0]) || {};
      setQ(el, 100, "已拒绝", "st-err");
      return { ok: false, detail: r.reason || "被拒绝" };
    } catch (e) {
      setQ(el, 100, "失败", "st-err");
      return { ok: false, detail: e.message };
    }
  }

  /** 分片上传（断点续传）；upload_id 存 localStorage 以支持刷新后继续 */
  async function uploadChunked(projectId, file) {
    var el = qItem(file.name + "（分片）", file.size);
    var key = "docUpload_" + projectId + "_" + file.name + "_" + file.size;
    try {
      var uploadId = localStorage.getItem(key);
      var info = null;
      if (uploadId) {
        try { info = await api(API + "/documents/chunk/" + uploadId); }
        catch (e) { uploadId = null; info = null; }
      }
      if (!info) {
        var init = await api(API + "/documents/chunk/init", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ project_id: projectId, filename: file.name, size: file.size })
        });
        uploadId = init.upload_id;
        info = { chunks_total: init.chunks_total, received: [], missing: [] };
        localStorage.setItem(key, uploadId);
      }
      setQ(el, 5, "续传中");
      var cs = (META && META.limits.chunk_size) || 5 * 1024 * 1024;
      var total = info.chunks_total;
      var done = (info.received || []).length;
      for (var i = 0; i < total; i++) {
        if ((info.received || []).indexOf(i) >= 0) continue;
        var blob = file.slice(i * cs, Math.min((i + 1) * cs, file.size));
        var r = await fetch(API + "/documents/chunk/" + uploadId + "/" + i,
                            { method: "PUT", body: blob });
        if (!r.ok) {
          var d = null; try { d = await r.json(); } catch (e2) {}
          throw new Error((d && d.detail) || ("分片 " + i + " 上传失败"));
        }
        done++;
        setQ(el, Math.round(done / total * 92), "分片 " + done + "/" + total);
      }
      var fin = await api(API + "/documents/chunk/" + uploadId + "/complete",
                          { method: "POST" });
      localStorage.removeItem(key);
      if (fin.uploaded && fin.uploaded.length) {
        setQ(el, 100, "已完成", "st-ok");
        return { ok: true, item: fin.uploaded[0] };
      }
      if (fin.duplicated && fin.duplicated.length) {
        setQ(el, 100, "重复跳过", "st-dup");
        return { ok: true, duplicated: true, detail: fin.duplicated[0] };
      }
      var rr = (fin.rejected && fin.rejected[0]) || {};
      setQ(el, 100, "已拒绝", "st-err");
      return { ok: false, detail: rr.reason || "被拒绝" };
    } catch (e) {
      setQ(el, 100, "失败（可重试）", "st-err");
      return { ok: false, detail: e.message };
    }
  }

  async function handleFiles(fileList) {
    if (!PROJECT) { flash("请先选择项目", "err"); return; }
    var files = Array.prototype.slice.call(fileList || []);
    if (!files.length) return;
    var max1 = (META && META.limits.max_size) || 10485760;
    var maxR = (META && META.limits.resumable_max_size) || 209715200;
    var okN = 0, dupN = 0, badN = 0;
    for (var i = 0; i < files.length; i++) {
      var f = files[i], r;
      if (f.size > maxR) {
        var el = qItem(f.name, f.size);
        setQ(el, 100, "超过上限", "st-err");
        badN++; continue;
      }
      r = f.size > max1 ? await uploadChunked(PROJECT, f) : await uploadOne(PROJECT, f);
      if (r.ok && r.duplicated) dupN++;
      else if (r.ok) okN++;
      else badN++;
      if (!r.ok && r.detail) flash(f.name + "：" + r.detail, "err");
    }
    flash("本次上传：成功 " + okN + " 个，跳过重复 " + dupN + " 个，失败 " + badN + " 个",
          badN ? "warn" : "ok");
    await loadList();
  }

  // ── 列表 ───────────────────────────────────────────────────────────
  async function loadList() {
    if (!PROJECT) { $("tbody").innerHTML = '<tr><td colspan="8" class="empty">请先选择项目</td></tr>'; return; }
    var p = new URLSearchParams();
    var q = $("q").value.trim(); if (q) p.set("q", q);
    if ($("f-cat").value) p.set("category", $("f-cat").value);
    if ($("f-status").value) p.set("parse_status", $("f-status").value);
    p.set("page", state.page); p.set("page_size", $("f-size").value);
    $("tbody").innerHTML = '<tr><td colspan="8" class="empty">加载中…</td></tr>';
    try {
      var d = await api(API + "/projects/" + PROJECT + "/documents?" + p.toString());
      state.items = d.items || []; state.total = d.total; state.pages = d.pages; state.page = d.page;
      renderList();
    } catch (e) {
      $("tbody").innerHTML = '<tr><td colspan="8" class="empty">加载失败：' + esc(e.message) + "</td></tr>";
    }
  }

  function renderList() {
    var tb = $("tbody");
    state.selected = state.selected || {};
    Object.keys(state.selected).forEach(function (k) {   // ★ 翻页/刷新即清空失效选中
      if (!state.items.some(function (d) { return String(d.id) === String(k); })) delete state.selected[k];
    });
    if (!state.items.length) {
      $("tbody").innerHTML = '<tr><td colspan="8" class="empty">暂无资料。拖拽文件到上方区域即可上传。</td></tr>';
    } else {
      tb.innerHTML = state.items.map(function (d) {
        var rows = d.pages_ref || "";
        return '<tr>' +
          '<td style="text-align:center"><input type="checkbox" class="row-sel" data-id="' + d.id + '"' +
            (state.selected[String(d.id)] ? " checked" : "") + '></td>' +
          '<td class="wrap-cell" title="原件名：' + esc(d.original_name) + '"><b>' + esc(d.original_name_masked || d.original_name) + '</b>' +
            (d.original_name_masked && d.original_name_masked !== d.original_name
              ? '<br><span class="muted" style="font-size:11px">（显示已脱敏，原件名保留可追溯）</span>' : '') + '</td>' +
          '<td><span class="tag cat-' + esc(d.category) + '">' + esc(d.category_cn) + '</span>' +
            (d.classify_by === "manual" ? '<br><span class="muted" style="font-size:11px">人工修正</span>' : '') + '</td>' +
          '<td><span class="tag ps-' + esc(d.parse_status) + '">' + esc(d.parse_status_cn) + '</span></td>' +
          '<td>' + fmtSize(d.size) + '</td>' +
          '<td>' + esc(String(d.uploaded_at || "").slice(0, 19).replace("T", " ")) + '</td>' +
          '<td>' + esc(d.uploaded_by || "—") + '</td>' +
          '<td>' +
            '<button class="btn ghost" data-act="detail" data-id="' + d.id + '">详情</button> ' +
            '<button class="btn ghost" data-act="classify" data-id="' + d.id + '">分类</button> ' +
            '<button class="btn ghost" data-act="download" data-id="' + d.id + '">下载</button> ' +
            '<button class="btn danger" data-act="del" data-id="' + d.id + '">删除</button>' +
          '</td></tr>';
      }).join("");
    }
    var n = Object.keys(state.selected).length;
    var btn = $("btn-del-selected");
    if (btn) { btn.hidden = n === 0; btn.textContent = "删除选中（" + n + "）"; }
    var sa = $("sel-all");
    if (sa) sa.checked = state.items.length > 0 &&
      state.items.every(function (d) { return state.selected[String(d.id)]; });
    $("count").textContent = "共 " + state.total + " 条";
    $("pageinfo").textContent = state.pages ? ("第 " + state.page + " / " + state.pages + " 页") : "";
    $("prev").disabled = state.page <= 1;
    $("next").disabled = state.pages === 0 || state.page >= state.pages;
  }

  // ── 详情 / 分类 / 下载 / 删除 ─────────────────────────────────────
  async function openDetail(id) {
    openModal("m-detail");
    $("detail-body").innerHTML = "加载中…";
    try {
      var d = await api(API + "/documents/" + id);
      $("detail-title").textContent = "资料详情：" + (d.original_name_masked || d.original_name);
      var pages = (d.pages || []).map(function (p) {
        return '<tr><td>' + p.page_no + '</td><td>' + (p.char_count || 0) + '</td><td>' +
          esc(p.status) + '</td></tr>';
      }).join("") || '<tr><td colspan="3" class="muted">暂无分页记录</td></tr>';
      $("detail-body").innerHTML =
        '<div class="kv">' +
        '<div class="k">文件名(显示)</div><div>' + esc(d.original_name_masked) + '</div>' +
        '<div class="k">文件名(原件)</div><div>' + esc(d.original_name) + '</div>' +
        '<div class="k">分类</div><div>' + esc(d.category_cn) + '（' +
          (d.classify_by === "manual" ? "人工修正" : "自动识别") + '）</div>' +
        '<div class="k">解析状态</div><div>' + esc(d.parse_status_cn) + '</div>' +
        '<div class="k">大小 / 扩展名</div><div>' + fmtSize(d.size) + ' / ' + esc(d.ext_cn) + '</div>' +
        '<div class="k">MD5</div><div style="word-break:break-all">' + esc(d.md5 || "—") + '</div>' +
        '<div class="k">SHA256</div><div style="word-break:break-all">' + esc(d.sha256 || "—") + '</div>' +
        '<div class="k">上传人 / 时间</div><div>' + esc(d.uploaded_by || "—") + '　' +
          esc(String(d.uploaded_at || "").slice(0, 19).replace("T", " ")) + '</div>' +
        '<div class="k">下载水印</div><div>' + (d.watermark_on_download ? "开启" : "关闭") + '</div>' +
        '</div>' +
        '<div style="margin-top:14px;font-weight:700;font-size:13px;color:#334155">分页记录（' +
          (d.pages || []).length + '）</div>' +
        '<table class="grid" style="margin-top:6px"><thead><tr><th>页</th><th>字符数</th><th>状态</th></tr></thead>' +
        '<tbody>' + pages + '</tbody></table>';
      // ★ 2026-10-15 解析与标准化融入：详情即含解析结果（原 /extract 页能力）
      state.exDoc = id;
      $("ex-wrap").hidden = false;
      $("ex-hint").textContent = "";
      await loadExtractedInto(id);
    } catch (e) {
      $("detail-body").innerHTML = '<div class="msg err">' + esc(e.message) + "</div>";
    }
  }

  // ── ★ 2026-10-15 解析与标准化融入（自 /extract 页移植；同一 API，零后端改动）──
  var EX_META = null;
  function loadExtractMeta() {
    api(API + "/extract/meta").then(function (m) { EX_META = m; }).catch(function () { EX_META = null; });
  }
  function cnDomain(code) {
    if (!EX_META) return code || "";
    var hit = (EX_META.standard_fields.domains || []).filter(function (d) { return d.value === code; })[0];
    return hit ? hit.label : (code || "");
  }
  function cnField(name) {
    if (!EX_META) return name || "";
    var hit = (EX_META.standard_fields.fields || []).filter(function (f) { return f.name === name; })[0];
    return hit ? hit.cn : (name || "");
  }
  async function loadExtractedInto(id) {
    try {
      var d = await api(API + "/documents/" + id + "/extracted");
      exRenderStats(d); exRenderFields(d); exRenderIssues(d); exRenderTables(d);
    } catch (e) {
      $("ex-hint").textContent = "加载解析结果失败：" + e.message;
    }
  }
  async function exReparse() {
    if (!state.exDoc) return;
    $("ex-reparse").disabled = true;
    $("ex-hint").textContent = "解析中…";
    try {
      var r = await api(API + "/documents/" + state.exDoc + "/extract", { method: "POST" });
      $("ex-hint").textContent = "解析完成（作业 " + (r.job_id || "-") + "）";
      if (r.parse_error) flash("解析提示：" + r.parse_error, "warn");
      else flash("解析完成：表 " + (r.tables || []).length + " 张、" +
                 (r.fields || []).length + " 个标准字段、" +
                 (r.issues || []).length + " 条校验异常");
      await loadExtractedInto(state.exDoc);
    } catch (e) {
      $("ex-hint").textContent = "";
      flash("解析失败：" + e.message, "err");
    } finally {
      $("ex-reparse").disabled = false;
    }
  }
  function exRenderStats(d) {
    var s = d.issue_summary || {};
    var errs = (s.by_severity || {}).error || 0;
    var warns = (s.by_severity || {}).warning || 0;
    $("ex-stats").innerHTML =
      '<div><b>' + (d.tables || []).length + '</b> 解析表格</div>' +
      '<div><b>' + (d.fields || []).length + '</b> 标准字段</div>' +
      '<div><b>' + (d.issues || []).length + '</b> 校验异常</div>' +
      '<div><b style="color:' + (errs ? "#b91c1c" : "#334155") + '">' + errs + '</b> 严重(error)</div>' +
      '<div><b style="color:' + (warns ? "#b45309" : "#334155") + '">' + warns + '</b> 提示(warning)</div>' +
      '<div><b>' + (d.fields || []).filter(function (f) { return f.corrected; }).length + '</b> 已人工校正</div>';
  }
  function exRenderFields(d) {
    var tb = $("ex-tb-fields");
    var fs = d.fields || [];
    if (!fs.length) {
      tb.innerHTML = '<tr><td colspan="6" class="empty">未登记到标准字段（可能该格式暂不支持结构化解析，或字段名未在字典中）</td></tr>';
      return;
    }
    tb.innerHTML = fs.map(function (f) {
      var src = f.source || {};
      var shown = f.value_amount !== null && f.value_amount !== undefined
        ? f.value_amount : (f.value_period || f.value_text || "");
      return '<tr>' +
        '<td>' + esc(cnDomain(f.domain)) + '</td>' +
        '<td><b>' + esc(f.field_cn || cnField(f.standard_field)) + '</b>' +
          '<br><span class="muted" style="font-size:11px">' + esc(f.standard_field) + '</span></td>' +
        '<td>' + esc(src.raw === undefined ? "" : src.raw) + '</td>' +
        '<td' + (f.corrected ? ' style="color:#b45309"' : '') + '>' + esc(shown) +
          (f.corrected ? '<br><span class="muted" style="font-size:11px">已校正（原值 ' + esc(f.original_value || "") + '）</span>' : '') + '</td>' +
        '<td class="muted" style="font-size:11px">' +
          esc((src.sheet ? src.sheet + " / " : "") + "第 " + (src.row || "?") + " 行") + '</td>' +
        '<td><input type="text" data-fid="' + f.id + '" value="' + esc(shown) + '" style="width:130px"> ' +
          '<button class="btn ghost" data-save="' + f.id + '">保存</button></td>' +
      '</tr>';
    }).join("");
  }
  function exRenderIssues(d) {
    var tb = $("ex-tb-issues");
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
        '<td>' + (x.severity === "error" ? '<b style="color:#b91c1c">严重</b>' : '提示') + '</td>' +
        '<td>' + esc(x.message || "") + '</td>' +
        '<td>' + esc(stCn) + '</td>' +
        '<td>' + (st === "open"
          ? '<button class="btn ghost" data-resolve="' + x.id + '" data-to="resolved">标记已处理</button> ' +
            '<button class="btn ghost" data-resolve="' + x.id + '" data-to="ignored">确认非问题</button>'
          : '<span class="muted">—</span>') + '</td>' +
      '</tr>';
    }).join("");
  }
  function exRenderTables(d) {
    var box = $("ex-tables");
    var ts = d.tables || [];
    if (!ts.length) { box.innerHTML = '<div class="empty">暂无解析产物</div>'; return; }
    box.innerHTML = ts.map(function (t) {
      var rows = t.rows_preview || [];
      var cols = rows.length ? Object.keys(rows[0]) : [];
      var head = '<tr>' + cols.map(function (c) { return '<th>' + esc(c) + '</th>'; }).join("") + '</tr>';
      var body = rows.map(function (r) {
        return '<tr>' + cols.map(function (c) { return '<td>' + esc(r[c]) + '</td>'; }).join("") + '</tr>';
      }).join("");
      return '<div style="margin-bottom:14px">' +
        '<div style="font-size:13px;font-weight:700;margin-bottom:6px">' +
          '表' + (t.sheet_name ? '「' + esc(t.sheet_name) + '」' : '') +
          '　<span class="muted" style="font-weight:400;font-size:12px">' +
          '识别类型 ' + esc(t.doc_type || "(未识别)") + '　置信度 ' + esc(t.confidence) +
          '　共 ' + t.row_count + ' 行 × ' + t.col_count + ' 列（仅预览前 ' + rows.length + ' 行）</span></div>' +
        '<table class="grid"><thead>' + head + '</thead><tbody>' + body + '</tbody></table>' +
      '</div>';
    }).join("");
  }
  async function exSaveField(fid) {
    var input = document.querySelector('input[data-fid="' + fid + '"]');
    if (!input) return;
    try {
      var r = await api(API + "/extracted/" + fid, {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ value: input.value })
      });
      flash("已校正「" + (r.field_cn || r.standard_field) + "」：" + r.previous_value + " → " + r.value);
      await loadExtractedInto(state.exDoc);
    } catch (e) {
      flash("校正失败：" + e.message, "err");
    }
  }
  async function exResolveIssue(iid, to) {
    try {
      await api(API + "/extract/issues/" + iid + "/resolve", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: to })
      });
      flash(to === "resolved" ? "已标记为已处理" : "已确认非问题");
      await loadExtractedInto(state.exDoc);
    } catch (e) {
      flash("操作失败：" + e.message, "err");
    }
  }

  function openClassify(d) {
    state.classifying = d;
    $("cl-name").textContent = d.original_name;
    var sel = $("cl-cat");
    sel.innerHTML = "";
    META.categories.forEach(function (c) {
      var o = document.createElement("option");
      o.value = c.value; o.textContent = c.label;
      if (c.value === d.category) o.selected = true;
      sel.appendChild(o);
    });
    $("cl-note").value = "";
    openModal("m-classify");
  }

  async function saveClassify() {
    if (!state.classifying) return;
    try {
      var r = await api(API + "/documents/" + state.classifying.id + "/classify", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ category: $("cl-cat").value, note: $("cl-note").value || null })
      });
      closeModal("m-classify");
      flash("分类已修正为「" + r.category_cn + "」");
      state.classifying = null;
      await loadList();
    } catch (e) {
      flash("修正失败：" + e.message, "err");
    }
  }

  async function downloadDoc(id) {
    try {
      var res = await fetch(API + "/documents/" + id + "/download");
      if (!res.ok) {
        var d = null; try { d = await res.json(); } catch (e) {}
        throw new Error((d && d.detail) || ("HTTP " + res.status));
      }
      var mode = res.headers.get("X-Watermark-Mode") || "";
      var msgText = res.headers.get("X-Watermark-Message") || "";
      try { msgText = decodeURIComponent(msgText); } catch (e) {}
      var blob = await res.blob();
      var cd = res.headers.get("Content-Disposition") || "";
      var m = /filename\*=UTF-8''([^;]+)/.exec(cd);
      var name = m ? decodeURIComponent(m[1]) : "download";
      var a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = name;
      document.body.appendChild(a); a.click();
      document.body.removeChild(a);
      setTimeout(function () { URL.revokeObjectURL(a.href); }, 4000);
      // ★ 水印形态**如实告知**：嵌入式 / 随附式（不静默）
      flash(mode === "embedded" ? "已下载（水印已嵌入文件）"
                                : ("已下载（" + (msgText || "该格式随附水印说明") + "）"),
            mode === "embedded" ? "ok" : "warn");
    } catch (e) {
      flash("下载失败：" + e.message, "err");
    }
  }

  function askDelete(d) {
    state.deleting = d;
    $("del-name").textContent = d.original_name_masked || d.original_name;
    openModal("m-del");
  }
  // ★ 2026-10-15 批量删除：逐条走**同一删除权威出口**（DELETE /documents/{id}，
  //    回收站 + 审计每条独立留痕），结果如实汇总（成功/失败分开报）。
  window.__delSelected = async function () {
    var ids = Object.keys(state.selected).map(Number);
    if (!ids.length) return;
    if (!window.confirm("确定删除选中的 " + ids.length + " 条资料？\n文件将移入回收站（可回滚），删除操作逐条留审计。")) return;
    var okN = 0, errs = [];
    for (var i = 0; i < ids.length; i++) {
      try {
        await api(API + "/documents/" + ids[i], { method: "DELETE" });
        okN++;
      } catch (e) {
        errs.push("ID " + ids[i] + "：" + e.message);
      }
    }
    state.selected = {};
    flash("已删除 " + okN + " 条" + (errs.length ? ("；失败 " + errs.length + " 条：" + errs.join("；")) : ""),
          errs.length ? "err" : "");
    await loadList();
  };
  async function doDelete() {
    if (!state.deleting) return;
    try {
      var r = await api(API + "/documents/" + state.deleting.id, { method: "DELETE" });
      closeModal("m-del");
      flash(r.message || "资料已删除");
      state.deleting = null;
      await loadList();
    } catch (e) {
      closeModal("m-del");
      flash("删除失败：" + e.message, "err");
    }
  }

  // ── 事件 ───────────────────────────────────────────────────────────
  function bind() {
    var drop = $("drop");
    drop.onclick = function () { $("picker").click(); };
    $("picker").onchange = function (e) { handleFiles(e.target.files); e.target.value = ""; };
    ["dragenter", "dragover"].forEach(function (ev) {
      drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.add("hot"); });
    });
    ["dragleave", "drop"].forEach(function (ev) {
      drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.remove("hot"); });
    });
    drop.addEventListener("drop", function (e) {
      handleFiles(e.dataTransfer && e.dataTransfer.files);
    });
    // 页面级拖拽也接收（避免拖到空白处被浏览器打开）
    document.addEventListener("dragover", function (e) { e.preventDefault(); });
    document.addEventListener("drop", function (e) {
      if (e.target === drop || drop.contains(e.target)) return;
      e.preventDefault();
      handleFiles(e.dataTransfer && e.dataTransfer.files);
    });

    $("btn-search").onclick = function () { state.page = 1; loadList(); };
    $("btn-reset").onclick = function () {
      $("q").value = ""; $("f-cat").value = ""; $("f-status").value = ""; state.page = 1; loadList();
    };
    $("q").addEventListener("keydown", function (e) { if (e.key === "Enter") { state.page = 1; loadList(); } });
    $("f-size").onchange = function () { state.page = 1; loadList(); };
    $("prev").onclick = function () { if (state.page > 1) { state.page--; loadList(); } };
    $("next").onclick = function () { if (state.page < state.pages) { state.page++; loadList(); } };
    $("btn-classify-save").onclick = saveClassify;
    $("btn-del-confirm").onclick = doDelete;
    $("proj").onchange = function () {
      PROJECT = Number($("proj").value) || null;
      localStorage.setItem("docProjectId", String(PROJECT || ""));
      state.page = 1;
      loadList();
    };
    document.querySelectorAll("[data-close]").forEach(function (el) {
      el.onclick = function () { closeModal(el.getAttribute("data-close")); };
    });
    document.addEventListener("click", function (e) {
      var t = e.target;
      if (!t || !t.getAttribute) return;
      var act = t.getAttribute("data-act");
      if (!act) return;
      var id = Number(t.getAttribute("data-id"));
      var d = state.items.filter(function (x) { return x.id === id; })[0];
      if (act === "detail") openDetail(id);
      else if (act === "classify" && d) openClassify(d);
      else if (act === "download") downloadDoc(id);
      else if (act === "del" && d) askDelete(d);
    });
    // ★ 2026-10-15 解析区块交互：重跑 / 字段校正 / 异常处理
    var _exr = $("ex-reparse");
    if (_exr) _exr.addEventListener("click", exReparse);
    var _exw = $("ex-wrap");
    if (_exw) _exw.addEventListener("click", function (e) {
      var t = e.target;
      if (!t || !t.getAttribute) return;
      var sv = t.getAttribute("data-save");
      if (sv) exSaveField(Number(sv));
      var rv = t.getAttribute("data-resolve");
      if (rv) exResolveIssue(Number(rv), t.getAttribute("data-to"));
    });
    $("tbody").addEventListener("change", function (e) {   // ★ 行选择框
      var t = e.target;
      if (t && t.classList && t.classList.contains("row-sel")) {
        var id = String(t.getAttribute("data-id"));
        if (t.checked) state.selected[id] = true; else delete state.selected[id];
        var n = Object.keys(state.selected).length;
        var btn = $("btn-del-selected");
        if (btn) { btn.hidden = n === 0; btn.textContent = "删除选中（" + n + "）"; }
        var sa = $("sel-all");
        if (sa) sa.checked = state.items.length > 0 &&
          state.items.every(function (d) { return state.selected[String(d.id)]; });
      }
    });
    var _sa = $("sel-all");                                 // ★ 全选/全不选（本页）
    if (_sa) _sa.addEventListener("change", function () {
      state.selected = {};
      if (_sa.checked) state.items.forEach(function (d) { state.selected[String(d.id)] = true; });
      document.querySelectorAll("#tbody input.row-sel").forEach(function (cb) {
        cb.checked = _sa.checked;
      });
      var btn = $("btn-del-selected");
      var n = Object.keys(state.selected).length;
      if (btn) { btn.hidden = n === 0; btn.textContent = "删除选中（" + n + "）"; }
    });
    ["m-classify", "m-detail", "m-del"].forEach(function (id) {
      $(id).addEventListener("click", function (e) { if (e.target === $(id)) $(id).hidden = true; });
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") ["m-classify", "m-detail", "m-del"].forEach(function (i) { $(i).hidden = true; });
    });
  }

  (async function init() {
    try {
      loadExtractMeta();   // ★ 解析字典（域/字段中文名），失败静默降级为代码显示
      // R-4（2026-10-14）：原为 "/api/me" —— 该路径**后端并不存在**（实测 404），
      //   唯一权威是 `/api/auth/me`（P0-8 之前就有）。原写法被 .catch 静默吞掉，
      //   导致子页面右上角用户名永远不显示（无人报错 ⇒ 属"静默降级"）。
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
    await loadList();
  })();
})();
