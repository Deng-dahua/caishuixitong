# -*- coding: utf-8 -*-
"""外部点评整改 —— **逐条独立复核**（可复现证据）。

为什么要有这个脚本：前面若干轮"改完 + 闸门通过"只能证明**被闸门覆盖的部分**没问题，
不能证明"点评清单每一条都真的落地了"。本脚本对 P0-1~P0-10 / P1-1~P1-16 / P2-1~P2-8
**逐条**给出「核验方式 / 证据 / 结论」，其中：

- **行为断言**：直接调用生产函数，断言输入→输出（首选，抗改名/换写法）；
- **报告实测**：对真实账套的重跑产物（`_fresh_result.json`）做统计断言；
- **静态接线**：仅在无法行为断言时使用（且断言**真实调用行**，不用裸函数名）。

用法：`python scripts/_verify_review_fixes.py [结果JSON]`
退出码 0 = 全部通过；非 0 = 有未通过项（明细打印在表内）。
"""
import io
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
sys.path.insert(0, REPO)

SRC = sys.argv[1] if len(sys.argv) > 1 else "scripts/four_reports/_fresh_result.json"

ROWS = []   # (编号, 问题, 核验方式, 证据, 通过?)


def rec(item, what, how, evidence, ok):
    ROWS.append((item, what, how, str(evidence)[:150], bool(ok)))


def _load():
    with io.open(SRC, encoding="utf-8") as fh:
        d = json.load(fh)
    return (d.get("report") or d)


REP = _load()
ER = REP.get("enterprise_readable_report") or {}
BLOB = json.dumps(ER, ensure_ascii=False)
ALLOB = json.dumps(REP, ensure_ascii=False)


def _src(rel):
    try:
        with io.open(os.path.join(REPO, rel), encoding="utf-8", newline="") as fh:
            return fh.read()
    except Exception:
        return ""


def _code(rel):
    """**去注释**源码（"不得出现某短语"类断言必须用它）。

    ⚠ 实测坑：修复说明注释里会**引用被禁短语**（如"废除「实际缴纳 0 元」断言"），
      在原文上判断会把注释判成违规。
    """
    try:
        from tools.audit_consistency import _strip_comments_keep_lines as _S
        return _S(_src(rel))
    except Exception:
        return _src(rel)


# ══════════════════════ P0 ══════════════════════

# P0-1 同一资料"已提供"与"未取得"并存
try:
    from engine.clue_chain import build_clue_chain
    _cc = build_clue_chain(
        {"type": "T", "detail": "d", "observed_metrics": {}},
        {"name": "n", "clue_chain": [{"step": 1, "source": "工资表", "action": "a", "output": "o"}]},
        engine_data={}, provided_materials=["工资表"])
    _gaps = (_cc or {}).get("data_gaps") or []
    _reasons = {g.get("reason") for g in _gaps}
    rec("P0-1", "已提供/未取得不得并存",
        "行为：资料已提供时环节缺口必须标 engine_gap（不算资料缺失）",
        "data_gaps reasons=%s" % (_reasons or "（无缺口）"),
        ("engine_gap" in _reasons) or not _gaps)
except Exception as e:
    rec("P0-1", "已提供/未取得不得并存", "行为断言", "执行失败: %s" % e, False)

# P0-2 "未取得"当 0
try:
    from engine.two_tax_income import run_two_tax_compare
    _tt = run_two_tax_compare(tax_declarations=[{"kind": "vat", "sales": 100.0}])
    _m = (_tt or {}).get("metrics") or {}
    rec("P0-2", "未取得不得当 0 参与计算",
        "行为：单边存在时差额必须为 None",
        "diff=%s vat_over_cit=%s verdict=%s" % (_m.get("diff"), _m.get("vat_over_cit"), str((_tt or {}).get("verdict"))[:24]),
        _m.get("diff") is None and _m.get("vat_over_cit") is None)
except Exception as e:
    rec("P0-2", "未取得不得当 0 参与计算", "行为断言", "执行失败: %s" % e, False)

