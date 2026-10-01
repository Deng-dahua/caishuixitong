# 项目长期记忆（caishuixitong 财税风险防控系统）

## ★ 能力优先级（最高约束）
- **① 风险分析能力=重中之重**（查出多少/多少种真实风险）；**② 报告编辑=锦上添花**；其余做减法。每轮自答「是否提高了①」。用户原话「该做就做，别跳过！！」
- 检出基线五档：①真检测器且触发 ②仅软匹配 ③有检测器未触发 ④仅兜底 ⑤无数据路径(盲区)。权威源 `scripts/_audit_redline_coverage.py`（**口径：scripts/ 下一次性脚本不算检测器来源**）。当前（红线 91）：盲区 0、有真实检测器 78、仅兜底 11。另两把尺：`_audit_unfired_redlines.py`、`_gap_constituent_hits`。
- 新增红线必过「9 处登记」（见 `caishuixitong-redline-engine` skill），漏一处 audit 报 WARN。
- ★★ 先查「是否已有 VR 仅缺 redline_id 归属」再补新检测器（零成本提①）：`scripts/_vr_rl_affinity.py`，闸门 `tests/test_vr_redline_declaration.py`。**只认扫描器真算过的要件（宁缺勿错）**。
- 加法范式：`engine/<x>_detector.py::detect_<x>()` → 带 `redline_id`+`constituent_hits` 的发现 → 接 `pipeline._run_analyze`；字段只读 `fieldkit`/`numparse`，禁写私有 `_buyer/_amount/_tax`。

## ★ 项目定位
上传什么查什么，以稽查专家身份查实所上传资料的全部税务风险，不等资料齐全；给解除方式+需补自证资料。终局＝证据闭合 或 自证清白。所分析风险全部入报告并标注证据地位。

## ★ 架构红线（违反即事故）
- 路由唯一收敛 `main::_execute_tax_risk_analysis`→`pipeline::_run_analyze`。
- 封印唯一产出点：`seal_governed_findings` 内写最终加工，写管道被丢弃。
- 防误判打标须作用 `_scenario_execution["findings"]` 且在封印前；打 `all_findings` 零生效。
- 「调保守阈值」伪命题；裁决三态＝确认/降级/unconfirmed；禁为降误报调高确认阈值。
- 改 pipeline 域调用后须真跑全量核对 `scripts/four_reports/company_1_full.json` 顶层 `overall_level`（`{"ok":false}`＝崩溃）。

## ★ 五条静默吃掉发现的机制（新域/新发现必过五关）
1. **输出封印**：`seal_governed_findings` 只留 `_scenario_governed is True` 的条目；追加进 `_scenario_execution["findings"]` 的探测 finding **必须自己打 `_scenario_governed=True`**，否则静默丢弃（`gap_risk_detectors` 6 个探测器曾是真死代码）。
2. 等级合法性：权威词表 极高风险5/高风险4/中风险3/待核验2/信息1/低风险0，词表外静默丢。
3. 文案门禁：`review_finding` 净化；新增枚举补 `_ENUM_FIELDS`。
4. 递归遇循环引用爆栈→出口加工静默跳过。铁律：遍历 report_data 一律**迭代+`id()`去环，禁递归**。
5. 未赋值局部变量/异常被 except 吞没→整段从未生效（实录 `_extract_material_intel` UnboundLocalError）。铁律：except 留痕≥warning；关键产出非空加断言；**变量名复用(`for d in…`)是被低估的坑**。闸门：pipeline_log 含「异常」即本轮静默失效。

