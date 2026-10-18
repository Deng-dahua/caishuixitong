# -*- coding: utf-8 -*-
"""反向验证：把本轮判据**故意打坏**，确认测试真的变红（不是假判据）。

用法：`.venv/Scripts/python.exe scripts/_reverse_verify_project_profile.py`
每个注入点独立子进程跑（避免 `sys.modules` 缓存导致假绿），跑完**必定还原**。
"""
from __future__ import annotations

import io
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = str(ROOT / ".venv" / "Scripts" / "python.exe")

CASES = [
    (
        "日期归一失效",
        "engine/project_service.py",
        '    return "%04d-%02d-%02d" % (y, mo, d)',
        '    return s  # 注入缺陷：不做归一',
        "tests/test_project_profile_ui.py::ProjectProfileServiceTests"
        "::test_create_persists_profile_and_normalizes_values",
    ),
    (
        "缺项标注失效（恒空）",
        "engine/project_service.py",
        "    missing = [label for key, label in AUDIT_FIELDS\n"
        "               if not (m.get(key) not in (None, \"\", [], ()))]",
        "    missing = []  # 注入缺陷：缺项不再标注",
        "tests/test_project_profile_ui.py::ProjectProfileServiceTests"
        "::test_missing_audit_fields_are_flagged_not_defaulted",
    ),
    (
        "资料页删除按钮复活",
        "static/js/documents.js",
        '<button class="btn ghost" data-act="download" data-id="\' + d.id + \'">下载</button>',
        '<button class="btn ghost" data-act="download" data-id="\' + d.id + \'">下载</button> '
        '<button class="btn danger" data-act="del" data-id="\' + d.id + \'">删除</button>',
        "tests/test_project_profile_ui.py::FrontendContractTests"
        "::test_documents_has_no_row_delete_button",
    ),
    (
        "侧边栏文案回退",
        "static/index.html",
        "<span class=\"icon\">📂</span> 稽查项目管理",
        "<span class=\"icon\">📂</span> 稽查项目\n",
        "tests/test_project_profile_ui.py::FrontendContractTests::test_sidebar_label_renamed",
    ),
    (
        "权限登记悬挂（入口被删但配置仍登记）",
        "static/documents.html",
        '<button class="btn danger" id="btn-del-selected"',
        '<button class="btn danger" id="btn-del-selected-renamed"',
        "tests/test_project_profile_ui.py::FrontendContractTests"
        "::test_frontend_perm_config_has_no_dangling_entries",
    ),
]


def main() -> int:
    ok = 0
    for name, rel, old, new, node in CASES:
        path = ROOT / rel
        original = io.open(path, encoding="utf-8").read()
        if old not in original:
            print("[跳过] %s：锚点不存在（%s）" % (name, rel))
            continue
        if old == new:
            print("[跳过] %s：注入与原状相同，不可能触发" % name)
            continue
        try:
            io.open(path, "w", encoding="utf-8").write(original.replace(old, new, 1))
            proc = subprocess.run([PY, "-m", "pytest", node, "-q"],
                                  cwd=str(ROOT), capture_output=True, text=True)
            red = proc.returncode != 0
            print("[%s] %s → %s" % ("通过" if red else "★假判据★", name,
                                    "测试变红" if red else "测试仍绿（判据无效）"))
            if red:
                ok += 1
        finally:
            io.open(path, "w", encoding="utf-8").write(original)
    print("\n反向验证：%d/%d 注入点成功触发红灯" % (ok, len(CASES)))
    return 0 if ok == len(CASES) else 1


if __name__ == "__main__":
    sys.exit(main())
