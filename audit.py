"""财税系统自动审查 — 启动时运行、每次变更后运行
检查7类常见错误：重复记账/来源不一致/科目名称/借贷平衡/三号分组/档案锁定/BK一致性
"""

import json
import re
import sys
import os
from database import get_db, JournalEntry, Account, BookkeepingInvoice, PurchaseInvoice
from database import BankTransaction, Supplier, Customer, Employee, Department
from sqlalchemy import func, or_, and_
from collections import defaultdict


def audit_all(company_id: int) -> dict:
    """运行全部审查，返回 {检查项: 结果}"""
    db = next(get_db())
    results = {}
    errors = []

    # 1. 重复记账检查
    dupes = _check_duplicate_journals(db, company_id)
    results["重复记账"] = len(dupes)
    errors.extend(dupes)

    # 2. 凭证借贷平衡
    unbalanced = _check_voucher_balance(db, company_id)
    results["借贷不平"] = len(unbalanced)
    errors.extend(unbalanced)

    # 3. 三号分组（同三号不同凭证）
    split = _check_same_key_split(db, company_id)
    results["三号拆分"] = len(split)
    errors.extend(split)

    # 4. BK voucher_no 一致性
    bk_fake = _check_bk_voucher_consistency(db, company_id)
    results["BK凭证号不一致"] = len(bk_fake)
    errors.extend(bk_fake)

    # 5. 科目名称格式
    bad_names = _check_account_names(db, company_id)
    results["科目名称格式错误"] = len(bad_names)
    errors.extend(bad_names)

    # 6. 档案锁定一致性
    lock_gaps = _check_archive_locks(db, company_id)
    results["档案锁定缺失"] = len(lock_gaps)
    errors.extend(lock_gaps)

    # 7. 来源一致性
    source_issues = _check_source_consistency(db, company_id)
    results["来源不一致"] = len(source_issues)
    errors.extend(source_issues)

    # 8. 系统一致性（数据源+字段完整性+数字核对）
    sys_issues = _check_system_consistency()
    results["系统一致性"] = len(sys_issues)
    errors.extend(sys_issues)

    return {
        "company_id": company_id,
        "total_errors": len(errors),
        "results": results,
        "errors": errors,
        "passed": len(errors) == 0,
    }


def _check_duplicate_journals(db, company_id):
    """检查同一银行流水是否被多个匹配函数重复记账"""
    errors = []
    # 查询所有银行流水来源的凭证，按 ref_id 分组
    entries = db.query(JournalEntry).filter(
        JournalEntry.company_id == company_id,
        JournalEntry.source == "银行流水",
        JournalEntry.ref_id.isnot(None)
    ).all()

    ref_sources = defaultdict(set)
    for e in entries:
        ref_sources[e.ref_id].add((
            e.voucher_no,
            e.account_code,
            "debit" if e.debit_amount > 0 else "credit"
        ))

    for ref_id, vouchers in ref_sources.items():
        vns = set(v[0] for v in vouchers)
        if len(vns) > 1:
            tx = db.query(BankTransaction).filter(BankTransaction.id == ref_id).first()
            name = tx.counterparty_name[:20] if tx else "?"
            errors.append(f"[重复记账] 银行流水#{ref_id}({name}) 生成多个凭证: {sorted(vns)}")

    return errors


def _check_voucher_balance(db, company_id):
    """检查每张凭证借贷是否相等"""
    errors = []
    entries = db.query(JournalEntry).filter(
        JournalEntry.company_id == company_id
    ).all()

    vouchers = defaultdict(lambda: {"debit": 0, "credit": 0})
    for e in entries:
        vouchers[e.voucher_no]["debit"] += e.debit_amount or 0
        vouchers[e.voucher_no]["credit"] += e.credit_amount or 0

    for vn, vals in vouchers.items():
        if abs(vals["debit"] - vals["credit"]) > 0.01:
            errors.append(f"[借贷不平] 记-{vn}: debit={vals['debit']:.2f} credit={vals['credit']:.2f}")

    return errors


def _check_same_key_split(db, company_id):
    """检查同三号发票是否被拆成多个凭证号"""
    errors = []
    entries = db.query(JournalEntry).filter(
        JournalEntry.company_id == company_id,
        JournalEntry.source == "未记账发票",
        JournalEntry.ref_id.isnot(None)
    ).all()

    # 按 PurchaseInvoice 的 ref_id 建三号映射
    pi_map = {}
    for inv in db.query(PurchaseInvoice).filter(PurchaseInvoice.company_id == company_id).all():
        key = (inv.invoice_code or "", inv.invoice_no or "", inv.digital_invoice_no or "")
        if key not in pi_map:
            pi_map[key] = set()
        pi_map[key].add(inv.id)

    # 检查每个三号对应的凭证号
    for key, ids in pi_map.items():
        if not key[0] and not key[1] and not key[2]:
            continue  # 三号全空，跳过
        vns = set()
        for pid in ids:
            for e in entries:
                if e.ref_id == pid:
                    vns.add(e.voucher_no)
        if len(vns) > 1:
            errors.append(f"[三号拆分] {key}: {sorted(vns)}")

    return errors


