# -*- coding: utf-8 -*-
"""strict Claim 必须反向进入 Manifest（v3.0.3 §8）。

要堵的口子：

    报告里出现了一个 critical Claim → 校验器检查它有没有落点；
    但如果**把它从 manifest.evidence_refs 里删掉**，那么「关键 Claim 有没有覆盖」
    这件事就没人问了 —— 删引用成了绕过路径。

于是 v3.0.3 补齐反向链：

    Claim Ledger  →  manifest.evidence_refs  →  Report Claim Anchor

三层都要能互相印证，任何一层缺失都算缺口。

规则（`scope=report` 是默认值）：

```text
scope=report + materiality ∈ {critical, major} → 必须进入 manifest.evidence_refs
scope=internal                                → 可以不进（内部中间结论，不对外交付）
materiality=normal                            → 不受约束（本就不进严格校验）
```

反例：确有内部中间 Claim 时，**不要靠删 manifest 隐藏**，而是显式标 `scope=internal`
—— 让「为什么它不在 manifest 里」变成一条可审查的记录，而不是一片空白。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for _p in (str(ROOT), str(ROOT / "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core.models import EvidenceModelError
from core.models.claim import CLAIM_SCOPES, Claim
from core.validation import validate_evidence
from core.validation.codes import severity_of
from helpers import make_claim


def _manifest(*claim_ids):
    return {
        "manifest_version": 3,
        "evidence_refs": [{"claim_id": cid, "importance": "critical"} for cid in claim_ids],
    }


def _validate(claims, manifest):
    bucket = []
    summary = validate_evidence(
        state=_state(claims),
        emit=lambda s, c, m, d="": bucket.append((s, c, d)),
        manifest=manifest,
    )
    return summary, [c for _, c, _ in bucket]


def _state(claims):
    from core.models import ResearchState

    state = ResearchState()
    for claim in claims:
        state.claims[claim.claim_id] = claim
    return state


# --------------------------------------------------------------------------- #
# 1–3. scope 字段本身
# --------------------------------------------------------------------------- #


def test_claim_scope_defaults_to_report():
    claim = make_claim()
    assert claim.scope == "report"
    assert "report" in CLAIM_SCOPES


def test_claim_scope_rejects_unknown_value():
    claim = make_claim("C_X", scope="sometimes")
    with pytest.raises(EvidenceModelError):
        claim.validate()


def test_claim_scope_roundtrips_through_dict():
    claim = make_claim("C_X", scope="internal")
    restored = Claim.from_dict(claim.to_dict())
    assert restored.scope == "internal"


# --------------------------------------------------------------------------- #
# 4–9. 反向覆盖：报告可见的 strict Claim 不得从 manifest 消失
# --------------------------------------------------------------------------- #


def test_critical_report_claim_present_passes():
    _summary, codes = _validate([make_claim("C_A")], _manifest("C_A"))
    assert "MANIFEST_STRICT_CLAIM_MISSING" not in codes


def test_major_report_claim_present_passes():
    claim = make_claim("C_A", materiality="major")
    _summary, codes = _validate([claim], _manifest("C_A"))
    assert "MANIFEST_STRICT_CLAIM_MISSING" not in codes


def test_critical_report_claim_missing_from_manifest_fails():
    """§10.4：从 manifest 删掉一个 critical Claim 必须被抓住。"""
    summary, codes = _validate([make_claim("C_A")], _manifest())
    assert "MANIFEST_STRICT_CLAIM_MISSING" in codes
    assert summary["P1"] >= 1


def test_major_report_claim_missing_from_manifest_fails():
    claim = make_claim("C_A", materiality="major")
    _summary, codes = _validate([claim], _manifest())
    assert "MANIFEST_STRICT_CLAIM_MISSING" in codes


def test_missing_claim_is_named_in_the_message():
    bucket = []
    validate_evidence(
        state=_state([make_claim("C_A")]),
        emit=lambda s, c, m, d="": bucket.append((c, m, d)),
        manifest=_manifest(),
    )
    rows = [(c, m, d) for c, m, d in bucket if c == "MANIFEST_STRICT_CLAIM_MISSING"]
    assert rows, bucket
    assert any("C_A" in (m + d) for _, m, d in rows)


def test_normal_claim_may_be_absent():
    claim = make_claim("C_A", materiality="normal")
    _summary, codes = _validate([claim], _manifest())
    assert "MANIFEST_STRICT_CLAIM_MISSING" not in codes


def test_internal_critical_claim_may_be_absent():
    """内部中间结论显式声明 scope=internal —— 是「说明白」，不是「藏起来」。"""
    claim = make_claim("C_A", materiality="critical", scope="internal")
    _summary, codes = _validate([claim], _manifest())
    assert "MANIFEST_STRICT_CLAIM_MISSING" not in codes


def test_internal_claim_present_is_fine_too(tmp_path):
    """scope=internal 只是「可以不进」，不是「不许进」——不制造反向义务。"""
    claim = make_claim("C_A", materiality="critical", scope="internal")
    _summary, codes = _validate([claim], _manifest("C_A"))
    assert "MANIFEST_STRICT_CLAIM_MISSING" not in codes


def test_only_the_missing_one_is_reported():
    claims = [
        make_claim("C_A"),
        make_claim("C_B", materiality="major"),
        make_claim("C_C", materiality="normal"),
    ]
    bucket = []
    validate_evidence(
        state=_state(claims),
        emit=lambda s, c, m, d="": bucket.append((c, m + d)),
        manifest=_manifest("C_A"),
    )
    missing = [text for c, text in bucket if c == "MANIFEST_STRICT_CLAIM_MISSING"]
    assert len(missing) == 1, missing
    assert "C_B" in missing[0]


# --------------------------------------------------------------------------- #
# 10–12. 与既有 manifest 规则共存，不互相掩盖
# --------------------------------------------------------------------------- #


def test_unknown_manifest_claim_still_reports_ref_unknown():
    """既有规则不变：manifest 引用了不存在的 Claim → EVIDENCE_REF_UNKNOWN。"""
    _summary, codes = _validate([make_claim("C_A")], _manifest("C_A", "C_GHOST"))
    assert "EVIDENCE_REF_UNKNOWN" in codes


def test_materiality_mismatch_still_reports():
    claim = make_claim("C_A", materiality="major")
    manifest = {
        "manifest_version": 3,
        "evidence_refs": [{"claim_id": "C_A", "importance": "critical"}],
    }
    _summary, codes = _validate([claim], manifest)
    assert "EVIDENCE_IMPORTANCE_MISMATCH" in codes
    assert "MANIFEST_STRICT_CLAIM_MISSING" not in codes  # 已覆盖，只是等级写错


def test_missing_refs_entirely_does_not_double_report():
    """整个 evidence_refs 缺失时只报 EVIDENCE_REFS_EMPTY，不逐条重复报覆盖缺口。"""
    _summary, codes = _validate([make_claim("C_A")], {"manifest_version": 3})
    assert "EVIDENCE_REFS_EMPTY" in codes
    assert codes.count("EVIDENCE_REFS_EMPTY") == 1


def test_severity_is_p1():
    assert severity_of("MANIFEST_STRICT_CLAIM_MISSING") == "P1"