## ★ 单一权威模块清单（多头维护=事故）
数值解析 `numparse`｜发票字段 `fieldkit`｜月份键 `findingkit`｜行业 `industry_resolver`｜红线配对 `tax_redlines.score_redline/match_redline_grounded`｜印花税 `domain_analysis._STAMP_DUTY_ITEMS`｜报告文本 `sentencekit`｜证据现状 `evidence_chain`｜净化 `_zh_normalize_obj`｜说人话 `plain_language`｜风格 `report_style`｜红线库 `tax_redlines`(constituents/constituent_sources/required_materials)｜要件独立核对 `constituent_checkpoint`｜要件阈值 `constituent_threshold`｜法条 `legal_citation`｜PDF/OCR `_parse_pdf_generic`+`_ocr_png_bytes`｜键汉化 `enterprise_report._translate_key`｜导出净化 `_EXPORT_STRIP_SELECTOR`｜台账 `ledger_governance`｜明细表 `table_governance`｜章节去重 `chapter_dedup`｜域间联动 `domain_linkage`｜护栏 `text_guardrails`｜**资料识别 `material_recognition._SUPP_ENTRIES`（补自证资料唯一权威；`_DOC_TYPE_TO_CATEGORY` 的 sup_* 映射由 `_SUPP_REC` 自动装配，不许手改 enterprise_report.py）**。
★★ `numparse.AMOUNT_KEYS`：**漏登字段＝静默返 0**（与"解析失败"不可区分）。新增字段名只加此处、**追加表末**。
★★ `numparse.to_number(None)` 静默返 0.0；区分缺失vs0 须用 `to_number_checked(v)->(val,ok)`。

## ★ 要件判定口径：存在即触发，不要阈值（2026-09-27）
情形≥1次即命中；幅度只作 evidence 不设门槛。禁「占比≥X%/张数≥N」。法定标准保留（扣除限额/结转5年/2:1债资比/起征点），措辞改「引用法定口径」。闸门 `check_constituent_no_threshold`。cap `_enterprise_situations(cap≥)` ≥红线最大要件数（现 max 5，已设 8）。

## ★★ 资料「是否已提供」两通路严格性刻意不同
`analysis_coverage.build_coverage` 可放宽；`redline_engine._available_materials` 影响 closure/confirmed→**必须严格只精确匹配 15 类**（主路径取 material_readiness["provided"]，回退只用 file_results 原始 type）。后者放宽→缺失证据误判已有→错升 confirmed(P0)。修 `_MATERIAL_SUPERCLASS` 绝不顺手放宽 redline_engine。

## ★★ 会计口径铁律
损益类科目禁取期末余额：成本(6401)/收入(6001)/费用期末已结转→余额恒 0；须取序时账按科目归集借方发生额；科目余额表仅「本期发生额」列回退。cost_recon_detail 阈值内也产出，三处渲染必齐。

## ★★ 成本/费用归属唯一权威：engine/account_classifier.py
三态 `CLASS_COST 主营业务成本`/`CLASS_EXPENSE 期间费用`/`CLASS_UNDETERMINED 待核`（+`CLASS_CAPITAL`）。**判不出必须待核，严禁默认判成本**（默认判成本＝虚增成本、压低毛利）。
六层：硬排除（个人消费/资本性/预付卡）→ 行业核心投入（`industry_data.json core_inputs`，行业优先于通用表）→ 通用成本材料 → 需上下文层（运输/水电/包装料/辅料/维修/租赁/检测…，无项目上下文→待核）→ 通用费用（销售/管理/财务/研发）→ 业态兜底（贸易/生产型→成本；服务型→待核）。
派生出口（其它模块**只引用不重抄**）：`major_expense_keywords()`/`operating_expense_keywords()`/`expense_element_keywords(exclusive)`/`all_authoritative_keywords()`。已收敛 4 处引用。闸门 `check_account_classifier_single_source`（交集≥5 且≥60%＝实质重抄→ERROR）+ `check_cost_expense_triad`。
- **「采购来源口径」`verified_rule_engine._procurement_scope(pur, industry)`（VR016/VR066 共用）**：= 全部采购 − 确定费用类（成本与待核都算真实采购来源地，只有办公/餐饮/住宿/差旅/咨询/利息才剔）。**铁律：收窄统计范围的规则，不得影响其前置条件/门槛；口径定义只允许一个来源。**
- **真实验收纪律**：`pipeline.py` 曾漏 `from engine import account_classifier` 别名却在 4010 行用 `_account_classifier.*` ⇒ 全量 pytest 全绿但一键分析整条链路 NameError。**凡在 pipeline 引用新权威模块，必须加一条「导入真的存在」的断言。**
  真实验收脚本 `scripts/_accept_cost_expense.py`（公司 3 真账套只读复制成临时 9999；文件名必须 `公司id_文档序号_原始名` 三段，否则 pipeline 磁盘扫描整份跳过）。

