# -*- coding: utf-8 -*-
"""_audit_boss_report.py 的反向验证（自检）：构造「故意带缺陷」的最小 docx，
确认每条判据真的会报红 —— 防止审计脚本本身出现假绿。

用法：
    ./.venv/Scripts/python.exe scripts/_selfcheck_audit_boss_report.py
退出码：0 = 全部判据有效；1 = 存在未触发的判据（假绿）。

为什么放在 scripts/ 而不是 tests/：
    项目 D1 的 `pytest_collect` 权威值绑定 tests/ 目录的用例总数，
    在 tests/ 新增文件会改变权威值并牵连第01批交付物的判定；自检脚本独立运行即可。
"""
from __future__ import annotations

import importlib.util
import io
import contextlib
import re
import sys
import tempfile
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

HERE = Path(__file__).resolve().parent
MOD_PATH = HERE / "_audit_boss_report.py"


def load_module():
    spec = importlib.util.spec_from_file_location("_audit_boss_report", MOD_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def make_docx(path: Path, paras: list[str], tbls: list[list[list[str]]]) -> None:
    body = [f'<w:p><w:r><w:t xml:space="preserve">{escape(p)}</w:t></w:r></w:p>' for p in paras]
    for tb in tbls:
        rows = "".join(
            "<w:tr>" + "".join(
                f'<w:tc><w:p><w:r><w:t xml:space="preserve">{escape(c)}</w:t></w:r></w:p></w:tc>'
                for c in r) + "</w:tr>"
            for r in tb)
        body.append(f"<w:tbl>{rows}</w:tbl>")
    doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
           "<w:body>" + "".join(body) + "</w:body></w:document>")
    ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
          '<Default Extension="xml" ContentType="application/xml"/>'
          '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
          "</Types>")
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            "</Relationships>")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ct)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", doc)


# 故意造缺陷的样本：每一处缺陷对应一条判据
DEFECTIVE = dict(
    paras=[
        "一、甲章二、乙章（目录里的括注）三、丙章四、丁章",          # 目录：单行连排
        "一、甲章",
        "二、乙章（正文的括注）",                                    # ★ 与目录括注不一致
        "三、丙章",
        "四、丁章",
        "疑点1：有编号项办理顺序：第一项",
        "涉嫌虚列成本。从本次上传资料来看，本企业本项已查明的风险；未认定到构成要件的可能性中等，但能补全尚缺的2项资料来排除此项嫌疑。",
        "一、涉及的风险事项",
        "本项检查需要5项材料，其中名称逐字对应、已确在手上的有2项（a、b），其中3项已提供同类资料（c、d、e）、但与本项范围未逐字对应，须确认是否覆盖。",
        "本项检查共2环，其中第1环因本轮未取得该环节所需资料，未取得数据。",
        "第1环所需资料已在本轮提供、但该环节未产出可展示数据（属检查程序待完善项）。",
        "表1 造缺陷表（合计 100.00 元，来源：X）",
        "疑点2：无编号项",                                            # ★ 缺『办理顺序』
        "从本次上传资料来看，本企业本项已查明的风险的可能性低，且所需资料已齐备。",
        "五、报告性质和使用说明",
        "说明2。要把这一项查清楚，需要：",
        "重复段落检查用句——同名句重复三次以上以确认重复度判据生效。",
        "重复段落检查用句——同名句重复三次以上以确认重复度判据生效。",
        "重复段落检查用句——同名句重复三次以上以确认重复度判据生效。",
    ],
    tbls=[
        [["供应商", "笔数", "金额"], ["甲", "1", "40.00"], ["乙", "1", "10.00"]],   # ★行合计 50.00 ≠ 标题 100.00
        [["", "", ""], ["", "", ""]],                                                # ★空表
        [["供应商", "笔数", "金额"], ["甲", "1", "641509.43"]],                       # ★金额未格式化
    ],
)

# 判据 → 必须命中的输出片段
EXPECT = {
    "[2] 破句/等级缺失": "本企业本项已查明的风险；",
    "[3] 头部≠正文": "★头部2 ≠ 确未提供0",
    "[4] 环级矛盾": "『因本轮未取得该环节所需资料』",
    "[6] 表格加总不符": "★标题合计 100.00 ≠ 列合计 50.00",
    "[7] 空表": "空表头",
    "[9] 目录括注不符": "★括注不一致",
    "[10] 编号断裂": "★ 无编号",
    "[11] 重复段落": "重复段落（>25 字）种类=",
    "[12] 数字未格式化": "未按千分位+两位小数=1",
    "[13] 末章混入": "★ 说明2",
}


def main() -> int:
    mod = load_module()
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "_selfcheck.docx"
        make_docx(p, DEFECTIVE["paras"], DEFECTIVE["tbls"])

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            lines = mod.extract(str(p))
            ts = mod.tables(lines)
            mod.check_scale(lines, ts)
            mod.check_qualification(lines)
            mod.check_headcount_vs_body(lines)
            mod.check_stage_contradiction(lines)
            mod.check_amount_collision(lines)
            mod.check_table_math(lines, ts)
            mod.check_empty_tables(ts)
            mod.check_residue(lines)
            mod.check_doc_counts(lines)
            mod.check_order_numbers(lines)
            mod.check_duplication(lines)
            mod.check_number_format(lines)
            mod.check_tail(lines)
        out = buf.getvalue()

    print("=" * 94)
    print("反向验证：在『故意破坏』的样本上，每条判据是否报红")
    print("=" * 94)
    ok = 0
    for name, needle in EXPECT.items():
        hit = needle in out
        ok += hit
        print(f"  {'PASS' if hit else 'FAIL'}  {name:<18} 需命中 {needle[:44]!r}")
    total = len(EXPECT)
    print(f"\n结果：{ok}/{total} → " + ("全部判据有效（无假绿）" if ok == total else "存在未触发判据，需修判据或样本"))
    return 0 if ok == total else 1


if __name__ == "__main__":
    sys.exit(main())
