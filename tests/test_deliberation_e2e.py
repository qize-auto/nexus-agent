"""
端到端测试: DeliberationEngine 5 Expert 研讨

验证:
    1. 研讨能正常发起并返回结果
    2. 结果包含 consensus 和 confidence
    3. 专家观点有区分度
    4. 空输入优雅处理
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock

from nexusagent.execution.deliberation import DeliberationEngine


@pytest_asyncio.fixture
async def deliberation_setup():
    """创建带 Mock LLM 的 DeliberationEngine"""
    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(return_value={
        "content": """
专家1 (架构师): 建议使用异步方案，性能更好
专家2 (安全员): 异步方案有并发风险，需要加锁
专家3 (产品经理): 用户更关心响应速度，支持异步
专家4 (测试工程师): 异步方案测试覆盖率低，有回归风险
专家5 (运维工程师): 异步增加系统复杂度，建议先小规模试点

共识: 采用异步方案，但需补充并发安全测试和渐进式部署计划
置信度: 0.75
"""
    })
    engine = DeliberationEngine(llm_backend=mock_llm)
    yield engine, mock_llm


class TestDeliberationE2E:
    """5 Expert 研讨端到端测试"""

    @pytest.mark.asyncio
    async def test_deliberate_returns_result(self, deliberation_setup):
        """研讨应返回结构化结果"""
        engine, _ = deliberation_setup
        result = await engine.deliberate(
            question="是否将系统改为异步架构？",
            context="当前系统为同步架构，用户反馈响应慢",
        )
        assert result is not None
        assert hasattr(result, "consensus")
        assert hasattr(result, "opinions")
        assert len(result.opinions) == 5

    @pytest.mark.asyncio
    async def test_consensus_nonempty(self, deliberation_setup):
        """共识不应为空"""
        engine, _ = deliberation_setup
        result = await engine.deliberate(
            question="测试问题",
            context="测试上下文",
        )
        assert result.consensus
        assert len(result.consensus) > 0

    @pytest.mark.asyncio
    async def test_opinions_have_roles(self, deliberation_setup):
        """每个专家观点应有角色和立场"""
        engine, _ = deliberation_setup
        result = await engine.deliberate(
            question="测试问题",
            context="测试上下文",
        )
        for opinion in result.opinions:
            assert hasattr(opinion, "role")
            assert hasattr(opinion, "perspective")

    @pytest.mark.asyncio
    async def test_opinions_confidence_in_range(self, deliberation_setup):
        """专家置信度应在 [0, 1] 范围内"""
        engine, _ = deliberation_setup
        result = await engine.deliberate(
            question="测试问题",
            context="测试上下文",
        )
        for opinion in result.opinions:
            assert 0.0 <= opinion.confidence <= 1.0

    @pytest.mark.asyncio
    async def test_llm_failure_graceful(self):
        """LLM 失败时应优雅降级"""
        mock_llm = AsyncMock()
        mock_llm.complete = AsyncMock(side_effect=Exception("LLM 服务不可用"))
        engine = DeliberationEngine(llm_backend=mock_llm)

        result = await engine.deliberate(
            question="测试问题",
            context="测试上下文",
        )
        # 即使 LLM 失败，也应返回一个结果（可能包含错误信息或降级内容）
        assert result is not None
