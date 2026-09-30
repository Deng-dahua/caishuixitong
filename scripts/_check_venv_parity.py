# -*- coding: utf-8 -*-
"""托管 venv 能力对齐核对（防止「脚本侧漏读文件」这类静默缺陷复发）。

背景（根因，非特例）：
  项目有两套 Python 环境——
    · 项目自带 `.venv`：App（uvicorn/main.py）真实运行时，按 `requirements.lock` 装齐。
    · 托管 venv（envs/default）：所有 import main 的诊断脚本/测试/全量核对使用。
  二者的**能力必须一致**；否则同一份上传资料在 App 里读得到、在诊断脚本里读不到，
  端到端验收就会「少算」而不报错（历史实例：托管 venv 缺 xlrd → 12 个 .xls 工资表全部读不到，
  且是静默的；缺 python-docx/python-pptx/pytesseract → .docx/.pptx/扫描件 PDF 会同样静默漏读）。

判定口径（刻意区分严重度，避免误报噪音）：
  · MISSING（ERROR）——`requirements.lock` 声明、托管 venv 未安装的「读取/解析类」依赖。
    这是真正的能力缺口，会让脚本侧静默漏读资料，必须补装。
  · VERSION-DRIFT（INFO）——已安装但版本与 lock 不同。托管 venv 允许比 lock 更新
    （fastapi 0.141 vs 0.115 等为已知有意差异），不视为缺陷，仅提示。
  · EXTRA（INFO）——托管 venv 装了但 lock 未声明的包，不处理。

退出码：存在 MISSING → 1；否则 0。
用法：C:/Users/Administrator/.workbuddy/binaries/python/envs/default/Scripts/python.exe scripts/_check_venv_parity.py
"""
from __future__ import annotations

import os
import re
import sys
import importlib.metadata as md

# 「读取/解析/生成」类依赖：缺了会直接影响资料能否被读入/报告能否产出，属 ERROR 级。
# 新增同类库时在此加一行即可（不改逻辑分支）。
_CAPABILITY_CRITICAL = {
    "xlrd", "openpyxl", "xlsxwriter", "pandas",
    "python-docx", "python-pptx", "pdfplumber", "pypdf",
    "pillow", "pytesseract", "reportlab", "lxml",
}

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCK = os.path.join(ROOT, "requirements.lock")


def _norm(name: str) -> str:
    return name.strip().lower().replace("_", "-")


def _parse_lock(path: str) -> dict:
    declared = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = re.match(r"^([A-Za-z0-9_.\-]+)==([^\s;]+)", line)
            if m:
                declared[_norm(m.group(1))] = m.group(2)
    return declared


def main() -> int:
    if not os.path.exists(LOCK):
        print(f"[SKIP] 未找到 {LOCK}")
        return 0

    declared = _parse_lock(LOCK)
    missing_critical, missing_other, drift = [], [], []
    for name, ver in sorted(declared.items()):
        try:
            have = md.version(name)
        except Exception:
            (missing_critical if name in _CAPABILITY_CRITICAL else missing_other).append((name, ver))
            continue
        if have != ver:
            drift.append((name, ver, have))

    print(f"requirements.lock 声明 {len(declared)} 个包")
    print(f"  MISSING(读取/解析类·ERROR) : {len(missing_critical)}")
    for n, v in missing_critical:
        print(f"      XX {n} (lock={v})  ← 会导致脚本侧静默漏读，必须补装")
    print(f"  MISSING(其他·WARN)         : {len(missing_other)}")
    for n, v in missing_other:
        print(f"      !  {n} (lock={v})")
    print(f"  VERSION-DRIFT(INFO)        : {len(drift)}")
    for n, v, h in drift:
        print(f"      ~  {n}: lock={v} have={h}")

    if missing_critical:
        print("\n[FAIL] 托管 venv 存在能力缺口 → 脚本侧分析与 App 口径不一致，请补装上述依赖。")
        return 1
    print("\n[OK] 托管 venv 与 requirements.lock 能力对齐（无读取/解析类缺口）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