def _check_bk_voucher_consistency(db, company_id):
    """检查 BookkeepingInvoice.voucher_no 是否与序时账一致（通过三号匹配PI→JE）"""
    errors = []
    from database import PurchaseInvoice

    bks = db.query(BookkeepingInvoice).filter(
        BookkeepingInvoice.company_id == company_id,
        BookkeepingInvoice.voucher_no.isnot(None)
    ).all()

    for bk in bks:
        # 通过三号找到对应PI，再通过PI.id找到JE
        pi = db.query(PurchaseInvoice).filter(
            PurchaseInvoice.company_id == company_id,
            PurchaseInvoice.invoice_code == bk.invoice_code,
            PurchaseInvoice.invoice_no == bk.invoice_no,
            PurchaseInvoice.digital_invoice_no == bk.digital_invoice_no,
        ).first() if (bk.invoice_code or bk.invoice_no or bk.digital_invoice_no) else None

        if not pi:
            errors.append(f"[BK凭证不一致] BK#{bk.id} {bk.seller_name[:20]} 三号={bk.invoice_code}/{bk.invoice_no}/{bk.digital_invoice_no} 找不到对应PurchaseInvoice")
            continue

        je = db.query(JournalEntry).filter(
            JournalEntry.company_id == company_id,
            JournalEntry.source == "未记账发票",
            JournalEntry.ref_id == pi.id
        ).first()

        if not je:
            errors.append(f"[BK凭证不一致] BK#{bk.id} {bk.seller_name[:20]} voucher={bk.voucher_no} PI#{pi.id}无对应凭证")
            continue

        expected = f"记-{je.voucher_no}"
        if bk.voucher_no != expected:
            errors.append(
                f"[BK凭证不一致] BK#{bk.id} {bk.seller_name[:20]} voucher={bk.voucher_no} 应为{expected}"
            )

    return errors


def _check_account_names(db, company_id):
    """检查科目名称是否只存本级名称（不含'/'）"""
    errors = []
    accounts = db.query(Account).filter(
        Account.company_id == company_id,
        Account.level >= 2,  # 只检查明细科目
        Account.name.contains("/")
    ).all()

    for acc in accounts:
        errors.append(f"[科目名称格式] {acc.code} name='{acc.name}' 含'/'，应为本级名称")

    return errors


def _check_archive_locks(db, company_id):
    """检查被序时账引用的档案（人员/客户/供应商）是否有锁定标记"""
    errors = []
    
    # 收集序时账中引用的人员/客户/供应商名称
    je_contacts = set()
    for (cp,) in db.query(JournalEntry.contact_project).filter(
        JournalEntry.company_id == company_id,
        JournalEntry.contact_project.isnot(None),
        JournalEntry.contact_project != ""
    ).distinct().all():
        if cp:
            je_contacts.add(cp.strip())
    
    if not je_contacts:
        return errors  # 无数据时不误报
    
    # 检查客户档案
    customers = db.query(Customer).filter(Customer.company_id == company_id).all()
    for cust in customers:
        if cust.name and cust.name in je_contacts:
            # 检查该客户是否在序时账中有可以删除的引用（即未被锁定的）
            ref_count = db.query(JournalEntry).filter(
                JournalEntry.company_id == company_id,
                JournalEntry.contact_project == cust.name
            ).count()
            # 如果客户被引用但没有is_active标记或标记为不可删除
            if ref_count > 0 and hasattr(cust, 'is_active') and cust.is_active is False:
                errors.append(f"[档案锁定缺失] 客户{cust.name}被{ref_count}条分录引用但标记为非活跃，建议锁定")
            elif ref_count > 0 and not hasattr(cust, 'is_active'):
                # 客户被引用但没有锁定机制，至少记录引用关系
                pass  # 当前模型可能没有is_active字段，不做误报
    
    # 检查供应商档案
    suppliers = db.query(Supplier).filter(Supplier.company_id == company_id).all()
    for supp in suppliers:
        if supp.name and supp.name in je_contacts:
            ref_count = db.query(JournalEntry).filter(
                JournalEntry.company_id == company_id,
                JournalEntry.contact_project == supp.name
            ).count()
            if ref_count > 0 and hasattr(supp, 'is_active') and supp.is_active is False:
                errors.append(f"[档案锁定缺失] 供应商{supp.name}被{ref_count}条分录引用但标记为非活跃，建议锁定")
    
    # 检查人员档案
    employees = db.query(Employee).filter(Employee.company_id == company_id).all()
    for emp in employees:
        if emp.name and emp.name in je_contacts:
            ref_count = db.query(JournalEntry).filter(
                JournalEntry.company_id == company_id,
                JournalEntry.contact_project == emp.name
            ).count()
            if ref_count > 0 and hasattr(emp, 'is_active') and emp.is_active is False:
                errors.append(f"[档案锁定缺失] 人员{emp.name}被{ref_count}条分录引用但标记为非活跃，建议锁定")
    
    return errors


