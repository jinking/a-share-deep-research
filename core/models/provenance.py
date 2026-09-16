#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""来源溯源：Provider ≠ Source（v3.0.2 §8），且 Provider 永不是 Primary（v3.0.3 §7）。

为什么需要它：`westock-data` / `neodata` 这类取数服务是 **Provider**，
不是 **Source**。它们把交易所公告、行情、股东名册搬过来，但搬运本身不产生
一手性 —— 如果把它们登记成 `official_database`，它们就凭空获得了「一手来源」
资格，可以单独支撑确认级 Claim。

v3.0.2 只拦住了「未声明 upstream 就自称一手」这一种写法，于是留下一条缝：

    provider=westock-data + source_type=official_database + 随便声明一个 upstream_*
    → 放行，且 is_primary=True

「上游」因此退化成一句可以随口声明的话。v3.0.3（§7）把它焊死：

    provider 是数据服务商  →  source_type 只允许 data_vendor / third_party_database
    provider 是数据服务商  →  is_primary 恒为 False（声明上游也不行）

一手性只属于**上游那份官方原件**本身，不随搬运转移。需要表达上游关系时：

    upstream_document_id   本库中的 Document ID（必须真实存在，否则 P1 EVIDENCE_UPSTREAM_UNKNOWN）
    upstream_external_id   外部系统中的引用 ID（不在本库，不做存在性校验）
"""

from __future__ import annotations

import re
from typing import Optional

__all__ = [
    "DATA_VENDOR_PROVIDERS",
    "VENDOR_SOURCE_TYPES",
    "normalize_provider",
    "is_data_vendor_provider",
    "is_vendor_source_type_allowed",
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

# v3.0.3 §7：服务商 Document 只允许这两个来源类型。
# 二者都不在一手来源集合里 —— 这不是「暂时降级」，是它们本来的位置。
VENDOR_SOURCE_TYPES = frozenset({"data_vendor", "third_party_database"})

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


def is_vendor_source_type_allowed(source_type: Optional[str]) -> bool:
    """服务商 Document 是否用了允许的来源类型（v3.0.3 §7）。"""
    return str(source_type or "").strip() in VENDOR_SOURCE_TYPES


def default_source_type_for(provider: Optional[str], fallback: str = "data_vendor") -> str:
    """按 provider 给出**默认** source_type。

    数据服务商一律落到 `data_vendor`；未知 provider 沿用 fallback
    （调用方原本的默认值），绝不因为「看起来像官方」就升级。
    """
    if is_data_vendor_provider(provider):
        return "data_vendor"
    return fallback