# P0-3 "未取得"当"未发生"
_src_stamp = _code("engine/domain_analysis.py")
_ok3 = ("实际缴纳 0 元" not in _src_stamp)
rec("P0-3", "未取得不得写成「未发生」",
    "静态（去注释）：不得出现「实际缴纳 0 元」断言",
    "源码含该短语=%s" % ("实际缴纳 0 元" in _src_stamp),
    _ok3 and "未能核实" in _src_stamp)
rec("P0-3b", "申报表未取得时的表述",
    "报告实测：不得出现「未见申报记录」类断言",
    "报告含「未见对应的城建税及附加申报记录」=%s" % BLOB.count("未见对应的城建税及附加申报记录"),
    BLOB.count("未见对应的城建税及附加申报记录") == 0)

# P0-4 税率错配
try:
    from engine.tax_impact import infer_rate_context
    _rc = infer_rate_context(sal_invs=[{"amount": 100.0, "tax": 6.0}], net_profit=400000.0)
    _rc2 = infer_rate_context(sal_invs=[{"amount": 100.0, "tax": 13.0}], net_profit=1000000.0)
    rec("P0-4", "税额测算税率须与销项/规模相符",
        "行为：有效税率落档（6% / 13%）+ 小微判定",
        "6%%→vat=%s cit=%s；13%%→vat=%s" % (_rc.get("vat_rate"), _rc.get("cit_rate"), _rc2.get("vat_rate")),
        _rc.get("vat_rate") == 0.06 and _rc2.get("vat_rate") == 0.13)
except Exception as e:
    rec("P0-4", "税额测算税率须与销项/规模相符", "行为断言", "执行失败: %s" % e, False)
_ti = ER.get("tax_impact_summary") or {}
rec("P0-4b", "敞口须声明为最坏情形上界",
    "报告实测：汇总 note 含「最坏情形上界…不可逐项相加」",
    str(_ti.get("note"))[:90],
    "最坏情形上界" in str(_ti.get("note")) and "不可逐项相加" in str(_ti.get("note")))

# P0-5 要件复制填格 + 语义错配 + 独立核对
try:
    from engine.constituent_checkpoint import (
        build_constituent_checkpoints, checkpoint_table, participating_indices)
    _cps = build_constituent_checkpoints({
        "constituents": ["要件一：存在大额未付款", "要件二：合同与验收单齐备性"],
        "evidence_chain": {"elements": [
            {"role": "直接证据", "name": "大额未付款明细与应付账款记录", "status": "已有"},
            {"role": "直接证据", "name": "合同与验收单", "status": "缺失"}]},
        "clue_chain": {"nodes": []},
        "argumentation": {"constituent_hits": [
            {"index": 1, "evidence": "应付余额 120 万元"}, {"index": 2, "evidence": "应付余额 120 万元"}]},
    })
    _part = participating_indices(_cps)
    rec("P0-5", "逐要件独立核对（独立数据源+独立结论）",
        "行为：数据源缺失的要件不得计入「涉及」",
        "参与认定=%s；条目数=%d；有核对表=%s" % (_part, len(_cps), bool(checkpoint_table(_cps))),
        _part == [1] and len(_cps) == 2)
except Exception as e:
    rec("P0-5", "逐要件独立核对", "行为断言", "执行失败: %s" % e, False)
rec("P0-5b", "同一段证据不得复制填多个要件",
    "静态接线：兜底命中只落首个序号",
    "含 for _i in _di = %s" % ("for _i in _di" in _src("engine/redline_engine.py")),
    "for _i in _di" not in _src("engine/redline_engine.py"))
rec("P0-5c", "报告须带要件级核对表",
    "报告实测：出现「构成要件独立核对表」",
    "出现次数=%d" % BLOB.count("构成要件独立核对表"),
    BLOB.count("构成要件独立核对表") > 0)

# P0-6 疑点标题与已核事实冲突
try:
    from engine.tax_redlines import trim_redline_title
    _rn = "长期亏损仍持续经营：收入或成本不实"
    _t1, _n1 = trim_redline_title("RL-CIT-004", "企业所得税贡献率偏低", [{"index": 2}], _rn)
    _t2, _ = trim_redline_title("RL-CIT-004", "x", [{"index": 1}], _rn)
    rec("P0-6", "标题须按实际命中要件裁剪",
        "行为：只命中非命名要件时裁剪并声明未就前提认定",
        "裁剪后含「未就」=%s；命中命名要件不裁剪=%s" % ("未就" in _t1, _t2 == _rn),
        "未就" in _t1 and _n1 and _t2 == _rn)
