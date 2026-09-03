# -*- coding: utf-8 -*-
"""经营模式识别（系统级共享能力）

背景
----
此前原子规则（典型如 VR024「个人或个体工商户供应商客户交易核验」）在判定时
**完全不知道被检查企业是干什么的**——规则引擎拿到的数据里既没有企业名称、
也没有行业和经营范围，只能"见个人主体就报风险"。结果是：宠物用品电商面向
普通消费者的正常零售被当成税务疑点（如"个人客户107家，合计41,705元"，
户均消费仅390元），形成典型误报。

本模块把"人类常识级"的经营模式判断沉淀为可复用能力：从工商信号与发票结构
两类证据综合推断企业是零售/电商（B2C）还是批发/生产/服务（B2B），
供全部规则共享，使规则在判定"个人主体交易是否异常"时先明确经营模式。

判定原则（与系统「发现≠确认」铁律一致）
--------------------------------------
* 本模块只提供**证据与结论倾向**，不替代规则裁决；
* 证据充分（is_b2c_retail=True）时，正常经营假设胜出，规则应判非风险；
* 证据不足（mixed）时，规则应转置疑清单要求企业说明经营模式，不得自动放过；
* 即使认定为零售模式，**异常子特征（关联自然人、巨额单户、伪装零售的批发）
  仍然必须暴露**，绝不因模式认定而屏蔽任何信号。
"""

from collections import defaultdict

# ══════════════════════════════════════════════════════════════
# 关键词库
# ══════════════════════════════════════════════════════════════

# 电商平台主体：出现在购方名称中，说明企业通过电商平台面向消费者销售
_ECOMMERCE_PLATFORM_KEYWORDS = (
    "天猫", "淘宝", "阿里妈妈", "阿里巴巴", "京东", "拼多多", "抖音", "快手",
    "唯品会", "苏宁", "小红书", "美团", "饿了么", "得物", "网易严选",
    "微店", "有赞", "小程序", "视频号",
)

# 零售/电商经营信号：出现在企业名称或经营范围中
_RETAIL_SIGNAL_KEYWORDS = (
    "零售", "电子商务", "互联网销售", "网上销售", "网络销售", "电商",
    "店铺", "门店", "连锁", "专卖", "便利店", "商超", "超市", "直销",
    "日用百货", "母婴", "宠物用品",
)

# 面向消费者的品类（销项品名），辅助印证终端零售
_CONSUMER_GOODS_KEYWORDS = (
    "饲料", "猫粮", "犬粮", "宠物", "零食", "日用", "母婴", "奶粉",
    "美妆", "化妆", "服饰", "服装", "鞋", "家居", "玩具", "生鲜",
    "食品", "饮料", "洗护",
)

# 批发/生产信号（反向证据）
_WHOLESALE_SIGNAL_KEYWORDS = ("批发", "经销", "代理", "制造", "生产", "加工", "工程", "施工")

# 被判为批零/商贸的行业写法
_RETAIL_INDUSTRY_LABELS = (
    "批发零售", "批发和零售业", "商贸", "商业", "零售", "批发", "贸易", "电子商务",
    "F",  # 国民经济行业分类门类 F = 批发和零售业
)

# ══════════════════════════════════════════════════════════════
# 阈值（集中配置，便于统一复核）
# ══════════════════════════════════════════════════════════════

# 零售票均金额：单张销项发票不含税金额低于该值，属消费级小额
RETAIL_AVG_INVOICE_AMOUNT = 2000.0
# 零售户均金额：单个客户累计销售额低于该值，属消费级
RETAIL_AVG_CUSTOMER_AMOUNT = 3000.0
# 客户分散度：客户家数达到该值视为高度分散
DISPERSED_CUSTOMER_COUNT = 30
# 单一客户占比上限：最大客户销售额占比低于该值视为不依赖单一客户
TOP1_CUSTOMER_SHARE_LIMIT = 0.30

# 判为零售模式的证据分门槛
RETAIL_SCORE_THRESHOLD = 5.0
# 弱证据区间下界（≥该值但不足零售门槛时，转置疑清单由企业说明）
WEAK_SCORE_THRESHOLD = 3.0

