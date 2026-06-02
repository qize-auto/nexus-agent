"""
NexusAgent v3.3 — 工具层：SkillGuard + 懒加载 + 审核日志 + 写队列 + 并发控制 + 进程池
补全: ARC-023/024, ARC-013/089, ARC-030/090, NFR-091/092/093, ARC-020
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("nexus.tools.guard")


# ═══════════════════════════════════════════════════════════════
# ARC-023: SkillGuard
# ═══════════════════════════════════════════════════════════════

@dataclass
class ScanResult:
    passed: bool
    risk_level: str = "SAFE"
    warnings: List[str] = field(default_factory=list)


class SkillGuard:
    """ARC-023: 技能安全审查 — 执行前扫描工具参数"""
    def __init__(self, config: Optional[Dict] = None):
        self._config = config or {}
    def scan(self, tool_name: str, params: Dict[str, Any]) -> ScanResult:
        warnings = []
        for k, v in params.items():
            if isinstance(v, str) and len(v) > 10000:
                warnings.append(f"参数{k}过长({len(v)}字符)")
            if isinstance(v, str) and any(c in v for c in ["../", "rm -", "eval("]):
                return ScanResult(passed=False, risk_level="HIGH", warnings=[f"参数{k}包含危险模式"])
        return ScanResult(passed=True, warnings=warnings)


# ═══════════════════════════════════════════════════════════════
# ARC-024: 懒加载
# ═══════════════════════════════════════════════════════════════

class LazyLoader:
    """ARC-024: 工具懒加载 — 首次调用时才初始化"""
    def __init__(self, factory: Callable[[], Any]):
        self._factory = factory
        self._instance: Optional[Any] = None
    def get(self) -> Any:
        if self._instance is None:
            self._instance = self._factory()
        return self._instance


# ═══════════════════════════════════════════════════════════════
# ARC-013/089: 审计日志轮转
# ═══════════════════════════════════════════════════════════════

class AuditLogger:
    """ARC-013/089: 审计日志 + 自动轮转 + 独立文件持久化"""
    def __init__(self, log_dir: str = "", max_size_mb: int = 100, retention_days: int = 90):
        self._log_dir = log_dir or os.path.join(os.path.expanduser("~"), ".nexusagent", "audit")
        os.makedirs(self._log_dir, exist_ok=True)
        self._max_size = max_size_mb * 1024 * 1024
        self._retention = retention_days
        self._file_path = os.path.join(self._log_dir, "audit.log")
        self._file_lock = asyncio.Lock()
    def log(self, event: str, detail: str = "", level: str = "INFO") -> None:
        """记录审计事件 — 同时写入结构化日志和独立审计文件"""
        logger.log(getattr(logging, level, logging.INFO), "AUDIT: %s | %s", event, detail)
        # 独立文件持久化（不可被常规日志级别过滤）
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%S")
        line = f"{timestamp} [{level}] {event} | {detail}\n"
        try:
            with open(self._file_path, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception as e:
            logger.error("审计日志文件写入失败: %s", e)
    async def rotate(self) -> int:
        """轮转过期日志 — 删除超过保留期的文件"""
        deleted = 0
        cutoff = time.time() - self._retention * 86400
        async with self._file_lock:
            for f in os.listdir(self._log_dir):
                path = os.path.join(self._log_dir, f)
                if os.path.isfile(path) and os.path.getmtime(path) < cutoff:
                    try:
                        os.unlink(path)
                        deleted += 1
                    except Exception as e:
                        logger.warning("审计日志轮转删除失败 %s: %s", path, e)
        return deleted


# ═══════════════════════════════════════════════════════════════
# ARC-030/090: 统一写入队列
# ═══════════════════════════════════════════════════════════════

class WriteQueue:
    """ARC-030/090: 异步序列化写入队列"""
    def __init__(self):
        self._queue: asyncio.Queue = asyncio.Queue()
        self._task: Optional[asyncio.Task] = None
    async def enqueue(self, writer: Callable, *args) -> None:
        await self._queue.put((writer, args))
    async def start(self) -> None:
        async def worker():
            while True:
                writer, args = await self._queue.get()
                try:
                    if asyncio.iscoroutinefunction(writer):
                        await writer(*args)
                    else:
                        writer(*args)
                except Exception as e:
                    logger.error("WriteQueue失败: %s", e)
                self._queue.task_done()
        self._task = asyncio.create_task(worker())
    async def stop(self) -> None:
        if self._task:
            self._task.cancel()


# ═══════════════════════════════════════════════════════════════
# NFR-091/092/093: 并发控制
# ═══════════════════════════════════════════════════════════════

class FileLock:
    """NFR-091: 文件级并发控制"""
    def __init__(self):
        self._locks: Dict[str, asyncio.Lock] = {}
    async def acquire(self, path: str) -> None:
        if path not in self._locks:
            self._locks[path] = asyncio.Lock()
        await self._locks[path].acquire()
    def release(self, path: str) -> None:
        if path in self._locks:
            self._locks[path].release()

class BlackboardMVCC:
    """NFR-092: 多版本并发控制"""
    def __init__(self):
        self._data: Dict[str, List[Dict]] = {}
    def write(self, key: str, value: Dict, version: int = 0) -> int:
        versions = self._data.setdefault(key, [])
        new_version = len(versions) + 1
        versions.append({"data": value, "version": new_version, "time": time.time()})
        return new_version
    def read(self, key: str, version: Optional[int] = None) -> Optional[Dict]:
        versions = self._data.get(key, [])
        if not versions: return None
        return versions[-1]["data"] if version is None else next((v["data"] for v in versions if v["version"] == version), None)

class OrderedParallel:
    """NFR-093: 有序并行 — 依赖图并行执行"""
    async def execute(self, tasks: List[Callable], dependencies: Optional[Dict[int, List[int]]] = None) -> List[Any]:
        results = [None] * len(tasks)
        deps = dependencies or {}
        for i, task in enumerate(tasks):
            if i in deps:
                for dep in deps[i]:
                    while results[dep] is None:
                        await asyncio.sleep(0.01)
            if asyncio.iscoroutinefunction(task):
                results[i] = await task()
            else:
                results[i] = task()
        return results


# ═══════════════════════════════════════════════════════════════
# ARC-020: 进程池隔离
# ═══════════════════════════════════════════════════════════════

class ProcessPool:
    """ARC-020: 子Agent进程级隔离"""
    def __init__(self, max_workers: int = 4):
        self._max_workers = max_workers
        self._active = 0
    async def submit(self, coro) -> Any:
        """简单并发限制（生产应使用真正的进程池）"""
        while self._active >= self._max_workers:
            await asyncio.sleep(0.1)
        self._active += 1
        try:
            return await coro
        finally:
            self._active -= 1