## ★ 红线驱动方法论（2026-09-06 确立）
税务红线不因行业而变；行业只影响线索长相。主线：红线判定→线索链→证据链→论证链。四条铁律（`tests/test_redline_methodology.py` 锁死）：① **触红≠定性**，触红只取决于线索链是否给出可量化触红事实，与证据闭合度无关；② **反证（正当理由）只认企业是否实际提交**，禁按资料类别关键词猜；③ 证据「已有/缺失」必须对齐 15 类稽查资料，禁模糊命中；④ 触红后置信度下限 0.60。报告标题必须是红线名（「RL-XXX 采购成本无对公付款资金证据」），禁「待核事实：XXX核验」空壳。

## ★ 问题挖掘四层机制
规则触发 → 方法论证析 → 要素缺失型异常（零运费/无场地/无能耗/必要费用缺失）→ 假设-证据裁决（贝叶斯）。原则：**发现≠确认**，缺失型疑点必须经竞争假设裁决，证据不足转置疑清单，绝不自动定罪。
- `missing_element` 实现在 `engine/hypothesis_engine.py`：**缺失型分支必须位于 `if "制造" in desc` 等通用经营模式分支之前**（否则「制造业无生产能耗」恒真）。`inspection_questions.run_inspection_questions(unconfirmed_findings=...)` 消费 unconfirmed，且须在假设验证**之后**跑。它是经营实质整体裁决（7 要素综合，单一要素补全不足以翻案）。
- 地区推断 `geo_infer.collect_regions` **始终剔除本企业所在省**（旧逻辑在「全部同省」时误把本省当外埠）。

## ★ 报告铁律（要点）
- **材料齐全度不得以比例/百分比表述**，只报项数（还缺＝待核+缺失）；`closure` 只内部用于判定能否定性，**不进正文**。闸门 `check_material_completeness_no_ratio`（禁比例 + **禁模糊套话**：须写明①定性对象②排除对象③还缺的具体资料名）。
- 标点规范化权威 `sentencekit.normalize_cjk_punct`；必须在两个输出收敛点生效——① `enterprise_report._zh_normalize_obj` ② `main._execute_tax_risk_analysis` 最终出口。保护小数 `0.00` 与扩展名 `.xlsx`。闸门 `check_report_punctuation`。
- ★★ 报告数字绝不可被文本清洗改写：`sentencekit.strip_meta_prefix` 曾把「1.3万」的「1.」判成列表编号剥掉 → 报告写成「3万」、「0.5」写成「5」（**金额凭空少一个数量级**）。修法为通用规则：`_LEAD_NUM` 加负向前瞻 `(?!\d)`（分隔符号后紧跟阿拉伯数字＝小数数位，不是编号），并抽 `_is_list_number_mark()` 供 `_LEAD_MARK`/`_LEAD_NUM` 两路径共用。教训：同类问题往往**有多处**——2026-09-26 只清了 `_LEAD_MARK` 字符类里的 `\d`，漏了 `_LEAD_NUM`。
- 行业专有名词原样（虚开/增值税/主营成本）；说人话只改系统/报告语。疑点 meta 行须自然句三段（涉嫌方向/结论+可信度/税种与潜在税额），禁「字段：值」。统一「涉嫌风险事项」，禁伪作执法文书。缺失≠0≠未发生：单边 diff 必须 None；申报表未取得禁写「实际缴纳0元」。截断必须可见：省略号「…」唯一信号（硬切片 `remark[:48]` 是缺陷，闸门 `check_evidence_text_not_truncated`）。空表必须解释。红线名是「要件包」，只命中非命名要件时标题裁剪+声明「未就〈前提〉作出认定」。资金回流闭环：≤5%等额双向/≤30%近似双向/>30%单侧不计。
- **结论句必须有宾语、必须有具体信息**：报「缺 N 项」必须点出具体资料名（≤3 个顿号连，>3 报「N 项（详见下表）」并指向明细表）。
- **★ 护栏不得中性化待核问句**：`text_guardrails._OVERCLAIM_RULES` ⑥ 只拦「已定性成立」的**断言**；句中含「成立还是不成立／成立与否／能否定性成立／是否足以定性」（`_HEDGE_QUERY` 命中）说明在**问** → 只应用 ①~⑤、**跳过 ⑥**。回归测试 `tests/test_report_credibility.py::TestOverclaimGuard`（双向锁：问句原样/断言照旧被降）。
- **呈现顺序**：总述章段序＝整体风险综合评价(结论先行置首)→编制声明→检查范围与结果概览→行业口径→按风险性质归纳→风险等级评定→分层点名→纳税遵从总体看法→未完成→下一步→监管态度→需要说明。疑点序唯一权威 `enterprise_report._RISK_PRESENT_ORDER`（**反例：`_LEVEL_RANK` 是等级高低标度，当呈现序用会让待核验排到低风险之前**）。监管态度序＝重点关注(高)→补证核实(中)→待核验→限期补正资料→提示提醒(低)。闸门 `check_conclusion_and_suspicion_order`。
- **★ 禁脱敏**：`pii_guard.py` 已整体删除；企业版报告与内部底稿同样不脱敏，自然人姓名原样。闸门是**反向**的（模块缺失+全库 AST 扫脱敏符号+报告实测「首字+等长星号」形态）。

