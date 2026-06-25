"""Add dynamic trigger status to 线索链 and 证据链 tabs."""
import re

with open('static/js/tax-risk-rules.js', 'r', encoding='utf-8') as f:
    content = f.read()

# ============================================================
# Part 1: filterChains — add dynamic trigger status overlay
# ============================================================

old_chain_start = "  if (!filtered.length) { body.innerHTML = '<div style=\"text-align:center;padding:40px;color:var(--gray-400)\">"

old_chain_end = """  var hc = document.getElementById('chain-header-count');
  if (hc) hc.textContent = trailCount;"""

if old_chain_start not in content:
    print("ERROR: filterChains anchor1 not found")
elif old_chain_end not in content:
    print("ERROR: filterChains anchor2 not found")
else:
    # Build the replacement
    new_chain = """  // build dynamic trigger map from last analysis
  var execMap = {};
  if (_chainDynamic && _chainDynamic.chain_execution) {
    _chainDynamic.chain_execution.forEach(function(ce) { execMap[ce.chain_name] = ce; });
  }
  var hasDynamic = Object.keys(execMap).length > 0;
  var triggeredTotal = 0;

  if (!filtered.length) { body.innerHTML = '<div style=\"text-align:center;padding:40px;color:var(--gray-400)\">\u65e0\u5339\u914d\u7ebf\u7d22\u94fe</div>'; } else {
    var html = '';
    if (hasDynamic && _chainDynamic) {
      html += '<div style=\"display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px\">'
        + '<span style=\"padding:4px 12px;border-radius:4px;font-size:10px;background:#eff6ff;border:1px solid #bfdbfe;color:#1e40af\"><b>\u603b\u89e6\u53d1\u94fe\u6570\uff1a</b>' + (_chainDynamic.triggered_count||0) + '</span>'
        + '<span style=\"padding:4px 12px;border-radius:4px;font-size:10px;background:#fef3c7;border:1px solid #fde68a;color:#92400e\"><b>\u95ed\u73af\u8bc1\u636e\u94fe\uff1a</b>' + (_chainDynamic.closed_count||0) + '</span>'
        + '</div>';
    }
    filtered.forEach(function(c) {
      var exec = execMap[c.name];
      var triggeredSteps = exec ? exec.triggered_steps : 0;
      var totalSteps = exec ? exec.total_steps : c.steps;
      var ratio = exec ? exec.triggered_ratio : 0;
      if (exec && exec.triggered_steps > 0) triggeredTotal++;

      var borderColor = ratio >= 80 ? '#dc2626' : (ratio >= 50 ? '#f59e0b' : (ratio > 0 ? '#059669' : 'var(--gray-200)'));
      var badgeHtml = '';
      if (exec && exec.triggered_steps > 0) {
        badgeHtml = ' <span style=\"background:' + (ratio >= 60 ? '#dc2626' : '#059669') + '15;color:' + (ratio >= 60 ? '#dc2626' : '#059669') + ';padding:1px 6px;border-radius:3px;font-size:9px;font-weight:700\">\u26a1 ' + triggeredSteps + '/' + totalSteps + ' (' + ratio + '%)</span>';
      }

      html += '<div style=\"border:2px solid ' + borderColor + ';border-radius:6px;padding:14px;margin-bottom:10px;background:#fff\">'
        + '<div style=\"font-weight:700;font-size:13px;margin-bottom:6px\">'+c.name+' <span style=\"font-weight:400;font-size:10px;color:var(--gray-400)\">'+c.steps+'\u6b65</span>' + badgeHtml + '</div>'
        + '<div style=\"display:flex;flex-wrap:wrap;gap:6px;align-items:center\">';
      (c.investigation_path||[]).forEach(function(s, idx) {
        var dot = s.level==='\u9ad8\u98ce\u9669'?'#dc2626':(s.level==='\u4e2d\u98ce\u9669'?'#f59e0b':'#94a3b8');
        var stepBg = '#f1f5f9';
        if (exec && exec.triggered_steps > 0) {
          stepBg = ratio >= 60 ? '#fef2f2' : '#f0fdf4';
          dot = ratio >= 60 ? '#dc2626' : '#059669';
        }
        html += '<span style=\"background:'+stepBg+';padding:3px 8px;border-radius:3px;font-size:10px;border-left:2px solid '+dot+'\">'+s.step+'</span>';
        if (idx < (c.investigation_path||[]).length - 1) html += '<span style=\"color:#94a3b8;font-weight:700\">-</span>';
      });
      html += '</div></div>';
    })
    html += '</div>';
    body.innerHTML = html;
  }
  var stats = document.getElementById('chain-stats');
  var trailCount = _allChains.filter(function(c){return c.chain_type==='\u7ebf\u7d22\u94fe';}).length;
  var statsText = '\u5171 ' + filtered.length + ' \u6761\u7ebf\u7d22\u94fe';
  if (hasDynamic && filtered.length > 0) statsText += ' | \u5df2\u89e6\u53d1 ' + triggeredTotal + ' \u6761';
  if (stats) stats.textContent = statsText;
  var hc = document.getElementById('chain-header-count');
  if (hc) hc.textContent = trailCount + (hasDynamic && _chainDynamic && _chainDynamic.triggered_count ? ' (' + _chainDynamic.triggered_count + '\u89e6\u53d1)' : '');"""

    # Find the section between the two anchors
    start_idx = content.find(old_chain_start)
    end_idx = content.find(old_chain_end, start_idx) + len(old_chain_end)
    
    if start_idx < 0 or end_idx < start_idx:
        print("ERROR: could not locate bounds")
    else:
        content = content[:start_idx] + new_chain + content[end_idx:]
        print("filterChains: updated successfully")

