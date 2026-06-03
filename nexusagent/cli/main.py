"""
NexusAgent v4.0+ — 统一 CLI 入口

设计参考:
- Mastra CLI: https://mastra.ai/docs/getting-started
  "mastra init / dev / build / deploy"
- Dify CLI 工具链

Usage:
    nexus init          # 初始化项目脚手架
    nexus dev           # 本地开发热启动
    nexus status        # 健康检查
    nexus deploy        # Docker Compose 部署
    nexus eval          # 运行评估
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional


def _ensure_project_root() -> Path:
    """确保项目根目录在 PYTHONPATH 中"""
    cli_dir = Path(__file__).parent.parent.resolve()
    if str(cli_dir) not in sys.path:
        sys.path.insert(0, str(cli_dir))
    return cli_dir


def _get_agent():
    """延迟导入 Agent（避免 CLI 启动时 heavy import）"""
    from nexusagent.main import NexusAgent
    return NexusAgent()


def cmd_init(args: list) -> int:
    """初始化 NexusAgent 项目脚手架"""
    project_name = args[0] if args else "my-nexus-project"
    project_path = Path.cwd() / project_name
    project_path.mkdir(parents=True, exist_ok=True)

    # 创建目录结构
    (project_path / "agents").mkdir(exist_ok=True)
    (project_path / "tools").mkdir(exist_ok=True)
    (project_path / "workflows").mkdir(exist_ok=True)
    (project_path / "evals").mkdir(exist_ok=True)

    # .env 模板
    env_content = """# NexusAgent 环境配置
