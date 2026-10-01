# 项目长期记忆（caishuixitong 财税风险防控系统）

## ★ 红线驱动方法论（2026-09-06 确立，替代「按行业套场景」）
**核心立场**：税务红线不因行业而变。行业只影响「线索长什么样」，不影响
「红线是什么」。一旦符合某项风险情形即触碰红线；原架构按行业场景输出
「待核事实：XXX核验」，从不回答「触碰了哪条红线」，已废弃。
**主线**：红线判定 → 线索链（怎么发现的）→ 证据链（要什么证据）→ 论证链（主张/反证/裁决）。
**模块**：`engine/tax_redlines.py`(红线库86条，运行期 len(REDLINES) 实时计数) / `clue_chain.py` / `evidence_chain.py` /
`argumentation.py` / `redline_engine.py`(按红线归并，不按 finding 罗列)；
pipeline 场景执行后接入，结果入 `comprehensive.redline_detection`；
报告 `enterprise_report._build_redline_problems` 五段式输出。
**四条判定铁律（契约测试 tests/test_redline_methodology.py 锁死）**：
1. 触红≠定性：是否触红**只取决于线索链是否给出可量化触红事实**，与证据链
   闭合度无关；闭合度只决定能否定性。（坑：曾用闭合度 0.35 卡触红，吞掉真实疑点）
2. 反证（正当理由）**只认企业是否实际提交**，严禁按资料类别关键词猜测。
   （坑：「银行承兑汇票」含「转账」二字被判反证已提供 → 147万成本无付款流水被误排除）
3. 证据「已有/缺失」必须对齐 15 类稽查资料，**禁止模糊命中**。
   （坑：清单含「渠道订单」把「采购合同」判已有 → 闭合度虚高100% → 错误定性）
4. 触红后置信度下限 0.60（符合构成要件就不能说成没把握）。
**报告标题必须是红线名**（如「RL-PTY-001 采购成本无对公付款资金证据」），
禁止再出现「待核事实：XXX核验」空壳。

## 问题挖掘四层机制（设计基线，2026-08 确立）
1. 规则触发（阈值/关键词命中）2. 方法论证析（行业方法论比对）3. 要素完备性/缺失型异常（"该有的没有"：零运费/无场地/无能耗/必要费用缺失，指向空壳·账外·虚开）4. 假设-证据裁决（竞争假设贝叶斯更新）。
核心原则：**发现≠确认**。缺失型疑点必须经竞争假设裁决，证据不足一律转「置疑清单」抛企业自证，系统绝不自动定罪。

## ⚠️ 铁律：「调保守阈值」是伪命题（老邓 2026-09-01 明确）
- 一个违法事实**不会**因为它没超过保守阈值就变成不违法。缺失败象（零运费/无场地/无能耗/无外省加工费产能等）**一律作为待证信号抓取**，确认/待证仅区分「现有资料能否直接断言」，绝不通过抬高阈值来放过任何信号。
- 裁决三态：① 风险假设后验≥0.60（缺失型）或置信差>0.6（通用）→ **直接确认风险**（升级 score）；② 正常假设胜出 → **降级**（判非风险）；③ 两假设后验接近、风险仅微弱胜出（后验 0.55~0.60）→ **unconfirmed 转置疑清单**。禁止为"降低误报"而调高确认阈值。

