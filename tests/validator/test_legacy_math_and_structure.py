# -*- coding: utf-8 -*-
"""存量 Validator 的数学与结构规则回归（v3.0 §9.1 A/B）。

这些用例直接调用 scripts/validate_report.py 中的既有校验函数，
目的是给 v3.0 改造加一层「不许打破旧能力」的护栏。
"""

from __future__ import annotations

import copy

import pytest

from helpers import minimal_report_html, report_error_codes, run_legacy_manifest_validator, valid_manifest


def mutate(**changes):
    data = copy.deepcopy(valid_manifest())
    for path, value in changes.items():
        node = data
        keys = path.split(".")
        for key in keys[:-1]:
            node = node[key]
        node[keys[-1]] = value
    return data


# --------------------------------------------------------------------------- #
# B. Math
# --------------------------------------------------------------------------- #


def test_baseline_manifest_is_clean():
    assert run_legacy_manifest_validator(valid_manifest()) == []


def test_eps_times_shares_mismatch():
    data = mutate()
    data["forecast"]["中性"][0]["eps"] = 9.99
    assert "MATH_EPS" in run_legacy_manifest_validator(data)


def test_price_times_shares_mismatch():
    data = mutate()
    data["meta"]["market_cap_billion"] = 999.0
    assert "MATH_MARKET_CAP" in run_legacy_manifest_validator(data)


def test_missing_shares_is_p0():
    data = mutate()
    data["meta"]["shares_billion"] = 0
    assert "META_SHARES" in run_legacy_manifest_validator(data)


def test_two_scenarios_only():
    data = mutate()
    data["forecast"].pop("悲观")
    assert "MANIFEST_SCENARIO" in run_legacy_manifest_validator(data)


def test_forecast_two_years_only():
    data = mutate()
    data["forecast"]["中性"] = data["forecast"]["中性"][:2]
    assert "MANIFEST_3X3" in run_legacy_manifest_validator(data)


def test_forecast_years_not_contiguous():
    data = mutate()
    for scenario in ("悲观", "中性", "乐观"):
        data["forecast"][scenario][2]["year"] = 2029
        data["forecast"][scenario][2]["eps"] = round(
            data["forecast"][scenario][2]["net_profit_billion"] / 1.9386, 2
        )
    assert "MANIFEST_YEAR_CONTIG" in run_legacy_manifest_validator(data)


def test_all_zero_forecast_is_placeholder():
    data = mutate()
    for rows in data["forecast"].values():
        for row in rows:
            row["revenue_billion"] = row["net_profit_billion"] = row["eps"] = 0.0
    assert "FORECAST_PLACEHOLDER" in run_legacy_manifest_validator(data)


def test_valuation_linked_metric_mismatch():
    data = mutate()
    data["valuation"]["linked_value"] = 5.0
    data["valuation"]["equity_value_billion"] = 175.0
    data["valuation"]["price_per_share"] = 90.3
    assert "VAL_METRIC_MISMATCH" in run_legacy_manifest_validator(data)


def test_valuation_multiplication_mismatch():
    data = mutate()
    data["valuation"]["equity_value_billion"] = 999.0
    assert "MATH_VALUATION" in run_legacy_manifest_validator(data)


def test_target_price_mismatch():
    data = mutate()
    data["valuation"]["price_per_share"] = 999.0
    assert "MATH_TARGET_PRICE" in run_legacy_manifest_validator(data)


def test_valuation_target_year_not_in_forecast():
    data = mutate()
    data["valuation"]["target_year"] = 2030
    assert "VAL_FORECAST_LINK" in run_legacy_manifest_validator(data)


def test_sotp_parts_sum_mismatch():
    data = mutate()
    data["sotp"]["total_equity_value_billion"] = 200.0
    assert "SOTP_VALUE_SUM" in run_legacy_manifest_validator(data)


def test_sotp_profit_sum_mismatch():
    data = mutate()
    data["sotp"]["reconciled_total_net_profit_billion"] = 9.9
    assert "SOTP_PROFIT_SUM" in run_legacy_manifest_validator(data)


def test_sotp_profit_year_mismatch_with_forecast():
    data = mutate()
    data["sotp"]["reconciled_total_net_profit_billion"] = 2.0
    assert "SOTP_FORECAST_MISMATCH" in run_legacy_manifest_validator(data)


def test_confirmed_level_with_low_grade_source():
    data = mutate()
    row = data["evidence"][0]
    row["level"] = "已确认订单"
    row["source_type"] = "media"
    assert "EVIDENCE_UPGRADE" in run_legacy_manifest_validator(data)


def test_tracking_count_out_of_range():
    data = mutate()
    data["quarterly_tracking"] = data["quarterly_tracking"][:9]
    assert "TRACKING_COUNT" in run_legacy_manifest_validator(data)


def test_final_status_invalid():
    data = mutate()
    data["final"]["status"] = "买买买"
    assert "FINAL_STATUS" in run_legacy_manifest_validator(data)


def test_final_invalidation_too_few():
    data = mutate()
    data["final"]["core_invalidation"] = ["只有一条"]
    assert "FINAL_INVALIDATION" in run_legacy_manifest_validator(data)


# --------------------------------------------------------------------------- #
# A. Structure（报告侧）
# --------------------------------------------------------------------------- #


def test_valid_report_structure_passes(tmp_path):
    assert report_error_codes(tmp_path, minimal_report_html()) == []


def test_missing_chapter_is_p0(tmp_path):
    html = minimal_report_html(chapters=[i for i in range(17) if i != 10])
    assert "STRUCT_CHAPTERS" in report_error_codes(tmp_path, html)


def test_missing_scenario_is_p0(tmp_path):
    html = minimal_report_html(scenarios=("悲观", "中性"))
    assert "FORECAST_SCENARIOS" in report_error_codes(tmp_path, html)


def test_two_forecast_years_is_p0(tmp_path):
    html = minimal_report_html(years=(2026, 2027))
    assert "FORECAST_YEARS" in report_error_codes(tmp_path, html)


@pytest.mark.parametrize("rows", [9, 16])
def test_tracker_rows_out_of_range(tmp_path, rows):
    html = minimal_report_html(tracker_rows=rows)
    assert "TRACKER_ROWS" in report_error_codes(tmp_path, html)


def test_missing_invalidation_section_is_p1(tmp_path):
    html = minimal_report_html(phrases=("当前价格隐含", "条件树"))
    assert "REQUIRED_ANALYSIS" in report_error_codes(tmp_path, html)


def test_missing_evidence_labels_is_p1(tmp_path):
    html = minimal_report_html(labels=("事实", "推断"))
    assert "EVIDENCE_LABELS" in report_error_codes(tmp_path, html)
