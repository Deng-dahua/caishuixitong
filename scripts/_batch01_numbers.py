# -*- coding: utf-8 -*-
"""第1批文档数字的**唯一产出点**（防"文档手抄数字漂移"）。

## 为什么需要它（用户验收「补做2」的根因）
本轮交付物里出现 6 处数字不一致（测试用例 25/28、passed 1421/1424、耗时 55.94/61.71、
认定要件 445/456、前提条数遗漏、综合疑点要件数 0）。**逐处取证后确认：5 处是我"手抄旧数字"、
1 处是系统计算 bug（已在 `trigger_conditions.classify()` 修）** ——
即**没有任何一处是"模块间统计口径不同"**。根因是**文档数字靠人手抄**，改一次系统就漂一次。

**用法**：文档里凡写数字，一律跑本脚本取；本文档不缓存结论，只打印命令 + 实测值。

```bash
./.venv/Scripts/python.exe scripts/_batch01_numbers.py
```
"""
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CFG = ROOT / "config" / "risk_conditions.json"
REPORT = ROOT / "scripts" / "four_reports" / "company_1_full.json"
TEST = ROOT / "tests" / "test_trigger_determination_separation.py"


def main() -> int:
    print("=" * 78)
    print("① 配置规模（唯一权威 config/risk_conditions.json）")
    c = json.loads(CFG.read_text(encoding="utf-8"))
    risks = c["risks"]
    n_tc = sum(len(r.get("trigger_conditions") or []) for r in risks)
    n_dc = sum(len(r.get("determination_criteria") or []) for r in risks)
    n_pre = sum(1 for r in risks for x in (r.get("determination_criteria") or [])
                if x.get("is_precondition"))
    n_al = sum(1 for r in risks if r.get("aliases"))
    print("  风险指标 %d ｜ 触发条件 %d ｜ 认定要件 %d ｜ 其中前提条 %d ｜ 含 aliases %d"
          % (len(risks), n_tc, n_dc, n_pre, n_al))
    print("  （红线派生 %d + 人工登记 %d）" % (len(risks) - n_al, n_al))

    print("② 产物规模（scripts/four_reports/company_1_full.json）")
    d = json.loads(REPORT.read_text(encoding="utf-8"))
    er = d.get("enterprise_readable_report") or {}
    ps = [p for p in (er.get("confirmed_problems") or []) if isinstance(p, dict)]
    with_blk = [p for p in ps if isinstance(p.get("trigger_determination"), dict)]
    n_crit = sum(len((p.get("trigger_determination") or {}).get("determination_criteria") or [])
                 for p in ps)
    n_hit = sum(1 for p in ps
                if int(((p.get("trigger_determination") or {}).get("trigger_status") or {})
                       .get("hit_count") or 0) > 0)
    print("  疑点 %d ｜ 落结构化块 %d ｜ 触发命中≥1 %d ｜ 认定要件合计 %d"
          % (len(ps), len(with_blk), n_hit, n_crit))
    print("  overall_level = %s" % d.get("overall_level"))
    zero = [p.get("seq") for p in ps
            if not ((p.get("trigger_determination") or {}).get("determination_criteria") or [])]
    print("  认定要件为 0 条的疑点：%s" % (zero or "无"))

    print("③ 测试用例数（唯一权威 = pytest 收集数）")
    r = subprocess.run([sys.executable, "-m", "pytest", str(TEST), "-q", "--collect-only"],
                       cwd=str(ROOT), capture_output=True, text=True)
    tail = [x for x in r.stdout.strip().split("\n") if "test" in x or "selected" in x]
    print("  %s" % (tail[-1] if tail else "(取不到，请手工跑 pytest --collect-only)"))

    print("④ 本次交付物目录的文件数")
    docdir = ROOT / "docs" / "第01批_触发条件与认定要件分离"
    files = sorted(p.name for p in docdir.glob("*.md"))
    print("  %d 份：%s" % (len(files), "、".join(files)))

    print("⑤ Skill 注册表（唯一权威 config/skill_specs.json + engine.skill_registry.validate）")
    from engine import skill_registry as SR          # 延迟导入：避免无谓的启动开销
    sp = json.loads((ROOT / "config" / "skill_specs.json").read_text(encoding="utf-8"))
    print("  Skill 总数 %d ｜ skill_registry.validate() = %r" % (len(sp["skills"]), SR.validate()))

    print("⑥ 门禁规则条数（唯一权威 tools/audit_consistency.py 的 TDS-* 清单）")
    from engine import doc_consistency_core as core
    cat = [r for r in (core.config().get("rule_catalog") or [])]
    print("  TDS 规则 %d 条：%s" % (len(cat), "、".join(str(r.get("id")) for r in cat)))

    if "--full" in sys.argv:
        print("⑦ 全量回归（唯一权威 = pytest 实测；仅在 --full 时执行，耗时约 1 分钟）")
        r2 = subprocess.run([sys.executable, "-m", "pytest", "tests/", "-q"],
                            cwd=str(ROOT), capture_output=True, text=True)
        tail2 = [x for x in r2.stdout.strip().split("\n") if x.strip()]
        print("  %s" % (tail2[-1] if tail2 else "(取不到)"))
    else:
        print("⑦ 全量回归：加 `--full` 参数即运行 `pytest tests/ -q` 并打印同一取值")

    print("=" * 78)
    print("★ 纪律：文档里出现的每个数字，都必须能在本脚本输出里找到同一取值。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
