# 项目长期记忆（caishuixitong 财税风险防控系统）

## ★ 能力优先级（最高约束）
- **① 风险分析能力=重中之重**（查出多少/多少种真实风险）；② 报告编辑=锦上添花。每轮自答「是否提高了①」。用户原话「该做就做，别跳过！！」
- 检出基线五档：①真检测器且触发 ②仅软匹配 ③有检测器未触发 ④仅兜底 ⑤无数据路径(盲区)。权威 `scripts/_audit_redline_coverage.py`（**口径：scripts/ 下一次性脚本不算检测器来源**）。当前（红线 91）：盲区 0、有真实检测器 78、仅兜底 11。另两把尺 `_audit_unfired_redlines.py`、`_gap_constituent_hits`。
- 新增红线必过「9 处登记」（`caishuixitong-redline-engine` skill），漏一处 audit 报 WARN。
- 先查「是否已有 VR 仅缺 redline_id 归属」再补检测器（零成本提①）：`scripts/_vr_rl_affinity.py`，闸门 `tests/test_vr_redline_declaration.py`。**只认扫描器真算过的要件（宁缺勿错）**。
- 加法范式：`engine/<x>_detector.py::detect_<x>()` → 带 `redline_id`+`constituent_hits` 的发现 → 接 `pipeline._run_analyze`；只读 `fieldkit`/`numparse`，禁写私有 `_buyer/_amount/_tax`。

## ★ 项目定位
上传什么查什么，以稽查专家身份查实所上传资料的全部税务风险，不等资料齐全；给解除方式+需补自证资料。终局＝证据闭合 或 自证清白。所分析风险全部入报告并标注证据地位。

## ★ 架构红线（违反即事故）
- 路由唯一收敛 `main::_execute_tax_risk_analysis`→`pipeline::_run_analyze`；封印唯一产出点 `seal_governed_findings`（只留 `_scenario_governed is True`，追加的探测 finding 必须自己打标）。
- 防误判打标须作用 `_scenario_execution["findings"]` 且在封印前；打 `all_findings` 零生效。
- 「调保守阈值」伪命题；裁决三态＝确认/降级/unconfirmed；禁为降误报调高确认阈值。
- 改 pipeline 域调用后须真跑全量核对 `scripts/four_reports/company_1_full.json` 顶层 `overall_level`（`{"ok":false}`＝崩溃）。

## ★ 五条静默吃掉发现的机制（新域/新发现必过五关）
1. **输出封印**：`seal_governed_findings` 只留 `_scenario_governed is True` 的条目；追加进 `_scenario_execution["findings"]` 的探测 finding **必须自己打 `_scenario_governed=True`**，否则静默丢弃（`gap_risk_detectors` 6 个探测器曾是真死代码）。
2. **等级合法性**：权威词表 极高风险5/高风险4/中风险3/待核验2/信息1/低风险0，词表外静默丢。
3. **文案门禁**：`review_finding` 净化；新增枚举补 `_ENUM_FIELDS`。
4. **递归爆栈**：遍历 report_data 一律**迭代+`id()`去环，禁递归**。
5. **未赋值局部变量/异常被 except 吞没**：整段从未生效（实录 `_extract_material_intel` UnboundLocalError）。铁律：except 留痕≥warning；关键产出非空加断言；**变量名复用(`for d in…`)是被低估的坑**。闸门：pipeline_log 含「异常」即本轮静默失效。

## ★ 单一权威模块清单（多头维护＝事故）
数值解析 `numparse`｜发票字段 `fieldkit`｜月份键 `findingkit`｜行业 `industry_resolver`｜**科目余额表取数口径 `financial_analyzer.trial_balance_amount`**｜红线配对 `tax_redlines.score_redline/match_redline_grounded`｜印花税 `domain_analysis._STAMP_DUTY_ITEMS`｜报告文本 `sentencekit`｜证据现状 `evidence_chain`｜净化 `_zh_normalize_obj`｜说人话 `plain_language`｜风格 `report_style`｜红线库 `tax_redlines`(constituents/constituent_sources/required_materials)｜要件核对 `constituent_checkpoint`｜要件阈值 `constituent_threshold`｜法条 `legal_citation`｜PDF/OCR `_parse_pdf_generic`+`_ocr_png_bytes`｜键汉化 `enterprise_report._translate_key`｜导出净化 `_EXPORT_STRIP_SELECTOR`｜台账 `ledger_governance`｜明细表 `table_governance`｜章节去重 `chapter_dedup`｜域间联动 `domain_linkage`｜护栏 `text_guardrails`｜**资料识别 `material_recognition._SUPP_ENTRIES`**。
★★ `numparse.AMOUNT_KEYS`：**漏登字段＝静默返 0**（与「解析失败」不可区分），新增字段名只追加表末。★★ `to_number(None)` 静默返 0.0；区分缺失vs0 须 `to_number_checked(v)->(val,ok)`。

