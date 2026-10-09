"""行业口径统一解析器 —— 行业判定的**唯一权威**（2026-09-25）

═══════════════════════════════════════════════════════════════════════════════
为什么要建这个模块（根因）
═══════════════════════════════════════════════════════════════════════════════
在此之前，"这家企业是什么行业"散落在 **6 处以上**各自实现，每处一套映射与兜底：
  `pipeline._detect_target_entity` / `phase1_triage._infer_industry_from_goods` /
  `main._extract_material_intel` / `pipeline._build_target_entity_snapshot` /
  `inspector_reasoning._match_benchmark` / `agi_core.classify` / `verified_rule_engine._INDUSTRY_VAT_BURDEN`
`_load_industry_data()` 甚至被**重复定义 3 次**（2 份无缓存、3 份兜底形状各不相同）。

后果（已发生的真实误报，非特例）：
  报告出现「对照**橡胶制品**基准，本企业毛利率0.0%（行业12%~30%），明显偏低」——
  只因经营范围里含"橡胶制品销售"，而被 `_match_benchmark` 当成橡胶制品**制造**企业。
  同类错误对**任何**"经营范围里写了某个商品品类"的企业都会发生，与行业无关。

═══════════════════════════════════════════════════════════════════════════════
设计原则（行业无关，适用于所有行业与企业）
═══════════════════════════════════════════════════════════════════════════════
优先级（高 → 低）：
  ① 销项发票品名推断（金税 `*分类*` 编码，META-001；反映**实际经营产出**）
     —— 本报告是**税务风险检查**，"企业实际卖什么"比"登记为何"更能决定税务风险，
        故销项口径置为 **主口径**（权重最高 6）。
  ② 外部工商核验（**真实**工商核验页面上的行业字段，官方登记口径）
     ⚠ 铁律：若该值实为**从经营范围推断**而来，**不得**标注为"外部工商核验"，
        必须降级为"经营范围推断"（低权威）——否则等于让经营范围绕道拿到最高权，R1 形同虚设。
  ③ 工商登记行业字段（账套档案）
  ④ 企业名称中的行业词（企业设立时对主营的自我标识）
  ⑤ 经营范围（**必须先定业态**：制造 / 购销 / 服务）
  ⑥ 经营模式 → 粗粒度兜底

四条铁律（任何行业都成立）：
  R1 **不得用"商品/物料名"当行业**。经营范围写"XX销售/零售/批发"说明是**商贸**企业，
     不是"XX制造"企业。凡从经营范围推断，先定业态再取口径。
  R2 判定必须携带 **来源** 与 **置信度**；取不到就明确输出"未确定"，
     **绝不静默套用默认档**（否则读者无法判断结论的依据）。
  R3 多来源不一致时 **全部保留** 并记为冲突 —— "登记口径≠实际口径"本身就是有价值的
     核查线索（超范围经营 / 变名开票）。
  R4 阈值类对标（毛利率/税负率/进销比…）必须能**自报口径**：用的哪个行业、
     来源是什么、区间出自基准库还是粗粒度。

所有消费端（行业对标、税负率区间、产品链关键字、规则门控、AGI 经营模式分类）
**必须**调用本模块，不得再各写兜底。
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

# ── 单一数据源 ──────────────────────────────────────────────────────────────
_IND_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)) or ".",
                         "static", "industry_data.json")
_CACHE: Optional[Dict[str, Any]] = None
# 加载失败时的安全形状（保证下游 `data.get("benchmarks")` 等不会炸）
_FALLBACK: Dict[str, Any] = {"benchmarks": {"_default": {}}, "benchmarks_coarse": {}}


def load_industry_data() -> Dict[str, Any]:
    """加载行业数据（唯一实现，带缓存）。所有模块统一调用本函数。"""
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    try:
        with open(_IND_PATH, "r", encoding="utf-8") as f:
            _CACHE = json.load(f) or {}
    except Exception:
        _CACHE = dict(_FALLBACK)
    for _k, _v in _FALLBACK.items():          # 缺键兜底
        _CACHE.setdefault(_k, _v)
    return _CACHE


def benchmark_keys() -> List[str]:
    """66 行业基准库的全部键（不含 `_default`）。"""
    return [k for k in (load_industry_data().get("benchmarks") or {}) if k != "_default"]


def coarse_keys() -> List[str]:
    """粗粒度（门类）基准键。"""
    return [k for k in (load_industry_data().get("benchmarks_coarse") or {})]


def is_in_benchmark_base(industry: str) -> bool:
    """行业是否落在行业基准库中（供"是否已在库中"的自我表述使用，避免谎报"不在库中"）。"""
    ind = str(industry or "").strip()
    if not ind:
        return False
    keys = benchmark_keys()
    return ind in keys or any(ind in k or k in ind for k in keys)


# ═══════════════════════════════════════════════════════════════════════════
# 铁律 R1 的落地：业态判别（行业无关的通用词表）
# ═══════════════════════════════════════════════════════════════════════════
# "制造/生产/加工"类业态 —— 只有出现这些词，经营范围才允许落到制造类基准
SCOPE_MFG_HINTS = ("制造", "生产", "加工", "组装", "冶炼", "铸造", "研发生产", "加工制造")
# "购销"类业态 —— 出现这些词而**无**制造类词时，只能落到商贸口径
SCOPE_TRADE_HINTS = ("销售", "零售", "批发", "贸易", "购销", "经销", "进出口")
# 「购销兜底口径」：这些行业本身就是**无具体指向**的兜底，不参与经营范围的「行业级线索」竞争
# （仅由 `_trade_benchmark` 在找不到任何行业线索时启用）。来源：`service_industries` 子集。
_TRADE_FALLBACK_INDUSTRIES = ("商贸", "商贸批发", "商贸零售", "外贸", "电子商务")
# 商贸口径的细分键（按批发/零售进一步收窄）
_TRADE_BENCH_ORDER = ("商贸批发", "商贸零售", "商贸")


def _longest_hit(text: str, keys: List[str]) -> Optional[str]:
    """取 text 中最长的命中键（长短优先，避免通用短词压过专业长词）。"""
    hits = [k for k in keys if k and k in text]
    return max(hits, key=len) if hits else None


def normalize_industry_name(name: str, _depth: int = 0) -> str:
    """把"发票分类名 / 外部来源的行业名"**归一到行业基准库的键**。

    为什么需要（真事故）：销项发票金税分类给的是「广告服务」，而基准库的键是
    「广告传媒」；字面不同 → `match_benchmark` 匹配不到 → 一路回退到经营范围 → 商贸，
    于是"以销项发票为准"**根本落不了地**（口径设了却无效）。

    通用做法（新增同类只需在 `industry_map` 加一行，不改逻辑）：
      1) 名称本身已是基准库键 → 直接用；
      2) 基准库键出现在名称中（如 "xx广告传媒xx" ⊇ "广告传媒"）→ 取最长者；
      3) 名称出现在基准库键中（如 "文化" ⊂ "文化传媒"）→ 取最长者；
      4) 用 `industry_map` 关键词映射（"广告" → "广告传媒"）→ 递归归一。
    都命中不了则原样返回（交给调用方按未匹配处理，**不静默套默认档**）。
    """
    n = str(name or "").strip()
    if not n or _depth >= 3:
        return n
    keys = benchmark_keys()
    if n in keys:
        return n
    hit = _longest_hit(n, keys)
    if hit:
        return hit
    # 名称是某个基准库键的一部分（最长优先，结果确定）
    contains = [k for k in keys if n in k]
    if contains:
        return max(contains, key=len)
    # industry_map 关键词映射（取最长命中词，结果确定）
    im = load_industry_data().get("industry_map") or {}
    best_kw, best_ind = "", ""
    for kw, ind in im.items():
        if kw and kw in n and len(str(kw)) > len(best_kw):
            best_kw, best_ind = str(kw), str(ind)
    if best_ind:
        mapped = normalize_industry_name(best_ind, _depth + 1)
        return mapped or best_ind
    return n


def _trade_benchmark(scope_text: str) -> Optional[str]:
    """纯购销业态 → 只允许落到商贸口径（R1）。"""
    bm = load_industry_data().get("benchmarks") or {}
    for k in _TRADE_BENCH_ORDER:
        if k not in bm:
            continue
        if k == "商贸":
            return k
        if k[2:] in scope_text:      # "商贸批发" → "批发"
            return k
    return None


# ═══════════════════════════════════════════════════════════════════════════
# ② 行业基准匹配（唯一实现）
# ═══════════════════════════════════════════════════════════════════════════
def match_benchmark(industry: str, biz_model: str = "", entity_name: str = "",
                    business_scope: str = "", industry_source: str = "") -> Tuple[Optional[str], Optional[dict]]:
    """按企业画像匹配行业基准，返回 (基准名, 基准dict)；匹配不到返回 (None, None)。

    与旧实现的区别：
      · 经营范围**先定业态**（R1），纯购销绝不落到制造/产品类基准；
      · 名称/经营范围都取**最长匹配**，不再取"字典插入顺序最先者"（结果可解释）；
      · 若已知行业口径来自"实际经营"（销项品名推断），直接以它为准。
    """
    data = load_industry_data()
    benchmarks = data.get("benchmarks") or {}
    coarse = data.get("benchmarks_coarse") or {}

    # ★★ 2026-10-08 修复（真缺陷）：入口先归一 —— 此前 match_benchmark 直接用原始行业名匹配，
    #    绕过 normalize_industry_name，导致「数字传媒」这类**别名业态**匹配不到「文化传媒」，
    #    一路回退到 `_default` 通用基准（本样本 深圳海更数字传媒 即落此项，行业基准形同虚设）。
    #    根因是「行业名归一」这个概念有两条链路，只有一条走了归一化。
    #    修法：薄转发到唯一权威 normalize_industry_name，不在本函数内重复实现别名逻辑。
    ind = normalize_industry_name(str(industry or "").strip())
    # 1. 精确匹配细分行业
    if ind and ind in benchmarks:
        return ind, benchmarks[ind]
    # 1b. 精确匹配**粗粒度门类**（"制造业""交通运输"等是门类键而非细分键）——
    #     此前这类名一路落到 `_default` 通用基准，等于行业基准失配（实测 "制造业" → _default）。
    if ind and ind in coarse:
        return ind, coarse[ind]
    # 2. 细分行业名互含匹配（"文化传媒" vs "广告传媒"）
    if ind:
        hit = _longest_hit(ind, benchmark_keys()) or None
        if hit:
            return hit, benchmarks[hit]
        for k in benchmark_keys():
            if ind in k:
                return k, benchmarks[k]

    # 3. 企业名称中的行业词（最具体、最可靠）
    name_text = str(entity_name or "")
    if name_text:
        hit = _longest_hit(name_text, benchmark_keys())
        if hit:
            return hit, benchmarks[hit]

    # 4. 经营范围 —— 必须先定业态（R1）
    scope_text = str(business_scope or "")
    if scope_text:
        # ★ 2026-10-01：同 resolve_industry——先取「行业级线索」，找不到才走购销兜底。
        _scope_hint = scope_industry_hint(scope_text, str(entity_name or ""))
        if _scope_hint and benchmarks.get(_scope_hint):
            return _scope_hint, benchmarks[_scope_hint]
        is_mfg = any(h in scope_text for h in SCOPE_MFG_HINTS)
        is_trade = any(h in scope_text for h in SCOPE_TRADE_HINTS)
        if is_trade and not is_mfg:
            tk = _trade_benchmark(scope_text)
            if tk:
                return tk, benchmarks[tk]
        else:
            hit = _longest_hit(scope_text, benchmark_keys())
            if hit:
                return hit, benchmarks[hit]

    # 5. 服务业细分 → 粗粒度
    scope_name = scope_text + name_text
    if str(biz_model or "").strip() == "服务业" and scope_name:
        for kw, coarse_key in SERVICE_FINE_TO_COARSE.items():
            if kw in scope_name and coarse.get(coarse_key):
                return coarse_key, coarse.get(coarse_key)
    # 6. 经营模式 → 粗粒度
    coarse_key = BIZ_TO_COARSE.get(str(biz_model or "").strip())
    if coarse_key and coarse.get(coarse_key):
        return coarse_key, coarse.get(coarse_key)
    # 7. 兜底
    if benchmarks.get("_default"):
        return "_default", benchmarks["_default"]
    return None, None


# 业务模式 → 粗粒度门类（R4：粗粒度也要能说清口径）
BIZ_TO_COARSE = {
    "制造业": "制造业",
    "贸易业": "批发零售",
    "服务业": "居民服务",
}
# 服务业细分 → 粗粒度（更贴切的兜底）
SERVICE_FINE_TO_COARSE = {
    "餐饮": "住宿餐饮", "酒店": "住宿餐饮", "住宿": "住宿餐饮",
    "广告": "租赁商务", "传媒": "租赁商务", "咨询": "租赁商务", "设计": "租赁商务",
    "信息": "软件信息服务", "软件": "软件信息服务", "互联网": "软件信息服务", "网络": "软件信息服务",
    "文化": "文化体育", "影视": "文化体育", "娱乐": "文化体育",
}


# ═══════════════════════════════════════════════════════════════════════════
# ① 行业口径解析（唯一权威）
# ═══════════════════════════════════════════════════════════════════════════
# 来源标识（会原样出现在报告里，必须是读者能懂的中文）
SRC_ONLINE = "外部工商核验"
SRC_REGISTERED = "工商登记"
SRC_INVOICE = "销项发票品名推断"
SRC_NAME = "企业名称推断"
SRC_SCOPE = "经营范围推断"
SRC_BIZMODEL = "经营模式兜底"
SRC_UNKNOWN = "未确定"

# 各来源的置信度（供报告与下游判据使用，避免"一刀切当确证"）
CONFIDENCE = {
    SRC_ONLINE: "高", SRC_REGISTERED: "中高", SRC_INVOICE: "高",
    SRC_NAME: "中", SRC_SCOPE: "低", SRC_BIZMODEL: "低", SRC_UNKNOWN: "无",
}
# 数值化权重，便于排序比较
# ★ 2026-09-26：销项发票品名（实际经营产出）提到最高权重 6，作为**税务风险对标主口径**；
#   外部工商核验（仅限真实工商页面行业字段）次之。理由与边界见模块 docstring。
_WEIGHT = {SRC_INVOICE: 6, SRC_ONLINE: 5, SRC_REGISTERED: 4, SRC_NAME: 3,
           SRC_SCOPE: 2, SRC_BIZMODEL: 1, SRC_UNKNOWN: 0}


def infer_industries_from_goods(sales_goods: List[str], min_share: float = 0.2) -> List[str]:
    """从销项发票品名推断**多个**行业口径（主类目 + 次类目）。

    为什么需要（2026-09-26 用户指令"多业态"）：`infer_from_goods` 只取**单众数**，
    对**混合经营**（既卖货又提供服务、既做制造又做贸易）必然失真——
    众数之外的那部分业务会被整个行业口径丢掉，进而其对应的进项被误判成"非成本"。

    做法：与 `infer_from_goods` 同一套类目抽取与归一，但**按票数占比保留次类目**
    （占比 ≥ min_share 且至少 2 票），返回按票数降序的行业键列表；第一项即主类目。
    """
    import re
    from collections import Counter as _C
    cats = _C()
    for g in sales_goods or []:
        m = re.search(r"\*([^*]+)\*", str(g))
        if m:
            cat = m.group(1).strip()
            if len(cat) >= 2 and not cat.isdigit():
                cats[cat] += 1
    if not cats:
        return []
    _min_share = 0.2
    try:
        from engine.numparse import to_number as _ton
        _v = _ton(min_share)
        if _v is not None and _v > 0:
            _min_share = _v
    except Exception:
        pass
    total = sum(cats.values()) or 1
    merged = _C()
    for cat, n in cats.items():
        key = normalize_industry_name(cat) or cat
        merged[key] += n
    out = []
    for key, n in merged.most_common():
        if n < 2 and len(merged) > 1:
            continue
        # ⚠ 数值解析走 numparse 单一来源（裸 float 转换遇千分位或货币符会静默变 0）
        if (n / total) >= _min_share:
            out.append(key)
    # 至少保留主类目，避免空集
    if not out and merged:
        out = [merged.most_common(1)[0][0]]
    return out


def core_inputs_for_many(industries) -> List[str]:
    """多个行业口径的「核心投入」**并集**（多业态企业：各类业务的成本投入都要算）。"""
    out: List[str] = []
    for ind in (industries or []):
        for kw in core_inputs_for(ind):
            if kw and kw not in out:
                out.append(kw)
    return out


def core_inputs_for(industry: str) -> List[str]:
    """该行业的「核心投入」关键词 —— 用于把**进项发票**区分为「主营业务成本」与「期间费用」。

    为什么需要（2026-09-26 用户指令）：`main_biz_cost.identify_main_biz_cost` 原先只用
    品名关键词 + 金额大小，且"其余一律默认判主营业务成本"；**没有用行业**。而"什么算该行业的
    成本性投入"本就是**行业相关**的（商贸是所售商品、服务业是外购服务、制造是原料与加工费）。

    数据来源（全部是**已有的单一权威数据**，不新增重复表）：
      ① `core_inputs[行业]`：服务/流通类行业的外购投入（显式登记，见 static/industry_data.json）
      ② `product_chains[行业].raw_materials / .finished_goods`：制造·加工·贸易类行业的投入与产出品名

    新增同类行业只需在对应数据表加一行，不改本函数逻辑。
    """
    ind = str(industry or "").strip()
    if not ind:
        return []
    data = load_industry_data()
    # 容忍把发票分类名传进来（"广告服务" → "广告传媒"）
    key = normalize_industry_name(ind) or ind

    out: List[str] = []

    def _add(kw: Any) -> None:
        s = str(kw or "").strip()
        if s and s not in out:
            out.append(s)

    ci = data.get("core_inputs") or {}
    for k in (key, ind):
        for kw in (ci.get(k) or []):
            _add(kw)

    pc = data.get("product_chains") or {}
    for k in (key, ind):
        chain = pc.get(k) or {}
        if isinstance(chain, dict):
            for field in ("raw_materials", "finished_goods"):
                for kw in (chain.get(field) or []):
                    _add(kw)
    return out


def infer_from_goods(sales_goods: List[str]) -> Tuple[str, Dict[str, int]]:
    """③ 从**销项**发票品名推断行业（META-001）。

    唯一依据为销项品名，不参考进项：
      销项＝企业实际经营产出（卖什么就是什么行业）；进项＝采购投入/成本结构。
    做法：优先取金税发票 `*分类*` 编码的出现次数众数；无编码时回退 industry_map 关键词加权投票。
    ★ 返回前统一经 `normalize_industry_name` 归一到**行业基准库的键**，
      否则「广告服务」这类金税分类名与基准库键「广告传媒」字面不符 → 下游对标匹配不到 →
      回退经营范围 → 销项口径失效（真事故）。
    """
    import re
    from collections import Counter
    cats: Counter = Counter()
    for g in sales_goods or []:
        m = re.search(r"\*([^*]+)\*", str(g))
        if m:
            cat = m.group(1).strip()
            if len(cat) >= 2 and not cat.isdigit():
                cats[cat] += 1
    if cats:
        best = cats.most_common(1)[0][0]
        # 金税分类名可能不等于基准库键，交给 normalize_industry_name 做通用归一
        return normalize_industry_name(best), dict(cats.most_common(5))

    industry_map = load_industry_data().get("industry_map") or {}
    text = " ".join(str(g) for g in (sales_goods or []))
    votes: Counter = Counter()
    for kw, ind in industry_map.items():
        if kw and kw in text:
            votes[ind] += 1
    if votes:
        return normalize_industry_name(votes.most_common(1)[0][0]), dict(votes.most_common(5))
    return "", {}


def scope_industry_hint(scope_text: str = "", company_name: str = "") -> Optional[str]:
    """从**经营范围 / 企业名称**里取「行业级线索」→ 基准库键（找不到返回 None）。

    为什么需要（2026-10-01 真事故）：原逻辑「经营范围含购销词 → 判商贸」把**所有**
    服务型企业都拉成商贸——因为「销售/批发/零售/贸易」是中国公司经营范围的**万能尾巴**。
    实证：某传媒企业数字传媒，经营范围明写「广告设计、制作、代理、发布」+ 尾部「办公用品
    销售」，仍被判「商贸」（销项品名一旦抽不到，就 100% 落商贸）。

    判据（行业无关，靠**已有**单一数据源，不新增分类表）：
      逐条查 `industry_map` 关键词是否出现在经营范围/名称里，只采纳那些映射到
      `service_industries`（服务业态）的映射——即**行业级**线索；
      映射到 `production_industries`（制造/商品级，如「服装→服装制造」「饲料→农业生产」）
      的一律**不算**，因为按铁律 R1 商品/物料名不是行业。
      命中多条时：关键词**长度优先**，等长取 `industry_map` 声明顺序靠前者（结果确定）。

    注意：本函数是**弱证据**（来源 `SRC_SCOPE` 权重 2），只在销项品名/工商登记等
    强证据缺席时才真正决定口径；有更强证据时它只是被保留在 `candidates` 里用于留痕
    （登记口径 ≠ 经营范围口径 本身就是核查线索）。
    """
    text = "%s %s" % (str(scope_text or ""), str(company_name or ""))
    if not text.strip():
        return None
    im = load_industry_data().get("industry_map") or {}
    svc = set(load_industry_data().get("service_industries") or [])
    best_kw, best_ind = "", ""
    for kw, ind in im.items():
        k = str(kw or "").strip()
        if not k or k not in text:
            continue
        v = str(ind or "")
        if not v or v not in svc:
            continue
        # 「商贸 / 商贸批发 / 商贸零售 / 外贸 / 电子商务」是**购销兜底口径**，不是具体行业。
        # 它们由 `_trade_benchmark` 负责（只有经营范围里**没有**行业级线索时才走）。
        # 这里必须跳过：否则通用购销词会按声明顺序压过真正的行业词 —— 等长关键词不覆盖时
        # 保留先声明者，而「贸易」(industry_map 第 47 条) 声明早于「广告」(第 50 条)，
        # 于是「广告设计…；办公用品销售；国内贸易」会被「贸易」判成商贸（真事故路径）。
        if v in _TRADE_FALLBACK_INDUSTRIES:
            continue
        if len(k) > len(best_kw):
            best_kw, best_ind = k, v
    if not best_ind:
        return None
    return normalize_industry_name(best_ind) or best_ind


def industry_scope_keywords(industry: str) -> List[str]:
    """某行业在本系统基准库里登记的全部**行业级关键词**（行业无关，纯查表）。

    数据来源就是 `industry_data.json::industry_map` 的反查（kw→行业 的倒排），
    ★ 因此新增/调整任何行业都**只改数据表**，这里不改逻辑——全行业通用。
    附带并入：该行业名本身（去「业/服务/行业」等通用尾缀后的最短 distinctive 段）、
    以及 `SCOPE_MFG_HINTS`/`SCOPE_TRADE_HINTS` 这类**门类通用词** iff 该行业确属该门类
    （用 `SERVICE_FINE_TO_COARSE`/`BIZ_TO_COARSE` 反查，不为任一行业硬写死）。
    """
    ind = normalize_industry_name(str(industry or "")) or str(industry or "").strip()
    if not ind:
        return []
    im = load_industry_data().get("industry_map") or {}
    out: List[str] = []
    for kw, v in im.items():
        k = str(kw or "").strip()
        if not k or len(k) < 2:
            continue
        vv = normalize_industry_name(str(v or "")) or str(v or "")
        if vv == ind:
            out.append(k)
    # 行业名本身 + 去尾缀后的核心段（「广告传媒」→「广告传媒」；「广告传媒服务」→「广告传媒」）
    core = ind
    for suf in ("行业", "服务", "业务"):
        if core.endswith(suf) and len(core) > len(suf):
            core = core[: -len(suf)]
    if len(core) >= 2 and core not in out:
        out.append(core)
    # 门类通用词（生产/购销）——只在行业确实属该门类时并入
    _data = load_industry_data()
    for table, hints in (("production_industries", SCOPE_MFG_HINTS),
                         ("trade_industries", SCOPE_TRADE_HINTS)):
        for row in (_data.get(table) or _data.get(table.replace("_", "")) or []):
            names = row if isinstance(row, (list, tuple)) else (row.get("industry") if isinstance(row, dict) else "")
            if isinstance(names, (list, tuple)):
                hit = any((normalize_industry_name(str(n or "")) or str(n)) == ind for n in names)
            else:
                hit = (normalize_industry_name(str(names or "")) or str(names)) == ind
            if hit:
                out.extend(h for h in hints if h not in out)
                break
    # 保序去重
    seen, final = set(), []
    for k in out:
        if k and k not in seen:
            seen.add(k)
            final.append(k)
    return final


#: 经营范围文本的最小可用长度。低于此长度不足以判断"是否涵盖某行业"。
_SCOPE_MIN_LEN = 40


def scope_text_issue(scope_text: Any) -> str:
    """经营范围文本是否**可用于判定**；返回 ""＝可用，否则返回问题说明（可直接进报告）。

    ★ 2026-10-02（用户质疑「为什么还表述商贸」牵出的数据可靠性问题）：
      实测公司1 的 `business_scope` 只有 **56 字**、且以「…服装...」结尾 —— 它不是完整的
      工商登记经营范围，而是**联网核验结果的摘要片段**（`pipeline` 用正则
      `经营范围[：:](.{10,}?)(?=\\s{2,}|行业分类|工商信息)` 从搜索结果文本里抓的同一行片段，
      网页摘要自带省略号就被原样存库）。
      这类文本若直接拿去做「有没有行业级关键词」的判断，会给出**看似确定、实则无据**的结论
      （用户原文场景：报告写"广告传媒在经营范围文本中未见行业级关键词"，读者会以为
      这家公司经营范围真的与广告无关；真相是**我们拿到的经营范围本身是残缺片段**）。
      按本项目铁律「取不到数据时明确说明未确定，不得静默顶替后照常出结论」，
      此处先判定文本可用性，不可用即不得据此下结论。
    """
    s = str(scope_text or "").strip()
    if not s:
        return "未取得经营范围文本"
    if "..." in s or "…" in s:
        return "经营范围文本含省略号，疑为工商信息摘要片段（非完整登记原文）"
    if len(s) < _SCOPE_MIN_LEN:
        return "经营范围文本仅 %d 字，不足以判断行业归属" % len(s)
    return ""


def scope_covers_industry(industry: str, scope_text: str) -> Optional[bool]:
    """★ 通用判据：本轮采用的行业是否被**经营范围**所涵盖（None＝无从判定）。

    为什么必须存在（2026-10-02 用户口径事故）：
      原实现只要「登记行业 ≠ 销项开票推断行业」就写「两者不一致，指向超范围经营/变名开票」。
      但**经营范围是宽口径许可清单**，一家公司常常同时挂好几类业务，其中就可能包含本轮
      采用的行业 ⇒ 此时**不冲突**，不该报「超范围经营」（那是假冲突误报）。

    判据（行业无关、全行业通用）：
      · 经营范围文本里出现该行业的任一**行业级关键词**（查 `industry_scope_keywords`）
        ⇒ True（涵盖）；
      · 文本**可用**（见 `scope_text_issue`）且一个关键词都不含 ⇒ False（真线索）；
      · 经营范围文本为空 / 残缺不可用 / 基准库无该行业关键词 ⇒ None（无从判定，
        此时**不得**认定冲突，也不得说"未见行业级关键词"这种确定结论）。

    ⚠ 与 `scope_industry_hint` 的区别：后者是「从经营范围反推行业」（弱证据、用于候选），
      本函数是「经营范围是否容纳已知行业」（强证据、决定是否算冲突），二者不可互换。
    """
    ind = normalize_industry_name(str(industry or "")) or str(industry or "").strip()
    if not ind:
        return None
    scope = str(scope_text or "").strip()
    if not scope:
        return None
    if scope_text_issue(scope):
        # ★ 文本残缺 ⇒ 无从判定（**不得**据此下"未见该行业关键词"的确定结论）
        return None
    kws = industry_scope_keywords(ind)
    if not kws:
        # 基准库没登记该行业关键词 ⇒ 无从判定，宁可不说冲突
        return None
    for k in kws:
        if k and k in scope:
            return True
    return False


def resolve_industry(company_name: str = "", registered_industry: str = "",
                     online_industry: str = "", sales_goods: Optional[List[str]] = None,
                     business_scope: str = "", biz_model: str = "",
                     pipeline_log: Optional[List[str]] = None) -> Dict[str, Any]:
    """行业口径统一解析（唯一权威）。返回带来源/置信度/冲突的判定结果。

    返回：
      {
        "industry": 最终采用的行业（或 ""＝未确定）,
        "source": 来源标识（中文，可直接进报告）,
        "confidence": 高/中高/中/低/无,
        "candidates": {来源: 行业} 全部候选（R3：不一致也全部保留）,
        "conflicts": [冲突说明...],
        "registered": 登记行业, "inferred": 品名推断行业,
        "unknown": 是否未确定,
      }
    """
    log = pipeline_log if pipeline_log is not None else []
    sales_goods = sales_goods or []
    candidates: Dict[str, str] = {}

    online_industry = str(online_industry or "").strip()
    registered_industry = str(registered_industry or "").strip()
    if online_industry:
        candidates[SRC_ONLINE] = online_industry
    if registered_industry:
        candidates[SRC_REGISTERED] = registered_industry

    inferred, votes = infer_from_goods(sales_goods)
    if inferred:
        candidates[SRC_INVOICE] = inferred

    # 名称 / 经营范围：只在前面都没给出可识别行业时作为**补充候选**（不覆盖权威来源）
    root = load_industry_data()
    bm_keys = benchmark_keys()
    name_hit = _longest_hit(str(company_name or ""), bm_keys)
    if name_hit:
        candidates.setdefault(SRC_NAME, name_hit)
    scope_text = str(business_scope or "")
    if scope_text:
        # ★ 2026-10-01：先找「行业级线索」（广告/咨询/设计/软件…）；只有找不到时，
        #   才退回购销兜底（商贸/商贸批发/商贸零售）。原实现直接判商贸，导致
        #   经营范围带万能"销售/贸易"尾巴的服务型企业 100% 被判成商贸（真事故）。
        _scope_hint = scope_industry_hint(scope_text, str(company_name or ""))
        if _scope_hint:
            candidates.setdefault(SRC_SCOPE, _scope_hint)
        else:
            is_mfg = any(h in scope_text for h in SCOPE_MFG_HINTS)
            is_trade = any(h in scope_text for h in SCOPE_TRADE_HINTS)
            if is_trade and not is_mfg:
                tk = _trade_benchmark(scope_text)
                if tk:
                    candidates.setdefault(SRC_SCOPE, tk)
            else:
                sc_hit = _longest_hit(scope_text, bm_keys)
                if sc_hit:
                    candidates.setdefault(SRC_SCOPE, sc_hit)

    # ★ 先给三个变量「无解」默认值（2026-10-02）：candidates 为空时（全无资料）下面
    #   的三态冲突块会读到 best_src —— 不预置就会 UnboundLocalError，把"未确定"变成整次解析崩溃。
    best_src = ""
    industry = ""
    source = ""
    # 最终采用：按来源权威度取最高（同权威度时按插入顺序，前面更权威）
    if candidates:
        best_src = max(candidates.keys(), key=lambda s: (_WEIGHT.get(s, 0), -list(candidates).index(s)))
        industry = candidates[best_src]
        source = best_src
    else:
        # ⑥ 兜底：只到"粗粒度门类"层面，并明确标注这是低置信度兜底
        coarse_key = BIZ_TO_COARSE.get(str(biz_model or "").strip())
        industry = coarse_key or ""
        source = SRC_BIZMODEL if coarse_key else SRC_UNKNOWN

    # ── 冲突留痕（三态，2026-10-02 重构）────────────────────────────────
    # ★ 旧缺陷（用户口径事故）：只要「登记 ≠ 销项推断」就写「指向超范围经营/变名开票」。
    #   经营范围是**宽口径许可清单**，正常公司必然同时挂多类业务（登记商贸 ≠ 不能做广告）。
    #   本轮销项只有广告传媒一个行业且经营范围里有「广告」⇒ 已涵盖 ⇒ 根本不冲突，
    #   照旧报「超范围经营」是假冲突误报。
    # 新判据：只有「登记口径 ≠ 本轮采用口径」**且** 该口径未被经营范围涵盖 才算线索；
    #         无从判定（无经营范围文本/基准库无该行业关键词）时**不**认定冲突。
    scope_covers: Optional[bool] = None
    try:
        scope_covers = scope_covers_industry(industry, scope_text)
    except Exception:
        scope_covers = None

    conflicts: List[str] = []
    scope_note = ""
    if best_src != SRC_REGISTERED:
        other = candidates.get(SRC_REGISTERED, "")
        if other and other != industry:
            if scope_covers is True:
                # 已涵盖：只留痕，不作风险表述（报告据此不写冲突句）
                conflicts = []
                scope_note = (f"工商登记行业为「{other}」，本轮销项开票品名指向「{industry}」，"
                              f"该行业已为经营范围所涵盖，不构成超范围经营；"
                              f"本轮行业口径采用「{industry}」（来源：{source}）。")
            elif scope_covers is False:
                conflicts.append(
                    f"{SRC_REGISTERED}「{other}」≠ {SRC_INVOICE or source}「{industry}」；"
                    f"且「{industry}」在经营范围文本中未见行业级关键词，"
                    f"开票品名与实际经营是否一致，需核实")
            else:
                # scope_covers is None ⇒ **无从判定**：不写冲突，但必须如实说明**为什么判不了**。
                # ★ 2026-10-02（用户质疑「为什么还表述商贸」）：这里的"判不了"最常见的原因不是
                #   "经营范围里确实没有"，而是**我们拿到的经营范围本身不完整**（实测公司1 只有
                #   56 字、带省略号，是联网核验的摘要片段）。此时若照旧输出"未见行业级关键词"，
                #   就是把"数据不可用"说成了"事实如此" —— 按铁律必须如实标注数据问题。
                # ⚠ 只有"**有文本但不可用**"才需要说明原因；"完全没提供经营范围"保持
                #   scope_note 为空（本函数原有的三态语义：未经提供资料不在此处发声，
                #   补充资料的要求由报告"需企业提供的资料"章节统一提出，避免噪声）。
                _issue = scope_text_issue(scope_text)
                if _issue == "未取得经营范围文本":
                    _issue = ""
                if _issue and other and other != industry:
                    scope_note = (
                        f"工商登记行业为「{other}」，本轮销项开票品名指向「{industry}」；"
                        f"因{_issue}，无法据以判断「{industry}」是否在经营范围内，"
                        f"须以工商登记原文核实；本轮行业口径采用「{industry}」（来源：{source}）。")
            # scope_covers is None ⇒ 不写入 conflicts、不写风险表述
    if conflicts and log is not None:
        log.append("[行业口径] " + "；".join(conflicts)
                   + f"；本轮采用「{industry}」（来源：{source}）。")
    elif scope_note and log is not None:
        log.append("[行业口径] " + scope_note)

    # ★ 2026-09-26 多业态：除主类目外，一并给出**次类目**（占比达标的其他经营类目），
    #   供成本识别按并集匹配——否则混合经营企业众数之外的业务其进项会被误判为"非成本"。
    secondary: List[str] = []
    try:
        secondary = [k for k in infer_industries_from_goods(sales_goods) if k and k != industry]
    except Exception:
        secondary = []

    return {
        "industry": industry,
        "source": source,
        "confidence": CONFIDENCE.get(source, "无"),
        "candidates": candidates,
        "conflicts": conflicts,
        "scope_covers": scope_covers,
        "scope_note": scope_note,
        "registered": registered_industry,
        "inferred": inferred,
        "secondary": secondary,
        "votes": votes,
        "unknown": not industry,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 经营模式五分类（供 AGI 决定"跳过/启用哪些分析域"）
# ═══════════════════════════════════════════════════════════════════════════
# 通用类别词表（行业无关：任何行业都落在这五类之一）
UNIVERSAL_CATEGORIES: Dict[str, Dict[str, Any]] = {
    "生产型": {
        "indicators": ["制造", "生产", "加工", "装配", "冶炼", "化工", "纺织", "印染"],
        "risk_focus": ["原材料消耗与产出匹配", "水电能耗与产能对应", "进项税额合理性"],
        "skip_domains": [],
        "enable_domains": ["进销存分析", "BOM映射", "加工费专项"],
    },
    "建筑型": {
        "indicators": ["建筑", "工程", "施工", "装修", "装饰", "园林", "市政"],
        "risk_focus": ["项目成本归集", "分包合规性", "甲供材处理"],
        "skip_domains": ["BOM映射", "加工费专项", "进销存分析"],
        "enable_domains": ["工程项目分析"],
    },
    "服务型": {
        "indicators": ["服务", "咨询", "设计", "软件", "科技", "信息", "互联网",
                       "广告", "传媒", "文化", "教育", "培训"],
        "risk_focus": ["人均产值合理性", "经营费用完整性", "工资社保合规性"],
        # ★ 2026-10-03（用户："服务类采购本无物流"）：服务型企业**天然无实物货物流转**，
        #   "物流单据/入库验收单/出库单"这类货物流资料对其不适用。此前只剔了进销存/BOM，
        #   于是"异地货物类采购无货物流佐证"这类**要件**永远判"独立数据源未取得" ⇒
        #   要件无法核对 ⇒ 出罪要件（"不属于正当情形"）也永远核对不了 ⇒ 企业永远无法自证清白。
        "skip_domains": ["进销存分析", "BOM映射", "加工费专项", "水电能耗分析", "存货周转",
                         "货物流核验"],
        "enable_domains": ["人均产值分析", "费用完整性分析"],
    },
    "贸易型": {
        # 补"销售/购销"：只写"日用百货销售"（无零售/批发字样）的企业占比很高，
        # 缺这两个词会导致其无类别可归。该位置权重最低(1)，不会主导判定。
        "indicators": ["贸易", "经销", "批发", "零售", "进出口", "商贸", "销售", "购销"],
        "risk_focus": ["进销品名匹配", "供应商/客户集中度", "购销价格合理性"],
        "skip_domains": ["BOM映射", "加工费专项"],
        "enable_domains": ["进销存分析", "购销品名映射"],
    },
    "混合型": {
        "indicators": [],
        "risk_focus": ["同时具备生产和服务的特征，需分别分析"],
        "skip_domains": [],
        "enable_domains": ["全量分析域"],
    },
}
# 平局判定顺序：**具体业态优先于宽泛业态**。
# 贸易型最宽泛（只要涉及购销就命中），因此排最后 —— 避免把"数字传媒"这类
# 有明确业态的企业判成贸易型。
_CATEGORY_TIEBREAK = ("生产型", "建筑型", "服务型", "贸易型", "混合型")
# 命中位置权重（决定"经营模式五分类"）。
#   企业名称 = 主体对主营的**自我标识**，最能反映实际经营形态 → 权重最高(6)
#   登记行业字段 = 行政登记口径，常为宽泛兜底 → 中(3)
#   经营范围 = 只是"**可以**做什么"，且几乎每家企业都写了"销售/零售"，
#             若给高权重会把所有公司都拉成"贸易型" → 最低(1)
#   已推断行业（来自销项品名，反映实际产出）→ 最高(8)
_POS_WEIGHT = {"inferred": 8, "name": 6, "industry": 3, "scope": 1}


def business_category(industry: str = "", biz_model: str = "", company_name: str = "",
                      business_scope: str = "", business_category_hint: str = "") -> Dict[str, Any]:
    """把企业归入五类通用经营模式（供 AGI 决定启用/跳过哪些分析域）。

    与旧实现的区别：**不再把"企业名+行业"拼成一串数关键词靠字典顺序定胜负**，
    而是分别对企业名称 / 行业字段 / 经营范围 / 已推断行业计分并加权，
    平局按"具体业态优先"的固定顺序解决 —— 结果确定、可解释、与行业无关。
    """
    if business_category_hint in UNIVERSAL_CATEGORIES:
        cat = business_category_hint
        return {"category": cat, "config": UNIVERSAL_CATEGORIES[cat],
                "is_known_industry": True, "confidence": "高", "scores": {cat: 1}}

    inferred_cat = ""
    if str(biz_model or "").strip() in ("制造业", "服务业", "贸易业"):
        inferred_cat = {"制造业": "生产型", "服务业": "服务型", "贸易业": "贸易型"}[biz_model.strip()]

    texts = {
        "inferred": str(inferred_cat or ""),
        "name": str(company_name or ""),
        "industry": str(industry or ""),
        "scope": str(business_scope or ""),
    }
    scores: Dict[str, int] = {}
    for cat, cfg in UNIVERSAL_CATEGORIES.items():
        if cat == "混合型":
            continue
        s = 0
        for pos, text in texts.items():
            if not text:
                continue
            if any(ind in text for ind in cfg["indicators"]) or text == cat:
                s += _POS_WEIGHT[pos]
        if s:
            scores[cat] = s

    if not scores:
        cat = "混合型"
        return {"category": cat, "config": UNIVERSAL_CATEGORIES[cat],
                "is_known_industry": False, "confidence": "低", "scores": {}}

    best = max(scores.values())
    winners = [c for c in _CATEGORY_TIEBREAK if scores.get(c) == best]
    cat = winners[0]
    return {"category": cat, "config": UNIVERSAL_CATEGORIES[cat],
            "is_known_industry": True,
            "confidence": "高" if best >= 8 else ("中" if best >= 4 else "低"),
            "scores": scores}


def generalization_note(industry: str, category: str) -> str:
    """自我表述（R2）：在库中就说在库中，不在库中才说泛化；不再谎报"不在库中"。"""
    if is_in_benchmark_base(industry):
        return f"行业「{industry}」已在行业基准库中，按其基准区间完成指标对标。"
    return (f"行业「{industry}」不在66行业基准库中，但基于名称与特征自动归类为「{category}」。"
            f"适配该类型的通用风险模型进行分析。")

# ── 行业「随资料再判读」（industry_reassess）──────────────────────────────
#    观点来源（用户 2026-10-02）：「对行业的判断应该是随着系统接收到的资料和
#    信息后，经重新判读后再次确认或变更行业」。
#
#    现状（为什么需要）：行业过去只在 `_detect_target_entity` 里定一次，之后
#    合同、进项票、资料清单陆续到位也不再回头看——于是"经营范围只写销售/贸易"
#    的企业被购销兜底口径一次性钉死成「商贸」，全链（行业对标 / 成本费用口径 /
#    行业门控）都跟着错，且**错得很静默**。
#
#    设计铁律：
#      ★ 再判读**只能推翻、不能凭空定**：没有新证据一律 insufficient（不猜）。
#      ★ 新行业必须是**具体行业**（`service_industries` 映射），购销兜底口径
#        （商贸/商贸批发/商贸零售/外贸/电子商务）不算行业，不构成变更依据。
#      ★ 商品/物料名不算行业（沿用铁律 R1，只采纳 service 侧映射）。
#      ★ 决策三态 change / keep / insufficient，全部留痕进 pipeline_log。


def industry_hints_from_text(text: str) -> Dict[str, int]:
    """从任意一段文本抽「行业级线索」投票表（行业名 -> 命中次数）。

    判据与 `scope_industry_hint` 同源：只采纳 `industry_map` 中映射到
    `service_industries` 的关键词；排除购销兜底口径；归一化后同名合并。
    """
    text = str(text or "")
    if not text.strip():
        return {}
    im = load_industry_data().get("industry_map") or {}
    svc = set(load_industry_data().get("service_industries") or [])
    raw = {}
    for kw, ind in im.items():
        k = str(kw or "").strip()
        if not k or k not in text:
            continue
        v = str(ind or "")
        if not v or v not in svc or v in _TRADE_FALLBACK_INDUSTRIES:
            continue
        raw[v] = raw.get(v, 0) + 1
    if not raw:
        return {}
    merged = {}
    for v, n in raw.items():
        k = normalize_industry_name(v) or v
        merged[k] = merged.get(k, 0) + n
    if not merged:
        return {}
    # 票数降序、同票取名字更长的（更具体）——禁 hash 序，保证可复现
    return dict(sorted(merged.items(), key=lambda kv: (-kv[1], -len(kv[0]), kv[0])))


def _industry_reassess_log(pipeline_log, msg):
    if pipeline_log is not None:
        try:
            pipeline_log.append(msg)
        except Exception:
            pass


def reassess_industry(current_industry: str = "", *,
                      purchase_goods=None,
                      material_hints=None,
                      contract_text: str = "",
                      current_source: str = "",
                      pipeline_log: Optional[List[str]] = None) -> Dict[str, Any]:
    """资料收齐后，用**新增**证据对行业做一次再判读（唯一权威）。

    证据三路，均为弱证据，不能单独定行业，只能推翻或确认：
      ① `purchase_goods` 进项发票品名（采购侧实际买的东西）
      ② `material_hints` 已上传资料的文件名 / 资料类型（如「广告设计合同.docx」）
      ③ `contract_text` 合同 / 协议文本

    决策规则（★ 只有「一致」才改，不一致一律 keep，绝不猜）：
      · 新行业 == current            → keep（已一致，无需变更）
      · current 是**购销兜底口径**
        （商贸/商贸批发/商贸零售/外贸/电子商务）→ 只要有 ≥1 路证据指向某个具体行业，
        就 change（兜底本就低置信，用户场景正是"先判商贸、后凭合同取证为广告传媒"）
      · current 是**高权威口径**（销项品名 / 外部工商 / 工商登记）
        → 须 ≥2 路证据**同时**指向同一个具体行业才 change，否则 keep
      · 无任何新证据                  → insufficient

    返回：{industry, decision, evidence, reason, from_fallback}
    """
    cur = normalize_industry_name(current_industry) or str(current_industry or "")
    goods = purchase_goods or []
    mats = material_hints or []

    routes = [
        ("进项票品名", " ".join(str(g or "") for g in goods)),
        ("资料与文件名", " ".join(str(m or "") for m in mats)),
        ("合同文本", str(contract_text or "")),
    ]
    evidence: Dict[str, Dict[str, int]] = {}
    by_route: Dict[str, str] = {}
    merged: Dict[str, int] = {}
    for name, text in routes:
        if not str(text or "").strip():
            continue
        hits = industry_hints_from_text(text)
        if not hits:
            continue
        top = sorted(hits.items(), key=lambda kv: (-kv[1], -len(kv[0]), kv[0]))[0][0]
        evidence[name] = hits
        by_route[name] = top
        merged[top] = merged.get(top, 0) + 1

    if not evidence:
        _industry_reassess_log(pipeline_log, "[行业再判读] 未取得任何新证据（进项品名/资料/合同均无行业级线索），"
                          "保持原行业口径 '%s'" % cur)
        return {"industry": cur, "decision": "insufficient", "evidence": {},
                "from_fallback": cur in _TRADE_FALLBACK_INDUSTRIES,
                "reason": "无新证据，不做变更"}

    # ★ 只认「≥2 路证据同时指向同一行业」；单路证据不足以推翻高权威口径。
    #   ★ 并列第一（多个行业同票）＝**没有共识**，一律不得据此变更——宁可 keep，
    #     也不让弱证据在平局时任意挑一个（选谁都不本正，等于现场猜）。
    order = sorted(merged.keys(), key=lambda k: (-merged[k], -len(k), k))
    top_ind = order[0] if order else ""
    top_routes = merged.get(top_ind, 0)
    tied = [k for k in order if merged.get(k, 0) == top_routes]
    if len(tied) > 1:
        _industry_reassess_log(
            pipeline_log,
            "[行业再判读] 新证据在 %s 之间并票（各 %d 路），无共识，"
            "不据此变更原口径 '%s'" % ("、".join(tied), top_routes, cur))
        return {"industry": cur, "decision": "keep", "evidence": evidence,
                "from_fallback": cur in _TRADE_FALLBACK_INDUSTRIES,
                "reason": "新证据多行业并票，无共识"}

    is_fallback = cur in _TRADE_FALLBACK_INDUSTRIES

    # ★ 判定顺序：先问「证据够不够推翻」，再问「是不是同一行业」——
    #   反过来的话，单路弱证据指向原行业会被说成"证据一致"，掩盖了"证据不足"这个事实。
    enough = (top_routes >= 2) or (is_fallback and top_routes >= 1)
    if not enough:
        msg = ("新证据仅 %d 路指向 '%s'，未达推翻门槛" % (top_routes, top_ind))
        if top_ind == cur:
            msg += "（且仍与原口径一致），" + ("原口径属购销兜底，仍无强证据可确认" if is_fallback
                                        else "维持原口径 '%s'" % cur)
        else:
            msg += "；原口径 '%s' 非购销兜底，弱证据不得推翻，维持原口径" % cur
        _industry_reassess_log(pipeline_log, "[行业再判读] %s，不变更" % msg)
        return {"industry": cur, "decision": "keep", "evidence": evidence,
                "from_fallback": is_fallback, "reason": msg}

    if top_ind == cur:
        _industry_reassess_log(pipeline_log,
                              "[行业再判读] 新证据 %d 路一致指向 '%s'，维持原口径不变更" % (top_routes, cur))
        return {"industry": cur, "decision": "keep", "evidence": evidence,
                "from_fallback": is_fallback, "reason": "新证据与原口径一致，维持"}

    reason = ("原口径 '%s' 属购销兜底（低置信），新证据 %d 路一致指向 '%s'"
              % (cur, top_routes, top_ind)) if is_fallback else \
             ("新证据 %d 路一致指向 '%s'，超过原口径（来源 %s）" % (top_routes, top_ind, current_source))
    _industry_reassess_log(pipeline_log, "[行业再判读] 行业口径变更：'%s' → '%s'；%s"
                           % (cur, top_ind, reason))
    return {"industry": top_ind, "decision": "change", "evidence": evidence,
            "from_fallback": is_fallback, "reason": reason}



# ══════════════════════════════════════════════════════════════════════════
# 行业解析 → 写回分析上下文（**全流程唯一写回点**，2026-10-02）
# ══════════════════════════════════════════════════════════════════════════
def resolve_into_profile(ctx, sales_goods, db=None, company_id=None):
    """解析行业并写回 `ctx.company_profile`（唯一写回点）。

    为什么必须是唯一写回点
    ----------------------
    实测事故（用户复核「主营业务成本/期间费用没有变化」）：行业口径被**多处**写回
    `ctx.company_profile["industry"]`，且各处用的证据与算法不同 ——
      · Phase1 只用品名推断（且把发票品名传成 `set`，把"按张数取众数"偷换成
        "按品名种类取众数"）→ 得出「现代服务」（金税税目大类，不是具体行业）；
      · 报告侧 `_detect_target_entity` 用完整 `resolve_industry` → 得出「广告传媒」。
    结果：报告写「广告传媒」，而「主营业务成本 vs 期间费用」的判定按「现代服务」算，
    该行业在行业库里**没有核心投入登记** → 全部走业态兜底"待核"
    （实测 167 类待核、主营业务成本只剩 521.24 元）。
    同一件事两个入口、两套证据、两个结果 —— 这就是"改了代码但报告数字不变/变错"的推手。

    现在：解析与写回都在这里（调用同一个 `resolve_industry`），
    `phase1_triage` 与 `domain_analysis` 只做**薄转发**（同步闸门
    `audit_consistency.check_duplicate_definitions` 要求同名函数为转发桩）。

    参数
      sales_goods —— **销项品名列表（含重复）**。必须是列表：`infer_from_goods`
        取的是 `*分类*` 出现次数众数，传 set 会改变口径（见上）。
      db / company_id —— 用于取工商登记行业与经营范围（解析器的第 4/5 路证据）。
    """
    cp = getattr(ctx, "company_profile", None)
    if not isinstance(cp, dict):
        return {}
    _sales = list(sales_goods or [])

    _name = str(cp.get("name") or "")
    # ⚠ 登记行业只取登记口径字段：把推断结果（cp["industry"]）当登记回填＝自证循环。
    _reg = str(cp.get("industry_registered") or "")
    _scope = str(cp.get("business_scope") or "")
    if db is not None and company_id:
        try:
            from database import Company
            _c = db.query(Company).filter(Company.id == company_id).first()
            if _c is not None:
                _name = _name or str(_c.name or "")
                _reg = str(_c.industry_code or "") or _reg
                _scope = _scope or str(_c.business_scope or "")
        except Exception:
            pass

    res: Dict[str, Any] = {}
    try:
        res = resolve_industry(company_name=_name, registered_industry=_reg,
                               sales_goods=_sales, business_scope=_scope,
                               biz_model=str(cp.get("biz_model") or "")) or {}
    except Exception:
        res = {}
    ind = str(res.get("industry") or "").strip()
    if not ind:
        # 解析器给不出（无任何线索）→ 如实回退品名推断，并标注来源
        try:
            ind, _votes = infer_from_goods(_sales)
        except Exception:
            ind = ""
        res = {"industry": ind, "source": "销项发票品名推断（回退）"}
    cp["industry"] = ind or "综合"
    cp["industry_source"] = str(res.get("source") or "")
    cp["_industry_resolved"] = res
    return res


# ══════════════════════════════════════════════════════════════════════════
# 「按业态不适用」的资料（唯一权威，2026-10-02）
# ══════════════════════════════════════════════════════════════════════════
# 用户质疑：「如果行业为服务业，是否还欠缺进销存台账呢？」
#   业态配置里每个业态已声明 `skip_domains`（服务型明确含「进销存分析/存货周转/BOM映射」），
#   域分析据此跳过分析；但**资料要求没跟着走** ⇒ 同一份报告自相矛盾：
#     一处写「进销存跳过-服务行业：不适用进销存比值分析」，
#     另一处把「进销存台账」列为缺失并要求企业补交（实测企业版报告 94 处提及、
#     29 个疑点中 8 个的待补清单里出现它，有的**只有**这一项）。
#   对服务企业要求存货台账是**无效要求**：既增加企业负担，又让"资料齐全"永远达不到。
#   本表：**业态跳过的域 → 该域所需的资料名**；新增同类只加一行（资料名取自已登记名）。
_SKIPPED_DOMAIN_DOCS = {
    "进销存分析": ("进销存台账",),
    "存货周转": ("进销存台账",),
    "BOM映射": ("BOM物料清单",),
    "加工费专项": (),
    "水电能耗分析": (),
    # ★ 2026-10-03：服务型企业无实物货物流转 ⇒ 货物流类资料不适用（新增同类只加一行）
    # ★★ 2026-10-06（补齐"同一实物、多种叫法"）：原表只列了 7 个名字，
    #   而红线 `required_materials` 里同一族资料写作 **20 余种**叫法
    #   （入库单 / 存货台账 / 出入库单 / 完工入库单 / 存货明细账 / 产成品明细账 /
    #     领料单 / 投料单 / 盘点表 / 运输单据 / 运输与保险单据 / 过磅单与入库验收单 …）。
    #   实测后果（company_1 某传媒企业数字传媒·广告传媒/服务业）：覆盖清单仍把
    #   「入库单、存货台账、出入库单、完工入库单、存货明细账、运输单据 …」
    #   共 17 个税务红线检查项列为"缺资料受限"，等于**让一家广告公司去补它天然不会有的货物流单据**。
    #   ⚠ 为什么不能靠"资料类别"归一（`material_names.canonical`）来兜：
    #     · 「存货明细账 / 产成品明细账」会归到**科目余额表**（"明细账"压过"存货"）；
    #     · 「运输合同」归到**合同文件**，而合同文件对该业态是**适用**的
    #       （采购合同仍须提供）⇒ 类别级剔除会把"采购合同"一并误删。
    #   ⇒ 本族只能按**具体名**登记。**新增同类叫法仍只加一行数据，不改任何判定逻辑**。
    "货物流核验": ("物流单据", "入库验收单", "出库单", "过磅单", "承运合同",
                   "物流单据与承运记录", "运输合同",
                   # —— 2026-10-06 补齐的同族叫法（同一实物、不同写法）
                   "入库单", "出入库单", "出库单与领用单", "完工入库单",
                   "存货台账", "存货明细账", "产成品明细账", "存货盘点表", "盘点表",
                   "盘点表与毁损鉴定报告", "领料单", "投料单", "过磅单与入库验收单",
                   "运输单据", "运输与保险单据"),
}


def not_required_materials(industry) -> Tuple[set, str]:
    """按**业态**给出「不该列为必查/待补」的资料名与原因（单一权威）。

    返回 `(资料名集合, 说明文本)`；业态未知或该业态未跳过任何域时返回空集合与空文本
    —— **不臆测**：判不出就不剔，宁可多列也不无据少列。
    """
    ind = str(industry or "").strip()
    if not ind:
        return set(), ""
    try:
        _info = business_category(ind) or {}
    except Exception:
        return set(), ""
    if not _info.get("is_known_industry"):
        return set(), ""
    _cat = str(_info.get("category") or "")
    _skip = [str(x) for x in ((_info.get("config") or {}).get("skip_domains") or [])]
    docs: set = set()
    for _d in _skip:
        docs.update(_SKIPPED_DOMAIN_DOCS.get(_d) or ())
    if not docs:
        return set(), ""
    return docs, ("本企业业态为「%s」，天然无实物货物流转（该业态不适用：%s），"
                  "故下列资料不属于必查项，不因未提供而计入缺失：%s。"
                  % (_cat, "、".join(_skip), "、".join(sorted(docs))))


# ══════════════════════════════════════════════════════════════════════════
# ★★ 2026-10-06：「按名剔除业态不适用资料」的**唯一权威**（两件事：怎么切段、怎么判）
#
# ## 为什么必须收敛（用户口径：解决根因，不打补丁）
# 「把本业态不适用的资料从××清单里剔掉」这一个概念，此前有 **4 份各自实现**，
# 分隔符表不同、判定方向也不同 ⇒ 同一份要件在同一份报告里出现 4 种判法：
#
#   ① `evidence_chain.build_evidence_chain`（引擎层，字符级 `str.replace`）
#        不切段，把不适用资料名**当子串删掉**：
#          "采购合同与入库验收单" → "采购合同与"（悬空连词残词）
#          "物流单据与承运记录"   → "与承运记录" **或** ""（**取决于 set 迭代序**）
#        ⚠ 且它发生在 `status`/`basis`/`direct_missing` **算完之后** ⇒ 只有名字被改，
#          依据与「取得直接证据」清单仍是原始要求 ⇒ 服务型企业仍被要求补物流单据。
#   ② `enterprise_report._strip_not_required`（报告层，段级，**这一份是对的**）
#   ③ `constituent_checkpoint._decl_na`（要件层）
#        分隔符表**不含「与/及/和」** + **双向包含** ⇒ "采购合同与入库验收单" 不切段，
#        整体命中 "入库验收单" ⇒ 整条要件被误判「本业态不适用」。
#   ④ `enterprise_report._trim_text_materials`（整句文本级）
#
# ## 判据（数据驱动，与 `not_required_materials` 同一权威）
#   · 先按**并列分隔符**切段（含「与/及/和」，否则复合名切不开）；
#   · 逐段判定：段 == 不适用名，或段**包含**不适用名 ⇒ 剔该段；
#     ⚠ **禁止反向**（不适用名包含段）—— 实测 "合同" ⊂ "承运合同/运输合同"，
#       反向判定会把"采购合同"里的"合同"一并误删（此坑已踩过一次）。
#   · 剔完一段不剩 ⇒ 返回 ""（**整项本业态不适用**，调用方应剔除该项，不得当作"缺失"）；
#   · 无并列结构 ⇒ 原样返回（避免把含「与/和/及」的专有名词切坏）。
#   · **幂等**：结果再过一次不变；**确定性**：与 set 迭代序无关。
# ══════════════════════════════════════════════════════════════════════════

#: 材料名/数据源名内的**并列分隔符（「且」语义）**（"采购合同与入库验收单" ⇒ 两段）
#  ★★ 全系统**只此一处** —— 见下方 ★★ 说明：曾出现 4 份实现、4 种判法。
MATERIAL_SEG_SEP = re.compile(r"[、，,；;／/｜|\s]+|与|及|和|以及")
#: 「或」分隔（A或B ＝ 其一即可，**不是**"两样都要"，不得与上表混用语义）
MATERIAL_ALT_SEP = re.compile(r"或(?:者)?")
#: 只要**原子名**、不区分且/或时的合并切分（由上面两张表**派生**，不另立一份）
MATERIAL_ATOM_SEP = re.compile(MATERIAL_SEG_SEP.pattern + "|" + MATERIAL_ALT_SEP.pattern)


def _norm_na(not_required) -> List[str]:
    """规范化不适用资料名集合（去空白、去空、**长度降序**保证判定与迭代序无关）。"""
    _seen = set()
    out: List[str] = []
    for x in (not_required or ()):
        t = str(x or "").strip()
        if t and t not in _seen:
            _seen.add(t)
            out.append(t)
    # ★ 长度降序：段级判定虽与顺序无关，但降序可保证任何"前缀/包含"类兜底也稳定
    return sorted(out, key=len, reverse=True)


def classify_not_required_segments(name, not_required):
    """把材料名按并列分隔符切段并逐段判定 → `(保留段, 被剔段, 是否有并列结构)`。

    **唯一判定的"带明细"入口** —— 需要说明依据（"剔掉了哪几段"）的调用方走它；
    只需要结果字符串的走 `exclude_not_required_material`（同一实现，**薄转发**）。
    """
    s = str(name or "").strip()
    nr = _norm_na(not_required)
    if not s or not nr:
        return ([s] if s else []), [], False
    if s in nr:
        return [], [s], False
    segs = [x.strip() for x in MATERIAL_SEG_SEP.split(s) if x.strip()]
    if len(segs) <= 1:
        return ([s] if s else []), [], False
    keep, drop = [], []
    for x in segs:
        # ⚠ 单向判定（段 == 不适用名 或 段**包含**不适用名）；
        #   **禁止反向**（不适用名包含段）——"合同" ⊂ "承运合同/运输合同"，
        #   反向会把"采购合同"里的"合同"一并误删。
        if any(x == n or n in x for n in nr):
            drop.append(x)
        else:
            keep.append(x)
    return keep, drop, True


def exclude_not_required_material(name, not_required) -> str:
    """段级剔除材料名里**本业态不适用**的段；返回 "" 表示整项都不适用。

    **全系统唯一实现** —— 任何"按名剔除业态不适用资料"的链路都必须薄转发到本函数，
    不得各自 `re.split` / `str.replace`（见本文件顶部 ★★ 说明：曾出现 4 份实现、4 种判法）。
    """
    s = str(name or "").strip()
    if not s:
        return ""
    if not _norm_na(not_required):
        return s
    keep, drop, had = classify_not_required_segments(s, not_required)
    if not had:
        return "" if drop else s     # 整名恰为不适用名 ⇒ 整项剔除；否则原样
    if not drop:
        return s                      # 无段被剔 ⇒ 原样返回，不做无意义重组
    if not keep:
        return ""                     # 一段不剩 ⇒ 整项不适用
    return "、".join(keep)


#: 剔除后只剩"空动词"的段 ⇒ 整段无意义（"提供"、"取得"…）
_TEXT_EMPTY_VERBS = ("提供", "补充提供", "补充", "取得", "提供相应", "留存",
                     "出具", "提供相应资料")
_TEXT_TRIM_PUNCT = " \u3000，,；;。：:（）()"


def exclude_not_required_in_text(text, not_required) -> str:
    """在**整句文本**里按「、」并列段剔除本业态不适用资料（**唯一实现**）。

    例：`提供付款对应的采购合同、入库验收单、物流单据，并对××作出书面说明`
      → `提供付款对应的采购合同，并对××作出书面说明`
    用于红线自带的「补救要求」等**成句文案**（`exclude_not_required_material` 只管单个名）。
    """
    t = str(text or "")
    nr = _norm_na(not_required)
    if not t or not nr:
        return t
    out = []
    for p in t.split("、"):
        core = p.strip(_TEXT_TRIM_PUNCT)
        drop = core in nr
        if not drop:
            for n in nr:
                if core.startswith(n):
                    p = p.replace(n, "", 1)
                    break
                if core.endswith(n):
                    i = p.rfind(n)
                    p = p[:i] + p[i + len(n):]
                    break
            if not p.strip(_TEXT_TRIM_PUNCT):
                drop = True
            elif p.strip(_TEXT_TRIM_PUNCT) in _TEXT_EMPTY_VERBS:
                drop = True
        out.append("" if drop else p)
    kept = []
    for i, p in enumerate(out):
        if not p.strip():
            continue
        if i > 0:
            p = p.lstrip(" \u3000，,；;。：:与及和")
        if p.strip():
            kept.append(p)
    return "、".join(kept).replace("、并", "，并")


#: 段级剔除后可能出现**悬空连词**（"采购合同**与**"）—— 残词自检用（闸门与测试共用）
_DANGLING_EDGE = "、，,；;与及和 \u3000"
#: 并列连词（段级剔除全部按它们切段 ⇒ 被改写过的结果里**不应再出现**）
_PARA_CONJ = "与及和"


def has_dangling_separator(text, original=None) -> bool:
    """名字是否因剔除不当而留下**残词**（悬空连词，如"采购合同与"、"与承运记录"）。

    ★★ 判据**必须给 `original`**（剔除前的原名），否则会把合法名称误判成残词 ——
      实测踩过：「与境外方签署的合同或协议、董事会利润分配决议」本就以「与」开头，
      单看字符串会当成残词（**闸门自己报的假红**）。
    给了原名后的精确判据：
      · `text == original` ⇒ **未被改写**，原样输出是正确行为，**不是**残词；
      · 被改写 ⇒ 结果里**不应再出现任何并列连词**（与/及/和）—— 它们是切段符，
        段级剔除的每个保留段都不含它们；再出现即只可能是"字符级删字"留下的残词。
    未给 `original` 时退回宽松判据（只看首尾字符），仅供调试，闸门不得用。
    """
    s = str(text or "").strip()
    if not s:
        return False
    if original is not None:
        o = str(original or "").strip()
        if s == o:
            return False
        return any(ch in s for ch in _PARA_CONJ)
    return s[0] in _DANGLING_EDGE or s[-1] in _DANGLING_EDGE
