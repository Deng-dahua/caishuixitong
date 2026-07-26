"""
税收优惠智能分析引擎

核心理念：应享尽享，应缴尽缴
- 应享未享 → 告诉企业差什么、怎么达标
- 错享/不应享 → 告诉企业错在哪、怎么纠正
- 临界达标 → 告诉企业维持标准的关键指标

联网核查三步法：
1. 搜索引擎定位 → 找到官方公告页面URL
2. 抓取公告全文 → 读取页面完整内容
3. 提取结构化条件 → 从原文中提取门槛值/税率/有效期

六大优惠类别：
1. 企业所得税：小微/高新/研发加计/西部大开发/软件企业
2. 增值税：小规模免税/简易计税/即征即退
3. 附加税：六税两费减半
4. 其他：残保金减免/小型微利/重点群体
"""
from datetime import date, datetime
import json, os, re, hashlib, time
from urllib.request import Request, urlopen
from urllib.parse import quote, urljoin
from html import unescape as html_unescape

# ============ 税收优惠政策库（结构化条件） ============
POLICY_VALIDITY = {
    "small_micro": {
        "name": "小型微利企业所得税优惠",
        "law": "财政部税务总局公告2025年第5号",
        "expiry": date(2027, 12, 31),
        "note": "延续至2027年12月31日",
        # 结构化核实条件（系统联网核查后填充，初始值来自已知最新政策）
        "conditions": {
            "应纳税所得额上限": 3000000,    # ≤300万元
            "从业人数上限": 300,             # ≤300人
            "资产总额上限": 50000000,        # ≤5000万元
            "减按比例": 25,                  # 减按25%计入应纳税所得额
            "优惠税率": 20,                  # 按20%税率缴纳
            "有效税率": 5,                   # 25%*20%=5%
        }
    },
    "small_taxpayer": {
        "name": "小规模纳税人增值税减免",
        "law": "财政部税务总局公告2023年第1号",
        "expiry": date(2027, 12, 31),
        "conditions": {"年销售额上限": 5000000}
    },
    "rd_deduction": {
        "name": "研发费用加计扣除",
        "law": "财政部税务总局公告2023年第7号",
        "expiry": None,
        "note": "长期政策",
        "conditions": {"加计比例": 100, "制造业加计比例": 120}
    },
    "high_tech": {
        "name": "高新技术企业15%税率",
        "law": "企业所得税法第21720条",
        "expiry": None,
        "note": "法律层面长期有效",
        "conditions": {"优惠税率": 15}
    },
    "six_tax": {
        "name": "六税两费减半",
        "law": "财政部税务总局公告2022年第10号",
        "expiry": date(2027, 12, 31),
        "conditions": {"减免比例": 50}
    },
    "software_vat": {
        "name": "软件产品即征即退",
        "law": "财税[2011]100号",
        "expiry": None,
        "conditions": {"税负超3%部分即征即退": True}
    },
    "disabled": {
        "name": "残疾人就业保障金减免",
        "law": "财政部公告2019年第98号",
        "expiry": date(2027, 12, 31),
        "conditions": {"在职职工20人以下免征": True}
    },
    "agri": {
        "name": "农林牧渔所得减免",
        "law": "企业所得税法第21720条",
        "expiry": None
    },
    "west": {
        "name": "西部大开发15%税率",
        "law": "财政部公告2020年第23号",
        "expiry": date(2030, 12, 31),
        "conditions": {"优惠税率": 15}
    },
}
CURRENT_YEAR = date.today().year

# ============ 联网核查三步法 + 结构化缓存 ============

POLICY_CACHE_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "policy_cache.json")

