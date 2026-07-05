"""税率阈值配置加载器
所有税务合规逻辑中的硬编码数值必须通过此模块获取，禁止在代码中直接写数字。
用法:
    from engine.thresholds import T
    if deviation > T.ratios.significant_deviation and amount > T.amounts.large_transaction:
        ...
"""
import json
import os

class _ThresholdAccessor:
    """将JSON嵌套结构转换为属性访问"""
    def __init__(self, data):
        self._data = data
    
    def __getattr__(self, name):
        if name.startswith('_'):
            raise AttributeError(name)
        val = self._data.get(name)
        if val is None:
            raise AttributeError(f"threshold '{name}' not found in {list(self._data.keys())}")
        if isinstance(val, dict):
            return _ThresholdAccessor(val)
        return val
    
    def __dir__(self):
        return list(self._data.keys())


def _load_config():
    json_path = os.path.join(os.path.dirname(__file__), 'thresholds.json')
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return _ThresholdAccessor(data)


T = _load_config()