## ★ 要件判定口径（2026-09-27）
存在即触发，不设阈值（禁「占比≥X%/张数≥N」，幅度只作 evidence）。法定标准保留（扣除限额/结转5年/2:1债资比/起征点），措辞改「引用法定口径」。闸门 `check_constituent_no_threshold`。

## ★★ 资料「是否已提供」两通路严格性刻意不同
`analysis_coverage.build_coverage` 可放宽；`redline_engine._available_materials` 影响 closure/confirmed → **必须严格只精确匹配 15 类**。后者放宽＝缺失证据误判已有→错升 confirmed(P0)。修 `_MATERIAL_SUPERCLASS` 绝不顺手放宽 redline_engine。

## ★★ 会计口径铁律
- **损益类科目禁取期末余额**：期末已结转本年利润，余额恒 0；且多数表把结转额也计入发生额 ⇒ 「借−贷」净额同样恒 0，只能取**本期发生额的总额侧**（成本/费用→借方，收入→贷方）。
- **科目余额表取数口径唯一权威 `financial_analyzer.trial_balance_amount(row, debit_positive)`**：损益类（17 个前缀，见 `PNL_CODE_PREFIXES`）取本期发生额总额侧、缺失才回退期末；资产负债类取**期末净额**（借−贷 / 贷−借）。派生 `extract_income_cost_from_trial_balance()` 供 pipeline 取收入/成本。真实实证：`data/uploads/1/1_928_2025年科目余额表.xlsx`（深圳海更 2025，156 行）6001/6401/6403/6602/6603/6801 期末双 0，收入 6,636,800.57、成本 4,187,220.84 只在发生额列。
- 损益类科目禁取期末余额 → 序时账取数按科目归集借方发生额；科目余额表仅「本期发生额」缺失时回退。cost_recon_detail 阈值内也产出，三处渲染必齐。

## ★★ 成本/费用归属唯一权威 `engine/account_classifier.py`
三态 `CLASS_COST 主营业务成本`/`CLASS_EXPENSE 期间费用`/`CLASS_UNDETERMINED 待核`（+`CLASS_CAPITAL`）。**判不出必须待核，严禁默认判成本**（＝虚增成本、压低毛利）。
- **结构性第一刀 `structural_kind(tax_code, unit, biz_type, text)`**：①业务类型 ②税收编码两位前缀（`TAX_CODE_CLASSES`：10/11 货物、20/30/40 服务、60 预付卡、61 代收代付）③计量单位 ④开票项目大类 ⑤品名含「服务」。服务/预付/代收代付 ⇒ 走 `_resolve_service` 服务轨道，**绝不业态兜底成成本**（真实验收漏网点：广告传媒 `*物流辅助服务*运输费` 曾被判成本）。
- 六层：硬排除（个人消费/资本性/预付卡）→ 行业核心投入（`industry_data.json core_inputs`，行业优先于通用表）→ 通用成本材料 → 需上下文层（拆 `INVENTORY_SUPPORT_KWS` 命中即成本但过**业态闸门** `_inventory_support_decision`：仅贸易/生产型，`AMBIGUOUS_KWS` 仍落待核）→ 通用费用（再分销售/管理/财务/研发）→ 业态兜底（贸易/生产→成本；服务→待核）。
- 派生出口（其它模块只引用不重抄）：`major_expense_keywords()`/`operating_expense_keywords()`/`expense_element_keywords(exclusive)`/`all_authoritative_keywords()`。闸门 `check_account_classifier_single_source`（交集≥5 且≥60%＝实质重抄→ERROR）+ `check_cost_expense_triad`。
- ★「采购来源口径」`verified_rule_engine._procurement_scope(pur, industry)`（VR016/VR066）：＝全部采购 − 确定费用类（成本与待核都算真实采购来源地）。**铁律：收窄统计范围的规则，不得影响其前置条件/门槛；口径定义只允许一个来源。**
- ★ 真实验收纪律：`pipeline.py` 曾漏 `from engine import account_classifier` 别名却在 4010 行用 `_account_classifier.*` ⇒ 全量 pytest 全绿但整条链路 NameError。**凡在 pipeline 引用新权威模块，必须加一条「导入真的存在」的断言**（如 `test_pipeline_binds_the_authority`）。真实验收脚本 `scripts/_accept_cost_expense.py`（公司3 只读复制成临时 9999；文件名必须 `公司id_文档序号_原始名` 三段）。

