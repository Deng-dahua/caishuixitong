# -*- coding: utf-8 -*-
"""法规时效映射引擎 —— 所有法律引用必须经过此引擎校验，禁止使用已废止法规

  使用方式:
    from engine.law_validity_checker import get_valid_citation
    valid_law = get_valid_citation("增值税暂行条例")  # → "中华人民共和国增值税法"

  运行时自动替换: pipeline注入时自动调用 check_law_validity() 清洗所有 law_refs
"""
import json, os, re
from typing import Dict, List, Tuple

# ═════════ 已废止法规 → 现行有效法规映射 ═════
# 格式: "已废止名称（含简称）": ("现行有效名称", "施行日期", "备注")
DEPRECATED_LAWS: Dict[str, Tuple[str, str, str]] = {
    # ── 增值税 ──
    "增值税暂行条例": ("中华人民共和国增值税法", "2026.1.1", "原条例全文废止"),
    "中华人民共和国增值税暂行条例": ("中华人民共和国增值税法", "2026.1.1", "原条例全文废止"),
    "增值税暂行条例实施细则": ("中华人民共和国增值税法实施条例", "2026.1.1", "原细则全文废止"),
    "增值税条例": ("中华人民共和国增值税法", "2026.1.1", ""),
    "增值税法": ("中华人民共和国增值税法", "2026.1.1", "全称规范化"),

    # ── 营业税 ──
    "营业税暂行条例": ("(已废止-营业税已取消)", "2016.5.1", "营改增后全文废止"),
    "中华人民共和国营业税暂行条例": ("(已废止-营业税已取消)", "2016.5.1", "营改增后全文废止"),

    # ── 企业所得税（暂未被直接废止，但需标注是否有效） ──
    # 企业所得税法(2008.1.1施行)目前仍有效

    # ── 房产税 ──
    "房产税暂行条例": ("中华人民共和国房产税法", "待审议", "现行仍为1986年条例，但建议标注为暂行条例"),
    
    # ── 城建税 ──
    "城建税暂行条例": ("中华人民共和国城市维护建设税法", "2021.9.1", "原暂行条例全文废止"),

    # ── 印花税 ──
    "印花税暂行条例": ("中华人民共和国印花税法", "2022.7.1", "原暂行条例全文废止"),

    # ── 其他常用废止/更新法规 ──
    "资源税暂行条例": ("中华人民共和国资源税法", "2020.9.1", "原暂行条例全文废止"),
    "契税暂行条例": ("中华人民共和国契税法", "2021.9.1", "原暂行条例全文废止"),
    "车辆购置税暂行条例": ("中华人民共和国车辆购置税法", "2019.7.1", "原暂行条例全文废止"),
    "耕地占用税暂行条例": ("中华人民共和国耕地占用税法", "2019.9.1", "原暂行条例全文废止"),
    "环境保护税法": ("中华人民共和国环境保护税法", "2018.1.1", "全称规范化"),
    "烟叶税法": ("中华人民共和国烟叶税法", "2018.7.1", "全称规范化"),
    "船舶吨税法": ("中华人民共和国船舶吨税法", "2018.7.1", "全称规范化"),

    # ── 土地增值税（现行仍为暂行条例） ──
    "土地增值税暂行条例": ("中华人民共和国土地增值税暂行条例", "1994.1.1(现行有效)", "虽冠名暂行但尚未上升为法律"),
}

# ═════ Alert 级别映射 ═════
ALERT_LEVELS = {
    "全文废止": "ERROR",   # 必须替换
    "部分修改": "WARN",    # 建议更新
    "暂行有效": "NOTE",    # 虽名暂行但现行有效
}

def get_valid_citation(text: str) -> Tuple[str, bool, str]:
    """
    输入: 法规引用文本
    返回: (修正后文本, 是否做了替换, 说明)
    
    >>> get_valid_citation("增值税暂行条例")
    ('中华人民共和国增值税法', True, '原条例全文废止，2024.1.1起替换')
    """
    for old, (new, date, note) in DEPRECATED_LAWS.items():
        if old in text:
            if new.startswith("(已废止"):
                return (new, True, f"⚠️ {old}已于{date}{note}")
            return (f"{new}", True, f"{old}已于{date}废止→替换为{new}")
    return (text, False, "")

