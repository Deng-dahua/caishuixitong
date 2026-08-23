# -*- coding: utf-8 -*-
"""端到端验证：走真实 /api/tax-risk-docs/upload + /analyze 端点，
跑达冠型完整数据集，提取 BOM/仓储/运输/存货域结论，与直接调用结果比对。"""
import os, csv, io, sqlite3, sys, json, traceback
os.environ["APP_COOKIE_SECURE"] = "0"
os.environ["APP_ALLOWED_ORIGINS"] = "http://127.0.0.1:8001"
TEST_CID = 9999
CO_NAME = "达冠测试样例纺织"
BASE = os.path.dirname(os.path.abspath(__file__))

# ── 1. 插入测试账套（让发票方向推断能匹配公司名）──
def setup_company():
    c = sqlite3.connect(os.path.join(BASE, "data", "accounting.db"))
    c.execute("DELETE FROM companies WHERE id=?", (TEST_CID,))
    c.execute(
        "INSERT INTO companies(id,name,uscc,registered_capital,established_date,"
        "legal_representative,legal_representative_id,address,business_scope,"
        "company_type,industry_code,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (TEST_CID, CO_NAME, "91442000MA55TEST", "5000000", "2018-03-15",
         "范善茂", "421025198001010015", "中山市达冠路1号", "棉纺织加工",
         "有限责任公司", "17", "2026-01-01"))
    c.commit(); c.close()
    print("[setup] company 9999 inserted")

def cleanup_company():
    c = sqlite3.connect(os.path.join(BASE, "data", "accounting.db"))
    c.execute("DELETE FROM companies WHERE id=?", (TEST_CID,))
    c.commit(); c.close()

# ── 2. 写 7 个达冠型 CSV ──
def wcsv(path, header, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f); w.writerow(header)
        for r in rows: w.writerow(r)

