"""
NexusAgent v4.0+ — MiroFish 端到端演示脚本 [MIROFISH-INSPIRED]

演示场景：跨部门报告生成
    市场部提供数据 → 分析师深度分析 → 写手撰写报告 → 审查员质量检查

来源: GitHub 666ghj/MiroFish (https://github.com/666ghj/MiroFish)
      — 基于 OASIS 框架的多智能体社会模拟引擎

运行:
    cd /c/Users/qize/Desktop/nexusagent
    python examples/mirofish_demo.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from nexusagent.orchestration.mirofish import (
    MiroFishScheduler,
    PersonaEngine,
    SocialGraph,
    SimulationClock,
)


async def demo_cross_department_report():
    """
    演示：跨部门报告生成 — 超长复杂任务

    任务: "基于 Q3 销售数据，分析市场趋势并生成一份面向高管的
          跨部门战略报告，包含数据可视化建议"
    """
    print("=" * 60)
    print("  MiroFish 端到端演示：跨部门报告生成")
    print("=" * 60)
    print()

    # Step 1: 初始化 MiroFish 调度器
    scheduler = MiroFishScheduler()

    # Step 2: 注册 Specialist Agents（带自定义人设）
    print("[Step 1] 注册 Specialist Agents...")
    scheduler.register_agent(
        "market_data",
        "researcher",
        "市场部-小李",
        custom_traits={
            "mbti": "ESTJ",
            "profession": "市场数据专员",
            "bio": "负责收集和整理市场数据，对数字极其敏感",
            "proactivity": 0.9,
            "detail_orientation": 0.8,
        },
        handler=lambda task, persona: f"[{persona.name}] 已收集 Q3 销售数据：销售额 1.2亿，同比增长 15%",
    )
    scheduler.register_agent(
        "analyst",
        "analyst",
        "分析师-老王",
        custom_traits={
            "mbti": "INTJ",
            "profession": "高级数据分析师",
            "bio": "擅长从数据中发现趋势和异常，有 10 年行业经验",
            "proactivity": 0.7,
            "detail_orientation": 0.95,
            "risk_tolerance": 0.3,
        },
        handler=lambda task, persona: f"[{persona.name}] 分析完成：核心趋势是下沉市场增长 32%，建议关注二三线城市",
    )
    scheduler.register_agent(
        "writer",
        "writer",
        "写手-阿文",
        custom_traits={
            "mbti": "ENFP",
            "profession": "战略报告撰写专家",
            "bio": "善于将复杂数据转化为高管易懂的叙事",
            "proactivity": 0.85,
            "detail_orientation": 0.5,
            "risk_tolerance": 0.6,
        },
        handler=lambda task, persona: f"[{persona.name}] 报告撰写完成：包含执行摘要、数据洞察、战略建议三章",
    )
    scheduler.register_agent(
        "critic",
        "critic",
        "审查员-严总",
        custom_traits={
            "mbti": "ISTJ",
            "profession": "质量审查总监",
            "bio": "对报告质量要求极高，擅长发现逻辑漏洞和数据不一致",
            "proactivity": 0.5,
            "detail_orientation": 0.9,
            "risk_tolerance": 0.2,
            "argumentativeness": 0.7,
        },
        handler=lambda task, persona: f"[{persona.name}] 审查通过：数据一致，逻辑清晰，建议补充风险评估",
    )

    # Step 3: 手动建立跨部门协作关系
    print("[Step 2] 构建社会协作图谱...")
    scheduler.add_relation("market_data", "analyst", "collaborates_with", 0.9)
    scheduler.add_relation("analyst", "writer", "collaborates_with", 0.85)
    scheduler.add_relation("writer", "critic", "reports_to", 0.8)
    scheduler.add_relation("critic", "analyst", "influences", 0.6)

    graph_stats = scheduler._social_graph.stats()
    print(f"  - Agent 数量: {graph_stats['node_count']}")
    print(f"  - 关系边数: {graph_stats['edge_count']}")
    print()

    # Step 4: 执行 MiroFish 协作预演
    print("[Step 3] 启动 MiroFish 协作预演模拟...")
    task = "基于 Q3 销售数据，分析市场趋势并生成一份面向高管的跨部门战略报告，包含数据可视化建议"
    result = await scheduler.run(task, max_rounds=5)
    print()

    # Step 5: 输出结果
    print("[Step 4] 模拟结果")
    print("-" * 60)
    print(result.output)
    print()

    # Step 6: 统计
    stats = scheduler.get_stats()
    print("[Step 5] 协作统计")
    print("-" * 60)
    print(f"Agent 总数: {stats['agents']}")
    print(f"任务分解数: {stats['tasks']}")
    print(f"完成任务数: {stats['completed']}")
    print(f"模拟轮次: {stats['rounds']}")
    print(f"共识便签数: {stats['consensus_notes']}")
    print(f"执行时间: {result.execution_time:.2f}s")
    print()

    # Step 7: 每个 Agent 的详细人设
    print("[Step 6] Agent 深度人设")
    print("-" * 60)
    for agent_id, persona in scheduler._agents.items():
        print(f"\n  {persona.name} ({persona.role})")
        print(f"     MBTI: {persona.mbti} | 年龄: {persona.age} | 国家: {persona.country}")
        print(f"     主动性: {persona.proactivity:.1f} | 细节导向: {persona.detail_orientation:.1f} | 风险承受: {persona.risk_tolerance:.1f}")
        print(f"     影响力: {persona.influence_weight:.1f} | 友好度: {persona.friendliness:.1f}")
        print(f"     Bio: {persona.bio}")

    print()
    print("=" * 60)
    print("  MiroFish 演示完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(demo_cross_department_report())
