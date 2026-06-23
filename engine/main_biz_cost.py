# 主营业务成本识别模块（全行业适用）
# 所有进销相关风险分析必须先识别主营业务成本，再分类判断。
# 核心原则：
#   1. 日常费用报销（餐饮/住宿/汽油等）→ 不参与供应商匹配/进销比对
#   2. 主营业务成本（原料/加工费/主要经营货物）→ 必须匹配验证
#   3. 重大费用（房租/咨询/广告等）→ 视情况匹配
# 稽查方法论：先分三层，再逐层分析，而非一刀切全量比对。
# ═══════════════════════════════════════════════════════════

# ├─ 日常报销关键词（全行业通用）
# │  员工先行垫付后凭发票报销，对公付款对象是员工而非开票单位
_REIMBURSEMENT_KWS_GLOBAL = [
    # 餐饮
    '餐饮','餐费','饭店','餐厅','食堂','伙食','外卖','快餐','盒饭','快餐费',
    # 住宿
    '住宿','酒店','宾馆','房费','旅馆','招待所','旅社','日租房',
    # 交通/加油
    '汽油','柴油','加油','车用','充电','过路费','停车费','停车','打车','出租车','网约车',
    # 差旅
    '差旅','机票','火车票','高铁','动车','船票',
    # 办公杂费
    '办公用品','文具','打印','复印','纸张','墨盒','色带','硒鼓','胶水','文件夹','档案盒',
    '快递','邮递','邮寄','运费','搬运费',
    '通讯','电话','话费','网络费','短信',
    # 培训/会务
    '培训','会务','展会','研讨会','讲座','论坛',
    # 劳保/福利
    '劳保','工作服','手套','口罩','防护','安全帽','防尘','员工体检','团建',
    # 其他杂项
    '保洁','清洁','卫生','洗涤','垃圾','年检',
]

# ├─ 重大费用关键词（需对公付款但非主营成本）
_MAJOR_EXPENSE_KWS = [
    '房租','租金','物业','物业管理',
    '咨询','顾问','法律','审计','评估','检测','认证',
    '广告','推广','宣传','展览','展会','发布',
    '运输','物流','货运','搬运','配送',
    '维修','保养','修缮','装修','装潢',
    '保险','社保','托管','代账',
    '招聘','猎头','人力资源',
]

def identify_main_biz_cost(pur_invs, sal_invs=None):
    """
    识别主营业务成本，将进项发票分为三层。
    
    参数:
        pur_invs: 进项发票列表
        sal_invs: 销项发票列表（可选，用于品名重合判断）
    
    返回:
        {
            "core_cost_invs": [...],      # 主营业务成本
            "major_expense_invs": [...],  # 重大费用
            "minor_expense_invs": [...],  # 日常报销
            "pur_core_goods": set(),      # 主营业务品名集合
            "pur_expense_goods": set(),   # 费用类品名集合
        }
    
    识别逻辑（像人类稽查员一样思考）:
    1. 日常报销关键词 → minor_expense（员工垫付后报销，付款对象非开票单位）
    2. 重大费用关键词 → major_expense（需对公付款，但不是主营成本）
    3. 加工费 → core_cost（制造业核心成本）
    4. 进销品名重合项 → core_cost（买什么卖什么=主营业务）
    5. 大额采购（>=总采购额5%）→ core_cost
    6. 余额 → 按关键词倾向判断
    """
    core_cost_invs = []
    major_expense_invs = []
    minor_expense_invs = []
    pur_core_goods = set()
    pur_expense_goods = set()
    
    if not pur_invs:
        return {
            "core_cost_invs": core_cost_invs,
            "major_expense_invs": major_expense_invs,
            "minor_expense_invs": minor_expense_invs,
            "pur_core_goods": pur_core_goods,
            "pur_expense_goods": pur_expense_goods,
        }
    
    # 提取销项品名集合（用于进销品名重合判断）
    sale_goods_set = set()
    if sal_invs:
        for inv in sal_invs:
            g = str(inv.get("goods", inv.get("货物或应税劳务名称", ""))).strip()
            if g: sale_goods_set.add(g)
    
    # 计算总采购额（用于大额判断）
    total_pur_amount = sum(float(inv.get("amount", inv.get("total", 0)) or 0) for inv in pur_invs)
    big_amount_threshold = total_pur_amount * 0.05  # 单品类>=5%视为重大
    
    for inv in pur_invs:
        goods = str(inv.get("goods", inv.get("货物或应税劳务名称", ""))).strip()
        amount = float(inv.get("amount", inv.get("total", 0)) or 0)
        
        # 规则1: 日常报销关键词 → 员工垫付报销模式
        if any(kw in goods for kw in _REIMBURSEMENT_KWS_GLOBAL):
            minor_expense_invs.append(inv)
            pur_expense_goods.add(goods)
            continue
        
        # 规则2: 重大费用关键词 → 需对公付款但非主营成本
        if any(kw in goods for kw in _MAJOR_EXPENSE_KWS):
            major_expense_invs.append(inv)
            pur_expense_goods.add(goods)
            continue
        
        # 规则3: 加工费 → 制造业核心成本
        if '加工' in goods or '加工费' in goods:
            core_cost_invs.append(inv)
            pur_core_goods.add(goods)
            continue
        
        # 规则4: 进销品名重合 → 买什么卖什么=主营业务
        if goods in sale_goods_set:
            core_cost_invs.append(inv)
            pur_core_goods.add(goods)
            continue
        
        # 规则5: 大额采购（>=5%总额）→ 大概率是主营业务
        if amount >= big_amount_threshold and amount > 0:
            core_cost_invs.append(inv)
            pur_core_goods.add(goods)
            continue
        
        # 规则6: 余额 → 默认归入主营业务成本（保守策略）
        # 企业正常经营中，采购的大头是主营成本，小杂项后续可由关键词持续完善
        core_cost_invs.append(inv)
        pur_core_goods.add(goods)
    
    return {
        "core_cost_invs": core_cost_invs,
        "major_expense_invs": major_expense_invs,
        "minor_expense_invs": minor_expense_invs,
        "pur_core_goods": pur_core_goods,
        "pur_expense_goods": pur_expense_goods,
    }


# ═══════════════════════════════════════════════════════════
# 稽查员推理引擎（Audit Reasoning Engine）
# 
# 核心设计理念：
#   不是29个域并行跑完再汇总，而是像人类稽查员一样——
#   初查发现信号 → 定向深挖 → 交叉验证 → 综合定性
# 
# 四个阶段：
#   Phase 1 — 初查（Triage）：资金流全景、发票全景、主营业务成本识别、
#             基本比率、资料质量评估。产出全局快照+初步信号。
#   Phase 2 — 定向深挖（Deep Dive）：基于Phase 1信号，选择性深入分析
#             关联域。信号驱动，而非全量盲跑。
#   Phase 3 — 交叉验证（Cross-Validation）：用多域结论互相印证。
#             利用已有结论验证/反驳/深化新结论。
#   Phase 4 — 综合定性（Synthesis）：汇总→去重→冲突消解→风险排序→
#             生成最终报告。
#
# AuditContext 是阶段间的状态载体，贯穿4个阶段。
# 每个阶段读取context中的前置发现，产出注入context供后续使用。
# ═══════════════════════════════════════════════════════════