## ★ 红线驱动方法论（2026-09-06）
税务红线不因行业而变；行业只影响线索长相。四条铁律（`tests/test_redline_methodology.py` 锁死）：① **触红≠定性**；② **反证只认企业是否实际提交**，禁按资料类别关键词猜；③ 证据「已有/缺失」必须对齐 15 类稽查资料；④ 触红后置信度下限 0.60。报告标题必须是红线名。

## ★ 问题挖掘四层机制
规则触发 → 方法论证析 → 要素缺失型异常 → 假设-证据裁决（贝叶斯）。**发现≠确认**，缺失型疑点经竞争假设裁决，证据不足转置疑清单。
- `missing_element` 在 `engine/hypothesis_engine.py`：**缺失型分支必须位于 `if "制造" in desc` 等通用经营模式分支之前**。`run_inspection_questions(unconfirmed_findings=...)` 须在假设验证之后跑。
- 地区推断 `geo_infer.collect_regions` **始终剔除本企业所在省**。

## ★ 报告铁律（要点）
- 材料齐全度**不得以比例/百分比表述**，只报项数；`closure` 只内部用，不进正文。闸门 `check_material_completeness_no_ratio`（禁比例 + 禁模糊套话）。
- 标点规范化权威 `sentencekit.normalize_cjk_punct`，必须在 `enterprise_report._zh_normalize_obj` 与 `main._execute_tax_risk_analysis` 两处收敛点生效。闸门 `check_report_punctuation`。
- 覆盖扫描判据须**分级**：★强命中（红线名/domain/taxes）／○弱命中（constituents/资料名，旁证不计）。
- **闸门自证循环（第 8 坑）**：`check_constituent_sources_consistency` 判据 (b) 的合法集合**不得含被检查红线自己的 required_materials**。
- ★ 改源码优先用 **Edit 工具**；bytes 手工插入时中文锚点须 `str.encode("utf-8")`，且不查行尾就 `b.find(marker)` 会把字符串劈成两半。
- ★★ 报告数字绝不可被文本清洗改写（`strip_meta_prefix` 曾把「1.3万」的「1.」当编号剥掉）。通用修法：`_LEAD_NUM` 加负向前瞻 `(?!\d)` + 共用 `_is_list_number_mark()`。同类问题往往**有多处**（2026-09-26 只清了 `_LEAD_MARK` 漏了 `_LEAD_NUM`）。
- 行业专有名词原样；说人话只改系统/报告语。疑点 meta 行须自然句三段，禁「字段：值」。统一「涉嫌风险事项」，禁伪作执法文书。缺失≠0≠未发生：单边 diff 必须 None；申报表未取得禁写「实际缴纳0元」。截断必须可见（省略号「…」唯一信号，闸门 `check_evidence_text_not_truncated`，硬切片 `remark[:48]` 是缺陷）。空表必须解释。资金回流闭环：≤5% 等额双向/≤30% 近似双向/>30% 单侧不计。
- **结论句必须有宾语**：报「缺 N 项」必须点出具体资料名（≤3 个顿号连，>3 报「N 项（详见下表）」）。
- **★ 护栏不得中性化待核问句**：`text_guardrails._OVERCLAIM_RULES` ⑥ 只拦断言；含「成立还是不成立／成立与否／能否定性成立」等 `_HEDGE_QUERY` 命中时只应用 ①~⑤。回归 `tests/test_report_credibility.py::TestOverclaimGuard`（双向锁）。
- **呈现顺序**（唯一 `enterprise_report._RISK_PRESENT_ORDER`；`_LEVEL_RANK` 是标度、当呈现序用会让待核验排到低风险前）；监管态度序＝重点关注(高)→补证核实(中)→待核验→限期补正资料→提示提醒(低)。闸门 `check_conclusion_and_suspicion_order`。
- **★ 禁脱敏**：`pii_guard.py` 已删；企业版报告与内部底稿同样不脱敏。闸门是**反向**的（模块缺失+AST 扫脱敏符号+报告实测星号形态）。

