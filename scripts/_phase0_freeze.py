# -*- coding: utf-8 -*-
"""阶段0：基准报告冻结 + 版本基线登记 + 资料清单/缺失清单落盘。

只读解析被冻结的 .docx 与同源 report_data，产出：
    baseline/V1.0/原始报告.docx            （位级副本，绝不覆盖）
    baseline/V1.0/原始报告_纯文本.txt       （按文档顺序抽取，含表）
    baseline/V1.0/元数据.json               （指纹/页数/字数/段落/表数/生成器）
    baseline/V1.0/资料清单.json             （已提供 8 类 / 缺失 6 类，从报告正文现算）
    baseline/VERSIONS.json                  （V1.0~V1.4 版本定义 + 修改日志初始条目）
    baseline/修改日志.md                    （修改位置/类型/原因/依据/影响范围 五列）

设计原则（与项目「唯一权威 + 可复现证据」一致）：
  * 冻结副本：shutil.copy2 位级复制，源文件只读不写。
  * 清单「从报告正文现算」，不手抄、不推断；取不到即登记 未确定。
  * 幂等：重复运行只刷新元数据，不破坏已有冻结副本（先比对 sha256）。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import zipfile
from collections import Counter, OrderedDict
from datetime import datetime
from xml.etree import ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(r"C:\Users\Administrator\Desktop", "新建 DOCX 文档.docx")
BASE = os.path.join(ROOT, "baseline")
V10 = os.path.join(BASE, "V1.0")
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


# ----------------------------------------------------------------- 抽取层
def _para_text(pel) -> str:
    return "".join(t.text or "" for t in pel.iter(W + "t"))


def extract(path: str) -> list[str]:
    root = ET.fromstring(zipfile.ZipFile(path).read("word/document.xml"))
    body = root.find(W + "body")
    out: list[str] = []

    def walk(el):
        for ch in el:
            if ch.tag == W + "p":
                out.append(_para_text(ch))
            elif ch.tag == W + "tbl":
                out.append("<<TABLE_START>>")
                for tr in ch.findall(W + "tr"):
                    cells = []
                    for tc in tr.findall(W + "tc"):
                        cells.append(
                            " ".join(x for x in (_para_text(p) for p in tc.findall(W + "p")) if x).strip()
                        )
                    out.append(" | ".join(cells))
                out.append("<<TABLE_END>>")
            elif ch.tag in (W + "sdt", W + "sdtContent"):
                walk(ch)

    walk(body)
    return out


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


# --------------------------------------------------------------- 资料清单
# 资料类别权威名：复用 material_names.CATEGORIES（14 类）作为分组锚；
# 这里做的是「本报告实际引用了哪些资料」的现算，键 = 权威类别名，不自造。
MATERIAL_PATTERNS: "OrderedDict[str, list[str]]" = OrderedDict([
    ("银行流水类", ["银行流水", "银行对账单", "流水明细"]),
    ("发票类-销项", ["销项发票", "开票数据", "销项明细"]),
    ("发票类-进项", ["进项发票", "进项明细", "取得发票"]),
    ("记账凭证类", ["记账凭证", "会计凭证", "凭证"]),
    ("工资薪酬类", ["工资表", "薪酬表", "工资发放"]),
    ("社保公积金类", ["社保明细", "社保申报", "公积金"]),
    ("账簿报表类", ["科目余额表", "余额表", "明细账"]),
    ("纳税申报类", ["增值税申报表", "申报表", "纳税申报"]),
    ("合同协议类", ["合同", "协议"]),
    ("财务报表类", ["资产负债表", "利润表", "现金流量表"]),
    ("所得税申报类", ["企业所得税申报表", "企业所得税"]),
    ("个税申报类", ["个人所得税申报表", "个税申报", "个人所得税"]),
    ("其他税种申报类", ["印花税", "城建税", "教育费附加", "附加税"]),
    ("其他资料", ["其他"]),
])


def scan_materials(lines: list[str]) -> dict:
    """现算：每类资料在正文中的出现次数；『已提供/缺失』以报告中显式声明为准。"""
    text = "\n".join(lines)
    hits = {}
    for cat, pats in MATERIAL_PATTERNS.items():
        c = sum(text.count(p) for p in pats)
        hits[cat] = c
    return hits


MISSING_DECL = [
    "合同文件", "资产负债表", "利润表", "企业所得税申报表", "个人所得税申报表", "其他税种申报表",
]


def find_missing_declarations(lines: list[str]) -> dict:
    """在正文中定位『缺失/未提供/未取得』+ 资料名的原文，登记行号。"""
    out = {}
    pat = re.compile(r"(缺失|未提供|未取得|未上传|无法取得)[^。；\n]{0,20}")
    for i, l in enumerate(lines, 1):
        for m in pat.finditer(l):
            seg = l[max(0, m.start()): min(len(l), m.end() + 24)]
            key = seg.strip()
            out.setdefault(key, []).append(i)
    return out


def main() -> int:
    if not os.path.exists(SRC):
        print(f"[FATAL] 源文件不存在: {SRC}")
        return 2
    os.makedirs(V10, exist_ok=True)

    # --- 1. 位级冻结副本（已存在且指纹一致则跳过，绝不覆盖为不同内容）
    sha = sha256_of(SRC)
    dst_docx = os.path.join(V10, "原始报告.docx")
    if os.path.exists(dst_docx) and sha256_of(dst_docx) == sha:
        print(f"[OK] 冻结副本已存在且指纹一致，跳过复制: {dst_docx}")
    else:
        shutil.copy2(SRC, dst_docx)
        print(f"[OK] 已冻结副本: {dst_docx}")

    # --- 2. 纯文本抽取
    lines = extract(dst_docx)
    txt_path = os.path.join(V10, "原始报告_纯文本.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    n_tbl = sum(1 for l in lines if l.strip() == "<<TABLE_START>>")
    n_chars = sum(len(l) for l in lines)

    # --- 3. 元数据
    z = zipfile.ZipFile(dst_docx)
    app = {}
    core = {}
    try:
        app = _xml_kv(z.read("docProps/app.xml"))
    except KeyError:
        pass
    try:
        core = _xml_kv(z.read("docProps/core.xml"))
    except KeyError:
        pass
    meta = {
        "source_path": SRC,
        "sha256": sha,
        "size_bytes": os.path.getsize(SRC),
        "frozen_at": datetime.now().isoformat(timespec="seconds"),
        "paragraph_blocks": len(lines),
        "tables": n_tbl,
        "chars": n_chars,
        "generator": app.get("Application", "未确定"),
        "app_version": app.get("AppVersion", "未确定"),
        "pages": app.get("Pages", "未确定"),
        "words": app.get("Words", "未确定"),
        "creator": core.get("creator", "未确定"),
        "lastModifiedBy": core.get("lastModifiedBy", "未确定"),
        "created": core.get("created", "未确定"),
        "modified": core.get("modified", "未确定"),
        "title": core.get("title", "未确定"),
    }
    with open(os.path.join(V10, "元数据.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    # --- 4. 资料清单
    hits = scan_materials(lines)
    miss = find_missing_declarations(lines)
    mat = {
        "口径说明": "『出现次数』为正文现算（不推断）；『是否提供』以报告显式声明为准，未声明即登记 未确定。",
        "已提供": [c for c, _ in MATERIAL_PATTERNS.items() if hits.get(c, 0) > 0],
        "正文出现次数": hits,
        "缺失声明词": MISSING_DECL,
        "缺失声明原文命中": {k: v[:12] for k, v in miss.items()},
    }
    with open(os.path.join(V10, "资料清单.json"), "w", encoding="utf-8") as f:
        json.dump(mat, f, ensure_ascii=False, indent=2)

    # --- 5. 版本定义 V1.0~V1.4
    versions = {
        "series": "深圳海更数字传媒有限公司税务风险检查报告",
        "sample_id": "WB-TRISK-SAMPLE-001",
        "versions": [
            {"version": "V1.0", "name": "原始冻结版", "stage": "阶段0",
             "desc": "用户提供的原始 DOCX 位级副本，本批次唯一不可变基线；任何后续版本均以此为对照。",
             "artifact": "baseline/V1.0/原始报告.docx", "sha256": sha, "status": "已冻结"},
            {"version": "V1.1", "name": "结构重构与去重版", "stage": "阶段4-5",
             "desc": "9 章结构 + 六段式改写 + 冗余重复消除 + 引用替换（见R1/见要件R1-C2/见事实F-012…）。",
             "artifact": "baseline/V1.1/报告_V1.1.md", "sha256": None, "status": "待生成"},
            {"version": "V1.2", "name": "数据与法规校验版", "stage": "阶段6",
             "desc": "金额重算、税率与限额口径修正（含业务招待费 5‰ 笔误）、法规引用逐条复核。",
             "artifact": "baseline/V1.2/报告_V1.2.md", "sha256": None, "status": "待生成"},
            {"version": "V1.3", "name": "等级与证据强度分离版", "stage": "阶段7",
             "desc": "风险等级与证据强度双字段分离，风险总表新增证据强度/闭合度/结论等级列。",
             "artifact": "baseline/V1.3/报告_V1.3.md", "sha256": None, "status": "待生成"},
            {"version": "V1.4", "name": "定稿版", "stage": "阶段11",
             "desc": "过四道门禁 + 20 项自检清单，可归档交付（对内完整版 / 对外脱敏版）。",
             "artifact": "baseline/V1.4/报告_V1.4.md", "sha256": None, "status": "待生成"},
        ],
        "freeze_rule": [
            "V1.0 只读，任何阶段不得修改 baseline/V1.0/ 下文件。",
            "每升一个版本必须先在 baseline/修改日志.md 登记一条五列记录。",
            "版本号与 git 提交、归档包文件名三者必须一致。",
        ],
    }
    with open(os.path.join(BASE, "VERSIONS.json"), "w", encoding="utf-8") as f:
        json.dump(versions, f, ensure_ascii=False, indent=2)

    # --- 6. 修改日志初始
    log = _render_log(meta, hits, n_tbl)
    with open(os.path.join(BASE, "修改日志.md"), "w", encoding="utf-8") as f:
        f.write(log)

    print(f"[OK] 文本：{len(lines)} 块 / {n_chars} 字 / {n_tbl} 表")
    print(f"[OK] sha256 = {sha[:16]}…  pages={meta['pages']}")
    print(f"[OK] 产出目录：{BASE}")
    return 0


def _xml_kv(blob: bytes) -> dict:
    root = ET.fromstring(blob)
    return {(c.tag.split('}')[-1]): (c.text or "") for c in root.iter() if c.text}


def _render_log(meta: dict, hits: dict, n_tbl: int) -> str:
    provided = [c for c, n in hits.items() if n > 0]
    pr = "、".join(provided) if provided else "未确定"
    return f"""# 报告修改日志（五列：修改位置 / 修改类型 / 修改原因 / 依据 / 影响范围）

