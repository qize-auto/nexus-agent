# Example: Cross-Department Report Generation / 跨部门报告生成

This example demonstrates **MiroFish multi-strategy auto-orchestration**.

本示例展示 **MiroFish 多策略自动编排**。

## Scenario / 场景

A user asks for a comprehensive market analysis report that requires:
- Research (信息检索)
- Analysis (数据分析)
- Writing (报告撰写)
- Review (质量审查)

NexusAgent automatically detects this as a **complex task** and routes it
to `MiroFishScheduler`, which simulates cross-department collaboration.

## Run / 运行

```bash
pip install -r requirements.txt
python main.py
```

## Expected Output / 预期输出

You should see log messages indicating strategy selection (`[MiroFish]`)
and evidence recording from multiple simulated agents.
