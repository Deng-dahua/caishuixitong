# -*- coding: utf-8 -*-
"""68 条红线 constituents 归一化+去生硬打磨（保留原意，最低风险）。

硬约束（务必守住）：
  - 只替换 19 处已枚举的"要件内混入判定方法论/模糊量词未锚定/生硬措辞"；
  - 不改条数、不改序号顺序、不触动末项「不属于…正当情形」出罪要件；
  - 因此 engine/redline_engine.py 的 _DEFAULT_HIT_INDEX 兜底映射继续有效。
验证：每处 old 在文件中恰好出现 1 次 -> 替换后重新导入 REDLINES，
  断言每条被改红线的 constituents 条数不变、末项仍含「不属于」、新文本已落地。
"""
import importlib.util
import os
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "engine", "tax_redlines.py")

# (old, new) —— 仅触及实质性要件（均不含「不属于」）
REPLACEMENTS = [
    ("存在无对应进项来源的销售额（金额与占同期销售额的比例需评估）",
     "存在无对应进项来源的销售额（需结合金额与占同期销售额比例综合研判）"),
    ("存在无对应销项实现的进项税额（金额与占同期进项的比例需评估）",
     "存在无对应销项实现的进项税额（需结合金额与占同期进项比例综合研判）"),
    ("上述差额的金额与占申报收入比例需评估",
     "上述差额金额与占申报收入比例异常（需结合企业规模综合研判）"),
    ("第四季度或12月费用占全年比例偏高（比例需评估）",
     "第四季度或12月费用占全年比例偏高（需结合行业与历史水平综合研判）"),
    ("不动销存货金额占存货的比重需评估",
     "不动销存货金额占存货的比重异常（需结合行业与历史水平综合研判）"),
    ("涉及工资列支金额（金额需评估）",
     "涉及工资列支金额重大（需结合企业规模与行业水平综合研判）"),
    ("存在未付款金额（占同类成本比例需评估）",
     "存在未付款金额（需结合占同类成本比例综合研判）"),
    ("存在异地采购，采购金额与异地占比需评估",
     "存在异地采购，采购金额与异地占比异常（需结合行业与历史水平综合研判）"),
    ("差额金额需评估",
     "差额金额异常（需结合合同与开票数据综合研判）"),
    ("损失金额需评估，且无合法有效证据支撑",
     "损失金额异常（需结合企业规模综合研判），且无合法有效证据支撑"),
    ("销售折扣、折让比例与合同、开票不一致，或比例需评估",
     "销售折扣、折让比例与合同、开票不一致，或比例异常（需结合行业与历史水平综合研判）"),
    ("偏离幅度需结合行业均值与自身历史水平评估",
     "毛利率偏离幅度异常（需结合行业均值与自身历史水平综合研判）"),
    ("与之发生购销交易且金额重大",
     "与之发生购销交易且金额重大（需结合企业规模与行业水平综合研判）"),
    ("加工费支出重大但受托方地域分散或与本企业无产能关联",
     "加工费支出重大（需结合企业规模与行业水平综合研判），且受托方地域分散或与本企业无产能关联"),
    ("断裂环节涉及金额重大",
     "断裂环节涉及金额重大（需结合企业规模与行业水平综合研判）"),
    ("差异金额重大",
     "差异金额重大（需结合企业规模与行业水平综合研判）"),
    ("咨询费、服务费、会务费、推广费等无形服务支出金额重大",
     "咨询费、服务费、会务费、推广费等无形服务支出金额重大（需结合企业规模与行业水平综合研判）"),
    ("与关联方发生大额资金拆借",
     "与关联方发生大额资金拆借（需结合企业规模与行业水平综合研判）"),
    ("差异人员无劳务派遣、退休返聘、实习生、非全日制等合法豁免身份",
     "差异人员不属于劳务派遣、退休返聘、实习生、非全日制等依法免缴社保的情形"),
]


def load_modified(text):
    spec = importlib.util.spec_from_file_location("tax_redlines_polish", SRC)
    mod = importlib.util.module_from_spec(spec)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".py",
                                     delete=False, dir=os.path.dirname(SRC)) as tf:
        tf.write(text)
        tmp = tf.name
    try:
        spec = importlib.util.spec_from_file_location("tax_redlines_polish", tmp)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        os.unlink(tmp)


def main():
    with open(SRC, encoding="utf-8") as f:
        text = f.read()

    # 1) 唯一性校验：每处 old 在原文件恰好出现 1 次
    for old, new in REPLACEMENTS:
        n = text.count(old)
        assert n == 1, "唯一性校验失败：「%s…」出现 %d 次（须恰好 1 次）" % (old[:20], n)

    # 2) 改前基线：被改红线的 constituents 条数
    before = load_modified(text)
    baseline = {}
    for rl in before.REDLINES:
        if any(c == old for old, _ in REPLACEMENTS for c in (rl.get("constituents") or [])):
            baseline[rl["id"]] = len(rl["constituents"])

    # 3) 应用替换
    new_text = text
    for old, new in REPLACEMENTS:
        new_text = new_text.replace(old, new)

    # 4) 重新导入验证
    after = load_modified(new_text)
    new_by_id = {r["id"]: r for r in after.REDLINES}
    assert len(after.REDLINES) == len(before.REDLINES), "红线总数变化！"

    for rid, n_cons in baseline.items():
        cons = new_by_id[rid].get("constituents") or []
        assert len(cons) == n_cons, "%s 要件条数变化：%d→%d" % (rid, n_cons, len(cons))
        assert ("不属于" in cons[-1]) or ("豁免" in cons[-1]), "%s 末项出罪要件丢失：%s" % (rid, cons[-1])

    flat = []
    for r in after.REDLINES:
        flat.extend(r.get("constituents") or [])
    flat = " ".join(flat)
    for old, new in REPLACEMENTS:
        assert new in flat, "新文本未落地：%s…" % new[:20]
    # 每处 old 在改前恰好 1 次（已校验），replace 为确定性替换 -> 旧文本必被新文本取代；
    # new 以 old 为前缀属预期，故不以 count(old)==0 判定，仅确认确有改动发生。
    assert new_text != text, "文件未发生任何改动"

    # 5) 写回原文件
    with open(SRC, "w", encoding="utf-8") as f:
        f.write(new_text)

    print("OK: 应用 %d 处 constituents 归一化+去生硬打磨，覆盖 %d 条红线" % (len(REPLACEMENTS), len(baseline)))
    for rid in baseline:
        print("  - %s（要件条数保持 %d）" % (rid, baseline[rid]))


if __name__ == "__main__":
    main()