# 零售模式下仍必须暴露的异常子特征阈值
# 单个自然人客户累计销售额超过该值，已非消费级，须核查
ABNORMAL_SINGLE_CUSTOMER_AMOUNT = 500000.0
# 伪装零售的批发：个人客户家数少但户均巨大
DISGUISED_WHOLESALE_MIN_AVG = 100000.0
DISGUISED_WHOLESALE_MAX_COUNT = 5


def _number(value, default=0.0):
    try:
        return float(value) if value not in (None, "", "None") else default
    except (TypeError, ValueError):
        return default


def _buyer_name(row):
    return str(row.get("buyer") or row.get("购方名称") or row.get("购买方名称") or "").strip()


def _seller_name(row):
    return str(row.get("seller") or row.get("销方名称") or row.get("销售方名称") or "").strip()


def is_individual_entity(name):
    """判断供应商/客户是否为个人或个体工商户（非公司制主体）。

    注意：本判定只在"名称层面"区分主体性质，**不表示交易异常**。
    是否异常须结合经营模式（见 detect_business_model）另行裁决。
    """
    name = str(name or "").strip()
    if not name:
        return False
    # 公司制主体直接排除
    if any(key in name for key in ("公司", "有限", "股份", "集团")):
        return False
    # 明确标注为个人的（如"王颖（个人）"）
    if "（个人）" in name or "(个人)" in name or "个人" in name:
        return True
    # 个体工商户常见字号
    if any(key in name for key in ("个体", "经营部", "商行", "经销部", "工作室", "摊", "户")):
        return True
    # 店铺/门市等终端主体
    if any(key in name for key in ("店", "部", "中心")):
        return True
    return len(name) <= 4  # 短名称大概率是人名


# 第三方支付平台主体关键词（出现在银行流水/序时账对手方名称中，说明资金经第三方支付
# 通道归集，并非真实交易对手方——零售/电商企业此类回款占比高属正常经营模式）
_THIRD_PARTY_PAYMENT_KEYWORDS = (
    "支付宝", "财付通", "微信支付", "网银在线", "通联支付", "汇付", "易宝",
    "连连支付", "快钱", "京东支付", "拼多多支付", "抖音支付", "首信易", "随行付",
    "聚合支付", "云闪付", "收钱吧", "拉卡拉",
)


def is_third_party_payment_channel(name):
    """判断对手方是否为第三方支付通道（支付宝/财付通/微信支付等），而非真实交易对手方。

    第三方支付归集账户（如"支付宝支付科技有限公司""财付通支付科技有限公司"）只是资金
    通道，其名下的大额往来对应的是海量终端消费者，不应被当作单一客户/供应商/关联方的
    异常交易来研判。本判定是系统级共享能力，供全部规则统一识别支付通道、避免误判。
    """
    name = str(name or "").strip()
    if not name:
        return False
    return any(key in name for key in _THIRD_PARTY_PAYMENT_KEYWORDS)


def _entity_profile(data):
    """从 data 中提取企业主体信息（名称/行业/经营范围），兼容多种字段名。"""
    entity = data.get("target_entity") or {}
    if not isinstance(entity, dict):
        entity = {}
    profile = data.get("company_profile") or {}
    if not isinstance(profile, dict):
        profile = {}
    name = str(
        entity.get("name") or profile.get("name")
        or data.get("company_name") or data.get("enterprise_name") or ""
    ).strip()
    scope = str(
        entity.get("business_scope") or entity.get("biz_scope")
        or profile.get("business_scope") or profile.get("biz_scope")
        or data.get("business_scope") or ""
    ).strip()
    industry = str(
        entity.get("industry") or profile.get("industry")
        or entity.get("industry_code") or profile.get("industry_code")
        or data.get("industry") or ""
    ).strip()
    return name, scope, industry


