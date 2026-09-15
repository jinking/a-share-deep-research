# -*- coding: utf-8 -*-
"""研究时间模型（v3.0.1 §4）：as_of / market_data_as_of / generated_at。

一个 research_date 曾同时隐含「数据截止日 / 研究基准日 / 行情截止日 / 报告生成日」，
导致无法判定「某条证据是否超出研究时点」。这里把三种时点各自的语义与错误码钉死。
"""

from __future__ import annotations

import copy

import pytest

from core.issue import Issue
from core.validation import (
    TIME_FIELDS,
    build_time_model,
    validate_evidence,
    validate_manifest_v3,
)
from helpers import RESEARCH_DATE, base_state, legacy_module, valid_manifest, valid_manifest_v3

AS_OF = "2026-09-15T09:00:00+08:00"
MARKET_AS_OF = "2026-09-14T15:00:00+08:00"
GENERATED_AT = "2026-09-15T09:05:32+08:00"


def _issues(state, **kwargs):
    bucket = []
    validate_evidence(
        state,
        emit=lambda s, c, m, d="": bucket.append(Issue(s, c, m, d)),
        **kwargs,
    )
    return bucket


def _codes(state, **kwargs):
    return [i.code for i in _issues(state, **kwargs)]


def _manifest_issues(data):
    bucket = []
    validate_manifest_v3(data, emit=lambda s, c, m, d="": bucket.append(Issue(s, c, m, d)))
    return bucket


def _manifest_with_time(**overrides):
    """v3 manifest 换成新时间模型。"""
    data = copy.deepcopy(valid_manifest_v3())
    meta = data["meta"]
    meta["as_of"] = AS_OF
    meta["market_data_as_of"] = MARKET_AS_OF
    meta["generated_at"] = GENERATED_AT
    meta.update(overrides)
    return data


# --------------------------------------------------------------------------- #
# 模型解析
# --------------------------------------------------------------------------- #


def test_build_time_model_parses_new_fields():
    model = build_time_model(
        {"as_of": AS_OF, "market_data_as_of": MARKET_AS_OF, "generated_at": GENERATED_AT}
    )
    assert model.is_new_model and not model.is_legacy
    assert model.info_cutoff.isoformat() == "2026-09-15"
    assert model.market_data_as_of < model.generated_at
    assert set(TIME_FIELDS) == {"as_of", "market_data_as_of", "generated_at"}


def test_build_time_model_legacy_cutoff_falls_back_to_research_date():
    model = build_time_model({"research_date": RESEARCH_DATE})
    assert model.is_legacy and not model.is_new_model
    assert model.info_cutoff.isoformat() == RESEARCH_DATE


# --------------------------------------------------------------------------- #
# §4 必测 Case：Evidence 时效
# --------------------------------------------------------------------------- #


def test_evidence_before_as_of_passes():
    state = base_state()  # 证据发布日期为 2026-08-25 / 2026-09-14
    codes = _codes(state, research_date=None, as_of=AS_OF)
    assert "SOURCE_DATE_AFTER_AS_OF" not in codes
    assert "SOURCE_DATE_AFTER_RESEARCH_DATE" not in codes


def test_evidence_equal_as_of_passes():
    """published_at == as_of 属于边界内，不算超时。"""
    state = base_state()
    codes = _codes(state, research_date=None, as_of="2026-09-14T00:00:00+08:00")
    assert "SOURCE_DATE_AFTER_AS_OF" not in codes


def test_evidence_after_as_of_is_p1():
    state = base_state()
    issues = _issues(state, research_date=None, as_of="2026-09-13T09:00:00+08:00")
    hit = [i for i in issues if i.code == "SOURCE_DATE_AFTER_AS_OF"]
    assert hit and hit[0].severity == "P1"
    assert "as_of=" in hit[0].detail
    # 新模型下不再使用旧错误码，避免两条语义重复的结论同时出现
    assert "SOURCE_DATE_AFTER_RESEARCH_DATE" not in [i.code for i in issues]


def test_as_of_wins_over_research_date():
    """同时给出时，时效判定以 as_of 为准。"""
    state = base_state()
    codes = _codes(state, research_date="2026-09-13", as_of=AS_OF)
    assert "SOURCE_DATE_AFTER_AS_OF" not in codes
    assert "SOURCE_DATE_AFTER_RESEARCH_DATE" not in codes


