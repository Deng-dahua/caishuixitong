# -*- coding: utf-8 -*-
"""一次性干净插入 20 条漂移资料名到 material_recognition.py（去重保护）。"""
import io, os

ROOT = "C:/Users/Administrator/WorkBuddy/2026-08-04-21-37-33/caishuixitong"
NL = "\r\n"
MR = os.path.join(ROOT, "engine/material_recognition.py")

def read(p):
    with io.open(p, "r", encoding="utf-8", newline="") as f:
        return f.read()

def write(p, s):
    with io.open(p, "w", encoding="utf-8", newline="") as f:
        f.write(s)

m = read(MR)
if "sup_farmland_approval" in m:
    print("[skip] 已存在，跳过")
else:
    new_mats = (
        '    # ── 小微税种/费义务（2026-09-30 新增，对应 _OBLIGATION_REDLINES）──' + NL
        + '    ("农用地转用批准文件", "sup_farmland_approval",' + NL
        + '     ["农用地转用批准", "农用地转用", "建设用地批准文件", "农转用批复"], []),' + NL
        + '    ("占用耕地面积资料", "sup_farmland_area",' + NL
        + '     ["占用耕地面积", "耕地占用面积", "占地资料", "占地测量"], []),' + NL
        + '    ("固定资产明细（车辆）", "sup_vehicle_fixed_asset",' + NL
        + '     ["车辆固定资产明细", "固定资产车辆", "车辆明细账", "车辆原值明细"], []),' + NL
        + '    ("土地出让/转让合同", "sup_land_transfer_contract",' + NL
        + '     ["土地出让合同", "土地转让合同", "土地出让转让合同", "土地成交"], []),' + NL
        + '    ("增值税纳税申报表（含留抵税额）", "sup_vat_decl_retention",' + NL
        + '     ["增值税纳税申报表", "增值税申报表", "留抵退税申报"], []),' + NL
        + '    ("广告服务/娱乐服务收入台账", "sup_ad_ent_ledger",' + NL
        + '     ["广告服务收入台账", "娱乐服务收入台账", "广告娱乐收入台账", "文建费收入"], []),' + NL
        + '    ("收购金额资料", "sup_tobacco_amount",' + NL
        + '     ["烟叶收购金额", "收购金额资料", "收购金额明细"], []),' + NL
        + '    ("文化事业建设费申报表", "sup_culture_decl",' + NL
        + '     ["文化事业建设费申报表", "文建费申报表", "文化事业建设费缴款"], []),' + NL
        + '    ("机动车销售统一发票", "sup_vehicle_invoice",' + NL
        + '     ["机动车销售统一发票", "机动车发票", "车辆销售发票"], []),' + NL
        + '    ("烟叶收购凭证与台账", "sup_tobacco_ledger",' + NL
        + '     ["烟叶收购凭证", "烟叶收购台账", "烟叶收购单据"], []),' + NL
        + '    ("烟叶税申报表", "sup_tobacco_tax_decl",' + NL
        + '     ["烟叶税申报表", "烟叶税缴款书"], []),' + NL
        + '    ("留抵退税申请与税务机关核准资料", "sup_retention_approval",' + NL
        + '     ["留抵退税申请", "留抵退税核准", "留抵退税审批", "留抵退税资料"], []),' + NL
        + '    ("耕地占用税申报表", "sup_farmland_tax_decl",' + NL
        + '     ["耕地占用税申报表", "耕地占用税缴款"], []),' + NL
        + '    ("船舶吨税完税凭证", "sup_ship_ton_cert",' + NL
        + '     ["船舶吨税完税", "船舶吨税缴款", "吨税完税证明"], []),' + NL
        + '    ("船舶登记与船籍资料", "sup_ship_reg",' + NL
        + '     ["船舶登记证", "船籍资料", "船舶登记资料"], []),' + NL
        + '    ("船舶进出境记录", "sup_ship_entry",' + NL
        + '     ["船舶进出境记录", "船舶进境", "船舶出境记录"], []),' + NL
        + '    ("车辆登记证", "sup_vehicle_reg_cert",' + NL
        + '     ["车辆登记证", "机动车登记证书", "车辆登记证书"], []),' + NL
        + '    ("车辆购置税完税证明", "sup_vehicle_purchase_cert",' + NL
        + '     ["车辆购置税完税证明", "车购税完税", "车辆购置税缴款书"], []),' + NL
        + '    ("进销存与银行流水", "sup_inout_bank_flow",' + NL
        + '     ["进销存与银行流水", "进销存银行流水", "进销存流水"], []),' + NL
        + '    ("进项发票全量明细", "sup_input_invoice_detail",' + NL
        + '     ["进项发票全量明细", "进项发票明细", "进项发票清单", "进项发票全量"], []),' + NL
    )
    close_anchor = ']' + NL + NL + '# 红线需求名 → 识别信息（单一权威）'
    if close_anchor not in m:
        raise SystemExit("close_anchor 未匹配")
    m = m.replace(close_anchor, new_mats + ']' + NL + NL + '# 红线需求名 → 识别信息（单一权威）', 1)
    write(MR, m)
    print("[ok] 插入 20 条漂移资料名（无重复）")
