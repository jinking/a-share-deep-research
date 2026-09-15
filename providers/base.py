#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""取数 provider 接口层 —— WorkBuddy 专用版。

三源分工
--------
本技能默认在 WorkBuddy 环境下运行，结构化数值与语义检索分别由不同数据源承担：

  1. westock-npm  —— 结构化主源（core）
       公开 npm 包 `westock-data-clawhub`，覆盖行情 / K线 / 三大财务报表 /
       技术指标 / 股东结构 / 分红 / 资金两融。零配置（只需 Node >= 18），
       是所有研究的默认结构化来源。字段名固定，下游 CSV 整理直接依赖它。

  2. westock-cli  —— 增强源（enhanced）
       腾讯官方 Go CLI `westock`（发布源 stockbuddy.qq.com），补齐 npm 包缺失的
       资讯面：新闻 / 券商研报 / 公司公告 / 资金流向。需先安装
       （scripts/install_westock_cli.sh）；未安装时自动跳过，不影响主流程。

  3. neodata      —— 语义检索源（search）
       WorkBuddy 平台金融数据服务，自然语言查询「财报全文 / 主营构成 / 供应链
       关系 / 业绩会纪要 / 机构一致预期 / 风险事件」。凭证由平台下发（本地缓存
       12 小时）；失效时由 Agent 调用 connect_cloud_service 刷新后再查。

降级纪律
--------
任一数据源不可用都 **不中断** 研究：
  - core 任务缺失 → 提示用一手资料搜索补齐（见 scripts/fetch_stock.py 的搜索清单）
  - enhanced 任务缺失 → 静默跳过（Go CLI 未装属正常状态）
  - search 任务缺失 → 记入元信息，由 Agent 用 WebSearch 兜底

