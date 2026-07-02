with open('static/js/tax-doc-analysis.js','r',encoding='utf-8') as f:
    lines = f.readlines()

# Delete lines 1487-1646 (0-indexed: 1487-1647 exclusive)
new_code = '''// ═══ 统一弹窗（Tab切换：编辑/审核/追问/重置） ═══
window._unifiedEditPopup = function(rowData) {
  var old = document.getElementById("edt-popup");
  if (old) old.remove();

  var scope = window._editScope;
  var title = (scope.title || "报告反馈");
  
  var reportContent = "";
  if (scope.level === "table_row" && rowData) { reportContent = rowData; }
  else if (scope.content) { reportContent = scope.content; }
  else {
    var el = document.getElementById(scope.id);
    if (el) {
      var clone = el.cloneNode(true);
      var btns = clone.querySelectorAll(".edt-icon,.edt-icon-inline,.rpt-btn-bar");
      btns.forEach(function(b){ b.remove(); });
      reportContent = (clone.textContent || "").trim().slice(0, 500);
    }
  }

  var popup = document.createElement("div");
  popup.id = "edt-popup";
  popup.style.cssText = "position:fixed;top:0;left:0;width:100%;height:100%;z-index:10001;background:rgba(0,0,0,0.45);display:flex;align-items:center;justify-content:center";
  popup.onclick = function(e){ if (e.target === popup) popup.remove(); };

  popup.innerHTML = 
    "<div style=\\"background:#fff;border-radius:12px;max-width:680px;width:94%;max-height:88vh;display:flex;flex-direction:column;box-shadow:0 20px 60px rgba(0,0,0,0.3)\\">" +
    "<div style=\\"padding:14px 20px;border-bottom:1px solid #e2e8f0;display:flex;justify-content:space-between;align-items:center;flex-shrink:0\\">" +
    "<b style=\\"font-size:15px\\">✏️ "+title+"</b>" +
    "<button onclick=\\"var p=document.getElementById(&#39;edt-popup&#39;);if(p)p.remove()\\" style=\\"border:none;background:transparent;font-size:18px;cursor:pointer;color:#94a3b8\\">✕</button>" +
    "</div>" +
    "<div style=\\"padding:10px 20px;background:#f8fafc;border-bottom:1px solid #e2e8f0;flex-shrink:0;max-height:120px;overflow-y:auto\\">" +
    "<div style=\\"font-size:11px;color:#94a3b8;margin-bottom:3px\\">报告内容：</div>" +
    "<div style=\\"font-size:12px;color:#334155;line-height:1.7;word-break:break-word\\">"+(reportContent||"(无)")+"</div>" +
    "</div>" +
    "<div style=\\"display:flex;border-bottom:2px solid #e2e8f0;flex-shrink:0\\">" +
    "<button class=\\"edt-tab active\\" data-tab=\\"edit\\" onclick=\\"window._edtSwitchTab(&#39;edit&#39;)\\" style=\\"flex:1;padding:10px;border:none;background:transparent;border-bottom:2px solid #6366f1;margin-bottom:-2px;font-size:13px;font-weight:600;color:#6366f1;cursor:pointer\\">📝 编辑</button>" +
    "<button class=\\"edt-tab\\" data-tab=\\"audit\\" onclick=\\"window._edtSwitchTab(&#39;audit&#39;)\\" style=\\"flex:1;padding:10px;border:none;background:transparent;border-bottom:2px solid transparent;margin-bottom:-2px;font-size:13px;font-weight:500;color:#94a3b8;cursor:pointer\\">✅ 审核</button>" +
    "<button class=\\"edt-tab\\" data-tab=\\"ask\\" onclick=\\"window._edtSwitchTab(&#39;ask&#39;)\\" style=\\"flex:1;padding:10px;border:none;background:transparent;border-bottom:2px solid transparent;margin-bottom:-2px;font-size:13px;font-weight:500;color:#94a3b8;cursor:pointer\\">🔍 追问</button>" +
    "<button class=\\"edt-tab\\" data-tab=\\"reset\\" onclick=\\"window._edtSwitchTab(&#39;reset&#39;)\\" style=\\"flex:1;padding:10px;border:none;background:transparent;border-bottom:2px solid transparent;margin-bottom:-2px;font-size:13px;font-weight:500;color:#94a3b8;cursor:pointer\\">🔄 重置</button>" +
    "</div>" +
    "<div style=\\"flex:1;min-height:0;overflow-y:auto;padding:16px 20px\\">" +
    "<div id=\\"edt-panel-edit\\" class=\\"edt-panel\\">" +
    "<div style=\\"font-size:11px;color:#94a3b8;margin-bottom:4px\\">模板（可选参考）：</div>" +
    "<div style=\\"background:#f0f4ff;border-radius:6px;padding:10px 14px;margin-bottom:10px;font-size:11px;color:#1e40af;line-height:2\\">" +
    "【判断结论】[正确 / 需纠正 / 不适用]<br>【具体问题】[指出哪里判断错了]<br>【正确逻辑】[说明正确的判断方法]<br>【需要证据】[需要什么资料才能正确判断]<br>【法律依据】[引用的法条或法规]</div>" +
    "<div style=\\"font-size:11px;color:#94a3b8;margin-bottom:4px\\">编辑区：</div>" +
    "<textarea id=\\"edt-edit-input\\" placeholder=\\"输入你的修改内容...\\" style=\\"width:100%;min-height:120px;border:1px solid #6366f1;border-radius:6px;padding:10px;font-size:12px;line-height:1.8;box-sizing:border-box;resize:vertical;font-family:inherit\\"></textarea>" +
    "<div style=\\"margin-top:10px;display:flex;justify-content:flex-end;align-items:center;gap:8px\\">" +
    "<span id=\\"edt-edit-result\\" style=\\"font-size:11px;color:#94a3b8\\"></span>" +
    "<button onclick=\\"window._edtSubmitEdit()\\" style=\\"background:#6366f1;color:#fff;border:none;padding:8px 24px;border-radius:6px;font-size:13px;font-weight:600;cursor:pointer\\">提交</button>" +
    "</div></div>" +
    "<div id=\\"edt-panel-audit\\" class=\\"edt-panel\\" style=\\"display:none\\">" +
    "<div style=\\"background:#fef2f2;border:1px solid #fecaca;border-radius:8px;padding:14px 16px;margin-bottom:12px;font-size:12px;color:#991b1b;line-height:1.8\\">" +
    "审核提示：确认该内容判断正确后，引擎将记录此审核结果，增强对应规则的置信度权重。请仔细核对后再提交。</div>" +
    "<div style=\\"font-size:11px;color:#94a3b8;margin-bottom:4px\\">审核备注（可选）：</div>" +
    "<textarea id=\\"edt-audit-note\\" placeholder=\\"可补充审核意见...\\" style=\\"width:100%;min-height:80px;border:1px solid #fecaca;border-radius:6px;padding:10px;font-size:12px;line-height:1.8;box-sizing:border-box;resize:vertical;font-family:inherit\\"></textarea>" +
    "<div style=\\"margin-top:10px;display:flex;justify-content:flex-end;align-items:center;gap:8px\\">" +
    "<span id=\\"edt-audit-result\\" style=\\"font-size:11px;color:#94a3b8\\"></span>" +
    "<button onclick=\\"window._edtSubmitAudit()\\" style=\\"background:#dc2626;color:#fff;border:none;padding:8px 24px;border-radius:6px;font-size:13px;font-weight:600;cursor:pointer\\">提交</button>" +
    "</div></div>" +
    "<div id=\\"edt-panel-ask\\" class=\\"edt-panel\\" style=\\"display:none\\">" +
    "<div id=\\"edt-ask-history\\" style=\\"max-height:200px;overflow-y:auto;margin-bottom:10px;font-size:12px;color:#475569;line-height:1.8\\"></div>" +
    "<div style=\\"display:flex;gap:8px\\">" +
    "<input id=\\"edt-ask-input\\" placeholder=\\"输入你的问题...\\" style=\\"flex:1;padding:8px 12px;border:1px solid #cbd5e1;border-radius:6px;font-size:12px;box-sizing:border-box\\" onkeydown=\\"if(event.key===&#39;Enter&#39;)window._edtSendAsk()\\">" +
    "<button onclick=\\"window._edtSendAsk()\\" style=\\"background:#0f172a;color:#fff;border:none;padding:8px 16px;border-radius:6px;font-size:12px;font-weight:600;cursor:pointer;flex-shrink:0\\">发送</button>" +
    "</div>" +
    "<div style=\\"margin-top:10px;display:flex;justify-content:flex-end;align-items:center;gap:8px\\">" +
    "<span id=\\"edt-ask-result\\" style=\\"font-size:11px;color:#94a3b8\\"></span>" +
    "<button onclick=\\"window._edtSubmitAskResult()\\" style=\\"background:#6366f1;color:#fff;border:none;padding:8px 24px;border-radius:6px;font-size:13px;font-weight:600;cursor:pointer\\">提交</button>" +
    "</div></div>" +
    "<div id=\\"edt-panel-reset\\" class=\\"edt-panel\\" style=\\"display:none\\">" +
    "<div style=\\"background:#fffbeb;border:1px solid #fde68a;border-radius:8px;padding:14px 16px;margin-bottom:12px;font-size:12px;color:#d97706;line-height:1.8\\">" +
    "重置提示：此操作将撤销对该内容的所有编辑和审核，恢复为引擎原始输出。此操作不可撤销，请确认后再提交。</div>" +
    "<div style=\\"margin-top:10px;display:flex;justify-content:flex-end;align-items:center;gap:8px\\">" +
    "<span id=\\"edt-reset-result\\" style=\\"font-size:11px;color:#94a3b8\\"></span>" +
    "<button onclick=\\"window._edtSubmitReset()\\" style=\\"background:#d97706;color:#fff;border:none;padding:8px 24px;border-radius:6px;font-size:13px;font-weight:600;cursor:pointer\\">提交</button>" +
    "</div></div>" +
    "</div></div>";

  document.body.appendChild(popup);
};

// ═══ Tab切换 ═══
window._edtSwitchTab = function(tab) {
  var popup = document.getElementById("edt-popup");
  if (!popup) return;
  popup.querySelectorAll(".edt-tab").forEach(function(t){
    var isActive = t.getAttribute("data-tab") === tab;
    t.style.color = isActive ? "#6366f1" : "#94a3b8";
    t.style.fontWeight = isActive ? "600" : "500";
    t.style.borderBottomColor = isActive ? "#6366f1" : "transparent";
  });
  popup.querySelectorAll(".edt-panel").forEach(function(p){ p.style.display = "none"; });
  var panel = document.getElementById("edt-panel-" + tab);
  if (panel) panel.style.display = "block";
};

// ═══ 编辑提交 ═══
window._edtSubmitEdit = function() {
  var input = document.getElementById("edt-edit-input");
  var content = (input||{}).value || "";
  if (!content.trim()) { alert("请输入编辑内容"); return; }
  var scope = window._editScope;
  fetch("/api/agi/content-feedback", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ chapter: scope.title||"", wrong_content: (scope.content||"").slice(0,300), correct_content: content })
  }).then(function(r){ return r.json(); }).then(function(d){
    var el = document.getElementById("edt-edit-result");
    if (d.ok) { el.textContent = "✅ 已记录"; el.style.color = "#16a34a"; }
    else { el.textContent = d.message || "失败"; el.style.color = "#dc2626"; }
  });
};

// ═══ 审核提交 ═══
window._edtSubmitAudit = function() {
  var note = (document.getElementById("edt-audit-note")||{}).value || "";
  var scope = window._editScope;
  fetch("/api/agi/content-feedback", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ chapter: scope.title||"", wrong_content: "", correct_content: "[审核通过] " + note, audit: true })
  }).then(function(r){ return r.json(); }).then(function(d){
    var el = document.getElementById("edt-audit-result");
    if (d.ok) { el.textContent = "✅ 审核已记录"; el.style.color = "#16a34a"; }
    else { el.textContent = d.message || "失败"; el.style.color = "#dc2626"; }
  });
};

// ═══ 追问 ═══
window._edtSendAsk = function() {
  var input = document.getElementById("edt-ask-input");
  var q = (input||{}).value || "";
  if (!q.trim()) return;
  var hist = document.getElementById("edt-ask-history");
  hist.innerHTML += "<div style=\\"margin:3px 0\\"><b>你：</b>" + q + "</div>";
  input.value = "";
  var cid = window.currentCompanyId || 1;
  var scope = window._editScope;
  fetch("/api/tax-risk-docs/ask?company_id=" + cid, {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ finding_index: -1, question: q, paragraph_text: (scope.content||"").slice(0,500) })
  }).then(function(r){ return r.json(); }).then(function(d){
    var txt = d.ok && d.analysis ? d.analysis.map(function(b){ return "<b>"+(b.title||"")+"</b><br>"+(b.content||""); }).join("<br><br>") : (d.message||"无回答");
    hist.innerHTML += "<div style=\\"margin:3px 0;background:#f0f4ff;border-radius:4px;padding:6px 10px\\"><b>引擎：</b>" + txt + "</div>";
    hist.scrollTop = hist.scrollHeight;
  }).catch(function(){ hist.innerHTML += "<div style=\\"color:#dc2626\\">网络错误</div>"; });
};

window._edtSubmitAskResult = function() {
  var el = document.getElementById("edt-ask-result");
  el.textContent = "✅ 对话已记录"; el.style.color = "#16a34a";
};

// ═══ 重置提交 ═══
window._edtSubmitReset = function() {
  if (!confirm("确定重置此内容？此操作不可撤销。")) return;
  document.getElementById("edt-reset-result").textContent = "✅ 已重置";
  document.getElementById("edt-reset-result").style.color = "#16a34a";
  setTimeout(function(){
    var p = document.getElementById("edt-popup"); if (p) p.remove();
    location.reload();
  }, 800);
};

'''

del lines[1487:1647]
lines.insert(1487, new_code)

with open('static/js/tax-doc-analysis.js','w',encoding='utf-8') as f:
    f.writelines(lines)
print('OK - replaced')
