# -*- coding: utf-8 -*-
"""疑点4 · D12 修复（一次性接线，锚点已验证唯一）。

根因：`estimate_tax` 对 taxes 里每个税种用同一个 amount × 税率，
**从不校验"该税种要求的基数性质"** ⇒ 工资差额被当应税收入算增值税（928,000×6%=55,680，
再随征 12% 出 6,681.60，凭空 62,361.60）。

修法（单一权威、数据驱动、**不删税种声明**）
--------------------------------------------
① `_TAX_BASE_NATURE` + `_FACT_NATURE_RULES` + `infer_amount_nature()`（表与判定）
② `estimate_tax(..., amount_nature="")`（**带默认值** ⇒ 不传时行为完全不变）
③ 循环内相容性判断：性质不符 ⇒ **不估**（amount=None + 如实说明），不删税种、不用默认值顶替
④ 调用点 `enterprise_report:3175` 传入性质（判不出传空 ⇒ 零回归）

纪律（今天用 7 次返工换来）
--------------------------
- **锚点全部校验唯一后才写盘**（②用 `def estimate_tax(...)` 两行组合，单用尾串会命中 2 次）；
- **写盘前先预检**性质判定，预检不过就不写；
- 四处一起应用，不中途退出留半成品。
"""
import io
import os
import sys

ROOT = os.getcwd()
NL = chr(10)
CRLF = chr(13) + chr(10)
TI = os.path.join(ROOT, "engine", "tax_impact.py")
ER = os.path.join(ROOT, "engine", "enterprise_report.py")

TABLE = '''# ★★ 2026-10-04（疑点4 D12 修复）：**税种 × 基数性质**相容性（单一权威）。
#   事故：RL-INC-002（个人账户收取经营性款项：公私混同隐匿收入）声明含增值税/附加，
#   而 `estimate_tax` 对每个税种用**同一个 amount × 税率**、从不校验基数性质
#   ⇒ 工资差额 928,000 被当成应税收入 × 6% = 55,680，再随征 12% 出附加 6,681.60
#   ⇒ **凭空 62,361.60**（发工资不产生销项税）。
#   本表只声明"各税种的基数必须是什么性质"；性质不符 ⇒ **不估**（如实标注），
#   **不删税种声明** —— 隐匿收入确实可能牵涉增值税，删掉会掩盖真实风险。
_TAX_BASE_NATURE: Dict[str, str] = {
    "增值税": "sales",
    "城建税及教育费附加": "sales",
    "城市维护建设税": "sales",
    "教育费附加": "sales",
    "地方教育附加": "sales",
    "企业所得税": "profit",
    "个人所得税": "wage",
    "印花税": "contract",
}

#: 事实类型 → 基数性质（**按顺序**匹配，先命中者胜）。
#   ⚠ 账户/往来/公私混同类**必须排在销售类之前**：否则「公私混同隐匿收入」
#   会因含"收入"被判成 sales ⇒ 恰恰放过 D12 这类张冠李戴。
#   ⚠ 判不出就返回 ""（调用方不做判断）——**宁可漏判相容性，也不误不估**。
_FACT_NATURE_RULES: tuple = (
    (("公私混同", "个人账户", "私户", "个人卡", "往来", "借款", "挂账", "其他应收"), "non_sales"),
    (("工资", "薪酬", "薪金", "代发", "劳务"), "wage"),
    (("账外收入", "开票", "销项", "销售额", "收入"), "sales"),
    (("利润", "成本", "费用", "税前", "所得"), "profit"),
)


def infer_amount_nature(obj: Any) -> str:
    """判定疑点的**基数性质**（sales/profit/wage/contract/non_sales）；判不出返回 ""。

    判据全部取自 `_FACT_NATURE_RULES`（数据驱动，新增事实类型只加一行）。
    判不出 ⇒ 返回 "" ⇒ 调用方不做相容性判断 ⇒ **行为与改动前完全一致**。
    """
    _t = obj if isinstance(obj, str) else " ".join(
        str(obj.get(k) or "") for k in ("title", "finding_type", "detail", "suspect", "taxes")
    )
    for _kws, _nat in _FACT_NATURE_RULES:
        for _k in _kws:
            if _k in _t:
                return _nat
    return ""


'''

A1 = "def estimate_tax(amount: Optional[float], taxes: Optional[List[str]]," + NL
A2 = (A1 + "                 rate_ctx: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:")
N2 = (A1 + NL
      + "                 rate_ctx: Optional[Dict[str, Any]] = None," + NL
      + '                 amount_nature: str = "") -> Dict[str, Any]:')