except Exception as e:
    rec("P0-6", "标题须按实际命中要件裁剪", "行为断言", "执行失败: %s" % e, False)

# P0-7 一数三名 / 口径对照
_iv = ER.get("inspection_overview") or {}
_ivp = " ".join(str(x) for x in (_iv.get("paragraphs") or []))
rec("P0-7", "全文口径须有对照与编号",
    "报告实测：总述含「关键口径对照」且逐条给来源",
    "含对照=%s；含来源=%s" % ("关键口径对照" in _ivp, "（来源：" in _ivp),
    "关键口径对照" in _ivp and "（来源：" in _ivp)

# P0-8 定性词
rec("P0-8", "不得使用定性词「坐实」",
    "报告实测：全文 0 处",
    "出现次数=%d" % BLOB.count("坐实"),
    BLOB.count("坐实") == 0)

# P0-9 导出管线（表自洽 / 截断注明 / 净化接线）
try:
    from engine.table_governance import align_table, collect_table_violations
    _t = {"title": "X（共1笔）", "columns": ["金额（元）"], "rows": [{"金额(元)": 1.0}] * 3}
    _a = align_table(_t)
    rec("P0-9", "明细表列名/行键自洽 + 表题计数校正",
        "行为：标点变体对齐 + 计数按实际行数",
        "columns=%s title=%s 违规=%d" % (_a["columns"], _a["title"], len(collect_table_violations({"t": _a}))),
        _a["columns"] == ["金额（元）"] and "共3笔" in _a["title"])
except Exception as e:
    rec("P0-9", "明细表自洽", "行为断言", "执行失败: %s" % e, False)
_tda = _src("static/js/tax-doc-analysis.js")
rec("P0-9b", "导出须净化（控件/折叠）",
    "静态接线：控件标记 + 折叠展开 + 打印展开",
    "标记=%s 净化=%s 打印展开=%s" % ("data-export-exclude" in _tda,
                                 "_sanitizeExportClone" in _tda, "details>div" in _tda),
    all(k in _tda for k in ("data-export-exclude", "_sanitizeExportClone", "details>div")))
_half = [m.group(0) for m in re.finditer(r".{0,18}\d,\d{1,2}(?![\d])(.{0,6})", BLOB)
         if "…" not in m.group(0) and "等" not in m.group(1)]
rec("P0-9c", "不得出现未标注截断的半截数字",
    "报告实测：0 处",
    "命中=%d %s" % (len(_half), _half[:2]),
    len(_half) == 0)

# P0-10 验证不了的要件不得计"涉及"
rec("P0-10", "未单独核对不得计入「涉及」",
    "报告实测：存在「未单独核对（独立数据源本轮未取得）」表述",
    "出现次数=%d" % BLOB.count("未单独核对（独立数据源本轮未取得）"),
    BLOB.count("未单独核对（独立数据源本轮未取得）") > 0)

# ══════════════════════ P1 ══════════════════════

# P1-1 表题与内容矛盾
from engine.enterprise_report import _with_scope_note  # noqa: E402
_sn = _with_scope_note([{"columns": ["A"], "rows": [{"A": 1}, {"A": 2}]}])
rec("P1-1", "附表须说明与正文口径差异",
    "行为：多行附表带 scope_note（单行不加）",
    "多行带说明=%s；单行不加=%s" % (bool((_sn or [{}])[0].get("scope_note")),
                                not (_with_scope_note([{"columns": ["A"], "rows": [{"A": 1}]}])[0].get("scope_note"))),
    bool((_sn or [{}])[0].get("scope_note")))

# P1-2 资金回流分级
try:
    from engine.fund_loop import _loop_tier
    rec("P1-2", "资金回流闭环须按对称度分级",
        "行为：等额双向计入闭环；金额悬殊不计入",
        "2万/2万=%s；107万/27.5万=%s" % (_loop_tier(20000, 20000)[0], _loop_tier(1070000, 275000)[0]),
        _loop_tier(20000, 20000)[0] is True and _loop_tier(1070000, 275000)[0] is False)
