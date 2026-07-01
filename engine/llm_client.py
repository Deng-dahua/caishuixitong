"""
统一LLM客户端 — 支持DeepSeek/Ollama/OpenRouter/OpenAI多后端自动切换

优先级：DeepSeek > Ollama(本地) > OpenRouter(免费) > 纯本地回退
"""
import json, os, httpx, asyncio
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

@dataclass
class LLMResponse:
    content: str
    model: str = ""
    backend: str = "unknown"
    tokens_used: int = 0
    raw: Optional[Dict] = None

class LLMClient:
    """多后端LLM客户端，自动检测可用后端"""
    
    def __init__(self):
        self._backends = []
        self._active = None
        self._scan()
    
    def _scan(self):
        """扫描可用后端（仅当真正可连通时加入）"""
        # 1. DeepSeek（国内首选，API免费额度30元）
        ds_key = os.environ.get("DEEPSEEK_API_KEY", "")
        if ds_key and self._probe_http("https://api.deepseek.com"):
            self._backends.append(("deepseek", {
                "url": "https://api.deepseek.com/v1/chat/completions",
                "key": ds_key,
                "model": "deepseek-chat",
            }))
        
        # 2. Ollama (本地，需验证实际响应)
        if self._probe_ollama():
            self._backends.append(("ollama", {
                "url": "http://localhost:11434/api/chat",
                "model": "qwen2.5:7b",
            }))
        
        # 3. OpenRouter (免费模型)
        or_key = os.environ.get("OPENROUTER_API_KEY", "")
        if or_key:
            self._backends.append(("openrouter", {
                "url": "https://openrouter.ai/api/v1/chat/completions",
                "key": or_key,
                "model": "google/gemma-3-27b-it:free",
            }))
        
        # 4. OpenAI兼容
        oa_key = os.environ.get("OPENAI_API_KEY", "")
        oa_url = os.environ.get("OPENAI_BASE_URL", "")
        if oa_key:
            self._backends.append(("openai", {
                "url": oa_url or "https://api.openai.com/v1/chat/completions",
                "key": oa_key,
                "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            }))
        
        self._set_active()
        
    def _probe_http(self, base_url: str) -> bool:
        """探测HTTP服务是否可连通"""
        try:
            resp = httpx.get(base_url, timeout=3.0)
            return resp.status_code < 500
        except:
            return False
    
    def _probe_ollama(self) -> bool:
        """探测Ollama是否实际在运行且有模型"""
        try:
            resp = httpx.get("http://localhost:11434/api/tags", timeout=3.0)
            if resp.status_code == 200:
                data = resp.json()
                models = data.get("models", [])
                return len(models) > 0
            return False
        except:
            return False
    
    def _set_active(self):
        """设置当前活跃后端"""
        self._active = self._backends[0] if self._backends else None
    
    @property
    def available(self) -> bool:
        return self._active is not None
    
    @property
    def active_backend(self) -> str:
        return self._active[0] if self._active else "none"
    
    def chat(self, messages: List[Dict], system: str = "", 
             temperature: float = 0.3, max_tokens: int = 2000) -> LLMResponse:
        """同步调用LLM"""
        if not self._active:
            return LLMResponse(content="", backend="none")
        
        name, cfg = self._active
        full_messages = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)
        
        try:
            if name in ("deepseek", "openai", "openrouter"):
                return self._call_openai_compat(name, cfg, full_messages, temperature, max_tokens)
            elif name == "ollama":
                return self._call_ollama(cfg, full_messages, temperature, max_tokens)
        except Exception as e:
            # 尝试下一个后端
            idx = self._backends.index((name, cfg))
            for i in range(idx + 1, len(self._backends)):
                try:
                    self._active = self._backends[i]
                    return self.chat(messages, system, temperature, max_tokens)
                except:
                    continue
            self._active = None
            return LLMResponse(content="", backend="failed")
        
        return LLMResponse(content="", backend="no_match")
    
    def _call_openai_compat(self, name, cfg, messages, temperature, max_tokens):
        headers = {"Content-Type": "application/json"}
        headers["Authorization"] = f"Bearer {cfg['key']}"
        
        body = {
            "model": cfg["model"],
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        
        resp = httpx.post(cfg["url"], headers=headers, json=body, timeout=30.0)
        resp.raise_for_status()
        data = resp.json()
        
        content = data["choices"][0]["message"]["content"]
        return LLMResponse(
            content=content.strip(),
            model=cfg["model"],
            backend=name,
            tokens_used=data.get("usage", {}).get("total_tokens", 0),
            raw=data,
        )
    
    def _call_ollama(self, cfg, messages, temperature, max_tokens):
        # Ollama uses a different format
        system_msg = ""
        user_msgs = []
        for m in messages:
            if m["role"] == "system":
                system_msg = m["content"]
            else:
                user_msgs.append(m)
        
        body = {
            "model": cfg["model"],
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        
        resp = httpx.post(cfg["url"], json=body, timeout=60.0)
        resp.raise_for_status()
        data = resp.json()
        
        content = data.get("message", {}).get("content", "")
        return LLMResponse(
            content=content.strip(),
            model=cfg["model"],
            backend="ollama",
        )

# 全局单例
llm = LLMClient()

def get_llm() -> LLMClient:
    return llm

def is_llm_available() -> bool:
    return llm.available
