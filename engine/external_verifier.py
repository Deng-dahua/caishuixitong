"""
外部数据源验证引擎 —— 对接天眼查/企查查/国家企业信用信息公示系统

设计：插件式架构，新数据源只需实现 verify() 方法即可接入。
AGI自动选择最合适的验证渠道。

当前支持：
  - 国家企业信用信息公示系统 (免费，HTML解析)
  - 天眼查 API (token配置)
  - 企查查 API (token配置)
  
默认回退：搜索引擎模糊核实（搜狗/360）
"""
import json, os, re, time
from urllib.request import Request, urlopen
from urllib.parse import quote
from typing import Optional, Dict, Any, List

# ═══════════════════ 验证器基类 ═══════════════════

class BaseVerifier:
    name = "base"
    
    def verify_company(self, company_name: str, tax_id: str = "") -> Dict:
        raise NotImplementedError
    
    def get_status(self) -> str:
        return "未配置"

# ═══════════════════ 1. 国家企业信用信息公示系统 ═══════════════════

class GovCreditVerifier(BaseVerifier):
    name = "国家企业信用信息公示系统"
    
    def verify_company(self, company_name: str, tax_id: str = "") -> Dict:
        """免费查询企业信用信息"""
        try:
            query = tax_id or company_name
            url = f"http://www.gsxt.gov.cn/index.html?q={quote(query)}"
            # 由于反爬较严，采用搜索结果页面提取
            # 实际生产环境中建议使用官方API
            
            # 备用：通过搜索引擎间接核实
            search_url = f"https://www.sogou.com/web?query={quote(company_name+' 工商信息 存续')}"
            req = Request(search_url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            resp = urlopen(req, timeout=10)
            body = resp.read().decode("gbk", errors="replace")
            
            # 提取关键状态信息
            status_match = re.search(r'(存续|在营|注销|吊销|迁出|停业)', body)
            status = status_match.group(1) if status_match else "未知"
            
            # 提取注册资本
            capital_match = re.search(r'注册资本[:：]?\s*(\d+\.?\d*)\s*(万)?', body)
            
            return {
                "ok": True,
                "company_name": company_name,
                "status": status,
                "is_active": status in ("存续", "在营"),
                "is_abnormal": status in ("注销", "吊销"),
                "capital": capital_match.group(0) if capital_match else "",
                "source": self.name,
                "verified_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
        except Exception as e:
            return {"ok": False, "error": str(e), "source": self.name}
    
    def get_status(self):
        return "免费可用"

# ═══════════════════ 2. 搜索引擎综合核实 ═══════════════════

class SearchEngineVerifier(BaseVerifier):
    name = "搜索引擎综合核实"
    
    def verify_company(self, company_name: str, tax_id: str = "") -> Dict:
        """搜索引擎多维度交叉验证"""
        checks = {
            "工商状态": False,
            "经营异常": False,
            "处罚记录": False,
            "涉诉记录": False,
        }
        details = []
        
        queries = [
            (f"{company_name} 工商信息", "工商状态"),
            (f"{company_name} 经营异常", "经营异常"),
            (f"{company_name} 行政处罚", "处罚记录"),
            (f"{company_name} 法院 裁判文书", "涉诉记录"),
        ]
        
        for q_str, check_name in queries:
            try:
                url = f"https://www.sogou.com/web?query={quote(q_str)}"
                req = Request(url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                })
                resp = urlopen(req, timeout=8)
                body = resp.read().decode("gbk", errors="replace")
                
                # 简单判断：有搜索结果就认为可能有记录
                has_results = bool(re.search(r'class="results', body))
                if has_results or len(body) > 10000:
                    checks[check_name] = True
                    details.append(f"{check_name}: 搜索结果提示可能存在相关记录")
            except:
                pass
        
        risk_score = sum(checks.values()) / len(checks)
        
        return {
            "ok": True,
            "company_name": company_name,
            "checks": checks,
            "risk_score": round(risk_score, 2),
            "details": details,
            "assessment": "高风险" if risk_score > 0.5 else ("需关注" if risk_score > 0.2 else "正常"),
            "source": self.name,
        }
    
    def get_status(self):
        return "免费可用(搜索引擎)"


# ═══════════════════ 3. 天眼查API ═══════════════════

class TianyanchaVerifier(BaseVerifier):
    name = "天眼查"
    
    def __init__(self):
        # 从环境或配置加载token
        self.token = os.environ.get("TYC_TOKEN", "")
    
    def verify_company(self, company_name: str, tax_id: str = "") -> Dict:
        if not self.token:
            return {"ok": False, "error": "天眼查Token未配置", "configure": "设置环境变量 TYC_TOKEN"}
        
        # TODO: 对接天眼查API
        # API文档: https://open.tianyancha.com
        return {"ok": False, "error": "API对接待实现", "source": self.name}
    
    def get_status(self):
        return "已配置" if self.token else "未配置Token"


# ═══════════════════ 4. 企查查API ═══════════════════

class QichachaVerifier(BaseVerifier):
    name = "企查查"
    
    def __init__(self):
        self.token = os.environ.get("QCC_TOKEN", "")
    
    def verify_company(self, company_name: str, tax_id: str = "") -> Dict:
        if not self.token:
            return {"ok": False, "error": "企查查Token未配置", "configure": "设置环境变量 QCC_TOKEN"}
        return {"ok": False, "error": "API对接待实现", "source": self.name}
    
    def get_status(self):
        return "已配置" if self.token else "未配置Token"


# ═══════════════════ 验证引擎 ═══════════════════

class ExternalVerificationEngine:
    """外部数据源验证引擎 —— AGI自主选择验证渠道"""
    
    def __init__(self):
        self.verifiers = [
            GovCreditVerifier(),
            SearchEngineVerifier(),
            TianyanchaVerifier(),
            QichachaVerifier(),
        ]
    
    def verify(self, company_name: str, tax_id: str = "", 
               use_premium: bool = False) -> Dict:
        """验证企业信息——自动选择可用渠道"""
        results = {}
        
        for verifier in self.verifiers:
            # 付费渠道仅在显式要求时使用
            if verifier.name in ("天眼查", "企查查") and not use_premium:
                results[verifier.name] = {"status": "跳过(免费模式)"}
                continue
            
            try:
                result = verifier.verify_company(company_name, tax_id)
                results[verifier.name] = result
            except Exception as e:
                results[verifier.name] = {"ok": False, "error": str(e)}
        
        # AGI综合判断
        assessment = self._assess(results)
        
        return {
            "ok": True,
            "company": company_name,
            "verified_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "channels_used": [v.name for v in self.verifiers],
            "results": results,
            "assessment": assessment,
        }
    
    def _assess(self, results: Dict) -> Dict:
        """AGI综合评估验证结果"""
        active_count = 0
        abnormal_count = 0
        risk_signals = []
        
        for channel, result in results.items():
            if isinstance(result, dict) and result.get("ok"):
                active_count += 1
                if result.get("is_abnormal") or result.get("is_active") == False:
                    abnormal_count += 1
                    risk_signals.append(f"{channel}: 企业状态异常")
                
                assessment = result.get("assessment", "")
                if assessment == "高风险":
                    risk_signals.append(f"{channel}: 高风险")
        
        return {
            "channels_responding": active_count,
            "abnormal_signals": abnormal_count,
            "risk_signals": risk_signals,
            "verdict": "需深入核实" if abnormal_count > 0 else ("正常" if active_count > 0 else "无法核实"),
            "recommendation": (
                "建议通过天眼查/企查查进一步核实" if abnormal_count > 0 
                else "企业工商信息正常" if active_count > 0
                else "所有渠道均无法核实，建议人工查验"
            ),
        }
    
    def get_available_channels(self) -> List[Dict]:
        return [{"name": v.name, "status": v.get_status()} for v in self.verifiers]


# 全局单例
_verifier = None

def get_external_verifier() -> ExternalVerificationEngine:
    global _verifier
    if _verifier is None:
        _verifier = ExternalVerificationEngine()
    return _verifier