def make_files():
    d = os.path.join(BASE, "_e2e_samples"); os.makedirs(d, exist_ok=True)
    # 银行流水（含仓库租金3万/月，无运输费；余额滚动；广州服装双向收付）
    wcsv(os.path.join(d, "达冠农业银行流水.csv"),
        ["交易日期","交易类型","对方账户","对方户名","借方发生额","贷方发生额","余额","摘要","交易渠道"],
        [
            ["2025-01-01","转账","6228*00","期初余额","","","9440000","期初","网银"],
            ["2025-01-05","转账","6228*12","河南鄢陵纺织加工厂","9040000","","400000","付加工费","网银"],
            ["2025-01-10","转账","6228*34","厦门旻刘纺织加工厂","3280000","","-2880000","付加工费","网银"],
            ["2025-01-15","转账","6228*56","新疆棉业有限公司","200000","","-3080000","购棉纱","网银"],
            ["2025-01-20","转账","6228*78","广东化工染料","50000","","-3130000","购染料","网银"],
            ["2025-01-28","转账","6228*88","中山市自来水公司","8000","","-3138000","水费","网银"],
            ["2025-02-05","转账","6228*90","中山市仓储服务部","30000","","-3168000","仓库租赁费","网银"],
            ["2025-02-05","转账","6228*91","广州服装有限公司","","1000000","-2168000","收货款","网银"],
            ["2025-02-06","转账","6228*91","广州服装有限公司","500000","","-2668000","付货款","网银"],
            ["2025-02-10","转账","6228*92","东莞制衣厂","","9500000","6832000","收货款","网银"],
            ["2025-02-15","转账","6228*93","佛山针织机械","120000","","6712000","购设备","网银"],
            ["2025-02-20","转账","6228*94","广州服装有限公司","","2000000","8712000","收货款","网银"],
        ])
    # 进项发票（含跨省加工费904万+328万；FP001 重复出现两次→重复发票号）
    wcsv(os.path.join(d, "达冠进项发票明细.csv"),
        ["发票号码","开票日期","货物或应税劳务名称","规格型号","单位","数量","单价","金额","税率","税额","销方名称","销方税号","购方名称","购方税号"],
        [
            ["FP001","2025-01-05","棉纱","32S","kg","4000","50","200000","13%","26000","新疆棉业有限公司","91650100MA01","达冠测试样例纺织","91442000MA55TEST"],
            ["FP002","2025-01-10","染料","活性","kg","500","100","50000","13%","6500","广东化工染料","91440100MA02","达冠测试样例纺织","91442000MA55TEST"],
            ["FP003","2025-01-08","加工费","染色","次","1","9040000","9040000","13%","1175200","河南鄢陵纺织加工厂","91411000MA03","达冠测试样例纺织","91442000MA55TEST"],
            ["FP004","2025-01-09","加工费","染色","次","1","3280000","3280000","13%","426400","厦门旻刘纺织加工厂","91350200MA04","达冠测试样例纺织","91442000MA55TEST"],
            ["FP001","2025-01-12","棉纱","40S","kg","1000","50","50000","13%","6500","新疆棉业有限公司","91650100MA01","达冠测试样例纺织","91442000MA55TEST"],
            ["FP005","2025-01-18","棉纱","32S","kg","2000","50","100000","13%","13000","新疆棉业有限公司","91650100MA01","达冠测试样例纺织","91442000MA55TEST"],
            ["FP006","2025-01-22","染料","分散","kg","300","100","30000","13%","3900","广东化工染料","91440100MA02","达冠测试样例纺织","91442000MA55TEST"],
        ])
    # 销项发票（针织布约1050万+新增）
    wcsv(os.path.join(d, "达冠销项发票明细.csv"),
        ["发票号码","开票日期","货物或应税劳务名称","规格型号","单位","数量","单价","金额","税率","税额","销方名称","销方税号","购方名称","购方税号"],
        [
            ["XS001","2025-02-05","针织布","全棉","米","40000","250","10000000","13%","1300000","达冠测试样例纺织","91442000MA55TEST","广州服装有限公司","91440100MA10"],
            ["XS002","2025-02-10","针织布","全棉","米","2000","250","500000","13%","65000","达冠测试样例纺织","91442000MA55TEST","东莞制衣厂","91441900MA11"],
            ["XS003","2025-02-20","针织布","全棉","米","8000","250","2000000","13%","260000","达冠测试样例纺织","91442000MA55TEST","广州服装有限公司","91440100MA10"],
        ])
    # BOM 物料清单
    wcsv(os.path.join(d, "达冠BOM物料清单.csv"),
        ["成品编码","成品名称","原料编码","原料名称","单位用量","损耗率","物料清单"],
        [
            ["FG01","针织布","RM01","棉纱","1.1","0.05","针织布配方"],
        ])
    # 进销存台账（废棉勾稽不平衡+40）
    wcsv(os.path.join(d, "达冠进销存台账.csv"),
        ["日期","存货编码","存货名称","期初库存","本期入库","本期出库","期末库存","单位","金额"],
        [
            ["2025-01-31","RM01","棉纱","200","4450","4000","650","kg","445000"],
            ["2025-01-31","FG01","针织布","50","4450","4000","500","米","500000"],
            ["2025-01-31","RM99","废棉","10","300","100","250","kg","1500"],
        ])
    # 仓库租赁合同（面积600㎡）
    wcsv(os.path.join(d, "达冠仓库租赁合同.csv"),
        ["仓库租赁","仓库坐落","仓储面积","仓库面积","租赁期限","月租金","仓储品类"],
        [["DH-CL-2025","中山市达冠路1号","600","600","2025全年","30000","纺织品"]])
    # 运输合同（运费承担方式=到货价，银行无运费支出）
    wcsv(os.path.join(d, "达冠运输合同.csv"),
        ["运输合同","承运方","起运地","到达地","运输方式","运输距离","运输重量","运费","运费承担方式"],
        [["DH-YS-2025","物流公司","新疆","中山","汽运","3500","4000","到货价含运","购方承担(到货价)"]])
    return d