## ★★ 闸门方法论（写闸门 / 反向验证，8 条坑）
① **闸门不得只做「静态名检查」**（第 7 坑）：判据——「保留函数名、改坏行为」能否绕过？实录 `check_audit_doctrine` 对兜底降级点补行为断言（构造缺资料驱动 → 断言降 `MISSING_DRIVEN_LEVEL_CAP`+`level_downgraded_from`+score≤4+`terminal_state`）后三种绕法全红。② 反向验证须覆盖**改参/改 `if`/删实现**三类。③ 破坏点须字节级打准（中文锚点 `str.encode("utf-8")`）。④ 破坏后须 `os.utime(未来120s)`+`PYTHONDONTWRITEBYTECODE=1`（防 `.pyc` 假绿）；同进程探针需 `del sys.modules[...]`+`importlib.invalidate_caches()`。⑤ 还原一律 `write_bytes(orig)`，**禁 `git checkout --`**（会连坐回滚同文件其它未提交改动）。⑥ pytest 节点选择器必须与文件路径**拼成同一 argv 元素**。⑦ 备份只放 `scripts/_bak*/` 或 `scripts/_archive/`（放 `engine/` 被 audit 判跨模块第二套实现）。⑧ 「基线绿」不算验证，**必须坏副本全红才算**。
- ★ **验收口径**：`tools/audit_consistency.py` 的 `ERROR 0 | WARN 0` 只是 COUNT 维度小结；文本维度由 `engine/shared_content_sync.py` 另起一节输出，须分维度读，**禁拿 tail/汇总行当全局验收**。
- 专用探测器通道 `special_redline_detectors._EXTRA_DETECTORS`；`_scan_ids` 认领写法＝**先 `redline_id = "RL-XXX"` 再传参**。

## ★ 闸门清单（全须 ERROR 0）
`check_report_consistency`/`check_finding_meta_wording`/`check_risk_item_section_wording`/`check_chapter_template_dedup`/`check_domain_missing_material_emits_finding`/`check_finding_level_legality`/`check_audit_doctrine`/`check_coverage_source_wiring`/`check_cost_recon_render`/`check_overall_conclusion_no_dup`/`check_report_chapter_integrity`/`check_report_plain_language`/`check_constituent_no_threshold`/`check_constituent_sources_consistency`/`check_material_completeness_no_ratio`/`check_industry_consistency`/`check_numparse_single_source`/`check_doc_type_category_map`/`check_evidence_text_not_truncated`/`check_material_alias_drift`/`check_no_lock_reentrancy`/`check_evidence_rows_semantic_match`/`check_account_classifier_single_source`/`check_cost_expense_triad`/`check_benchmark_caution_single_source`/`check_conclusion_and_suspicion_order`/`check_report_punctuation`/`check_venv_parity`。
**新闸门必须做反向验证**。验收基线：audit ERROR 0/WARN 0；verify_release All passed；全量 pytest 全绿（`--junitxml=scripts/_bak/x.xml` 落盘解析，stdout 摘要常被 safe-delete 守护截断）。

## ★★ 资料登记名铁律（2026-10-01 用户拍板）
- 登记名必须**逐字 == 红线 `required_materials` 文案**（`redline_engine._map_finding` 严格相等 → 只补别名无效）。
- 关键词必须留长度差；**通用解法：给 `_SUPP_ENTRIES` 每条追加「登记名全称」**（自身既有关键词的严格超串 ⇒ 打平结构上不可能）。
- **铁律：红线里写的资料名必须是已登记名；补新资料名必须同步登记 `_SUPP_ENTRIES`**，否则只是把静默缺口换成永久缺口。闸门 `check_material_alias_drift`；`_MATERIAL_SUPERCLASS` 键必须是**泛化需求名**（`check_coverage_source_wiring` bad_keys）。

## ★★ 两个已结案的事故模式
- **自死锁 `check_no_lock_reentrancy`**：`_run_analysis_thread` 在 `with _analysis_lock:` 内取同一不可重入锁 → 线程自杀等（CPU 0%、前端 99%）。修法：无锁快照读 + 检查点写回移出锁外。定位用 `py-spy dump --pid`（**wmic 被安全策略拦**）。
- **假证据 `check_evidence_rows_semantic_match`**：detector 只交 `observed_metrics` 没交 `evidence_rows` ⇒ 通用兜底按金额 TOP5 给每条发现挂同一批凭证；`_salary_row` 自写键表与真实结构对不上 ⇒ 55 行金额全静默返 0。原则：**宁缺毋错；「按金额 TOP-N 取证」一律是错的；兜底只作救命不作正路。** 同源收敛 `findingkit.cjk_bigrams`。

