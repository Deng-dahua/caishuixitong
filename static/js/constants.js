// ==================== 全局常量（替换魔法字符串）====================
const STATUS = {
  // 发票/档案通用状态
  NORMAL: '正常',
  VOID: '作废',
  RED: '红冲',
  // 勾选状态
  CHECKED: '已勾选',
  UNCHECKED: '未勾选',
  // 认证/抵扣状态
  CERTIFIED: '已认证',
  DEDUCTED: '已抵扣',
  PARTIAL: '部分抵扣',
  NOT_DEDUCTIBLE: '不得抵扣',
  // 付款状态
  PENDING: '待审批',
  APPROVED: '已审批',
  PAID: '已付款',
  REJECTED: '已驳回',
  // 风险等级
  RISK_NORMAL: '正常',
  RISK_FOLLOW: '关注',
  FOLLOW_ATTENTION: '关注',
  RISK_WARN: '疑点',
  RISK_ABNORMAL: '异常',
  RISK_LOST: '失控',
};
const PAYMENT_STATUS_COLORS = {
  '待审批': '#c27803',
  '已审批': '#1a56db',
  '已付款': '#0e9f6e',
  '已驳回': '#e02424'
};

// ==================== 风险等级展示映射（唯一权威的 JS 侧镜像）====================
// ★ 2026-10-15（用户裁定）：等级「待核验/待核」的**呈现措辞**统一为「涉嫌风险」——
//   该等级的含义是"已触碰税务红线、但尚未定性"，称"待核验"会让企业误以为
//   疑点没核出来。底层数据值不变（兼容既有载荷，结构性字段不得改写），
//   所有显示经此单点映射。
// ★ 本表是后端唯一权威 `engine/risk_levels.py::DISPLAY_LABELS` 的 JS 侧镜像，
//   由闸门 `check_level_display_single_source` 逐键比对（新增一档=两边各加一行）。
var LEVEL_DISPLAY = { '待核验': '涉嫌风险', '待核': '涉嫌风险' };
function levelDisplayOf(lv) {
  var s = String(lv === null || lv === undefined ? '' : lv).trim();
  return LEVEL_DISPLAY[s] || s;
}
// ============================================================

