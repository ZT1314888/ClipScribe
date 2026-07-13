#!/usr/bin/env python3
"""
共享代码质量检查核心（工具无关）。

单一事实源：Claude Code 的 post-write hook、git pre-commit、Codex 都调用这里。

能力：
1. black 格式化
2. isort import 排序
3. flake8 critical 检查（E9,F63,F7,F82）

所有外部工具通过 `uv run` 调用，跨平台、自动使用项目虚拟环境，
不写死 `venv/bin/*` 之类路径。

用法：
    库调用:  from core_quality import run_quality; report = run_quality(path)
    CLI:     uv run python scripts/checks/core_quality.py <file1.py> [file2.py ...]
             critical flake8 错误时退出码为 1（供 git hook 拦截提交）。
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Windows 控制台默认 GBK，报告含 emoji 会 UnicodeEncodeError；强制 UTF-8 输出。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

# 通过 uv run 调用工具：跨平台、自动走项目 env
UV_RUN = ["uv", "run"]

# flake8 只检查会导致运行失败的严重错误
CRITICAL_SELECT = "E9,F63,F7,F82"

EXCLUDE_PATTERNS = [
    "/venv/",
    "/env/",
    "/.venv/",
    "/site-packages/",
    "/__pycache__/",
    "/.pytest_cache/",
    "/node_modules/",
]


def should_run_checks(file_path: str) -> bool:
    """仅对项目内 Python 文件运行检查。"""
    if not file_path.endswith(".py"):
        return False
    normalized = file_path.replace("\\", "/")
    return not any(pattern in normalized for pattern in EXCLUDE_PATTERNS)


def _run_tool(
    tool_args: List[str], project_dir: Optional[str], timeout: int = 30
) -> subprocess.CompletedProcess:
    """通过 uv run 执行一个工具。

    project_dir 无效时回退到当前工作目录，避免 subprocess 因 cwd
    无效直接抛 WinError 267（例如传入 MSYS 风格路径）。
    """
    cmd = UV_RUN + tool_args
    cwd = project_dir if project_dir and os.path.isdir(project_dir) else None
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=cwd,
    )


def run_black(file_path: str, project_dir: Optional[str]) -> Dict:
    try:
        result = _run_tool(["black", file_path], project_dir)
        if result.returncode == 0:
            return {"success": True, "message": "Black formatting applied"}
        return {
            "success": False,
            "message": f"Black failed: {(result.stderr or result.stdout).strip()}",
            "can_continue": True,
        }
    except FileNotFoundError:
        return {
            "success": False,
            "message": "uv not found. Install uv and run `uv sync`.",
            "can_continue": True,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "message": "Black timed out", "can_continue": True}
    except Exception as e:  # noqa: BLE001 - 检查脚本需宽容，不应因自身异常阻断
        return {"success": False, "message": f"Black error: {e}", "can_continue": True}


def run_isort(file_path: str, project_dir: Optional[str]) -> Dict:
    try:
        result = _run_tool(["isort", file_path], project_dir)
        if result.returncode == 0:
            return {"success": True, "message": "Import sorting applied"}
        return {
            "success": False,
            "message": f"isort failed: {(result.stderr or result.stdout).strip()}",
            "can_continue": True,
        }
    except FileNotFoundError:
        return {
            "success": False,
            "message": "uv not found. Install uv and run `uv sync`.",
            "can_continue": True,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "message": "isort timed out", "can_continue": True}
    except Exception as e:  # noqa: BLE001
        return {"success": False, "message": f"isort error: {e}", "can_continue": True}


def parse_flake8_errors(output: str) -> List[Dict]:
    errors = []
    for line in output.strip().split("\n"):
        if not line.strip():
            continue
        # 格式: file.py:line:col: CODE message
        parts = line.split(":", 3)
        if len(parts) >= 4:
            errors.append(
                {
                    "file": parts[0],
                    "line": int(parts[1]) if parts[1].isdigit() else 0,
                    "column": int(parts[2]) if parts[2].isdigit() else 0,
                    "message": parts[3].strip(),
                }
            )
    return errors


def run_flake8(file_path: str, project_dir: Optional[str]) -> Dict:
    try:
        result = _run_tool(
            ["flake8", f"--select={CRITICAL_SELECT}", file_path], project_dir
        )
        if result.returncode == 0:
            return {"success": True, "message": "No critical errors found"}
        errors_text = result.stdout or result.stderr
        return {
            "success": False,
            "message": f"Critical errors found:\n{errors_text.strip()}",
            "can_continue": False,  # critical 错误必须修复
            "errors": parse_flake8_errors(errors_text),
        }
    except FileNotFoundError:
        return {
            "success": False,
            "message": "uv not found. Install uv and run `uv sync`.",
            "can_continue": True,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "message": "Flake8 timed out", "can_continue": True}
    except Exception as e:  # noqa: BLE001
        return {"success": False, "message": f"Flake8 error: {e}", "can_continue": True}


def run_quality(file_path: str, project_dir: Optional[str] = None) -> Optional[Dict]:
    """
    对单个文件运行全部质量检查。

    返回 results dict（含 black/isort/flake8 三项结果），
    非 Python / 排除路径返回 None。
    """
    if not should_run_checks(file_path):
        return None
    # 用绝对路径传给工具：这样无论 subprocess 的 cwd 是什么，都能定位到文件，
    # 避免相对路径 + 变更 cwd 导致的路径重复拼接（scripts/checks/scripts/checks）。
    abs_path = str(Path(file_path).resolve())
    if project_dir is None:
        project_dir = os.getcwd()
    return {
        "black": run_black(abs_path, project_dir),
        "isort": run_isort(abs_path, project_dir),
        "flake8": run_flake8(abs_path, project_dir),
    }


def has_critical_errors(results: Dict) -> bool:
    """是否存在必须修复的 critical 错误。"""
    flake8 = results.get("flake8")
    return bool(
        flake8 and not flake8["success"] and not flake8.get("can_continue", False)
    )


def format_report(file_path: str, results: Dict) -> str:
    """把 results 渲染成可读报告。"""
    lines = [f"\n📊 Code Quality Report: {file_path}\n", "═" * 50]

    for tool_key, label in (
        ("black", "Black Formatter"),
        ("isort", "isort"),
        ("flake8", "Flake8 Critical Checks"),
    ):
        res = results.get(tool_key)
        if not res:
            continue
        if tool_key == "flake8":
            icon = "✅" if res["success"] else "❌"
        else:
            icon = "✅" if res["success"] else "⚠️"
        lines.append(f"\n{icon} {label}")
        lines.append(f"   {res['message']}")
        if res.get("errors"):
            lines.append("\n   Errors to fix:")
            for err in res["errors"]:
                lines.append(f"   - Line {err['line']}: {err['message']}")

    lines.append("\n" + "═" * 50)
    return "\n".join(lines)


def _cli(argv: List[str]) -> int:
    """CLI 入口：供 git pre-commit / Codex 直接调用。"""
    files = [a for a in argv if a.endswith(".py")]
    if not files:
        return 0

    exit_code = 0
    for file_path in files:
        results = run_quality(file_path)
        if results is None:
            continue
        print(format_report(file_path, results))
        if has_critical_errors(results):
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