## ★★ 闸门方法论（写闸门 / 反向验证，8 条坑）
★★① **闸门不得只做「静态名检查」**（2026-10-02 第 7 坑）：`if need not in source` 只证明「函数被引用过」，证明不了「行为还在」。判据——**「保留函数名、改坏行为」能否绕过？能即假闸门。** 实录 `check_audit_doctrine` 对兜底降级点：改成空函数 / 去掉 `missing_driven=True` 全绿（D2 红线形同虚设）；补行为断言（构造缺资料驱动「极高风险/score=9」→断言降 `MISSING_DRIVEN_LEVEL_CAP`+`level_downgraded_from`+score≤4+`terminal_state`+`resolve_steps`，且有据中风险零误伤）后三种绕法全红。
② 反向验证必须覆盖三类绕法：**改参 / 改 `if` / 删实现**。
③ 破坏点必须字节级打准；中文锚点用 `str.encode("utf-8")`，纯 ASCII 用 `b'...'`（bytes 字面量不能含中文）。
④ 破坏后必须 `os.utime(未来120s)` + `PYTHONDONTWRITEBYTECODE=1`（防同秒 `.pyc` 假绿）；同进程探针同样被 pyc 骗 → 需 `del sys.modules[...]` + `importlib.invalidate_caches()`。
⑤ 还原一律 `write_bytes(orig)`，**禁 `git checkout --`**（会连坐回滚同文件其它未提交改动）。
⑥ pytest 节点选择器必须与文件路径**拼成同一 argv 元素**（拆参→`rc=4` + `directory argument cannot contain :: selection parts`，曾让 5 个 CASE 全判「未变红」）；反向验证脚本**必须打印子进程 stderr 尾巴**做诊断。
⑦ 备份只放 `scripts/_bak*/` 或 `scripts/_archive/`（放 `engine/` 被 audit 判跨模块第二套实现，实锤过）。
⑧ 反向验证的「基线绿」不算验证，必须坏副本全红才算。
- ★ **验收口径**：`tools/audit_consistency.py` 的 `ERROR 0 | WARN 0` 只是 **COUNT 维度小结**；文本维度（共享内容一致性）由 `engine/shared_content_sync.py` 另起一节输出，须分维度读，**禁拿 tail/汇总行当全局验收**。
- 专用探测器通道 `special_redline_detectors._EXTRA_DETECTORS`；`_scan_ids` 认领的写法＝**先 `redline_id = "RL-XXX"` 再传参**（内联会被漏扫）。

## ★ 闸门清单（全须 ERROR 0）
`check_report_consistency`/`check_finding_meta_wording`/`check_risk_item_section_wording`/`check_chapter_template_dedup`/`check_domain_missing_material_emits_finding`/`check_finding_level_legality`/`check_audit_doctrine`/`check_coverage_source_wiring`/`check_cost_recon_render`/`check_overall_conclusion_no_dup`/`check_report_chapter_integrity`/`check_report_plain_language`/`check_constituent_no_threshold`/`check_constituent_sources_consistency`/`check_material_completeness_no_ratio`/`check_industry_consistency`/`check_numparse_single_source`/`check_doc_type_category_map`/`check_evidence_text_not_truncated`/`check_material_alias_drift`/`check_no_lock_reentrancy`/`check_evidence_rows_semantic_match`/`check_account_classifier_single_source`/`check_cost_expense_triad`/`check_benchmark_caution_single_source`/`check_conclusion_and_suspicion_order`/`check_report_punctuation`/`check_venv_parity`。
**新闸门必须做反向验证**（故意破坏→闸门必须变红），否则闸门是假的。
验收基线：audit ERROR 0/WARN 0；verify_release All passed；全量 pytest 974 passed / 0 fail / 0 err。