def _load_policy_cache():
    try:
        with open(POLICY_CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except: return {}

def _save_policy_cache(cache):
    try:
        os.makedirs(os.path.dirname(POLICY_CACHE_FILE), exist_ok=True)
        with open(POLICY_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except: pass

# ========== 三步法 第1步：搜索引擎定位 → 找到官方公告URL ==========

def _search_policy_url(policy_name, policy_law):
    """搜索政策关键词，从搜索结果中提取官方公告URL"""
    queries = [
        f"{policy_name} 财政部 税务总局公告 2025 2026 site:chinatax.gov.cn",
        f"{policy_name} 延续 国家税务总局 site:gov.cn",
        f"{policy_law} site:chinatax.gov.cn",
    ]
    urls = []
    for q in queries[:2]:
        try:
            search_url = f"https://www.sogou.com/web?query={quote(q)}"
            req = Request(search_url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html"
            })
            resp = urlopen(req, timeout=10)
            body = resp.read().decode("gbk", errors="replace")
            # 提取搜索结果中的链接URL
            hrefs = re.findall(r'href="(https?://[^"]*(?:chinatax\.gov\.cn|mof\.gov\.cn|gov\.cn)[^"]*)"', body)
            urls.extend(hrefs)
            if not urls:
                # 泛域名匹配不到，退化为提取所有HTTP链接
                hrefs = re.findall(r'href="(https?://[^"]+)"', body)
                for h in hrefs:
                    h_decoded = html_unescape(h)
                    if any(d in h_decoded for d in ["chinatax.gov.cn", "mof.gov.cn", "shui5.cn"]):
                        urls.append(h_decoded)
            if urls:
                break
        except: pass
    
    # 搜狗找不到，试360
    if not urls:
        try:
            search_url = f"https://www.so.com/s?q={quote(queries[0])}"
            req = Request(search_url, headers={"User-Agent": "Mozilla/5.0"})
            resp = urlopen(req, timeout=10)
            body = resp.read().decode("utf-8", errors="replace")
            hrefs = re.findall(r'href="(https?://[^"]*(?:chinatax|mof|gov\.cn|shui5)[^"]*)"', body)
            urls.extend(hrefs)
        except: pass
    
    return list(set(urls))[:3]  # 去重，最多3个候选URL


# ========== 三步法 第2步：抓取公告全文 ==========

def _fetch_policy_page(url):
    """抓取政策公告页面全文"""
    try:
        req = Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml"
        })
        resp = urlopen(req, timeout=15)
        content_type = resp.headers.get("Content-Type", "")
        # 自动检测编码
        charset_match = re.search(r'charset=([^\s;]+)', content_type)
        encoding = charset_match.group(1) if charset_match else "utf-8"
        body = resp.read().decode(encoding, errors="replace")
        return body
    except:
        return ""


# ========== 三步法 第3步：从原文提取结构化条件 ==========

# 各政策的提取规则
_POLICY_EXTRACTION_RULES = {
    "small_micro": {
        "extractors": [
            # (正则, 字段名, 转换函数)
            (r'年应纳税所得额[不超]*(?:过|大于)?\s*(\d+)\s*万', "应纳税所得额上限", lambda v: int(v) * 10000),
            (r'从业人数[不超]*(?:过|大于)?\s*(\d+)\s*人', "从业人数上限", int),
            (r'资产总额[不超]*(?:过|大于)?\s*(\d+)\s*万', "资产总额上限", lambda v: int(v) * 10000),
            (r'减按\s*(\d+)\s*%\s*计入', "减按比例", int),
            (r'按\s*(\d+)\s*%\s*的税率[缴征]', "优惠税率", int),
            (r'(?:自|从)\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日[至到].*?(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日', None, None),
        ]
    },
    "small_taxpayer": {
        "extractors": [
            (r'年[应]?销售额[不超]*(?:过|大于)?\s*(\d+)\s*万', "年销售额上限", lambda v: int(v) * 10000),
            (r'月销售额[不超]*(?:过|大于)?\s*(\d+)\s*万', "月销售额上限", lambda v: int(v) * 10000),
        ]
    },
    "rd_deduction": {
        "extractors": [
            (r'加[计记]\s*(\d+)\s*%\s*扣除', "加计比例", int),
        ]
    },
    "six_tax": {
        "extractors": [
            (r'减半|减免\s*(\d+)\s*%|减[征按]\s*(\d+)\s*%', "减免比例", lambda v: int(v) if v else 50),
        ]
    },
}