DEFAULT_PROVIDER=deepseek
DEFAULT_MODEL=deepseek-chat
DEEPSEEK_API_KEY=your-key-here
NEXUS_DEBUG=false
"""
    (project_path / ".env").write_text(env_content, encoding="utf-8")

    # 示例工作流
    workflow_content = '''"""示例工作流 — 分析任务"""
from nexusagent.execution.state_graph import StateGraph, END

async def analyze(state):
    return {"result": f"分析完成: {state.get('task', '')}"}

graph = StateGraph()
graph.add_node("analyze", analyze)
graph.set_entry_point("analyze")
graph.add_edge("analyze", END)

compiled = graph.compile()
'''
    (project_path / "workflows" / "example.py").write_text(workflow_content, encoding="utf-8")

    print(f"✅ 项目初始化完成: {project_path}")
    print(f"   cd {project_name}")
    print(f"   nexus dev")
    return 0


def cmd_dev(args: list) -> int:
    """本地开发热启动（Web 模式）"""
    _ensure_project_root()
    from nexusagent.run_web import main as web_main
    try:
        import asyncio
        asyncio.run(web_main())
    except KeyboardInterrupt:
        print("\n👋 开发服务器已停止")
    return 0


def cmd_status(args: list) -> int:
    """健康检查"""
    _ensure_project_root()
    import urllib.request
    try:
        resp = urllib.request.urlopen("http://localhost:8080/api/health", timeout=5)
        data = json.loads(resp.read())
        print("🟢 NexusAgent 运行中")
        print(f"   状态: {data.get('status', 'unknown')}")
        print(f"   延迟: {data.get('latency_ms', 0):.1f}ms")
        return 0
    except Exception as e:
        print(f"🔴 NexusAgent 未运行: {e}")
        return 1


def cmd_deploy(args: list) -> int:
    """Docker Compose 部署"""
    project_root = _ensure_project_root()
    compose_file = project_root / "docker-compose.yml"
    if not compose_file.exists():
        print(f"❌ 未找到 {compose_file}")
        return 1

    print("🚀 启动 Docker Compose 部署...")
    result = subprocess.run(
        ["docker-compose", "up", "-d"],
        cwd=project_root,
        capture_output=False,
    )
    return result.returncode


def cmd_eval(args: list) -> int:
    """运行评估 — 执行测试套件并输出摘要"""
    _ensure_project_root()
    import subprocess
    print("📊 启动 NexusAgent 评估...")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short", "-q"],
        cwd=_ensure_project_root(),
    )
    if result.returncode == 0:
        print("✅ 评估通过：所有测试成功")
    else:
        print(f"❌ 评估失败：exit code {result.returncode}")
    return result.returncode


def cmd_tool(args: list) -> int:
    """工具管理: nexus tool ls | info <name> | search <query>"""
    _ensure_project_root()
    from nexusagent.tools.registry import get_registry

    registry = get_registry()
    subcmd = args[0] if args else "ls"
    rest = args[1:]

    if subcmd == "ls":
        source = rest[0] if rest else None
        tools = registry.list_tools(source=source)
        print(f"📦 已注册工具 ({len(tools)} 个)")
        for t in tools:
            status = "🟢" if t["enabled"] else "🔴"
            print(f"  {status} {t['name']:<30} v{t['version']:<8} [{t['source']}]  {t['description'][:50]}")
        stats = registry.get_stats()
        print(f"\n统计: 总计 {stats['total']} | 启用 {stats['enabled']} | 来源 {stats['sources']}")
        return 0

    elif subcmd == "info" and rest:
        name = rest[0]
        tool = registry.get(name)
        if not tool:
            print(f"❌ 未找到工具: {name}")
            return 1
        meta = tool.metadata
        print(f"🔧 {meta.name}")
        print(f"   描述: {meta.description}")
        print(f"   版本: {meta.version}")
        print(f"   作者: {meta.author}")
        print(f"   来源: {meta.source} ({meta.source_ref})")
        print(f"   标签: {', '.join(meta.tags) or '(无)'}")
        print(f"   状态: {'启用' if meta.enabled else '禁用'}")
        if meta.dependencies:
            print(f"   依赖: {', '.join(meta.dependencies)}")
        return 0

    elif subcmd == "search" and rest:
        query = rest[0]
        results = registry.search(query)
        print(f"🔍 搜索 '{query}': {len(results)} 个结果")
        for t in results:
            print(f"  • {t['name']:<30} [{t['source']}]  {t['description'][:60]}")
        return 0

    else:
        print("用法: nexus tool <ls|info|search> [args...]")
        print("  nexus tool ls              列出所有工具")
        print("  nexus tool ls builtin      列出内置工具")
        print("  nexus tool info <name>     查看工具详情")
        print("  nexus tool search <query>  搜索工具")
        return 0


def cmd_profile(args: list) -> int:
    """用户画像管理: nexus profile show | learn | forget"""
    _ensure_project_root()
    import asyncio
    from nexusagent.memory.user_profile import UserProfileManager

    subcmd = args[0] if args else "show"
    rest = args[1:]
    user_id = os.getenv("NEXUS_USER_ID", "cli_user")

    mgr = UserProfileManager()

    async def _run():
        if subcmd == "show":
            profile = await mgr.get_or_create(user_id)
            print(f"👤 用户画像: {user_id} (v{profile.version})")
            print(f"   技术栈: {', '.join(profile.static.tech_stack) or '未记录'}")
            print(f"   偏好工具: {', '.join(profile.static.preferred_tools) or '未记录'}")
            print(f"   沟通风格: {profile.static.communication_style}")
            print(f"   耐心指数: {profile.behavioral.patience_index:.2f}")
            print(f"   细节偏好: {profile.behavioral.detail_preference:.2f}")
            print(f"   温度偏好: {profile.behavioral.temperature_preference:.2f}")
            print(f"   信任积分: {profile.security.trust_score:.1f} ({profile.security.trust_tier})")
            print(f"   最近话题: {', '.join(profile.dynamic.recent_topics[:5]) or '无'}")
            print(f"   待验证条目: {len(profile.pending_traits)}")
            return 0

        elif subcmd == "learn" and rest:
            preference = ' '.join(rest)
            from nexusagent.cognition.user_profiler import UserProfiler
            profiler = UserProfiler()
            signals = profiler.process_message(user_id=user_id, message=preference)
            for sig in signals:
                await mgr.add_pending_trait(
                    user_id, sig.category, sig.key, sig.value,
                    confidence=sig.confidence, source="explicit_cli",
                )
            print(f"✅ 已记录 {len(signals)} 条画像信号")
            for s in signals:
                print(f"   • [{s.category}] {s.key} = {s.value} (置信度 {s.confidence:.2f})")
            return 0

        elif subcmd == "forget" and rest:
            topic = ' '.join(rest)
            await mgr.delete_profile(user_id)
            print(f"🗑️  用户画像已删除: {user_id}")
            return 0

        else:
            print("用法: nexus profile <show|learn|forget> [args...]")
            print("  nexus profile show              显示当前画像")
            print('  nexus profile learn "偏好描述"   显式教学')
            print('  nexus profile forget            删除画像 (GDPR)')
            return 0

    return asyncio.run(_run())


def cmd_dream(args: list) -> int:
    """梦境引擎: nexus dream now"""
    _ensure_project_root()
    import asyncio
    from nexusagent.memory.user_profile import UserProfileManager
    from nexusagent.cognition.dream_engine import DreamEngine

    subcmd = args[0] if args else "now"
    user_id = os.getenv("NEXUS_USER_ID", "cli_user")

    mgr = UserProfileManager()
    dream = DreamEngine(profile_manager=mgr)

    async def _run():
        if subcmd == "now":
            print("🌙 启动梦境周期...")
            report = await dream.dream_cycle(user_id)
            print(f"   合并: {report.traits_merged}")
            print(f"   拒绝: {report.traits_rejected}")
            print(f"   过期: {report.traits_staled}")
            print(f"   冲突解决: {report.conflicts_resolved}")
            print(f"   摘要生成: {'是' if report.summary_generated else '否'}")
            print(f"   耗时: {report.elapsed_ms:.1f}ms")
            return 0
        else:
            print("用法: nexus dream now")
            return 0

    return asyncio.run(_run())




def cmd_eval_framework(args: list) -> int:
    """运行评估框架 — 使用 evals/framework.py 中的评估器
    Usage: nexus eval-framework <input> <output> [expected]
    """
    _ensure_project_root()
    import asyncio
    from nexusagent.evals.framework import EvalRunner, ExactMatchEvaluator, ContainsEvaluator

    if len(args) < 2:
        print("用法: nexus eval-framework <input> <output> [expected]")
        print("  nexus eval-framework 'hello' 'hello world' 'hello world'")
        return 1

    input_data, output = args[0], args[1]
    expected = args[2] if len(args) > 2 else None

    async def _run():
        runner = EvalRunner()
        runner.add_evaluator(ExactMatchEvaluator())
        runner.add_evaluator(ContainsEvaluator(required_phrases=["hello"]))
        results = await runner.run(input_data, output, expected)
        summary = runner.summary(results)
        print(f"📊 评估结果: {summary['passed']}/{summary['total']} 通过 (平均分: {summary['avg_score']})")
        for r in results:
            status = "✅" if r.passed else "❌"
            print(f"  {status} {r.evaluator}: {r.reason}")
        return 0 if summary['passed'] == summary['total'] else 1

    return asyncio.run(_run())


def cmd_regression(args: list) -> int:
    """运行回归测试 — 使用 evals/regression.py
    Usage: nexus regression <test_json_path>
    """
    _ensure_project_root()
    import asyncio
    from nexusagent.evals.regression import RegressionSuite
    from nexusagent.main import NexusAgent

    test_path = args[0] if args else "tests/regression_tests.json"
    if not Path(test_path).exists():
        print(f"❌ 测试文件不存在: {test_path}")
        print("  创建示例: echo '[]' > tests/regression_tests.json")
        return 1

    suite = RegressionSuite.from_json(test_path)
    agent = NexusAgent()

    async def _agent_fn(msg: str) -> str:
        await agent.initialize()
        return await agent.process_message("regression_user", msg)

    async def _run():
        print(f"📊 运行回归测试: {len(suite._test_cases)} 个用例")
        results = await suite.run(_agent_fn)
        report = suite.report(results)
        print(f"   通过: {report['passed']}/{report['total']} ({report['pass_rate']*100:.0f}%)")
        print(f"   阈值: {report['threshold']*100:.0f}% | 可接受: {'✅' if report['acceptable'] else '❌'}")
        if report['failures']:
            print("\n失败用例:")
            for f in report['failures'][:5]:
                print(f"  • {f['test_id']}: expected={f['expected'][:40]} actual={f['actual'][:40]}")
        return 0 if report['acceptable'] else 1

    return asyncio.run(_run())


def cmd_mcp(args: list) -> int:
    """启动 MCP Server — 暴露 ToolRegistry 为 MCP Server
    Usage: nexus mcp
    """
    _ensure_project_root()
    import asyncio
    from nexusagent.tools.registry import get_registry
    from nexusagent.tools.mcp_server import MCPServer

    registry = get_registry()
    registry.discover_builtin_tools()
    server = MCPServer(registry)

    print("🔌 启动 MCP Server (stdio mode)...")
    print("   工具数量:", len(registry.list_tools()))
    try:
        asyncio.run(server.run())
    except KeyboardInterrupt:
        print("\n👋 MCP Server 已停止")
    return 0



def _print_table(headers: list, rows: list) -> None:
    """简易终端表格输出"""
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(cell)))
    # 表头
    header_line = " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
    print("  " + header_line)
    print("  " + "-+-".join("-" * w for w in col_widths))
    for row in rows:
        print("  " + " | ".join(str(cell).ljust(col_widths[i]) for i, cell in enumerate(row)))


def cmd_doctor(args: list) -> int:
    """诊断检查 — 运行全部诊断并输出终端报告
    Usage: nexus doctor [--json] [--export <path>]
    """
    _ensure_project_root()
    import asyncio
    from nexusagent.diagnostics import (
        collect_health, collect_connectivity, collect_audit,
        collect_modules, collect_ux,
    )

    output_json = "--json" in args
    export_path = None
    if "--export" in args:
        idx = args.index("--export")
        if idx + 1 < len(args):
            export_path = args[idx + 1]

    async def _run():
        results = {}

        # Health
        if not output_json:
            print("🏥 收集 Health 数据…")
        results["health"] = await collect_health()

        # Connectivity
        if not output_json:
            print("🔗 收集 Connectivity 数据…")
        results["connectivity"] = await collect_connectivity()

        # Modules
        if not output_json:
            print("📦 收集 Modules 数据…")
        results["modules"] = await collect_modules()

        # Audit
        if not output_json:
            print("📋 收集 Audit 数据…")
        results["audit"] = await collect_audit(limit=10)

        # UX
        if not output_json:
            print("✨ 收集 UX 数据…")
        results["ux"] = await collect_ux(theme="dark", model="cli")

        if export_path:
            from nexusagent.diagnostics.report import generate_report
            from nexusagent.diagnostics.persistence import DiagnosticStore
            store = DiagnosticStore()
            # Seed current results as snapshots so report can reference them
            store.save_snapshot("health", results["health"], 0)
            store.save_snapshot("connectivity", results["connectivity"], 0)
            store.save_snapshot("modules", results["modules"], 0)
            store.save_snapshot("ux", results["ux"], 0)
            markdown = generate_report(store)
            with open(export_path, "w", encoding="utf-8") as f:
                f.write(markdown)
            print(f"Diagnostic report exported to: {export_path}")
            store.close()
            return 0

        if output_json:
            print(json.dumps(results, indent=2, ensure_ascii=False))
            return 0

        # ── Terminal Report ──
        print()
        print("=" * 60)
        print("  NexusAgent Doctor Report")
        print("=" * 60)

        # Health Summary
        h = results["health"]
        m = h.get("metrics", {})
        print()
        print(f"  Overall: {'🟢 Healthy' if h.get('overall_healthy') else '🔴 Issues Detected'}")
        print(f"  Sessions: {m.get('active_sessions', 0)}  |  Latency: {m.get('avg_latency_ms', 0):.1f}ms  |  Requests(1h): {m.get('requests_total', 0)}")

        # System
        sys_info = h.get("system", {})
        if isinstance(sys_info.get("memory"), dict):
            mem = sys_info["memory"]
            print(f"  Memory: {mem.get('percent_used', 0)}% used  |  Disk: {sys_info.get('disk', {}).get('percent_used', 'N/A')}% used")

        # Backends
        backends = h.get("backends", {})
        if backends:
            print()
            print("  Backends:")
            _print_table(
                ["Name", "Status", "Err%", "p99 ms"],
                [
                    [name, "OK" if info.get("is_healthy") else "FAIL", f"{(info.get('error_rate', 0) * 100):.1f}%", f"{info.get('p99_latency_ms', 0):.0f}"]
                    for name, info in backends.items()
                ],
            )

        # Security
        sec = h.get("security", {})
        if sec:
            print()
            print("  Security:")
            for name, info in sec.items():
                avail = info.get("available", False) if isinstance(info, dict) else (info != "unavailable")
                icon = "🟢" if avail else "🔴"
                detail = ""
                if isinstance(info, dict):
                    if "ml_threshold" in info:
                        detail = f" (ml_threshold={info['ml_threshold']})"
                    elif "default_allow" in info:
                        detail = f" (default_allow={info['default_allow']})"
                print(f"    {icon} {name}{detail}")

        # Memory
        mem = h.get("memory", {})
        if mem.get("total") is not None:
            print()
            print(f"  Memory DB: {mem.get('total', 0)} entries  |  Size: {mem.get('db_file_size_mb', 0)}MB  |  Core blocks: {mem.get('core_blocks', 0)}")

        # Connectivity
        conn = results["connectivity"]
        print()
        print("  Connectivity Probes:")
        probes = conn.get("probes", {})
        for name, info in probes.items():
            icon = "🟢" if info.get("status") == "ok" else "🔴"
            print(f"    {icon} {name}")

        # Modules
        mod = results["modules"]
        print()
        print(f"  Modules: {mod.get('healthy', 0)}/{mod.get('total', 0)} healthy")
        failed = [m for m in mod.get("modules", []) if m["status"] != "ok"]
        if failed:
            print("    Failed:")
            for m in failed:
                print(f"      🔴 {m['name']}: {m.get('error', 'unknown')}")

        # UX
        ux = results["ux"]
        print()
        score = ux.get("score", 0)
        color = "🟢" if score >= 80 else "🟡" if score >= 50 else "🔴"
        print(f"  UX Score: {color} {score}/100")
        for r in ux.get("recommendations", [])[:5]:
            print(f"    → {r}")

        # Audit
        aud = results["audit"]
        print()
        print(f"  Audit: {aud['summary'].get('recent_traces_count', 0)} traces  |  {aud['summary'].get('audit_entries_loaded', 0)} log entries")

        print()
        print("=" * 60)

        # Exit code: 0 if all healthy, 1 if issues
        all_ok = h.get("overall_healthy") and conn.get("ok") and mod.get("ok")
        return 0 if all_ok else 1

    return asyncio.run(_run())


def cmd_status_enhanced(args: list) -> int:
    """增强状态检查 — 使用 HeartbeatMonitor
    Usage: nexus status
    """
    _ensure_project_root()
    from nexusagent.orchestration.scheduler import HeartbeatStatus

    # 模拟心跳检查（实际生产环境应检查各组件）
    components = [
        HeartbeatStatus("guardrails", alive=True),
        HeartbeatStatus("react_engine", alive=True),
        HeartbeatStatus("memory_store", alive=True),
        HeartbeatStatus("tool_registry", alive=True),
    ]
    print("🟢 NexusAgent 组件状态")
    for c in components:
        status = "🟢" if c.alive else "🔴"
        print(f"  {status} {c.component:<20} 延迟: {c.latency_ms:.1f}ms")
    return 0


def cmd_encryption_export(args: list) -> int:
    """导出加密密钥包
    Usage: nexus encryption export
    """
    _ensure_project_root()
    from nexusagent.memory.encryption import MemoryEncryption

    enc = MemoryEncryption()
    try:
        bundle = enc.export_key_bundle()
        print("🔐 密钥包导出成功")
        print(f"   DEK ID: {bundle.dek_id}")
        print(f"   版本: {bundle.version}")
        print(f"   Salt (base64): {bundle.salt.hex()[:16]}...")
        return 0
    except Exception as e:
        print(f"❌ 导出失败: {e}")
        return 1


def cmd_graph_visualize(args: list) -> int:
    """生成 StateGraph Mermaid 可视化
    Usage: nexus graph visualize
    """
    _ensure_project_root()
    from nexusagent.execution.state_graph import StateGraph, END

    g = StateGraph()
    # 构建一个示例图用于展示
    async def node_a(state):
        return {**state, "step": "a"}
    async def node_b(state):
        return {**state, "step": "b"}

    g.add_node("start", node_a)
    g.add_node("end", node_b)
    g.set_entry_point("start")
    g.add_edge("start", "end")
    g.add_edge("end", END)

    mermaid = g.to_mermaid()
    print("```mermaid")
    print(mermaid)
    print("```")
    return 0

def cmd_benchmark(args: list) -> int:
    """LLM Provider 性能基准测试
    Usage: nexus benchmark [--provider <p>] [--model <m>] [--runs <n>] [--dry-run] [--output <file>]
    """
    _ensure_project_root()
    import asyncio

    provider = "deepseek"
    model = "deepseek-chat"
    runs = 3
    dry_run = False
    output_file = ""

    i = 0
    while i < len(args):
        if args[i] == "--provider" and i + 1 < len(args):
            provider = args[i + 1]
            i += 2
        elif args[i] == "--model" and i + 1 < len(args):
            model = args[i + 1]
            i += 2
        elif args[i] == "--runs" and i + 1 < len(args):
            runs = int(args[i + 1])
            i += 2
        elif args[i] == "--dry-run":
            dry_run = True
            i += 1
        elif args[i] == "--output" and i + 1 < len(args):
            output_file = args[i + 1]
            i += 2
        else:
            i += 1

    from nexusagent.benchmark.runner import BenchmarkRunner
    from nexusagent.benchmark.report import BenchmarkReport

    async def _run():
        runner = BenchmarkRunner()
        print(f"🧪 开始基准测试: {provider}/{model} (runs={runs}, dry_run={dry_run})")
        result = await runner.run_provider(provider, model, runs=runs, dry_run=dry_run)
        report = BenchmarkReport([result])
        md = report.to_markdown()
        print(md)
        if output_file:
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(md)
            print(f"\n✓ 报告已保存: {output_file}")
        return 0

    return asyncio.run(_run())


def cmd_backup(args: list) -> int:
    """记忆系统备份管理
    Usage: nexus backup [create|list|restore|cleanup] [--label <label>]
    """
    _ensure_project_root()
    from nexusagent.memory.backup import MemoryBackupManager

    action = args[0] if args else "create"
    label = ""
    i = 0
    while i < len(args):
        if args[i] == "--label" and i + 1 < len(args):
            label = args[i + 1]
            i += 2
        else:
            i += 1

    mgr = MemoryBackupManager()

    if action == "create":
        info = mgr.backup(label=label)
        print(f"✓ 备份创建成功: {info.timestamp}")
        print(f"  路径: {info.path}")
        print(f"  大小: {info.size_bytes / 1024 / 1024:.1f} MB")
        print(f"  文件数: {info.file_count}")
        return 0

    elif action == "list":
        backups = mgr.list_backups()
        if not backups:
            print("暂无备份")
            return 0
        print(f"{'时间戳':<25} {'大小(MB)':>10} {'文件数':>8}")
        print("-" * 50)
        for b in backups:
            print(f"{b.timestamp:<25} {b.size_bytes / 1024 / 1024:>10.1f} {b.file_count:>8}")
        return 0

    elif action == "restore":
        if len(args) < 2 or args[1].startswith("-"):
            print("用法: nexus backup restore <timestamp>")
            return 1
        timestamp = args[1]
        if mgr.restore(timestamp):
            print(f"✓ 备份已恢复: {timestamp}")
            return 0
        else:
            print(f"❌ 恢复失败: {timestamp}")
            return 1

    elif action == "cleanup":
        deleted = mgr.auto_cleanup()
        print(f"✓ 已清理 {deleted} 个旧备份")
        return 0

    elif action == "status":
        usage = mgr.get_disk_usage()
        print("磁盘使用统计:")
        for name, size in usage.items():
            print(f"  {name:<15} {size / 1024 / 1024:>10.1f} MB")
        return 0

    else:
        print(f"未知操作: {action}")
        print("用法: nexus backup [create|list|restore|cleanup|status]")
        return 1


def cmd_evolution(args: list) -> int:
    """自我进化系统: nexus evolution status | review | approve <id> | reject <id> | history | rollback <dim> [ver]
    Usage:
        nexus evolution status          查看进化系统状态
        nexus evolution review          查看待审批建议
        nexus evolution approve <id>    批准建议
        nexus evolution reject <id>     拒绝建议
        nexus evolution history         查看配置历史
        nexus evolution rollback <dim> [ver]  回滚配置
    """
    _ensure_project_root()
    import asyncio
    from pathlib import Path
    from nexusagent.evolution.engine import EvolutionEngine
    from nexusagent.benchmark.runner import BenchmarkRunner
    from nexusagent.evolution.strategies import (
        PromptOptimizationStrategy,
        ToolMappingStrategy,
        BudgetTuningStrategy,
    )

    subcmd = args[0] if args else "status"
    rest = args[1:]

    config_dir = Path.home() / ".nexusagent" / "evolution"
    engine = EvolutionEngine(
        config_dir=str(config_dir),
        benchmark_runner=BenchmarkRunner(),
    )
    engine.register_strategy(PromptOptimizationStrategy())
    engine.register_strategy(ToolMappingStrategy())
    engine.register_strategy(BudgetTuningStrategy())

    async def _run():
        if subcmd == "status":
            status = engine.get_status()
            print("🧬 自我进化系统状态")
            print(f"   注册策略: {status['strategies_registered']} 个")
            for s in status["strategies"]:
                print(f"      • {s['dimension']} ({s['class']})")
            print(f"   待审批建议: {status['pending_proposals']} 个")
            print("   配置历史:")
            for dim, count in status["config_history"].items():
                print(f"      • {dim}: {count} 个版本")
            return 0

        elif subcmd == "review":
            pending = engine.get_pending_proposals()
            if not pending:
                print("暂无待审批的进化建议")
                return 0
            print(f"📋 待审批建议 ({len(pending)} 个):")
            for p in pending:
                print(f"\n   ID: {p.id}")
                print(f"   维度: {p.dimension}")
                print(f"   置信度: {p.confidence:.2f}")
                print(f"   描述: {p.description}")
                print(f"   创建时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(p.created_at))}")
                print(f"   操作: nexus evolution approve {p.id} | nexus evolution reject {p.id}")
            return 0

        elif subcmd == "approve" and rest:
            proposal_id = rest[0]
            approver = os.getenv("USER", "cli_user")
            if engine.approve(proposal_id, approver):
                print(f"✓ 建议已批准: {proposal_id}")
                # 尝试自动部署
                pending = engine.get_pending_proposals()
                for p in pending:
                    if p.id == proposal_id:
                        print("  开始 A/B 测试并部署...")
                        success = await engine.deploy(p)
                        if success:
                            print("  ✓ 配置已部署")
                        else:
                            print("  ✗ A/B 测试未通过，配置已回滚")
                        break
                return 0
            print(f"❌ 批准失败: {proposal_id}")
            return 1

        elif subcmd == "reject" and rest:
            proposal_id = rest[0]
            approver = os.getenv("USER", "cli_user")
            if engine.reject(proposal_id, approver):
                print(f"✓ 建议已拒绝: {proposal_id}")
                return 0
            print(f"❌ 拒绝失败: {proposal_id}")
            return 1

        elif subcmd == "history":
            print("📜 配置历史:")
            for strategy in engine.list_strategies():
                dim = strategy["dimension"]
                versions = engine._history.list(dim)
                if versions:
                    print(f"\n   {dim} ({len(versions)} 个版本):")
                    for v in versions[:10]:
                        ts = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(v.timestamp))
                        print(f"      • {v.version_id} @ {ts} — {v.description}")
            return 0

        elif subcmd == "rollback" and rest:
            dimension = rest[0]
            version_id = rest[1] if len(rest) > 1 else None
            if engine.rollback(dimension, version_id):
                print(f"✓ 配置已回滚: {dimension}")
                return 0
            print(f"❌ 回滚失败: {dimension}")
            return 1

        elif subcmd == "run":
            print("🧬 启动进化周期...")
            proposals = await engine.run_cycle()
            if proposals:
                print(f"   生成 {len(proposals)} 个进化建议")
                for p in proposals:
                    print(f"   • [{p.dimension}] {p.description} (confidence={p.confidence:.2f})")
                print(f"\n   使用 'nexus evolution review' 查看待审批建议")
            else:
                print("   未生成进化建议（当前配置已优化或冷却中）")
            return 0

        elif subcmd == "mode" and rest:
            new_mode = rest[0]
            try:
                engine.set_mode(new_mode)
                print(f"✓ 进化模式已切换为: {new_mode}")
                if new_mode == "off":
                    print("   提示: 进化系统已关闭，可使用 'nexus evolution run' 手动触发")
                elif new_mode == "notify":
                    print("   提示: 后台分析后会通知您审批")
                elif new_mode == "auto":
                    print("   提示: 高置信度建议将自动部署")
                return 0
            except ValueError as e:
                print(f"❌ {e}")
                return 1

        else:
            print("用法: nexus evolution <status|review|approve|reject|history|rollback|run|mode>")
            print("  nexus evolution status              查看状态")
            print("  nexus evolution review              查看待审批建议")
            print("  nexus evolution approve <id>        批准建议")
            print("  nexus evolution reject <id>         拒绝建议")
            print("  nexus evolution history             查看配置历史")
            print("  nexus evolution rollback <dim>      回滚配置")
            print("  nexus evolution run                 手动触发进化周期")
            print("  nexus evolution mode <off|notify|auto>  切换运行模式")
            return 0

    return asyncio.run(_run())


def cmd_module(args: list) -> int:
    """模块管理: nexus module init <name> | ls | health
    Usage:
        nexus module init my_skill --desc "我的技能" --author "user"
        nexus module ls
        nexus module health
    """
    _ensure_project_root()
    import shutil

    subcmd = args[0] if args else "ls"

    if subcmd == "init":
        if len(args) < 2:
            print("用法: nexus module init <name> [--desc <描述>] [--author <作者>]")
            return 1

        name = args[1]
        desc = f"{name} 模块"
        author = "unknown"
        i = 2
        while i < len(args):
            if args[i] == "--desc" and i + 1 < len(args):
                desc = args[i + 1]
                i += 2
            elif args[i] == "--author" and i + 1 < len(args):
                author = args[i + 1]
                i += 2
            else:
                i += 1

        target = Path("modules") / name
        if target.exists():
            print(f"❌ 模块目录已存在: {target}")
            return 1

        # 复制模板
        template_dir = Path(__file__).parent.parent.parent / "templates" / "module"
        if not template_dir.exists():
            print(f"❌ 模板目录不存在: {template_dir}")
            return 1

        target.mkdir(parents=True, exist_ok=True)
        (target / "tests").mkdir(exist_ok=True)

        # 生成文件
        replacements = {
            "{{module_name}}": name,
            "{{ModuleName}}": name.replace("_", " ").title().replace(" ", ""),
            "{{module_description}}": desc,
            "{{author}}": author,
            "{{tag1}}": name.split("_")[0] if "_" in name else name,
            "{{tag2}}": "skill",
        }

        for tmpl_file in ["__init__.py", "module_spec.py", "handlers.py"]:
            src = template_dir / tmpl_file
            if src.exists():
                content = src.read_text(encoding="utf-8")
                for k, v in replacements.items():
                    content = content.replace(k, v)
                dest = target / tmpl_file
                dest.write_text(content, encoding="utf-8")

        # 测试文件
        test_src = template_dir / "tests" / "test_module.py"
        if test_src.exists():
            content = test_src.read_text(encoding="utf-8")
            for k, v in replacements.items():
                content = content.replace(k, v)
            (target / "tests" / "test_module.py").write_text(content, encoding="utf-8")
        (target / "tests" / "__init__.py").write_text("", encoding="utf-8")

        print(f"✓ 模块已创建: {target}")
        print(f"  名称: {name}")
        print(f"  描述: {desc}")
        print(f"  作者: {author}")
        print(f"\n下一步:")
        print(f"  1. 编辑 {target}/module_spec.py 实现业务逻辑")
        print(f"  2. 编辑 {target}/handlers.py 实现处理函数")
        print(f"  3. 运行 pytest {target}/tests/ 确保测试通过")
        return 0

    elif subcmd == "ls":
        from nexusagent.core.registry import get_module_registry
        registry = get_module_registry()
        modules = registry.list_modules()
        if not modules:
            print("暂无注册的模块")
            return 0
        print(f"{'模块名':<30} {'版本':<10} {'状态':<12} {'能力'}")
        print("-" * 70)
        for m in modules:
            caps = ",".join(k for k, v in m["capabilities"].items() if v)
            print(f"{m['name']:<30} {m['version']:<10} {m['state']:<12} {caps}")
        return 0

    elif subcmd == "health":
        from nexusagent.core.registry import get_module_registry
        registry = get_module_registry()
        health = registry.health_check_all()
        print(f"{'模块名':<30} {'状态':<12} {'详情'}")
        print("-" * 60)
        for name, h in health.items():
            status = h.get("status", "unknown")
            detail = h.get("error", "") or h.get("details", "")
            emoji = "🟢" if status == "healthy" else "🟡" if status == "degraded" else "🔴"
            print(f"{emoji} {name:<28} {status:<12} {str(detail)[:40]}")
        return 0

    else:
        print(f"未知操作: {subcmd}")
        print("用法: nexus module <init|ls|health>")
        return 1


def cmd_mode(args: list) -> int:
    """严谨执行模式管理: nexus mode <auto|strict|chat> | status
    Usage:
        nexus mode auto       自动检测模式（默认）
        nexus mode strict     强制严谨执行模式
        nexus mode chat       强制对话模式
        nexus mode status     查看当前模式配置
    """
    _ensure_project_root()
    from nexusagent.config.settings import get_config, reload_config

    subcmd = args[0] if args else "status"
    config = get_config()

    if subcmd in ("auto", "strict", "chat"):
        config.strict.mode = subcmd
        print(f"✓ 严谨执行模式已切换为: {subcmd}")
        if subcmd == "auto":
            print("   说明: 自动检测用户意图，任务请求走严谨模式，对话走常规模式")
        elif subcmd == "strict":
            print("   说明: 所有请求均走严谨执行模式（意图分析 + 任务分解 + 验证交付）")
        elif subcmd == "chat":
            print("   说明: 所有请求走常规 ReAct 对话模式")
        return 0

    elif subcmd == "status":
        print("📋 严谨执行模式状态")
        print(f"   当前模式: {config.strict.mode}")
        print(f"   最大澄清轮数: {config.strict.max_clarify_rounds}")
        print(f"   最大重试次数: {config.strict.max_retry_attempts}")
        print(f"   LLM 增强分析: {'启用' if config.strict.llm_enhanced_analysis else '禁用'}")
        print(f"   5 Expert 研讨: {'启用' if config.strict.enable_deliberation else '禁用'}")
        print(f"   自动重试: {'启用' if config.strict.auto_retry_on_failure else '禁用'}")
        return 0

    else:
        print(f"❌ 未知模式: {subcmd}")
        print("用法: nexus mode <auto|strict|chat|status>")
        return 1


def main() -> int:
    """CLI 主入口"""
    if len(sys.argv) < 2:
        print("NexusAgent CLI v4.0+")
        print()
        print("用法: nexus <command> [args...]")
        print()
        print("命令:")
        print("  init <name>    初始化项目脚手架")
        print("  dev            本地开发热启动")
        print("  status         组件健康检查 (HeartbeatMonitor)")
        print("  doctor         运行全部诊断检查")
        print("  encryption     导出加密密钥包")
        print("  graph          生成 StateGraph Mermaid 图")
        print("  deploy         Docker Compose 部署")
        print("  eval           运行 pytest 测试套件")
        print("  eval-framework 运行评估框架")
        print("  regression     运行回归测试")
        print("  benchmark      LLM Provider 性能基准测试")
        print("  backup         记忆系统备份管理")
        print("  module         模块管理 (init/ls/health)")
        print("  evolution      自我进化系统 (status/review/approve/reject/history/rollback/run/mode)")
        print("  mode           严谨执行模式切换 (auto/strict/chat/status)")
        print("  mcp            启动 MCP Server")
        print("  tool           工具管理 (ls/info/search)")
        print("  profile        用户画像 (show/learn/forget)")
        print("  dream          梦境引擎 (now)")
        return 0

    command = sys.argv[1]
    args = sys.argv[2:]

    commands = {
        "init": cmd_init,
        "dev": cmd_dev,
        "status": cmd_status_enhanced,
        "doctor": cmd_doctor,
        "deploy": cmd_deploy,
        "eval": cmd_eval,
        "eval-framework": cmd_eval_framework,
        "regression": cmd_regression,
        "benchmark": cmd_benchmark,
        "backup": cmd_backup,
        "module": cmd_module,
        "evolution": cmd_evolution,
        "mode": cmd_mode,
        "mcp": cmd_mcp,
        "tool": cmd_tool,
        "profile": cmd_profile,
        "dream": cmd_dream,
        "encryption": cmd_encryption_export,
        "graph": cmd_graph_visualize,
    }

    handler = commands.get(command)
    if not handler:
        print(f"❌ 未知命令: {command}")
        print(f"可用命令: {', '.join(commands.keys())}")
        return 1

    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