## ★★ 资料登记名铁律（2026-10-01 用户拍板）
- 登记名必须**逐字 == 红线 `required_materials` 文案**（`redline_engine._map_finding` 严格相等 → 只补别名完全无效）。
- 一个 doc_type 只服务一种红线文案；冲突时**拆独立 doc_type**（如 `sup_equity_transfer_contract_plus`）。
- 关键词必须留长度差（`>` 才更新→等长先声明者赢）。**通用解法：给 `_SUPP_ENTRIES` 每条追加「登记名全称」**（自身既有关键词的严格超串 → 长度唯一 → 打平结构上不可能）。本次消掉 12 处打平。→ 反向验证：剔掉长词打平须回升 0→15 且 224 个文件名识别差异必须为 0。
- 闸门 `check_material_alias_drift`（撞车/漂移/跨项等长打平）；`_MATERIAL_SUPERCLASS` 键必须是**泛化需求名**（闸门 `check_coverage_source_wiring` bad_keys）。
- **铁律：红线里写的资料名必须是已登记名；补新资料名必须同步登记 `_SUPP_ENTRIES`，否则只是把静默缺口换成永久缺口。**

## ★★ 自死锁事故 check_no_lock_reentrancy（2026-10-01）
`_run_analysis_thread` 在 `with _analysis_lock:` 内调 `_write_analysis_checkpoint`→`_is_result_deleted` 再取同一**不可重入**锁 → 线程自杀等（CPU 0%、前端 99%、报告已落盘取不到）。修法：无锁快照读 + 成功检查点写回移出锁外 + except 分支保持锁内。定位：`py-spy dump --pid` + Windows API GetProcessTimes（**wmic 被安全策略拦**）。

## ★★ 证据明细表「不匹配」事故 check_evidence_rows_semantic_match（2026-10-01）
假证据两条根因：① detector 只交 `observed_metrics` 没交 `evidence_rows` → 通用兜底接管 → **按金额 TOP5 给每条发现挂同一批最大额凭证**（凭证分支词含「凭证」+文案写「参保**凭证**」二义）；② `_salary_row` 自写键表与真实结构（`name/salary/net/gross/period_start`）对不上 → 55 行金额**全静默返 0**。
修法：detector 交**自有 `evidence_rows`**（兜底按 `if f.get("evidence_rows"): continue` 跳过）+ 走 `fieldkit` + 语义/期间对齐守卫。
原则：**宁缺毋错；「按金额 TOP-N 取证」一律是错的；静默返 0 是最隐蔽的假证据；兜底只作救命不作正路。** 反向验证须**硬编码**事故态那 8 行（从产物读会被全量重跑覆盖→失真报绿）。
同源收敛：`pipeline._cjk_bigrams`/`enterprise_report._cjk_bigrams` → 唯一 `findingkit.cjk_bigrams`。

## ★★ 行业判定（「定行业」与「改行业」两件事分开）
- **定行业**：`industry_resolver._trade_benchmark` 曾只要有「商贸」键就**无条件 return 商贸**，完全不看经营范围；而「销售/批发/零售/贸易/购销/经销/进出口」是万能尾巴 → 服务型（如广告/传媒）100% 判商贸、对标基准全错。修法 `scope_industry_hint(scope_text, company_name)`：只采纳映射到 `service_industries` 且**不属于** `_TRADE_FALLBACK_INDUSTRIES` 的词；命中多条按**关键词长度优先、等长取 `industry_map` 声明顺序**；商品/物料名不算行业（R1）。`resolve_industry`/`match_benchmark` 统一「先行业级线索，找不到才走购销兜底」。
- **改行业**：`reassess_industry(current, *, purchase_goods, material_hints, contract_text, current_source, pipeline_log)`。用户原话「行业应随资料摄入重判确认/变更」→ 落地为**只能推翻、不能凭空定**（三态 change/keep/insufficient）；先问证据够不够推翻，再问是不是同一行业。门槛：current 是购销兜底→≥1 路一致即推翻；current 高权威→≥2 路同指才改；并票＝无共识→keep。接线 `pipeline._run_analyze` Phase 2 前，change 时同步 `main_biz_cost` 并留痕；测试锁 `reassess_industry as _reassess` 与 `_reassess(` 两形态。
- 遗留：触发条件太窄、未用进项品名/合同类型/自由文本频次投票、重判结果未回灌全部下游且无闸门。