# ============================================================
# Part 2: filterEvidence — add evidence closure status
# ============================================================

old_ev_line = "      html += '<div style=\"border:1px solid var(--gray-200);border-radius:6px;padding:16px;margin-bottom:12px;background:#fff\">'"

if old_ev_line not in content:
    print("ERROR: filterEvidence anchor not found")
else:
    new_ev_line = """      // dynamic evidence closure status
      var evExecMap = {};
      if (_chainDynamic && _chainDynamic.evidence_closures) {
        _chainDynamic.evidence_closures.forEach(function(ec) { evExecMap[ec.chain_name] = ec; });
      }
      var evExec = evExecMap[c.name];
      var evBorder = evExec ? (evExec.closed ? '#dc2626' : '#f59e0b') : 'var(--gray-200)';
      var evBadge = evExec ? (' <span style=\"background:' + (evExec.closed ? '#dc2626' : '#f59e0b') + '15;color:' + (evExec.closed ? '#dc2626' : '#f59e0b') + ';padding:1px 6px;border-radius:3px;font-size:9px;font-weight:700\">' + (evExec.closed ? '\U0001f512\u95ed\u73af' : '\u26a0\u672a\u95ed\u73af') + ' ' + evExec.ratio + '%</span>') : '';

      html += '<div style=\"border:2px solid ' + evBorder + ';border-radius:6px;padding:16px;margin-bottom:12px;background:#fff\">'"""

    content = content.replace(old_ev_line, new_ev_line)
    print("filterEvidence: updated successfully")

# ============================================================
# Part 3: Add dynamic stats at filterEvidence end
# ============================================================
old_ev_end = """  var stats = document.getElementById('evidence-stats');
  if (stats) stats.textContent = '\u5171 ' + filtered.length + ' \u6761\u8bc1\u636e\u94fe';"""

if old_ev_end not in content:
    print(f"ERROR: filterEvidence end anchor not found. Looking...")
    # search for evidence-stats
    idx = content.find("evidence-stats")
    if idx > 0:
        print(f"  Found at char {idx}: {content[idx:idx+80]}")
else:
    new_ev_end = """  var stats = document.getElementById('evidence-stats');
  var closedInFiltered = 0;
  if (_chainDynamic && _chainDynamic.evidence_closures) {
    var evNames = new Set(filtered.map(function(f){return f.name;}));
    _chainDynamic.evidence_closures.forEach(function(ec){ if (ec.closed && evNames.has(ec.chain_name)) closedInFiltered++; });
  }
  var evText = '\u5171 ' + filtered.length + ' \u6761\u8bc1\u636e\u94fe';
  if (closedInFiltered > 0) evText += ' | \U0001f512\u5df2\u95ed\u73af ' + closedInFiltered + ' \u6761';
  if (stats) stats.textContent = evText;"""
    content = content.replace(old_ev_end, new_ev_end)
    print("filterEvidence end: updated successfully")

with open('static/js/tax-risk-rules.js', 'w', encoding='utf-8') as f:
    f.write(content)

print("\nAll patches applied. File saved.")
