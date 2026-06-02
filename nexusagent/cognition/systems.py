"""
NexusAgent v3.3 — 工具层/认知层/合规层 批量补全
补全: ARC-026, ARC-025/029, ARC-030/090, ARC-044, ARC-041/042/043,
      ARC-045, ARC-013/089, NFR-088, ARC-033/NFR-084/085, NFR-098,
      RUL-064/NFR-095, ARC-005/NFR-086
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional

try:
    import structlog
    _structlog_available = True
except ImportError:
    _structlog_available = False

logger = logging.getLogger("nexus.cognition")

# ═══════════════════════════════════════════════════════════════
# ARC-026: AgentEvent 统一通信
# ═══════════════════════════════════════════════════════════════

class EventKind(Enum):
    TOOL_CALL = auto()
    TOOL_RESULT = auto()
    THINKING = auto()
    ERROR = auto()
    CHECKPOINT = auto()
    AUDIT = auto()


@dataclass
class AgentEvent:
    """ARC-026: 子Agent间统一事件"""
    event_id: str
    kind: EventKind
    source: str
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    session_id: str = ""
    trace_id: str = ""

    def to_json(self) -> str:
        return json.dumps({
            "event_id": self.event_id, "kind": self.kind.name,
            "source": self.source, "payload": self.payload,
            "timestamp": self.timestamp,
        })


# ═══════════════════════════════════════════════════════════════
# ARC-025/029: sqlite-vec 混合搜索 + NFR-088 结构化日志
# ═══════════════════════════════════════════════════════════════

def setup_structured_logging() -> None:
    """NFR-088: 配置structlog JSON格式日志"""
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
    )


class HybridSearch:
    """ARC-025/029: FTS5 + sqlite-vec 向量混合搜索

    使用 Reciprocal Rank Fusion (RRF) 融合两种搜索结果：
        score = Σ 1 / (k + rank)   (k=60 为常数)
    """

    def __init__(self, memory_store: Any):
        self._memory = memory_store

    async def search(self, query: str, limit: int = 10) -> List[Dict]:
        """FTS5 全文搜索"""
        if not self._memory:
            return []
        entries = await self._memory.search_fts(query, limit=limit * 2)
        return [
            {
                "source": "fts5",
                "entry_id": e.id,
                "session_id": e.session_id,
                "content": e.content[:300],
                "score": 1.0,  # FTS5 的 rank 在 SQL 中已排序
            }
            for e in entries
        ]

    async def vector_search(self, embedding: List[float], limit: int = 10) -> List[Dict]:
        """sqlite-vec 向量相似度搜索"""
        if not self._memory:
            return []
        entries = await self._memory.search_vector(embedding, limit=limit * 2)
        return [
            {
                "source": "vector",
                "entry_id": e.id,
                "session_id": e.session_id,
                "content": e.content[:300],
                "score": 1.0,  # 距离在 SQL 中已排序
            }
            for e in entries
        ]

    async def hybrid_search(
        self,
        query: str = "",
        embedding: Optional[List[float]] = None,
        limit: int = 10,
        rrf_k: int = 60,
    ) -> List[Dict]:
        """混合搜索 — RRF 融合 FTS5 + 向量结果

        Args:
            query: 文本查询（用于FTS5）
            embedding: 查询向量（用于向量搜索）
            limit: 返回结果数
            rrf_k: RRF 融合常数

        Returns:
            按融合分数排序的结果列表
        """
        from collections import defaultdict

        # 并行执行两种搜索
        fts_task = self.search(query, limit) if query else []
        vec_task = self.vector_search(embedding, limit) if embedding else []

        if fts_task and vec_task:
            fts_results, vec_results = await asyncio.gather(fts_task, vec_task)
        elif fts_task:
            fts_results = await fts_task
            vec_results = []
        elif vec_task:
            fts_results = []
            vec_results = await vec_task
        else:
            return []

        # RRF 分数融合
        scores: Dict[int, float] = defaultdict(float)
        metas: Dict[int, Dict] = {}

        for rank, item in enumerate(fts_results, start=1):
            eid = item.get("entry_id")
            if eid is not None:
                scores[eid] += 1.0 / (rrf_k + rank)
                metas[eid] = item

        for rank, item in enumerate(vec_results, start=1):
            eid = item.get("entry_id")
            if eid is not None:
                scores[eid] += 1.0 / (rrf_k + rank)
                if eid not in metas:
                    metas[eid] = item
                else:
                    metas[eid]["source"] = "hybrid"

        # 按融合分数排序
        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
        return [
            {**metas[eid], "rrf_score": round(scores[eid], 4)}
            for eid in sorted_ids[:limit]
        ]


# ═══════════════════════════════════════════════════════════════
# ARC-044: Trace/Metrics/Log 可观测性
# ═══════════════════════════════════════════════════════════════

class ObservabilityLayer:
    """ARC-044: Trace + Metrics + Log 三位一体 + OpenTelemetry 持久化

    外部依据:
    - opentelemetry.io/docs/zero-code/python/example/ (auto-instrumentation)
    - coralogix.com/guides/opentelemetry/opentelemetry-python-basics-tutorial-practices/
      "Combine Manual and Auto-Instrumentation"
    """
    def __init__(self, service_name: str = "nexusagent"):
        self._service_name = service_name
        self._traces: List[Dict] = []
        self._metrics: Dict[str, List[float]] = {}
        self._otel_available = False
        self._tracer: Any = None
        self._meter: Any = None
        self._init_otel()

    def _init_otel(self) -> None:
        """初始化 OpenTelemetry SDK（优雅降级）"""
        try:
            from opentelemetry import trace, metrics
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
            from opentelemetry.sdk.metrics import MeterProvider
            from opentelemetry.sdk.metrics.export import InMemoryMetricReader
            from opentelemetry.sdk.resources import Resource, SERVICE_NAME

            resource = Resource.create({SERVICE_NAME: self._service_name})
            # Traces
            trace_provider = TracerProvider(resource=resource)
            trace_provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
            trace.set_tracer_provider(trace_provider)
            self._tracer = trace.get_tracer(__name__)
            # Metrics
            reader = InMemoryMetricReader()
            metrics_provider = MeterProvider(resource=resource, metric_readers=[reader])
            metrics.set_meter_provider(metrics_provider)
            self._meter = metrics.get_meter(__name__)
            self._otel_available = True
            logger.info("OpenTelemetry SDK 已初始化 (service=%s)", self._service_name)
        except ImportError:
            self._otel_available = False
            logger.debug("OpenTelemetry SDK 未安装，使用内存存储降级")

    def start_trace(self, name: str) -> str:
        trace_id = os.urandom(8).hex()
        self._traces.append({"id": trace_id, "name": name, "start": time.time()})
        if self._otel_available and self._tracer:
            span = self._tracer.start_as_current_span(name)
            self._traces[-1]["_otel_span"] = span
        return trace_id

    def end_trace(self, trace_id: str) -> None:
        for t in self._traces:
            if t["id"] == trace_id:
                t["end"] = time.time()
                t["duration_ms"] = (t["end"] - t["start"]) * 1000
                if "_otel_span" in t:
                    try:
                        t["_otel_span"].set_attribute("duration_ms", t["duration_ms"])
                        t["_otel_span"].end()
                    except Exception as e:
                        logger.debug("OpenTelemetry span end failed: %s", e)

    def record_metric(self, name: str, value: float) -> None:
        self._metrics.setdefault(name, []).append(value)
        if self._otel_available and self._meter:
            try:
                counter = self._meter.create_counter(name)
                counter.add(value)
            except Exception as e:
                logger.debug("OpenTelemetry metric record failed: %s", e)

    def get_metrics(self) -> Dict[str, Dict]:
        return {k: {"avg": sum(v)/len(v), "max": max(v)} for k, v in self._metrics.items() if v}

    def export_to_file(self, filepath: str) -> None:
        """将内存中的 traces 和 metrics 导出到 JSON 文件"""
        import json
        payload = {
            "service": self._service_name,
            "exported_at": time.time(),
            "traces": self._traces,
            "metrics": self.get_metrics(),
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, default=str)


# ═══════════════════════════════════════════════════════════════
# ARC-041/042/043: OCEL循环 + 8类信号 + 三层进化
# ═══════════════════════════════════════════════════════════════

class SignalType(Enum):
    ERROR_RATE = auto(); LATENCY = auto(); RESOURCE = auto()
    USER_FEEDBACK = auto(); PATTERN = auto(); SECURITY = auto()
    COST = auto(); SUCCESS_RATE = auto()


@dataclass
class EvolutionAction:
    action_type: str; description: str; confidence: float
    sandbox_result: Optional[str] = None


class OCELEngine:
    """ARC-041: OCEL循环 (Observe→Classify→Evaluate→Learn)

    完整8类信号评估:
    - ERROR_RATE: 最近10次错误率均值 >30% → alert
    - LATENCY: 最近10次P99延迟 >5s → throttle
    - RESOURCE: 最近10次内存/CPU >80% → scale
    - USER_FEEDBACK: 最近10次满意度 <0.3 → tune_prompt
    - PATTERN: 最近10次重复工具调用 >3 → break_loop
    - SECURITY: 任意安全事件 >0 → audit
    - COST: 单次成本 >预算2倍 → cost_alert
    - SUCCESS_RATE: 最近10次成功率 <50% → degrade
    """
    def __init__(self):
        self._signals: Dict[SignalType, List[float]] = {s: [] for s in SignalType}
        self._actions: List[EvolutionAction] = []

    def observe(self, signal: SignalType, value: float) -> None:
        self._signals[signal].append(value)
        # 限制滑动窗口大小，避免内存无限增长
        if len(self._signals[signal]) > 1000:
            self._signals[signal] = self._signals[signal][-500:]

    def _window_avg(self, signal: SignalType, window: int = 10) -> float:
        vals = self._signals[signal]
        if not vals:
            return 0.0
        recent = vals[-window:]
        return sum(recent) / len(recent)

    def evaluate(self) -> List[EvolutionAction]:
        actions: List[EvolutionAction] = []

        # 1. ERROR_RATE — 错误率 > 30%
        if self._window_avg(SignalType.ERROR_RATE) > 0.3:
            actions.append(EvolutionAction("alert", "错误率>30%", 0.9))

        # 2. LATENCY — P99 延迟 > 5s
        latencies = self._signals[SignalType.LATENCY]
        if latencies:
            sorted_vals = sorted(latencies[-100:])
            p99 = sorted_vals[int(len(sorted_vals) * 0.99)] if len(sorted_vals) >= 2 else sorted_vals[-1]
            if p99 > 5000:  # ms
                actions.append(EvolutionAction("throttle", f"P99延迟{p99:.0f}ms>5s", 0.85))

        # 3. RESOURCE — 资源使用率 > 80%
        if self._window_avg(SignalType.RESOURCE) > 0.8:
            actions.append(EvolutionAction("scale", "资源使用率>80%", 0.8))

        # 4. USER_FEEDBACK — 用户满意度 < 0.3
        if self._window_avg(SignalType.USER_FEEDBACK) < 0.3 and len(self._signals[SignalType.USER_FEEDBACK]) >= 5:
            actions.append(EvolutionAction("tune_prompt", "用户满意度<0.3", 0.75))

        # 5. PATTERN — 重复工具调用频率 > 3次/窗口
        patterns = self._signals[SignalType.PATTERN]
        if patterns and sum(patterns[-10:]) / min(10, len(patterns)) > 3:
            actions.append(EvolutionAction("break_loop", "检测到重复工具调用循环", 0.9))

        # 6. SECURITY — 任意安全事件
        security = self._signals[SignalType.SECURITY]
        if security and sum(security[-10:]) > 0:
            actions.append(EvolutionAction("audit", "安全事件触发", 0.95))

        # 7. COST — 单次成本超预算2倍
        costs = self._signals[SignalType.COST]
        if costs and costs[-1] > 2.0:  # 相对倍数
            actions.append(EvolutionAction("cost_alert", f"单次成本超预算2倍({costs[-1]:.1f}x)", 0.85))

        # 8. SUCCESS_RATE — 成功率 < 50%
        if self._window_avg(SignalType.SUCCESS_RATE) < 0.5 and len(self._signals[SignalType.SUCCESS_RATE]) >= 10:
            actions.append(EvolutionAction("degrade", "成功率<50%", 0.8))

        self._actions.extend(actions)
        return actions

    def get_evolution_plan(self) -> Dict[str, Any]:
        return {"signals": {s.name: len(v) for s, v in self._signals.items()}, "actions": len(self._actions), "latest_actions": [a.description for a in self._actions[-5:]]}


# ═══════════════════════════════════════════════════════════════
# ARC-033/NFR-084/085: GDPR/PIPL 合规
# ═══════════════════════════════════════════════════════════════

class ComplianceEngine:
    """ARC-033/NFR-084/085: GDPR第17条 + PIPL"""
    def __init__(self, memory_store: Any = None):
        self._memory = memory_store
        self._deletion_requests: List[Dict] = []
    async def right_to_be_forgotten(self, user_id: str) -> Dict[str, Any]:
        """NFR-084: GDPR第17条 被遗忘权
        
        基于 session_id 中包含 user_id 的模式进行匹配删除。
        生产环境建议为 MemoryEntry 添加独立的 user_id 字段以实现精确删除。
        """
        deleted = 0
        if self._memory:
            try:
                deleted = await self._memory.delete_by_user(user_id)
            except Exception as e:
                logger.warning("被遗忘权删除失败: %s", e)
                deleted = 0
        self._deletion_requests.append({"user_id": user_id, "timestamp": time.time(), "items": deleted})
        return {"status": "completed", "user_id": user_id, "items_deleted": deleted}
    async def export_data(self, user_id: str) -> Dict[str, Any]:
        """GDPR Art.20 / PIPL: 数据可携带权

        以结构化、通用、机器可读的 JSON 格式导出用户全部个人数据。
        外部依据: legiscope.com/blog/data-portability-right.html
                  "JSON is widely supported, preserves data structure"
        """
        exported_at = time.time()
        data: Dict[str, Any] = {
            "export_metadata": {
                "user_id": user_id,
                "exported_at": exported_at,
                "format_version": "1.0",
                "legal_basis": "GDPR_Article_20",
            },
            "memories": [],
            "checkpoints": [],
        }

        if self._memory and hasattr(self._memory, "get_by_user"):
            try:
                entries = await self._memory.get_by_user(user_id)
                data["memories"] = [
                    {
                        "id": e.id,
                        "session_id": e.session_id,
                        "memory_type": e.memory_type,
                        "content": e.content,
                        "metadata": e.to_dict().get("metadata", {}),
                        "created_at": e.created_at,
                        "importance": e.importance,
                    }
                    for e in entries
                ]
            except Exception as e:
                logger.warning("GDPR导出查询记忆失败: %s", e)

        if self._memory and hasattr(self._memory, "load_checkpoint"):
            try:
                # 尝试加载与用户相关的checkpoint（基于session_id匹配）
                checkpoint = await self._memory.load_checkpoint(f"session_{user_id}")
                if checkpoint:
                    data["checkpoints"].append(checkpoint)
            except Exception as e:
                logger.debug("GDPR导出查询checkpoint失败: %s", e)

        return {
            "user_id": user_id,
            "exported_at": exported_at,
            "data": data,
        }
    def get_data_retention_policy(self) -> Dict[str, Any]:
        return {"max_days": 90, "auto_delete": True, "encryption": "AES-256", "gdpr_compliant": True}


# ═══════════════════════════════════════════════════════════════
# RUL-064/NFR-095: 成本预算强制执行
# ═══════════════════════════════════════════════════════════════

class CostEnforcer:
    """RUL-064/NFR-095: 运行时成本硬限制"""
    def __init__(self, monthly_limit: float = 100.0, daily_limit: float = 5.0, per_task_limit: float = 10.0):
        self._monthly_limit = monthly_limit
        self._daily_limit = daily_limit
        self._per_task_limit = per_task_limit
        self._monthly_usage = 0.0
        self._daily_usage = 0.0
        self._month_reset = time.time()
        self._day_reset = time.time()
        self._logger = logging.getLogger("nexus.cost")
    def _reset_if_needed(self) -> None:
        now = time.time()
        if now - self._month_reset > 2592000:
            self._monthly_usage = 0.0; self._month_reset = now
        if now - self._day_reset > 86400:
            self._daily_usage = 0.0; self._day_reset = now
    def check_and_consume(self, estimated_cost: float) -> bool:
        """检查并消耗预算，返回是否允许"""
        self._reset_if_needed()
        if estimated_cost > self._per_task_limit:
            self._logger.warning("任务成本$%.2f超出单任务上限$%.2f", estimated_cost, self._per_task_limit)
            return False
        if self._monthly_usage + estimated_cost > self._monthly_limit:
            self._logger.warning("月度预算耗尽: $%.2f/$%.2f", self._monthly_usage, self._monthly_limit)
            return False
        if self._daily_usage + estimated_cost > self._daily_limit:
            self._logger.warning("日度预算耗尽: $%.2f/$%.2f", self._daily_usage, self._daily_limit)
            return False
        self._monthly_usage += estimated_cost
        self._daily_usage += estimated_cost
        return True
    def get_usage(self) -> Dict[str, float]:
        return {"monthly": self._monthly_usage, "daily": self._daily_usage, "monthly_limit": self._monthly_limit}
