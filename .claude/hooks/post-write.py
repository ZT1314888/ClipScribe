#!/usr/bin/env python3
"""
Claude Code Post-Write Hook —— 薄适配器。

职责仅限于：
1. 读取 Claude Code 通过 stdin 传入的 JSON（tool_input.file_path 等）。
2. 调用工具无关的共享核心 scripts/checks/core_quality.py。
3. 按 Claude Code 的 hookSpecificOutput 协议输出结果。

真正的检查逻辑不在这里，而在 scripts/checks/core_quality.py，
以便 git pre-commit / Codex 复用同一份逻辑。
"""

import json
import os
import sys
from pathlib import Path

# 让本适配器能 import 到 scripts/checks/ 下的共享核心
PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_DIR / "scripts" / "checks"))

import core_quality  # noqa: E402


def load_input():
    try:
        if not sys.stdin.isatty():
            return json.load(sys.stdin)
        return None
    except json.JSONDecodeError:
        return None


def main():
    input_data = load_input()

    if input_data:
        tool_input = input_data.get("tool_input", {})
        file_path = tool_input.get("file_path", "")
        project_dir = input_data.get("cwd", str(PROJECT_DIR))
    else:
        file_path = os.environ.get("TOOL_INPUT_file_path", "")
        project_dir = os.environ.get("CLAUDE_PROJECT_DIR", str(PROJECT_DIR))

    if not file_path:
        sys.exit(0)

    results = core_quality.run_quality(file_path, project_dir)
    if results is None:
        sys.exit(0)  # 非 Python / 排除路径，静默通过

    report = core_quality.format_report(file_path, results)

    output = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "displayText": report,
        }
    }

    if core_quality.has_critical_errors(results):
        output["hookSpecificOutput"]["permissionDecision"] = "block"
        output["hookSpecificOutput"][
            "permissionDecisionReason"
        ] = "Critical Flake8 errors must be fixed before proceeding"
        print(json.dumps(output))
        sys.exit(1)

    print(json.dumps(output))
    sys.exit(0)


if __name__ == "__main__":
    main()