## 缺失型（missing_element）实现要点
- 引擎：`engine/hypothesis_engine.py` 的 `missing_element` 模板 + `SIGNAL_TO_TEMPLATE` 映射 + `_evaluate_evidence` 缺失型分支 + `run_hypothesis_verification` 的 `adjudication=="missing"→_hypothesis_unconfirmed`。
- 联动：`engine/inspection_questions.py` `run_inspection_questions(unconfirmed_findings=...)` 把 unconfirmed 缺失型发现转成具体询问；`engine/pipeline.py` 中稽查询问步骤须**在假设验证之后**执行（consumes unconfirmed）。
- **已知坑**：`_evaluate_evidence` 中缺失型分支必须位于 `if "制造" in desc` 等通用经营模式分支**之前**，否则「制造业无生产能耗支出」被误判恒真。
- 地区推断：`engine/geo_infer.py` 从购销方名称反推省份（发票无 city/税号字段）；`collect_regions(invs, self_names)` **始终剔除本企业所在省**，仅返回外埠省份（2026-09-01 修复：旧逻辑在「全部同省」时误将本省返回为外埠，导致同省加工费被误判「外省加工费无自有产能」→ 误报）；`is_cross_region` 取外埠省份数≥2。
- `missing_element` 模板为**经营实质整体性**裁决（7 项必要要素综合聚合）：单一要素补全不足以翻案（如仅补租金但缺运输+能耗+车辆仍判风险）；正常型须场地/运输/能耗/车辆齐备方判良性。`unconfirmed` 标志在 `_verify_hypothesis` 返回与 `run_hypothesis_verification` 的 `details` 双写，`enterprise_report._build_confirmed_problems` 以 details 为权威源剔除 unconfirmed，避免既"已核定"又"待证"矛盾。

## 服务器
- 后台 uvicorn 进程随会话/关机被回收，须手动 `start8001.bat` 起重启（默认 8001）。系统级自启（schtasks/WScript.Shell）被环境安全策略阻断，不要重试。

## 报告四类呈现（2026-08-26 重构）
确认问题 / 已执行无异常 / 处理意见+复查标准 / 资料缺失+能力边界+置疑清单。前端 `tax-doc-analysis.js` 收敛四类；`capb`/`iqSec` 变量声明勿随删除块消失（否则 ReferenceError）。

## ★ 报告表述口径（用户约定）
- **材料齐全程度不得以比例/百分比表述**（严禁"材料齐全程度40%"），只表述**项数**——"已有几项、还缺几项"（还缺 = 待核 + 缺失）。`closure`（证据链加权闭合度）仅内部用于判定能否定性，**不进正文**。落地：`enterprise_report`(p3 + `evidence_have`/`evidence_need`)、`evidence_chain.evidence_text`、`argumentation`、`tax-doc-analysis.js`。闸门 `audit_consistency.check_material_completeness_no_ratio`（ERROR 0）。
- **标点规范化（中文语境半角→全角）**：权威 `engine/sentencekit.normalize_cjk_punct`；必须在**两个输出收敛点**生效——① `enterprise_report._zh_normalize_obj`（企业易读报告）② `main._execute_tax_risk_analysis` **最终出口**（覆盖 `all_findings`/`domain_summary`/`_engine_hub` 等前端直接消费字段）。保护小数 `0.00` 与扩展名 `.xlsx`。闸门 `check_report_punctuation`（ERROR 0）。

## ★★ 资料登记名铁律（2026-10-01 用户拍板「资料登记名改用红线文案」， audit ERROR 20→0）
- **登记名必须逐字 == 红线 `required_materials` 文案**：`_recognize_supplementary` 命中的是关键词，但 `_doc_covered_categories` 返回的 `materials` 里只装中文登记名，而 `redline_engine._map_finding` 用**严格相等**匹配 → **只补别名完全无效**（装不进 mats）。唯一有效修法：改登记 `name` 去迁就红线，或改红线文案去迁就登记名。
- **一个 doc_type 只服务一种红线文案**：一条红线写 A、另一条写 B 时，不可能同时匹配；收敛办法是**拆出独立 doc_type**（如 `sup_equity_transfer_contract_plus` / `sup_weight_receipt` / `sup_land_vat_decl`）+ 少数派红线改文案/needs 同步跟。
- **关键词必须留长度差**：`_recognize_supplementary` 取最长命中（`>` 才更新 → **等长时先声明者赢**）。等长打平且赢家恰好正确时，两条旧判据都不响 → 判定靠声明顺序侥幸。判别式：新增关键词用「全名/长词」压过同文件的短词。
- **闸门 `check_material_alias_drift` 三条判据**：①完全相同关键词被多条登记项共用（撞车）②打平后赢家门 ≠ 需求名（漂移）③④2026-10-01 新增：跨登记项等长打平（不同字符串、等长、同时命中同一文件名）。同登记项内多叫法等长打平属**有意容错**，不算。
- `_MATERIAL_SUPERCLASS` 的**键必须是泛化需求名，不得是具体资料类别名**（闸门 `check_coverage_source_wiring` 的 `bad_keys` 强制）；已登记为具体类别的键要删，否则等于拿「合同文件」这类泛化资料冒充具体资料已提供。该表**只读**（仅 C3 覆盖 `.missing` 表述），删键不改 findings。
- 配套工具：`scripts/_dump_alias_map.py`（异名/撞车/一对多四段普查）、`scripts/_scan_kw_ties.py`（同/跨登记项打平分类）、`scripts/_reverse_verify_alias.py`（7 组反向验证：故意破坏 → 闸门必须变红），全部 bare-LF=0。