## ★ 行业基准口径单一权威（2026-10-02）
非官方＝`static/industry_data.json` / `industry_benchmark` 的**行业基准区间**（第三方公开统计参考值）；官方＝本企业从自己上传资料取到的**实测值**。裁定：基准**只有线索/预警参照价值，不构成硬化判定依据**，以它为要件的表述一律「对照参照、偏离只作待核线索」。唯一常量 `engine/industry_benchmark.py::BENCHMARK_CAUTION(_SHORT)`，`tax_redlines`/`redline_benchmark`/`domain_analysis`/`enterprise_report` 全引用，禁第二份字面声明（闸门 `check_benchmark_caution_single_source`）。

## 运行环境（关键陷阱）
- base python 缺 fastapi；凡 import main 的脚本/测试/全量核对**必须**用 `C:/Users/Administrator/.workbuddy/binaries/python/envs/default/Scripts/python.exe`。
- ★★ **两套 venv 能力必须对齐**：托管 venv 少读取类依赖 → App 读得到、脚本**静默**读不到。已补 xlrd/python-docx/python-pptx/pytesseract/reportlab。闸门 `scripts/_check_venv_parity.py`（读取类缺失=ERROR；版本漂移 INFO 不阻断），已并入 `_verify_run_no_silent_failure.py`。
- 全量 pipeline 约 5 分钟；改 .py 两步：①重启 uvicorn（无热重载）②重跑一键分析。
- ★ **端口别混**：用户实际用 **8001**（`start8001.bat`，须带 `APP_COOKIE_SECURE=0`，否则 http 下浏览器不发 auth_token、全 401）；`start.sh` 是 **8000** 的另一实例。
- 探活三态（区分「挂了」vs「鉴权」）：`GET /`→302、`GET /api/companies`→401、`POST /api/auth/login`→400，**都说明服务在响应**；只有端口无 LISTENING 才是真挂。curl 必须 `--noproxy '*'`（否则代理返回 502 误导）。
- `nohup … &` 在 Bash 工具里随会话被杀 → 起服务用 `run_in_background=true` **前台阻塞**，别加 `&`/nohup。
- **行尾铁律**（改动前先查）：新建文件必须 CRLF（bare-LF=0）；`main.py`、`tools/audit_consistency.py`、`tests/test_report_credibility.py` 是 LF；`engine/sentencekit.py`、`tests/test_audit_doctrine.py`、记忆 md 是 CRLF。用 `split("\n")/join("\n")` 处理过的文件要重查。`engine/material_recognition.py` 曾因此 353 个 CRLF 全丢。
- 提交 CRLF 工作区文件须 `git -c core.autocrlf=false add <file>`（`git add -c` 会报 unknown switch）；commit 时**显式指定文件，勿 `git add -A`**（工作树有 pre-existing 的 start*.bat 删除等）。
- safe-delete 守护按轮累计 `os.remove` 超阈值(50) 会 SIGTERM 长任务——环境问题非产品缺陷。pytest 计数改用 `--junitxml=scripts/_bak/x.xml` 落盘 + `ElementTree` 解析（stdout 摘要行常被截断）。

## ★ 已完成的重大变更
- AGI 子系统整体移除（先 A/B 实测证明对①零增量）：删 11 引擎模块。★ 甄别：`_build_causal_narratives`/`_bayesian_causal_network`/`_ema_self_learning` 在 domain_analysis.py（核心①）→**保留勿删**；`static/*.json` 被未删核心模块读取→保留。
- 盲区红线 27→0：`gap_risk_detectors` 6 探测补 `redline_id`+`_scenario_governed`；新增 `engine/special_redline_detectors.py` 表驱动 22 条。
- 精度修复：探测器曾误报（销售类风险命中在**进项**侧；公积金「未缴存」命中在**有**缴存）→ 加 `source`(sales/purchase)、`require`、`mode=absence`。**铁律：信号必须对齐风险发生侧。① 的价值在真实，不在数量。**
- 要件独立数据源全库补齐（91 条/453 要件），占位符 73(53.3%)→0。
- 其余大收敛（呈现顺序 / 禁脱敏 / 行业基准单一权威 / account_classifier 单一权威 / 资料登记名）已在本文各节记录。
