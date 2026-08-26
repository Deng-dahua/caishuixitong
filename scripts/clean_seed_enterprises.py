# -*- coding: utf-8 -*-
"""
清理 seed_related_enterprises.py 灌入的占位企业/发票，使 cross_enterprise 图谱
仅由 4 家真实上传企业的真实发票往来重建。
- 先备份 data/accounting.db -> data/accounting.db.seedbak
- 仅按占位特征删除：company id=10、seller_name∈{丙/丁/戊}、buyer_name∈{己/庚}
- 不触碰真实上传发票（真实供应商/客户不会叫"丙物流/丁材料"等占位名）
"""
import sys, os, shutil
sys.path.insert(0, ".")

DB = "data/accounting.db"
BAK = "data/accounting.db.seedbak"
from database import SessionLocal, Company, PurchaseInvoice, SalesInvoice

if os.path.exists(DB):
    shutil.copy(DB, BAK)
    print("✅ DB 备份 ->", BAK)

SEED_SELLERS = ["丙物流有限公司", "丁材料有限公司", "戊包装有限公司"]
SEED_BUYERS = ["己商贸有限公司", "庚科技有限公司"]

db = SessionLocal()
try:
    n_co = db.query(Company).filter(Company.id == 10).count()
    n_pur = db.query(PurchaseInvoice).filter(PurchaseInvoice.seller_name.in_(SEED_SELLERS)).count()
    n_sal = db.query(SalesInvoice).filter(SalesInvoice.buyer_name.in_(SEED_BUYERS)).count()
    print(f"[before] company#10={n_co}  seed_purchase={n_pur}  seed_sales={n_sal}")

    db.query(Company).filter(Company.id == 10).delete()
    db.query(PurchaseInvoice).filter(PurchaseInvoice.seller_name.in_(SEED_SELLERS)).delete(synchronize_session=False)
    db.query(SalesInvoice).filter(SalesInvoice.buyer_name.in_(SEED_BUYERS)).delete(synchronize_session=False)
    db.commit()

    n_co2 = db.query(Company).filter(Company.id == 10).count()
    n_pur2 = db.query(PurchaseInvoice).filter(PurchaseInvoice.seller_name.in_(SEED_SELLERS)).count()
    n_sal2 = db.query(SalesInvoice).filter(SalesInvoice.buyer_name.in_(SEED_BUYERS)).count()
    print(f"[after ] company#10={n_co2}  seed_purchase={n_pur2}  seed_sales={n_sal2}")
    print("✅ seed 占位数据已清除；cross_enterprise 将仅从真实发票重建")
finally:
    db.close()
