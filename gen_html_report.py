"""
Generate professional HTML report from report_data.json
"""
import json, os

with open('report_data.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

def esc(s):
    if s is None: return ''
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')

# Level badge
def level_badge(level):
    if '高' in str(level): return '<span class="badge badge-high">高风险</span>'
    if '中' in str(level): return '<span class="badge badge-mid">中风险</span>'
    return '<span class="badge badge-low">低风险</span>'

# Domain color
def domain_color(i):
    colors = ['#f43f5e','#f97316','#eab308','#22c55e','#06b6d4','#3b82f6','#8b5cf6','#ec4899',
              '#14b8a6','#84cc16','#f59e0b','#6366f1','#a855f7','#0ea5e9','#10b981',
              '#f43f5e','#f97316','#eab308','#22c55e','#06b6d4','#3b82f6','#8b5cf6',
              '#ec4899','#14b8a6','#84cc16','#f59e0b','#6366f1','#a855f7','#0ea5e9']
    return colors[i % len(colors)]

# Build domain findings HTML
domain_html = ''
for i, d in enumerate(data['domain_summary']):
    findings = d.get('findings', [])
    if not findings: continue
    h = d.get('high', 0)
    m = d.get('mid', 0)
    c = d.get('count', len(findings))
    dc = domain_color(i)
    
    findings_html = ''
    for f in findings[:10]:  # max 10 per domain
        level = str(f.get('level', f.get('risk_level', '低风险')))
        desc = f.get('description') or f.get('detail') or f.get('type', '')
        suggestion = f.get('suggestion', '')
        tax_impact = f.get('tax_impact', '')
        score = f.get('score', 0)
        policy = f.get('policy_ref', '')
        
        findings_html += f'''
        <div class="finding-card level-{level}">
            <div class="finding-header">
                {level_badge(level)}
                <span class="finding-score">风险分: {score}</span>
            </div>
            <div class="finding-body">{esc(desc)}</div>
            {f'<div class="finding-section"><strong>税务影响：</strong>{esc(tax_impact)}</div>' if tax_impact else ''}
            {f'<div class="finding-section"><strong>政策依据：</strong>{esc(policy)}</div>' if policy else ''}
            {f'<div class="finding-section suggestion"><strong>💡 建议：</strong>{esc(suggestion)}</div>' if suggestion else ''}
        </div>'''
    
    domain_html += f'''
    <div class="domain-section">
        <div class="domain-header" style="border-left: 4px solid {dc}">
            <span class="domain-num" style="background:{dc}">域{i+1}</span>
            <span class="domain-name">{esc(d['name'])}</span>
            <span class="domain-stats">
                <span class="stat-high">{'🔴' if h > 0 else ''} H{h}</span>
                <span class="stat-mid">{'🟡' if m > 0 else ''} M{m}</span>
                <span>{c - h - m} L</span>
            </span>
        </div>
        <div class="domain-findings">{findings_html}</div>
    </div>'''

# Build summary cards
overall = data['overall']
colors = {'高风险': '#dc2626', '中风险': '#f59e0b', '低风险': '#22c55e'}
overall_color = colors.get(overall, '#6b7280')

# Monthly flow chart data
monthly = data.get('monthly_bt', [])
chart_months = [m['month'] for m in monthly[-24:]]  # last 24 months
chart_out = [m['outflow'] for m in monthly[-24:]]
chart_in = [m['inflow'] for m in monthly[-24:]]

# Data stats
totals = data['totals']
counts = data['data_counts']

html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>税务风险综合分析报告 — {esc(data['company']['name'])}</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif; background:#0f172a; color:#e2e8f0; line-height:1.7; }}
.container {{ max-width:1200px; margin:0 auto; padding:24px; }}

/* Header */
.report-header {{ background:linear-gradient(135deg,#1e293b 0%,#0f172a 100%); border:1px solid #334155; border-radius:16px; padding:40px; margin-bottom:24px; text-align:center; }}
.report-header h1 {{ font-size:32px; font-weight:800; color:#f8fafc; margin-bottom:8px; }}
.report-header .subtitle {{ color:#94a3b8; font-size:14px; }}
.report-header .meta {{ display:flex; justify-content:center; gap:32px; margin-top:20px; flex-wrap:wrap; }}
.report-header .meta-item {{ text-align:center; }}
.report-header .meta-label {{ color:#64748b; font-size:11px; text-transform:uppercase; letter-spacing:1px; }}
.report-header .meta-value {{ color:#f8fafc; font-size:18px; font-weight:700; }}

/* Summary cards */
.summary-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:16px; margin-bottom:24px; }}
.summary-card {{ background:#1e293b; border:1px solid #334155; border-radius:12px; padding:20px; text-align:center; }}
.summary-card .label {{ color:#94a3b8; font-size:12px; margin-bottom:4px; }}
.summary-card .value {{ font-size:28px; font-weight:800; }}
.summary-card .sub {{ color:#64748b; font-size:11px; margin-top:4px; }}

/* Data overview */
.data-overview {{ background:#1e293b; border:1px solid #334155; border-radius:12px; padding:24px; margin-bottom:24px; }}
.data-overview h2 {{ font-size:18px; color:#f8fafc; margin-bottom:16px; }}
.data-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; }}
.data-item {{ padding:12px; background:#0f172a; border-radius:8px; text-align:center; }}
.data-item .d-label {{ color:#64748b; font-size:11px; }}
.data-item .d-value {{ font-size:22px; font-weight:700; color:#f8fafc; }}

/* Domain sections */
.domain-section {{ background:#1e293b; border:1px solid #334155; border-radius:12px; margin-bottom:16px; overflow:hidden; }}
.domain-header {{ padding:16px 20px; display:flex; align-items:center; gap:12px; background:#0f172a; }}
.domain-num {{ width:32px; height:32px; border-radius:8px; display:flex; align-items:center; justify-content:center; color:#fff; font-weight:700; font-size:13px; }}
.domain-name {{ font-weight:700; font-size:15px; color:#f8fafc; flex:1; }}
.domain-stats {{ display:flex; gap:12px; font-size:13px; color:#94a3b8; }}
.stat-high {{ color:#fca5a5; }}
.stat-mid {{ color:#fcd34d; }}

/* Finding cards */
.domain-findings {{ padding:16px 20px; }}
.finding-card {{ background:#0f172a; border-radius:8px; padding:16px; margin-bottom:12px; border-left:3px solid #334155; }}
.finding-card.level-高风险 {{ border-left-color:#dc2626; background:linear-gradient(90deg,rgba(220,38,38,0.08),transparent); }}
.finding-card.level-中风险 {{ border-left-color:#f59e0b; background:linear-gradient(90deg,rgba(245,158,11,0.06),transparent); }}
.finding-header {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; }}
.finding-body {{ color:#cbd5e1; font-size:14px; margin-bottom:8px; line-height:1.8; white-space:pre-wrap; }}
.finding-section {{ color:#94a3b8; font-size:13px; margin-top:8px; padding-top:8px; border-top:1px solid #1e293b; }}
.finding-section.suggestion {{ background:rgba(59,130,246,0.08); border-radius:6px; padding:10px 12px; border:none; color:#93c5fd; }}
.finding-score {{ font-size:12px; color:#64748b; }}

/* Badges */
.badge {{ display:inline-block; padding:2px 10px; border-radius:4px; font-size:12px; font-weight:600; }}
.badge-high {{ background:rgba(220,38,38,0.2); color:#fca5a5; }}
.badge-mid {{ background:rgba(245,158,11,0.2); color:#fcd34d; }}
.badge-low {{ background:rgba(34,197,94,0.2); color:#86efac; }}

/* Chart */
.chart-container {{ background:#1e293b; border:1px solid #334155; border-radius:12px; padding:24px; margin-bottom:24px; }}
.chart-container h2 {{ font-size:18px; color:#f8fafc; margin-bottom:16px; }}
.chart-bars {{ display:flex; align-items:flex-end; gap:4px; height:300px; overflow-x:auto; padding-bottom:8px; }}
.chart-bar-group {{ display:flex; flex-direction:column; align-items:center; min-width:40px; }}
.chart-bar-in {{ width:18px; background:linear-gradient(180deg,#22c55e,#15803d); border-radius:4px 4px 0 0; }}
.chart-bar-out {{ width:18px; background:linear-gradient(180deg,#ef4444,#b91c1c); border-radius:4px 4px 0 0; margin-left:2px; }}
.chart-label {{ font-size:10px; color:#64748b; margin-top:4px; writing-mode:vertical-rl; transform:rotate(180deg); max-height:50px; }}

/* Counterparty table */
.cp-table {{ width:100%; border-collapse:collapse; font-size:13px; }}
.cp-table th {{ text-align:left; color:#64748b; font-weight:600; padding:10px 12px; border-bottom:1px solid #334155; }}
.cp-table td {{ padding:8px 12px; border-bottom:1px solid #1e293b; color:#cbd5e1; }}
.cp-table tr:hover td {{ background:rgba(59,130,246,0.04); }}
.amount-out {{ color:#fca5a5; }}
.amount-in {{ color:#86efac; }}

/* Tabs */
.tabs {{ display:flex; gap:8px; margin-bottom:16px; flex-wrap:wrap; }}
.tab {{ padding:8px 20px; background:#1e293b; border:1px solid #334155; border-radius:8px; color:#94a3b8; cursor:pointer; font-size:14px; transition:all 0.2s; }}
.tab.active {{ background:#3b82f6; border-color:#3b82f6; color:#fff; }}
.tab-content {{ display:none; }}
.tab-content.active {{ display:block; }}

/* Risk Overview */
.risk-verdict {{ background:linear-gradient(135deg,rgba(220,38,38,0.15),rgba(220,38,38,0.05)); border:2px solid #dc2626; border-radius:16px; padding:32px; margin-bottom:24px; text-align:center; }}
.risk-verdict h2 {{ font-size:24px; color:#fca5a5; margin-bottom:8px; }}
.risk-verdict .verdict-text {{ color:#cbd5e1; font-size:15px; margin-top:12px; line-height:1.8; }}
.risk-verdict .verdict-stats {{ display:flex; justify-content:center; gap:40px; margin-top:20px; }}
.risk-verdict .verdict-stat {{ text-align:center; }}
.risk-verdict .verdict-num {{ font-size:36px; font-weight:800; }}

/* Footer */
.report-footer {{ text-align:center; color:#475569; font-size:12px; padding:40px 0 20px; border-top:1px solid #1e293b; margin-top:40px; }}

@media (max-width:768px) {{
    .report-header h1 {{ font-size:22px; }}
    .summary-grid {{ grid-template-columns:repeat(2,1fr); }}
    .tabs {{ flex-direction:column; }}
}}

.tab-btn {{ display:inline-block; padding:8px 20px; background:#1e293b; border:1px solid #334155; border-radius:8px; color:#94a3b8; cursor:pointer; font-size:14px; transition:all 0.2s; margin:0 4px; }}
.tab-btn.active {{ background:#3b82f6; border-color:#3b82f6; color:#fff; }}
.tab-pane {{ display:none; }}
.tab-pane.active {{ display:block; }}
</style>
<script>
function switchTab(tabName) {{
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
    document.getElementById('tab-' + tabName).classList.add('active');
    event.target.classList.add('active');
}}
</script>
</head>
<body>

<div class="container">

<!-- Header -->
<div class="report-header">
    <h1>📊 税务风险综合分析报告</h1>
    <p class="subtitle">{esc(data['company']['name'])} · 统一社会信用代码: {esc(data['company']['tax_no'])}</p>
    <div class="meta">
        <div class="meta-item">
            <div class="meta-label">报告生成时间</div>
            <div class="meta-value">{data['generated_at']}</div>
        </div>
        <div class="meta-item">
            <div class="meta-label">数据期间</div>
            <div class="meta-value">{data['period_info']['bt_from']} ~ {data['period_info']['bt_to']}</div>
        </div>
        <div class="meta-item">
            <div class="meta-label">分析引擎</div>
            <div class="meta-value">29域 + 312规则</div>
        </div>
        <div class="meta-item">
            <div class="meta-label">数据记录数</div>
            <div class="meta-value">{data['bt_count'] + data['si_count'] + data['pi_count'] + data['je_count']:,}</div>
        </div>
    </div>
</div>

<!-- Risk Verdict -->
<div class="risk-verdict">
    <h2>⚠️ 综合风险判定：{overall}</h2>
    <div style="color:#cbd5e1;font-size:15px;margin-top:8px;">
        共发现 <strong style="color:#fca5a5">{data['total_findings']}</strong> 条风险异常
    </div>
    <div class="verdict-stats">
        <div class="verdict-stat">
            <div class="verdict-num" style="color:#fca5a5">{data['high_count']}</div>
            <div style="color:#94a3b8;font-size:13px;">高风险</div>
        </div>
        <div class="verdict-stat">
            <div class="verdict-num" style="color:#fcd34d">{data['mid_count']}</div>
            <div style="color:#94a3b8;font-size:13px;">中风险</div>
        </div>
        <div class="verdict-stat">
            <div class="verdict-num" style="color:#86efac">{data['total_findings'] - data['high_count'] - data['mid_count']}</div>
            <div style="color:#94a3b8;font-size:13px;">低风险/信息</div>
        </div>
    </div>
    <div class="verdict-text">
        该企业呈现<strong>典型的"空壳经营"特征</strong>：银行流水近4000万但仅有5张销项发票（24.6万元）、无进项发票、无合同、无工资社保记录、无经营实质费用（房租/水电/办公全为零）。银行资金进出完全无法与发票购销匹配——这是税务稽查中最核心的隐匿收入/虚开发票信号。
    </div>
</div>

<!-- Quick Stats -->
<div class="summary-grid">
    <div class="summary-card">
        <div class="label">银行流水净额</div>
        <div class="value" style="color:{'#22c55e' if totals['bt_in'] - totals['bt_out'] > 0 else '#ef4444'}">{totals['bt_in'] - totals['bt_out']:+,.0f}</div>
        <div class="sub">流入 {totals['bt_in']:,.0f} / 流出 {totals['bt_out']:,.0f}</div>
    </div>
    <div class="summary-card">
        <div class="label">销项开票金额</div>
        <div class="value" style="color:#f59e0b">{totals['si_amt']:,.0f}</div>
        <div class="sub">{data['si_count']}张发票 · 税额{totals['si_tax']:,.0f}</div>
    </div>
    <div class="summary-card">
        <div class="label">主营业务收入</div>
        <div class="value" style="color:#3b82f6">{totals['je_cr']:,.0f}</div>
        <div class="sub">{data['je_count']}条分录 · 借贷{'{:.0f}'.format(totals['je_dr'])}</div>
    </div>
    <div class="summary-card">
        <div class="label">银行流水笔数</div>
        <div class="value" style="color:#8b5cf6">{data['bt_count']:,}</div>
        <div class="sub">{len(data['top_counterparties'])}个对手方</div>
    </div>
</div>

<!-- Data Overview -->
<div class="data-overview">
    <h2>📋 数据底账</h2>
    <div class="data-grid">
        <div class="data-item">
            <div class="d-label">银行流水</div>
            <div class="d-value">{data['bt_count']:,}</div>
        </div>
        <div class="data-item">
            <div class="d-label">销项发票</div>
            <div class="d-value">{data['si_count']}</div>
        </div>
        <div class="data-item">
            <div class="d-label">进项发票</div>
            <div class="d-value" style="color:#ef4444">{data['pi_count']}</div>
        </div>
        <div class="data-item">
            <div class="d-label">序时账凭证</div>
            <div class="d-value">{data['je_count']}</div>
        </div>
        <div class="data-item">
            <div class="d-label">工资记录</div>
            <div class="d-value" style="color:#ef4444">{data['salary_count']}</div>
        </div>
        <div class="data-item">
            <div class="d-label">客户</div>
            <div class="d-value">{data['data_counts'].get('客户', 0)}</div>
        </div>
        <div class="data-item">
            <div class="d-label">供应商</div>
            <div class="d-value" style="color:#ef4444">{data['data_counts'].get('供应商', 0)}</div>
        </div>
        <div class="data-item">
            <div class="d-label">合同</div>
            <div class="d-value" style="color:#ef4444">{data['data_counts'].get('合同', 0)}</div>
        </div>
    </div>
</div>

<!-- Tab Navigation -->
<div class="tabs">
    <button class="tab-btn active" onclick="switchTab('domains')">🔍 29域分析</button>
    <button class="tab-btn" onclick="switchTab('cashflow')">💰 资金流水</button>
    <button class="tab-btn" onclick="switchTab('counterparties')">🏢 对手方</button>
    <button class="tab-btn" onclick="switchTab('recommendations')">💡 整改建议</button>
</div>

<!-- Tab: Domains -->
<div id="tab-domains" class="tab-pane active">
    <div style="margin-bottom:16px;color:#94a3b8;font-size:13px;">
        共触发 {len(data['domain_summary'])} 个分析域，产出 {data['total_findings']} 条发现（高{data['high_count']}/中{data['mid_count']}）
    </div>
    {domain_html}
</div>

<!-- Tab: Cashflow -->
<div id="tab-cashflow" class="tab-pane">
    <div class="chart-container">
        <h2>📈 月度银行资金进出</h2>
        <div style="color:#94a3b8;font-size:13px;margin-bottom:12px;">绿色=流入 · 红色=流出 · 近24个月</div>
        <div class="chart-bars">
'''

# Add chart bars
max_val = max(max(chart_out or [1]), max(chart_in or [1]), 1)
bar_height = 250
for i, (m, o, n) in enumerate(zip(chart_months, chart_out, chart_in)):
    html += f'''
            <div class="chart-bar-group">
                <div style="display:flex;align-items:flex-end;height:{bar_height}px;">
                    <div class="chart-bar-in" style="height:{n/max_val*bar_height:.0f}px;min-height:1px;"></div>
                    <div class="chart-bar-out" style="height:{o/max_val*bar_height:.0f}px;min-height:1px;"></div>
                </div>
                <div class="chart-label">{m[-2:]}</div>
            </div>'''

html += '''
        </div>
        <div style="display:flex;gap:16px;justify-content:center;margin-top:8px;font-size:12px;color:#94a3b8;">
            <span>🟢 流入</span><span>🔴 流出</span>
        </div>
    </div>

    <!-- Monthly table -->
    <div class="data-overview">
        <h2>月度明细</h2>
        <table class="cp-table">
            <thead><tr><th>月份</th><th>笔数</th><th>流出</th><th>流入</th><th>净额</th></tr></thead>
            <tbody>
'''

for m in reversed(monthly):
    net = m['inflow'] - m['outflow']
    html += f'''                <tr>
                    <td>{m['month']}</td>
                    <td>{m['count']}</td>
                    <td class="amount-out">{m['outflow']:,.0f}</td>
                    <td class="amount-in">{m['inflow']:,.0f}</td>
                    <td style="color:{'#86efac' if net >= 0 else '#fca5a5'}">{net:+,.0f}</td>
                </tr>
'''

html += '''            </tbody>
        </table>
    </div>
</div>

<!-- Tab: Counterparties -->
<div id="tab-counterparties" class="tab-pane">
    <div class="data-overview">
        <h2>🏢 交易对手方 TOP20</h2>
        <table class="cp-table">
            <thead><tr><th>#</th><th>对手方名称</th><th>交易笔数</th><th>流出金额</th><th>流入金额</th><th>净额</th></tr></thead>
            <tbody>
'''

for i, cp in enumerate(data['top_counterparties'][:20]):
    net = cp['inflow'] - cp['outflow']
    html += f'''                <tr>
                    <td>{i+1}</td>
                    <td>{esc(cp['name'])}</td>
                    <td>{cp['count']}</td>
                    <td class="amount-out">{cp['outflow']:,.0f}</td>
                    <td class="amount-in">{cp['inflow']:,.0f}</td>
                    <td style="color:{'#86efac' if net >= 0 else '#fca5a5'}">{net:+,.0f}</td>
                </tr>
'''

html += '''            </tbody>
        </table>
    </div>
</div>

<!-- Tab: Recommendations -->
<div id="tab-recommendations" class="tab-pane">
    <div class="domain-section">
        <div class="domain-header" style="border-left:4px solid #3b82f6">
            <span class="domain-num" style="background:#3b82f6">※</span>
            <span class="domain-name">紧急整改建议（按优先级）</span>
        </div>
        <div class="domain-findings">
            <div class="finding-card level-高风险">
                <div class="finding-header">
                    <span class="badge badge-high">P0 — 立即处理</span>
                    <span class="finding-score">核心证据链断裂</span>
                </div>
                <div class="finding-body">
<strong>1. 补全进项发票</strong>：当前进项发票为零，无法验证成本真实性和进项税额抵扣合规性。至少应取得与已付款项对应的供应商发票（已付款2118万元）。
<strong>2. 补签购销合同</strong>：2个销项客户均无合同。发票+资金流+合同流+货物流"四流合一"是稽查底线。
<strong>3. 整理经营费用凭证</strong>：房租/水电/物业/办公/物流费用全部缺失——补齐这些基本费用凭证（至少能证明有实际经营场所）。
<strong>4. 补录未开票收入申报</strong>：245,827元主营业务收入100%未开票，需核对是否已在增值税申报表"未开具发票"栏次填报。
                </div>
            </div>
            <div class="finding-card level-中风险">
                <div class="finding-header">
                    <span class="badge badge-mid">P1 — 近期处理</span>
                    <span class="finding-score">账务与资金流匹配</span>
                </div>
                <div class="finding-body">
<strong>1. 建立银行—发票—凭证三方对账机制</strong>：银行流水3920万但仅5张发票，收款无法匹配客户（0%匹配率）、付款无法匹配供应商（0%匹配率）。
<strong>2. 建全工资社保公积金档案</strong>：当前工资记录为零——有收入但无人工成本是明显的不合理迹象。
<strong>3. 规范交易时间</strong>：672笔周末交易、60笔整数金额交易——建立工作日交易管理制度，降低人为构造痕迹。
                </div>
            </div>
            <div class="finding-card level-低风险">
                <div class="finding-header">
                    <span class="badge badge-low">P2 — 持续改进</span>
                    <span class="finding-score">档案体系完善</span>
                </div>
                <div class="finding-body">
<strong>1. 建立完整的客户/供应商档案</strong>（目前仅2个客户、0个供应商）
<strong>2. 补齐合同备案</strong>（当前0份合同）
<strong>3. 完善记账凭证</strong>（凭证号100%为空，无法做逐张凭证平衡校验）
<strong>4. 建立存货管理台账</strong>（无存货数据）
                </div>
            </div>
        </div>
    </div>
</div>

<!-- Footer -->
<div class="report-footer">
    <p>本报告由税务风险智能分析系统自动生成 · 分析引擎：29域综合研判 + 312规则引擎</p>
    <p>报告生成时间：{data['generated_at']} · 数据期间：{data['period_info']['bt_from']} ~ {data['period_info']['bt_to']}</p>
    <p style="margin-top:8px;">⚠️ 免责声明：本报告基于企业上传的经营数据自动分析生成，仅供参考。具体税务处理请咨询专业税务顾问。</p>
</div>

</div>
</body>
</html>'''

with open('static/tax_risk_comprehensive_report.html', 'w', encoding='utf-8') as f:
    f.write(html)

file_size = os.path.getsize('static/tax_risk_comprehensive_report.html') / 1024
print(f'HTML report generated: static/tax_risk_comprehensive_report.html ({file_size:.0f}KB)')
