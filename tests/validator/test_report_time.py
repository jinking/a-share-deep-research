# -*- coding: utf-8 -*-
"""报告层时间一致性：manifest.generated_at ↔ 报告内时间戳 ↔ 文件名（v3.0.1 §4）。"""

from __future__ import annotations

import copy

import pytest

from helpers import legacy_module

GENERATED_AT = "2026-09-15T09:05:32+08:00"
REPORT_TS = "2026-09-15 09:05:32"


def _report_html(*timestamps: str) -> str:
    parts = ["<html><head>"]
    for ts in timestamps:
        parts.append(f"<title>意华股份（002897）｜ 生成于 {ts}</title>")
    parts.append("</head><body>")
    parts.append("<h1>意华股份<small>生成于 2026-09-15 09:05:32</small></h1>")
    for ts in timestamps:
        parts.append(f"<!-- 报告生成时间：{ts} -->")
    parts.append("</body></html>")
    return "".join(parts)


def _run(tmp_path, *, filename: str, html: str, generated_at=GENERATED_AT):
    module = legacy_module()
    report = tmp_path / filename
    report.write_text(html, encoding="utf-8")
    manifest = {"manifest_version": 3, "meta": {"generated_at": generated_at}}
    findings = []
    module.validate_generated_at(report, html, manifest, findings)
    return [f for f in findings if f.code == "GENERATED_AT_MISMATCH"]


def test_consistent_generated_at_passes(tmp_path):
    hit = _run(
        tmp_path,
        filename="意华股份002897_深度研究_20260915_090532.html",
        html=_report_html(REPORT_TS),
    )
    assert hit == []


def test_filename_timestamp_mismatch_is_p1(tmp_path):
    hit = _run(
        tmp_path,
        filename="意华股份002897_深度研究_20260915_120000.html",
        html=_report_html(REPORT_TS),
    )
    assert hit and hit[0].severity == "P1" and "文件名" in hit[0].message


def test_filename_without_timestamp_is_p1(tmp_path):
    hit = _run(tmp_path, filename="意华股份002897_深度研究.html", html=_report_html(REPORT_TS))
    assert hit and "文件名" in hit[0].message


def test_report_body_timestamp_mismatch_is_p1(tmp_path):
    hit = _run(
        tmp_path,
        filename="意华股份002897_深度研究_20260915_090532.html",
        html=_report_html("2026-09-15 11:00:00"),
    )
    assert hit and "报告内生成时间" in hit[0].message


def test_report_without_any_timestamp_is_p1(tmp_path):
    """manifest 声明了 generated_at，报告却没承载它——正是要消除的歧义。"""
    hit = _run(
        tmp_path,
        filename="意华股份002897_深度研究_20260915_090532.html",
        html="<html><body><h1>意华股份</h1></body></html>",
    )
    assert hit and "没有可校验的生成时间戳" in hit[0].message


def test_multiple_inconsistent_timestamps_all_reported(tmp_path):
    hit = _run(
        tmp_path,
        filename="意华股份002897_深度研究_20260915_090532.html",
        html=_report_html(REPORT_TS, "2026-09-15 08:00:00"),
    )
    assert hit and "2026-09-15 08:00:00" in hit[0].detail


def test_missing_generated_at_skips_check(tmp_path):
    """v2 / 旧 v3 没有 generated_at → 完全不检查，行为零变化。"""
    module = legacy_module()
    report = tmp_path / "任意名字.html"
    html = "<html><body><h1>旧报告</h1></body></html>"
    report.write_text(html, encoding="utf-8")
    findings = []
    module.validate_generated_at(report, html, {"meta": {"research_date": "2026-09-14"}}, findings)
    assert findings == []
