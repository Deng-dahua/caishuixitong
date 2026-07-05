"""
人类学习引擎 — 12项认知能力
=================================
像人一样学习：记忆/遗忘/举一反三/质疑自己/抽象归纳/因果推理/容错机制/主动提问/自我评估/渐进调整/回测验证/关系发现

调用方式：
    from engine.human_learning import HumanLearner
    learner = HumanLearner()
    learner.learn(correction_text, source="编辑", context={})

数据存储：static/human_learning_state.json
"""

import json
import os
import time
import hashlib
from datetime import datetime, timedelta
from collections import defaultdict, Counter

STATE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)) or ".", "static", "human_learning_state.json")

# ── 辅助函数 ──
def _load_state():
    try:
        if os.path.exists(STATE_PATH):
            with open(STATE_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
    except: pass
    return _default_state()

def _save_state(state):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def _default_state():
    return {
        "decision_log": [],       # 记忆：每次决策记录
        "active_rules": {},       # 活跃规则 {rule_id: {content, confidence, usage_count, ...}}
        "archived_rules": {},     # 遗忘归档
        "conflicts": [],          # 质疑：冲突登记
        "correction_clusters": [],# 抽象归纳：纠正聚类
        "root_causes": [],        # 因果推理：根因记录
        "pending_verification": [],# 容错：待验证规则
        "questions": [],          # 主动提问：待确认问题
        "backtest_results": [],   # 回测验证结果
        "rule_relationships": [], # 关系发现：规则关联
    }


class HumanLearner:
    """人类学习引擎 — 模拟人的12项认知能力"""

    def __init__(self):
        self.state = _load_state()

    def _now(self):
        return datetime.now().isoformat()

    # ════════════════════════════════════════════════════
    # 1. 记忆 — 记住每次决策的原因和结果
    # ════════════════════════════════════════════════════
    def memorize(self, action: str, reason: str, result: dict, context: dict = None):
        """记录一次决策行为"""
        entry = {
            "action": action,
            "reason": reason,
            "result": result,
            "context": context or {},
            "timestamp": self._now(),
            "id": hashlib.md5(f"{action}{reason}{time.time()}".encode()).hexdigest()[:12],
        }
        self.state["decision_log"].insert(0, entry)
        # 保留最近500条
        if len(self.state["decision_log"]) > 500:
            self.state["decision_log"] = self.state["decision_log"][:500]
        self._persist()
        return entry["id"]

    def recall(self, query: str = None, limit: int = 10):
        """回忆过去的决策"""
        logs = self.state["decision_log"]
        if query:
            logs = [l for l in logs if query in str(l)]
        return logs[:limit]

    def self_reflect(self, rule_id: str):
        """自省：这条规则上次采纳后影响是什么"""
        related = [l for l in self.state["decision_log"] if rule_id in str(l)]
        if not related:
            return {"conclusion": "无历史记录", "impact": "未知"}
        last = related[0]
        return {
            "conclusion": f"上次'{last['action']}'后，{last.get('result',{}).get('summary','结果未知')}",
            "impact": last.get("result", {}),
            "history_count": len(related),
        }

    # ════════════════════════════════════════════════════
    # 2. 遗忘 — 识别无效规则，自动降低权重或归档
    # ════════════════════════════════════════════════════
    def decay_rules(self):
        """定期调用：检查活跃规则，长期不用或矛盾则降低权重/归档"""
        now = datetime.now()
        decayed = []
        for rid, rule in list(self.state["active_rules"].items()):
            last_used = rule.get("last_used", "")
            if last_used:
                try:
                    last = datetime.fromisoformat(last_used)
                    days_unused = (now - last).days
                except: days_unused = 999
            else:
                days_unused = 999

            # 超过30天 → 降低置信度
            if days_unused > 30:
                rule["confidence"] = max(0.1, rule.get("confidence", 0.5) - 0.1)
                rule["decay_note"] = f"超过{days_unused}天未使用，置信度已降低"
                decayed.append(rid)

            # 超过180天 → 归档
            if days_unused > 180:
                self.state["archived_rules"][rid] = rule
                del self.state["active_rules"][rid]
                decayed.append(rid)

        self._persist()
        return {"decayed_count": len(decayed), "decayed_rules": decayed}

    # ════════════════════════════════════════════════════
    # 3. 举一反三 — 规则跨行业迁移
    # ════════════════════════════════════════════════════
    def cross_industry_transfer(self, rule_id: str):
        """一条规则在一个行业生效，尝试推广到其他行业"""
        rule = self.state["active_rules"].get(rule_id)
        if not rule:
            return {"ok": False, "message": "规则不存在"}

        source_industry = rule.get("industry", "未知")
        transfer_candidates = []
        # 找到所有行业
        all_industries = set()
        for r in self.state["active_rules"].values():
            ind = r.get("industry", "")
            if ind and ind != source_industry:
                all_industries.add(ind)

        for ind in list(all_industries)[:5]:
            # 检查该行业是否已有同类规则
            existing = [r for r in self.state["active_rules"].values()
                        if r.get("industry") == ind and r.get("finding_type") == rule.get("finding_type")]
            if not existing:
                new_rule = dict(rule)
                new_rule["id"] = f"{rule_id}_transfer_{ind}"
                new_rule["industry"] = ind
                new_rule["confidence"] = rule.get("confidence", 0.5) * 0.7  # 70%信任度
                new_rule["transfer_from"] = source_industry
                new_rule["transfer_note"] = f"从{source_industry}迁移至{ind}，置信度打折至70%"
                new_rule["created_at"] = self._now()
                new_rule["last_used"] = ""
                new_rule["usage_count"] = 0
                new_rule["manual_confirm"] = False  # 需要人工确认
                self.state["active_rules"][new_rule["id"]] = new_rule
                transfer_candidates.append({"industry": ind, "rule_id": new_rule["id"]})

        self._persist()
        return {
            "ok": True,
            "source_industry": source_industry,
            "transfer_count": len(transfer_candidates),
            "candidates": transfer_candidates,
        }

    # ════════════════════════════════════════════════════
    # 4. 质疑自己 — 新旧证据冲突标记
    # ════════════════════════════════════════════════════
    def detect_conflict(self, new_evidence: str, rule_id: str):
        """新证据与旧规则矛盾时，标记冲突而不是盲目覆盖"""
        rule = self.state["active_rules"].get(rule_id)
        if not rule:
            return {"ok": False, "message": "规则不存在"}

        conflict = {
            "rule_id": rule_id,
            "rule_content": rule.get("content", "")[:200],
            "new_evidence": new_evidence[:200],
            "timestamp": self._now(),
            "status": "unresolved",
            "resolution": "",
        }
        self.state["conflicts"].insert(0, conflict)
        # 降低规则状态为"有争议"
        rule["disputed"] = True
        rule["confidence"] = max(0.1, rule.get("confidence", 0.5) - 0.15)
        rule["conflict_count"] = rule.get("conflict_count", 0) + 1
        self._persist()
        return {
            "ok": True,
            "message": f"冲突已登记，规则'{rule_id}'置信度降至{rule['confidence']}，标记为'有争议'",
            "conflict_id": len(self.state["conflicts"]) - 1,
        }

    # ════════════════════════════════════════════════════
    # 5. 抽象归纳 — 多条纠正提炼为通用规则
    # ════════════════════════════════════════════════════
    def abstract_generalize(self, correction_texts: list):
        """多条纠正合并为一条通用规则"""
        if len(correction_texts) < 2:
            return {"ok": False, "message": "至少需要2条纠正才能归纳"}

        # 找共同关键词
        all_words = []
        for t in correction_texts:
            # 简单分词：中文按字+英文按空格
            words = [w for w in t if '\u4e00' <= w <= '\u9fff']
            all_words.extend(words)
        word_counts = Counter(all_words)
        common = [w for w, c in word_counts.most_common(10) if c >= 2]

        # 尝试用LLM归纳
        generalized = self._try_llm_generalize(correction_texts, common)

        cluster = {
            "id": hashlib.md5("|".join(correction_texts).encode()).hexdigest()[:12],
            "source_count": len(correction_texts),
            "sources": correction_texts,
            "common_keywords": common,
            "generalized_rule": generalized,
            "created_at": self._now(),
        }
        self.state["correction_clusters"].insert(0, cluster)

        # 生成新规则
        new_rule = {
            "id": f"generalized_{cluster['id']}",
            "content": generalized,
            "confidence": 0.75,
            "source": "抽象归纳",
            "source_count": len(correction_texts),
            "created_at": self._now(),
            "last_used": "",
            "usage_count": 0,
        }
        self.state["active_rules"][new_rule["id"]] = new_rule
        self._persist()
        return {"ok": True, "rule_id": new_rule["id"], "content": generalized}

    def _try_llm_generalize(self, texts, keywords):
        """用LLM尝试归纳"""
        try:
            # 本地Ollama
            import httpx
            prompt = f"以下用户纠正指向同一个根本问题，请用一句话总结为通用规则：\n" + "\n".join(texts[:5])
            resp = httpx.post("http://localhost:11434/api/generate", json={
                "model": "qwen2.5:7b", "prompt": prompt, "stream": False
            }, timeout=30)
            if resp.status_code == 200:
                return resp.json().get("response", "")[:200]
        except: pass
        # LLM不可用时用关键词拼装
        return f"通用规则：涉及{'、'.join(keywords[:3])}等关键词的纠正，应统一检查相关分类与计算逻辑。来源于{len(texts)}次用户纠正。"

    # ════════════════════════════════════════════════════
    # 6. 因果推理 — 分析"为什么之前错了"
    # ════════════════════════════════════════════════════
    def reason_root_cause(self, error_finding: str, correct_answer: str):
        """分析引擎误判的根本原因"""
        root_cause = {
            "id": hashlib.md5(f"{error_finding}{time.time()}".encode()).hexdigest()[:12],
            "error": error_finding[:200],
            "correct": correct_answer[:200],
            "timestamp": self._now(),
            "analysis": self._analyze_why_wrong(error_finding, correct_answer),
        }
        self.state["root_causes"].insert(0, root_cause)
        self._persist()
        return root_cause

    def _analyze_why_wrong(self, error: str, correct: str):
        """分析为什么之前会出错"""
        reasons = []
        et = error.lower(); ct = correct.lower()
        if "税率" in error and "税率" in correct:
            reasons.append("税率参数配置错误或未及时更新")
        if "含税" in error or "含税" in correct:
            reasons.append("未区分含税/不含税金额")
        if "分类" in error or "分类" in correct:
            reasons.append("科目/费用分类判断错误")
        if "行业" in error or "行业" in correct:
            reasons.append("未考虑行业特殊性")
        if len(reasons) == 0:
            reasons.append("数据源解析或计算逻辑需人工复核")
        return "；".join(reasons)

    # ════════════════════════════════════════════════════
    # 7. 容错机制 — 纠正次数不足时不采纳
    # ════════════════════════════════════════════════════
    def verify_before_adopt(self, correction_text: str, source: str = "编辑"):
        """纠正先标记为待验证，满足条件后才采纳"""
        verify = {
            "id": hashlib.md5(f"{correction_text}{time.time()}".encode()).hexdigest()[:12],
            "content": correction_text[:200],
            "source": source,
            "submit_count": 1,
            "first_seen": self._now(),
            "last_seen": self._now(),
            "status": "pending",
        }
        # 检查是否已有同类待验证
        for v in self.state["pending_verification"]:
            if similar_text(v["content"], correction_text, 0.6):
                v["submit_count"] += 1
                v["last_seen"] = self._now()
                if v["submit_count"] >= 3:
                    v["status"] = "verified"
                    self.state["pending_verification"].remove(v)
                    # 经过3次验证 → 创建正式规则
                    rule_id = f"verified_{v['id']}"
                    self.state["active_rules"][rule_id] = {
                        "id": rule_id, "content": v["content"],
                        "confidence": 0.8, "source": "容错验证(3次确认)",
                        "created_at": self._now(),
                        "last_used": "", "usage_count": 0,
                    }
                    self._persist()
                    return {"ok": True, "status": "verified", "message": "经3次确认，已采纳为正式规则", "rule_id": rule_id}
                self._persist()
                return {"ok": True, "status": "pending", "message": f"第{v['submit_count']}次出现，再{v['submit_count']}次即可采纳"}

        self.state["pending_verification"].insert(0, verify)
        self._persist()
        return {"ok": True, "status": "pending", "message": "首次出现，已标记为待验证(需3次确认)"}

    # ════════════════════════════════════════════════════
    # 8. 主动提问 — 纠正模糊时反问用户
    # ════════════════════════════════════════════════════
    def ask_if_unclear(self, correction_text: str):
        """纠正内容模糊时，生成反问问题"""
        questions = []
        text = correction_text.lower()

        if any(w in text for w in ["主营业务", "主营收入"]) or "主营" in text:
            questions.append("'主营业务'的判断标准是什么？按品名分类、按金额占比、还是按发票备注？")
        if "成本" in text and "费用" not in text:
            questions.append("这属于'成本'还是'费用'？两者的会计处理不同。")
        if any(w in text for w in ["13%", "9%", "6%", "税率"]):
            questions.append("确认的税率依据是哪条法规？是否考虑了一般纳税人和小规模纳税人的差异？")
        if "比例" in text or "占比" in text:
            questions.append("具体的计算口径是什么？分子和分母分别怎么算？")
        if "进项" in text and "销项" in text:
            questions.append("进销配对的依据是什么？按品名、按发票号、还是按时间顺序？")

        if questions:
            q = {
                "id": hashlib.md5(f"{correction_text}{time.time()}".encode()).hexdigest()[:12],
                "correction": correction_text[:200],
                "questions": questions,
                "timestamp": self._now(),
                "status": "awaiting_answer",
            }
            self.state["questions"].insert(0, q)
            self._persist()
            return {"ok": True, "needs_clarification": True, "questions": questions, "question_id": q["id"]}

        return {"ok": True, "needs_clarification": False}

    # ════════════════════════════════════════════════════
    # 9. 自我评估 — 给每条规则打置信度分
    # ════════════════════════════════════════════════════
    def evaluate_rule(self, rule_id: str):
        """评规则置信度，低于阈值标记'需人工复核'"""
        rule = self.state["active_rules"].get(rule_id)
        if not rule:
            return {"ok": False, "message": "规则不存在"}

        confidence = rule.get("confidence", 0.5)
        usage = rule.get("usage_count", 0)
        conflicts = rule.get("conflict_count", 0)
        age_days = 0
        if rule.get("created_at"):
            try:
                age_days = (datetime.now() - datetime.fromisoformat(rule["created_at"])).days
            except: pass

        # 评分算法
        score = confidence * 0.4  # 基础信任度 40%
        score += min(usage / 20, 0.3)  # 使用次数 30%
        score -= conflicts * 0.1  # 冲突扣分
        score -= min(age_days / 365, 0.1)  # 年龄衰减

        score = max(0, min(1, score))
        rule["confidence"] = score

        if score < 0.5:
            rule["review_needed"] = True
            rule["review_reason"] = f"置信度仅{score:.0%}，建议人工复核"
        elif score < 0.7:
            rule["review_needed"] = False
            rule["caution"] = True

        self._persist()
        return {"rule_id": rule_id, "confidence": score, "review_needed": rule.get("review_needed", False)}

    # ════════════════════════════════════════════════════
    # 10. 渐进调整 — 逐步调权而不是极端切换
    # ════════════════════════════════════════════════════
    def gradual_adjust(self, rule_id: str, direction: str = "up", amount: float = 0.05):
        """渐进式调整规则权重"""
        rule = self.state["active_rules"].get(rule_id)
        if not rule:
            return {"ok": False, "message": "规则不存在"}

        old = rule.get("confidence", 0.5)
        if direction == "up":
            rule["confidence"] = min(1.0, old + amount)
        elif direction == "down":
            rule["confidence"] = max(0.1, old - amount)

        rule["adjust_history"] = rule.get("adjust_history", [])
        rule["adjust_history"].append({
            "from": old, "to": rule["confidence"],
            "direction": direction, "time": self._now(),
        })
        self._persist()
        return {"rule_id": rule_id, "old_confidence": old, "new_confidence": rule["confidence"]}

    # ════════════════════════════════════════════════════
    # 11. 回测验证 — 新规则跑旧数据验证效果
    # ════════════════════════════════════════════════════
    def backtest(self, rule_id: str, company_id: int = None):
        """用旧数据回测新规则"""
        rule = self.state["active_rules"].get(rule_id)
        if not rule:
            return {"ok": False, "message": "规则不存在"}

        # 尝试加载上次分析缓存
        cache_path = os.path.join(os.path.dirname(STATE_PATH), "uploads", "tax-risk-docs")
        if company_id:
            cache_path = os.path.join(cache_path, str(company_id), "last_analysis_cache.json")
        else:
            # 找最近的缓存
            import glob
            caches = sorted(glob.glob(os.path.join(cache_path, "*", "last_analysis_cache.json")), key=os.path.getmtime, reverse=True)
            cache_path = caches[0] if caches else ""

        result = {
            "rule_id": rule_id,
            "timestamp": self._now(),
            "status": "unknown",
            "findings_before": 0,
            "findings_after": 0,
            "delta": 0,
        }

        if os.path.exists(cache_path):
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    old_data = json.load(f)
                old_findings = old_data.get("report", {}).get("all_findings", [])
                result["findings_before"] = len(old_findings)
                # 模拟应用新规则后可能的变化（简化版）
                result["findings_after"] = len(old_findings) + _estimate_rule_impact(rule, old_findings)
                result["delta"] = result["findings_after"] - result["findings_before"]
                result["status"] = "completed"
            except: pass

        if result["status"] == "unknown":
            result["status"] = "no_cache"
            result["message"] = "无历史分析缓存，无法回测"

        self.state["backtest_results"].insert(0, result)
        self._persist()
        return result

    # ════════════════════════════════════════════════════
    # 12. 关系发现 — 规则关联网络
    # ════════════════════════════════════════════════════
    def discover_relationships(self):
        """发现规则之间的关联关系"""
        rules = list(self.state["active_rules"].values())
        if len(rules) < 2:
            return {"ok": True, "relationships": []}

        relationships = []
        for i in range(len(rules)):
            for j in range(i + 1, len(rules)):
                ri, rj = rules[i], rules[j]
                similarity = _text_similarity(ri.get("content", ""), rj.get("content", ""))
                if similarity > 0.5:
                    relationships.append({
                        "rule_a": ri["id"],
                        "rule_b": rj["id"],
                        "similarity": round(similarity, 2),
                        "type": "内容相似",
                    })
                # 同行业规则
                if ri.get("industry") and ri["industry"] == rj.get("industry"):
                    relationships.append({
                        "rule_a": ri["id"],
                        "rule_b": rj["id"],
                        "similarity": 1.0,
                        "type": "同行业",
                    })
                # 同发现类型
                if ri.get("finding_type") and ri["finding_type"] == rj.get("finding_type"):
                    relationships.append({
                        "rule_a": ri["id"],
                        "rule_b": rj["id"],
                        "similarity": 1.0,
                        "type": "同发现类型",
                    })

        # 去重
        seen = set()
        unique = []
        for r in relationships:
            key = tuple(sorted([r["rule_a"], r["rule_b"]] + [r["type"]]))
            if key not in seen:
                seen.add(key)
                unique.append(r)

        self.state["rule_relationships"] = unique
        self._persist()
        return {"ok": True, "relationship_count": len(unique), "relationships": unique[:20]}

    # ════════════════════════════════════════════════════
    # 统一学习入口
    # ════════════════════════════════════════════════════
    def learn(self, correction: str, source: str = "编辑", context: dict = None):
        """统一学习入口：用户纠正 → 引擎综合学习"""
        ctx = context or {}
        results = {}

        # 1. 记忆这次学习行为
        results["memory"] = self.memorize(
            action=f"{source}提交纠正",
            reason=correction[:100],
            result={"status": "已记录"},
            context=ctx,
        )

        # 2. 容错：先验证后采纳
        results["verify"] = self.verify_before_adopt(correction, source)

        # 3. 主动提问：纠正模糊时反问
        clarification = self.ask_if_unclear(correction)
        if clarification.get("needs_clarification"):
            results["clarification"] = clarification

        # 4. 因果推理：为什么会出错
        error_detail = ctx.get("error_detail", "")
        results["root_cause"] = self.reason_root_cause(error_detail, correction)

        # 5. 检查是否有旧冲突
        for c in self.state["conflicts"]:
            if similar_text(c["new_evidence"], correction, 0.5):
                results["conflict"] = {"existing": True, "conflict_id": self.state["conflicts"].index(c)}

        # 6. 关系发现（每10次学习触发一次）
        if len(self.state["decision_log"]) % 10 == 0:
            results["relationships"] = self.discover_relationships()

        # 7. 渐进调整：学习完调整相关规则权重
        for rid in list(self.state["active_rules"].keys())[:3]:
            self.gradual_adjust(rid, "up", 0.02)

        return {
            "ok": True,
            "steps_completed": list(results.keys()),
            "details": results,
        }

    # ════════════════════════════════════════════════════
    # 状态查询接口
    # ════════════════════════════════════════════════════
    def status(self):
        """返回当前引擎状态摘要"""
        return {
            "记忆": len(self.state["decision_log"]),
            "活跃规则": len(self.state["active_rules"]),
            "已归档规则": len(self.state["archived_rules"]),
            "待解决冲突": sum(1 for c in self.state["conflicts"] if c.get("status") == "unresolved"),
            "待验证纠正": sum(1 for v in self.state["pending_verification"] if v.get("status") == "pending"),
            "已归纳聚类": len(self.state["correction_clusters"]),
            "根因分析": len(self.state["root_causes"]),
            "待回答问题": sum(1 for q in self.state["questions"] if q.get("status") == "awaiting_answer"),
            "回测记录": len(self.state["backtest_results"]),
            "规则关联": len(self.state["rule_relationships"]),
        }

    def _persist(self):
        _save_state(self.state)


# ── 工具函数 ──
def similar_text(a: str, b: str, threshold: float = 0.6) -> bool:
    """简单文本相似度判断"""
    if not a or not b: return False
    a_words = set(a); b_words = set(b)
    if not a_words or not b_words: return False
    intersection = a_words & b_words
    union = a_words | b_words
    return len(intersection) / len(union) >= threshold if union else False

def _text_similarity(a: str, b: str) -> float:
    """计算文本相似度"""
    if not a or not b: return 0
    a_w = set(a); b_w = set(b)
    if not a_w or not b_w: return 0
    return len(a_w & b_w) / len(a_w | b_w)

def _estimate_rule_impact(rule: dict, findings: list) -> int:
    """估算新规则可能影响的发现数量"""
    content = rule.get("content", "")
    keywords = [w for w in content if '\u4e00' <= w <= '\u9fff'][:10]
    count = 0
    for f in findings:
        ftext = str(f)
        matches = sum(1 for kw in keywords if kw in ftext)
        if matches >= 2:
            count += 1
    return count
