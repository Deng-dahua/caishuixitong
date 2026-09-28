# -*- coding: utf-8 -*-
"""修复 _DEFAULT_HIT_INDEX：enrich 脚本的正则未读到原 18 条，误清空。
重建 = 原 18 条索引（enrich 只追加在出罪要件前，原序号仍有效） ∪ 本轮新增场景序号。
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "engine", "tax_redlines.py")
ENG = os.path.join(ROOT, "engine", "redline_engine.py")

# 原 18 条兜底红线索引（enrich 前状态，现仍有效）
ORIGINAL_18 = {
    "RL-PTY-002": [2],
    "RL-FUND-001": [1],
    "RL-CIT-001": [1],
    "RL-PTY-004": [1, 2],
    "RL-SPT-008": [1],
    "RL-SPT-011": [1],
    "RL-PAY-005": [2, 3],
    "RL-PTY-003": [1, 3],
    "RL-INC-002": [1, 3],
    "RL-AST-003": [1, 2],
    "RL-PAY-002": [1, 2],
    "RL-PAY-003": [1],
    "RL-AST-001": [1, 2, 3],
    "RL-FUND-002": [1, 2, 3],
    "RL-OTH-003": [1, 2],
    "RL-VAT-002": [1, 2, 3],
    "RL-VAT-006": [1, 2, 3],
    "RL-COST-003": [1, 2],
}

# 本轮各红线新增场景数（与 _enrich_constituents.EXTRA 一致）
EXTRA_N = {
    "RL-VAT-001": 2, "RL-VAT-002": 2, "RL-VAT-003": 1, "RL-VAT-004": 1,
    "RL-VAT-005": 1, "RL-VAT-006": 1, "RL-VAT-007": 1, "RL-VAT-008": 1,
    "RL-VAT-009": 1, "RL-VAT-010": 1, "RL-VAT-011": 1, "RL-INC-001": 1,
    "RL-INC-002": 1, "RL-INC-003": 1, "RL-INC-004": 1, "RL-COST-001": 1,
    "RL-COST-002": 1, "RL-COST-003": 1, "RL-COST-004": 1, "RL-COST-005": 1,
    "RL-COST-006": 1, "RL-FUND-001": 1, "RL-FUND-002": 1, "RL-FUND-003": 1,
    "RL-FUND-004": 1, "RL-FUND-005": 1, "RL-FUND-006": 1, "RL-INV-001": 1,
    "RL-INV-002": 1, "RL-INV-003": 1, "RL-PAY-001": 1, "RL-PAY-002": 1,
    "RL-PAY-003": 1, "RL-PAY-004": 1, "RL-PAY-005": 1, "RL-PAY-006": 1,
    "RL-CIT-001": 1, "RL-CIT-002": 1, "RL-CIT-003": 1, "RL-CIT-004": 1,
    "RL-CIT-005": 1, "RL-CIT-006": 1, "RL-CIT-007": 1, "RL-PTY-001": 1,
    "RL-PTY-002": 1, "RL-PTY-003": 1, "RL-PTY-004": 1, "RL-PTY-005": 1,
    "RL-AST-001": 1, "RL-AST-002": 1, "RL-AST-003": 1, "RL-OTH-001": 1,
    "RL-OTH-002": 1, "RL-OTH-003": 1, "RL-OTH-004": 1, "RL-OTH-005": 1,
    "RL-OTH-006": 1, "RL-SPT-001": 1, "RL-SPT-002": 1, "RL-SPT-003": 1,
    "RL-SPT-004": 1, "RL-SPT-005": 1, "RL-SPT-006": 1, "RL-SPT-007": 1,
    "RL-SPT-008": 1, "RL-SPT-009": 1, "RL-SPT-010": 1, "RL-SPT-011": 1,
}


def main():
    import importlib.util
    import tempfile

    def load(text_src):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".py",
                                         delete=False, dir=os.path.dirname(SRC)) as tf:
            tf.write(text_src)
            tmp = tf.name
        try:
            spec = importlib.util.spec_from_file_location("rl_load", tmp)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
        finally:
            os.unlink(tmp)

    with open(SRC, encoding="utf-8") as f:
        text = f.read()
    mod = load(text)
    by_id = {r["id"]: r for r in mod.REDLINES}

    merged = {}
    for rid, orig in ORIGINAL_18.items():
        cur = len(by_id[rid].get("constituents") or [])
        n_new = EXTRA_N.get(rid, 0)
        orig_len = cur - n_new
        new_idx = list(range(orig_len, cur))
        merged[rid] = sorted(set(orig) | set(new_idx))
        # 校验原索引 + 新索引均在界内且不出罪
        cons = by_id[rid]["constituents"]
        for i in merged[rid]:
            assert 1 <= i <= cur, "%s 索引 %d 越界(共%d)" % (rid, i, cur)
            assert ("不属于" not in cons[i - 1]) and ("豁免" not in cons[i - 1]), \
                "%s 索引 %d 指向出罪要件" % (rid, i)

    order = ["RL-PTY-002", "RL-FUND-001", "RL-CIT-001", "RL-PTY-004", "RL-SPT-008",
             "RL-SPT-011", "RL-PAY-005", "RL-PTY-003", "RL-INC-002", "RL-AST-003",
             "RL-PAY-002", "RL-PAY-003", "RL-AST-001", "RL-FUND-002", "RL-OTH-003",
             "RL-VAT-002", "RL-VAT-006", "RL-COST-003"]
    parts = ["_DEFAULT_HIT_INDEX = {"]
    parts.append("    # —— 原兜底（外部核验待办 + 关键字匹配型红线），序号对应 constituents 顺序 ——")
    for rid in order:
        if rid in merged:
            parts.append('    "%s": %s,' % (rid, merged[rid]))
    parts.append("    # —— 本轮新增场景追加（逐条判定兜底，序号按 constituents 顺序计算）——")
    for rid in sorted(merged):
        if rid not in order:
            parts.append('    "%s": %s,' % (rid, merged[rid]))
    parts.append("}")
    new_block = "\n".join(parts)

    eng_text = open(ENG, encoding="utf-8").read()
    m = re.search(r"_DEFAULT_HIT_INDEX\s*=\s*\{.*?\n\}", eng_text, re.S)
    assert m, "未找到 _DEFAULT_HIT_INDEX"
    eng_text = eng_text[:m.start()] + new_block + eng_text[m.end():]
    with open(ENG, "w", encoding="utf-8") as f:
        f.write(eng_text)

    print("OK: 重建 _DEFAULT_HIT_INDEX，共 %d 条兜底红线" % len(merged))
    for rid in order:
        print("  %s: %s" % (rid, merged[rid]))


if __name__ == "__main__":
    main()
