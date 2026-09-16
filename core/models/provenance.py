#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""来源溯源：Provider ≠ Source（v3.0.2 §8）。

为什么需要它：`westock-data` / `neodata` 这类取数服务是 **Provider**，
不是 **Source**。它们把交易所公告、行情、股东名册搬过来，但搬运本身不产生
一手性 —— 如果把它们登记成 `official_database`，它们就凭空获得了「一手来源」
资格，可以单独支撑确认级 Claim。

本模块把这条判断收敛成一个纯数据 + 纯函数的地方，任何人不得再各自硬编码：

    provider = "westock-data(kline)"   →  是数据服务商
    source_type = "official_database"  →  自称一手来源
    且没有声明 upstream_*              →  非法（见 SourceDocument.validate）

只有明确声明了上游官方原件（`upstream_source_type` / `upstream_document_id`）
时，才允许把 `source_type` 写成一手来源类型。
"""

from __future__ import annotations

import re
from typing import Optional

__all__ = [
    "DATA_VENDOR_PROVIDERS",
    "normalize_provider",
    "is_data_vendor_provider",
    "default_source_type_for",
]

# 数据服务商（Provider）白名单：这些名字永远不构成「一手来源」。
# 只收录确实在用的；新增必须说明上游，否则不如不加。
DATA_VENDOR_PROVIDERS = frozenset(
    {
        "westock-data",
        "westock",
        "neodata",
    }
)

# provider 常见的写法是 "westock-data(kline)" / "westock-data (dividend)"，
# 统一剥掉括号后缀再判断。
_PARENTHETICAL_RE = re.compile(r"[\s(（].*$")


def normalize_provider(provider: Optional[str]) -> str:
    """把 provider 归一化成小写主体名（用于比较，不做任何猜测）。"""
    text = str(provider or "").strip().lower()
    if not text:
        return ""
    text = _PARENTHETICAL_RE.sub("", text)
    return text.strip()


def is_data_vendor_provider(provider: Optional[str]) -> bool:
    """该 provider 是否是数据服务商（因此不构成一手来源）。"""
    return normalize_provider(provider) in DATA_VENDOR_PROVIDERS


def default_source_type_for(provider: Optional[str], fallback: str = "data_vendor") -> str:
    """按 provider 给出**默认** source_type。

    数据服务商一律落到 `data_vendor`；未知 provider 沿用 fallback
    （调用方原本的默认值），绝不因为「看起来像官方」就升级。
    """
    if is_data_vendor_provider(provider):
        return "data_vendor"
    return fallback
