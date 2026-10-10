# -*- coding: utf-8 -*-
"""普查：全量产物里**译不出中文**的指标键与枚举值（只读，不改任何东西）。

## 为什么要有它
报告「二、发现的依据」会把引擎 `observed_metrics` 逐条列成「中文键=值」。
一旦某个键/枚举值**没登记**进汉化表，它就只剩两条路：
  · 原样漏英文（历史事故：`declared_input_tax_total=192463.32`、`经营模式=b2b_or_unknown`）；
  · 被"未汉化就不写"的守卫静默丢掉（数字消失）。
两条都不好 ⇒ 正确做法是**在汉化表里补一行数据**（同类对象只加数据、不改逻辑分支）。
本脚本把"该补哪几行"一次列全，避免逐次踩坑、也避免只针对某一家企业打补丁。

用法：
    ./.venv/Scripts/python.exe scripts/_audit_unlocalized_metrics.py
    ./.venv/Scripts/python.exe scripts/_audit_unlocalized_metrics.py --json   # 机器可读
"""
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding="utf-8")

ART = os.path.join(ROOT, "scripts", "four_reports", "company_1_full.json")


def _iter_findings(report):
    seen = set()

    def _yield(fs):
        for f in (fs or []):
            if isinstance(f, dict) and id(f) not in seen:
                seen.add(id(f))
                yield f

    for f in _yield(report.get("all_findings")):
        yield f
    comp = report.get("comprehensive") or {}
    for f in _yield((comp.get("scenario_execution") or {}).get("findings")):
        yield f
    for f in _yield((report.get("scenario_execution") or {}).get("findings")):
        yield f
    for dom in (report.get("domain_summary") or []):
        for f in _yield(dom.get("findings")):
            yield f
    for dom in (comp.get("scenario_execution") or {}).get("domain_summary") or []:
        for f in _yield(dom.get("findings")):
            yield f


def main():
    if not os.path.exists(ART):
        print("无产物：%s（先跑一次全量分析）" % ART)
        return 2
    from engine.enterprise_report import _translate_key          # noqa: PLC0415

    with io.open(ART, encoding="utf-8") as fh:
        d = json.load(fh)
    report = d.get("report") if isinstance(d.get("report"), dict) else d

    bad_keys = {}          # 键 → 一个样例值
    bad_enums = {}         # 枚举值 → 出现次数
    for f in _iter_findings(report):
        for k, v in (f.get("observed_metrics") or {}).items():
            if not isinstance(v, (int, float, str, bool)):
                continue
            if re.search(r"[A-Za-z]", str(_translate_key(k))):
                bad_keys.setdefault(k, v)
            if isinstance(v, str) and re.match(r"^[a-z][a-z0-9_]*$", v):
                if re.search(r"[A-Za-z]", str(_translate_key(v))):
                    bad_enums[v] = bad_enums.get(v, 0) + 1

    if "--json" in sys.argv:
        print(json.dumps({"unlocalized_keys": sorted(bad_keys),
                          "unlocalized_enums": sorted(bad_enums)},
                         ensure_ascii=False, indent=1))
        return 0

    print("=" * 74)
    print("未汉化指标键/枚举值普查（产物：%s）" % os.path.basename(ART))
    print("=" * 74)
    if bad_keys:
        print("\n【键】译不出中文 —— 请在 `enterprise_report._METRIC_CN` 各补一行：")
        for k in sorted(bad_keys):
            print("    %-38s 样例值=%r" % (k, bad_keys[k]))
    if bad_enums:
        print("\n【枚举值】译不出中文 —— 请在 `enterprise_report._ENUM_CODE_CN` 各补一行：")
        for k in sorted(bad_enums):
            print("    %-38s 出现 %d 次" % (k, bad_enums[k]))
    if not bad_keys and not bad_enums:
        print("\n  ✓ 全部可汉化（键与枚举值都不含英文残留）")
    print("\n合计：键 %d 个 / 枚举值 %d 个" % (len(bad_keys), len(bad_enums)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
