# -*- coding: utf-8 -*-
"""线索层校验规则：线索 ≠ 证据（v3.0.1 §5、§9）。"""

from __future__ import annotations

from core.models import EvidenceLink
from helpers import (
    RESEARCH_DATE,
    base_state,
    collect,
    make_candidate,
    make_claim,
    valid_manifest_v3,
)


def _codes(state, **kwargs):
    return [i.code for i in collect(state, **kwargs)]


def _issue(state, code, **kwargs):
    hits = [i for i in collect(state, **kwargs) if i.code == code]
    assert hits, f"{code} 未出现: {_codes(state, **kwargs)}"
    return hits[0]


# --------------------------------------------------------------------------- #
# promoted 只是跟进状态，不是证据
# --------------------------------------------------------------------------- #


def test_promoted_candidate_without_document_is_p1():
    state = base_state()
    state.add_candidate(make_candidate("CAN_prom0001", status="promoted"))
    issue = _issue(state, "CANDIDATE_PROMOTED_WITHOUT_DOCUMENT")
    assert issue.severity == "P1"
    assert "CAN_prom0001" in issue.message


def test_promoted_candidate_with_unknown_document_is_p1():
    state = base_state()
    state.add_candidate(
        make_candidate("CAN_prom0002", status="promoted", promoted_document_id="DOC_notexist")
    )
    assert "CANDIDATE_PROMOTED_WITHOUT_DOCUMENT" in _codes(state)


def test_promoted_candidate_with_real_document_passes():
    state = base_state()
    doc_id = next(iter(state.documents))
    state.add_candidate(
        make_candidate("CAN_prom0003", status="promoted", promoted_document_id=doc_id)
    )
    assert "CANDIDATE_PROMOTED_WITHOUT_DOCUMENT" not in _codes(state)


def test_non_terminal_candidate_produces_no_issues():
    """new / reviewed 的线索只是待办，不产生任何结论。"""
    state = base_state()
    baseline = _codes(state)
    state.add_candidate(make_candidate("CAN_new0001", status="new"))
    state.add_candidate(make_candidate("CAN_rev0001", status="reviewed"))
    assert _codes(state) == baseline


# --------------------------------------------------------------------------- #
# 线索不能顶替正式证据
# --------------------------------------------------------------------------- #


def test_link_pointing_to_candidate_is_p0():
    state = base_state()
    state.add_candidate(make_candidate("CAN_used0001"))
    state.links[0].document_id = "CAN_used0001"
    issue = _issue(state, "CANDIDATE_USED_AS_EVIDENCE")
    assert issue.severity == "P0"
    # 不能被误报成普通的「文档缺失」
    assert "EVIDENCE_DOC_MISSING" not in _codes(state)


def test_link_claim_pointing_to_candidate_is_p0():
    state = base_state()
    state.add_candidate(make_candidate("CAN_used0002"))
    state.links.append(
        EvidenceLink(
            evidence_id="EV_ghost_01",
            claim_id="CAN_used0002",
            document_id=next(iter(state.documents)),
            support_type="direct",
        )
    )
    issue = _issue(state, "CANDIDATE_USED_AS_EVIDENCE")
    assert issue.severity == "P0"
    assert "EVIDENCE_CLAIM_MISSING" not in _codes(state)


def test_manifest_ref_pointing_to_candidate_is_p0():
    from core.validation import validate_evidence
    from core.issue import Issue

    state = base_state()
    state.add_candidate(make_candidate("CAN_ref0001"))
    manifest = valid_manifest_v3()
    manifest["evidence_refs"].append({"claim_id": "CAN_ref0001", "importance": "normal"})

    bucket = []
    validate_evidence(
        state,
        emit=lambda s, c, m, d="": bucket.append(Issue(s, c, m, d)),
        manifest=manifest,
        research_date=RESEARCH_DATE,
    )
    hits = [i for i in bucket if i.code == "CANDIDATE_USED_AS_EVIDENCE"]
    assert hits and hits[0].severity == "P0"
    assert "EVIDENCE_REF_UNKNOWN" not in [i.code for i in bucket]


# --------------------------------------------------------------------------- #
# 线索的存在不该改变 Claim 的判定
# --------------------------------------------------------------------------- #


def test_rejected_candidate_does_not_affect_claim_status():
    state = base_state()
    before_codes = _codes(state)
    before_status = {cid: c.status for cid, c in state.claims.items()}

    state.add_candidate(
        make_candidate("CAN_rej0001", status="rejected", claim_id="C_FIN_REV_2026H1")
    )

    assert _codes(state) == before_codes
    assert {cid: c.status for cid, c in state.claims.items()} == before_status


def test_candidates_do_not_change_independent_source_count():
    """即使给同一 Claim 挂上一堆线索，独立来源数仍只由 Document 决定。"""
    state = base_state()
    baseline = state.independent_source_count("C_FIN_REV_2026H1")
    for i in range(3):
        state.add_candidate(
            make_candidate(f"CAN_many000{i}", claim_id="C_FIN_REV_2026H1", url=f"https://x/{i}")
        )
    assert state.independent_source_count("C_FIN_REV_2026H1") == baseline