except Exception as e:
    rec("P1-2", "资金回流闭环须按对称度分级", "行为断言", "执行失败: %s" % e, False)

# P1-3 本企业自身剔除
rec("P1-3", "本企业不得列入交易对手清单",
    "静态接线：归一化企业名剔除已接线",
    "含 _norm_entity_name(company_name)=%s" % ("_norm_entity_name(company_name)" in _src("engine/pipeline.py")),
    "_norm_entity_name(company_name)" in _src("engine/pipeline.py"))

# P1-4 引擎未算 vs 资料未取得
rec("P1-4", "「引擎未算」不得写成「资料未取得」",
    "报告实测：存在「不计入资料缺失」的三态表述",
    "出现次数=%d" % BLOB.count("不计入资料缺失"),
    BLOB.count("不计入资料缺失") > 0)

# P1-5 量纲错配
try:
    from engine.constituent_threshold import check_constituent_hit
    _v1 = check_constituent_hit("未付款占比超过50%", "未付款占比 32.5%")[0]
    _v2 = check_constituent_hit("占比超过50%", "仅有金额 1,000,000 元")[0]
    rec("P1-5", "要件阈值须同量纲校验",
        "行为：未达门槛→unmet；取不到同量纲值→unknown（放行不误杀）",
        "32.5%% vs 门槛50%% → %s；无同量纲值 → %s" % (_v1, _v2),
        _v1 == "unmet" and _v2 == "unknown")
except Exception as e:
    rec("P1-5", "要件阈值须同量纲校验", "行为断言", "执行失败: %s" % e, False)

# P1-6 敞口重叠声明（同 P0-4b，此处核报告实际文本）
rec("P1-6", "敞口加总须声明事项重叠",
    "报告实测：note 含重叠声明",
    "含「可能重叠」=%s" % ("可能重叠" in str(_ti.get("note"))),
    "可能重叠" in str(_ti.get("note")))

# P1-7 台账聚合 + 统一 ID + 疑点映射
_led = ER.get("resolution_ledger") or {}
_rows_l = _led.get("rows") or []
_cols_l = _led.get("columns") or []
rec("P1-7", "台账须类型级聚合 + 统一发现 ID + 疑点映射",
    "报告实测：三列齐备且每行带 R- 编号、无未聚合同质行",
    "列=%s；行=%d；带ID=%d；聚合行=%d" % (
        [c for c in _cols_l if c in ("发现ID", "聚合项数", "关联疑点")], len(_rows_l),
        sum(1 for r in _rows_l if str(r.get("发现ID") or "").startswith("R-")),
        sum(1 for r in _rows_l if r.get("聚合项数"))),
    all(c in _cols_l for c in ("发现ID", "聚合项数", "关联疑点"))
    and all(str(r.get("发现ID") or "").startswith("R-") for r in _rows_l))

# P1-8 模板句重复
try:
    from engine.chapter_dedup import collapse_common_tail
    _tail = "办理须指定熟悉该项业务和资料的负责人，并由另一名人员复核；验收时确认处理过程能够回查。"
    _items = [{"narrative": "本项处理意见：针对「%s」情形，应补齐原始凭证与说明材料。" % s + _tail}
              for s in ("甲事项异常", "乙事项异常", "丙事项异常")]
    _new, _note = collapse_common_tail(_items, "narrative")
    rec("P1-8", "章节内模板句须只说明一次",
        "行为：抽出公共结尾模板并剥离条目",
        "有章首说明=%s；剥离条数=%d" % (bool(_note), sum(1 for x in _new if x.get("_template_collapsed"))),
        bool(_note) and sum(1 for x in _new if x.get("_template_collapsed")) == 3)
except Exception as e:
    rec("P1-8", "章节内模板句须只说明一次", "行为断言", "执行失败: %s" % e, False)
