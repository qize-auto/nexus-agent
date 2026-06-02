"""
端到端集成测试: 完整消息处理链路
"""

import pytest
import asyncio


class TestEndToEnd:
    """完整链路: 用户输入 → 编排 → 安全审查 → 执行 → 输出"""

    def test_full_message_flow(self):
        """正常消息处理"""
        from nexusagent.main import NexusAgent

        async def _test():
            agent = NexusAgent()
            await agent.initialize()
            result = await agent.process_message("test_user", "你好，帮我分析一下项目")
            assert len(result) > 0
            await agent.shutdown()
        asyncio.run(_test())

    def test_dangerous_command_blocked(self):
        """危险命令被阻断 — 直接测试Orchestrator"""
        from nexusagent.main import NexusAgent

        async def _test():
            agent = NexusAgent()
            await agent.initialize()
            # 直接通过Orchestrator测试（process_message走旧路径）
            result = await agent._orchestrator.process("test_user", "请执行 rm -rf /")
            assert "确认" in result.answer or "安全" in result.answer or result.exit_reason == "requires_approval"
            await agent.shutdown()
        asyncio.run(_test())

    def test_multiple_messages_session(self):
        """多轮对话"""
        from nexusagent.main import NexusAgent

        async def _test():
            agent = NexusAgent()
            await agent.initialize()
            for msg in ["你好", "帮我分析架构", "谢谢"]:
                result = await agent.process_message("u1", msg)
                assert len(result) > 0
            await agent.shutdown()
        asyncio.run(_test())

    def test_orchestrator_integrated(self):
        """Orchestrator已集成"""
        from nexusagent.main import NexusAgent

        async def _test():
            agent = NexusAgent()
            await agent.initialize()
            assert agent._orchestrator is not None
            await agent.shutdown()
        asyncio.run(_test())


class TestCostEnforcement:
    """成本预算强制"""

    def test_within_budget(self):
        from nexusagent.cognition.systems import CostEnforcer
        enforcer = CostEnforcer(monthly_limit=100)
        assert enforcer.check_and_consume(1.0) == True

    def test_exceeds_per_task(self):
        from nexusagent.cognition.systems import CostEnforcer
        enforcer = CostEnforcer(per_task_limit=5.0)
        assert enforcer.check_and_consume(10.0) == False

    def test_exceeds_daily(self):
        from nexusagent.cognition.systems import CostEnforcer
        enforcer = CostEnforcer(daily_limit=0.01)
        enforcer.check_and_consume(0.01)  # 耗尽
        assert enforcer.check_and_consume(0.01) == False


class TestSecurityLevel:
    """数据四级分类 + 最小权限同步"""

    def test_can_sync_higher_to_lower(self):
        from nexusagent.interface.adapter import SecurityLevel
        assert SecurityLevel.HIGH.can_sync_to(SecurityLevel.MEDIUM) == True

    def test_cannot_sync_lower_to_higher(self):
        from nexusagent.interface.adapter import SecurityLevel
        assert SecurityLevel.LOW.can_sync_to(SecurityLevel.HIGH) == False

    def test_minimum_sync(self):
        from nexusagent.interface.adapter import SecurityLevel
        assert SecurityLevel.CRITICAL.minimum_sync_level(SecurityLevel.PUBLIC) == True
        assert SecurityLevel.PUBLIC.minimum_sync_level(SecurityLevel.CRITICAL) == False


class TestConfigDefaults:
    """零配置 + 隐私默认"""

    def test_data_collection_off_by_default(self):
        from nexusagent.config.settings import get_config
        config = get_config()
        assert config.security.telemetry_enabled == False
        assert config.security.analytics_enabled == False
        assert config.security.crash_reporting == False
