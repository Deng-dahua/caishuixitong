"""
统一LLM客户端 — 支持DeepSeek/Ollama/OpenRouter/OpenAI多后端自动切换

优先级：DeepSeek > Ollama(本地) > OpenRouter(免费) > 纯本地回退
"""
import json, os, httpx, asyncio
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from llm_config import get_llm_config

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
        """扫描可用后端（支持DeepSeek/智谱/豆包/OpenAI等所有OpenAI兼容API）"""
        # 0. 从全局配置文件加载API Key（账套选择页填写的）
        global_key = self._load_global_key()
        
        # 1. 全局API Key（统一入口，兼容所有OpenAI格式的API）
        if global_key:
            # 自动推断base_url（可根据key前缀判断服务商）
            base_url = self._detect_provider(global_key)
            self._backends.append(("global", {
                "url": base_url,
                "key": global_key,
                "model": "auto",
            }))
        
        # 2. 环境变量指定的DeepSeek
        ds_key = os.environ.get("DEEPSEEK_API_KEY", "")
        if ds_key and not global_key:  # 有全局key就不用环境变量
            self._backends.append(("deepseek", {
                "url": "https://api.deepseek.com/v1/chat/completions",
                "key": ds_key,
                "model": "deepseek-chat",
            }))
        
        # 3. Ollama (本地)
        if self._probe_ollama():
            self._backends.append(("ollama", {
                "url": "http://localhost:11434/api/chat",
                "model": "qwen2.5:7b",
            }))
        
        self._set_active()
    
    def _load_global_key(self) -> str:
        return get_llm_config(include_secret=True).get("key", "")
        """从全局配置文件加载API Key"""
        try:
            path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "api_key.json")
            with open(path, encoding="utf-8") as f:
                return json.load(f).get("key", "")
        except:
            return ""
    
    def _detect_provider(self, key: str) -> str:
        """根据API Key前缀自动检测服务商，返回对应的base_url"""
        # sk-xxx格式 → OpenAI兼容，可以使用DeepSeek作为默认端点
        # DeepSeek的API兼容OpenAI格式，智谱/豆包也兼容
        return get_llm_config(include_secret=False)["base_url"].rstrip("/") + "/chat/completions"
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
            if name in ("global", "deepseek", "openai", "openrouter"):
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

def reload_llm_client(api_key: str = ""):
    """重载LLM客户端（API Key变更时调用）"""
    global llm
    llm = LLMClient()
    return llm.available
