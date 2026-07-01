"""
Agent基类 — 所有专业Agent的父类

设计原则：
- 每个Agent有独立的角色定义(system prompt)和领域知识
- Agent通过工具(tools)与外部世界交互
- 协调器(coordinator)负责Agent间的消息路由
"""
import json
from typing import Dict, List, Any, Optional, Callable
from abc import ABC, abstractmethod

class BaseAgent(ABC):
    """专业Agent基类"""
    
    def __init__(self, name: str, role: str, expertise: List[str]):
        self.name = name
        self.role = role
        self.expertise = expertise
        self._tools: Dict[str, Callable] = {}
        self._memory: List[Dict] = []  # 短期记忆
        self._knowledge: Dict[str, Any] = {}  # 领域知识
    
    @property
    def system_prompt(self) -> str:
        """Agent的角色提示词"""
        return f"""你是「{self.name}」——{self.role}。
你的专业领域包括：{', '.join(self.expertise)}。
你的职责：
1. 基于专业知识给出准确判断
2. 对不确定的内容明确标注"待核实"
3. 引用具体数据和法律条文
4. 与其他Agent协作时，输出结构化消息"""
    
    def register_tool(self, name: str, func: Callable):
        """注册工具函数"""
        self._tools[name] = func
    
    def call_tool(self, name: str, **kwargs) -> Any:
        """调用工具"""
        if name not in self._tools:
            raise ValueError(f"工具 '{name}' 未注册")
        return self._tools[name](**kwargs)
    
    def remember(self, key: str, value: Any):
        """存储短期记忆"""
        self._memory.append({"key": key, "value": value, "timestamp": __import__('datetime').datetime.now().isoformat()})
        if len(self._memory) > 50:
            self._memory = self._memory[-50:]
    
    def recall(self, key: str) -> Optional[Any]:
        """检索短期记忆"""
        for m in reversed(self._memory):
            if m["key"] == key:
                return m["value"]
        return None
    
    def set_knowledge(self, key: str, value: Any):
        """设置领域知识"""
        self._knowledge[key] = value
    
    def get_knowledge(self, key: str) -> Optional[Any]:
        """获取领域知识"""
        return self._knowledge.get(key)
    
    @abstractmethod
    def process(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """处理消息，返回结构化响应"""
        pass
    
    def format_for_llm(self, context: Dict[str, Any]) -> List[Dict]:
        """构建发送给LLM的消息列表"""
        messages = [{"role": "system", "content": self.system_prompt}]
        
        # 添加领域知识
        if self._knowledge:
            kn_text = "\n".join(f"- {k}: {v}" for k, v in list(self._knowledge.items())[:10])
            messages.append({"role": "system", "content": f"领域知识：\n{kn_text}"})
        
        # 添加上下文
        ctx_text = json.dumps(context, ensure_ascii=False, indent=2)
        messages.append({"role": "user", "content": f"上下文数据：\n{ctx_text}\n\n请基于以上数据给出专业分析。"})
        
        return messages
