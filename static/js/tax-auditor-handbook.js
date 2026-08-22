/* 企业内部财税风险核验手册。不得将本页面解释为税务机关执法流程或文书。 */
function renderAuditorHandbook(container) {
  if (!container) return;
  window.currentModule = '财税风险核验方法手册';

  var chapters = [
    ['1. 任务、主体与期间', '先冻结被核验企业、纳税人身份、所属期、业务范围和案件快照。主体或期间不明时，所有场景只能输出资料不足。'],
    ['2. 资料覆盖与质量', '逐类登记申报、账簿、凭证、发票、资金、合同、物流、工资、资产和关联方资料；记录文件哈希、页/行、解析状态、期间及缺口。'],
    ['3. 场景适用性', '先判断行业、交易类型、税种和纳税人身份，再运行适用场景。行业未知时不得默认套用制造、商贸或服务业场景。'],
    ['4. 五链核验', '每个事项必须形成线索链、证据链、分析链、政策链和金额链，并能回到原文件和计算底稿。'],
    ['5. 反向证据', '每项不利线索都要列出正常商业解释、支持该解释的资料、排除路径和停止条件，禁止只收集不利证据。'],
    ['6. 五状态结论', '统一使用资料不足、存在线索、事实倾向支持、事实充分支持待审理、已排除或已整改验证；风险分只用于排序。'],
    ['7. 政策有效性', '按事实期间核验官方来源、生效和失效日期、纳税人身份及属地条件。过期政策不得靠网页相似文本自动续期。'],
    ['8. 金额复算', '记录税基、税率、公式、来源字段、期间和舍入规则，区分确定数、估算数和无法测算。没有底稿不得给出确定金额。'],
    ['9. 风险卡与报告', '按固定顺序表达已观察事实、目标事实、当前状态、资料缺口、正常解释、调查步骤、政策边界、金额和人工复核。'],
    ['10. 整改任务', '整改建议必须合法、真实、可验证，并写明责任人、计划日期、所需资料、完成标准、回传证据和重跑触发器。'],
    ['11. 税收优惠与权益', '优惠独立形成待核验权益候选，不混入风险发现；系统不得自动确认资格、承诺收益或代替申报。'],
    ['12. 复查与收敛', '补充资料后建立新快照并重跑全部场景，比较消除、降低、不变、新增和反弹，逐轮趋于合规。'],
    ['13. 权利与保密', '企业可补充有利证据和正常解释。商业秘密、个人信息和文件按最小权限使用；正式程序权利以实际送达文书和现行法律为准。'],
    ['14. 发布与留痕', '方法论、证据、政策、金额、报告质量和人工签署闸门全部通过后才允许正式发布；保留版本差异和全量操作轨迹。']
  ];

  var h = '<div style="max-width:980px;margin:0 auto;padding:36px 28px;font-family:-apple-system,\"Microsoft YaHei\",sans-serif">';
  h += '<h1 style="font-size:24px;color:#16233a;margin:0 0 10px">财税风险核验方法手册</h1>';
  h += '<p style="font-size:13px;color:#64748b;line-height:1.9;margin:0 0 18px">本手册服务于企业内部持续合规：已上传资料全量核验，未上传资料形成可追踪缺口；整改后建立新快照并全量重跑。系统是辅助分析工具，不冒充或替代税务机关的选案、检查、审理、处理或救济程序。</p>';
  h += '<div style="padding:14px 16px;border:1px solid #fed7aa;background:#fff7ed;border-radius:8px;color:#9a3412;line-height:1.8;margin-bottom:18px"><b>四条硬边界：</b>缺资料不定性；模型分不定性；过期政策不自动续期；报告与优惠不自动发布或办理。</div>';
  h += '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:12px">';
  chapters.forEach(function(chapter) {
    h += '<article style="background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:16px 18px">'
      + '<h2 style="font-size:15px;color:#1e293b;margin:0 0 8px">' + chapter[0] + '</h2>'
      + '<p style="font-size:12px;color:#475569;line-height:1.9;margin:0">' + chapter[1] + '</p>'
      + '</article>';
  });
  h += '</div>';
  h += '<div style="margin-top:18px;padding:14px 16px;border:1px solid #bfdbfe;background:#eff6ff;border-radius:8px;color:#1e40af;line-height:1.8"><b>风险关闭条件：</b>真实证据进入新快照，原异常被解释或纠正，相关账、票、款、税一致，金额完成复算，关联场景重跑通过，且由有权人员复核。</div>';
  h += '</div>';
  container.innerHTML = h;
}
