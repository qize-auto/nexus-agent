"""
Cross-Department Report Demo / 跨部门报告生成示例

Demonstrates MiroFishScheduler auto-routing for complex collaborative tasks.
"""

import asyncio
import os

# Optional: load API key from env / 从环境变量加载 API 密钥
os.environ.setdefault("NEXUS_LLM_PROVIDER", "deepseek")


async def main():
    from nexusagent.main import NexusAgent

    agent = NexusAgent()
    await agent.initialize()

    task = (
        "Please generate a comprehensive cross-department collaboration report "
        "on the current AI agent market landscape, including research, analysis, "
        "and strategic recommendations."
    )

    print("=" * 60)
    print("Task / 任务:", task)
    print("=" * 60)

    result = await agent.process_message(
        user_id="demo_user",
        message=task,
        session_id="cross_dept_demo",
    )

    print("\nResult / 结果:\n")
    print(result)

    await agent.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
