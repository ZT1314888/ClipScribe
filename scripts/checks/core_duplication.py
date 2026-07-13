#!/usr/bin/env python3
"""
共享代码重复检测 + 架构规则核心（工具无关）。

单一事实源：Claude Code 的 pre-write hook、以及后续 Codex/CI 都可调用这里。

能力：
1. AST 结构分析 —— 提取类/方法/导入/装饰器/继承等特征（复用自原 hook）
2. 多维相似度评分 —— 检测潜在重复代码
3. 架构规则校验 —— 已改写为贴合本 MVP（SQLite 单容器，无 Redis/Celery/S3）

设计要点：
- 搜索路径基于本项目实际源码目录；目录不存在时静默跳过（早期结构未建立时不误报）。
- 架构规则针对本 MVP 的边界，而非上游 prepwise（Postgres/Celery/Redis）项目。

用法：
    库调用: from core_duplication import analyze_file
            dups, violations, role = analyze_file(path, content, project_dir)
    CLI:    uv run python scripts/checks/core_duplication.py <file.py>
"""

import ast
import os
import re
import subprocess
import sys
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# Windows 控制台默认 GBK，报告含 emoji 会 UnicodeEncodeError；强制 UTF-8 输出。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

# ============================================================================
# 配置
# ============================================================================

# 相似度阈值 (0-100)，按文件角色区分
SIMILARITY_THRESHOLDS = {
    "service": 60,
    "model": 55,
    "api": 45,
    "util": 65,
    "schema": 45,
    "default": 60,
}

# 各维度权重，总和为 1.0
KEYWORD_WEIGHTS = {
    "class_name": 0.20,
    "method_names": 0.25,
    "imports": 0.15,
    "decorators": 0.10,
    "base_classes": 0.15,
    "function_names": 0.15,
}

MAX_FILE_SIZE_MB = 5
FIND_TIMEOUT = 5
MAX_CANDIDATE_FILES = 30

# 本项目源码根候选目录。导入 AI-Video-Transcriber 底座后，
# 实际结构可能是 app/ 或 backend/ 等；此处列出候选，不存在的自动跳过。
SOURCE_ROOTS = ["app", "backend", "src", "server"]


# ============================================================================
# 文件角色识别
# ============================================================================


def detect_file_role(file_path: str) -> str:
    """识别文件在架构中的角色。"""
    path_lower = file_path.replace("\\", "/").lower()
    if "/services/" in path_lower:
        return "service"
    elif "/models/" in path_lower:
        return "model"
    elif "/api/" in path_lower or "/route/" in path_lower or "/routers/" in path_lower:
        return "api"
    elif "/schemas/" in path_lower:
        return "schema"
    elif "/utils/" in path_lower or "/core/" in path_lower:
        return "util"
    return "unknown"


# ============================================================================
# AST 代码分析（复用自原 hook）
# ============================================================================


class CodeAnalyzer(ast.NodeVisitor):
    """AST 代码分析器 —— 提取结构特征。"""

    def __init__(self):
        self.classes: List[Dict] = []
        self.functions: List[str] = []
        self.imports: Set[str] = set()
        self.decorators: Set[str] = set()

    def visit_ClassDef(self, node):
        self.classes.append(
            {
                "name": node.name,
                "methods": [
                    m.name for m in node.body if isinstance(m, ast.FunctionDef)
                ],
                "base_classes": [self._get_base_name(b) for b in node.bases],
                "decorators": [
                    self._get_decorator_name(d) for d in node.decorator_list
                ],
            }
        )
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        for decorator in node.decorator_list:
            self.decorators.add(self._get_decorator_name(decorator))
        self.generic_visit(node)

    def visit_Import(self, node):
        for alias in node.names:
            self.imports.add(alias.name.split(".")[0])

    def visit_ImportFrom(self, node):
        if node.module:
            self.imports.add(node.module.split(".")[0])

    def _get_base_name(self, base) -> str:
        if isinstance(base, ast.Name):
            return base.id
        elif isinstance(base, ast.Attribute):
            return base.attr
        return ""

    def _get_decorator_name(self, decorator) -> str:
        if isinstance(decorator, ast.Name):
            return decorator.id
        elif isinstance(decorator, ast.Attribute):
            return decorator.attr
        elif isinstance(decorator, ast.Call):
            if isinstance(decorator.func, ast.Name):
                return decorator.func.id
            elif isinstance(decorator.func, ast.Attribute):
                return decorator.func.attr
        return ""


