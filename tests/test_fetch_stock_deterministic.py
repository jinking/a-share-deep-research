#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sprint 5：fetch_stock.py 中确定性逻辑的离线单测（v3.0 §11 / §17 DoD）。

覆盖：
- 股票代码归一化（入口不再静默兜底）
- K 线可用性校验（行数 / 日期 / 收盘价）
- K 线自动回退（主源达标则不回退；不达标则回退并写回）

全部为纯函数或注入了 runner 的测试，**不需要联网**。
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT), str(ROOT / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core.normalize import StockCodeError, normalize_stock_code  # noqa: E402
from fetch_stock import (  # noqa: E402
    KLINE_MIN_ROWS,
    fetch_kline_with_fallback,
    validate_kline_text,
)


def kline_md(n: int, *, last_day: str = "2026-09-14", bad_rows: int = 0) -> str:
    """造一段标准 md 表格形式的日 K。bad_rows 指定末尾插入几行脏数据。"""
    lines = [
        "| date | open | last | high | low | volume | amount | exchange |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    end = date.fromisoformat(last_day)
    for i in range(n):
        d = end - timedelta(days=i)
        lines.append(f"| {d.isoformat()} | 63.99 | {70.0 + i * 0.01:.2f} | 71.39 | 61.04 | 244364 | 1621049895 | 13.25 |")
    for i in range(bad_rows):
        lines.append(f"| 2026/09/{i + 1:02d} | 1 | abc | 1 | 1 | 1 | 1 | 1 |")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- 代码归一化


def test_entry_normalizes_supported_forms():
    assert normalize_stock_code("002897") == "sz002897"
    assert normalize_stock_code("002897.SZ") == "sz002897"
    assert normalize_stock_code("SZ002897") == "sz002897"
    assert normalize_stock_code("600584") == "sh600584"
    assert normalize_stock_code("688981") == "sh688981"
    assert normalize_stock_code("300750") == "sz300750"
    assert normalize_stock_code("430047") == "bj430047"
    assert normalize_stock_code("920819") == "bj920819"


def test_entry_rejects_undecidable_code():
    for bad in ("999999", "12345", ""):
        with pytest.raises(StockCodeError):
            normalize_stock_code(bad)


# ---------------------------------------------------------------- K 线校验


def test_validate_kline_ok():
    ok, rows, why = validate_kline_text(kline_md(60))
    assert ok
    assert len(rows) == 60
    assert rows[0]["date"] == "2026-09-14"
    assert why == "OK"


def test_validate_kline_requires_minimum_rows():
    ok, rows, why = validate_kline_text(kline_md(KLINE_MIN_ROWS - 1))
    assert not ok
    assert "最低要求" in why
    assert len(rows) == KLINE_MIN_ROWS - 1


def test_validate_kline_skips_bad_rows_but_still_passes():
    ok, rows, why = validate_kline_text(kline_md(50, bad_rows=3))
    assert ok
    assert len(rows) == 50
    assert "跳过" in why


def test_validate_kline_empty_text():
    ok, rows, why = validate_kline_text("")
    assert not ok
    assert rows == []


# ---------------------------------------------------------------- K 线回退


def make_outdir(tmp_path: Path, text: str = "") -> Path:
    raw = tmp_path / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    if text:
        (raw / "kline.txt").write_text(text, encoding="utf-8")
    return tmp_path


def test_main_source_ok_never_calls_fallback(tmp_path):
    outdir = make_outdir(tmp_path, kline_md(60))
    calls = []

    def runner(code, *, limit=62):
        calls.append(code)
        return ""

    ok, note, n = fetch_kline_with_fallback("sz002897", outdir, runner=runner)
    assert ok and n == 60
    assert "主源可用" in note
    assert calls == []


def test_fallback_rescues_empty_main_source(tmp_path):
    outdir = make_outdir(tmp_path, "")  # 主源取空（raw/kline.txt 不存在）
    ok, note, n = fetch_kline_with_fallback(
        "sz002897", outdir, runner=lambda code, *, limit=62: kline_md(50)
    )
    assert ok and n == 50
    assert "fallback 成功" in note
    written = (outdir / "raw" / "kline.txt").read_text(encoding="utf-8")
    assert written.count("| 2026-") >= 50


def test_fallback_rejects_still_bad_data(tmp_path):
    outdir = make_outdir(tmp_path, "")
    ok, note, n = fetch_kline_with_fallback(
        "sz002897", outdir, runner=lambda code, *, limit=62: kline_md(3)
    )
    assert not ok
    assert "fallback 仍不达标" in note


def test_fallback_unavailable_marks_failure(tmp_path):
    outdir = make_outdir(tmp_path, "")
    ok, note, n = fetch_kline_with_fallback(
        "sz002897", outdir, runner=lambda code, *, limit=62: ""
    )
    assert not ok
    assert n == 0
    # 码由调用方（main）追加：此处只保证返回失败，不会静默当成成功
    assert "未返回数据" in note