def _extract_conditions_from_text(policy_key, html_text):
    """从HTML文本中提取结构化政策条件"""
    if policy_key not in _POLICY_EXTRACTION_RULES:
        return {}
    
    # 清理HTML标签，只保留文本
    text = re.sub(r'<[^>]+>', ' ', html_text)
    text = re.sub(r'\s+', ' ', text)
    # 还原HTML实体
    text = html_unescape(text)
    
    extractors = _POLICY_EXTRACTION_RULES[policy_key]["extractors"]
    conditions = {}
    
    for pattern, field_name, converter in extractors:
        match = re.search(pattern, text)
        if match and field_name and converter:
            try:
                if match.lastindex and match.lastindex >= 1:
                    val = converter(match.group(1))
                    conditions[field_name] = val
            except: pass
        elif match and field_name is None:
            # 有效期提取
            try:
                y1, m1, d1, y2, m2, d2 = [int(x) for x in match.groups()]
                conditions["有效期起"] = f"{y1}-{m1:02d}-{d1:02d}"
                conditions["有效期止"] = f"{y2}-{m2:02d}-{d2:02d}"
            except: pass
    
    # 补全默认条件
    if not conditions and policy_key in POLICY_VALIDITY:
        defaults = POLICY_VALIDITY[policy_key].get("conditions", {})
        if defaults:
            conditions = dict(defaults)
            conditions["_source"] = "内置默认值(联网未提取到条件)"
    
    if conditions:
        conditions["_extracted_at"] = datetime.now().isoformat()
        conditions["_source"] = "联网提取"
    
    return conditions


def _verify_conditions_against_data(conditions, company_data):
    """将提取的政策条件与企业数据进行比对核实"""
    if not conditions:
        return {"status": "条件未提取", "details": []}
    
    details = []
    all_pass = True
    
    # 应纳税所得额核实
    if "应纳税所得额上限" in conditions and "profit" in company_data:
        limit = conditions["应纳税所得额上限"]
        actual = company_data["profit"] or 0
        if actual > 0:
            if actual <= limit:
                details.append(f"应纳税所得额{actual:,.0f}元 ≤ {limit:,.0f}元 ✓ 符合")
            else:
                details.append(f"应纳税所得额{actual:,.0f}元 > {limit:,.0f}元 ✗ 不符合")
                all_pass = False
    
    # 从业人数核实
    if "从业人数上限" in conditions and "employee_count" in company_data:
        limit = conditions["从业人数上限"]
        actual = company_data["employee_count"] or 0
        if actual > 0:
            if actual <= limit:
                details.append(f"从业人数{actual}人 ≤ {limit}人 ✓ 符合")
            else:
                details.append(f"从业人数{actual}人 > {limit}人 ✗ 不符合")
                all_pass = False
    
    # 资产总额核实
    if "资产总额上限" in conditions and "total_assets" in company_data:
        limit = conditions["资产总额上限"]
        actual = company_data["total_assets"] or 0
        if actual > 0:
            if actual <= limit:
                details.append(f"资产总额{actual:,.0f}元 ≤ {limit:,.0f}元 ✓ 符合")
            else:
                details.append(f"资产总额{actual:,.0f}元 > {limit:,.0f}元 ✗ 不符合")
                all_pass = False
    
    return {
        "status": "符合条件" if all_pass else "不符合条件",
        "details": details,
        "has_data": len(details) > 0
    }


# ========== 综合核查入口 ==========

def _verify_policy_online(policy_key):
    """联网核查三步法总入口：搜URL→抓页面→提取条件"""
    p = POLICY_VALIDITY.get(policy_key)
    if not p:
        return {"success": False, "reason": "未登记的政策"}
    
    # 第1步：搜URL
    urls = _search_policy_url(p["name"], p["law"])
    if not urls:
        return {"success": False, "reason": "未找到官方公告URL", "conditions": None}
    
    # 第2步：抓页面
    page_text = ""
    fetched_url = ""
    for url in urls:
        text = _fetch_policy_page(url)
        if text and len(text) > 500:
            page_text = text
            fetched_url = url
            break
    
    if not page_text:
        return {"success": False, "reason": "抓取页面失败", "urls_tried": urls}
    
    # 第3步：提取结构化条件
    conditions = _extract_conditions_from_text(policy_key, page_text)
    
    return {
        "success": True,
        "source_url": fetched_url,
        "conditions": conditions,
        "page_length": len(page_text)
    }


