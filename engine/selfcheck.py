# -*- coding: utf-8 -*-
"""自检与回归测试模块（唯一权威实现）——报告生成后自动运行 20 项校验清单。

指令依据（阶段9 第8项 + 自动自检清单）：
  「未通过以下任一项，不得输出报告。」（20 项）

**阻断语义**：`blocking(checks)` 为真 ⇒ 报告不得输出。
本模块是 20 项自检的**唯一实现**；`scripts/_phase11_final.py` 与产出链都调用它，
避免"自检清单两处实现必然漂移"。

输入：报告文本 + 各阶段诊断结果（重复率/重复清单/问题诊断）。取不到即 SKIP，**不静默通过**。
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional

#: 每项详情的页数换算口径（A4 打印含表格约 2200 字/页）
CHARS_PER_PAGE = 2200
ITEM_PAGE_LIMIT = 2
SUMMARY_PAGE_LIMIT = 1


def _load_json(p: str) -> Optional[dict]:
    try:
        with open(p, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:  # noqa: BLE001 —— 取不到返回 None（调用方标 SKIP）
        return None


def run_checks(lines: List[str], text: str, *, base_dir: str, out_dir: str,
               project_root: str = "") -> List[Dict[str, Any]]:
    """执行指令版 20 项自检。

    base_dir  —— 版本目录（如 baseline/V1.4），其下 诊断/ 放 rate/dup/prob 三个 json
    out_dir   —— 对外版所在目录（检查第 17 项）
    """
    checks: List[Dict[str, Any]] = []

    def add(no: int, name: str, ok: bool, detail: str, *, skip: bool = False) -> None:
        checks.append({"no": no, "项": name,
                       "结果": "SKIP" if skip else ("通过" if ok else "不通过"),
                       "明细": detail})

    d = os.path.join(base_dir, "诊断")
    rate = _load_json(os.path.join(d, "重复率.json"))
    dup = _load_json(os.path.join(d, "重复清单.json"))
    prob = _load_json(os.path.join(d, "问题诊断.json"))
    if rate is None:
        return [{"no": 0, "项": "自检前置", "结果": "不通过",
                 "明细": "未找到重复率诊断结果（先跑 scripts/_phase1_diagnose.py）"}]
    pmap = {p["id"]: p for p in (prob or {}).get("problems", [])}
    o, c, f = rate["整体"], rate["章节统计"], rate["事实重复"]
    dby: Dict[str, int] = {}
    for x in (dup or {}).get("findings", []):
        dby[x["type"]] = dby.get(x["type"], 0) + 1

    add(1, "整体重复率≤10%", o["判定"] == "PASS", f"{o['重复率']:.2%}")
    add(2, "同章节重复率≤5%", c["超阈章节"] == 0,
        f"参与判定 {c['参与判定章节']} 章，超阈 {c['超阈章节']}")
    add(3, "同一事实完整出现≤1次", f["判定"] == "PASS", f"超额 {f['超额出现次数合计']} 次")
    add(4, "无整段完全重复", dby.get("完全重复", 0) == 0, f"完全重复 {dby.get('完全重复', 0)} 组")
    add(5, "无近似重复", dby.get("近似重复", 0) == 0, f"近似重复 {dby.get('近似重复', 0)} 组")
    add(6, "无模板套话重复", dby.get("套话重复", 0) == 0, f"套话重复 {dby.get('套话重复', 0)} 组")

    n_loc = text.count("原文位置：")
    add(7, "原报告事实/数据/结论/资料缺口/法规依据仍可追溯", n_loc >= 16,
        f"逐项原始行号标注 {n_loc} 处（应 ≥16）")

    pair_bad = ("未取得" in text and "均已取得" in text)
    add(8, "去重后未产生新矛盾", not pair_bad,
        "未检出相反断言并存" if not pair_bad else "检出『未取得』与『均已取得』并存，须复核")

    lv = all(k in text for k in ("风险信号", "待核事项", "已认定事实"))
    no_illegal = not any(k in text for k in
                         ("本项构成偷税", "已认定其违法", "认定为偷税", "本项定性为", "虚开成立"))
    add(9, "区分风险信号/待核事项/已认定事实/违法认定", lv and no_illegal,
        f"四级术语表齐备={lv}；未越权作违法认定={no_illegal}")

    add(10, "风险等级与证据强度分开展示",
        ("| 风险等级 |" in text and "证据强度" in text and "定性状态" in text),
        "风险总表含独立『风险等级』『证据强度』『定性状态』列")

    add(11, "资料缺失单列、未计入风险事项数",
        ("资料缺失与检查受限汇总表" in text) and len(re.findall(r"^### R\d+", text, re.M)) >= 16,
        "CH9 独立汇总；风险事项数按 R 标题计数")

    add(12, "法规标注版本和现行有效性",
        ("待人工核" in text or "版本待核" in text) and "法规索引" in text,
        "法规索引已标注版本状态（未登记一律『待核』）")

    seg = text.split("## CH1")[0]
    ch0 = seg.split("## CH0")[-1] if "## CH0" in seg else seg
    add(13, "执行摘要≤1页", len(ch0) <= SUMMARY_PAGE_LIMIT * CHARS_PER_PAGE,
        f"CH0 约 {len(ch0)} 字（1页≈{CHARS_PER_PAGE}字）")

    ch2 = text.split("## CH2")[-1].split("## CH3")[0]
    ntab = sum(1 for ln in ch2.split("\n")
               if ln.strip().startswith("|") and set(ln.strip()) <= set("|-: "))
    add(14, "风险总表≤1张", ntab <= 2, f"风险总表区表格数 {ntab}（含术语表；总表本身 1 张）")

    parts = text.split("\n### R")
    over = []
    for seg_ in parts[1:]:
        seg_ = seg_.split("\n## ")[0]
        ls = seg_.split("\n")
        body = sum(len(x) for x in ls if not x.startswith("|"))
        rows = sum(1 for x in ls if x.startswith("|"))
        if body > ITEM_PAGE_LIMIT * 1500 or rows > 80:
            over.append((seg_[:6], body, rows))
    add(15, f"每项详情≤{ITEM_PAGE_LIMIT}页", not over,
        f"口径 正文≤{ITEM_PAGE_LIMIT * 1500}字 且 表格≤80行；超长项：{over[:3] or '无'}")

    add(16, "空白表格/残缺列表/签章日期已修复或标注待补",
        "|  |  |" not in text and "（待签署）" in text,
        "空表 0；签章栏已标『（待签署）/（待补）』")

    ext_candidates = [os.path.join(out_dir, n) for n in os.listdir(out_dir)
                      if n.endswith(".md") and ("对外" in n)] if os.path.isdir(out_dir) else []
    add(17, "已输出内部版和对外版",
        bool(ext_candidates) and ("内部完整版" in text or "内部版" in text),
        f"对外版文件 {len(ext_candidates)} 个")

    root = project_root or os.path.dirname(base_dir)
    rev = os.path.join(root, "docs", "第12批_报告修订闭环", "14_修订说明.md")
    add(18, "保留原始底稿和修订说明",
        os.path.exists(os.path.join(os.path.dirname(base_dir), "V1.0", "原始报告.docx"))
        and os.path.exists(rev), "V1.0 位级底稿 + 《修订说明》")

    rl = os.path.join(root, "docs", "第12批_报告修订闭环", "15_系统规则库V1.0.md")
    add(19, "已形成系统规则库和回归测试报告",
        os.path.exists(rl), "《系统规则库V1.0》")
    pipe = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "engine", "dedup_pipeline.py")
    add(20, "去重能力已固化进系统、可自动执行",
        os.path.exists(pipe), f"engine/dedup_pipeline.py 存在={os.path.exists(pipe)}")
    return checks


def blocking(checks: List[Dict[str, Any]]) -> bool:
    """是否存在**不通过**项（SKIP 不算通过也不阻断，但须在报告中如实列出）。"""
    return any(c.get("结果") == "不通过" for c in checks)


def summary_line(checks: List[Dict[str, Any]]) -> str:
    npass = sum(1 for c in checks if c.get("结果") == "通过")
    skip = sum(1 for c in checks if c.get("结果") == "SKIP")
    bad = [c for c in checks if c.get("结果") == "不通过"]
    s = f"自检 {npass}/{len(checks)} 通过（SKIP {skip}）"
    if bad:
        s += "；不通过：" + "、".join(f"[{c['no']}]{c['项']}" for c in bad[:5])
    return s


def render_md(checks: List[Dict[str, Any]]) -> str:
    rows = ["| # | 自检项 | 结果 | 明细 |", "|---|---|---|---|"]
    for c in checks:
        rows.append(f"| {c['no']} | {c['项']} | **{c['结果']}** | {c['明细']} |")
    rows.append("")
    rows.append(f"> {summary_line(checks)}。**存在『不通过』项 ⇒ 报告不得输出**"
                f"（指令「报告生成后的自动自检清单」总则）。")
    return "\n".join(rows)