# ── 3. 走真实端点 ──
def run_e2e(sample_dir):
    from fastapi.testclient import TestClient
    import main as appmod
    client = TestClient(appmod.app)
    # 登录（admin/Admin@2024caishui）
    lr = client.post("/api/auth/login", json={"username":"admin","password":"Admin@2024caishui"})
    print("[login]", lr.status_code, json.dumps(lr.json(), ensure_ascii=False)[:120])
    if not lr.json().get("ok"):
        return None
    csrf = client.cookies.get("csrf_token", "")
    hdr = {"X-CSRF-Token": csrf} if csrf else {}
    files = []
    for fn in ["达冠农业银行流水.csv","达冠进项发票明细.csv","达冠销项发票明细.csv",
               "达冠BOM物料清单.csv","达冠进销存台账.csv","达冠仓库租赁合同.csv","达冠运输合同.csv"]:
        p = os.path.join(sample_dir, fn)
        files.append(("files", (fn, open(p, "rb").read(), "text/csv")))
    r = client.post(f"/api/tax-risk-docs/upload?company_id={TEST_CID}", files=files, headers=hdr)
    print("[upload]", r.status_code, json.dumps(r.json(), ensure_ascii=False)[:200])
    # 分析
    r = client.post(f"/api/tax-risk-docs/analyze?company_id={TEST_CID}", headers=hdr)
    print("[analyze]", r.status_code)
    body = r.json()
    if not body.get("ok"):
        print("  analyze failed:", body.get("message", body)[:300])
        return None
    rep = body["report"]
    allf = rep.get("all_findings", []) or []
    print(f"\n========== 一键分析结果 ==========")
    print(f"文件数:{rep.get('files_count')}  规则:{rep.get('rules_used')}  总发现:{len(allf)}  综合等级:{rep.get('overall_level')}")
    print(f"高:{rep.get('high_risk')} 中:{rep.get('mid_risk')} 低:{rep.get('low_risk')}")
    # 提取关键域
    KEY_DOMAINS = ["BOM投入产出验证","仓储容量匹配","运输费量化配比","存货周转预警","进销存匹配"]
    print(f"\n----- 关键域发现（与直接跑的结果比对）-----")
    for f in allf:
        dom = f.get("domain","")
        if any(k in dom for k in KEY_DOMAINS):
            print(f"[{f.get('level','?')}] {dom} :: {f.get('type','')}")
            det = f.get("detail","")
            if det: print(f"      detail: {det[:160]}")
    # 企业版九章报告是否含这些发现
    err = rep.get("enterprise_readable_report", {}) or {}
    probs = err.get("confirmed_problems", []) or []
    print(f"\n----- 九章报告·确认问题数: {len(probs)} -----")
    for p in probs[:12]:
        print(f"  · [{p.get('conclusion_grade','?')}] {p.get('title','')[:60]}")
    summ = err.get("summary", {}) or {}
    print(f"\n----- 摘要 headline -----\n{summ.get('headline','')}")
    print(f"已核定问题:{summ.get('verified_problem_count')} 待核问题:{summ.get('pending_problem_count')}")
    # 抽查一个已核定项的结论状态段
    for p in probs:
        if p.get("conclusion_grade") == "已核定":
            paras = p.get("narrative_paragraphs", [])
            cs = next((x for x in paras if x.get("heading") == "结论状态"), None)
            print(f"\n----- 抽查已核定项『{p.get('title','')[:40]}』结论状态段 -----")
            print((cs or {}).get("text", "")[:260])
            break
    # ── 全量 detail / metrics 深度诊断（评估报告厚度瓶颈）──
    print("\n===== 全部发现 detail / observed_metrics 深度诊断 =====")
    for f in rep.get("all_findings", []) or []:
        m = f.get("observed_metrics") or {}
        print(f"\n[{f.get('level')}] {f.get('type')}  | metrics字段数={len(m)}")
        print("  detail:", (f.get('detail') or '')[:300])
        if m:
            import json as _json
            print("  metrics:", _json.dumps(m, ensure_ascii=False)[:600])

    # ── 本轮修复验证 ──
    print("\n===== 五项修复 + 厚度增厚验证 =====")
    import re as _re
    all_text = json.dumps(rep, ensure_ascii=False)
    bad_punct = _re.findall(r"。。|。；|；。|、、|。\、|\.、", all_text)
    print(f"[1] 异常标点（。。/。；/、等）出现次数: {len(bad_punct)}  样例: {bad_punct[:5]}")
    eng_leak = _re.findall(r"[\u4e00-\u9fff](?:bank_statement|purchase_invoice|sales_invoice)|(?:bank_statement|purchase_invoice|sales_invoice)[\u4e00-\u9fff]", all_text)
    print(f"[2] 英文类型编码紧邻中文出现次数: {len(eng_leak)}")
    kp = summ.get("key_points") or []
    print(f"[3] 重点摘要 {len(kp)} 条（验证无半句截断）:")
    for k in kp:
        print(f"    - {k[:200]}")
    for p in probs:
        paras = p.get("narrative_paragraphs", [])
        fact = next((x for x in paras if x.get("heading") == "查明的主要事实"), None)
        scope_p = next((x for x in paras if x.get("heading") == "检查范围、方法和资料依据"), None)
        ft = (fact or {}).get("text", "")
        if "余额" in ft or "对手方" in ft or "发票号码出现多次" in ft:
            print(f"\n[4/5] 『{p.get('title','')[:30]}』查明的主要事实:\n    {ft[:400]}")
            print(f"    资料依据: {(scope_p or {}).get('text','')[:120]}")

    # ── 厚度增厚专项验证 ──
    print("\n===== 厚度增厚专项 =====")
    # (a) 明细表：确认问题是否挂了 detail_table
    dt_count = 0
    for p in probs:
        for para in p.get("narrative_paragraphs", []):
            if para.get("detail_table") and para["detail_table"].get("rows"):
                dt_count += 1
                break
    print(f"[A] 挂有可回查明细表的确认问题数: {dt_count}/{len(probs)}")
    for p in probs:
        for para in p.get("narrative_paragraphs", []):
            dt = para.get("detail_table")
            if dt and dt.get("rows"):
                print(f"      · 『{p.get('title','')[:28]}』明细表 {len(dt['rows'])} 行 × {len(dt['columns'])} 列: {dt['columns']}")
                break
    # (b) 全部发现一览
    ov = err.get("discovery_overview", []) or []
    print(f"[B] 本轮全部发现一览条目数: {len(ov)}")
    for row in ov[:20]:
        print(f"      - [{row.get('category')}] {row.get('type','')[:34]} | {row.get('grade')}")
    # (c) 资料清单含文件名
    mats = err.get("materials", []) or []
    print(f"[C] 资料清单类数: {len(mats)}（验证具名文件名）")
    for m_ in mats:
        fns = m_.get("file_names") or []
        print(f"      - {m_.get('display_name')}: {m_.get('row_count')}条 / {len(fns)}文件 -> {('、'.join(fns))[:60]}")
    return rep