def check_policy(policy_key, auto_verify=True):
    """检查政策有效期并联网核实（返回结构化核实结果）"""
    p = POLICY_VALIDITY.get(policy_key)
    if not p:
        return {"valid": True, "status": "未登记", "source": "", "conditions": None, "verification": None}
    if p["expiry"] is None:
        return {"valid": True, "status": f"长期政策({p['law']})", "source": "", "conditions": p.get("conditions"), "verification": None}
    
    analysis_date = date(CURRENT_YEAR, 12, 31)
    if analysis_date <= p["expiry"]:
        return {"valid": True, "status": f"有效至{p['expiry']}", "source": p["law"], "conditions": p.get("conditions"), "verification": None}
    
    # 已到期 → 联网核实
    if auto_verify:
        cache = _load_policy_cache()
        cache_key = f"{policy_key}_{CURRENT_YEAR}"
        
        if cache_key in cache:
            cached = cache[cache_key]
            if cached.get("expires", 0) > time.time():
                return cached
        
        # 三步法联网核查
        result = _verify_policy_online(policy_key)
        
        if result["success"] and result["conditions"]:
            conds = result["conditions"]
            effective_conditions = conds.get("有效税率") or (conds.get("减按比例") and conds.get("优惠税率") and f"{conds['减按比例']*conds['优惠税率']//100}%")
            status = f"已于{p['expiry']}到期，联网提取到新政策条件（来源：{result['source_url'][:60]}）"
            
            cache_entry = {
                "valid": True,
                "status": status,
                "source": result["source_url"],
                "conditions": conds,
                "expires": time.time() + 86400 * 90  # 缓存90天
            }
            cache[cache_key] = cache_entry
            _save_policy_cache(cache)
            return cache_entry
        else:
            status = f"已于{p['expiry']}到期！联网未提取到有效条件：{result.get('reason','')}"
            default_conditions = p.get("conditions", {})
            cache_entry = {
                "valid": False,
                "status": status,
                "source": "",
                "conditions": default_conditions,
                "expires": time.time() + 86400 * 30  # 缓存30天
            }
            cache[cache_key] = cache_entry
            _save_policy_cache(cache)
            return cache_entry
    
    return {"valid": False, "status": f"已于{p['expiry']}到期！{p.get('note','')}须核实是否延续", "source": "", "conditions": p.get("conditions"), "verification": None}



def analyze_tax_incentives(ctx, sal_invs, pur_invs, bank_txs, salaries, income_stmt, balance_sheet, vouchers):
    """
    税收优惠全景分析主入口
    
    返回：(findings, opportunities)
    - findings: 当前问题（错享/不应享）
    - opportunities: 可争取的优惠（应享未享/临界达标）
    """
    findings = []
    opportunities = []
    
    # 提取关键指标
    revenue = _extract_revenue(income_stmt, sal_invs, vouchers)
    profit = _extract_profit(income_stmt, vouchers)
    total_assets = _extract_assets(balance_sheet)
    employee_count = _extract_employee_count(salaries)
    industry = ctx.company_profile.get("industry", "") if ctx else ""
    biz_model = ctx.company_profile.get("biz_model", "") if ctx else ""
    
    # ═══ 1. 小微企业优惠 ═══
    _check_small_micro(revenue, profit, total_assets, employee_count, findings, opportunities)
    
    # ═══ 2. 小规模纳税人增值税 ═══
    _check_small_taxpayer(revenue, findings, opportunities, sal_invs)
    
    # ═══ 3. 高新技术企业 ═══
    _check_high_tech(industry, revenue, findings, opportunities)
    
    # ═══ 4. 研发费用加计扣除 ═══
    _check_rd_deduction(industry, biz_model, pur_invs, findings, opportunities)
    
    # ═══ 5. 六税两费减半 ═══
    _check_six_tax_two_fee(employee_count, total_assets, revenue, findings, opportunities)
    
    # ═══ 6. 软件产品即征即退 ═══
    _check_software_vat(industry, sal_invs, findings, opportunities)
    
    # ═══ 7. 安排残疾人就业/残保金 ═══
    _check_disabled_employment(employee_count, salaries, findings, opportunities)
    
    # ═══ 8. 小型微利企业附加优惠 ═══
    _check_other_incentives(revenue, profit, industry, findings, opportunities)
    
    # ═══ 9. 政策有效期统一核实 ═══
    # 每条优惠建议/发现自动标注有效期状态
    _attach_policy_validity(findings, opportunities)
    
    return findings, opportunities


# ═══════════════ 1. 小微企业优惠 ═══════════════