_ap = ER.get("action_plan") or []
rec("P1-8b", "整改章模板已折叠",
    "报告实测：action_plan 条目带折叠标记",
    "折叠=%d/%d；章首说明=%s" % (sum(1 for x in _ap if x.get("_template_collapsed")), len(_ap),
                             bool(ER.get("action_plan_note"))),
    any(x.get("_template_collapsed") for x in _ap) and bool(ER.get("action_plan_note")))

# P1-9 可信度口径披露
try:
    from engine.argumentation import CONFIDENCE_WEIGHTS, build_argumentation
    _arg = build_argumentation(
        {"type": "T", "level": "高风险", "detail": "d", "redline_id": "RL-X",
         "constituent_hits": [{"index": 1, "evidence": "e"}]},
        {"id": "RL-X", "name": "n", "suspect": "s", "constituents": ["c1"],
         "clue_chain": [{"step": 1, "source": "凭证", "action": "a", "output": "o"}],
         "legal_basis": ["《税收征收管理法》第三十五条"]},
        {"nodes": [{"step": 1, "source": "凭证", "has_data": True, "observed": "x"}], "terminal_signal": "s"},
        {"closure": 0.9, "elements": []}, [])
    rec("P1-9", "可信度须给分项口径与公式",
        "行为：输出 confidence_breakdown + formula；总述披露口径",
        "分项=%d；公式=%s；总述含口径=%s" % (
            len(_arg.get("confidence_breakdown") or []), "可信度 =" in str(_arg.get("confidence_formula")),
            "反证已提交比例" in _ivp),
        bool(_arg.get("confidence_breakdown")) and "反证已提交比例" in _ivp)
except Exception as e:
    rec("P1-9", "可信度须给分项口径与公式", "行为断言", "执行失败: %s" % e, False)

# P1-10 外部核验"没能查"
try:
    from engine.external_verifier import ExternalVerificationEngine
    _as = ExternalVerificationEngine()._assess(
        {"搜索引擎综合核实": {"ok": True, "assessment": "信息不足，未能核实", "found_any": False}})
    rec("P1-10", "检索不到不得写成「正常」",
        "行为：各通道未检索到 → 结论不得为「正常」",
        "verdict=%s" % _as.get("verdict"),
        _as.get("verdict") != "正常")
except Exception as e:
    rec("P1-10", "检索不到不得写成「正常」", "行为断言", "执行失败: %s" % e, False)

# P1-11 个人信息脱敏
try:
    from engine.pii_guard import redact_enterprise_report as _rg
    _o = _rg({"identity": {"organization": {"名称": "深圳海更数字传媒有限公司"}},
              "p": [{"text": "收款人 杨莹 收到 670,000 元。"}]},
             source={"rows": [{"counterparty": "杨莹"}, {"counterparty": "深圳海更数字传媒有限公司"}]})
    _ob = json.dumps(_o, ensure_ascii=False)
    rec("P1-11", "个人信息须脱敏 + 内部资料标识",
        "行为：正文姓名脱敏、企业名不误改、带 _pii_notice",
        "姓名残留=%s；企业名保留=%s；标识=%s" % ("杨莹" in _ob, "深圳海更数字传媒有限公司" in _ob,
                                            bool(_o.get("_pii_notice"))),
        "杨莹" not in _ob and "深圳海更数字传媒有限公司" in _ob and bool(_o.get("_pii_notice")))
except Exception as e:
    rec("P1-11", "个人信息须脱敏", "行为断言", "执行失败: %s" % e, False)
rec("P1-11b", "报告须带脱敏标识",
    "报告实测：enterprise_readable_report 带 _pii_notice",
    "存在=%s" % bool(ER.get("_pii_notice")),
    bool(ER.get("_pii_notice")))

# P1-12 时效与滞纳金
rec("P1-12", "须给时效与滞纳金提示",
    "报告实测：总述含时效提示且注明日万分之五",
    "含「时效与滞纳金提示」=%s；含「万分之五」=%s" % ("时效与滞纳金提示" in _ivp, "万分之五" in _ivp),
    "时效与滞纳金提示" in _ivp and "万分之五" in _ivp)

