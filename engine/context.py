# ═══ 全局 AuditContext 传递机制 ═══
# 域分析函数可以通过 get_audit_ctx() 获取当前分析上下文
# Phase 2 在执行域函数前自动设置此值
_current_ctx = None

def set_audit_ctx(ctx):
    """设置当前线程的 AuditContext（Phase 2 调用）"""
    global _current_ctx
    _current_ctx = ctx

def get_audit_ctx():
    """获取当前 AuditContext（域分析函数调用）"""
    return _current_ctx


class AuditContext:
    """
    税务合规上下文——贯穿4阶段的状态容器
    
    这个对象是推理引擎的"工作记忆"。每个分析阶段：
    1. 读取context中已有的发现和信号
    2. 据此决定分析策略和深度
    3. 产出新的发现注入context
    """
    def __init__(self):
        # ── 企业画像（初查阶段填充）──
        self.company_profile = {
            "industry": "",           # 推断行业
            "biz_model": "",          # 经营模式：制造业/贸易/服务
            "scale": "",              # 规模：大/中/小/微
            "has_manufacturing": False,  # 是否有加工信号
            "has_trading": False,     # 是否有贸易信号
        }
        
        # ── 财务快照（初查阶段填充）──
        self.financial_snapshot = {
            "total_sales": 0,         # 销项总额
            "total_purchases": 0,     # 进项总额
            "total_bank_in": 0,       # 银行收入总额
            "total_bank_out": 0,      # 银行支出总额
            "total_salary": 0,        # 工资总额
            "gross_margin_pct": 0,    # 毛利率
            "sale_count": 0,          # 销项发票张数
            "pur_count": 0,           # 进项发票张数
            "bank_tx_count": 0,       # 银行交易笔数
            "salary_count": 0,        # 工资记录数
        }
        
        # ── 主营业务成本三层分类（初查阶段填充）──
        self.biz_cost_classification = None  # identify_main_biz_cost() 返回值
        
        # ── 初查信号（红灯/黄灯/绿灯）──
        self.red_flags = []     # 需立即深挖的重大信号
        self.yellow_flags = []  # 需关注的次要信号
        self.green_signals = [] # 正常的信号（用于排除误报）
        
        # ── 跨阶段共享的中间结论 ──
        self.bom_missing = False        # 是否缺少BOM表
        self.has_processing_fee = False # 是否有加工费发票
        self.has_personal_payments = False  # 是否有大量个人付款
        self.supplier_concentration = 0  # 供应商集中度(%)
        self.customer_concentration = 0  # 客户集中度(%)
        self.data_quality_score = 0     # 资料质量评分(0-100)
        self.missing_critical_docs = [] # 缺失的关键资料
        self.missing_doc_keys = []      # 缺失的14类资料key列表（供Phase 4缺失后果触发用）
        self.all_findings = []          # 所有阶段的发现汇总
        self.file_results = []          # 文件解析结果
        self.industry_profile = None    # 行业画像（_load_industry_profile返回值）
        self.memory_learner = None      # 记忆学习器
        self.trend_data = None          # 趋势数据
        self.trend_findings = []        # 趋势发现
        self._memory_data = None        # 记忆数据
        self._memory_insight = None     # 记忆洞察
        self._ema_learning = None       # EMA学习数据
        self._entity_graph = None       # 实体关系图
        self._bayesian = None           # 贝叶斯网络
        self._benford = None            # 本福特定律结果
        self._multimodal = None         # 多模态支持
        self._audit_strategies = None   # 审计策略
        self._discovered_rules = {}     # 发现的规则
        
        # ── 结论索引（供交叉验证时快速检索）──
        self.finding_index = {}   # {"type_prefix": [finding_dict, ...]}
        
        # ── 阶段追踪 ──
        self.current_phase = 0
        self.phase_history = []   # 每阶段的执行摘要
    
    def add_flag(self, level, signal_type, detail, source_domain=""):
        """添加税务合规信号"""
        entry = {
            "type": signal_type,
            "detail": detail,
            "source": source_domain,
            "timestamp": None  # 由调用方填充
        }
        if level == "red":
            self.red_flags.append(entry)
        elif level == "yellow":
            self.yellow_flags.append(entry)
        else:
            self.green_signals.append(entry)
    
    def index_findings(self, findings, domain=""):
        """将一批发现索引到finding_index，供后续阶段快速检索"""
        for f in findings:
            if not isinstance(f, dict): continue
            ftype = f.get("type", "")
            # 按type前缀索引（取前6个字符作为键）
            key = ftype[:8] if len(ftype) >= 8 else ftype
            if key not in self.finding_index:
                self.finding_index[key] = []
            self.finding_index[key].append({**f, "_indexed_domain": domain})
    
    def query_findings(self, keyword):
        """在已索引的结论中搜索关键词"""
        results = []
        for key, findings in self.finding_index.items():
            if keyword in key:
                results.extend(findings)
            else:
                for f in findings:
                    ftype = f.get("type", "")
                    desc = f.get("description", "")
                    if keyword in ftype or keyword in desc:
                        results.append(f)
        return results
    
    def get_snapshot_summary(self):
        """生成初查快照摘要"""
        fs = self.financial_snapshot
        cp = self.company_profile
        lines = []
        lines.append(f"行业推断: {cp['industry'] or '未识别'}")
        lines.append(f"经营模式: {cp['biz_model'] or '待定'}")
        lines.append(f"销项: {fs['sale_count']}张 {fs['total_sales']:,.0f}元")
        lines.append(f"进项: {fs['pur_count']}张 {fs['total_purchases']:,.0f}元")
        lines.append(f"银行: {fs['bank_tx_count']}笔 收{fs['total_bank_in']:,.0f}/支{fs['total_bank_out']:,.0f}")
        lines.append(f"工资: {fs['salary_count']}条 {fs['total_salary']:,.0f}元")
        if self.biz_cost_classification:
            bcc = self.biz_cost_classification
            lines.append(f"主营成本: 核心{len(bcc['core_cost_invs'])}张/重大费用{len(bcc['major_expense_invs'])}张/日常报销{len(bcc['minor_expense_invs'])}张")
        lines.append(f"红灯信号: {len(self.red_flags)}个")
        lines.append(f"黄灯信号: {len(self.yellow_flags)}个")
        return self, "\n".join(lines)