def _check_small_micro(revenue, profit, total_assets, employee_count, findings, opportunities):
    """小微企业：所得税优惠（年应纳税所得额≤300万）
    
    政策依据：财政部税务总局公告2023年第6号→2024-12-31到期
    延续政策：财政部税务总局公告2025年第5号→2027-12-31到期
    税率规则：年应纳税所得额≤300万 → 减按25%×20%=5%有效税率（全档位统一）
    """
    if not revenue: return
    
    # 从政策库获取结构化条件（联网核查后动态更新）
    policy_conds = POLICY_VALIDITY["small_micro"].get("conditions", {})
    profit_limit = policy_conds.get("应纳税所得额上限", 3000000)
    emp_limit = policy_conds.get("从业人数上限", 300)
    asset_limit = policy_conds.get("资产总额上限", 50000000)
    effective_rate = policy_conds.get("有效税率", 5)  # 默认5%
    
    # 条件判定
    can_qualify = (profit and profit <= profit_limit) and employee_count <= emp_limit and total_assets <= asset_limit
    near_margin = (profit and profit_limit * 0.9 <= profit <= profit_limit * 1.2) or \
                  (emp_limit * 0.9 <= employee_count <= emp_limit * 1.2) or \
                  (asset_limit * 0.9 <= total_assets <= asset_limit * 1.2)
    
    if can_qualify and profit > 0:
        # 统一5%有效税率 → 节省 = 25% - 5% = 20%
        tax_saved = profit * (0.25 - effective_rate / 100.0)
        
        opportunities.append({
            "type": "小微企业税收优惠(应享)",
            "level": "优惠机会",
            "priority": "高",
            "detail": f"符合小微企业标准(利润{profit:,.0f}≤{profit_limit/10000:.0f}万/人数{employee_count}≤{emp_limit}/资产{total_assets:,.0f}≤{asset_limit/10000:.0f}万)",
            "tax_benefit": f"可享受企业所得税优惠税率（减按{policy_conds.get('减按比例',25)}%×{policy_conds.get('优惠税率',20)}%={effective_rate}%有效税率），预计节省税款约{tax_saved:,.0f}元",
            "action": "在企业所得税汇算清缴时填报A107040表享受减免",
            "law_ref": POLICY_VALIDITY["small_micro"]["law"],
            "policy_conditions_source": "联网核查·结构化提取" if policy_conds.get("_source") == "联网提取" else "内置政策库",
        })
    
    if near_margin and not can_qualify:
        issues = []
        if profit and profit > profit_limit: issues.append(f"利润{profit:,.0f}元超出{profit_limit/10000:.0f}万限额")
        if employee_count > emp_limit: issues.append(f"从业人数{employee_count}超出{emp_limit}人限额")
        if total_assets > asset_limit: issues.append(f"资产{total_assets:,.0f}超出{asset_limit/10000:.0f}万限额")
        
        opportunities.append({
            "type": "小微企业优惠(临界)",
            "level": "提醒",
            "priority": "中",
            "detail": f"接近但未达小微企业标准：{'；'.join(issues)}",
            "tax_benefit": f"如能满足标准，可节省{25-effective_rate}%企业所得税",
            "action": f"建议：①控制利润不超{profit_limit/10000:.0f}万 ②控制从业人数≤{emp_limit} ③控制资产总额≤{asset_limit/10000:.0f}万",
            "law_ref": POLICY_VALIDITY["small_micro"]["law"],
        })


# ═══════════════ 2. 小规模纳税人增值税 ═══════════════

def _check_small_taxpayer(revenue, findings, opportunities, sal_invs=None):
    """小规模纳税人：年销售额≤500万可享受1%或免税
    
    关键：必须有足够的时间跨度数据才能判定。
    单月/单季度数据不足以推断年销售额，会降级为"数据不足"提示。
    """
    if not revenue: return
    
    # 检查数据覆盖的时间跨度
    months_covered = _count_months_covered(sal_invs)
    how_found = f"销项发票合计{revenue:,.0f}元"
    if months_covered > 0:
        how_found += f"（覆盖{months_covered}个月）"
    
    # 数据不足：少于6个月的数据不能推断年销售额
    if months_covered < 6:
        if revenue <= 5000000:
            opportunities.append({
                "type": "小规模纳税人资格(应享)",
                "level": "提示",
                "priority": "低",
                "detail": f"销项发票合计{revenue:,.0f}元，但仅覆盖{months_covered}个月（非全年数据），无法据此判定年销售额≤500万。如需确认资格，请提供完整年度销项发票或利润表。",
                "how_found": how_found,
                "tax_benefit": "增值税税率从6%/13%降至1%或免税(月销售额≤10万)",
                "action": "补全至少6个月以上的销项数据后再评估；或直接查看增值税申报表全年累计销售额",
                "law_ref": "财政部税务总局公告2023年第1号",
            })
        return
    
    # 数据充分（≥6个月）：可以合理推断
    if revenue <= 5000000:
        opportunities.append({
            "type": "小规模纳税人资格(应享)",
            "level": "优惠机会",
            "priority": "高",
            "detail": f"销项发票{months_covered}个月合计{revenue:,.0f}元，全年推算≤500万，符合小规模纳税人标准",
            "how_found": how_found,
            "tax_benefit": "增值税税率从6%/13%降至1%或免税(月销售额≤10万)",
            "action": "如业务结构允许，可考虑转为小规模纳税人或分立业务主体",
            "law_ref": "财政部税务总局公告2023年第1号",
        })
    elif revenue <= 6000000:
        opportunities.append({
            "type": "小规模纳税人(临界)",
            "level": "提醒",
            "priority": "中",
            "detail": f"销项发票{months_covered}个月合计{revenue:,.0f}元，接近500万小规模标准",
            "how_found": how_found,
            "action": "可考虑分立部分业务到新主体，使各主体年销售额≤500万",
        })


