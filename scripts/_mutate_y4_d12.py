# -*- coding: utf-8 -*-
"""疑点4 · D12 修复：**税种 × 基数性质**相容性（防止"工资差额被当应税收入算增值税"）。

根因（`engine/tax_impact.estimate_tax`）
--------------------------------------
它对 `taxes` 里的**每个税种**用 `_RATES` 税率 × **同一个 `amount`**，
**从不校验"该税种要求的基数性质"与本项事实是否相容**。
事故：RL-INC-002（个人账户收取经营性款项：公私混同隐匿收入）声明含增值税/附加
⇒ 工资差额 928,000 被当作应税收入 × 6%（`rate_ctx.vat_rate`）= 55,680
⇒ 再随征 12% 出附加 6,681.60 ⇒ **凭空 62,361.60**（发工资不产生销项税）。

修法（单一权威、数据驱动、**不删税种声明**）
--------------------------------------------
① `_TAX_BASE_NATURE`：各税种**要求的基数性质**（sales/profit/wage/contract）。
② `estimate_tax(..., amount_nature="")`：传入性质且与该税种要求**不符** ⇒
   该税种**不估**（`amount=None` + 如实说明"基数口径为 X、与本税种要求的 Y 不符，不作加计"）。
   增值税不估 ⇒ `vat_amount=0` ⇒ 随征附加**自动不估**（现有逻辑已保证）。
③ `infer_amount_nature(problem)`：从疑点文本按**优先级**判事实性质
   （账户/公私混同/私户/往来 优先于 销售/开票/账外收入 —— 否则"隐匿收入"会把
   公私混同误判成"销售"）；判不出返回 "" ⇒ **保持现状**（零回归）。
④ 缺陷描述：④③ 任一为空 ⇒ 全部保持原行为。

**预检（写盘前必过）**：先验证 `infer_amount_nature` 对三个真实标题给出预期性质，
预检不过就**不写盘**（吸取 `canonical()` 返回 None 还继续推进的教训）。
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


def swap(path, old, new, tag):
    raw = io.open(path, "r", encoding="utf-8", newline="").read()
    crlf = CRLF in raw
    t = raw.replace(CRLF, NL)
    if t.count(old) != 1:
        print("!! %s 命中 %d 次" % (tag, t.count(old)))
        sys.exit(2)
    t = t.replace(old, new, 1)
    io.open(path, "w", encoding="utf-8", newline="").write(t.replace(NL, CRLF) if crlf else t)
    print("OK " + tag)


# ── ① 表 + 判定函数（插在 estimate_tax 之前）──────────────────────────
# ══ 预检（必须在写盘前跑）════════════════════════════════════════════
print("")
print("=== 预检（性质判定）===")
ns = {"Dict": dict, "Any": object, "List": list, "Tuple": tuple}
exec(TABLE, ns)   # 只执行表与判定函数（无副作用）
cases = [
    ({"title": "个人账户收取经营性款项：公私混同隐匿收入"}, "non_sales", "RL-INC-002"),
    ({"title": "银行收款大于申报收入：存在账外收入嫌疑"}, "sales", "RL-INC-001"),
    ({"title": "公转私大额频繁支出：变相分配与个税风险"}, "", "公转私⇒不判(安全默认)"),
    ({"title": "某无关事项"}, "", "判不出⇒空⇒行为不变"),
]
_ok = True
for obj, want, tag in cases:
    got = ns["infer_amount_nature"](obj)
    flag = "OK" if got == want else "**不符**"
    if got != want:
        _ok = False
    print("  %-34s 期望=%-10s 实得=%-10s %s  (%s)" % (tag[:32], want, got, flag, ""))
print("")
print("预检通过" if _ok else "预检未通过")
if not _ok:
    sys.exit(3)   # 预检不过 ⇒ 不写盘


if "_TAX_BASE_NATURE" in io.open(TI, encoding="utf-8").read():
    print("SKIP ①表与函数（已存在，幂等）")
else:
    swap(TI, "def estimate_tax(amount: Optional[float], taxes: Optional[List[str]],",
         TABLE + "def estimate_tax(amount: Optional[float], taxes: Optional[List[str]],", "①表与函数")

# ── ② 签名加可选参数 amount_nature（带默认值 ⇒ 零回归）────────────────
swap(TI,
     "def estimate_tax(amount: Optional[float], taxes: Optional[List[str]],\n"
                 "rate_ctx: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:",
     "def estimate_tax(amount: Optional[float], taxes: Optional[List[str]],\n"
     "                 rate_ctx: Optional[Dict[str, Any]] = None,\n"
     "                 amount_nature: str = \"\") -> Dict[str, Any]:",
     "②签名加参数")

# ── ③ 循环内相容性判断（放在 amt 计算前）────────────────────────────
swap(TI,
     "        amt = round(amount * rate, 2)\n        if t == \"增值税\":",
     "        # ★ 2026-10-04（疑点4 D12）：**基数性质相容性** —— 基数口径与本税种要求不符\n"
     "        #   ⇒ **不估**（不删税种、不用默认值顶替），如实登记一条未量化项。\n"
     "        _need = _TAX_BASE_NATURE.get(t)\n"
     "        if amount_nature and _need and _need != amount_nature:\n"
     "            items.append({\"tax\": t, \"rate\": \"\", \"amount\": None,\n"
     "                          \"note\": (\"本项事实的金额口径为「%s」，与本税种要求的基数性质\"\n"
     "                                   \"「%s」不符，不作加计（无应税收入/所得/工资等对应事实支撑）；\"\n"
     "                                   \"如另存在应税收入事实，应另行核对。\" % (amount_nature, _need))})\n"
     "            continue\n"
     "        amt = round(amount * rate, 2)\n        if t == \"增值税\":",
     "③相容性判断")

# ── ④ 调用点传 nature ────────────────────────────────────────────────
swap(ER,
     "            _p[\"tax_impact\"] = estimate_tax(_norm.get(\"amount\"), _p.get(\"taxes\"),\n"
     "                                            rate_ctx=rate_ctx)",
     "            # ★ 2026-10-04（疑点4 D12）：传入**基数性质**，让 tax_impact 能判断\n"
     "            #   \"这个税种的基数是不是本项事实的金额\"（判不出则传空，行为不变）。\n"
     "            from engine.tax_impact import infer_amount_nature as _ian\n"
     "            _p[\"tax_impact\"] = estimate_tax(_norm.get(\"amount\"), _p.get(\"taxes\"),\n"
     "                                            rate_ctx=rate_ctx,\n"
     "                                            amount_nature=_ian(_p))",
     "④调用点传参")

