"""
整改跟踪闭环 — 从发现问题到整改完成的完整生命周期管理

每个风险发现可进入整改流程：
发现问题 → 下达整改通知 → 企业整改 → 提交证据 → 复查验收 → 归档闭环
"""
import json, os
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

class RectificationTracker:
    """整改跟踪引擎"""
    
    STATUS_FLOW = [
        "已识别",       # 发现问题
        "已通知",       # 下达整改
        "整改中",       # 企业正在整改
        "已提交",       # 企业提交了整改证据
        "复查中",       # 税务合规员复查
        "已验收",       # 整改通过
        "未通过",       # 整改不通过，重新下达
        "已归档",       # 归档闭环
    ]
    
    DEADLINES = {
        "高风险": 15,   # 15天
        "中风险": 30,   # 30天
        "低风险": 60,   # 60天
    }
    
    def __init__(self):
        self._items: List[Dict] = []
        self._load()
    
    def _load(self):
        path = os.path.join(os.path.dirname(__file__), "..", "static", "rectifications.json")
        try:
            with open(path, encoding="utf-8") as f:
                self._items = json.load(f)
        except:
            self._items = []
    
    def _save(self):
        path = os.path.join(os.path.dirname(__file__), "..", "static", "rectifications.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._items[-500:], f, ensure_ascii=False, indent=2)
    
    def create(self, finding: Dict, company_id: int, company_name: str = "") -> Dict:
        """从风险发现创建整改事项"""
        item = {
            "id": f"RECT-{len(self._items)+1:04d}",
            "company_id": company_id,
            "company_name": company_name,
            "finding_type": finding.get("type", ""),
            "finding_detail": finding.get("detail", "")[:200],
            "risk_level": finding.get("level", "中风险"),
            "status": "已识别",
            "deadline_days": self.DEADLINES.get(finding.get("level", "中风险"), 30),
            "created_at": datetime.now().isoformat(),
            "deadline": (datetime.now() + timedelta(days=self.DEADLINES.get(finding.get("level", "中风险"), 30))).isoformat(),
            "history": [{"status": "已识别", "timestamp": datetime.now().isoformat(), "note": "系统自动创建"}],
            "evidence": [],
            "result": "",
        }
        self._items.append(item)
        self._save()
        return item
    
    def update_status(self, rect_id: str, new_status: str, note: str = "", evidence: List[str] = None) -> Dict:
        """更新整改状态"""
        for item in self._items:
            if item["id"] == rect_id:
                old_status = item["status"]
                
                # 验证状态流转合法性
                valid_next = {
                    "已识别": ["已通知"],
                    "已通知": ["整改中"],
                    "整改中": ["已提交"],
                    "已提交": ["复查中"],
                    "复查中": ["已验收", "未通过"],
                    "未通过": ["整改中"],
                    "已验收": ["已归档"],
                }
                
                allowed = valid_next.get(old_status, [])
                if new_status not in allowed and old_status != new_status:
                    return {"ok": False, "message": f"不能从「{old_status}」直接转到「{new_status}」，允许: {', '.join(allowed)}"}
                
                item["status"] = new_status
                item["history"].append({
                    "status": new_status,
                    "timestamp": datetime.now().isoformat(),
                    "note": note,
                })
                if evidence:
                    item.setdefault("evidence", []).extend(evidence)
                if new_status in ("已验收", "未通过"):
                    item["result"] = note
                
                self._save()
                return {"ok": True, "item": item}
        
        return {"ok": False, "message": f"整改事项 {rect_id} 不存在"}
    
    def get_pending(self, company_id: int = None) -> List[Dict]:
        """获取待处理的整改事项"""
        items = self._items
        if company_id:
            items = [i for i in items if i.get("company_id") == company_id]
        
        return [
            i for i in items
            if i["status"] not in ("已归档",)
            # 检查是否超期
        ]
    
    def get_overdue(self) -> List[Dict]:
        """获取已超期的整改事项"""
        now = datetime.now().isoformat()
        return [
            i for i in self._items
            if i["status"] not in ("已验收", "已归档")
            and i.get("deadline", "") < now
        ]
    
    def get_stats(self, company_id: int = None) -> Dict:
        """整改统计"""
        items = self._items
        if company_id:
            items = [i for i in items if i.get("company_id") == company_id]
        
        by_status = {}
        for s in self.STATUS_FLOW:
            by_status[s] = len([i for i in items if i["status"] == s])
        
        overdue = self.get_overdue()
        if company_id:
            overdue = [o for o in overdue if o.get("company_id") == company_id]
        
        return {
            "total": len(items),
            "by_status": by_status,
            "overdue": len(overdue),
            "completion_rate": by_status.get("已归档", 0) / max(len(items), 1),
            "active": len([i for i in items if i["status"] not in ("已验收", "已归档")]),
        }
    
    def generate_report(self, company_id: int = None) -> str:
        """生成整改跟踪报告"""
        stats = self.get_stats(company_id)
        items = self.get_pending(company_id)
        overdue = self.get_overdue()
        
        lines = [
            "═══════════════════════════════",
            "       整改跟踪闭环报告",
            "═══════════════════════════════",
            "",
            f"总整改事项: {stats['total']}",
            f"已完成归档: {stats['by_status'].get('已归档', 0)}",
            f"超期未整改: {stats['overdue']}",
            f"完成率: {stats['completion_rate']:.0%}",
            "",
            "── 待处理事项 ──",
        ]
        
        for item in items[:10]:
            due = item.get("deadline", "")[:10]
            lines.append(f"  [{item['risk_level']}] {item['finding_type'][:30]} - {item['status']} (截止:{due})")
        
        if overdue:
            lines.append("")
            lines.append("── ⚠️ 超期事项 ──")
            for item in overdue[:5]:
                lines.append(f"  [{item['risk_level']}] {item['finding_type'][:30]} - 超期")
        
        return "\n".join(lines)


# 全局整改跟踪器
tracker = RectificationTracker()

def get_tracker() -> RectificationTracker:
    return tracker