def analyze_code(content: str) -> Optional[CodeAnalyzer]:
    """分析代码结构；解析失败返回 None。"""
    try:
        tree = ast.parse(content)
        analyzer = CodeAnalyzer()
        analyzer.visit(tree)

        class_methods = set()
        for cls in analyzer.classes:
            class_methods.update(cls["methods"])
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name not in class_methods:
                analyzer.functions.append(node.name)
        return analyzer
    except SyntaxError:
        return None
    except Exception as e:  # noqa: BLE001
        print(f"Warning: Failed to parse code: {e}", file=sys.stderr)
        return None


# ============================================================================
# 相似度计算
# ============================================================================


def calculate_string_similarity(str1: str, str2: str) -> float:
    return SequenceMatcher(None, str1.lower(), str2.lower()).ratio()


def calculate_set_similarity(set1: Set[str], set2: Set[str]) -> float:
    """Jaccard 相似度。"""
    if not set1 or not set2:
        return 0.0
    intersection = len(set1 & set2)
    union = len(set1 | set2)
    return intersection / union if union > 0 else 0.0


def calculate_code_similarity(
    analyzer1: CodeAnalyzer, analyzer2: CodeAnalyzer
) -> Tuple[float, Dict[str, float]]:
    scores: Dict[str, float] = {}

    scores["class_name"] = calculate_set_similarity(
        {c["name"] for c in analyzer1.classes},
        {c["name"] for c in analyzer2.classes},
    )

    methods1: Set[str] = set()
    methods2: Set[str] = set()
    for cls in analyzer1.classes:
        methods1.update(cls["methods"])
    for cls in analyzer2.classes:
        methods2.update(cls["methods"])
    scores["method_names"] = calculate_set_similarity(methods1, methods2)

    scores["imports"] = calculate_set_similarity(analyzer1.imports, analyzer2.imports)
    scores["decorators"] = calculate_set_similarity(
        analyzer1.decorators, analyzer2.decorators
    )

    bases1: Set[str] = set()
    bases2: Set[str] = set()
    for cls in analyzer1.classes:
        bases1.update(cls["base_classes"])
    for cls in analyzer2.classes:
        bases2.update(cls["base_classes"])
    scores["base_classes"] = calculate_set_similarity(bases1, bases2)

    scores["function_names"] = calculate_set_similarity(
        set(analyzer1.functions), set(analyzer2.functions)
    )

    total = sum(scores.get(k, 0) * w for k, w in KEYWORD_WEIGHTS.items())
    return total * 100, scores


# ============================================================================
# 候选文件搜索
# ============================================================================


def _existing_source_roots(project_dir: str) -> List[str]:
    """返回项目中实际存在的源码根目录（不存在的自动跳过）。"""
    roots = []
    for name in SOURCE_ROOTS:
        candidate = os.path.join(project_dir, name)
        if os.path.isdir(candidate):
            roots.append(candidate)
    return roots


def find_similar_files(file_path: str, project_dir: str) -> List[str]:
    """在实际存在的源码目录中搜索候选 Python 文件。"""
    search_roots = _existing_source_roots(project_dir)
    if not search_roots:
        return []  # 源码结构尚未建立 —— 早期静默跳过，不误报

    candidate_files: List[str] = []
    for root in search_roots:
        try:
            result = subprocess.run(
                [
                    "find",
                    root,
                    "-type",
                    "f",
                    "-name",
                    "*.py",
                    "-not",
                    "-path",
                    "*/.venv/*",
                    "-not",
                    "-path",
                    "*/__pycache__/*",
                    "-not",
                    "-path",
                    "*/test_*",
                    "-not",
                    "-path",
                    "*/migrations/*",
                ],
                capture_output=True,
                text=True,
                timeout=FIND_TIMEOUT,
            )
            if result.returncode == 0:
                for f in result.stdout.split("\n"):
                    f = f.strip()
                    if f and f != file_path:
                        candidate_files.append(f)
        except subprocess.TimeoutExpired:
            print(f"Warning: find timed out in {root}", file=sys.stderr)
        except Exception as e:  # noqa: BLE001
            print(f"Warning: search failed in {root}: {e}", file=sys.stderr)

    return candidate_files[:MAX_CANDIDATE_FILES]


def detect_code_duplication(
    file_path: str, content: str, project_dir: str
) -> List[Dict]:
    analyzer = analyze_code(content)
    if not analyzer:
        return []

    role = detect_file_role(file_path)
    threshold = SIMILARITY_THRESHOLDS.get(role, SIMILARITY_THRESHOLDS["default"])
    candidates = find_similar_files(file_path, project_dir)

    results: List[Dict] = []
    for candidate in candidates:
        try:
            if os.path.getsize(candidate) > MAX_FILE_SIZE_MB * 1024 * 1024:
                continue
            with open(candidate, "r", encoding="utf-8") as f:
                candidate_content = f.read()
            candidate_analyzer = analyze_code(candidate_content)
            if not candidate_analyzer:
                continue
            score, details = calculate_code_similarity(analyzer, candidate_analyzer)
            if score >= threshold:
                results.append(
                    {
                        "similar_file": candidate,
                        "similarity_score": score,
                        "threshold": threshold,
                        "details": details,
                    }
                )
        except UnicodeDecodeError:
            continue
        except Exception as e:  # noqa: BLE001
            print(f"Warning: failed to analyze {candidate}: {e}", file=sys.stderr)
            continue

    results.sort(key=lambda x: x["similarity_score"], reverse=True)
    return results[:3]