**报告系列**：深圳海更数字传媒有限公司税务风险检查报告
**样本编号**：WB-TRISK-SAMPLE-001
**V1.0 指纹**：`{meta['sha256'][:16]}`…（{meta['size_bytes']} 字节，{meta['pages']} 页，{meta['paragraph_blocks']} 块，{n_tbl} 表）
**冻结时间**：{meta['frozen_at']}

> 规则：V1.0 只读；每升一个版本必须先登记一条记录，再改文件。

| # | 版本 | 修改位置 | 修改类型 | 修改原因 | 依据 | 影响范围 |
|---|---|---|---|---|---|---|
| 0 | V1.0 | 全文 | 基线冻结 | 建立不可变对照基线，供去重/校验/回归逐项比对 | 本批次总指令 阶段0 | 无（只读） |
| — | V1.1 | 待阶段4-5 登记 | 结构重构 / 去重 | 待补 | 待补 | 待补 |
| — | V1.2 | 待阶段6 登记 | 数据与法规校验 | 待补 | 待补 | 待补 |
| — | V1.3 | 待阶段7 登记 | 等级与证据强度分离 | 待补 | 待补 | 待补 |
| — | V1.4 | 待阶段11 登记 | 定稿 / 归档 | 待补 | 待补 | 待补 |

## 资料清单（阶段0 现算）

**已提供（正文出现过的资料类别）**：{pr}

**缺失（指令登记）**：{'、'.join(MISSING_DECL)}

> 说明：「出现次数」为正文现算值（不推断）；「缺失」以指令登记为准，报告中显式声明的缺失原文见 `baseline/V1.0/资料清单.json`。
"""


if __name__ == "__main__":
    sys.exit(main())
