"""
共享工具函数 — 供 main.py 和各 router 模块使用
不依赖 main.py（只依赖 database.py + 标准库/FastAPI），避免循环导入
"""
from sqlalchemy.orm import Session
from database import (
    Account, JournalEntry, BankTransaction,
    InputVATDeduction, BookkeepingInvoice, PurchaseInvoice,
)


def build_account_hierarchy(db: Session, company_id: int) -> dict:
    """构建科目编码→全级次名称的映射"""
    all_accounts = db.query(Account).filter(Account.company_id == company_id).all()
    code_map = {a.code: a for a in all_accounts}

    def get_full_name(acct):
        parts = []
        current = acct
        visited = set()
        while current and current.code not in visited:
            visited.add(current.code)
            parts.append(f"{current.code} {current.name}")
            current = code_map.get(current.parent_code) if current.parent_code else None
        parts.reverse()
        return " / ".join(parts)

    return {a.code: get_full_name(a) for a in all_accounts}


def sync_biz_voucher_no(db, company_id, entry, new_voucher_str):
    """同步更新单条分录关联的业务表凭证号"""
    if not entry.ref_id or not entry.source:
        return
    if entry.source == "银行流水":
        db.query(BankTransaction).filter(
            BankTransaction.company_id == company_id,
            BankTransaction.id == entry.ref_id
        ).update({"journal_voucher_no": new_voucher_str}, synchronize_session=False)
    elif entry.source == "进项抵扣":
        db.query(InputVATDeduction).filter(
            InputVATDeduction.company_id == company_id,
            InputVATDeduction.id == entry.ref_id
        ).update({"voucher_no": new_voucher_str}, synchronize_session=False)


def renumber_vouchers(db, company_id, period, voucher_word):
    """删除后自动重排同一期间+凭证字下的凭证号，并同步业务表"""
    entries = db.query(JournalEntry).filter(
        JournalEntry.company_id == company_id,
        JournalEntry.period == period,
        JournalEntry.voucher_word == voucher_word,
    ).order_by(JournalEntry.voucher_no.asc(), JournalEntry.id.asc()).all()
    if not entries:
        return
    groups = {}
    for e in entries:
        groups.setdefault(e.voucher_no, []).append(e)
    new_no = 1
    for old_no in sorted(groups.keys()):
        voucher_str_new = f"{voucher_word}-{new_no}"
        for e in groups[old_no]:
            e.voucher_no = new_no
            sync_biz_voucher_no(db, company_id, e, voucher_str_new)
        new_no += 1
    db.flush()


def clear_source_voucher_no(db, company_id, entry):
    """删除序时账凭证时，同步清除关联业务记录的凭证号"""
    if not entry.source:
        return
    voucher_str = f"{entry.voucher_word}-{entry.voucher_no}"

    # ── 银行流水：双保险清除 ──
    if entry.source == "银行流水" and entry.ref_id:
        db.query(BankTransaction).filter(
            BankTransaction.company_id == company_id,
            BankTransaction.id == entry.ref_id
        ).update({"journal_voucher_no": None}, synchronize_session=False)
    db.query(BankTransaction).filter(
        BankTransaction.company_id == company_id,
        BankTransaction.journal_voucher_no == voucher_str
    ).update({"journal_voucher_no": None}, synchronize_session=False)

    # ── 进项抵扣 ──
    if entry.source == "进项抵扣" and entry.ref_id:
        db.query(InputVATDeduction).filter(
            InputVATDeduction.company_id == company_id,
            InputVATDeduction.id == entry.ref_id
        ).update({"voucher_no": None}, synchronize_session=False)
    db.query(InputVATDeduction).filter(
        InputVATDeduction.company_id == company_id,
        InputVATDeduction.voucher_no == voucher_str
    ).update({"voucher_no": None}, synchronize_session=False)

    # ── 记账发票 ──
    affected_bis = db.query(BookkeepingInvoice.invoice_code, BookkeepingInvoice.invoice_no,
                            BookkeepingInvoice.digital_invoice_no).filter(
        BookkeepingInvoice.company_id == company_id,
        BookkeepingInvoice.voucher_no == voucher_str
    ).all()
    bi_keys = set((c or "", n or "", d or "") for c, n, d in affected_bis)

    db.query(BookkeepingInvoice).filter(
        BookkeepingInvoice.company_id == company_id,
        BookkeepingInvoice.voucher_no == voucher_str
    ).update({"voucher_no": None}, synchronize_session=False)
    db.flush()

    # ── 取得发票：解锁对应的 skip_accounting ──
    if bi_keys:
        pis = db.query(PurchaseInvoice).filter(
            PurchaseInvoice.company_id == company_id,
            PurchaseInvoice.skip_accounting == True
        ).all()
        for pi in pis:
            pi_key = (pi.invoice_code or "", pi.invoice_no or "", pi.digital_invoice_no or "")
            if pi_key in bi_keys:
                pi.skip_accounting = False
        db.flush()


def renumber_archive(db, company_id, model_cls, prefix):
    """删除后自动整理档案编码，使其连续不断号"""
    entries = db.query(model_cls).filter(
        model_cls.company_id == company_id,
        model_cls.code.like(prefix + '%')
    ).order_by(model_cls.code).all()
    prefix_len = len(prefix)
    for i, entry in enumerate(entries, 1):
        new_code = f"{prefix}{i:03d}"
        if entry.code != new_code:
            entry.code = new_code
    db.flush()
