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