## ★★ 自死锁事故与闸门 `check_no_lock_reentrancy`（2026-10-01，用户报「一键分析卡在 99%」）
- **根因**：`_run_analysis_thread` 在 `with _analysis_lock:` 内调 `_write_analysis_checkpoint` → `_is_result_deleted` 再 `with _analysis_lock:`。`threading.Lock` **不可重入** → 同一线程自己等自己 → 分析线程永久卡死（CPU 0%、状态恒 running、前端停 99%、报告已落盘却取不到）。
- **修法**：① `_is_result_deleted` 改**无锁快照读**（`list(_analysis_tasks.values())`，CPython 读原子，宁看过期快照）；② 成功检查点 `_write_analysis_checkpoint(company_id,"done","ok")` 从锁内移到**锁外**；③ `except` 分支保持锁内调用（现在安全，且它是闸门的主要防护面）。
- **闸门 `check_no_lock_reentrancy`（已进 `run_checks`）**：AST 扫 main.py（不 import main）。判据＝「传递可达取锁者」：调用链上任一跳出现过 `with _analysis_lock:` 就算会取锁，任一锁块体内调用到它即 ERROR。真实 main.py 可达者 9 个、命中 0（不误报）。
- ★★ **写闸门的方法论（否则必产假闸门）**：判据必须覆盖事故的完整跳数（**第一版只传一层，对这条两跳链完全不响**，实测坏副本全绿）；坏副本**先过 `ast.parse`**，红色若来自「语法错误/解析失败」＝白捡的、等于没验证；每道坏副本要能触发**同一条**判据（本项目统一用消息含「自死锁」做 Sentinel）；`baseline 绿` 不算验证，要 `scripts/_reverse_verify_lock_gate.py` 全场景通过才算。
- **闸门消息里写「CPU 0%」会被 `%` 格式化吃掉** → 必须写 `0%%`。
- **定位手法**：`py-spy dump --pid`（托管 venv 装了 py-spy 0.4.2）+ Windows API `GetProcessTimes` 采样 CPU 增量（0 增量＝阻塞非自旋；**wmic 本机被安全策略拦，别用**）；再用 `scripts/_repro_99.py` 分别只跑 pipeline 与全链路，证明「报告侧正常、卡在收尾」。
- **行尾**：`main.py` 在 git HEAD 上**本来就是全 LF**（仓库既有惯例，别顺手转 CRLF，会出一整文件 diff）。行尾铁律只约束**新建文件**（Write 出来的脚本是纯 LF，要转）。
- **curl 探活必须加 `--noproxy '*'`**，否则经代理返回 502 误导（真值是首页 302、`/api/companies` 401）。
- 配套：`scripts/_reverse_verify_lock_gate.py`（7 场景）、`scripts/_verify_lock_fix.py`（持锁调写回路径 0.06s 不死锁）、`scripts/_repro_99.py`。验收：audit ERROR 0/WARN 0、pytest 743+166 全过、8001 pid 21868。

