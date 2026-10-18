# -*- coding: utf-8 -*-
"""GAP-13 字段映射域隔离（2026-10-18）。

事故（差距清单原文）：`counterparty` 写成品名；`tx_date` 挂 bank 域；
银行流水混入 `invoice_amount`。

根因两条，都在"映射面"上：
  ① `config/standard_fields.json` 里 `counterparty.aliases_from` 指向
     `fieldkit.BANK_TX_TEXT_KEYS` —— 那是**拼接流水可读文本**用的字段清单，
     含「摘要/用途/备注」与「goods/货物或应税劳务名称」⇒「对手方」在发票表里
     取到品名、在账簿里取到摘要。
  ② `extract_service._other_domain_hits()` 是**无上界**的跨域登记：任何域的
     字段只要行里取到值就登记 ⇒ 银行流水的「金额」被登记成发票域「不含税金额」，
     账簿的「记账日期」/发票的「日期」被登记成银行域「交易日期」。

修复口径（唯一实现 `standard_fields.cross_domain_hits`）：
  · 已知域（ledger/invoice/bank/report/declaration/payroll）**不许跨域**登记；
  · 只有「资料类型无对应域」（合同/协议/档案等）才允许按白名单跨域；
  · 跨域命中只能凭**该字段独有的别名**，共用别名（日期/金额/税额/借方发生额/摘要）
    **一律不作依据**（宁缺勿错）；
  · 必填字段只按**本表所在域**要求，不为别的域强加必填缺失。
"""
from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from engine import fieldkit as _FK                                   # noqa: E402
from engine import standard_fields as SF                             # noqa: E402
from engine.extract_service import _domain_of, _registered_names     # noqa: E402

#: 真实导出形态的样例行（列名按真实发票/流水/账簿导出取）
INVOICE_ROWS = [{
    "发票代码": "044001900111", "发票号码": "18765432", "开票日期": "2024-03-15",
    "购方名称": "深圳市海更科技有限公司", "销方名称": "东莞市恒达钢材有限公司",
    "货物或应税劳务名称": "热轧钢板", "金额": 100000.00, "税率": "13%",
    "税额": 13000.00, "价税合计": 113000.00,
}]
BANK_ROWS = [{
    "交易日期": "2024-03-20", "对方户名": "东莞市恒达钢材有限公司", "摘要": "货款",
    "金额": 113000.00, "借方金额": 113000.00, "贷方金额": 0.00, "余额": 552340.12,
}]
LEDGER_ROWS = [{
    "记账日期": "2024-03-15", "凭证号": "记-0012", "科目编码": "6001",
    "科目名称": "主营业务收入", "摘要": "销售钢材",
    "借方发生额": 0.00, "贷方发生额": 100000.00,
}]
CONTRACT_ROWS = [{
    "合同编号": "HT-2024-007", "对方单位": "东莞市恒达钢材有限公司",
    "金额": 113000.00, "签订日期": "2024-03-01",
}]
#: ★ 关键样例：未知域资料里出现**裸「日期」列**。`「日期」` 同时被
#: `invoice_date` 与 `tx_date` 声明 ⇒ 属**共用别名**，跨域时不得作为命中依据。
#: 旧口径下这条会同时登记成「开票日期」和「交易日期」（同一列被当两个语义）。
CONTRACT_DATED_ROWS = [{
    "合同编号": "HT-2024-008", "对方单位": "东莞市恒达钢材有限公司",
    "日期": "2024-03-01",
}]


def _hits(rows, doc_type):
    """`{字段名: 取到的值}`（只含真取到值的字段）。"""
    out = {}
    for n in _registered_names(rows, doc_type):
        v = SF.value_from_row(n, rows[0])
        if v not in (None, ""):
            out[n] = v
    return out


class TestNoCrossDomainLeak:
    """① 三个串域症状必须都不再出现。"""

    def test_invoice_counterparty_is_not_goods(self):
        h = _hits(INVOICE_ROWS, "purchase_invoice")
        assert "counterparty" not in h, "发票表的品名被登记成对手方：%r" % h.get("counterparty")
        assert h.get("goods") == "热轧钢板"

    def test_bank_has_no_invoice_amount(self):
        h = _hits(BANK_ROWS, "bank_statement")
        assert "invoice_amount" not in h, "流水金额被登记成发票不含税金额：%r" % h.get("invoice_amount")
        assert "invoice_total" not in h
        assert h.get("debit") == 113000.0

    def test_tx_date_only_on_bank(self):
        assert "tx_date" in _hits(BANK_ROWS, "bank_statement")
        assert "tx_date" not in _hits(INVOICE_ROWS, "purchase_invoice")
        assert "tx_date" not in _hits(LEDGER_ROWS, "ledger")
        # 非银行资料自己的日期必须还在（不能为了隔离把真字段一起挡掉）
        assert _hits(INVOICE_ROWS, "purchase_invoice").get("invoice_date") == "2024-03-15"
        assert _hits(LEDGER_ROWS, "ledger").get("voucher_date") == "2024-03-15"

    def test_ledger_counterparty_is_not_summary(self):
        h = _hits(LEDGER_ROWS, "ledger")
        assert "counterparty" not in h, "账簿摘要被登记成对手方：%r" % h.get("counterparty")
        assert h.get("summary") == "销售钢材"

    def test_declaration_tax_payable_not_on_invoice(self):
        h = _hits(INVOICE_ROWS, "purchase_invoice")
        assert "tax_payable" not in h, "发票税额被登记成申报域应纳税额"
        assert h.get("invoice_tax") == 13000.0