def _sales_structure(sal_invs):
    """从销项发票计算客户结构指标（零售判定的核心证据）。"""
    by_customer = defaultdict(lambda: {"amount": 0.0, "count": 0})
    invoice_count = 0
    total_amount = 0.0
    platform_hits = set()
    consumer_goods_amount = 0.0
    for row in sal_invs:
        name = _buyer_name(row)
        amount = _number(row.get("amount"))
        total_amount += amount
        invoice_count += 1
        goods = str(row.get("goods") or row.get("货物或应税劳务名称") or row.get("开票项目") or "")
        if any(k in goods for k in _CONSUMER_GOODS_KEYWORDS):
            consumer_goods_amount += amount
        if not name:
            continue
        by_customer[name]["amount"] += amount
        by_customer[name]["count"] += 1
        for platform in _ECOMMERCE_PLATFORM_KEYWORDS:
            if platform in name:
                platform_hits.add(platform)
                break
    if not by_customer:
        return {
            "customer_count": 0, "invoice_count": invoice_count, "total_amount": round(total_amount, 2),
            "avg_invoice_amount": 0.0, "top1_share": 0.0, "platforms": [],
            "consumer_goods_amount": round(consumer_goods_amount, 2),
            "by_customer": {},
        }
    top1 = max(agg["amount"] for agg in by_customer.values())
    return {
        "customer_count": len(by_customer),
        "invoice_count": invoice_count,
        "total_amount": round(total_amount, 2),
        "avg_invoice_amount": round(total_amount / invoice_count, 2) if invoice_count else 0.0,
        "top1_share": round(top1 / total_amount, 4) if total_amount > 0 else 0.0,
        "platforms": sorted(platform_hits),
        "consumer_goods_amount": round(consumer_goods_amount, 2),
        "by_customer": {k: {"amount": round(v["amount"], 2), "count": v["count"]}
                        for k, v in by_customer.items()},
    }


