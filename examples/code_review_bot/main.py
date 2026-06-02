"""
Code Review Bot Demo / 代码审查机器人示例

Demonstrates AntiCompressionDetector + CompletenessValidator on code outputs.
"""

import asyncio
import os

os.environ.setdefault("NEXUS_LLM_PROVIDER", "deepseek")


async def main():
    from nexusagent.main import NexusAgent

    agent = NexusAgent()
    await agent.initialize()

    task = (
        "Write a Python module with a Stack class including push, pop, peek, "
        "and is_empty methods. Include docstrings and a simple usage example."
    )

    print("=" * 60)
    print("Task / 任务:", task)
    print("=" * 60)

    result = await agent.process_message(
        user_id="code_review_demo",
        message=task,
        session_id="cr_demo",
    )

    print("\nGenerated Code / 生成代码:\n")
    print(result)

    # Demonstrate anti-laziness validation manually / 手动演示防偷懒验证
    from nexusagent.execution.anti_compression import AntiCompressionDetector
    from nexusagent.execution.completeness import CompletenessValidator
    from nexusagent.execution.tracker import ExecutionTracker

    ac = AntiCompressionDetector()
    cv = CompletenessValidator()
    tracker = ExecutionTracker()
    task_ctx = tracker.create_task("cr_demo", task)

    ac_summary = ac.get_summary(result)
    comp_summary = cv.get_summary(task_ctx, result)

    print("\n" + "=" * 60)
    print("Anti-Laziness Report / 防偷懒报告:")
    print(f"  Compressed? / 压缩偷懒? : {ac_summary['is_compressed']}")
    print(f"  Complete?   / 完整?     : {comp_summary['is_complete']}")
    if not comp_summary['is_complete']:
        print(f"  Issues      / 问题      : {comp_summary['issues_by_type']}")
    print("=" * 60)

    await agent.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
