"""汎用ファイル・コマンド操作 MCP tool 群。

read_file / write_file / run_command。
Claude Desktop からリポジトリを直接操作するための最小限 I/F。
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from mcp_server._context import mcp, BASE_DIR



@mcp.tool()
def read_file(file_path: str) -> str:
    """指定パスのファイルを読み取る。

    Args:
        file_path: 絶対パスまたはリポジトリルートからの相対パス
    """
    target = Path(file_path)
    if not target.is_absolute():
        target = GITHUB_DIR / file_path
    if not target.exists():
        return f"ERROR: File not found: {target}"
    if not target.is_file():
        return f"ERROR: Not a file: {target}"
    try:
        return target.read_text(encoding="utf-8")
    except Exception as e:
        return f"ERROR: {e}"


@mcp.tool()
def write_file(file_path: str, content: str) -> str:
    """指定パスにファイルを書き込む（上書き保存）。

    Args:
        file_path: 絶対パスまたはリポジトリルートからの相対パス
        content: ファイルの全内容
    """
    target = Path(file_path)
    if not target.is_absolute():
        target = GITHUB_DIR / file_path
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        target.write_text(content, encoding="utf-8")
        return f"OK: Saved {target} ({len(content)} chars)"
    except Exception as e:
        return f"ERROR: {e}"


@mcp.tool()
def run_command(command: str, working_directory: str = "") -> str:
    """PowerShellコマンドを実行して結果を返す。

    Args:
        command: 実行するPowerShellコマンド
        working_directory: 作業ディレクトリ（空ならリポジトリルート）
    """
    cwd = working_directory if working_directory else str(GITHUB_DIR)
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=300,
        )
        output = result.stdout.strip()
        err = result.stderr.strip()
        parts = []
        if output:
            parts.append(output)
        if err:
            parts.append(f"[STDERR]\n{err}")
        if result.returncode != 0:
            parts.insert(0, f"[EXIT CODE: {result.returncode}]")
        return "\n".join(parts) if parts else "(no output)"
    except subprocess.TimeoutExpired:
        return "ERROR: Command timed out (300s limit)"
    except Exception as e:
        return f"ERROR: {e}"


# ---------------------------------------------------------------------------