## ★★ 行业判定（`engine/industry_resolver.py` 唯一权威）
- **定行业**：「销售/批发/零售/贸易/购销/经销/进出口」是万能尾巴 → 服务型（广告/传媒）曾被 100% 判商贸、对标基准全错。修法 `scope_industry_hint(scope_text, company_name)`：只采纳映射到 `service_industries` 且**不属于** `_TRADE_FALLBACK_INDUSTRIES` 的词；命中多条按长度优先、等长取 `industry_map` 声明顺序；商品/物料名不算行业（R1）。
- **改行业** `reassess_industry(...)`：只能推翻、不能凭空定（三态 change/keep/insufficient）。门槛：current 是购销兜底→≥1 路一致即推翻；current 高权威→≥2 路同指才改；并票→keep。接线 `pipeline._run_analyze` Phase 2 前。
- ★**经营范围是宽口径许可清单，不是「实际只做这一行」** ⇒「登记≠销项发票品名」**≠**「超范围经营」。三态 `scope_covers_industry(industry, scope_text)`：True（已被涵盖，只出中性 note）／False（范围文本无该行业级关键词，中性提核查）／None（无范围文本或基准库无关键词，**不认定冲突**）。关键词 `industry_scope_keywords()` 反查 `industry_data.json` 的 kw→行业倒排＋行业名去尾缀＋门类通用词，**新增/调行业只改数据表**。
- **承载链（下游禁止重算）**：`resolve_industry` 带出 `scope_covers`/`scope_note` → `pipeline` 两处写入 `target_entity["_industry_resolved"]` → `overall_conclusion._industry_scope_covers(te)` **只读** → `main._write_resolved_industry()` 回写 `Company.industry_resolved/industry_resolved_source` → `_company_to_card` 前端优先显示本轮口径。
- 行业基准单一权威 `engine/industry_benchmark.py::BENCHMARK_CAUTION(_SHORT)`：基准只有线索/预警价值，不构成硬化判定依据（闸门 `check_benchmark_caution_single_source`）。

## 运行环境（关键陷阱）
- base python 缺 fastapi；凡 import main 的脚本/测试/全量核对**必须**用 `C:/Users/Administrator/.workbuddy/binaries/python/envs/default/Scripts/python.exe`。
- ★★ **两套 venv 能力必须对齐**：托管 venv 少读取类依赖 → App 读得到、脚本**静默**读不到。闸门 `scripts/_check_venv_parity.py`（并入 `_verify_run_no_silent_failure.py`）。
- **文件写入铁律**：`open(p,"wb")` 会**先截断**，补丁脚本中途异常会把目标文件写空（实录 29549 B → 0 B）。必须「内存中算完 → 单次写 → 写后自检（长度+锚点）」。
- 全量 pipeline 约 5 分钟；改 .py 两步：①重启 uvicorn（无热重载）②重跑一键分析。
- ★ **端口别混**：用户实际用 **8001**（`start8001.bat`，须带 `APP_COOKIE_SECURE=0`，否则 http 下浏览器不发 auth_token、全 401）；`start.sh` 是 **8000**。探活三态：`GET /`→302、`GET /api/companies`→401、`POST /api/auth/login`→400＝服务在响应；只有端口无 LISTENING 才是真挂。curl 必须 `--noproxy '*'`。
- `nohup … &` 随会话被杀 → 起服务用 `run_in_background=true` 前台阻塞。
- **行尾铁律**：新建文件必须 CRLF（bare-LF=0）；`main.py`、`tools/audit_consistency.py`、`tests/test_report_credibility.py` 是 LF；记忆 md 是 CRLF。
- 提交 CRLF 工作区文件须 `git -c core.autocrlf=false add <file>`（`git add -c` 报 unknown switch）；commit **显式指定文件，勿 `git add -A`**。
- safe-delete 守护按轮累计 `os.remove` 超阈值(50) 会 SIGTERM 长任务——环境问题非产品缺陷。

## ★ 已完成的重大变更
- AGI 子系统整体移除（先 A/B 实测证明对①零增量）。★ 甄别：`_build_causal_narratives`/`_bayesian_causal_network`/`_ema_self_learning` 在 domain_analysis.py（核心①）→**保留勿删**。
- 盲区红线 27→0：`gap_risk_detectors` 6 探测补 `redline_id`+`_scenario_governed`；新增 `engine/special_redline_detectors.py` 表驱动 22 条。
- 精度修复：探测器曾误报（销售类风险命中在**进项**侧；公积金「未缴存」命中在**有**缴存）→ 加 `source`(sales/purchase)、`require`、`mode=absence`。**铁律：信号必须对齐风险发生侧。① 的价值在真实，不在数量。**
- 要件独立数据源全库补齐（91 条/453 要件，占位符 73(53.3%)→0）；要件口径改「存在即触发」。
- 行业判定三态 + 回写 `Company.industry_resolved`（2026-10-02，端到端 company_1 实测 `industry_resolved='广告传媒'`）。
- 科目余额表取数口径收敛（`financial_analyzer.trial_balance_amount`），修 pipeline 收入/成本静默读 0（2026-10-02）。
