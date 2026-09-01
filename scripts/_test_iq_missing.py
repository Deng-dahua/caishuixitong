# -*- coding: utf-8 -*-
"""inspection_questions 缺失型待证联动单元测试（不调用大模型）。

验证：经假设-验证后标 _hypothesis_unconfirmed 的缺失型发现，
会被 inspection_questions 转成具体询问（抛企业自证）；
而良性（已降级、非 unconfirmed）发现不应生成该置疑。
"""
import os, sys
sys.path.insert(0, os.getcwd())
from engine import inspection_questions as IQ


def _c2_unconfirmed():
    return [{
        "type": "零运输费+跨省购销-货物流断裂",
        "score": 9,
        "level": "高风险",
        "description": "企业购销货值达8,327,081元，且交易跨越11个地区（广东、浙江、江苏…）。"
                      "全部流水与发票中运输/物流类支出为0。零运输费意味着货物流物证链完全断裂。",
        "_hypothesis_unconfirmed": True,
        "_hypothesis_note": "缺失型疑点证据不足，转置疑清单待企业自证",
    }]


def _benign():
    # 良性：假设验证降级，非 unconfirmed → 不应生成缺失型置疑
    return [{
        "type": "零运输费+跨省购销-货物流断裂",
        "score": 8,
        "level": "中风险",
        "description": "已提供运输费发票与场地租赁合同。",
        "_hypothesis_unconfirmed": False,
        "_hypothesis_note": "假设验证倾向正常解释，风险降级",
    }]


def main():
    print("=== 测试A：缺失型待证 → 应生成跨省零运费置疑 ===")
    iq = IQ.run_inspection_questions(
        comprehensive={}, company_name="深圳市某实业有限公司",
        data_overview={"missing": []}, unconfirmed_findings=_c2_unconfirmed())
    themes = iq.get("themes", [])
    flat = [q for t in themes for q in t["questions"]]
    print("  主题数:", len(themes), "问题数:", len(flat))
    for t in themes:
        print("    主题:", t["theme"], "级别:", t["severity"])
    assert any("跨省零运费待证" in t["theme"] for t in themes), "未生成跨省零运费置疑主题"
    assert any(any("运单" in m for m in (q.get("materials") or [])) for q in flat), "置疑未要求物流单据"
    assert iq.get("verdict"), "应给出 verdict"
    print("  ✅ 缺失型待证已转企业自证询问")

    print("\n=== 测试B：良性（已降级、非 unconfirmed）→ 不应生成缺失型置疑 ===")
    iq2 = IQ.run_inspection_questions(
        comprehensive={}, company_name="深圳市某实业有限公司",
        data_overview={"missing": []}, unconfirmed_findings=_benign())
    themes2 = iq2.get("themes", [])
    assert not any("待证" in t["theme"] for t in themes2), "良性发现不应生成待证置疑"
    print("  ✅ 良性发现未误生成置疑（无误伤）")

    print("\n全部断言通过 ✅")


if __name__ == "__main__":
    main()
