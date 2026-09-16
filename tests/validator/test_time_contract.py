# -*- coding: utf-8 -*-
"""Schema 与 Runtime 的时间契约必须完全一致（v3.0.3 §9）。

Runtime 早已要求「声明了 `as_of` 就等于走正式 v3 时间模型，三个时点缺一不可」，
但 JSON Schema 当时只写了：

    anyOf: [required as_of, required research_date]

于是 `as_of` 单独出现、或只配一个时点，Schema 都判 PASS —— 契约两边说法不一致：
按 Schema 校验通过的东西，Runtime 会报 `TIME_MODEL_INCOMPLETE`。

v3.0.3 把 Schema 改成同一套规则：

    有 as_of → as_of + market_data_as_of + generated_at 三者齐全
    无 as_of → required research_date（旧模型兼容路径）

本文件的重点是最后那个「一致性」断言：对每一种字段组合，
**Schema 的判定必须与 Runtime 的结构判定相同** —— 只测单边都可能各自绿、
合起来矛盾。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for _p in (str(ROOT), str(ROOT / "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core.validation import validate_manifest_v3

jsonschema = pytest.importorskip("jsonschema")

SCHEMA = json.loads(
    (ROOT / "schemas" / "research_manifest.v3.schema.json").read_text(encoding="utf-8")
)
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "valid" / "manifest_v3_new_time.json"

AS_OF = "2026-09-15T09:00:00+08:00"
MARKET_AS_OF = "2026-09-14T15:00:00+08:00"
GENERATED_AT = "2026-09-15T09:05:32+08:00"

# 除时间字段外的必需 meta
BASE_META = {
    "company": "测试公司",
    "code": "002897.SZ",
    "current_price": 71.39,
    "shares_billion": 1.9386,
    "market_cap_billion": 138.4,
    "evidence_dir": "evidence",
}

# 结构性问题（Schema / Runtime 都该拦下的那两类）
STRUCTURAL_CODES = {"MANIFEST_V3_STRUCTURE", "TIME_MODEL_INCOMPLETE"}


def _manifest(time_fields):
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    meta = dict(BASE_META)
    meta.update(time_fields)
    data["meta"] = meta
    return data


def _schema_ok(data):
    validator_cls = jsonschema.validators.validator_for(SCHEMA)
    validator_cls.check_schema(SCHEMA)
    try:
        validator_cls(SCHEMA).validate(data)
    except jsonschema.ValidationError:
        return False
    return True


def _runtime_structural_codes(data):
    codes = []
    validate_manifest_v3(data, emit=lambda s, c, m, d="": codes.append(c))
    return [c for c in codes if c in STRUCTURAL_CODES]


# (名称, 时间字段, Schema 期望)
COMBOS = [
    ("legacy_research_date_only", {"research_date": "2026-09-14"}, True),
    ("as_of_only", {"as_of": AS_OF}, False),
    ("as_of_plus_generated_at", {"as_of": AS_OF, "generated_at": GENERATED_AT}, False),
    ("as_of_plus_market_data_as_of", {"as_of": AS_OF, "market_data_as_of": MARKET_AS_OF}, False),
    (
        "formal_complete",
        {
            "as_of": AS_OF,
            "market_data_as_of": MARKET_AS_OF,
            "generated_at": GENERATED_AT,
        },
        True,
    ),
    (
        "formal_malformed_as_of",
        {
            "as_of": "2026-09-15 09:00 左右",
            "market_data_as_of": MARKET_AS_OF,
            "generated_at": GENERATED_AT,
        },
        False,
    ),
    (
        "formal_malformed_market_data_as_of",
        {
            "as_of": AS_OF,
            "market_data_as_of": "昨天下午收盘",
            "generated_at": GENERATED_AT,
        },
        False,
    ),
    (
        "formal_malformed_generated_at",
        {
            "as_of": AS_OF,
            "market_data_as_of": MARKET_AS_OF,
            "generated_at": "刚刚",
        },
        False,
    ),
    (
        "formal_all_malformed",
        {"as_of": "x", "market_data_as_of": "y", "generated_at": "z"},
        False,
    ),
]


# --------------------------------------------------------------------------- #
# Schema 侧：六类组合的判定
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("name,fields,expected", COMBOS, ids=[c[0] for c in COMBOS])
def test_schema_time_contract(name, fields, expected):
    assert _schema_ok(_manifest(fields)) is expected, name


def test_schema_still_accepts_legacy_only():
    """旧模型兼容路径不能因为收严而断掉：只有 research_date 仍然 PASS。"""
    data = _manifest({"research_date": "2026-09-14"})
    assert _schema_ok(data) is True
    # 且 Runtime 只提示 P2 兼容，不当结构错误
    assert _runtime_structural_codes(data) == []


def test_schema_requires_research_date_when_as_of_absent():
    data = _manifest({})
    assert _schema_ok(data) is False


# --------------------------------------------------------------------------- #
# 一致性：Schema 说了算的地方，Runtime 必须同一答案（v3.0.3 §9 的核心）
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("name,fields,expected", COMBOS, ids=[c[0] for c in COMBOS])
def test_schema_and_runtime_agree(name, fields, expected):
    data = _manifest(fields)
    schema_ok = _schema_ok(data)
    runtime_ok = not _runtime_structural_codes(data)
    assert schema_ok == expected and runtime_ok == expected, (
        f"{name}: schema_ok={schema_ok} runtime_ok={runtime_ok} expected={expected}"
    )


@pytest.mark.parametrize("name,fields,expected", COMBOS, ids=[c[0] for c in COMBOS])
def test_schema_and_runtime_agree_on_rejection(name, fields, expected):
    """被拒的组合，两边都必须给出**结构化**的拒绝理由，而不是沉默。"""
    data = _manifest(fields)
    if expected:
        return
    assert _schema_ok(data) is False
    assert _runtime_structural_codes(data), f"{name}: Runtime 没有报结构错误"


# --------------------------------------------------------------------------- #
# 样例清单本身必须落在契约允许的形态里
# --------------------------------------------------------------------------- #


# 精简副本（例如技能安装目录）不带 examples/，用 skipif 逐条跳过 ——
# 不是 `assert is_file()`：那会把「没随包分发」变成 4 条看起来像故障的红。
_SAMPLE_MANIFESTS = [
    "examples/意华股份002897_样板/research_manifest.v3.json",
    "examples/invalid/意华股份002897_旧结论漂移样板/research_manifest.v3.json",
]


@pytest.mark.parametrize(
    "path",
    [
        pytest.param(
            p,
            marks=pytest.mark.skipif(
                not (ROOT / p).is_file(), reason=f"缺少样板 {p}（examples/ 未随包分发）"
            ),
        )
        for p in _SAMPLE_MANIFESTS
    ],
)
def test_sample_manifests_match_schema(path):
    data = json.loads((ROOT / path).read_text(encoding="utf-8"))
    assert _schema_ok(data) is True, path
    assert _runtime_structural_codes(data) == [], path
