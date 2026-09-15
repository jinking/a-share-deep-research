#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""westock-npm —— 结构化主源（core）。

数据来源为公开 npm 包 `westock-data-clawhub`，通过 `npx -y` 调用，无需任何账号
或私有凭证，只要本机有 Node.js >= 18 即可运行：

    npx -y westock-data-clawhub@1.0.4 search 贵州茅台

它是本技能所有 core 数值（行情/K线/三大表/技术指标/股东/分红/资金两融）的默认来源，
字段名固定，下游 scripts/fetch_stock.py 的 CSV 整理直接依赖其英文列名。

⚠️ 数据源说明
-------------
该 npm 包由第三方个人维护，本项目仅调用其命令行接口。用于投资决策前请以交易所公告、
公司定期报告等一手资料交叉核验。若上游包停更，可在 providers/ 下接入替代源。
"""

from __future__ import annotations

from .base import DEFAULT_TIMEOUT, FetchResult, Provider, run_cmd

PKG = "westock-data-clawhub@1.0.4"

# core 任务名 -> 命令行参数（保持 TASK_SPECS 顺序）
# 注意：npm 包要求股票代码必须**紧跟子命令**，再跟其它参数
#   ✅ westock-data finance sz002897 --type lrb --num 30
#   ❌ westock-data finance --type lrb --num 30 sz002897
# 故用 {code} 占位符标记代码位置，由 fetch() 展开。
ARGV: dict[str, list[str]] = {
    "profile":     ["profile", "{code}"],
    "finance_is":  ["finance", "{code}", "--type", "lrb", "--num", "30"],
    "finance_bs":  ["finance", "{code}", "--type", "zcfz", "--num", "30"],
    "finance_cf":  ["finance", "{code}", "--type", "xjll", "--num", "30"],
    "technical":   ["technical", "{code}"],
    "shareholder": ["shareholder", "{code}"],
    "kline":       ["kline", "{code}", "--period", "day", "--limit", "60"],
    "dividend":    ["dividend", "{code}", "--years", "5"],
    "asfund":      ["asfund", "{code}"],
    "margintrade": ["margintrade", "{code}"],
}


class WestockNpmProvider(Provider):
    name = "westock-npm"
    desc = "结构化主源：公开 npm 包 westock-data-clawhub（行情/K线/三大表/技术/股东/资金，需 Node >= 18）"
    supports = set(ARGV)

    def available(self) -> tuple[bool, str]:
        ok, out = run_cmd(["npx", "-y", PKG, "search", "贵州茅台"], timeout=90)
        if ok and "600519" in out:
            return True, f"npx + {PKG} 可用"
        if not ok and "命令不存在" in out:
            return False, "未检测到 Node.js / npx（需 Node >= 18）"
        return False, "npx 调用失败或返回内容异常（可能是网络问题，请重试）"

    def fetch(self, task: str, code: str, name: str = "",
              timeout: int = DEFAULT_TIMEOUT) -> FetchResult:
        argv = ARGV.get(task)
        if argv is None:
            return FetchResult(task, False, error=f"未知任务: {task}")
        args = [a.replace("{code}", code) for a in argv]
        ok, out = run_cmd(["npx", "-y", PKG] + args, timeout=timeout)
        return FetchResult(task=task, ok=ok, text=out,
                           error="" if ok else out.strip()[:200])