def detect_business_model(data):
    """识别企业经营模式，返回证据化的模式画像。

    返回结构::

        {
          "model": "retail_b2c" | "mixed" | "b2b_or_unknown",
          "is_b2c_retail": bool,          # 证据充分支持零售/B2C（可直接判非风险）
          "needs_clarification": bool,    # 证据不足，须企业说明经营模式
          "score": float,
          "confidence": float,
          "evidence": [str, ...],         # 人类可读的证据链
          "metrics": {...},               # 可复算的中间指标
          "platforms": [str, ...],
        }
    """
    data = data or {}
    sal_invs = data.get("sal_invs") or []
    name, scope, industry = _entity_profile(data)
    struct = _sales_structure(sal_invs)

    evidence = []
    score = 0.0

    # ── 证据1：电商平台客户（强信号）──
    if struct["platforms"]:
        score += 2.0
        evidence.append(
            "销项客户中存在电商平台主体（%s），说明企业通过电商平台面向终端消费者销售"
            % "、".join(struct["platforms"][:5])
        )

    # ── 证据2：客户高度分散 ──
    if struct["customer_count"] >= DISPERSED_CUSTOMER_COUNT:
        add = 2.0 if struct["customer_count"] >= 80 else 1.0
        score += add
        evidence.append(
            "销项客户%s家、高度分散，符合面向不特定消费者的零售特征"
            % struct["customer_count"]
        )

    # ── 证据3：销项票均金额小 ──
    if 0 < struct["avg_invoice_amount"] <= RETAIL_AVG_INVOICE_AMOUNT:
        add = 3.0 if struct["avg_invoice_amount"] <= 1000 else 2.0
        score += add
        evidence.append(
            "销项票均金额%.2f元，属消费级小额（零售阈值%.0f元）"
            % (struct["avg_invoice_amount"], RETAIL_AVG_INVOICE_AMOUNT)
        )

    # ── 证据4：客户户均金额小 ──
    if struct["customer_count"] > 0:
        avg_customer = struct["total_amount"] / struct["customer_count"]
        if 0 < avg_customer <= RETAIL_AVG_CUSTOMER_AMOUNT:
            add = 3.0 if avg_customer <= 1000 else 2.0
            score += add
            evidence.append(
                "客户户均销售额%.2f元，属消费级（零售阈值%.0f元）"
                % (avg_customer, RETAIL_AVG_CUSTOMER_AMOUNT)
            )

    # ── 证据5：不依赖单一客户 ──
    if 0 < struct["top1_share"] <= TOP1_CUSTOMER_SHARE_LIMIT:
        score += 1.0
        evidence.append(
            "最大单一客户销售额占比%.1f%%，不依赖单一客户，符合零售分散成交特征"
            % (struct["top1_share"] * 100)
        )

    # ── 证据6：工商登记与经营范围的零售信号 ──
    reg_text = name + " " + scope
    hit_retail = [k for k in _RETAIL_SIGNAL_KEYWORDS if k in reg_text]
    if hit_retail:
        score += 2.0
        evidence.append(
            "企业名称/经营范围含零售或电商经营表述（%s）" % "、".join(hit_retail[:5])
        )
    if industry and any(label == industry or label in industry for label in _RETAIL_INDUSTRY_LABELS):
        score += 2.0
        evidence.append("登记行业为批发零售/商贸类（%s）" % industry)

    # ── 证据7：销项品名以终端消费品为主 ──
    if struct["total_amount"] > 0 and struct["consumer_goods_amount"] / struct["total_amount"] >= 0.5:
        score += 1.0
        evidence.append(
            "销项品名中终端消费品金额占比%.1f%%，销售对象为最终消费者"
            % (struct["consumer_goods_amount"] / struct["total_amount"] * 100)
        )

    # ── 反向证据：批发/生产/ B2B 特征 ──
    if struct["top1_share"] >= 0.5 and struct["avg_invoice_amount"] >= 50000:
        score -= 3.0
        evidence.append(
            "最大单一客户占比%.1f%%且票均金额%.2f元，呈大宗批发/项目制特征，非零售"
            % (struct["top1_share"] * 100, struct["avg_invoice_amount"])
        )
    hit_wholesale = [k for k in _WHOLESALE_SIGNAL_KEYWORDS if k in reg_text]
    if hit_wholesale and not hit_retail:
        score -= 1.0
        evidence.append(
            "名称/经营范围以批发、生产或工程类表述为主（%s），非终端零售"
            % "、".join(hit_wholesale[:4])
        )

    score = round(score, 2)
    if score >= RETAIL_SCORE_THRESHOLD:
        model = "retail_b2c"
    elif score >= WEAK_SCORE_THRESHOLD:
        model = "mixed"
    else:
        model = "b2b_or_unknown"

    metrics = {
        "sale_invoice_count": struct["invoice_count"],
        "sale_total_amount": struct["total_amount"],
        "customer_count": struct["customer_count"],
        "avg_invoice_amount": struct["avg_invoice_amount"],
        "avg_customer_amount": (
            round(struct["total_amount"] / struct["customer_count"], 2)
            if struct["customer_count"] else 0.0
        ),
        "top1_customer_share": struct["top1_share"],
        "consumer_goods_amount": struct["consumer_goods_amount"],
        "enterprise_name": name,
        "industry": industry,
    }

    return {
        "model": model,
        "is_b2c_retail": model == "retail_b2c",
        "needs_clarification": model == "mixed",
        "score": score,
        "confidence": round(min(score / 10.0, 1.0), 2),
        "evidence": evidence,
        "metrics": metrics,
        "platforms": struct["platforms"],
    }


def describe_model_text(model_result):
    """把经营模式画像转成报告可读的一段话（中性口径，不作风险定性）。"""
    if not isinstance(model_result, dict):
        return ""
    m = model_result.get("metrics", {}) or {}
    if model_result.get("is_b2c_retail"):
        platforms = model_result.get("platforms") or []
        platform_text = ("，并经由%s等电商平台成交" % "、".join(platforms[:3])) if platforms else ""
        return (
            "经核验销项发票结构，企业销项发票{mcnt}张、金额合计{amt:,.2f}元，客户{cust}家，"
            "票均{avg_inv:,.2f}元、户均{avg_cus:,.2f}元{plat}，最大单一客户占比{top1:.1f}%，"
            "呈典型的面向终端消费者的零售（B2C）经营特征。"
        ).format(
            mcnt=m.get("sale_invoice_count", 0), amt=m.get("sale_total_amount", 0.0),
            cust=m.get("customer_count", 0), avg_inv=m.get("avg_invoice_amount", 0.0),
            avg_cus=m.get("avg_customer_amount", 0.0), plat=platform_text,
            top1=m.get("top1_customer_share", 0.0) * 100,
        )
    return ""
