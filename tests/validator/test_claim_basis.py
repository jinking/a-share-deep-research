# -*- coding: utf-8 -*-
"""Claim 粒度与依据规则（v3.0.1 §8 Task 5 / §9 Task 6）。

背景：Golden Sample 里曾把「收盘价 + 总市值 + PE(TTM)」塞进同一个 Claim。
三件事的事实等级完全不同：

    收盘价  事实（行情数据）
    总市值  推导（收盘价 × 股本）
    PE(TTM) 未确认（缺可靠 TTM 口径）

一个 Claim 混装三种等级，等于让最弱的那一环拖垮整个结论的可信度。
所以 §8 要求拆开，并要求 validator 能识别两类结构性错误：

    fact      不能建立在不确认的推导之上
    unconfirmed 不能被标成 supported

再加上 §9 的 CLAIM_BASIS_UNKNOWN：依据本身必须真实存在。
本文件把这几条固定下来，同时为 §9 的五个新错误码各留一个 FAIL Case。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for _p in (str(ROOT), str(ROOT / "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from helpers import base_state, codes, collect, make_claim  # noqa: E402
from core.models import Claim  # noqa: E402


def _with_basis(claim, basis):
    claim.basis_claim_ids = list(basis)
    return claim


def _add_claim(state, claim):
    state.add_claim(claim)
    return state


# --------------------------------------------------------------------------- #
# inference / assumption 可以声明依据 —— 这是合法用法，必须放行
# --------------------------------------------------------------------------- #


def test_inference_claim_with_valid_basis_passes():
    state = base_state()
    _add_claim(
        state,
        _with_basis(
            make_claim(
                "C_MKT_CAP_20260914",
                claim="按 2026-09-14 收盘价与 2026H1 股本推算总市值约 138.40 亿元",
                category="market",
                level="inference",
                materiality="major",
                status="supported",
            ),
            ["C_FIN_REV_2026H1"],
        ),
    )
    assert "CLAIM_BASIS_UNKNOWN" not in codes(state)
    assert "CLAIM_BASIS_LEVEL_INVALID" not in codes(state)


def test_basis_claim_ids_roundtrip_through_json():
    claim = make_claim("C_A", level="inference", basis_claim_ids=["C_B", "C_C"])
    back = Claim.from_dict(claim.to_dict())
    assert back.basis_claim_ids == ["C_B", "C_C"]
    # 单值写法也接受，统一成列表
    assert Claim.from_dict({"claim_id": "C_A", "claim": "x", "basis_claim_ids": "C_B"}).basis_claim_ids == ["C_B"]


# --------------------------------------------------------------------------- #
# §9 CLAIM_BASIS_UNKNOWN
# --------------------------------------------------------------------------- #


def test_unknown_basis_claim_is_p1():
    state = base_state()
    _add_claim(
        state,
        _with_basis(
            make_claim(
                "C_MKT_CAP_20260914",
                level="inference",
                category="market",
                materiality="major",
                status="supported",
            ),
            ["C_NOT_EXIST"],
        ),
    )
    issues = collect(state)
    hit = [i for i in issues if i.code == "CLAIM_BASIS_UNKNOWN"]
    assert hit and hit[0].severity == "P1"
    assert "C_NOT_EXIST" in hit[0].detail


def test_known_basis_does_not_trigger_unknown_code():
    state = base_state()
    _add_claim(
        state,
        _with_basis(
            make_claim("C_MKT_CAP_20260914", level="inference", category="market",
                       materiality="major", status="supported"),
            ["C_FIN_REV_2026H1", "C_ORDER_224G_STATUS"],
        ),
    )
    assert "CLAIM_BASIS_UNKNOWN" not in codes(state)


# --------------------------------------------------------------------------- #
# §8 fact 不能建立在不确认的推导之上
# --------------------------------------------------------------------------- #


def test_fact_claim_cannot_rest_on_inference():
    state = base_state()
    _add_claim(
        state,
        make_claim("C_BAD_FACT", level="inference", category="other",
                   materiality="normal", status="supported"),
    )
    _add_claim(
        state,
        _with_basis(
            make_claim("C_BAD_FACT_DOWNSTREAM", level="fact", materiality="normal",
                       status="supported"),
            ["C_BAD_FACT"],
        ),
    )
    issues = collect(state)
    hit = [i for i in issues if i.code == "CLAIM_BASIS_LEVEL_INVALID"]
    assert hit and hit[0].severity == "P1"
    assert "C_BAD_FACT" in hit[0].detail


@pytest.mark.parametrize("basis_level", ["assumption", "unconfirmed"])
def test_fact_claim_cannot_rest_on_unconfirmed_levels(basis_level):
    state = base_state()
    _add_claim(
        state,
        make_claim("C_WEAK", level=basis_level, category="other",
                   materiality="normal", status="pending"),
    )
    _add_claim(
        state,
        _with_basis(
            make_claim("C_DOWNSTREAM", level="fact", materiality="normal", status="supported"),
            ["C_WEAK"],
        ),
    )
    assert "CLAIM_BASIS_LEVEL_INVALID" in codes(state)


def test_fact_claim_may_rest_on_fact_and_confirmed_levels():
    state = base_state()
    _add_claim(
        state,
        make_claim("C_CONFIRMED", level="confirmed_revenue", category="financial",
                   materiality="major", status="supported"),
    )
    _add_claim(
        state,
        _with_basis(
            make_claim("C_OK_FACT", level="fact", materiality="normal", status="supported"),
            ["C_FIN_REV_2026H1", "C_CONFIRMED"],
        ),
    )
    assert "CLAIM_BASIS_LEVEL_INVALID" not in codes(state)


def test_non_fact_claim_may_rest_on_inference():
    """推导链可以叠推导 —— 只有 fact 这一层要求依据足够硬。"""
    state = base_state()
    _add_claim(
        state,
        make_claim("C_INFER_1", level="inference", category="market",
                   materiality="normal", status="supported"),
    )
    _add_claim(
        state,
        _with_basis(
            make_claim("C_INFER_2", level="inference", category="market",
                       materiality="normal", status="supported"),
            ["C_INFER_1"],
        ),
    )
    assert "CLAIM_BASIS_LEVEL_INVALID" not in codes(state)


# --------------------------------------------------------------------------- #
# §8 unconfirmed 不能伪装成 critical-supported
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("level", ["unconfirmed", "assumption"])
def test_unconfirmed_critical_supported_is_p1(level):
    state = base_state()
    _add_claim(
        state,
        make_claim(
            "C_PE_TTM_20260914",
            claim="PE(TTM) 约 33 倍",
            category="valuation",
            level=level,
            materiality="critical",
            status="supported",
        ),
    )
    issues = collect(state)
    hit = [i for i in issues if i.code == "CLAIM_UNCONFIRMED_SUPPORTED"]
    assert hit and hit[0].severity == "P1"


def test_unconfirmed_critical_pending_is_fine():
    """诚实地说「没确认」是允许的 —— 这正是拆分后的正确形态。"""
    state = base_state()
    _add_claim(
        state,
        make_claim(
            "C_PE_TTM_20260914",
            claim="PE(TTM) 待补充可靠口径",
            category="valuation",
            level="unconfirmed",
            materiality="critical",
            status="pending",
        ),
    )
    assert "CLAIM_UNCONFIRMED_SUPPORTED" not in codes(state)


def test_unconfirmed_normal_supported_is_tolerated():
    """只有进入严格校验的 critical/major 才拦；normal 不拦。"""
    state = base_state()
    _add_claim(
        state,
        make_claim(
            "C_ASSUMED_NORMAL",
            level="assumption",
            materiality="normal",
            status="supported",
        ),
    )
    assert "CLAIM_UNCONFIRMED_SUPPORTED" not in codes(state)


def test_major_unconfirmed_supported_is_p1():
    state = base_state()
    _add_claim(
        state,
        make_claim("C_MAJOR_UNCONF", level="unconfirmed", materiality="major", status="supported"),
    )
    assert "CLAIM_UNCONFIRMED_SUPPORTED" in codes(state)


def test_management_statement_is_not_treated_as_unconfirmed():
    """管理层口径是**已披露**的信息，不是「未确认」，不该被这条规则误伤。"""
    state = base_state()
    assert "CLAIM_UNCONFIRMED_SUPPORTED" not in codes(state)


def test_inference_claim_may_be_supported():
    """推导是可以 supported 的 —— 前提是依据真实存在（另有规则管）。"""
    state = base_state()
    _add_claim(
        state,
        make_claim("C_MKT_CAP_20260914", level="inference", category="market",
                   materiality="critical", status="supported"),
    )
    assert "CLAIM_UNCONFIRMED_SUPPORTED" not in codes(state)


# --------------------------------------------------------------------------- #
# 非严格模式（v2 兼容）不受影响
# --------------------------------------------------------------------------- #


def test_v2_compat_mode_skips_claim_rules():
    state = base_state()
    _add_claim(
        state,
        _with_basis(
            make_claim("C_DOWNSTREAM", level="fact", materiality="normal", status="supported"),
            ["C_NOT_EXIST"],
        ),
    )
    assert "CLAIM_BASIS_UNKNOWN" not in codes(state, strict=False)
    assert "CLAIM_BASIS_UNKNOWN" in codes(state)