# ============================================================================
# 架构规则校验（已改写适配本 MVP）
# ============================================================================


def validate_architecture(file_path: str, content: str) -> List[Dict]:
    """
    校验本 MVP 的架构边界。

    MVP 方案明确：SQLite 单容器单 worker，不引入 Redis/Celery/Postgres/S3。
    这些规则用于在早期就挡住"偷偷把砍掉的复杂度加回来"。
    """
    violations: List[Dict] = []
    normalized = file_path.replace("\\", "/")

    # 规则 1：MVP 已砍掉 Redis / Celery 队列
    if re.search(r"^\s*import\s+(redis|celery)\b", content, re.MULTILINE) or re.search(
        r"^\s*from\s+(redis|celery)\b", content, re.MULTILINE
    ):
        violations.append(
            {
                "rule": "MVP Scope",
                "severity": "warning",
                "message": (
                    "MVP 方案明确不引入 Redis/Celery 队列（单容器单 worker）。"
                    "如确需队列，请先更新方案文档与 ADR。"
                ),
            }
        )

    # 规则 2：MVP 用 SQLite，不用 Postgres 异步引擎
    if (
        re.search(r"create_async_engine\s*\(", content)
        and "postgres" in content.lower()
    ):
        violations.append(
            {
                "rule": "MVP Scope",
                "severity": "warning",
                "message": "MVP 使用 SQLite；Postgres 异步引擎不在第一版范围内。",
            }
        )

    # 规则 3：环境变量集中管理 —— 仅允许在配置模块读取
    if ("os.getenv" in content or "os.environ" in content) and not re.search(
        r"(^|/)(config|settings)\.py$", normalized
    ):
        violations.append(
            {
                "rule": "Configuration",
                "severity": "warning",
                "message": "环境变量请集中在 config/settings 模块读取，避免散落各处。",
            }
        )

    return violations


# ============================================================================
# 对外统一入口
# ============================================================================


def analyze_file(
    file_path: str, content: str, project_dir: str
) -> Tuple[List[Dict], List[Dict], str]:
    """
    返回 (duplications, violations, file_role)。
    供各适配器（Claude hook / CLI）复用。
    """
    duplications = detect_code_duplication(file_path, content, project_dir)
    violations = validate_architecture(file_path, content)
    role = detect_file_role(file_path)
    return duplications, violations, role


def format_report(
    duplications: List[Dict], violations: List[Dict], role: str
) -> Optional[str]:
    if not duplications and not violations:
        return None

    lines = ["🔍 Pre-Write Analysis\n", "═" * 60]

    if duplications:
        lines.append(f"\n📊 Code Similarity (Role: {role})")
        for idx, dup in enumerate(duplications, 1):
            score = dup["similarity_score"]
            if score >= 80:
                level = "🚨 Very High"
            elif score >= 70:
                level = "⚠️  High"
            else:
                level = "ℹ️  Moderate"
            lines.append(
                f"\n{idx}. {level} Similarity: {score:.1f}/100 "
                f"(Threshold: {dup['threshold']})"
            )
            lines.append(f"   Similar to: {dup['similar_file']}")
            for key, value in dup["details"].items():
                if value > 0:
                    lines.append(f"     - {key}: {value * 100:.0f}%")
        lines.append("\n💡 建议：能否扩展已有代码而非新增？必要时咨询架构。")

    if violations:
        lines.append("\n\n🚨 架构规则提示：")
        for v in violations:
            icon = "❌" if v["severity"] == "error" else "⚠️"
            lines.append(f"\n{icon} {v['rule']}")
            lines.append(f"   {v['message']}")
            if "details" in v:
                lines.append(f"   Details: {v['details']}")

    return "\n".join(lines)


def _cli(argv: List[str]) -> int:
    files = [a for a in argv if a.endswith(".py")]
    if not files:
        return 0
    project_dir = os.getcwd()
    for file_path in files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except OSError:
            continue
        dups, violations, role = analyze_file(file_path, content, project_dir)
        report = format_report(dups, violations, role)
        if report:
            print(report)
    return 0


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