# ── 4. 进化规则严谨稽查：用达冠真实样本数字构造含申报表的引擎数据，
#       直接跑 run_verified_rules，验证 VR026–VR031 对达冠的风险命中 ──
def run_evolved_audit():
    import sys as _sys
    _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from engine.verified_rule_engine import run_verified_rules

    # 达冠真实样本数字（来自上方 make_files 的银行/进销发票）
    bank_txs = [
        {"date": "2025-02-05", "counterparty": "广州服装有限公司", "credit": 1000000, "debit": 0, "balance": -2168000, "summary": "收货款"},
        {"date": "2025-02-06", "counterparty": "广州服装有限公司", "credit": 0, "debit": 500000, "balance": -2668000, "summary": "付货款"},
        {"date": "2025-02-10", "counterparty": "东莞制衣厂", "credit": 9500000, "debit": 0, "balance": 6832000, "summary": "收货款"},
        {"date": "2025-02-20", "counterparty": "广州服装有限公司", "credit": 2000000, "debit": 0, "balance": 8712000, "summary": "收货款"},
        # 资金回流/公私混同：向六员个人范善茂大额转出（增值税法/征管法63条信号）
        {"date": "2025-02-25", "counterparty": "范善茂", "credit": 0, "debit": 600000, "balance": 8112000, "summary": "转存"},
    ]
    sal_invs = [
        {"invoice_no": "XS001", "date": "2025-02-05", "goods": "针织布", "unit": "米", "qty": 40000, "amount": 10000000, "tax": 1300000, "total": 11300000, "buyer": "广州服装有限公司"},
        {"invoice_no": "XS002", "date": "2025-02-10", "goods": "针织布", "unit": "米", "qty": 2000, "amount": 500000, "tax": 65000, "total": 565000, "buyer": "东莞制衣厂"},
        {"invoice_no": "XS003", "date": "2025-02-20", "goods": "针织布", "unit": "米", "qty": 8000, "amount": 2000000, "tax": 260000, "total": 2260000, "buyer": "广州服装有限公司"},
        # VR037 触发：同品名针织布/米，关联对手方单价 80（中位数250，偏离68%）
        {"invoice_no": "XS004", "date": "2025-02-25", "goods": "针织布", "unit": "米", "qty": 2000, "amount": 160000, "tax": 20800, "total": 180800, "buyer": "达冠关联贸易公司"},
    ]
    pur_invs = [
        {"invoice_no": "FP001", "date": "2025-01-05", "goods": "棉纱", "amount": 200000, "tax": 26000, "total": 226000, "seller": "新疆棉业有限公司"},
        {"invoice_no": "FP003", "date": "2025-01-08", "goods": "加工费", "amount": 9040000, "tax": 1175200, "total": 10215200, "seller": "河南鄢陵纺织加工厂"},
        {"invoice_no": "FP004", "date": "2025-01-09", "goods": "加工费", "amount": 3280000, "tax": 426400, "total": 3706400, "seller": "厦门旻刘纺织加工厂"},
        {"invoice_no": "FP002", "date": "2025-01-10", "goods": "染料", "amount": 50000, "tax": 6500, "total": 56500, "seller": "广东化工染料"},
        {"invoice_no": "FP005", "date": "2025-01-18", "goods": "棉纱", "amount": 100000, "tax": 13000, "total": 113000, "seller": "新疆棉业有限公司"},
        {"invoice_no": "FP006", "date": "2025-01-22", "goods": "染料", "amount": 30000, "tax": 3900, "total": 33900, "seller": "广东化工染料"},
        # VR032 触发：取得的专票但用途为业务招待（酒），应转出未转出
        {"invoice_no": "FP007", "date": "2025-01-25", "invoice_code": "011002100", "goods": "高档酒-业务招待", "amount": 100000, "tax": 13000, "total": 113000, "seller": "某商贸有限公司"},
    ]
    vouchers = [
        # 其他应收款挂股东范善茂借款（财税[2003]158号信号）
        {"account_name": "其他应收款-股东借款", "summary": "范善茂借款", "debit": 600000, "credit": 0},
        # VR034 触发：大额咨询费（虚列成本费用高频载体）
        {"account_name": "管理费用-咨询费", "summary": "管理咨询服务费", "debit": 800000, "credit": 0, "settle": "转账"},
        # VR035 触发：租赁合同（其他税目印花税）
        {"account_name": "管理费用-租赁费", "summary": "厂房租金", "debit": 1200000, "credit": 0, "settle": "转账"},
        # VR036 触发：无偿赠送样品（视同销售未计销项）
        {"account_name": "销售费用-样品", "summary": "赠送样品宣传", "debit": 30000, "credit": 0, "settle": "转账"},
        # VR038 触发：业务招待费 20万（收入1250万，限额=min(12万,6.25万)=6.25万，超限13.75万）
        {"account_name": "管理费用-业务招待费", "summary": "客户招待宴请", "debit": 200000, "credit": 0, "settle": "转账"},
        # VR039 触发：广告费 300万（收入1250万，限额=187.5万，超限112.5万）
        {"account_name": "销售费用-广告费", "summary": "央视广告投放", "debit": 3000000, "credit": 0, "settle": "转账"},
        # VR040 触发：福利费 200万（无工资数据→走提示分支，验证不报错）
        {"account_name": "应付职工薪酬-职工福利费", "summary": "节日福利", "debit": 200000, "credit": 0, "settle": "转账"},
        # VR041 触发：折旧 500万（无固定资产原值→走提示分支，验证不报错）
        {"account_name": "制造费用-折旧费", "summary": "设备折旧", "debit": 5000000, "credit": 0, "settle": "转账"},
    ]
    # 申报表：模拟达冠实际可能低报的情形——
    # 销项申报仅 250万（隐匿 ~1000万未开票），实缴增值税仅 5万 → 税负率极低
    # 注意：引擎读取的键为 declaration（非 tax_declarations）
    tax_declarations = [
        {"period": "2025-01", "sales_amount": 0, "sales_tax": 0, "input_tax": 1646600, "payable_tax": 0},
        {"period": "2025-02", "sales_amount": 2500000, "sales_tax": 325000, "input_tax": 0, "payable_tax": 50000,
         "uninvoiced_sales": 0, "stamp_tax_base": 300000},
    ]
    declaration = tax_declarations
    # VR042 触发：固定资产房屋原值 + 仓库租赁合同租金
    fixed_assets = [
        {"name": "生产厂房", "original_value": 10000000, "category": "房屋建筑物"},
    ]
    contracts = [
        {"合同类型": "仓库租赁", "月租金": 30000, "租赁月数": 12, "合同编号": "DH-CL-2025"},
    ]
    target_entity = {"legal_representative": "范善茂", "industry_code": "17"}

    engine_data = {
        "bank_txs": bank_txs,
        "sal_invs": sal_invs,
        "pur_invs": pur_invs,
        "vouchers": vouchers,
        "tax_declarations": tax_declarations,
        "declaration": declaration,
        "fixed_assets": fixed_assets,
        "contracts": contracts,
        "target_entity": target_entity,
    }
    result = run_verified_rules(engine_data)
    print("\n========== 进化规则·达冠严谨稽查（VR026–VR043）==========")
    new_ids = {f"VR{i:03d}" for i in range(26, 44)}
    hit = [f for f in result["findings"] if f["rule_id"] in new_ids]
    print(f"新增规则命中数: {len(hit)} / 18")
    for f in hit:
        m = f.get("observed_metrics", {})
        print(f"  [{f['rule_id']}] {f['type']} | 等级:{f.get('level')} | 优先级:{f.get('priority')}")
        print(f"      {f['detail'][:200]}")
    # 断言：达冠在进化后应被识别出的风险点
    hit_ids = {f["rule_id"] for f in hit}
    expected = {"VR026", "VR028", "VR030", "VR032", "VR034", "VR035", "VR036",
                "VR038", "VR039", "VR042", "VR043"}  # 税负率/未开票/股东借款/进项转出/费用虚列/印花其他税目/视同销售/招待费/广告费/房产税/城建附加
    missing = expected - hit_ids
    print(f"  预期命中 {sorted(expected)}，实际缺失 {sorted(missing) if missing else '无'}")
    assert not missing, f"达冠严谨稽查未命中预期风险点: {missing}"
    # VR033 独立对照：进销品名严重背离（煤炭→建材变名）验证规则本身能力
    ctrl = run_verified_rules({
        "sal_invs": [{"invoice_no": "X1", "goods": "建材", "amount": 1000000, "tax": 130000, "total": 1130000}],
        "pur_invs": [{"invoice_no": "P1", "invoice_code": "011", "goods": "煤炭", "amount": 800000, "tax": 104000, "total": 904000}],
    })
    ctrl_hit = {f["rule_id"] for f in ctrl["findings"]}
    print(f"  [VR033对照] 煤炭→建材背离命中: {'VR033' in ctrl_hit}")
    assert "VR033" in ctrl_hit, "VR033 变名开票规则未命中对照样本"
    # VR037 独立验证：价格偏离探针应检出 XS004 关联低价，或给出需补股权数据提示
    v37 = [f for f in result["findings"] if f["rule_id"] == "VR037"]
    assert v37, "VR037 关联交易价格偏离探针未触发"
    v37_m = v37[0].get("observed_metrics", {})
    dev_n = v37_m.get("deviation_count", 0)
    has_pointer = (dev_n and dev_n > 0) or v37_m.get("related_party_data") is False
    print(f"  [VR037] 单价偏离笔数={dev_n} | 股权穿透提示={'已给出' if v37_m.get('related_party_data') is False else '无'}")
    assert has_pointer, "VR037 既未检出价格偏离也未给出需补数据提示"
    # VR040 提示分支验证（无工资数据→福利费超14%无法精确，产出提示）
    v40 = [f for f in result["findings"] if f["rule_id"] == "VR040"]
    print(f"  [VR040] 福利费提示发现数={len(v40)}")
    assert len(v40) >= 1, "VR040 福利费提示分支未产出"
    # VR041 独立对照：有折旧凭证但无房屋类固定资产原值，应产出'数据缺失'提示而非静默
    v41_ctrl = run_verified_rules({
        "vouchers": [{"account_name": "制造费用-折旧费", "summary": "设备折旧", "debit": 5000000}],
        "fixed_assets": [{"name": "设备", "original_value": 100, "category": "机器设备"}],
    })
    v41 = [f for f in v41_ctrl["findings"] if f["rule_id"] == "VR041"]
    print(f"  [VR041对照] 无固定资产时提示发现数={len(v41)}")
    assert len(v41) >= 1, "VR041 折旧异常提示分支（无固定资产）未产出"
    # 覆盖度自检器输出
    cov = result.get("coverage", {})
    print("\n========== 稽查覆盖度自检 ==========")
    print(result.get("coverage_text", ""))
    assert cov.get("summary", {}).get("coverage_rate", 0) > 0, "覆盖度自检未生成"
    return hit_ids


if __name__ == "__main__":
    try:
        setup_company()
        sd = make_files()
        rep = run_e2e(sd)
        run_evolved_audit()
    except Exception:
        traceback.print_exc()
        rep = None
    finally:
        # 清理内存文档与磁盘文件（避免污染）
        try:
            import main as appmod
            appmod._tax_risk_docs[:] = [d for d in appmod._tax_risk_docs if d.get("company_id") != TEST_CID]
            ud = appmod._get_company_upload_dir(TEST_CID)
            if os.path.isdir(ud):
                import shutil
                shutil.rmtree(ud, ignore_errors=True)
        except Exception as e:
            print("cleanup-upload:", e)
        try: cleanup_company()
        except Exception as e: print("cleanup-co:", e)
        print("\n[cleanup] test company 9999 + files removed")