新增数据源
----------
写一个 `Provider`（结构化）或 `SearchProvider`（检索）子类，在
`providers/__init__.py` 的注册表里登记即可，主流程无需改动。
"""

from __future__ import annotations

import subprocess

# ---------------------------------------------------------------- 任务表
# 任务名 -> (中文说明, 是否关键, 分组)
#   分组 core     : 结构化数值，由 westock-npm 承担（关键项缺失需搜索补齐）
#   分组 enhanced : 资讯面增强，由 westock-cli 承担（缺失可容忍）
TASK_SPECS: dict[str, tuple[str, bool, str]] = {
    # ---- core：结构化数值（westock-npm）----
    "profile":     ("公司简况",           True,  "core"),
    "finance_is":  ("利润表(近30期)",     True,  "core"),
    "finance_bs":  ("资产负债表(近30期)", True,  "core"),
    "finance_cf":  ("现金流量表(近30期)", True,  "core"),
    "technical":   ("技术指标",           False, "core"),
    "shareholder": ("股东结构",           False, "core"),
    "kline":       ("日K线(60日)",        False, "core"),
    "dividend":    ("分红(近5年)",        False, "core"),
    "asfund":      ("主力资金",           False, "core"),
    "margintrade": ("融资融券",           False, "core"),
    # ---- enhanced：资讯面（westock-cli）----
    "news":        ("近期新闻",           False, "enhanced"),
    "report":      ("券商研报",           False, "enhanced"),
    "notice":      ("公司公告",           False, "enhanced"),
    "fund_flow":   ("资金流向",           False, "enhanced"),
}

# 检索任务（neodata 专属）：任务名 -> (中文说明, 自然语言 query 模板)
# 模板占位符：{name} 股票名、{code_plain} 去市场前缀的代码
SEARCH_TASKS: dict[str, tuple[str, str]] = {
    "s_fin_latest": ("最新一期财报",   "{name}（{code_plain}）最新一期财报 营业收入 归母净利润 扣非 毛利率 经营现金流"),
    "s_business":   ("主营构成拆解",   "{name} 最新主营构成 分业务收入 占比 同比增速 毛利率"),
    "s_supply":     ("供应链关系",     "{name} 主要供应商 主要客户 采购金额 销售金额 占比"),
    "s_consensus":  ("机构一致预期",   "{name} 最新机构评级 目标价 盈利预测 一致预期"),
    "s_earnings":   ("业绩会纪要",     "{name} 最近一次业绩发布会 纪要 管理层 经营指引"),
    "s_risk":       ("风险事件",       "{name} 股权质押 解禁 减持 诉讼 监管问询 风险提示"),
}

DEFAULT_TIMEOUT = 120


# ---------------------------------------------------------------- 结果容器
class FetchResult:
    """单次取数结果。"""

    __slots__ = ("task", "ok", "text", "error")

    def __init__(self, task: str, ok: bool, text: str = "", error: str = ""):
        self.task = task
        self.ok = ok
        self.text = text
        self.error = error

    @property
    def has_table(self) -> bool:
        """结构化源普遍返回 markdown 表格；无表格视为空结果。"""
        return "|" in self.text

    @property
    def has_content(self) -> bool:
        """检索源没有表格，以「非空且无错误前缀」判定有效。"""
        t = (self.text or "").strip()
        return bool(t) and not t.startswith(("ERROR", "TIMEOUT", "TOKEN_", "AUTH_"))

    def __repr__(self) -> str:
        return f"<FetchResult {self.task} ok={self.ok} len={len(self.text)}>"


# ---------------------------------------------------------------- 基类
class Provider:
    """取数 provider 基类。子类至少实现 `available()` 与 `fetch()`。

    `supports` 声明该源能提供的任务名集合；主流程据此决定向谁取哪一类数据。
    """

    name = "base"
    desc = ""
    supports: set[str] = set()

    def available(self) -> tuple[bool, str]:
        """返回 (是否可用, 说明)。说明用于打印给用户看。"""
        return False, "未实现"

    def fetch(self, task: str, code: str, name: str = "",
              timeout: int = DEFAULT_TIMEOUT) -> FetchResult:
        """取单项数据。`task` 取值见 TASK_SPECS / SEARCH_TASKS。"""
        raise NotImplementedError

    def fetch_supported(self, code: str, name: str = "",
                        timeout: int = DEFAULT_TIMEOUT) -> dict[str, FetchResult]:
        """取本源支持的全部任务（保持 TASK_SPECS 里声明的顺序）。"""
        out: dict[str, FetchResult] = {}
        for task in list(TASK_SPECS) + list(SEARCH_TASKS):
            if task in self.supports:
                out[task] = self.fetch(task, code, name, timeout)
        return out


class SearchProvider(Provider):
    """检索型数据源基类：自然语言 query → 结构化 + 文档混合结果。"""

    def search(self, query: str, data_type: str = "all",
               timeout: int = 90) -> FetchResult:
        """执行一次自然语言检索。`data_type`: all | api | doc。"""
        raise NotImplementedError

    def fetch(self, task: str, code: str, name: str = "",
              timeout: int = DEFAULT_TIMEOUT) -> FetchResult:
        """按 SEARCH_TASKS 模板把任务名展开为自然语言查询。"""
        spec = SEARCH_TASKS.get(task)
        if spec is None:
            return FetchResult(task, False, error=f"未知检索任务: {task}")
        _, template = spec
        query = template.format(name=name or code, code_plain=_plain_code(code))
        return self.search(query, timeout=timeout)


def _plain_code(code: str) -> str:
    """去掉市场前缀（sh/sz/bj/hk/us 等），保留纯数字代码。"""
    c = (code or "").lower().strip()
    for p in ("sh", "sz", "bj", "hk", "us", "t", "ks", "kq", "fu", "fx", "pt"):
        if c.startswith(p) and c[len(p):].isdigit():
            return c[len(p):]
    return c


# ---------------------------------------------------------------- 命令执行
def run_cmd(args, timeout=DEFAULT_TIMEOUT) -> tuple[bool, str]:
    """执行命令并返回 (成功, 输出)。stdout 与 stderr 合并返回。"""
    try:
        r = subprocess.run(
            args, capture_output=True, text=True, timeout=timeout, shell=False
        )
        return r.returncode == 0, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        return False, f"TIMEOUT after {timeout}s"
    except FileNotFoundError as e:
        return False, f"命令不存在: {e}"
    except OSError as e:
        return False, f"ERROR: {e}"