## ★★ 消除关键词等长打平**：追加「登记名全称」到 kws（2026-10-01，用户拍板「要动」）
- **通用规则**（非特例）：给 `_SUPP_ENTRIES` 某条目的关键词组**追加该条登记名全称**——它是自身既有关键词的严格超串，只要 `len(登记名) > max(现有关键词长度)`，最长命中就唯一，打平结构上不可能发生。判据从「靠声明顺序侥幸」升级为「靠长度确定」。
- 本次消掉 12 处同登记项内打平（「生产工艺文件」「政府补助文件」「竣工验收备案表」「自动监测数据或检测报告」「对外付汇凭证」「工商变更登记」「住房公积金缴存明细」「资产损失鉴证报告（达到标准时）」「不动产权证或土地使用证」「受赠对象与用途说明」「代收代付或返还证明」「折扣折让审批与商业理由说明」）→ 打平 **12→0**，跨登记项保持 0。
- **反向验证＋识别回归**（`scripts/_scan_kw_ties.py` 内建）：剔掉全部「登记名全称」长词后，① 打平数必须**回升**（0→15，证明扫描器不是摆设）② 224 个文件名的识别结果差异**必须为 0**（证明加长词不改变判定）。
- 工具：`scripts/_apply_kw_ties.py`（干跑/`--apply`，AST 落位 + 撞车预检 + 后置断言）、`scripts/_scan_kw_ties.py`（打平普查 + 反向验证）。
- **按 AST 改写源码的三条铁律**（本轮全踩过）：① `assert cond,\n "msg"` 跨行**是语法错误**（逗号不开括号）；② AST 行号相对「改写前」文本，替换必须**保持行数不变**并加行数相等断言，否则后续条目静默错位；③ 不能用 `rfind("]")` 找闭合括号（extra 与 kw 同行时会咬错、把词插进 extra），必须做**括号配对扫描**。
- **写完必须用 `split("\n")/join("\n")` 的文件要重查行尾**：本次把 `engine/material_recognition.py` 的 353 个 CRLF 全打没了，已转回。

## ★★ 证据明细表与疑点「不匹配」事故（2026-10-01，用户复核 8 行表提问「是不是又不匹配」→ 是，已修）
- **事故实态**：「工资名册与社会保险人员范围差异」明细表挂了 4 张**完全无关**的记账凭证（销售服务/收到款项 161 万、结转期间损益 152 万…）+ 4 行脱敏且金额**恒 0** 的工资人员行，标题「共8笔」把两类混计。
- **根因① 关键词二义 + 按金额 TOP5**：detector 只把 `person_month_detail` 放进 `observed_metrics`、**没交 `evidence_rows`** → `pipeline._enrich_evidence_rows` 通用兜底接管。
  凭证分支词含「凭证」，而本疑点文案写了「参保**凭证**」→ 误命中；分支内又是 `sorted(vouchers, key=金额)[:5]` = **给每条发现都挂全公司最大额 5 张凭证**。触发词再准也救不了口径本身。
