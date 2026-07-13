#!/usr/bin/env python3
"""
Claude Code Pre-Write Hook —— 薄适配器。

职责仅限于：
1. 读取 Claude Code 通过 stdin 传入的 JSON（tool_input.file_path / content 等）。
2. 调用工具无关的共享核心 scripts/checks/core_duplication.py。
3. 按 Claude Code 的 PreToolUse 协议输出结果（可 ask 阻断）。

真正的重复检测与架构规则逻辑在 scripts/checks/core_duplication.py，
以便 git pre-commit / Codex 复用同一份逻辑。
"""

import json
import os
import sys
from pathlib import Path

# 让本适配器能 import 到 scripts/checks/ 下的共享核心
PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_DIR / "scripts" / "checks"))

import core_duplication  # noqa: E402

# 与 core_quality 一致的排除路径 + 本 hook 自身
EXCLUDE_PATTERNS = [
    "/venv/",
    "/env/",
    "/.venv/",
    "/__pycache__/",
    "/site-packages/",
    "/.claude/hooks/",
    "/scripts/checks/",
    "/migrations/",
    "/test_",
]


def load_input():
    try:
        return json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON input: {e}", file=sys.stderr)
        sys.exit(0)  # 输入异常时放行，不阻断用户


def main():
    input_data = load_input()

    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})
    project_dir = input_data.get("cwd", str(PROJECT_DIR))

    if tool_name not in ("Write", "Edit"):
        sys.exit(0)

    file_path = tool_input.get("file_path", "")
    content = tool_input.get("content", "") or tool_input.get("new_string", "")

    if not file_path.endswith(".py"):
        sys.exit(0)

    normalized = file_path.replace("\\", "/")
    if any(pattern in normalized for pattern in EXCLUDE_PATTERNS):
        sys.exit(0)

    duplications, violations, role = core_duplication.analyze_file(
        file_path, content, project_dir
    )
    message = core_duplication.format_report(duplications, violations, role)

    if not message:
        sys.exit(0)

    has_errors = any(v["severity"] == "error" for v in violations)
    has_high_similarity = any(d["similarity_score"] >= 80 for d in duplications)

    if has_errors or has_high_similarity:
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "ask",
                "permissionDecisionReason": message,
            }
        }
        print(json.dumps(output))
        sys.exit(0)

    # 仅警告：展示但放行
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "displayText": message,
        }
    }
    print(json.dumps(output))
    sys.exit(0)


if __name__ == "__main__":
    main()
