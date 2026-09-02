/**
 * 人类学习引擎 — 前端展示页
 * 12项认知能力详述 + 上下游模块关系 + 实时状态
 * API: /api/human-learning/status
 */
function renderHumanLearningPage(container) {
  if (!container) return;
  window.currentModule = '人类学习引擎';

  container.innerHTML =
    '<style>' +
    '.hl-wrap{max-width:960px;margin:0 auto;padding:20px 24px}' +
    // 段落
    '.hl-section{margin-bottom:28px}' +
    '.hl-sectitle{font-size:15px;font-weight:700;color:#0f172a;margin:0 0 12px;padding-left:10px;border-left:3px solid #2563eb;line-height:1.4}' +
    '.hl-para{font-size:13px;color:#475569;line-height:1.9;margin:0 0 10px;text-align:justify}' +
    '.hl-para strong{color:#0f172a}' +
    '.hl-para code{background:#f1f5f9;padding:1px 5px;border-radius:3px;font-size:11px;color:#2563eb}' +
    // 上下游
    '.hl-flow{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:28px}' +
    '.hl-flow-col{background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:14px 18px}' +
    '.hl-flow-title{font-size:13px;font-weight:700;color:#0f172a;margin:0 0 10px;display:flex;align-items:center;gap:6px}' +
    '.hl-flow-arrow{font-size:15px;font-weight:700}' +
    '.hl-flow-item{font-size:12px;color:#475569;line-height:1.8;margin-bottom:8px;padding-left:14px;position:relative}' +
    '.hl-flow-item:last-child{margin-bottom:0}' +
    '.hl-flow-item:before{content:"";position:absolute;left:0;top:9px;width:5px;height:5px;border-radius:50%;background:#94a3b8}' +
    '.hl-flow-item strong{color:#0f172a;font-weight:600}' +
    // 能力详述
    '.hl-ability{margin-bottom:10px;padding:12px 16px;background:#fff;border:1px solid #e2e8f0;border-radius:6px;transition:box-shadow .15s}' +
    '.hl-ability:hover{box-shadow:0 1px 4px rgba(0,0,0,.04)}' +
    '.hl-ability-h{display:flex;align-items:center;gap:8px;margin-bottom:4px}' +
    '.hl-ability-num{font-size:11px;font-weight:700;color:#fff;background:#2563eb;border-radius:50%;width:20px;height:20px;display:inline-flex;align-items:center;justify-content:center;flex-shrink:0}' +
    '.hl-ability-name{font-size:14px;font-weight:600;color:#0f172a}' +
    '.hl-badge{padding:2px 8px;border-radius:10px;font-size:10px;font-weight:600;margin-left:auto;white-space:nowrap}' +
    '.hl-badge-green{background:#dcfce7;color:#16a34a}' +
    '.hl-badge-red{background:#fee2e2;color:#dc2626}' +
    '.hl-badge-yellow{background:#fef3c7;color:#d97706}' +
    '.hl-badge-blue{background:#dbeafe;color:#2563eb}' +
    '.hl-badge-gray{background:#f1f5f9;color:#94a3b8}' +
    '.hl-ability-desc{font-size:12px;color:#64748b;line-height:1.8;margin:0}' +
    '.hl-ability-desc .num{font-weight:700;color:#0f172a}' +
    // 操作
    '.hl-actions{display:flex;gap:8px;margin-top:20px;padding-top:16px;border-top:1px solid #e2e8f0}' +
    '.hl-btn{padding:6px 14px;border:1px solid #e2e8f0;border-radius:6px;font-size:12px;cursor:pointer;background:#fff;color:#475569;transition:all .15s}' +
    '.hl-btn:hover{background:#f1f5f9;border-color:#cbd5e1}' +
    '.hl-btn-primary{background:#eff6ff;color:#2563eb;border-color:#bfdbfe}' +
    '.hl-btn-primary:hover{background:#dbeafe}' +
    // 状态
    '.hl-loading{text-align:center;padding:60px;color:#94a3b8;font-size:13px}' +
    '.hl-error{text-align:center;padding:40px;color:#dc2626;font-size:13px}' +
    '@media(max-width:700px){.hl-flow{grid-template-columns:1fr}}' +
    '</style>' +
    '<div class="hl-wrap">' +
    // 功能与作用
    '<div class="hl-section">' +
    '<div class="hl-sectitle">功能与作用</div>' +
    '<p class="hl-para">人类学习引擎是财税风险检查系统的<strong>自我进化核心</strong>。当风险检查员在资料风险分析报告中进行编辑纠正、审核确认或追问补充时，引擎不是简单地接受修改，而是模拟人类认知的12项能力，从纠正内容中提炼规则、验证真伪、发现关联、回测效果，最终形成可复用的知识沉淀。</p>' +
    '<p class="hl-para">与传统规则引擎不同，人类学习引擎引入了<strong>容错机制</strong>（3次确认后才采纳纠正）、<strong>遗忘机制</strong>（30天降权、180天归档无效规则）和<strong>渐进调整</strong>（每次\u00b15%逐步调权），避免因单次误操作导致规则被污染。引擎还会在纠正内容模糊时<strong>主动反问</strong>用户确认，而非盲目猜测。</p>' +
    '<p class="hl-para">统一学习入口 <code>learner.learn(correction, source, context)</code> 串联了记忆\u2192容错验证\u2192主动提问\u2192因果推理\u2192冲突检测\u2192关系发现\u2192渐进调整的完整链路，每次用户纠正都会触发这条学习流水线。</p>' +
    '</div>' +
    // 上下游模块
    '<div class="hl-flow">' +
    '<div class="hl-flow-col">' +
    '<div class="hl-flow-title"><span class="hl-flow-arrow" style="color:#16a34a">\u2193</span> 上游关联模块</div>' +
    '<div class="hl-flow-item"><strong>\u8d44\u6599\u98ce\u9669\u5206\u6790\u62a5\u544a</strong> \u2014 \u7528\u6237\u5728\u62a5\u544a\u4e2d\u7f16\u8f91\u7ea0\u6b63\u3001\u5ba1\u6838\u786e\u8ba4\u3001\u8ffd\u95ee\u8865\u5145\u65f6\uff0c\u901a\u8fc7 /api/human-learning/learn \u63a5\u53e3\u89e6\u53d1\u5b66\u4e60</div>' +
    '<div class="hl-flow-item"><strong>\u7a3d\u67e5\u5458\u63a8\u7406\u5f15\u64ce</strong> \u2014 \u63a8\u7406\u5f15\u64ce\u4ea7\u51fa\u7684\u5206\u6790\u7ed3\u8bba\u88ab\u7528\u6237\u7ea0\u6b63\uff0c\u7ea0\u6b63\u5185\u5bb9\u4f5c\u4e3a\u5b66\u4e60\u7d20\u6750\u8f93\u5165\u5f15\u64ce</div>' +
    '<div class="hl-flow-item"><strong>\u89c4\u5219\u5f15\u64ce</strong> \u2014 \u521d\u59cb\u89c4\u5219\u914d\u7f6e\u4e3a\u5b66\u4e60\u5f15\u64ce\u63d0\u4f9b\u57fa\u7ebf\u89c4\u5219\uff0c\u5b66\u4e60\u5f15\u64ce\u5728\u6b64\u57fa\u7840\u4e0a\u4fee\u6b63\u548c\u8fdb\u5316</div>' +
    '</div>' +
    '<div class="hl-flow-col">' +
    '<div class="hl-flow-title"><span class="hl-flow-arrow" style="color:#dc2626">\u2191</span> \u4e0b\u6e38\u5173\u8054\u6a21\u5757</div>' +
    '<div class="hl-flow-item"><strong>\u89c4\u5219\u5f15\u64ce</strong> \u2014 \u5b66\u4e60\u5f15\u64ce\u4ea7\u51fa\u7684\u6d3b\u8dc3\u89c4\u5219\u56de\u6d41\u5230\u89c4\u5219\u5f15\u64ce\uff0c\u5f71\u54cd\u540e\u7eed\u5206\u6790\u5224\u65ad\u7684\u51c6\u786e\u5ea6</div>' +
    '<div class="hl-flow-item"><strong>\u7a3d\u67e5\u65b9\u6cd5\u8bba</strong> \u2014 \u6839\u56e0\u5206\u6790\u7ed3\u679c\u53cd\u9988\u5230\u65b9\u6cd5\u8bba\u4f53\u7cfb\uff0c\u4f18\u5316\u7a3d\u67e5\u7b56\u7565\u548c\u68c0\u67e5\u91cd\u70b9</div>' +
    '<div class="hl-flow-item"><strong>\u7a3d\u67e5\u5458\u63a8\u7406\u5f15\u64ce</strong> \u2014 \u5b66\u4e60\u540e\u7684\u89c4\u5219\u7f6e\u4fe1\u5ea6\u548c\u5173\u8054\u5173\u7cfb\u4f9b\u63a8\u7406\u5f15\u64ce\u8c03\u7528\uff0c\u63d0\u5347\u63a8\u7406\u8d28\u91cf</div>' +
    '</div>' +
    '</div>' +
    // 12项认知能力
    '<div class="hl-section">' +
    '<div class="hl-sectitle">12\u9879\u8ba4\u77e5\u80fd\u529b\u8be6\u8ff0</div>' +
    '<div id="hl-content" class="hl-loading">\u52a0\u8f7d\u5f15\u64ce\u72b6\u6001...</div>' +
    '</div>' +
    '</div>';

  loadHumanLearningState();
}

