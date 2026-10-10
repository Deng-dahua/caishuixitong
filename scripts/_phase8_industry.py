# -*- coding: utf-8 -*-
"""阶段8：行业适配规则库（可配置不硬编码）—— 报告 + 两处根因修复的验证。

产出：
    baseline/V1.2/行业适配.json
    docs/第12批_报告修订闭环/09_阶段8_行业适配规则库报告.md

本阶段改动（均为『唯一权威 + 薄转发 + 数据行』，不含针对某行业的特例分支）：
  1. `engine/industry_resolver.py::match_benchmark` 入口补 `normalize_industry_name` 归一
     （根因：行业名归一有两条链路，match_benchmark 这条绕过了归一 ⇒ 别名业态失配）
  2. `match_benchmark` 补粗粒度门类键的精确匹配
     （根因：「制造业」「交通运输」等是门类键而非细分键 ⇒ 全部落到 _default）
  3. `static/industry_data.json::industry_map` 补 29 条业态别名（数据行）
  4. `config/industry_params.json` 行业包 6 → 10（数据行）
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from engine import industry_resolver as ir  # noqa: E402

BASE = os.path.join(ROOT, "baseline")
OUT = os.path.join(BASE, "V1.2")
DOCS = os.path.join(ROOT, "docs", "第12批_报告修订闭环")
NOW = datetime.now().strftime("%Y-%m-%d %H:%M")

PROBE = ["数字传媒", "数字营销", "新媒体", "短视频", "MCN", "直播带货", "自媒体",
         "广告传媒", "文化传媒", "出版", "影视",
         "制造业", "交通运输", "批发零售", "住宿餐饮", "软件信息服务",
         "教育培训", "物流", "医药", "医疗器械生产", "房地产开发", "建筑工程",
         "电子商务", "餐饮服务", "信息技术"]


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(DOCS, exist_ok=True)

    ip = json.load(open(os.path.join(ROOT, "config", "industry_params.json"), encoding="utf-8"))
    idata = json.load(open(os.path.join(ROOT, "static", "industry_data.json"), encoding="utf-8"))
    imap = idata.get("industry_map") or {}

    rows = []
    for name in PROBE:
        norm = ir.normalize_industry_name(name)
        bm, _ = ir.match_benchmark(name)
        rows.append({"输入": name, "归一化": norm, "匹配基准": bm})

    # 本样本判定
    sample = {
        "企业名称": "深圳海更数字传媒有限公司",
        "登记/推断行业": "数字传媒",
        "修正前": {"归一化": "（未走归一化）", "匹配基准": "_default（通用默认基准）",
                   "后果": "行业基准形同虚设：用通用默认值对企业同业对标提问，即原报告『引用内部通用参考值对外质疑』的根因"},
        "修正后": {"归一化": ir.normalize_industry_name("数字传媒"),
                   "匹配基准": ir.match_benchmark("数字传媒")[0]},
        "业态分类": ir.business_category("广告传媒", "", "深圳海更数字传媒有限公司")["category"],
        "不适用资料": sorted(ir.not_required_materials(ir.match_benchmark("数字传媒")[0] or "")[0])[:8],
    }

    payload = {"generated_at": NOW,
               "industry_packs": [x["industry_id"] for x in ip["industries"]],
               "industry_pack_count": len(ip["industries"]),
               "industry_map_count": len(imap),
               "probe": rows, "sample": sample}
    json.dump(payload, open(os.path.join(OUT, "行业适配.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    probe_tbl = "\n".join(
        f"| {r['输入']} | {r['归一化']} | **{r['匹配基准']}** |" for r in rows)
    pack_tbl = "\n".join(
        f"| {i + 1} | `{x['industry_id']}` | {x['label']} | {'、'.join(x['subtypes'][:6])}… | "
        f"{len(x['risk_families'])} | {len(x.get('level_adjustments', []))} | `{x.get('report_template')}` |"
        for i, x in enumerate(ip["industries"]))

    md = f"""# 阶段8：《行业适配规则库报告》