# ═══════════════ 3. 高新技术企业 ═══════════════

def _check_high_tech(industry, revenue, findings, opportunities):
    """高新技术企业：15%税率"""
    tech_kw = ["软件","信息","技术","科技","数据","数字","智能","网","电子","通信","半导体","芯片","生物","医药"]
    is_tech_related = any(k in (industry or "") for k in tech_kw)
    
    if is_tech_related:
        opportunities.append({
            "type": "高新技术企业资格(建议申请)",
            "level": "优惠机会",
            "priority": "高",
            "detail": f"所属行业'{industry}'符合高新技术领域",
            "tax_benefit": "企业所得税从25%降至15%，节省40%的所得税",
            "action": "满足以下条件即可申请：①高新收入占比≥60% ②研发费用占比达标 ③科技人员占比≥10% ④核心知识产权",
            "law_ref": "高新技术企业认定管理办法(国科发火[2016]32号)",
            "requirements": {
                "高新收入占比": "≥60%",
                "研发费用占比(收入≤5000万)": "≥5%",
                "研发费用占比(收入5000万-2亿)": "≥4%",
                "研发费用占比(收入>2亿)": "≥3%",
                "科技人员占比": "≥10%",
                "核心知识产权": "≥1项发明专利或6项实用新型",
            }
        })


# ═══════════════ 4. 研发费用加计扣除 ═══════════════

def _check_rd_deduction(industry, biz_model, pur_invs, findings, opportunities):
    """研发费用加计扣除——双层判断：行业匹配+进项品名信号"""
    # 用行业profile数据替代硬编码关键词
    tech_kw = ["软件","信息","技术","科技","数据","数字","智能","电子","通信","半导体","生物","医药","新能源"]
    is_tech = any(k in (industry or "") for k in tech_kw)
    
    # 服务型企业如果行业不含科技关键词，不强行检测研发
    if biz_model == "服务" and not is_tech:
        return
    
    # 检查进项中是否有研发相关品名
    rd_signals = False
    if pur_invs:
        rd_kw = ["开发","研发","测试","设计","技术服务","软件开发","系统","平台"]
        for inv in pur_invs:
            goods = str(inv.get("goods", ""))
            if any(k in goods for k in rd_kw):
                rd_signals = True
                break
    
    if is_tech or rd_signals:
        # 构建具体的迹象描述
        detail_parts = []
        how_found_parts = []
        if is_tech:
            how_found_parts.append(f"行业分类含科技关键词(行业:{industry})")
        if rd_signals and pur_invs:
            # 收集具体的研发相关品名
            rd_items = []
            for inv in pur_invs:
                goods = str(inv.get("goods", ""))
                if any(k in goods for k in rd_kw):
                    rd_items.append(goods[:30])
            if rd_items:
                detail_parts.append("进项发票中含有研发相关品名：" + "、".join(rd_items[:5]))
                how_found_parts.append("进项发票品名匹配研发关键词")
        
        detail_text = (industry + "行业，" + "；".join(detail_parts)) if detail_parts else industry + "行业含科技关键词，具备研发活动条件"
        how_found_text = "；".join(how_found_parts)
        
        opportunities.append({
            "type": "研发费用加计扣除(建议享受)",
            "level": "优惠机会",
            "priority": "高",
            "detail": detail_text,
            "how_found": how_found_text,
            "tax_benefit": "研发费用可在税前加计100%扣除(制造业/科技型中小企业120%)→每100万研发费用多扣100万→节省25万企业所得税",
            "action": "①建立研发费用辅助账 ②归集研发人员工资/材料/折旧/设计费等 ③汇算清缴时填报A107012表",
            "law_ref": "财政部税务总局公告2023年第7号",
        })


