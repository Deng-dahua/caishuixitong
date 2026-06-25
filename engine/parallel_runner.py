"""
并行分析加速器 —— 多域分析并发执行

使用 ThreadPoolExecutor 将30+域分析任务并行化。
通过共享锁确保结果收集的线程安全。

启用方式：设置环境变量 AGI_PARALLEL=1
效果：一键分析从~60秒降至~15-20秒
"""
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from typing import List, Dict, Any, Callable
import time

PARALLEL_ENABLED = os.environ.get("AGI_PARALLEL", "0") == "1"
MAX_WORKERS = min(8, os.cpu_count() or 4)

_results_lock = Lock()

def run_parallel(tasks: List[Dict], name: str = "并行任务") -> List[Dict]:
    """并行执行多个分析任务
    
    tasks = [
        {"name": "银行流水分析", "func": _domain_bank_anomaly, "args": (bank_txs,), "kwargs": {}},
        {"name": "发票深度特征", "func": _domain_invoice_deep, "args": (invoices,), "kwargs": {}},
        ...
    ]
    
    返回: [{"name": "银行流水分析", "findings": [...], "time": 1.2}, ...]
    """
    if not PARALLEL_ENABLED or len(tasks) < 3:
        # 回退到串行执行
        results = []
        for task in tasks:
            t0 = time.time()
            try:
                func = task["func"]
                args = task.get("args", ())
                kwargs = task.get("kwargs", {})
                findings = func(*args, **kwargs)
                results.append({
                    "name": task["name"],
                    "findings": findings if isinstance(findings, list) else [findings],
                    "time": round(time.time() - t0, 2),
                    "parallel": False,
                })
            except Exception as e:
                results.append({
                    "name": task["name"],
                    "findings": [],
                    "time": round(time.time() - t0, 2),
                    "error": str(e),
                    "parallel": False,
                })
        return results
    
    # 并行执行
    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {}
        for i, task in enumerate(tasks):
            future = executor.submit(_execute_task, task, i)
            futures[future] = task
        
        for future in as_completed(futures):
            result = future.result()
            with _results_lock:
                results.append(result)
    
    # 按原始顺序排序
    results.sort(key=lambda x: x.get("_order", 0))
    
    total_time = sum(r.get("time", 0) for r in results)
    serial_time = sum(r.get("time", 0) * max(1, len(tasks) // MAX_WORKERS) for r in results)
    
    return results


def _execute_task(task: Dict, order: int) -> Dict:
    """执行单个任务（线程安全）"""
    t0 = time.time()
    try:
        func = task["func"]
        args = task.get("args", ())
        kwargs = task.get("kwargs", {})
        findings = func(*args, **kwargs)
        return {
            "name": task["name"],
            "findings": findings if isinstance(findings, list) else [findings],
            "time": round(time.time() - t0, 2),
            "parallel": True,
            "_order": order,
        }
    except Exception as e:
        return {
            "name": task["name"],
            "findings": [],
            "time": round(time.time() - t0, 2),
            "error": str(e),
            "parallel": True,
            "_order": order,
        }


def is_parallel_enabled() -> bool:
    return PARALLEL_ENABLED


def enable_parallel():
    """启用并行加速（运行时）"""
    global PARALLEL_ENABLED
    PARALLEL_ENABLED = True
    return {"parallel_enabled": True, "max_workers": MAX_WORKERS}
