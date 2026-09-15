# -*- coding: utf-8 -*-
"""manifest v2 / v3 结构校验与版本识别（v3.0 §7）。"""

from __future__ import annotations

from core.issue import Issue
from core.validation import detect_manifest_version, validate_manifest_v3
from helpers import v3_state, valid_manifest, valid_manifest_v3
from core.validation import validate_evidence


def _run(data) -> list:
    bucket = []
    validate_manifest_v3(data, emit=lambda s, c, m, d="": bucket.append(Issue(s, c, m, d)))
    return bucket


def _codes(data) -> list:
    return [i.code for i in _run(data)]


def _p0p1(data) -> list:
    return [i.code for i in _run(data) if i.severity in {"P0", "P1"}]


def test_detect_manifest_version():
    assert detect_manifest_version(valid_manifest()) == 2
    assert detect_manifest_version(valid_manifest_v3()) == 3
    assert detect_manifest_version({"manifest_version": 3}) == 3
    assert detect_manifest_version({"manifest_version": "2"}) == 2


def test_v3_valid_manifest_passes_structure():
    assert _p0p1(valid_manifest_v3()) == []


def test_v2_manifest_reports_compat_mode_not_error():
    issues = _run(valid_manifest())
    assert [i.code for i in issues] == ["MANIFEST_V2_COMPAT"]
    assert issues[0].severity == "INFO"


def test_v3_without_evidence_refs_is_p1():
    data = valid_manifest_v3()
    data.pop("evidence_refs")
    issues = _run(data)
    hit = [i for i in issues if i.code == "EVIDENCE_REFS_EMPTY"]
    assert hit and hit[0].severity == "P1"


def test_v3_empty_evidence_refs_is_p1():
    data = valid_manifest_v3()
    data["evidence_refs"] = []
    assert "EVIDENCE_REFS_EMPTY" in _codes(data)


def test_v3_missing_required_block_is_p1():
    data = valid_manifest_v3()
    data.pop("valuation")
    assert "MANIFEST_V3_STRUCTURE" in _codes(data)


def test_v3_missing_research_date_is_p1():
    data = valid_manifest_v3()
    data["meta"].pop("research_date")
    assert "MANIFEST_V3_STRUCTURE" in _codes(data)


def test_v3_refs_format_errors_are_p1():
    data = valid_manifest_v3()
    data["evidence_refs"] = ["C_FIN_REV_2026H1", {"importance": "critical"}]
    assert _codes(data).count("MANIFEST_EVIDENCE_REFS_FORMAT") >= 2


def test_v3_duplicate_claim_ref_is_p1():
    data = valid_manifest_v3()
    data["evidence_refs"].append({"claim_id": "C_FIN_REV_2026H1", "importance": "critical"})
    assert "MANIFEST_EVIDENCE_REFS_FORMAT" in _codes(data)


def test_v3_invalid_importance_is_p1():
    data = valid_manifest_v3()
    data["evidence_refs"][0]["importance"] = "very_critical"
    assert "MANIFEST_EVIDENCE_REFS_FORMAT" in _codes(data)


def test_unsupported_version_is_p1():
    data = valid_manifest_v3()
    data["manifest_version"] = 9
    issues = _run(data)
    hit = [i for i in issues if i.code == "MANIFEST_VERSION_UNSUPPORTED"]
    assert hit and hit[0].severity == "P1"


def test_evidence_refs_pointing_to_unknown_claim_is_p1():
    state = v3_state()
    data = valid_manifest_v3()
    data["evidence_refs"].append({"claim_id": "C_GHOST", "importance": "normal"})
    bucket = []
    validate_evidence(
        state,
        emit=lambda s, c, m, d="": bucket.append(Issue(s, c, m, d)),
        manifest=data,
        research_date="2026-09-14",
    )
    hit = [i for i in bucket if i.code == "EVIDENCE_REF_UNKNOWN"]
    assert hit and hit[0].severity == "P1" and "C_GHOST" in hit[0].message


def test_importance_mismatch_is_p2():
    state = v3_state()
    data = valid_manifest_v3()
    data["evidence_refs"][0]["importance"] = "major"   # store 中该 Claim 为 critical
    bucket = []
    validate_evidence(
        state,
        emit=lambda s, c, m, d="": bucket.append(Issue(s, c, m, d)),
        manifest=data,
        research_date="2026-09-14",
    )
    hit = [i for i in bucket if i.code == "EVIDENCE_IMPORTANCE_MISMATCH"]
    assert hit and hit[0].severity == "P2"


def test_consistent_v3_manifest_and_store_pass():
    state = v3_state()
    bucket = []
    summary = validate_evidence(
        state,
        emit=lambda s, c, m, d="": bucket.append(Issue(s, c, m, d)),
        manifest=valid_manifest_v3(),
        research_date="2026-09-14",
    )
    assert summary.get("P0", 0) == 0 and summary.get("P1", 0) == 0