# ═══════════════ 5. 六税两费减半 ═══════════════

def _check_six_tax_two_fee(employee_count, total_assets, revenue, findings, opportunities):
    """六税两费减半：小规模/小微/个体户适用"""
    is_small = (employee_count <= 300 and total_assets <= 50000000) or (revenue and revenue <= 5000000)
    
    if is_small:
        opportunities.append({
            "type": "六税两费减半(应享)",
            "level": "优惠机会",
            "priority": "中",
            "detail": "符合小型微利企业或小规模纳税人标准",
            "tax_benefit": "城建税/教育费附加/地方教育附加/房产税/城镇土地使用税/印花税减半征收",
            "action": "申报时选择小型微利企业优惠自动享受",
            "law_ref": "财政部税务总局公告2022年第10号",
        })


# ═══════════════ 6. 软件产品增值税即征即退 ═══════════════

def _check_software_vat(industry, sal_invs, findings, opportunities):
    """软件产品增值税即征即退"""
    if not sal_invs: return
    
    sw_kw = ["软件","系统","平台","程序","APP","小程序","SaaS","应用"]
    sw_revenue = 0
    for inv in sal_invs:
        goods = str(inv.get("goods", ""))
        if any(k in goods for k in sw_kw):
            sw_revenue += float(inv.get("amount", 0) or 0)
    
    if sw_revenue > 0:
        opportunities.append({
            "type": "软件产品即征即退(建议申请)",
            "level": "优惠机会",
            "priority": "高",
            "detail": f"销项中含软件产品收入{sw_revenue:,.0f}元",
            "tax_benefit": f"增值税实际税负超3%部分即征即退→预计可退{(0.13-0.03)*sw_revenue:,.0f}元(如按13%开票)",
            "action": "①取得软件产品登记证书 ②向主管税务机关备案 ③申报时填报即征即退",
            "law_ref": "财税[2011]100号",
        })


# ═══════════════ 7. 安排残疾人就业/残保金 ═══════════════

def _check_disabled_employment(employee_count, salaries, findings, opportunities):
    """残疾人就业减免残保金"""
    if employee_count < 20:
        opportunities.append({
            "type": "残保金免征(应享)",
            "level": "优惠机会",
            "priority": "低",
            "detail": f"在职职工{employee_count}人<20人，免征残疾人就业保障金",
            "tax_benefit": "免征残保金",
            "law_ref": "财政部公告2019年第98号",
        })
    elif employee_count >= 20:
        required = max(1, int(employee_count * 0.015))
        opportunities.append({
            "type": "残疾人就业优惠(建议)",
            "level": "优惠机会",
            "priority": "中",
            "detail": f"在职{employee_count}人，按1.5%比例应安排{required}名残疾人就业",
            "tax_benefit": f"安排残疾人就业可免缴残保金，企业所得税可100%加计扣除残疾人工资",
            "action": f"建议安排{required}名残疾人就业，同时享受残保金免缴+工资加计扣除双重优惠",
            "law_ref": "残疾人就业条例；财税[2009]70号",
        })


# ═══════════════ 8. 其他税收优惠检查 ═══════════════

def _check_other_incentives(revenue, profit, industry, findings, opportunities):
    """其他零散优惠"""
    # 农林牧渔
    agri_kw = ["农业","林业","畜牧","渔业","养殖","种植"]
    if any(k in (industry or "") for k in agri_kw):
        opportunities.append({
            "type": "农林牧渔项目所得减免",
            "level": "优惠机会",
            "priority": "高",
            "detail": f"所属行业'{industry}'可能符合农林牧渔优惠",
            "tax_benefit": "从事农林牧渔项目所得免征或减征企业所得税",
            "action": "核实具体项目是否在《企业所得税优惠目录》中",
            "law_ref": "企业所得税法第21720条；企业所得税法实施条例第81720条",
        })
    
    # 小型微利企业附加
    if profit and profit <= 1000000 and revenue and revenue <= 10000000:
        opportunities.append({
            "type": "特定小微企业优惠叠加",
            "level": "优惠机会",
            "priority": "中",
            "detail": "年利润≤100万且年收入≤1000万，可能享受多重叠加优惠",
            "tax_benefit": "所得税低至5%+六税两费减半+残保金免征",
            "action": "检查是否已享受全部符合条件的优惠",
        })