def check_law_validity(law_text: str) -> Dict:
    """
    全面检查一条法规引用是否有效
    返回: {valid: bool, suggested: str, alert: str, reason: str}
    """
    result = {"valid": True, "suggested": law_text, "alert": "OK", "reason": ""}
    
    for old, (new, date, note) in DEPRECATED_LAWS.items():
        if old in law_text:
            if new.startswith("(已废止"):
                result["valid"] = False
                result["alert"] = "ERROR"
                result["reason"] = f"法规已废止: {old}于{date}{note}"
                result["suggested"] = f"(已废止-不可引用)"
            elif "暂行" in old and "暂行有效" in note:
                result["valid"] = True
                result["alert"] = "NOTE"
                result["reason"] = f"虽名'暂行'但现行有效: {old}({date})"
            else:
                result["valid"] = False
                result["alert"] = "ERROR"
                result["reason"] = f"法规已更新: {old}→{new}({date}施行)"
                result["suggested"] = new
            break
    
    return result

def check_and_fix_law_refs(law_refs: List[str]) -> Tuple[List[str], List[str]]:
    """
    批量检查并修正法规引用列表
    返回: (修正后列表, 告警信息列表)
    """
    fixed = []
    alerts = []
    for ref in law_refs:
        new_ref, changed, alert = get_valid_citation(ref)
        fixed.append(new_ref)
        if changed:
            alerts.append(f"🔴 {ref[:40]}... → {new_ref[:40]}... ({alert})")
    return fixed, alerts

class LawValidityCache:
    """法规时效缓存——启动时加载，运行时 O(1) 查询"""
    
    def __init__(self):
        self._deprecated_set = set(DEPRECATED_LAWS.keys())
        self._mapping = DEPRECATED_LAWS
    
    def is_deprecated(self, law_text: str) -> bool:
        """快速判断是否包含已废止法规"""
        for old in self._deprecated_set:
            if old in law_text:
                return True
        return False
    
    def get_replacement(self, old_law: str) -> str:
        """获取替换后的法规名称"""
        _, result, _ = get_valid_citation(old_law)
        return result
    
    def scan_text(self, text: str) -> List[Dict]:
        """扫描任意文本中的法规引用，返回所有发现和修正建议"""
        findings = []
        for old, (new, date, note) in self._mapping.items():
            if old in text:
                findings.append({
                    "found": old,
                    "suggested": new,
                    "date": date,
                    "note": note,
                    "severity": "ERROR" if not new.startswith("(已废止") else "WARN"
                })
        return findings

# 全局缓存实例
_law_cache = LawValidityCache()

def init_law_checker():
    """在引擎启动时调用，确保法规时效数据已加载"""
    return _law_cache

# ── 批量修复工具：扫描并修复所有JSON文件中的过期法规引用 ──
def batch_fix_law_refs_in_files(file_paths: List[str], dry_run: bool = True) -> Dict:
    """
    批量修复指定JSON文件中的法规引用
    
    返回: {file: {fixed_count: int, details: [str]}}
    """
    results = {}
    for fp in file_paths:
        if not os.path.exists(fp): continue
        try:
            with open(fp, 'r', encoding='utf-8') as f:
                content = f.read()
            
            fixed_count = 0
            new_content = content
            details = []
            
            for old, (new, date, note) in DEPRECATED_LAWS.items():
                if new.startswith("(已废止"): continue  # 跳过无法替换的
                count = new_content.count(old)
                if count > 0:
                    new_content = new_content.replace(old, new)
                    fixed_count += count
                    details.append(f"{old}→{new} ({count}处)")
            
            if fixed_count > 0 and not dry_run:
                with open(fp, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                # 重新验证JSON合法性
                json.loads(new_content)
            
            results[os.path.basename(fp)] = {
                "fixed_count": fixed_count,
                "details": details,
                "dry_run": dry_run
            }
        except Exception as e:
            results[os.path.basename(fp)] = {"error": str(e)}
    
    return results

if __name__ == "__main__":
    # 测试
    print(get_valid_citation("增值税暂行条例"))
    print(get_valid_citation("中华人民共和国增值税法"))
    print(get_valid_citation("城建税暂行条例"))
    print(get_valid_citation("印花税暂行条例"))
    print(get_valid_citation("土地增值税暂行条例"))
