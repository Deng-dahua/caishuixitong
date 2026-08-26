# -*- coding: utf-8 -*-
"""跨企业能力集成验证（第四阶 P1 验证空洞补齐）。

目的：证明「跨企业图谱为空」不再是死代码——
  1) run_cross_enterprise_analysis 能从真实形状的多企业发票往来建出非空图谱（含高风险关系）；
  2) run_fund_loop_check 的「三角/关联闭环」分支在关联组上真正命中；
  3) run_false_invoice_check 的「跨企业图谱高风险关联」信号在图谱非空时真正命中。

用 stub DB 真实驱动跨企业图谱引擎（不手搓 dict），其余数据按真实字段结构构造。
运行：python scripts/integration_multienterprise.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.cross_enterprise_graph import run_cross_enterprise_analysis
from engine.fund_loop import run_fund_loop_check
from engine.false_invoice import run_false_invoice_check

# ───────────────────────────── 让跨企业引擎在「未装 sqlalchemy」环境下也能真跑 ─────────────────────────────
# run_cross_enterprise_analysis 在方法内 `from database import Company`，而 database.py 依赖 sqlalchemy。
# 托管 Python 未装 sqlalchemy，故把 database 模块 monkeypatch 成桩：提供模型占位类，并给
# PurchaseInvoice/SalesInvoice 配一个支持 `==` 比较的占位列 company_id，使引擎的
# `.filter(PurchaseInvoice.company_id == X)` 能产出可被桩 query 解析的过滤表达式，从而按企业正确取数。
import sys as _sys
import types as _types


class _Col:
    """占位列，支持 == 比较以产出可被桩 query 解析的过滤表达式。"""

    def __init__(self, name):
        self.name = name

    def __eq__(self, other):
        return _Expr(self, other)


class _Expr:
    def __init__(self, left, right):
        self.left = left
        self.right = right


_database_stub = _types.ModuleType("database")


class Company:
    pass


class PurchaseInvoice:
    company_id = _Col("company_id")


class SalesInvoice:
    company_id = _Col("company_id")


_database_stub.Company = Company
_database_stub.PurchaseInvoice = PurchaseInvoice
_database_stub.SalesInvoice = SalesInvoice
_sys.modules["database"] = _database_stub


# ───────────────────────────── 合成多企业数据 ─────────────────────────────
# 四家企业：A=被分析企业；B、C 共享同一法定代表人（构成关联组）；D=独立对手方（做直接闭环）
A_NAME = "云链科技（深圳）有限公司"
B_NAME = "宏远供应链管理有限公司"
C_NAME = "恒通建材贸易有限公司"
D_NAME = "鑫源实业有限公司"

SHARED_SUPPLIER_1 = "华强电子有限公司"
SHARED_SUPPLIER_2 = "东信材料有限公司"


class _Company:
    def __init__(self, cid, name, legal_rep, shareholders=None, directors=None, supervisors=None):
        self.id = cid
        self.name = name
        self.legal_representative = legal_rep
        self.shareholders = shareholders or []
        self.directors = directors or []
        self.supervisors = supervisors or []


class _Named:
    def __init__(self, name):
        self.name = name


class _PInv:
    def __init__(self, company_id, seller_name):
        self.company_id = company_id
        self.seller_name = seller_name
        self.seller = seller_name


class _SInv:
    def __init__(self, company_id, buyer_name):
        self.company_id = company_id
        self.buyer_name = buyer_name
        self.buyer = buyer_name


class _Q:
    def __init__(self, rows):
        self._rows = list(rows)
        self._f = self._rows

    def filter(self, *a, **k):
        p = a[0] if a else None
        if p is not None and getattr(getattr(p, "left", None), "name", None) == "company_id":
            v = getattr(p, "right", None)
            self._f = [r for r in self._rows if getattr(r, "company_id", None) == v]
        return self

    def all(self):
        return list(self._f)


class _DB:
    def __init__(self, companies, pinvs, sinvs):
        self._companies = companies
        self._pinvs = pinvs
        self._sinvs = sinvs

    def query(self, model):
        name = getattr(model, "__name__", "")
        if name == "Company":
            return _Q(self._companies)
        if name == "PurchaseInvoice":
            return _Q(self._pinvs)
        if name == "SalesInvoice":
            return _Q(self._sinvs)
        return _Q([])


def build_stub_db():
    companies = [
        _Company(1, A_NAME, "李四"),
        _Company(2, B_NAME, "张三"),   # 与 C 同法人 → 高风险关联 + 关联组
        _Company(3, C_NAME, "张三"),
        _Company(4, D_NAME, "王五"),
    ]
    # 让 A/B/C 共享两家供应商（驱动「由发票往来建图」）
    pinvs = [
        _PInv(1, B_NAME), _PInv(1, SHARED_SUPPLIER_1), _PInv(1, SHARED_SUPPLIER_2),
        _PInv(2, SHARED_SUPPLIER_1), _PInv(2, SHARED_SUPPLIER_2),
        _PInv(3, SHARED_SUPPLIER_1), _PInv(3, SHARED_SUPPLIER_2),
    ]
    sinvs = [
        _SInv(1, C_NAME), _SInv(1, B_NAME), _SInv(1, "零散客户甲"), _SInv(1, "零散客户乙"),
    ]
    return _DB(companies, pinvs, sinvs)


# 目标企业 A 的进/销项发票（制造虚开特征组合）
SAL_INVS = [
    {"buyer": C_NAME, "amount": 4000000.0},   # 集中顶额 + 关联方大客户
    {"buyer": B_NAME, "amount": 100000.0},     # B 既是客户又是供应商 → 自循环
    {"buyer": "零散客户甲", "amount": 600000.0},
    {"buyer": "零散客户乙", "amount": 400000.0},
]
PUR_INVS = [
    {"seller": B_NAME, "amount": 500000.0},
    {"seller": SHARED_SUPPLIER_1, "amount": 200000.0},
    {"seller": SHARED_SUPPLIER_2, "amount": 100000.0},
]

# 银行流水：A→B 付款、C→A 回款（关联组闭环）；A↔D 互收互付（直接闭环）
BANK_TXS = [
    {"counterparty": B_NAME, "debit": 500000.0, "credit": 0.0},   # A 付 B
    {"counterparty": C_NAME, "credit": 4000000.0, "debit": 0.0},  # C 回 A
    {"counterparty": D_NAME, "debit": 200000.0, "credit": 0.0},  # A 付 D
    {"counterparty": D_NAME, "credit": 200000.0, "debit": 0.0},  # D 回 A
]


# ───────────────────────────── 断言工具 ─────────────────────────────
FAILS = []


def check(cond, msg, got=None):
    if cond:
        print(f"  [PASS] {msg}")
    else:
        print(f"  [FAIL] {msg}" + (f"  got={got}" if got is not None else ""))
        FAILS.append(msg)


def main():
    print("=" * 64)
    print("① 跨企业图谱（真实驱动 run_cross_enterprise_analysis）")
    print("=" * 64)
    ce = run_cross_enterprise_analysis(build_stub_db())
    print(f"  summary: {ce.get('summary')}")
    print(f"  companies={ce.get('total_companies')} "
          f"relationships={ce.get('total_relationships')} "
          f"high_risk={ce.get('high_risk_relationships')}")
    for r in ce.get("relationships", []):
        print(f"    - {r['company_a']} ↔ {r['company_b']} "
              f"[{r['type']}/{r['risk_level']}] : {r['description'][:40]}")
    check(ce.get("total_companies", 0) == 4, "图谱覆盖 4 家企业", ce.get("total_companies"))
    check(ce.get("total_relationships", 0) >= 1, "图谱关系非空", ce.get("total_relationships"))
    check(ce.get("high_risk_relationships", 0) >= 1, "存在高风险关联关系（同法人）",
          ce.get("high_risk_relationships"))

    print()
    print("=" * 64)
    print("② 跨企业资金回流闭环（关联分支必须命中）")
    print("=" * 64)
    fl = run_fund_loop_check(BANK_TXS, cross_enterprise=ce, company_name=A_NAME)
    m = fl["metrics"]
    print(f"  summary: {fl.get('summary')}")
    print(f"  direct={m['direct_loop_amount']}  indirect={m['indirect_loop_amount']}  "
          f"circular={m['circular_amount']}  groups={m['related_groups']}")
    check(m["direct_loop_amount"] == 200000.0, "直接闭环 = 200000（A↔D 互收互付）",
          m["direct_loop_amount"])
    check(m["indirect_loop_amount"] == 500000.0, "关联闭环 = 500000（A→B 付 / C→A 收，B、C 同组）",
          m["indirect_loop_amount"])
    check(m["circular_amount"] == 700000.0, "合计闭环 = 700000", m["circular_amount"])
    check(m["related_groups"] >= 1, "关联组已构建（来自图谱）", m["related_groups"])
    check("闭环" in fl["verdict"], "verdict 命中资金回流闭环", fl["verdict"])

    print()
    print("=" * 64)
    print("③ 虚开风险网络（跨企业高风险关联信号必须命中）")
    print("=" * 64)
    fi = run_false_invoice_check(SAL_INVS, PUR_INVS, cross_enterprise=ce,
                                 bank_txs=BANK_TXS, company_name=A_NAME)
    fm = fi["metrics"]
    print(f"  summary: {fi.get('summary')}")
    print(f"  in_out_ratio={fm['in_out_ratio']}  top3_share={fm['top3_customer_share']}  "
          f"circular={fm['circular_supplier_count']}  fund_loop={fm['fund_loop_amount']}  "
          f"high_risk_rel={fm['high_risk_relationships']}")
    for s in fi.get("signals", []):
        print(f"    - {s['signal']}")
    check(fm["high_risk_relationships"] >= 1, "跨企业高风险关联信号命中",
          fm["high_risk_relationships"])
    check(fm["in_out_ratio"] is not None and fm["in_out_ratio"] >= 5.0,
          "进销严重背离（≥5 倍）", fm["in_out_ratio"])
    check(fm["top3_customer_share"] >= 0.80, "集中顶额开票（前3客户≥80%）",
          fm["top3_customer_share"])
    check(fm["circular_supplier_count"] >= 1, "供应商=客户自循环命中", fm["circular_supplier_count"])
    check(fm["fund_loop_amount"] >= 200000.0, "资金回流闭环（直接）命中",
          fm["fund_loop_amount"])
    check("虚开特征组合" in fi["verdict"], "verdict = 多项虚开特征组合", fi["verdict"])

    print()
    print("=" * 64)
    if FAILS:
        print(f"结果：{len(FAILS)} 项未通过 ❌")
        for f in FAILS:
            print(f"   - {f}")
        sys.exit(1)
    print("结果：全部通过 ✅ —— 跨企业三能力在真实网状数据形状下均非死代码")
    print("=" * 64)


if __name__ == "__main__":
    main()
