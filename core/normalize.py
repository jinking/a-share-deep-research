#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""股票代码归一化（v3.0 §11.1）。

把「如何判断代码前缀」这类确定性逻辑从 SKILL.md 下沉到代码。

规则：
    60 / 68 开头        -> sh
    00 / 30 开头        -> sz
    4 / 8 / 92 开头     -> bj（北交所）
    其他                -> raise StockCodeError（禁止 silent failure）

支持的历史写法：
    002897 / sz002897 / SZ002897 / 002897.SZ / SZ.002897
"""

from __future__ import annotations

import re
from typing import Tuple

__all__ = [
    "StockCodeError",
    "normalize_stock_code",
    "split_stock_code",
    "try_normalize_stock_code",
]

_FORM_RE = re.compile(
    r"^(?:(?P<pre>SH|SZ|BJ)\.?)?(?P<digits>\d{6})(?:\.(?P<suf>SH|SZ|BJ))?$",
    re.IGNORECASE,
)
_EXCHANGES = ("sh", "sz", "bj")


class StockCodeError(ValueError):
    """无法归一化股票代码（输入非法或存在交易所矛盾）。"""


def _raw_digits(code) -> str:
    if isinstance(code, bool):
        raise StockCodeError("股票代码不能为 bool")
    if isinstance(code, int):
        text = str(code)
    elif isinstance(code, str):
        text = code.strip()
    else:
        raise StockCodeError(f"不支持的股票代码类型: {type(code).__name__}")
    if not text:
        raise StockCodeError("股票代码为空")
    if text.isdigit() and len(text) != 6:
        # 例如把 002897 当成 int 传入后变成 2897，属于信息丢失，必须显式报错。
        raise StockCodeError(
            f"股票代码位数不是 6 位: {text!r}（若原始带前导零，请以字符串传入）"
        )
    return text


def _exchange_from_digits(digits: str) -> str:
    if digits[:2] in {"60", "68"}:
        return "sh"
    if digits[:2] in {"00", "30"}:
        return "sz"
    if digits[0] in {"4", "8"} or digits[:2] == "92":
        return "bj"
    raise StockCodeError(f"无法判断交易所前缀（不接受猜测）: {digits}")


def split_stock_code(code) -> Tuple[str, str]:
    """返回 (exchange, digits)，例如 ('sz', '002897')。"""
    text = _raw_digits(code)
    m = _FORM_RE.match(text)
    if not m:
        raise StockCodeError(f"无法解析股票代码: {code!r}")
    digits = m.group("digits")
    derived = _exchange_from_digits(digits)
    declared = m.group("pre") or m.group("suf")
    if declared:
        declared = declared.lower()
        if declared not in _EXCHANGES:
            raise StockCodeError(f"未知交易所标识: {declared!r}")
        if declared != derived:
            raise StockCodeError(
                f"股票代码与交易所标识矛盾: {text!r} 按代码段应为 {derived.upper()}，但显式写为 {declared.upper()}"
            )
    return derived, digits


def normalize_stock_code(code, *, with_exchange: bool = True) -> str:
    """归一化股票代码。

    >>> normalize_stock_code("002897")
    'sz002897'
    >>> normalize_stock_code("600584")
    'sh600584'
    >>> normalize_stock_code("430047")
    'bj430047'
    >>> normalize_stock_code("002897.SZ", with_exchange=False)
    '002897'
    """
    exchange, digits = split_stock_code(code)
    return f"{exchange}{digits}" if with_exchange else digits


def try_normalize_stock_code(code, *, with_exchange: bool = True):
    """宽松版本：失败返回 None，仅用于探测/展示场景，不得用于正式取数。"""
    try:
        return normalize_stock_code(code, with_exchange=with_exchange)
    except StockCodeError:
        return None