class TestLegitimateCrossDomainPreserved:
    """② 隔离不得把「未知域资料取发票/银行字段」这条合法通路堵死。"""

    def test_unknown_domain_can_still_take_whitelisted(self):
        h = _hits(CONTRACT_ROWS, "contract")
        assert _domain_of("contract") == ""
        assert "counterparty" in h, "合同「对方单位」应能登记为对手方"
        assert h["counterparty"] == "东莞市恒达钢材有限公司"

    def test_unknown_domain_uses_exclusive_alias_only(self):
        # 合同只有「金额」「签订日期」—— 金额类字段**一律不进跨域白名单**
        # （「金额」在发票域=不含税金额，在合同里=合同总价，口径不同 ⇒ 不得等同）
        h = _hits(CONTRACT_ROWS, "contract")
        assert "invoice_amount" not in h, "跨域不得把合同「金额」记成发票不含税金额"
        assert "salary_pay" not in h
        assert "tx_date" not in h, "合同「签订日期」不是银行交易日期"

    def test_shared_alias_cannot_trigger_cross_domain(self):
        """★ 共用别名（「日期」被 invoice_date 与 tx_date 同时声明）跨域**不得**命中。

        这是反向验证抓出来的判据缺口：只测「金额」测不到这一条，
        必须给一个**带裸「日期」列的未知域资料**才触发。
        """
        h = _hits(CONTRACT_DATED_ROWS, "contract")
        assert "tx_date" not in h, "共用别名「日期」被当作银行交易日期：%r" % h.get("tx_date")
        assert "invoice_date" not in h, "共用别名「日期」被当作开票日期：%r" % h.get("invoice_date")
        assert h.get("counterparty") == "东莞市恒达钢材有限公司"


class TestIsolationContract:
    """③ 规则本身的自洽性（防"白名单被悄悄放宽"）。"""

    def test_known_domains_have_empty_allowlist(self):
        for d in ("ledger", "invoice", "bank", "report", "declaration", "payroll", "common"):
            assert SF.cross_domain_allowed(d) == (), "%s 域不应允许跨域登记" % d

    def test_unknown_domain_allowlist_non_empty(self):
        assert SF.cross_domain_allowed(""), "未知域必须能按白名单跨域"

    def test_counterparty_has_own_alias_source(self):
        f = SF.field("counterparty") or {}
        assert f.get("aliases_from") == "COUNTERPARTY_KEYS"
        # 旧指向是"拼接流水文本"的清单，含品名 ⇒ 必须不是它
        assert f.get("aliases_from") != "BANK_TX_TEXT_KEYS"
        assert "货物或应税劳务名称" not in SF.aliases_of("counterparty")
        assert "摘要" not in SF.aliases_of("counterparty")

    def test_counterparty_keys_are_semantic(self):
        assert "对手方" in _FK.COUNTERPARTY_KEYS
        for bad in ("summary", "摘要", "goods", "货物或应税劳务名称", "remark", "备注"):
            assert bad not in _FK.COUNTERPARTY_KEYS, "对手方清单混入了「%s」" % bad

    def test_shared_aliases_not_usable_for_crossing(self):
        shared = set(SF.shared_aliases())
        for a in ("日期", "date", "amount", "税额", "借方发生额", "凭证日期"):
            assert a in shared, "「%s」应被识别为共用别名" % a
        # 「摘要」修好之后只属 summary 一个字段（旧口径下它同时属 counterparty）
        assert "摘要" not in shared
        assert SF.alias_owners().get("摘要") == ["summary"]
        for n in SF.field_names():
            for a in SF.exclusive_aliases(n):
                assert a not in shared
        for n in ("tx_date", "counterparty"):
            assert "摘要" not in SF.exclusive_aliases(n)
            assert "日期" not in SF.exclusive_aliases(n)

    def test_amount_fields_not_cross_domain(self):
        """金额类字段的口径依赖所在域 ⇒ 一律不许跨域（防「合同金额」当「不含税金额」）。"""
        allow = set(SF.cross_domain_allowed(""))
        amount_like = {str(f.get("name")) for f in SF.fields()
                       if str(f.get("type")) == "amount"
                       and str(f.get("domain")) != "common"}
        leaked = sorted(allow & amount_like)
        assert not leaked, "金额类字段混入跨域白名单：%s" % leaked

    def test_registered_names_required_only_in_own_domain(self):
        # 发票表不因"账簿域必填"而虚报 account_code/account_name 缺失
        names = set(_registered_names(INVOICE_ROWS, "purchase_invoice"))
        assert "invoice_no" in names and "buyer" in names and "seller" in names
        assert "account_code" not in names
        assert "tax_type" not in names

    def test_no_second_implementation_left(self):
        """`_other_domain_hits`（无上界跨域）必须已删除，不得留第二套实现。"""
        import engine.extract_service as ES
        assert not hasattr(ES, "_other_domain_hits"), \
            "无上界跨域实现 _other_domain_hits 仍在 ⇒ 存在两套口径"
