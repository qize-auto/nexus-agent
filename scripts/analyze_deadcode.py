"""
死代码分析脚本 — 静态扫描所有类/函数定义，检查是否被引用
"""
import ast
import os
from pathlib import Path
from collections import defaultdict

PROJECT_ROOT = Path("C:/Users/qize/Desktop/nexusagent")
EXCLUDE_DIRS = {".git", "__pycache__", ".pytest_cache", "node_modules", "htmlcov", "_backup"}
EXCLUDE_FILES = {"analyze_deadcode.py"}

def find_python_files():
    files = []
    for p in PROJECT_ROOT.rglob("*.py"):
        if any(part in EXCLUDE_DIRS for part in p.parts):
            continue
        if p.name in EXCLUDE_FILES:
            continue
        files.append(p)
    return files

def extract_definitions(source, filepath):
    """从AST中提取类名、函数名"""
    defs = {"classes": [], "functions": [], "imports": []}
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        print(f"  Syntax error in {filepath}: {e}")
        return defs
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            defs["classes"].append((node.name, node.lineno))
        elif isinstance(node, ast.FunctionDef) and node.name.startswith("_") is False:
            defs["functions"].append((node.name, node.lineno))
        elif isinstance(node, ast.AsyncFunctionDef) and node.name.startswith("_") is False:
            defs["functions"].append((node.name, node.lineno))
    return defs

def main():
    files = find_python_files()
    print(f"找到 {len(files)} 个 Python 文件")

    # 收集所有定义
    all_defs = defaultdict(list)  # name -> [(filepath, type, lineno)]
    file_sources = {}

    for f in files:
        rel = f.relative_to(PROJECT_ROOT)
        src = f.read_text(encoding="utf-8")
        file_sources[rel] = src
        defs = extract_definitions(src, rel)
        for name, lineno in defs["classes"]:
            all_defs[name].append((rel, "class", lineno))
        for name, lineno in defs["functions"]:
            all_defs[name].append((rel, "function", lineno))

    # 检查每个定义是否被其他文件引用
    dead_candidates = []
    test_only_candidates = []

    for name, locations in all_defs.items():
        # 忽略常见的不需要检查的名称
        if name in {"main", "test", "setup", "teardown", "pytest", "asyncio"}:
            continue
        if name.startswith("Test") or name.startswith("test_"):
            continue
        if name in {"Path", "Dict", "List", "Any", "Optional", "Tuple", "Enum", "auto", "dataclass", "field"}:
            continue

        for loc in locations:
            rel, typ, lineno = loc
            is_test_file = "test_" in str(rel) or "/tests/" in str(rel)
            if is_test_file:
                continue  # 只分析非测试文件中的定义

            # 搜索引用
            referenced_elsewhere = False
            referenced_in_test = False
            for other_rel, other_src in file_sources.items():
                if other_rel == rel:
                    continue
                # 简单文本搜索（不够精确但够用）
                if name in other_src:
                    if "test_" in str(other_rel) or "/tests/" in str(other_rel):
                        referenced_in_test = True
                    else:
                        referenced_elsewhere = True
                        break

            if not referenced_elsewhere:
                if referenced_in_test:
                    test_only_candidates.append((name, typ, rel, lineno))
                else:
                    dead_candidates.append((name, typ, rel, lineno))

    print("\n=== 仅被测试引用的定义 ===")
    for name, typ, rel, lineno in sorted(test_only_candidates, key=lambda x: str(x[2])):
        print(f"  {rel}:{lineno} [{typ}] {name} — 仅测试引用")

    print("\n=== 疑似死代码（无任何引用） ===")
    for name, typ, rel, lineno in sorted(dead_candidates, key=lambda x: str(x[2])):
        print(f"  {rel}:{lineno} [{typ}] {name} — 未引用")

    print(f"\n总计: {len(dead_candidates)} 个死代码候选, {len(test_only_candidates)} 个仅测试引用")

if __name__ == "__main__":
    main()