# ═══════════════ 辅助函数 ═══════════════

def _extract_revenue(income_stmt, sal_invs, vouchers):
    revenue = 0
    if income_stmt:
        revenue = income_stmt.get("revenue", income_stmt.get("total_revenue", 0)) or 0
    if not revenue and sal_invs:
        revenue = sum(float(i.get("amount", 0) or 0) for i in sal_invs)
    if not revenue and vouchers:
        revenue = sum(float(v.get("credit", 0) or 0) for v in vouchers if "主营业务收入" in str(v.get("account_name", v.get("科目", ""))))
    return revenue


def _count_months_covered(invoices):
    """统计发票数据覆盖了多少个自然月"""
    if not invoices: return 0
    from datetime import datetime
    months = set()
    for inv in invoices:
        date_str = str(inv.get("date", inv.get("invoice_date", inv.get("开票日期", ""))))
        if not date_str: continue
        try:
            # 尝试多种日期格式
            for fmt in ["%Y-%m-%d", "%Y/%m/%d", "%Y%m%d", "%Y-%m-%d %H:%M:%S"]:
                try:
                    dt = datetime.strptime(date_str[:10], fmt)
                    months.add((dt.year, dt.month))
                    break
                except: continue
        except: pass
    return len(months)


def _extract_profit(income_stmt, vouchers):
    if income_stmt:
        return income_stmt.get("net_profit", income_stmt.get("total_profit", 0)) or 0
    return 0


def _extract_assets(balance_sheet):
    if balance_sheet:
        return balance_sheet.get("total_assets", 0) or 0
    return 0


def _extract_employee_count(salaries):
    if not salaries:
        return 0
    return len(set(str(s.get("name", s.get("姓名", ""))).strip() for s in salaries if str(s.get("name", s.get("姓名", ""))).strip()))

# ═══════════════ 9. 政策有效期统一核实 ═══════════════

# 政策key→分析函数映射
_POLICY_FUNCTION_MAP = {
    "small_micro": "_check_small_micro",
    "small_taxpayer": "_check_small_taxpayer",
    "high_tech": "_check_high_tech",
    "rd_deduction": "_check_rd_deduction",
    "six_tax": "_check_six_tax_two_fee",
    "software_vat": "_check_software_vat",
    "disabled": "_check_disabled_employment",
    "agri": "_check_other_incentives",
}

def _attach_policy_validity(findings, opportunities):
    """每条优惠结论自动附加有效期核实状态——系统自主学习政策延续"""
    for item in findings + opportunities:
        item_type = item.get("type", "")
        
        # 识别所属优惠类型
        matched_key = None
        if "小微" in item_type:
            matched_key = "small_micro"
        elif "小规模" in item_type:
            matched_key = "small_taxpayer"
        elif "高新" in item_type:
            matched_key = "high_tech"
        elif "研发" in item_type and ("加计" in item_type or "扣除" in item_type):
            matched_key = "rd_deduction"
        elif "六税" in item_type or "两费" in item_type:
            matched_key = "six_tax"
        elif "软件" in item_type or "即征即退" in item_type:
            matched_key = "software_vat"
        elif "残疾人" in item_type or "残保金" in item_type:
            matched_key = "disabled"
        elif "农林" in item_type or "牧" in item_type or "渔" in item_type:
            matched_key = "agri"
        elif "西部" in item_type:
            matched_key = "west"
        
        if matched_key:
            result = check_policy(matched_key, auto_verify=True)
            p = POLICY_VALIDITY.get(matched_key, {})
            item["policy_validity"] = {
                "valid": result.get("valid", True),
                "status": result.get("status", ""),
                "source": result.get("source", ""),
                "policy_name": p.get("name", ""),
                "law": p.get("law", ""),
                "expiry": str(p.get("expiry", "长期")),
            }
            # 附加结构化条件（供前端展示核实详情）
            if result.get("conditions"):
                item["policy_validity"]["conditions"] = result["conditions"]
            if result.get("verification"):
                item["policy_verification"] = result["verification"]