A3 = ('        amt = round(amount * rate, 2)' + NL + '        if t == "增值税":')
N3 = (
    '        # ★ 2026-10-04（疑点4 D12）：**基数性质相容性** —— 基数口径与本税种要求不符' + NL +
    '        #   ⇒ **不估**（不删税种、不用默认值顶替），如实登记一条未量化项。' + NL +
    '        _need = _TAX_BASE_NATURE.get(t)' + NL +
    '        if amount_nature and _need and _need != amount_nature:' + NL +
    '            items.append({"tax": t, "rate": "", "amount": None,' + NL +
    '                          "note": ("本项事实的金额口径为「%s」，与本税种要求的基数性质"' + NL +
    '                                   "「%s」不符，不作加计（无对应的应税收入/所得/工资事实支撑）；"' + NL +
    '                                   "如另存在应税收入事实，应另行核对。"' + NL +
    '                                   % (amount_nature, _need))})' + NL +
    '            continue' + NL +
    '        amt = round(amount * rate, 2)' + NL + '        if t == "增值税":')
A4 = ('            _p["tax_impact"] = estimate_tax(_norm.get("amount"), _p.get("taxes"),' + NL
      + '                                            rate_ctx=rate_ctx)')
N4 = ('            # ★ 2026-10-04（疑点4 D12）：传入**基数性质**，让 tax_impact 能判断' + NL
      + '            #   这个税种的基数是不是本项事实的金额（判不出则传空，行为不变）。' + NL
      + '            from engine.tax_impact import infer_amount_nature as _ian' + NL
      + '            _p["tax_impact"] = estimate_tax(_norm.get("amount"), _p.get("taxes"),' + NL
      + '                                            rate_ctx=rate_ctx,' + NL
      + '                                            amount_nature=_ian(_p))')


def rd(p):
    return io.open(p, "r", encoding="utf-8", newline="").read().replace(CRLF, NL)


def wr(p, s, had_crlf):
    io.open(p, "w", encoding="utf-8", newline="").write(s.replace(NL, CRLF) if had_crlf else s)


# ══ 步骤 1：预检（性质判定）══
ns = {"Dict": dict, "Any": object, "List": list, "Tuple": tuple}
exec(TABLE, ns)
print("=== 预检：性质判定 ===")
_cases = [
    ({"title": "个人账户收取经营性款项：公私混同隐匿收入"}, "non_sales", "RL-INC-002（D12 现场）"),
    ({"title": "银行收款大于申报收入：存在账外收入嫌疑"}, "sales", "RL-INC-001（应仍估增值税）"),
    ({"title": "公转私大额频繁支出：变相分配与个税风险"}, "", "公转私⇒不判（安全默认）"),
    ({"title": "某无关事项"}, "", "判不出⇒空⇒行为不变"),
]
_ok = True
for _obj, _want, _tag in _cases:
    _got = ns["infer_amount_nature"](_obj)
    if _got != _want:
        _ok = False
    print("  %-26s 期望=%-10s 实得=%-10s %s" % (_tag, _want, _got,
          "OK" if _got == _want else "**不符**"))
if not _ok:
    print("!! 预检未通过 ⇒ 不写盘")
    sys.exit(3)

# ══ 步骤 2：锚点全部校验（先查后写，一次应用）══
ti = rd(TI)
er = rd(ER)
plan = [(TI, ti, A1, TABLE + A1, "①表与函数"),
        (TI, ti, A2, N2, "②签名加参数"),
        (TI, ti, A3, N3, "③相容性判断"),
        (ER, er, A4, N4, "④调用点传参")]
print("")
print("=== 锚点校验 ===")
for _p, _body, _old, _new, _tag in plan:
    _c = _body.count(_old)
    print("  %-12s 命中 %d 次 %s" % (_tag, _c, "OK" if _c == 1 else "**不唯一**"))
    if _c != 1:
        print("!! 锚点不唯一 ⇒ 不写盘（避免半成品）")
        sys.exit(2)

# ══ 步骤 3：应用（两文件分别一次性写）══
for _p, _body, _old, _new, _tag in plan:
    _had = CRLF in io.open(_p, "r", encoding="utf-8", newline="").read()
    _t = _body.replace(_old, _new, 1)
    wr(_p, _t, _had)
    print("  OK " + _tag)
print("[DONE] D12 已接线")