- **根因② 证据行键表漂移**：`_salary_row` 自写键表（姓名/部门/实发金额/period）与工资表真实结构（`name/salary/net/gross/period_start`）对不上 → 12 张真实工资表 **55 行金额全静默返 0**（假证据：看着像"这几个人没发工资"）。
- **修法**：detector 交**自有 `evidence_rows`**（逐人逐月 姓名/月份/工资/社保基数/匹配状态/来源资料），兜底按 `if f.get("evidence_rows"): continue` 自动跳过；`_salary_row` 走 `fieldkit`；凭证分支三守卫 `_is_ledger_voucher_context`（排除参保/原始/发票/合同/开户/权属"凭证"）+ `_voucher_relevant`（凭证摘要↔发现正文 2-gram 实义词交集，空→**不采**，宁缺毋错）+ **期间对齐**（发现正文 20xx-mm 过滤）；`_with_scope_note` 删「（全量）」（`[:30]` 截断却称全量＝虚假陈述）；`_evidence_rows_to_detail_table` 对未识别 float 补千分位。
- **闸门 `check_evidence_rows_semantic_match`（已进 `run_checks`）**：(a) 带记账凭证证据但与本发现语义无关 → ERROR；(b) 带工资证据且金额**全 0** → ERROR；(c) 原「凭证+工资混装」告警**故意删掉**——一条疑点本就可能在多资料取证，那是假警报。
- ★ **反向验证 `scripts/_reverse_verify_evidence_gate.py` 4/4**（0 基线绿 / A 事故态证据行**硬编码回放** ERROR 2 / B 旧工资键表回归 ERROR 1 / C 无关改动绿）。**A 场景初版从产物读事故态、被全量重跑覆盖 → 失真报绿；必须硬编码用户实测那 8 行。**
- 同源收敛：`pipeline._cjk_bigrams` 与 `enterprise_report._cjk_bigrams` 各一份被跨模块分歧检查抓出 → 唯一实现 `findingkit.cjk_bigrams`，两侧改转调，审计回 0。
- **通用原则（要长记）**：① **宁缺毋错**——给不出证据，也好过给假证据；② evidence_rows 应由 detector 交出真逐笔明细，通用关键词兜底只作**救命**不作正路；③ 任何"按金额 TOP-N"的取证口径都是错的（等于所有发现挂同一批凭证）；④ 静默返 0 是最隐蔽的假证据。
- 验收：audit ERROR 0/WARN 0、pytest tests=909/0fail/0err、`all_findings=162`、目标疑点明细 30 行（首行 杨莹|2025-01|工资8500|社保0|仅有工资无社保）；8001 重启 pid 21060。
- **新坑**：`nohup … &` 在 Bash 工具里随会话结束被杀（uvicorn 起来即没）→ 重启服务须 `run_in_background=true` **前台阻塞**跑 uvicorn，别加 `&`/nohup。
## ★ 报告呈现顺序铁律（2026-10-02，用户定调「一定是先说重要的信息」）
- 总述章段落顺序＝**企业整体风险综合评价（结论先行，置首段）** → 编制声明 → 检查范围与结果概览
  → 行业口径 → 按风险性质归纳 → 风险等级评定 → 分层点名 → 纳税遵从总体看法 → 未完成 → 下一步
  → 监管态度 → 需要说明。原「企业整体风险综合评价」排第 6 段，整体定调被明细淹没。
- ★ 去重纪律：结论段**只给整体等级 + 主要风险领域**；各等级项数与点名仍只由「风险等级评定」段给，
  该段改前指「整体等级见本章首段」（禁止把同一事实在章内说两遍）。
- 监管态度分级条款顺序＝**重点关注(高) → 补证核实(中) → 待核验 → 限期补正资料 → 提示提醒(低)**
  （原 低→中→高 与"先说重要的信息"相反）。
- 疑点呈现顺序唯一权威 `engine/enterprise_report.py::_RISK_PRESENT_ORDER`
  （极高0/高1/中2/低3/待核验=待核=信息4，表外沉底99），`problems.sort` 必须引用它。
  ★ 反例：`_LEVEL_RANK` 是**等级高低标度**（低=0 < 待核验=1），拿它当呈现序用会让待核验排到
  低风险之前；表外等级取 1 会插进高/中之间；`reverse=True` 会把金额缺失(0)项提到同级最前。
- 闸门 `check_conclusion_and_suspicion_order`；测试 `tests/test_conclusion_and_suspicion_order.py`。
- ★ 反向验证坑：改磁盘字节做破坏/还原后，**必须先清 `sys.modules`**（`del sys.modules[...]` +
  `importlib.invalidate_caches()`）再跑闸门，否则一直跑破坏态（会看到假红/假绿）。
- ★ 还原坑：反向验证**绝不能用 `git checkout --`** 还原已改动文件（会连坐回滚同文件其它未提交改动）。

