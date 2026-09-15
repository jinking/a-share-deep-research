#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""取数 provider 注册表（WorkBuddy 专用版）。

三个数据源按「能力分组」注册，主流程按组取数、互不干扰：

    REGISTRY
      ├─ westock-npm  →  core     （结构化主源，默认必用）
      ├─ westock-cli  →  enhanced （资讯面增强，装上才用）
      └─ neodata      →  search   （语义检索，凭证有效才用）

新增数据源：写一个 Provider / SearchProvider 子类，加进 REGISTRY 即可。
"""

from __future__ import annotations

from .base import (
    DEFAULT_TIMEOUT,
    SEARCH_TASKS,
    TASK_SPECS,
    FetchResult,
    Provider,
    SearchProvider,
    run_cmd,
)
from .neodata import NeodataProvider
from .westock_cli import WestockCliProvider
from .westock_npm import WestockNpmProvider

# 注册顺序即同组内的优先顺序：靠前的先试
REGISTRY: dict[str, type[Provider]] = {
    WestockNpmProvider.name: WestockNpmProvider,
    WestockCliProvider.name: WestockCliProvider,
    NeodataProvider.name: NeodataProvider,
}

__all__ = [
    "Provider",
    "SearchProvider",
    "FetchResult",
    "TASK_SPECS",
    "SEARCH_TASKS",
    "DEFAULT_TIMEOUT",
    "run_cmd",
    "REGISTRY",
    "group_of",
    "list_providers",
    "probe",
    "providers_for",
    "first_for",
]


def group_of(task: str) -> str | None:
    """任务属于哪个分组：core / enhanced / search。"""
    spec = TASK_SPECS.get(task)
    if spec is not None:
        return spec[2]
    if task in SEARCH_TASKS:
        return "search"
    return None


def list_providers() -> list[tuple[str, str, str]]:
    """列出全部已注册数据源 (名称, 说明, 支持分组)。"""
    out = []
    for cls in REGISTRY.values():
        groups = "、".join(sorted({g for g in (group_of(t) for t in cls.supports) if g}))
        out.append((cls.name, cls.desc, groups or "-"))
    return out


def probe(name: str):
    """构造并探测单个数据源。可用返回实例，否则返回 (None, 原因)。"""
    cls = REGISTRY.get(name)
    if cls is None:
        return None, f"未注册的数据源: {name}"
    p = cls()
    try:
        ok, why = p.available()
    except Exception as e:  # noqa: BLE001
        return None, f"探测异常: {e}"
    return (p, "") if ok else (None, why)


def providers_for(group: str, preferred: str = "") -> list[Provider]:
    """返回能承担指定分组、且当前可用的所有 provider（指定 preferred 时只返回它）。"""
    if preferred:
        p, _ = probe(preferred)
        if p and any(group_of(t) == group for t in p.supports):
            return [p]
        return []

    out: list[Provider] = []
    for cls in REGISTRY.values():
        if not any(group_of(t) == group for t in cls.supports):
            continue
        p, _ = probe(cls.name)
        if p is not None:
            out.append(p)
    return out


def first_for(group: str, preferred: str = ""):
    """返回指定分组下首个可用 provider（无则 None）。"""
    lst = providers_for(group, preferred=preferred)
    return lst[0] if lst else None
