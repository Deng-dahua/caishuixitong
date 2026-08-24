# -*- coding: utf-8 -*-
"""
种子数据：灌入 3 家关联企业 + 发票往来，触发 CrossEnterpriseGraph 的
三种关联类型（同一法人 / 共享供应商 / 共享客户），让第三阶网状图谱有真实效果。

仅用于本地演示/验证，不依赖外部凭证。运行：
    .venv/Scripts/python.exe scripts/seed_related_enterprises.py
"""
import sys
sys.path.insert(0, ".")

from datetime import date
from database import (
    SessionLocal, Company, PurchaseInvoice, SalesInvoice,
)


def _mk_purchase(company_id, seller_name, seller_tax, goods, amount, tax, day):
    total = round(amount + tax, 2)
    return PurchaseInvoice(
        company_id=company_id,
        invoice_code="P2026",
        invoice_no=f"P{company_id}{day:02d}",
        digital_invoice_no=f"DP{company_id}{day:02d}",
        seller_tax_no=seller_tax,
        seller_name=seller_name,
        buyer_tax_no="",
        buyer_name="",
        invoice_date=date(2026, 3, day),
        goods_name=goods,
        quantity=1,
        unit_price=amount,
        amount=amount,
        tax_rate=0.13,
        tax_amount=tax,
        total_amount=total,
        invoice_category="purchase",
        status="normal",
        is_positive=True,
    )


def _mk_sales(company_id, buyer_name, buyer_tax, goods, amount, tax, day):
    total = round(amount + tax, 2)
    return SalesInvoice(
        company_id=company_id,
        invoice_code="S2026",
        invoice_no=f"S{company_id}{day:02d}",
        digital_invoice_no=f"DS{company_id}{day:02d}",
        seller_tax_no="",
        seller_name="",
        buyer_tax_no=buyer_tax,
        buyer_name=buyer_name,
        invoice_date=date(2026, 4, day),
        goods_name=goods,
        quantity=1,
        unit_price=amount,
        amount=amount,
        tax_rate=0.13,
        tax_amount=tax,
        total_amount=total,
        invoice_category="sales",
        status="normal",
        is_positive=True,
    )


def main():
    db = SessionLocal()
    try:
        # ── 1. 新增企业 C（与 B 同法人「范善茂」）──
        existing = db.query(Company).filter(Company.id == 10).first()
        if existing:
            print("企业 C(id=10) 已存在，跳过创建")
        else:
            c = Company(
                id=10,
                name="中山市冠茂供应链管理有限公司",
                uscc="91442000MA55LC9X21",
                registered_capital=5000000.0,
                established_date=date(2021, 6, 1),
                legal_representative="范善茂",  # ← 与 id=2 中山达冠相同
                legal_representative_id="442000199003070012",
                address="广东省中山市南区街道冠茂大厦 8 层",
                business_scope="供应链管理；纺织品、服装辅料批发；物流代理",
                company_type="有限责任公司",
                industry_code="L7224",
            )
            db.add(c)
            db.flush()
            print("✅ 新增企业 C: 中山市冠茂供应链管理有限公司 (id=10, 法人=范善茂)")

        # ── 2. A(id=1) 与 B(id=2) 共享 3 家供应商 ──
        shared_suppliers = [
            ("丙物流有限公司", "91440300MA5G001LP1", "运输费", 80000, 10400),
            ("丁材料有限公司", "91440300MA5G002DM2", "面料", 200000, 26000),
            ("戊包装有限公司", "91440300MA5G003BZ3", "包装物", 50000, 6500),
        ]
        for idx, (sname, stax, goods, amt, tax) in enumerate(shared_suppliers, start=1):
            # A 的采购
            db.add(_mk_purchase(1, sname, stax, goods, amt, tax, idx))
            # B 的采购
            db.add(_mk_purchase(2, sname, stax, goods, amt, tax, idx))
        print("✅ A(id=1) 与 B(id=2) 共享 3 家供应商: 丙物流/丁材料/戊包装")

        # ── 3. A(id=1) 与 C(id=10) 共享 2 家客户 ──
        shared_customers = [
            ("己商贸有限公司", "91442000MA5H101SM1", "成衣", 300000, 39000),
            ("庚科技有限公司", "91442000MA5H102KJ2", "技术服务", 120000, 15600),
        ]
        for idx, (bname, btax, goods, amt, tax) in enumerate(shared_customers, start=1):
            # A 的销售
            db.add(_mk_sales(1, bname, btax, goods, amt, tax, idx))
            # C 的销售
            db.add(_mk_sales(10, bname, btax, goods, amt, tax, idx))
        print("✅ A(id=1) 与 C(id=10) 共享 2 家客户: 己商贸/庚科技")

        db.commit()
        print("\n🎉 种子数据已提交。预期跨企业关联：")
        print("   - B(id=2) ↔ C(id=10): 同一法定代表人「范善茂」(high)")
        print("   - A(id=1) ↔ B(id=2): 共享 3 家供应商 (high)")
        print("   - A(id=1) ↔ C(id=10): 共享 2 家客户 (medium)")
    except Exception as e:
        db.rollback()
        print(f"❌ 失败并回滚: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
