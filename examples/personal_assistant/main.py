"""
Personal Assistant with Profiling Demo / 带画像的个人助理示例

Demonstrates HybridMemory + UserProfileManager + DreamEngine integration.
"""

import asyncio
import os

os.environ.setdefault("NEXUS_LLM_PROVIDER", "deepseek")


async def main():
    from nexusagent.main import NexusAgent

    agent = NexusAgent()
    await agent.initialize()

    user_id = "pa_demo_user"
    session_id = "pa_demo_session"

    # Simulate a multi-turn conversation / 模拟多轮对话
    messages = [
        "Hi, I prefer concise technical answers.",
        "What are the main differences between asyncio and threading in Python?",
        "Summarize my preference so far.",
    ]

    for msg in messages:
        print(f"\nUser / 用户: {msg}")
        result = await agent.process_message(
            user_id=user_id,
            message=msg,
            session_id=session_id,
        )
        print(f"Agent / 助手: {result[:300]}...")

    # Manually trigger a dream cycle / 手动触发梦境周期
    if agent._dream:
        print("\n[DreamEngine] Running consolidation cycle...")
        report = await agent._dream.dream_cycle(user_id)
        print(
            f"[DreamEngine] Merged: {report.traits_merged}, "
            f"Rejected: {report.traits_rejected}, "
            f"Staled: {report.traits_staled}"
        )

    await agent.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
