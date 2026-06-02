# Example: Code Review Bot / 代码审查机器人

This example demonstrates the **anti-laziness execution guards**.

本示例展示 **防偷懒执行保障**。

## Scenario / 场景

A code review bot that checks for:
- Output truncation (`...`, `[omitted]`, etc.)
- Skipped implementation steps
- Incomplete file generation
- Missing tests or documentation

NexusAgent's `AntiCompressionDetector` and `CompletenessValidator` catch
these patterns automatically.

## Run / 运行

```bash
pip install -r requirements.txt
python main.py
```