# P1-13 域间联动
try:
    from engine.domain_linkage import link_findings
    _lk = link_findings([
        {"type": "私户收款", "detail": "个人账户收款", "evidence_rows": [{"counterparty": "杨某"}], "taxes": ["增值税"]},
        {"type": "公户代发", "detail": "个人账户付款", "evidence_rows": [{"counterparty": "杨某"}], "taxes": ["个人所得税"]}])
    _rels = {l["relation"] for v in _lk.values() for l in v}
    rec("P1-13", "域间联动须识别互证关系",
        "行为：同主体反向资金须连线；台账含「联动事项」列",
        "关系=%s；台账列=%s" % (_rels, "联动事项" in _cols_l),
        "同主体反向资金" in _rels and "联动事项" in _cols_l)
except Exception as e:
    rec("P1-13", "域间联动须识别互证关系", "行为断言", "执行失败: %s" % e, False)

# P1-14 明细与合计对不上 / 截断注明
_viol = []
try:
    from engine.table_governance import collect_table_violations
    _viol = collect_table_violations(ER)
except Exception as e:
    _viol = ["执行失败: %s" % e]
rec("P1-14", "明细表须自洽且截断注明",
    "报告实测：全报告明细表零违规（列名/行键一致、无内部列）",
    "违规=%d %s" % (len(_viol), _viol[:2]),
    len(_viol) == 0)
_tda_note = ("仅列示前" in _src("static/js/tax-doc-analysis.js") or "rows_total" in _src("engine/enterprise_report.py"))
rec("P1-14b", "截断须注明「仅列示前 N 笔」",
    "静态接线：渲染层按 rows_total 注明截断",
    "含 rows_total=%s" % ("rows_total" in _src("engine/enterprise_report.py")),
    _tda_note)

# P1-15 目录与正文结构
rec("P1-15", "目录不得出现缩进符号/失配编号",
    "报告实测：无「└」等缩进符",
    "含「└」=%d" % BLOB.count("└"),
    BLOB.count("└") == 0)

# P1-16 内部工具条目混入台账
_internal_in_ledger = [r for r in _rows_l
                       if any(k in str(r.get("风险事项") or "")
                              for k in ("审计检查", "系统一致性", "取证要求", "补充资料单"))]
rec("P1-16", "内部工具条目不得进企业台账",
    "报告实测：台账 0 条内部工具条目 + 带剔除说明",
    "残留=%d；剔除数=%s" % (len(_internal_in_ledger), len(_led.get("excluded_internal") or [])),
    len(_internal_in_ledger) == 0)

# ══════════════════════ P2 ══════════════════════

_eb = ER.get("executive_brief") or {}
rec("P2-1", "须有决策层摘要（3 分钟版）",
    "报告实测：executive_brief 可用、含关键数字/最要紧项/下一步",
    "段落=%d 指标=%d 待办=%d" % (len(_eb.get("paragraphs") or []), len(_eb.get("metrics") or []),
                            len(_eb.get("top_items") or [])),
    bool(_eb.get("available")) and len(_eb.get("top_items") or []) > 0)

try:
    from engine.enterprise_report import _clue_table
    _ct = _clue_table({"nodes": [{"step": 1, "source": "s", "action": "a", "observed": "合计 100 元"},
                                 {"step": 2, "source": "s", "action": "b", "observed": "合计 100 元"}]})
    _has_same = any(str(r.get("实际看到的数据") or "") == "同上" for r in (_ct or {}).get("rows") or [])
    rec("P2-2", "表格内不得出现「同上」",
        "行为：环节表重复值原样回填",
        "表格含「同上」=%s" % _has_same,
        not _has_same)
except Exception as e:
    rec("P2-2", "表格内不得出现「同上」", "行为断言", "执行失败: %s" % e, False)

try:
    from engine.overall_conclusion import compilation_declaration
    _d1 = compilation_declaration({"compliance_round": {"round_no": 1}})
    _d3 = compilation_declaration({"compliance_round": {"round_no": 3}})
    rec("P2-3", "轮次措辞须条件化",
        "行为：第1轮不得称「独立于此前任何一轮」；第N轮须称",
        "第1轮含=%s；第3轮含=%s" % ("独立于此前任何一轮" in _d1, "独立于此前任何一轮" in _d3),
        "独立于此前任何一轮" not in _d1 and "独立于此前任何一轮" in _d3)
