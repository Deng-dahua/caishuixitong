// ═══════════════════════════════════════════════════════════════
//  报告块渲染器 — 通用渲染，不预设任何模块/模板/开关
//  后端推什么 blocks，前端就渲染什么。全行业各企业通用。
// ═══════════════════════════════════════════════════════════════
//  架构：
//    前端：renderReportBlocks(blocks) → 遍历 → renderBlock[type](data) → 拼接 HTML
//    后端：_build_report_blocks() → 根据数据动态 push blocks → 输出 JSON
//  效果：
//    加段落 = 后端 push block → 前端自动渲染
//    删段落 = 后端不 push block → 前端不渲染
//    改顺序 = 后端调 blocks 顺序 → 前端自动按序渲染
//    不同公司 = 后端推不同 blocks → 前端同代码出不同报告
// ═══════════════════════════════════════════════════════════════

(function() {
  'use strict';

  if (typeof window === 'undefined') return;

  var esc = window.esc || function(s) {
    return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  };

  function fmtMoney(v) {
    if (v === undefined || v === null || v === '') return '';
    return Number(v).toLocaleString('zh-CN');
  }

  // ── block 渲染函数映射 ──
  // 每种 type 对应一个渲染函数，接收 (block, index, blocks) 返回 HTML 字符串

  var renderBlock = {};

  // 封皮
  renderBlock['cover'] = function(b) {
    var d = b.data;
    return ''
      + '<div class="block-cover">'
      + '<h1>税 务 稽 查 报 告</h1>'
      + '<div class="cover-sub">'
      + '编号：' + esc(d.report_no) + '<br>'
      + '被查单位：' + esc(d.company_name) + '<br>'
      + '报告日期：' + new Date().toLocaleDateString('zh-CN') + '<br>'
      + '资料数量：' + (d.files_count || 0) + '份'
      + '</div></div>';
  };

  // 企业基本画像
  renderBlock['entity_profile'] = function(b) {
    var e = b.data.entity || {};
    var h = '<table class="block-tbl">';
    var fields = [
      ['企业名称', e.name],
      ['法定代表人', e.legal_representative],
      ['注册资本', e.registered_capital],
      ['成立日期', e.established_date],
      ['企业类型', e.company_type],
      ['经营状态', e.company_status],
      ['注册地址', e.address],
      ['统一社会信用代码', e.uscc],
      ['行业分类', '发票推断：' + esc(e.industry || '') + ' | 联网核查：' + esc(e.industry_online || '')],
    ];
    fields.forEach(function(f) {
      if (f[1]) h += '<tr><td class="lbl">' + f[0] + '</td><td>' + esc(f[1]) + '</td></tr>';
    });
    if (e.business_scope) {
      h += '<tr><td class="lbl">经营范围</td><td style="font-size:12px">' + esc(e.business_scope) + '</td></tr>';
    }
    h += '</table>';
    return h;
  };

  // 资料完备度
  renderBlock['data_completeness'] = function(b) {
    var d = b.data;
    var cats = d.categories || {};
    var missing = d.missing || [];
    var h = '<p>本次稽查共收到' + (d.files_count || 0) + '份资料，覆盖';
    var catNames = Object.keys(cats);
    h += catNames.map(function(k) { return k + ' ' + cats[k] + '份'; }).join('、');
    h += '。';
    if (missing.length > 0) {
      h += '<span style="color:#dc2626">缺失' + missing.length + '类稽查必查资料（'
        + missing.join('、') + '）。</span>';
    }
    h += '</p>';
    return h;
  };

  // 风险总览
  renderBlock['risk_summary'] = function(b) {
    var d = b.data;
    return ''
      + '<div class="block-stats">'
      + '<div class="stat-card"><div class="stat-num">' + d.total + '</div><div class="stat-lbl">风险发现总数</div></div>'
      + '<div class="stat-card" style="color:#991b1b"><div class="stat-num">' + d.high + '</div><div class="stat-lbl">高风险</div></div>'
      + '<div class="stat-card" style="color:#92400e"><div class="stat-num">' + d.mid + '</div><div class="stat-lbl">中风险</div></div>'
      + '<div class="stat-card" style="color:#166534"><div class="stat-num">' + d.low + '</div><div class="stat-lbl">低风险</div></div>'
      + '</div>';
  };

  // 稽查方法
  renderBlock['methods'] = function(b) {
    var d = b.data;
    var methods = d.methods || [];
    var ii = d.invoice_stats || {};
    var bi = d.bank_stats || {};
    var h = '<p>根据资料驱动稽查方法论，本次核查采用以下方法：</p>';
    var labels = {
      '工商登记核查法': '工商登记核查法：联网核查被查单位工商登记信息，登记行业为' + esc(d.registered_business || '未获取'),
      '进销存数据比对法': '进销存数据比对法：进销比' + esc(ii['进销比'] || '') + '，销项发票' + esc(ii['销项发票'] || '') + '，进项发票' + esc(ii['进项发票'] || ''),
      '资金流与发票流核对法': '资金流与发票流核对法：银行收款' + esc(bi['总收款'] || '') + '，付款' + esc(bi['总付款'] || '') + '，税费支出' + esc(bi['税费支出总额'] || ''),
      '供应商及客户穿透分析法': '供应商及客户穿透分析法：对供应商和客户进行集中度检测和名称群集检测，排查关联交易和虚开风险',
      '加工环节穿透法': '加工环节穿透法：进项发票中存在加工费等品名，逐笔核实委托加工的真实性',
      '五步核查法': '五步核查法：按工商登记→进项审核→销项审核→交叉比对→综合判断的顺序进行全流程核查',
    };
    h += '<ol>';
    methods.forEach(function(m) {
      h += '<li>' + (labels[m] || m) + '</li>';
    });
    h += '</ol>';
    return h;
  };

  // 发现项
  renderBlock['finding'] = function(b) {
    var f = b.data.finding || {};
    var level = f.level || '中风险';
    var cls = level === '高风险' ? 'finding-high' : (level === '中风险' ? 'finding-mid' : 'finding-low');
    var h = '<div class="finding-block ' + cls + '">';
    h += '<div class="finding-title">' + (f.title || f.category || '风险发现') + '</div>';
    if (f.summary) h += '<div class="finding-body">' + esc(f.summary) + '</div>';
    if (f.detail) h += '<div class="finding-detail">' + esc(f.detail) + '</div>';
    if (f.law_ref) h += '<div class="finding-law">法规依据：' + esc(f.law_ref) + '</div>';
    if (f.action) h += '<div class="finding-action">建议：' + esc(f.action) + '</div>';
    h += '</div>';
    return h;
  };

  // 结论
  renderBlock['conclusion'] = function(b) {
    var d = b.data;
    var h = '<p>经对被查单位「' + esc(d.entity_name) + '」进行分析，形成结论如下：</p>';
    h += '<p>综合风险评级：<b>' + esc(d.overall_level || '未评定') + '</b>，共发现' + (d.total_risks || 0) + '项风险。</p>';
    if (d.missing_docs && d.missing_docs.length > 0) {
      h += '<p style="color:#dc2626">资料完备度不足：缺失' + d.missing_docs.length + '类必查资料。</p>';
    }
    h += '<div class="block-seal"><p>稽查员（签名）：_______________</p><p>日期：' + new Date().toLocaleDateString('zh-CN') + '</p></div>';
    return h;
  };

  // 签字
  renderBlock['signature'] = function(b) {
    return '<div class="block-seal"><p>稽查员（签名）：_______________</p><p>日期：' + new Date().toLocaleDateString('zh-CN') + '</p></div>';
  };


  // ═══════════════════════════════════════════════════════════
  //  主渲染函数
  // ═══════════════════════════════════════════════════════════

  function renderReportBlocks(blocks, targetEl) {
    if (!blocks || !blocks.length) {
      targetEl.innerHTML = '<p style="color:#999">暂无可渲染的报告块。</p>';
      return;
    }

    // 按 priority 排序
    blocks.sort(function(a, b) { return (a.priority || 99) - (b.priority || 99); });

    // CSS
    var css = ''
      + '.block-cover{text-align:center;padding:60px 0 40px;border-bottom:3px double #1a1a2e;margin-bottom:40px}'
      + '.block-cover h1{font-size:28px;font-weight:900;letter-spacing:6px;margin-bottom:16px}'
      + '.block-cover .cover-sub{font-size:14px;color:#555;line-height:2.5}'
      + '.block-tbl{width:100%;border-collapse:collapse;margin:12px 0;font-size:13px}'
      + '.block-tbl td{padding:6px 12px;border-bottom:1px solid #eee}'
      + '.block-tbl .lbl{width:140px;font-weight:600;color:#666;background:#fafafa}'
      + '.block-stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:16px 0}'
      + '.stat-card{text-align:center;padding:16px;background:#f8f9fa;border-radius:8px}'
      + '.stat-num{font-size:28px;font-weight:700}'
      + '.stat-lbl{font-size:12px;color:#666;margin-top:4px}'
      + '.finding-block{margin:12px 0;padding:14px 18px;border-left:4px solid #e67700;border-radius:6px;background:#fff;border:1px solid #eee}'
      + '.finding-block.finding-high{border-left-color:#dc2626}'
      + '.finding-block.finding-mid{border-left-color:#e67700}'
      + '.finding-block.finding-low{border-left-color:#16a34a}'
      + '.finding-title{font-weight:700;font-size:14px;margin-bottom:6px}'
      + '.finding-body{font-size:13px;color:#334155;line-height:1.8}'
      + '.finding-detail{font-size:12px;color:#64748b;margin-top:4px}'
      + '.finding-law{font-size:12px;color:#0ea5e9;margin-top:4px}'
      + '.finding-action{font-size:12px;color:#16a34a;margin-top:4px}'
      + '.block-seal{text-align:right;margin-top:40px;padding-top:20px;border-top:2px solid #1a1a2e}'
      + '.block-ol{list-style:cjk-ideographic;padding-left:2em}';

    var h = '<style>' + css + '</style><div id="report-blocks">';

    blocks.forEach(function(block, i) {
      // 章节标题（第一个非 cover 的 block 触发章节）
      if (block.title && block.type !== 'cover') {
        // 用 priority 作为章节号
        h += '<h2 class="block-section-title">' + esc(block.title) + '</h2>';
      }

      var fn = renderBlock[block.type];
      if (fn) {
        try {
          h += fn(block, i, blocks);
        } catch(e) {
          h += '<div style="color:#dc2626;font-size:12px">⚠ 渲染 [' + block.type + '] 失败: ' + esc(e.message) + '</div>';
        }
      } else {
        h += '<div style="color:#999;font-size:12px;padding:8px;border:1px dashed #ddd">未定义渲染器: ' + esc(block.type) + '</div>';
      }
    });

    h += '</div>';
    targetEl.innerHTML = h;
  }

  // 挂载到全局
  window.renderReportBlocks = renderReportBlocks;
  window.renderBlock = renderBlock;
  console.log('[block-renderer] 报告块渲染器已就绪');
})();