def test_legacy_research_date_still_reports_old_code():
    """v2 / 旧 v3 行为不变：仍报 SOURCE_DATE_AFTER_RESEARCH_DATE。"""
    state = base_state()
    issues = _issues(state, research_date="2026-09-13")
    hit = [i for i in issues if i.code == "SOURCE_DATE_AFTER_RESEARCH_DATE"]
    assert hit and hit[0].severity == "P1"
    assert "SOURCE_DATE_AFTER_AS_OF" not in [i.code for i in issues]


# --------------------------------------------------------------------------- #
# §4 必测 Case：三个时点之间的关系
# --------------------------------------------------------------------------- #


def test_generated_at_after_as_of_passes():
    issues = _manifest_issues(_manifest_with_time())
    assert [i.code for i in issues if i.severity in {"P0", "P1"}] == []
    assert "TIME_MODEL_LEGACY" not in [i.code for i in issues]


def test_market_data_as_of_before_generated_at_passes():
    issues = _manifest_issues(_manifest_with_time())
    assert "MARKET_DATA_AFTER_GENERATED_AT" not in [i.code for i in issues]


def test_market_data_as_of_after_generated_at_is_p1():
    data = _manifest_with_time(market_data_as_of="2026-09-15T18:00:00+08:00")
    issues = _manifest_issues(data)
    hit = [i for i in issues if i.code == "MARKET_DATA_AFTER_GENERATED_AT"]
    assert hit and hit[0].severity == "P1"


def test_market_data_as_of_equal_generated_at_passes():
    """同一时刻不算倒挂。"""
    data = _manifest_with_time(market_data_as_of=GENERATED_AT)
    assert "MARKET_DATA_AFTER_GENERATED_AT" not in [i.code for i in _manifest_issues(data)]


# --------------------------------------------------------------------------- #
# §4 必测 Case：向后兼容
# --------------------------------------------------------------------------- #


def test_research_date_only_is_legacy_p2():
    issues = _manifest_issues(valid_manifest_v3())
    hit = [i for i in issues if i.code == "TIME_MODEL_LEGACY"]
    assert hit and hit[0].severity == "P2"
    # P2 不阻断：不得因此产生 P0/P1
    assert [i.code for i in issues if i.severity in {"P0", "P1"}] == []


def test_v2_manifest_behaviour_unchanged():
    """v2 只报一条 INFO，不掺入任何时间模型结论。"""
    issues = _manifest_issues(valid_manifest())
    assert [(i.severity, i.code) for i in issues] == [("INFO", "MANIFEST_V2_COMPAT")]


def test_missing_both_time_anchors_is_structure_error():
    data = valid_manifest_v3()
    data["meta"].pop("research_date")
    hit = [i for i in _manifest_issues(data) if i.code == "MANIFEST_V3_STRUCTURE"]
    assert hit and hit[0].severity == "P1"


def test_malformed_time_field_is_structure_error():
    data = _manifest_with_time(as_of="2026年9月15日")
    hit = [i for i in _manifest_issues(data) if i.code == "MANIFEST_V3_STRUCTURE"]
    assert hit and hit[0].severity == "P1" and "as_of" in hit[0].message


@pytest.mark.parametrize("missing", ["market_data_as_of", "generated_at"])
def test_partial_new_time_model_is_tolerated(missing):
    """缺 market_data_as_of / generated_at：不算旧模型，也不报结构错误。"""
    data = _manifest_with_time()
    data["meta"].pop(missing)
    codes = [i.code for i in _manifest_issues(data)]
    assert "MANIFEST_V3_STRUCTURE" not in codes
    assert "TIME_MODEL_LEGACY" not in codes


def test_missing_as_of_but_has_research_date_falls_back_to_legacy():
    """as_of 缺失而 research_date 仍在 → 确实是旧模型，报 P2 而不是结构错误。"""
    data = _manifest_with_time()
    data["meta"].pop("as_of")
    codes = [i.code for i in _manifest_issues(data)]
    assert "TIME_MODEL_LEGACY" in codes
    assert "MANIFEST_V3_STRUCTURE" not in codes
