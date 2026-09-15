# -*- coding: utf-8 -*-
"""股票代码归一化（v3.0 §11.1）。"""

from __future__ import annotations

import pytest

from core.normalize import (
    StockCodeError,
    normalize_stock_code,
    split_stock_code,
    try_normalize_stock_code,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("002897", "sz002897"),          # 深主板 / 中小板
        ("300750", "sz300750"),          # 创业板
        ("600584", "sh600584"),          # 沪主板
        ("688981", "sh688981"),          # 科创板
        ("430047", "bj430047"),          # 北交所
        ("830799", "bj830799"),
        ("920819", "bj920819"),
        ("002897.SZ", "sz002897"),       # 常见后缀写法
        ("600584.SH", "sh600584"),
        ("SZ300750", "sz300750"),        # 常见前缀写法
        ("sh600584", "sh600584"),
        ("  002897  ", "sz002897"),      # 去空白
    ],
)
def test_normalize_ok(raw, expected):
    assert normalize_stock_code(raw) == expected


def test_normalize_without_exchange():
    assert normalize_stock_code("002897.SZ", with_exchange=False) == "002897"


def test_split_returns_exchange_and_digits():
    assert split_stock_code("002897.SZ") == ("sz", "002897")


def test_int_input_ok():
    assert normalize_stock_code(600584) == "sh600584"


def test_int_input_losing_leading_zero_must_fail():
    # 002897 作为 int 传入会变成 2897，位数不足必须报错，禁止静默补零猜测
    with pytest.raises(StockCodeError):
        normalize_stock_code(2897)


def test_unknown_prefix_must_raise():
    with pytest.raises(StockCodeError):
        normalize_stock_code("123456")


def test_exchange_contradiction_must_raise():
    with pytest.raises(StockCodeError):
        normalize_stock_code("002897.SH")   # 002897 属于深市
    with pytest.raises(StockCodeError):
        normalize_stock_code("BJ002897")    # 显式写成北交所，与代码段矛盾


def test_consistent_exchange_prefix_is_accepted():
    assert normalize_stock_code("SH600584") == "sh600584"
    assert normalize_stock_code("SZ002897") == "sz002897"


def test_empty_and_non_string_must_raise():
    for bad in ("", "   ", None, True, 3.14, ["002897"]):
        with pytest.raises(StockCodeError):
            normalize_stock_code(bad)


def test_try_normalize_returns_none_instead_of_raising():
    assert try_normalize_stock_code("123456") is None
    assert try_normalize_stock_code("002897") == "sz002897"
