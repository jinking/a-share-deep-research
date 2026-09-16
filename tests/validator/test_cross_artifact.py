# -*- coding: utf-8 -*-
"""跨产物一致性校验测试（v3.0.2 §6 / §15-B）。

15 个用例：6 条规则的正常侧与失败侧、critical 覆盖率、canonical 例外，
以及「报告用旧 status / 新 status」这组最容易写错的边界。
"""

from __future__ import annotations

from typing import Any, Dict, List

from core.models import Claim
from core.report import ReportClaimRef
from core.validation import validate_report_claims


# --------------------------------------------------------------------- 构件


def make_claims() -> Dict[str, Claim]:
    return {
        "E007": Claim(
            claim_id="E007",
            claim="224G 与液冷产品处于在研阶段",
            category="order",
            level="management_statement",
            materiality="critical",
            status="supported",
        ),
        "C_PE_TTM_20260914": Claim(
            claim_id="C_PE_TTM_20260914",
            claim="PE(TTM) 约 53.83×（口径待确认）",
            category="valuation",
            level="unconfirmed",
            materiality="normal",
            status="pending",
        ),
        "E008": Claim(
            claim_id="E008",
            claim="机构一致预期 2026E 归母 4.22 亿元",
            category="valuation",
            level="third_party_consensus",
            materiality="normal",
            status="pending",
        ),
        "C_MKT_CAP_20260914": Claim(
            claim_id="C_MKT_CAP_20260914",
            claim="按收盘价 × 股本推算总市值约 138.40 亿元",
            category="market",
            level="inference",
            materiality="critical",
            status="supported",
        ),
        "E001": Claim(
            claim_id="E001",
            claim="2026H1 营业收入 28.63 亿元（同比 -5.97%）",
            category="financial",
            level="fact",
            materiality="critical",
            status="supported",
        ),
        "E003": Claim(
            claim_id="E003",
            claim="2026H1 太阳能支架收入 12.23 亿元",
            category="financial",
            level="fact",
            materiality="normal",
            status="supported",
        ),
    }


def ref(claim_id: str, **kw) -> ReportClaimRef:
    kw.setdefault("text", "锚点文本")
    kw.setdefault("location", "<span#1>")
    return ReportClaimRef(claim_id=claim_id, **kw)


def run(refs: List[ReportClaimRef], **kw) -> List[Any]:
    out: List[Any] = []
    validate_report_claims(
        refs,
        claims=kw.pop("claims", make_claims()),
        evidence_refs=kw.pop("evidence_refs", None),
        emit=lambda s, c, m, d="": out.append((s, c, m, d)),
        **kw,
    )
    return out


def codes(refs: List[ReportClaimRef], **kw) -> List[str]:
    return [c for _, c, _, _ in run(refs, **kw)]


def summary(refs: List[ReportClaimRef], **kw) -> Dict[str, int]:
    out = {"P0": 0, "P1": 0, "P2": 0}
    for severity, _, _, _ in run(refs, **kw):
        out[severity] = out.get(severity, 0) + 1
    return out


# --------------------------------------------------------- 1. REPORT_CLAIM_UNKNOWN


def test_unknown_claim_is_p0():
    assert codes([ref("E999")]) == ["REPORT_CLAIM_UNKNOWN"]
    assert summary([ref("E999")])["P0"] == 1


def test_missing_claim_id_is_also_unknown():
    assert "REPORT_CLAIM_UNKNOWN" in codes([ref("")])


# ------------------------------------------ 2. REPORT_PENDING_CLAIM_ASSERTED


def test_pending_claim_asserted_as_supported_is_p0():
    """等级已如实声明为 unconfirmed，只把状态写成 supported —— 精确命中一条 P0。"""
    assert codes([ref("C_PE_TTM_20260914", declared_level="unconfirmed", declared_status="supported")]) == [
        "REPORT_PENDING_CLAIM_ASSERTED"
    ]


def test_pending_claim_asserted_by_omission_is_p0():
    """旧报告不会写 data-claim-level / data-claim-status —— 缺省即「当成事实」。
    此时两条 P0 同时成立（等级过度声明 + 状态过度声明），不合并、不掩盖。"""
    out = codes([ref("C_PE_TTM_20260914")])
    assert "REPORT_PENDING_CLAIM_ASSERTED" in out
    assert "REPORT_UNCONFIRMED_AS_FACT" in out
    assert summary([ref("C_PE_TTM_20260914")])["P0"] == 2


def test_pending_claim_correctly_declared_passes():
    assert run([ref("C_PE_TTM_20260914", declared_level="unconfirmed", declared_status="pending")]) == []