def _check_source_consistency(db, company_id):
    """检查代码中引用的 source 值是否一致"""
    errors = []

    # 检查序时账中 source='取得发票' 的条目（应全部改为未记账发票）
    old_source = db.query(JournalEntry).filter(
        JournalEntry.company_id == company_id,
        JournalEntry.source == "取得发票"
    ).count()
    if old_source > 0:
        errors.append(f"[来源不一致] 还有 {old_source} 条分录 source='取得发票'，应改为'未记账发票'")

    return errors


def _check_system_consistency() -> list:
    """系统一致性审计：JSON字段完整+system_config核对+JS数字过时检查"""
    errors = []
    base = os.path.dirname(os.path.abspath(__file__)) or "."

    # ═══ 1. 权威方法论目录核对 ═══
    try:
        from engine.methodology_catalog import methodology_inventory
        inventory = methodology_inventory()
        if not inventory.get("rules") or not inventory.get("industry_scenarios"):
            errors.append("[系统一致性] 权威规则或行业场景为空")
        if len(inventory.get("clue_depths", [])) < 2 or len(inventory.get("validation_depths", [])) < 2:
            errors.append("[系统一致性] 行业场景仍呈现固定链深或固定案例数")
    except Exception as e:
        errors.append(f"[系统一致性] 权威方法论目录核对失败: {e}")

    # ═══ 2. 规则—线索—证据—分析合同字段完整性 ═══
    try:
        from engine.methodology_catalog import load_canonical_catalog
        catalog = load_canonical_catalog()
        for module in catalog.get("modules", []):
            for field in ("rules", "clue_paths", "evidence_plan", "analysis_tests", "validation_cases", "report_boundary"):
                if not module.get(field):
                    errors.append(f"[系统一致性] {module.get('id')} 缺少 {field}")
    except Exception as e:
        errors.append(f"[系统一致性] 方法论合同字段检查失败: {e}")

    # ═══ 3. JS过时数字扫描 ═══
    try:
        js_path = os.path.join(base, "static", "js", "tax-pipeline-pages.js")
        with open(js_path, "r", encoding="utf-8") as f:
            js = f.read()
        stale_patterns = [
            ("pc('rules','1514')", "规则回退值1514应为1608"),
            ("pc('trailChains','396')", "线索回退值396应为437"),
            ("pc('evidenceChains','745')", "证据回退值745应为781"),
        ]
        for pattern, desc in stale_patterns:
            if pattern in js:
                errors.append(f"[系统一致性] JS过时引用: {desc}")
    except Exception as e:
        errors.append(f"[系统一致性] JS扫描失败: {e}")

    # ═══ 4. 僵尸文件检查 ═══
    zombie_files = ["report-custom-modules.js", "report-module-panel.js"]
    for zf in zombie_files:
        path = os.path.join(base, "static", "js", zf)
        if os.path.exists(path):
            errors.append(f"[系统一致性] 僵尸文件仍存在: static/js/{zf}")

    return errors


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python audit.py <company_id>")
        sys.exit(1)
    company_id = int(sys.argv[1])
    result = audit_all(company_id)
    print(f"\n{'='*60}")
    print(f"财税系统自动审查 — 公司ID={company_id}")
    print(f"{'='*60}")
    print(f"结果: {'[PASS] 全部通过' if result['passed'] else '[FAIL] 发现问题'}")
    print(f"错误总数: {result['total_errors']}")
    print()
    for check, count in result['results'].items():
        icon = "[OK]" if count == 0 else "[ERR]"
        print(f"  {icon} {check}: {count}项")
    if result['errors']:
        print(f"\n详细错误:")
        for e in result['errors']:
            print(f"  • {e}")
    print()
    sys.exit(0 if result['passed'] else 1)
