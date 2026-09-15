#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""westock-cli —— 增强源（enhanced）。

腾讯官方 Go CLI `westock`（发布源 https://stockbuddy.qq.com/release/workbuddy/cli），
与 npm 包同源（腾讯自选股数据），但命令面更全。本 provider 只用它补齐 npm 包
**没有的资讯面**：

    news   新闻    westock news list <code> --limit 10
    report 研报    westock report list <code> --limit 8
    notice 公告    westock notice list <code> --limit 10
    fund   资金    westock fund flow <code>

core 数值（财务/K线等）仍由 westock-npm 提供，避免两源字段口径不一致。

安装
----
    bash scripts/install_westock_cli.sh

脚本从官方源下载并做 SHA256 校验，默认装到技能私有目录
`<skill_root>/tools/bin/westock`（不污染系统 PATH，也不用 sudo）。
若系统 PATH 里已有 `westock`，则优先使用系统版本。
未安装时 `available()` 返回 False，主流程自动跳过增强任务，不影响研究。
"""

from __future__ import annotations

import shutil
from pathlib import Path

from .base import DEFAULT_TIMEOUT, FetchResult, Provider, run_cmd

# 技能私有安装位置（install_westock_cli.sh 的默认目标）
SKILL_ROOT = Path(__file__).resolve().parent.parent
PRIVATE_BIN = SKILL_ROOT / "tools" / "bin" / "westock"

# enhanced 任务名 -> 命令行参数（code 由 fetch 追加到末尾）
ARGV: dict[str, list[str]] = {
    "news":      ["news", "list"],
    "report":    ["report", "list"],
    "notice":    ["notice", "list"],
    "fund_flow": ["fund", "flow"],
}

# 各命令的条数上限（避免返回体积过大）
LIMITS: dict[str, str] = {
    "news": "10",
    "report": "8",
    "notice": "10",
}


class WestockCliProvider(Provider):
    name = "westock-cli"
    desc = "增强源：腾讯官方 Go CLI westock（新闻/研报/公告/资金流向，需先安装）"
    supports = set(ARGV)

    @staticmethod
    def binary() -> str | None:
        """定位 westock 可执行文件：系统 PATH 优先，其次技能私有目录。"""
        sys_bin = shutil.which("westock")
        if sys_bin:
            return sys_bin
        if PRIVATE_BIN.is_file():
            return str(PRIVATE_BIN)
        return None

    def available(self) -> tuple[bool, str]:
        bin_path = self.binary()
        if not bin_path:
            return False, "未安装 westock CLI（运行 scripts/install_westock_cli.sh 安装）"
        # 轻量探活：--help 应返回 0 且输出含 usage 信息
        ok, out = run_cmd([bin_path, "--help"], timeout=30)
        if ok or "westock" in out.lower():
            return True, f"已安装（{bin_path}）"
        return False, "westock 无法正常执行（可能架构不匹配或损坏，请重装）"

    def fetch(self, task: str, code: str, name: str = "",
              timeout: int = DEFAULT_TIMEOUT) -> FetchResult:
        argv = ARGV.get(task)
        if argv is None:
            return FetchResult(task, False, error=f"未知任务: {task}")
        bin_path = self.binary()
        if not bin_path:
            return FetchResult(task, False, error="未安装 westock CLI")

        cmd = [bin_path] + argv + [code]
        if task in LIMITS:
            cmd += ["--limit", LIMITS[task]]
        ok, out = run_cmd(cmd, timeout=timeout)
        return FetchResult(task=task, ok=ok, text=out,
                           error="" if ok else out.strip()[:200])