# ------------------------------------------- 3. REPORT_CLAIM_LEVEL_MISMATCH


def test_inference_declared_as_fact_is_p0():
    assert codes([ref("C_MKT_CAP_20260914", declared_level="fact", declared_status="supported")]) == [
        "REPORT_CLAIM_LEVEL_MISMATCH"
    ]


def test_management_statement_declared_as_fact_is_p0():
    assert codes([ref("E007", declared_level="fact", declared_status="supported")]) == [
        "REPORT_CLAIM_LEVEL_MISMATCH"
    ]


def test_inference_correctly_declared_passes():
    assert run([ref("C_MKT_CAP_20260914", declared_level="inference", declared_status="supported")]) == []


# ------------------------------------------ 4. REPORT_CLAIM_STATUS_MISMATCH


def test_status_mismatch_is_p1():
    """Ledger=support 而报告声明 pending（保守但已过期）→ P1。"""
    assert codes([ref("E007", declared_level="management_statement", declared_status="pending")]) == [
        "REPORT_CLAIM_STATUS_MISMATCH"
    ]
    assert summary([ref("E007", declared_level="management_statement", declared_status="pending")])["P1"] == 1


def test_unsupported_ledger_asserted_as_supported_is_p1():
    claims = make_claims()
    claims["E003"] = Claim(
        claim_id="E003",
        claim="x",
        category="financial",
        level="fact",
        materiality="normal",
        status="unsupported",
    )
    assert codes([ref("E003", declared_level="fact", declared_status="supported")], claims=claims) == [
        "REPORT_CLAIM_STATUS_MISMATCH"
    ]


# ------------------------------------------ 5. REPORT_UNCONFIRMED_AS_FACT


def test_unconfirmed_declared_as_fact_is_p0_unconfirmed_code():
    out = codes([ref("C_PE_TTM_20260914", declared_level="fact", declared_status="pending")])
    assert "REPORT_UNCONFIRMED_AS_FACT" in out
    assert "REPORT_CLAIM_LEVEL_MISMATCH" not in out  # P0 优先，不重复报


def test_third_party_consensus_declared_as_fact_is_p0():
    assert "REPORT_UNCONFIRMED_AS_FACT" in codes(
        [ref("E008", declared_level="fact", declared_status="pending")]
    )


def test_third_party_consensus_declared_as_confirmed_revenue_is_p0():
    assert "REPORT_UNCONFIRMED_AS_FACT" in codes(
        [ref("E008", declared_level="confirmed_revenue", declared_status="pending")]
    )


# --------------------------------------- 6. REPORT_CRITICAL_CLAIM_MISSING


def test_critical_claim_without_anchor_is_p1():
    refs = [ref("E001", declared_level="fact", declared_status="supported")]
    out = codes(refs, evidence_refs=[{"claim_id": "E001", "importance": "critical"},
                                     {"claim_id": "E007", "importance": "critical"}])
    assert out == ["REPORT_CRITICAL_CLAIM_MISSING"]


def test_critical_claim_covered_passes_and_normal_not_required():
    refs = [
        ref("E001", declared_level="fact", declared_status="supported"),
        ref("E007", declared_level="management_statement", declared_status="supported"),
        ref("C_MKT_CAP_20260914", declared_level="inference", declared_status="supported"),
    ]
    refs += [
        ref("C_PE_TTM_20260914", declared_level="unconfirmed", declared_status="pending"),
    ]
    out = run(
        refs,
        evidence_refs=[
            {"claim_id": "E001", "importance": "critical"},
            {"claim_id": "E007", "importance": "critical"},
            {"claim_id": "C_MKT_CAP_20260914", "importance": "critical"},
            {"claim_id": "E003", "importance": "normal"},   # normal 可不落报告
        ],
    )
    assert out == []


def test_manifest_without_claim_refs_skips_coverage_check():
    assert run([ref("E001", declared_level="fact", declared_status="supported")], evidence_refs=[]) == []


# ------------------------------------------------------------------ 其它边界


def test_same_claim_anchored_many_times_is_allowed():
    good = dict(declared_level="management_statement", declared_status="supported")
    refs = [ref("E007", **good), ref("E007", **good), ref("E007", **good)]
    assert run(refs) == []


def test_no_claim_report_is_clean_when_manifest_is_v2():
    """v2 路径下没有 evidence_refs，空锚点列表不应产生任何问题。"""
    assert run([]) == []


def test_fact_correctly_declared_passes():
    assert run([ref("E001", declared_level="fact", declared_status="supported")]) == []