## ★ 行业基准口径单一权威（2026-10-02）
- 非官方的那一份 ＝ `static/industry_data.json` / `industry_benchmark` 的**行业基准区间**
  （系统内置第三方公开行业统计通用参考值：人均营收/进销比/毛利率/税负率/期间费用率）；
  官方口径 ＝ 本企业从自己上传资料取到的**实测值**（收入/成本/工资/开票/银行）。
- 裁定：非官方基准**只有线索/预警参照价值，不构成硬化判定依据**；以它为要件的表述一律
  「对照参照、偏离只作待核线索」。
- 唯一常量 `engine/industry_benchmark.py::BENCHMARK_CAUTION` / `BENCHMARK_CAUTION_SHORT`；
  `tax_redlines` / `redline_benchmark` / `domain_analysis` / `enterprise_report` 全部引用，
  禁第二份字面声明（闸门 `check_benchmark_caution_single_source`）。

## ★★ 行业判定：经营范围「行业级线索」优先于购销兜底（2026-10-01 事故修复）
- 根因：`industry_resolver._trade_benchmark` 只要基准库有「商贸」键就**无条件 return「商贸」**，
  完全不看经营范围内容；而「销售/批发/零售/贸易/购销/经销/进出口」是中国公司经营范围的
  **万能尾巴**（几乎每家都写）→ **销项品名抽不到时服务型企业 100% 判成商贸**（深圳海更数字传媒实证；
  同任何广告/咨询/IT 公司一样）。行业对标基准随之全错。
- 修法（行业无关，只加数据与一个函数，不改逻辑特例）：新增 `scope_industry_hint(scope_text, company_name)`
  —— 逐条查 `industry_map`，只采纳映射到 `service_industries`（服务业态）且
  **不属于** `_TRADE_FALLBACK_INDUSTRIES(商贸/商贸批发/商贸零售/外贸/电子商务)` 的关键词；
  命中多条按**关键词长度优先、等长取 `industry_map` 声明顺序靠前**（结果确定可复现，禁 hash 序）。
  映射到 `production_industries` 的**商品名不算行业**（铁律 R1：服装→服装制造、饲料→农业生产）。
  `resolve_industry` / `match_benchmark` 两处调用点统一改为「先行业级线索，找不到才走原购销兜底」。
- ★ 踩坑（第一版写错）：等长按声明顺序 tiebreak 时，`贸易`(im 第47条) 声明早于 `广告`(第50条)，
  于是「广告设计…；办公用品销售；**国内贸易**」被「贸易」判成商贸 → 必须把购销兜底口径排除出竞争。
- ★★ 新坑：**临时备份文件绝不能放 `engine/`**（`engine/_bak_industry_resolver.py` 被
  `audit_consistency` 判为「跨模块真实第二套实现」→ WARN）。备份一律 `scripts/_bak_*.py`。
  该 WARN 反而证明防多头维护闸门有效。
- 验收：定向 37 passed（新增 7 条，含把判据摘掉即退回「商贸」的反向验证）/ 全量 **775 passed,166 subtests** /
  audit **ERROR 0 WARN 0** / 真实验收（公司3 临时 9999）**PASS 且逐项一致**（行业=农业生产、
  合计 4,576,298.21、cost 443张 4,432,294.53、expense 1张 625.92、pending 3张 143,377.76）。
- 遗留（用户观点采纳为待办）：「行业应随资料摄入重判确认/变更」——系统已有雏形（`pipeline` 外部工商核验后
  重解析 + 变更写 pipeline_log），缺口是触发条件太窄（仅网查成功且有 industry 字段才重判）、
  未用进项品名/合同资料类型/无 `*金税分类*` 时的自由文本频次投票、重判结果未回灌全部下游且无闸门。

## ★ 报告禁止脱敏/禁止隐藏（2026-10-02 用户定调）
- `engine/pii_guard.py` 整体删除；企业版报告与内部底稿**同样不脱敏**，自然人姓名原样呈现
  （「疑点3：需逐人说明：杨*」→「杨莹」）。