async function loadHumanLearningState() {
  var el = document.getElementById('hl-content');
  if (!el) return;
  try {
    var resp = await fetch('/api/human-learning/status');
    var data = await resp.json();
    if (!data.ok) {
      el.innerHTML = '<div class="hl-error">\u52a0\u8f7d\u5931\u8d25: ' + (data.message || '\u672a\u77e5') + '</div>';
      return;
    }
    renderHLState(data.status);
  } catch(e) {
    el.innerHTML = '<div class="hl-error">\u8fde\u63a5\u5931\u8d25: ' + e.message + '</div>';
  }
}

function renderHLState(st) {
  var el = document.getElementById('hl-content');
  if (!el) return;

  var abilities = [
    {
      num: 1, name: '\u8bb0\u5fc6', key: '\u8bb0\u5fc6',
      desc: '\u5f15\u64ce\u8bb0\u4f4f\u6bcf\u6b21\u51b3\u7b56\u7684\u539f\u56e0\u548c\u7ed3\u679c\uff0c\u4fdd\u7559\u6700\u8fd1500\u6761\u51b3\u7b56\u65e5\u5fd7\u3002\u652f\u6301\u6309\u5173\u952e\u8bcd\u68c0\u7d22\u5386\u53f2\u51b3\u7b56\u8fdb\u884c\u81ea\u7701\u56de\u987e\uff0c\u56de\u7b54\u201c\u4e0a\u6b21\u7c7b\u4f3c\u60c5\u51b5\u662f\u600e\u4e48\u5904\u7406\u7684\u201d\u3002\u5f53\u524d\u5df2\u8bb0\u5f55 <span class="num">' + (st['\u8bb0\u5fc6'] || 0) + '</span> \u6761\u51b3\u7b56\u8bb0\u5fc6\u3002',
      badgeKey: '\u8bb0\u5fc6', badgeType: 'blue'
    },
    {
      num: 2, name: '\u9057\u5fd8', key: '\u5df2\u5f52\u6863\u89c4\u5219',
      desc: '\u5f15\u64ce\u4e0d\u662f\u65e0\u9650\u5806\u79ef\u89c4\u5219\uff0c\u800c\u662f\u5b9a\u671f\u68c0\u67e5\u6d3b\u8dc3\u89c4\u5219\u7684\u4f7f\u7528\u9891\u7387\u3002\u8d85\u8fc730\u5929\u672a\u4f7f\u7528\u7684\u89c4\u5219\u964d\u4f4e\u7f6e\u4fe1\u5ea6\uff0c\u8d85\u8fc7180\u5929\u7684\u81ea\u52a8\u5f52\u6863\u3002\u8fd9\u786e\u4fdd\u89c4\u5219\u5e93\u4fdd\u6301\u7cbe\u7b80\u6709\u6548\u3002\u5f53\u524d\u5df2\u5f52\u6863 <span class="num">' + (st['\u5df2\u5f52\u6863\u89c4\u5219'] || 0) + '</span> \u6761\u89c4\u5219\u3002',
      badgeKey: '\u5df2\u5f52\u6863\u89c4\u5219', badgeType: 'gray'
    },
    {
      num: 3, name: '\u4e3e\u4e00\u53cd\u4e09', key: '\u6d3b\u8dc3\u89c4\u5219',
      desc: '\u4e00\u6761\u89c4\u5219\u5728\u67d0\u4e2a\u884c\u4e1a\u9a8c\u8bc1\u6709\u6548\u540e\uff0c\u5f15\u64ce\u5c1d\u8bd5\u4ee570%\u7f6e\u4fe1\u5ea6\u8fc1\u79fb\u5230\u5176\u4ed6\u884c\u4e1a\uff0c\u6807\u8bb0\u4e3a\u201c\u9700\u4eba\u5de5\u786e\u8ba4\u201d\u3002\u8fd9\u5b9e\u73b0\u4e86\u4e00\u6b21\u5b66\u4e60\u3001\u8de8\u884c\u4e1a\u590d\u7528\u3002\u5f53\u524d\u6709 <span class="num">' + (st['\u6d3b\u8dc3\u89c4\u5219'] || 0) + '</span> \u6761\u6d3b\u8dc3\u89c4\u5219\u3002',
      badgeKey: '\u6d3b\u8dc3\u89c4\u5219', badgeType: 'purple'
    },
    {
      num: 4, name: '\u8d28\u7591\u81ea\u5df1', key: '\u5f85\u89e3\u51b3\u51b2\u7a81',
      desc: '\u5f53\u65b0\u8bc1\u636e\u4e0e\u65e7\u89c4\u5219\u77db\u76fe\u65f6\uff0c\u5f15\u64ce\u4e0d\u76f2\u76ee\u8986\u76d6\u65e7\u89c4\u5219\uff0c\u800c\u662f\u767b\u8bb0\u51b2\u7a81\u3001\u964d\u4f4e\u89c4\u5219\u7f6e\u4fe1\u5ea6\u5e76\u6807\u8bb0\u4e3a\u201c\u6709\u4e89\u8bae\u201d\uff0c\u7b49\u5f85\u4eba\u5de5\u88c1\u51b3\u3002\u5f53\u524d\u6709 <span class="num">' + (st['\u5f85\u89e3\u51b3\u51b2\u7a81'] || 0) + '</span> \u4e2a\u672a\u89e3\u51b3\u51b2\u7a81\u3002',
      badgeKey: '\u5f85\u89e3\u51b3\u51b2\u7a81', badgeType: 'red'
    },
    {
      num: 5, name: '\u62bd\u8c61\u5f52\u7eb3', key: '\u5df2\u5f52\u7eb3\u805a\u7c7b',
      desc: '\u5f53\u591a\u6761\u7528\u6237\u7ea0\u6b63\u6307\u5411\u540c\u4e00\u6839\u672c\u95ee\u9898\u65f6\uff0c\u5f15\u64ce\u63d0\u53d6\u5171\u540c\u5173\u952e\u8bcd\uff0c\u5c1d\u8bd5\u7528LLM\u5f52\u7eb3\u4e3a\u4e00\u6761\u901a\u7528\u89c4\u5219\uff0c\u907f\u514d\u89c4\u5219\u788e\u7247\u5316\u3002\u5f53\u524d\u5df2\u5f52\u7eb3 <span class="num">' + (st['\u5df2\u5f52\u7eb3\u805a\u7c7b'] || 0) + '</span> \u4e2a\u805a\u7c7b\u3002',
      badgeKey: '\u5df2\u5f52\u7eb3\u805a\u7c7b', badgeType: 'purple'
    },
    {
      num: 6, name: '\u56e0\u679c\u63a8\u7406', key: '\u6839\u56e0\u5206\u6790',
      desc: '\u6bcf\u6b21\u51fa\u9519\u540e\uff0c\u5f15\u64ce\u5206\u6790\u201c\u4e3a\u4ec0\u4e48\u4f1a\u9519\u201d\u2014\u2014\u662f\u7a0e\u7387\u914d\u7f6e\u95ee\u9898\u3001\u542b\u7a0e/\u4e0d\u542b\u7a0e\u672a\u533a\u5206\u3001\u79d1\u76ee\u5206\u7c7b\u9519\u8bef\uff0c\u8fd8\u662f\u884c\u4e1a\u7279\u6b8a\u6027\u672a\u8003\u8651\u3002\u5f53\u524d\u5df2\u8bb0\u5f55 <span class="num">' + (st['\u6839\u56e0\u5206\u6790'] || 0) + '</span> \u6761\u6839\u56e0\u3002',
      badgeKey: '\u6839\u56e0\u5206\u6790', badgeType: 'blue'
    },
    {
      num: 7, name: '\u5bb9\u9519\u673a\u5236', key: '\u5f85\u9a8c\u8bc1\u7ea0\u6b63',
      desc: '\u7528\u6237\u7ea0\u6b63\u4e0d\u4f1a\u7acb\u5373\u53d8\u4e3a\u89c4\u5219\u3002\u5f15\u64ce\u8981\u6c42\u540c\u4e00\u7ea0\u6b63\u51fa\u73b03\u6b21\u540e\u624d\u91c7\u7eb3\u4e3a\u6b63\u5f0f\u89c4\u5219\uff08\u7f6e\u4fe1\u5ea60.8\uff09\uff0c\u9632\u6b62\u5355\u6b21\u8bef\u64cd\u4f5c\u6c61\u67d3\u89c4\u5219\u5e93\u3002\u5f53\u524d\u6709 <span class="num">' + (st['\u5f85\u9a8c\u8bc1\u7ea0\u6b63'] || 0) + '</span> \u6761\u5f85\u9a8c\u8bc1\u3002',
      badgeKey: '\u5f85\u9a8c\u8bc1\u7ea0\u6b63', badgeType: 'yellow'
    },
    {
      num: 8, name: '\u4e3b\u52a8\u63d0\u95ee', key: '\u5f85\u56de\u7b54\u95ee\u9898',
      desc: '\u5f53\u7ea0\u6b63\u5185\u5bb9\u6a21\u7cca\u65f6\uff08\u5982\u201c\u4e3b\u8425\u4e1a\u52a1\u201d\u5224\u65ad\u6807\u51c6\u4e0d\u6e05\u3001\u7a0e\u7387\u4f9d\u636e\u4e0d\u660e\uff09\uff0c\u5f15\u64ce\u4e3b\u52a8\u751f\u6210\u53cd\u95ee\u95ee\u9898\uff0c\u8981\u6c42\u7528\u6237\u6f84\u6e05\u800c\u975e\u731c\u6d4b\u3002\u5f53\u524d\u6709 <span class="num">' + (st['\u5f85\u56de\u7b54\u95ee\u9898'] || 0) + '</span> \u4e2a\u5f85\u56de\u7b54\u95ee\u9898\u3002',
      badgeKey: '\u5f85\u56de\u7b54\u95ee\u9898', badgeType: 'red'
    },
    {
      num: 9, name: '\u81ea\u6211\u8bc4\u4f30', key: '\u6d3b\u8dc3\u89c4\u5219',
      desc: '\u5f15\u64ce\u7ed9\u6bcf\u6761\u89c4\u5219\u6253\u7f6e\u4fe1\u5ea6\u5206\uff08\u57fa\u7840\u4fe1\u4efb40%\u002b\u4f7f\u7528\u6b21\u657030%\u002d\u51b2\u7a81\u6263\u5206\u002d\u5e74\u9f84\u8870\u51cf\uff09\uff0c\u4f4e\u4e8e50%\u6807\u8bb0\u201c\u9700\u4eba\u5de5\u590d\u6838\u201d\u3002\u5f53\u524d\u6709 <span class="num">' + (st['\u6d3b\u8dc3\u89c4\u5219'] || 0) + '</span> \u6761\u89c4\u5219\u5df2\u8bc4\u4f30\u3002',
      badgeKey: '\u6d3b\u8dc3\u89c4\u5219', badgeType: 'green'
    },
    {
      num: 10, name: '\u6e10\u8fdb\u8c03\u6574', key: '\u6d3b\u8dc3\u89c4\u5219',
      desc: '\u89c4\u5219\u6743\u91cd\u4e0d\u662f\u8df3\u53d8\u5f0f\u8c03\u6574\uff0c\u800c\u662f\u6bcf\u6b21\u00b15%\u9010\u6b65\u5fae\u8c03\uff0c\u8bb0\u5f55\u5b8c\u6574\u7684\u8c03\u6574\u5386\u53f2\uff0c\u907f\u514d\u89c4\u5219\u6743\u91cd\u5267\u70c8\u6ce2\u52a8\u3002\u8c03\u6574\u5747\u5728\u6d3b\u8dc3\u89c4\u5219\u4e0a\u8fdb\u884c\u3002',
      badgeKey: '\u6d3b\u8dc3\u89c4\u5219', badgeType: 'blue'
    },
    {
      num: 11, name: '\u56de\u6d4b\u9a8c\u8bc1', key: '\u56de\u6d4b\u8bb0\u5f55',
      desc: '\u65b0\u89c4\u5219\u6b63\u5f0f\u91c7\u7eb3\u524d\uff0c\u7528\u5386\u53f2\u5206\u6790\u7f13\u5b58\u8dd1\u56de\u6d4b\uff0c\u5bf9\u6bd4\u5e94\u7528\u524d\u540e\u7684\u53d1\u73b0\u6570\u91cf\u53d8\u5316\uff08delta\uff09\uff0c\u91cf\u5316\u89c4\u5219\u7684\u5b9e\u9645\u5f71\u54cd\u3002\u5f53\u524d\u6709 <span class="num">' + (st['\u56de\u6d4b\u8bb0\u5f55'] || 0) + '</span> \u6761\u56de\u6d4b\u8bb0\u5f55\u3002',
      badgeKey: '\u56de\u6d4b\u8bb0\u5f55', badgeType: 'purple'
    },
    {
      num: 12, name: '\u5173\u7cfb\u53d1\u73b0', key: '\u89c4\u5219\u5173\u8054',
      desc: '\u5f15\u64ce\u5206\u6790\u89c4\u5219\u4e4b\u95f4\u7684\u5173\u8054\uff1a\u5185\u5bb9\u76f8\u4f3c\uff08>50%\u76f8\u4f3c\u5ea6\uff09\u3001\u540c\u884c\u4e1a\u3001\u540c\u53d1\u73b0\u7c7b\u578b\uff0c\u6784\u5efa\u89c4\u5219\u5173\u8054\u7f51\u7edc\uff0c\u4e3a\u8de8\u57df\u5206\u6790\u63d0\u4f9b\u57fa\u7840\u3002\u5f53\u524d\u5df2\u53d1\u73b0 <span class="num">' + (st['\u89c4\u5219\u5173\u8054'] || 0) + '</span> \u6761\u5173\u8054\u3002',
      badgeKey: '\u89c4\u5219\u5173\u8054', badgeType: 'red'
    },
  ];

  var html = '';
  abilities.forEach(function(a){
    var val = st[a.key] || 0;
    var badgeText = val > 0 ? val + ' \u6761' : '\u5c31\u7eea';
    var badgeClass = val > 0 ? 'hl-badge-' + a.badgeType : 'hl-badge-gray';
    html += '<div class="hl-ability">' +
      '<div class="hl-ability-h">' +
      '<span class="hl-ability-num">' + a.num + '</span>' +
      '<span class="hl-ability-name">' + a.name + '</span>' +
      '<span class="hl-badge ' + badgeClass + '">' + badgeText + '</span>' +
      '</div>' +
      '<p class="hl-ability-desc">' + a.desc + '</p>' +
      '</div>';
  });

  // 操作按钮
  html += '<div class="hl-actions">' +
    '<button class="hl-btn" onclick="callHLAction(\'decay\')">\u89e6\u53d1\u9057\u5fd8\u8870\u51cf</button>' +
    '<button class="hl-btn" onclick="callHLAction(\'relationships\')">\u89e6\u53d1\u5173\u7cfb\u53d1\u73b0</button>' +
    '<button class="hl-btn hl-btn-primary" onclick="loadHumanLearningState()">\u5237\u65b0\u72b6\u6001</button>' +
    '</div>';

  el.innerHTML = html;
}

async function callHLAction(action) {
  try {
    var resp = await fetch('/api/human-learning/' + action, {method:'POST'});
    var data = await resp.json();
    if (data.ok) {
      loadHumanLearningState();
    } else {
      alert('\u64cd\u4f5c\u5931\u8d25: ' + (data.message || ''));
    }
  } catch(e) {
    alert('\u8bf7\u6c42\u5931\u8d25: ' + e.message);
  }
}
