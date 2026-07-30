// ==================== 税收权益保障（独立职责模块） ====================

function renderTaxpayerRightsHub(container) {
  if (!container) return;
  window.currentModule = '税收权益保障';
  container.innerHTML = `
    <style>
      .rights-shell{max-width:1240px;margin:0 auto;padding:24px;color:#334155}
      .rights-head{padding:24px;border:1px solid #d9eadf;border-radius:14px;background:linear-gradient(135deg,#f4fbf6,#fbfdfb);margin-bottom:18px}
      .rights-head h1{margin:0 0 8px;color:#14532d;font-size:24px}
      .rights-head p{margin:0;color:#5b6875;line-height:1.8}
      .rights-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-bottom:18px}
      .rights-card{padding:15px;border:1px solid #dfe9e2;border-radius:10px;background:#fff}
      .rights-card b{display:block;margin-bottom:6px;color:#166534}
      .rights-card span{display:block;color:#64748b;font-size:12px;line-height:1.7}
      .rights-flow{padding:16px 18px;border:1px solid #e2e8f0;border-radius:10px;background:#fff;margin-bottom:18px}
      .rights-flow h2{margin:0 0 10px;color:#1e293b;font-size:16px}
      .rights-steps{display:flex;flex-wrap:wrap;gap:8px;align-items:center;color:#475569;font-size:12px}
      .rights-steps span{padding:7px 11px;border-radius:999px;background:#edf8f0;color:#166534;font-weight:600}
      .rights-steps i{font-style:normal;color:#94a3b8}
      .rights-boundary{margin-top:12px;color:#64748b;line-height:1.75;font-size:12px}
      .rights-workspace{border:1px solid #e2e8f0;border-radius:12px;background:#fff;overflow:hidden;min-height:220px}
      .rights-workspace-title{padding:14px 18px;border-bottom:1px solid #e2e8f0;background:#f8fafc;color:#166534;font-weight:700}
      @media(max-width:900px){.rights-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
      @media(max-width:600px){.rights-shell{padding:14px}.rights-grid{grid-template-columns:1fr}.rights-head{padding:18px}}
    </style>
    <div class="rights-shell">
      <header class="rights-head">
        <h1>🎁 税收权益保障</h1>
        <p>税收优惠是对纳税人合法权益的主动保护，不应与风险疑点和违法定性混排。本模块独立承接原“税收优惠”，负责识别应享未享、核验适用条件、测算节税金额并给出申报与补充材料建议。</p>
      </header>
      <div class="rights-grid">
        <div class="rights-card"><b>政策匹配</b><span>根据行业、企业规模、资质、人员和经营数据筛选可能适用的现行优惠。</span></div>
        <div class="rights-card"><b>条件核验</b><span>逐条核对资格条件、有效期间、备案资料和限制性条款，不以单一标签直接判定。</span></div>
        <div class="rights-card"><b>权益测算</b><span>估算可减免税额、可退税额或可扣除金额，并明确数据口径与测算前提。</span></div>
        <div class="rights-card"><b>办理建议</b><span>输出申报路径、所需材料、待确认事项和政策依据，确保建议可执行、可复核。</span></div>
      </div>
      <section class="rights-flow">
        <h2>权益保障工作流</h2>
        <div class="rights-steps">
          <span>识别企业画像</span><i>→</i><span>匹配优惠政策</span><i>→</i><span>核验适用条件</span><i>→</i><span>测算权益金额</span><i>→</i><span>形成办理建议</span>
        </div>
        <div class="rights-boundary"><b>职责边界：</b>本模块只确认“是否可能享受、尚缺什么材料、如何办理”；对已享优惠是否存在违规适用的风险核查，仍由“稽查方法论”中的疑点规则和证据链负责。两者共享数据，但不混用结论。</div>
      </section>
      <section class="rights-workspace">
        <div class="rights-workspace-title">税收优惠扫描与核验结果</div>
        <div id="taxpayer-rights-incentives"><div style="padding:24px;color:#64748b">正在载入税收优惠数据...</div></div>
      </section>
    </div>`;
  var target = document.getElementById('taxpayer-rights-incentives');
  if (!target) return;
  if (typeof renderTaxIncentivesPage !== 'function') {
    target.innerHTML = '<div style="padding:24px;color:#b91c1c">税收优惠能力暂未完成载入，请刷新页面后重试。</div>';
    return;
  }
  try {
    var result = renderTaxIncentivesPage(target);
    if (result && typeof result.catch === 'function') {
      result.catch(function(error) {
        target.innerHTML = '<div style="padding:24px;color:#b91c1c">税收优惠数据载入失败：'
          + (error && error.message ? error.message : '未知错误') + '</div>';
      });
    }
  } catch (error) {
    target.innerHTML = '<div style="padding:24px;color:#b91c1c">税收优惠数据载入失败：'
      + (error && error.message ? error.message : '未知错误') + '</div>';
  }
  window.currentModule = '税收权益保障';
}