- 闸门是**反向**的：原 P1-11「必须接脱敏」改成「禁止脱敏」（模块缺失 + 全库 AST 扫脱敏符号 +
  报告实测「首字+等长星号」形态）；`_verify_review_fixes` P1-11/11b/11c 同步。

## ★★ 成本/费用判定口径（2026-10-01 讨论定）
- **票面无会计科目**：「货物或应税劳务名称」只是候选信号，成本/费用是**推断不是读取**。
  第一刀按「是否构成存货 / 是否资本化」，**不按品名**（水电·运输·包装·维修·租赁同一品名可两边落）。
  用途·部门·承担主体只有回账才知道 → 发票明细只能出 evidence + 待核线索，**不得单独定性**。
- 易错：委托加工费=成本（非费用）｜采购端运费→存货成本、销售端运费→销售费用｜利息·银行手续费=财务费用｜
  研发=研发费用单列｜工资·社保·折旧摊销**不是发票**｜个人抬头消费不得税前扣除｜金额取**不含税**、进项税额单列。
- ★ 系统现状缺陷（待收敛）：费用类品名有 **4 套口径互打架**——
  `memory.BIZ_EXPENSE_KEYWORDS` / `domain_analysis._MAJOR_EXPENSE_KWS` / `main_biz_cost._MAJOR_EXPENSE_KWS`
  （同一名单多了运费装卸承运运送）/ `pipeline._EXPENSE_KWS`（多了住宿餐饮差旅汽油停车）。
  → 同一张住宿费票：pipeline 判费用、main_biz_cost 判核心投入品。收敛目标＝`engine/account_classifier.py` 单一权威
  （表项 `{品名 → (account_class, needs_context, basis)}`，行业核心投入表第一顺位，`needs_context` 词出「待核」）+ 闸门。
- ★★ **接入一键分析的可行性已定（2026-10-01 用户追问）**：做得到，且**必须做成规则表 + 三态裁决，
  禁让 LLM 现场判断**（否则每轮口径漂移＝多头维护复发）。票侧链路已通（疑点3「同一对手既客户又供应商」
  已在产出），**只缺成本/费用分类这一层**。能自动＝销项反推主营 / 进项初筛 / 行业差异化 / 红冲净额 /
  有票无账·有账无票交叉 / 候选清单+置信度+待核清单 / 自动出补证资料清单。
  不能自动＝项目·合同·验收单归属 → 一律出「待核」并索取合同+项目台账+验收(入库)单+付款凭证；
  **无项目名称或合同号字段时只能给成本候选大类，必须如实声明精度边界**。
  铁律：分类**不得**品名命中即 confirmed（违反「存在即触发、禁阈值」），
  `needs_context=True` 词（运输·水电·包装·维修·租赁·差旅·会议·检测）无项目上下文即降级待核。
  落地：`account_classifier`→`fieldkit`→`pipeline._run_analyze`→detector→报告三层（候选+待核+补证）；
  闸门 `check_account_classifier_single_source` + `check_cost_expense_triad`，两处均须反向验证。

## ★ 验收口径铁律（2026-10-02 教训）
`tools/audit_consistency.py` 打印的 `ERROR 0 项 | WARN 0 项` **只是数字/COUNT 维度小结**；
文本维度（共享内容一致性）由 `engine/shared_content_sync.py` 另起一节输出，须分维度读，
**别拿 tail / 汇总行当全局验收**（此前「WARN 0」的说法因此越界，已更正）。
存量 10 条 ⚠「历史遗留块…tax-report-standards.js 不存在」＝该文件在 8bfbe5c9 已有意删除、
git 从未跟踪 → 属「闸门指向已删文件」，走豁免登记（#440/#444 同款）收口，不是新缺陷。
- ★ 反向验证同理：破坏/还原改磁盘字节后必须 `del sys.modules[...]` + `importlib.invalidate_caches()`
  再 import，否则跑的是缓存里的旧对象 → 假红/假绿。还原一律用 `write_bytes(orig)`，**禁 `git checkout --`**。
