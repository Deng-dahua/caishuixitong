// ==================== 税收权益保障（独立职责模块） ====================

function renderTaxpayerRightsHub(container) {
  if (!container) return;
  window.currentModule = '税收权益保障';
  container.innerHTML = `
    <style>
      .rights-shell{
        --rights-ink:#17273c;
        --rights-text:#405166;
        --rights-muted:#6b7b8f;
        --rights-line:#dce4ed;
        --rights-accent:#18725a;
        max-width:1680px;
        margin:0 auto;
        padding:36px clamp(8px,1.1vw,18px) 56px;
        box-sizing:border-box;
        color:var(--rights-text);
        background:#f5f7fa;
        font-family:"Microsoft YaHei UI","Microsoft YaHei","PingFang SC",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
        font-size:15px;
        line-height:1.78
      }
      .rights-shell *{box-sizing:border-box}
      .rights-head{position:relative;overflow:hidden;margin-bottom:26px;padding:42px 46px 39px;border:1px solid rgba(255,255,255,.12);border-radius:17px;color:#fff;background:linear-gradient(135deg,#17273c 0%,#24475b 68%,#286451 100%);box-shadow:0 14px 34px rgba(20,34,52,.14)}
      .rights-head:after{content:"";position:absolute;right:-65px;bottom:-100px;width:300px;height:300px;border:1px solid rgba(255,255,255,.08);border-radius:50%;box-shadow:0 0 0 48px rgba(40,116,88,.12),0 0 0 96px rgba(255,255,255,.025)}
      .rights-kicker{position:relative;z-index:1;display:inline-block;margin-bottom:14px;padding:6px 11px;border:1px solid rgba(255,255,255,.2);border-radius:5px;color:#cce8dc;background:rgba(24,114,90,.25);font-size:12px;font-weight:750;letter-spacing:.08em}
      .rights-head h1{position:relative;z-index:1;margin:0 0 13px;color:#fff;font-size:32px;line-height:1.3;font-weight:750}
      .rights-head p{position:relative;z-index:1;max-width:1080px;margin:0;color:#dce7ed;font-size:15px;line-height:1.95;text-align:justify}
      .rights-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:15px;margin-bottom:22px}
      .rights-card{position:relative;min-height:150px;padding:23px 21px;border:1px solid var(--rights-line);border-radius:11px;background:#fff;box-shadow:0 4px 14px rgba(20,34,52,.035)}
      .rights-card-num{display:inline-flex;align-items:center;justify-content:center;width:30px;height:30px;margin-bottom:16px;border-radius:7px;color:#fff;background:var(--rights-accent);font-size:12px;font-weight:800}
      .rights-card b{display:block;margin-bottom:9px;color:var(--rights-ink);font-size:15px;line-height:1.5}
      .rights-card span{display:block;color:#64758a;font-size:13px;line-height:1.85;text-align:justify}
      .rights-flow{margin-bottom:22px;padding:25px 27px;border:1px solid var(--rights-line);border-radius:11px;background:#fff}
      .rights-flow h2{margin:0 0 7px;color:var(--rights-ink);font-size:19px;line-height:1.5}
      .rights-flow-lead{margin:0 0 19px;color:var(--rights-muted);font-size:13px;line-height:1.8}
      .rights-steps{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px}
      .rights-step{position:relative;padding:16px 15px;border-top:3px solid #2f8068;border-radius:8px;background:#f5faf8}
      .rights-step b{display:block;margin-bottom:6px;color:#1e5949;font-size:13px}
      .rights-step small{display:block;color:#64758a;font-size:12px;line-height:1.7}
      .rights-boundary{margin-top:19px;padding:15px 17px;border-left:4px solid #2f8068;border-radius:7px;color:#56687d;background:#f7faf9;font-size:13px;line-height:1.85}
      .rights-workspace{min-height:260px;border:1px solid var(--rights-line);border-radius:12px;background:#fff;overflow:hidden;box-shadow:0 5px 16px rgba(20,34,52,.035)}
      .rights-workspace-title{padding:21px 24px 18px;border-bottom:1px solid var(--rights-line);color:var(--rights-ink);background:#f8fafc;font-size:18px;font-weight:750}
      .rights-workspace-title small{display:block;margin-top:6px;color:var(--rights-muted);font-size:12px;line-height:1.65;font-weight:400}
      .rights-incentive-intro{padding:20px 24px 16px;color:#52647a;font-size:13px;line-height:1.8}
      .rights-incentive-intro b{color:#1e5949;font-size:14px}
      .rights-incentive-list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;padding:0 24px 24px}
      .rights-incentive-item{padding:19px 20px;border:1px solid #dce7e2;border-radius:9px;background:#fbfdfc}
      .rights-incentive-item b{display:block;margin-bottom:8px;color:#184f40;font-size:14px;line-height:1.55}
      .rights-incentive-item p{margin:0;color:#5e6f83;font-size:13px;line-height:1.82}
      .rights-incentive-benefit{display:block;margin-top:10px;padding-top:9px;border-top:1px solid #e3ece8;color:#18725a;font-size:13px;font-weight:700}
      .rights-empty{margin:0 24px 24px;padding:28px;border:1px dashed #cbd8d2;border-radius:9px;color:#657589;background:#fbfdfc;text-align:center;font-size:13px;line-height:1.8}
      @media(max-width:1180px){.rights-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.rights-steps{grid-template-columns:repeat(3,minmax(0,1fr))}}
      @media(max-width:760px){.rights-shell{padding:14px 4px 34px}.rights-head{padding:29px 23px}.rights-head h1{font-size:25px}.rights-head p{text-align:left}.rights-grid,.rights-steps,.rights-incentive-list{grid-template-columns:1fr}.rights-flow{padding:21px 18px}.rights-incentive-list{padding:0 16px 18px}.rights-incentive-intro{padding:18px 16px 14px}}
    </style>
    <div class="rights-shell">
      <header class="rights-head">
        <div class="rights-kicker">合法权益 · 政策核验 · 办理闭环</div>
        <h1>🎁 税收权益保障</h1>
        <p>税收优惠是对纳税人合法权益的主动保护，不应与风险疑点和违法定性混排。本模块独立承接原“税收优惠”，负责识别应享未享、核验适用条件、测算节税金额并给出申报与补充材料建议。</p>
      </header>
      <div class="rights-grid">
        <div class="rights-card"><span class="rights-card-num">01</span><b>政策匹配</b><span>根据行业、企业规模、资质、人员和经营数据筛选可能适用的现行优惠。</span></div>
        <div class="rights-card"><span class="rights-card-num">02</span><b>条件核验</b><span>逐条核对资格条件、有效期间、备案资料和限制性条款，不以单一标签直接判定。</span></div>
        <div class="rights-card"><span class="rights-card-num">03</span><b>权益测算</b><span>估算可减免税额、可退税额或可扣除金额，并明确数据口径与测算前提。</span></div>
        <div class="rights-card"><span class="rights-card-num">04</span><b>办理建议</b><span>输出申报路径、所需材料、待确认事项和政策依据，确保建议可执行、可复核。</span></div>
      </div>
      <section class="rights-flow">
        <h2>权益保障工作流</h2>
        <p class="rights-flow-lead">以企业画像为起点，以政策有效性和资料完整性为门禁，最终形成可办理、可复核的权益实现方案。</p>
        <div class="rights-steps">
          <div class="rights-step"><b>01 识别企业画像</b><small>确认行业、规模、资质、人员与经营期间。</small></div>
          <div class="rights-step"><b>02 匹配优惠政策</b><small>从现行政策中筛选可能适用的权益事项。</small></div>
          <div class="rights-step"><b>03 核验适用条件</b><small>逐条检查资格、期限、限制与资料要求。</small></div>
          <div class="rights-step"><b>04 测算权益金额</b><small>明确计算口径、数据来源与测算前提。</small></div>
          <div class="rights-step"><b>05 形成办理建议</b><small>整理申报路径、所需材料和待确认事项。</small></div>
        </div>
        <div class="rights-boundary"><b>职责边界：</b>本模块只确认“是否可能享受、尚缺什么材料、如何办理”；对已享优惠是否存在违规适用的风险核查，仍由“风险检查方法论”中的疑点规则和证据链负责。两者共享数据，但不混用结论。</div>
      </section>
      <section class="rights-workspace">
        <div class="rights-workspace-title">税收优惠扫描与核验结果<small>展示当前账套可能适用的权益事项、预期收益和进一步核验要求。</small></div>
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