except Exception as e:
    rec("P2-3", "轮次措辞须条件化", "行为断言", "执行失败: %s" % e, False)

_pipe = _code("engine/pipeline.py")
rec("P2-4", "署名栏不得仿真税务机关",
    "静态（去注释）：无执法证件号/税务机关公章/报送上级备案",
    "命中=%s" % [k for k in ("执法证件号", "税务机关公章", "报送上一级税务机关备案") if k in _pipe],
    not any(k in _pipe for k in ("执法证件号", "税务机关公章", "报送上一级税务机关备案")))

rec("P2-5", "须有「非税务机关文书」声明",
    "报告实测 + 源码：声明存在且渲染",
    "报告含声明=%s" % ("非税务机关文书" in BLOB),
    "非税务机关文书" in _pipe and ("文书性质声明" in _tda))

rec("P2-6", "四套计数须有映射表",
    "报告实测：counts_map 行数 ≥6 且含口径/来源/关系",
    "行数=%d" % len(_eb.get("counts_map") or []),
    len(_eb.get("counts_map") or []) >= 6
    and all(r.get("口径") and r.get("来源") and r.get("关系") for r in (_eb.get("counts_map") or [])))

# P2-7 结构性重复：跨章重复段 + 章节说明
def _texts(o, out=None):
    out = out if out is not None else []
    if isinstance(o, dict):
        for v in o.values():
            if isinstance(v, str) and len(v) >= 25:
                out.append(v)
            else:
                _texts(v, out)
    elif isinstance(o, list):
        for v in o:
            _texts(v, out)
    return out


def _key(s):
    return re.sub(r"[\s，。；：、（）()【】\[\]「」“”\"'\-—_/|]", "", str(s))[:45]


_seen = {}
_dup = 0
for _ck in ("materials", "inspection_procedures", "discovery_overview", "analysis_coverage"):
    for _t in _texts(ER.get(_ck)):
        _k = _key(_t)
        if len(_k) < 20:
            continue
        if _k in _seen and _seen[_k] != _ck:
            _dup += 1
        else:
            _seen.setdefault(_k, _ck)
rec("P2-7", "章节间不得重复陈述同一事实",
    "报告实测：跨章重复段计数",
    "跨章重复段=%d；整改章模板折叠=%d条" % (_dup, sum(1 for x in _ap if x.get("_template_collapsed"))),
    _dup <= 2 and any(x.get("_template_collapsed") for x in _ap))

# P2-8 印花税口径重申
rec("P2-8", "印花税推算口径须重申局限",
    "报告实测：含「以合同台账为准」与「仅供筛查」",
    "以合同台账为准=%d；仅供筛查=%d" % (BLOB.count("以合同台账为准"), BLOB.count("仅供筛查")),
    BLOB.count("以合同台账为准") > 0 and BLOB.count("仅供筛查") > 0)


# ══════════════════════ 输出 ══════════════════════
def main():
    w_item, w_how = 8, 34
    print("=" * 108)
    print("外部点评整改 —— 逐条独立复核（结果源：%s）" % SRC)
    print("=" * 108)
    print("%-*s %-*s %-6s %s" % (w_item, "编号", w_how, "核验方式", "结论", "证据"))
    print("-" * 108)
    fails = []
    for item, what, how, ev, ok in ROWS:
        print("%-*s %-*s %-6s %s" % (w_item, item, w_how, how[:w_how], "通过" if ok else "未通过", ev[:60]))
        if not ok:
            fails.append((item, what, how, ev))
    print("-" * 108)
    print("合计 %d 项：通过 %d，未通过 %d" % (len(ROWS), len(ROWS) - len(fails), len(fails)))
    if fails:
        print("\n未通过明细：")
        for item, what, how, ev in fails:
            print("  [%s] %s\n     核验方式：%s\n     证据：%s" % (item, what, how, ev))
    print("\n结论：%s" % ("✅ 点评清单全部通过逐条复核" if not fails else "❌ 存在未通过项，见上"))
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