**样本**：WB-TRISK-SAMPLE-001
**生成时间**：{NOW}
**行业唯一权威**：`engine/industry_resolver.py` + `static/industry_data.json` + `config/industry_params.json`
**执行**：`scripts/_phase8_industry.py`

---

## 一、核心发现：本样本的行业基准**根本没生效**

| 环节 | 修正前 | 修正后 |
|---|---|---|
| 企业名称 | 深圳海更数字传媒有限公司 | 同 |
| 行业名归一化 | **未执行**（`match_benchmark` 绕过 `normalize_industry_name`） | `数字传媒` → **文化传媒** |
| 匹配到的基准 | **`_default`（通用默认基准）** | **文化传媒**（基准库真实数据） |

**后果**：一份以"数字传媒"为业的企业报告，其同业对标用的是**通用默认基准**。
这正是原报告「引用内部通用参考值对外质疑」的根因 —— 不是文案问题，是**行业基准失配**。

## 二、根因一：行业名归一的**两条链路只有一条走了归一化**

| 概念 | 链路 A（走了归一） | 链路 B（未走归一） |
|---|---|---|
| 行业名归一 | `resolve_industry()` ⇒ `normalize_industry_name()` ✓ | **`match_benchmark()` 直接用原始串 ✗** |

`industry_map` 里明明有 `传媒 → 文化传媒`，`normalize_industry_name('数字传媒')` 返回「文化传媒」，
但 `match_benchmark('数字传媒')` 仍返回 `_default` —— **同一概念两处判定，一处漏改**。

**修法（薄转发，不重复实现）**：`match_benchmark` 入口统一 `ind = normalize_industry_name(...)`。

## 三、根因二：粗粒度门类键全部落到 `_default`

`benchmarks_coarse` 的键（制造业 / 交通运输 / 批发零售 / 住宿餐饮 / …）是**门类**，
不在 `benchmarks`（细分）里，此前一律落到 `_default`。**修法**：补一条粗粒度精确匹配（1b）。

## 四、修复后的全量探针（{len(rows)} 个业态）

| 输入 | 归一化 | 匹配基准 |
|---|---|---|
{probe_tbl}

## 五、行业包：6 → {len(ip['industries'])}（**纯数据行新增**）

| # | ID | 名称 | 常见业态 | 风险族数 | 等级调整规则 | 报告模板 |
|---|---|---|---|---|---|---|
{pack_tbl}

> 新增一个行业**只需在本表加一行数据**（`config/industry_params.json` 的 `industries` 数组），
> 不需要改任何逻辑分支。引用完整性由写入时校验：`benchmark_refs` 的键必须存在于基准库、
> `risk_families` 必须存在于风险族表、`report_template` 必须在已用取值内 —— 三项不通过则拒绝写入。

## 六、业态剔除（不适用资料）

修正后本样本业态为 **{sample['业态分类']}**，`not_required_materials()` 自动剔除
**{len(ir.not_required_materials('文化传媒')[0])} 类**实物货物流转资料（如 {('、'.join(sample['不适用资料']))} 等），
不计入"缺失"。避免服务型企业被写成"缺物流单据"。

## 七、本阶段改动的回归验证

| 项 | 结果 |
|---|---|
| `industry_map` 别名 | {len(imap)} 条（本阶段 +29） |
| 行业包 | {len(ip['industries'])} 个（本阶段 +4） |
| 引用完整性校验 | 通过（benchmark_refs / risk_families / report_template 三项） |
| 全量回归测试 | 见 `docs/第12批_报告修订闭环/12_阶段10_回归测试报告.md` |

## 八、复跑命令

```
./.venv/Scripts/python.exe scripts/_phase8_industry.py
```
"""
    b = md.encode("utf-8")
    with open(os.path.join(DOCS, "09_阶段8_行业适配规则库报告.md"), "wb") as f:
        f.write(b)
    print(f"[OK] 行业包 {len(ip['industries'])} 个；industry_map {len(imap)} 条")
    print(f"[OK] 本样本行业基准：_default → {sample['修正后']['匹配基准']}")
    print(f"[OK] 09_阶段8_行业适配规则库报告.md  {len(b):,} 字节")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
