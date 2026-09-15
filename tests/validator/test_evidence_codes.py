# -*- coding: utf-8 -*-
"""Evidence Validator：P0/P1/P2 规则与固定错误码（v3.0 §8、§9.1 C）。"""

from __future__ import annotations

import pytest

from core.evidence import sha256_file
from helpers import (
    RESEARCH_DATE,
    base_state,
    codes,
    collect,
    make_document,
    make_link,
    severities,
)


# --------------------------------------------------------------------------- #
# 正常 Case
# --------------------------------------------------------------------------- #


def test_valid_state_has_no_p0_p1():
    issues = collect(base_state())
    assert [i.code for i in issues if i.severity in {"P0", "P1"}] == []
    assert "EVIDENCE_SUMMARY" in [i.code for i in issues]


# --------------------------------------------------------------------------- #
# P0
# --------------------------------------------------------------------------- #


def test_doc_missing_is_p0_for_critical_claim():
    state = base_state()
    state.links[0].document_id = "DOC_ghost"
    issues = collect(state)
    hit = [i for i in issues if i.code == "EVIDENCE_DOC_MISSING"]
    assert hit and hit[0].severity == "P0"


def test_hash_mismatch_is_p0(tmp_path):
    path = tmp_path / "2026H1.txt"
    path.write_text("原始内容", encoding="utf-8")
    digest = sha256_file(path)
    state = base_state()
    state.documents["DOC_h1report"] = make_document(local_path=str(path), sha256=digest)
    assert "EVIDENCE_HASH_MISMATCH" not in codes(state)

    path.write_text("事后被篡改的内容", encoding="utf-8")
    issues = collect(state)
    hit = [i for i in issues if i.code == "EVIDENCE_HASH_MISMATCH"]
    assert hit and hit[0].severity == "P0"


def test_confirmed_order_supported_only_by_media_is_p0():
    state = base_state()
    state.claims["C_ORDER_224G_STATUS"].level = "confirmed_order"
    state.claims["C_ORDER_224G_STATUS"].requires_two_sources = False
    state.links = [l for l in state.links if l.claim_id == "C_ORDER_224G_STATUS"]
    state.links[0].document_id = "DOC_media_only"
    state.add_document(
        make_document("DOC_media_only", source_type="media", url="https://x/media", source_group="M1", page_count=None, sections=None)
    )
    issues = collect(state)
    hit = [i for i in issues if i.code == "EVIDENCE_PRIMARY_REQUIRED"]
    assert hit and hit[0].severity == "P0"


def test_confirmed_order_with_context_support_is_p0():
    state = base_state()
    claim = state.claims["C_ORDER_224G_STATUS"]
    claim.level = "confirmed_order"
    state.links = [l for l in state.links if l.claim_id == "C_ORDER_224G_STATUS"]
    state.links[0].support_type = "context"
    issues = collect(state)
    hit = [i for i in issues if i.code == "EVIDENCE_DIRECT_REQUIRED"]
    assert hit and hit[0].severity == "P0"


def test_direct_evidence_from_secondary_source_is_p0():
    state = base_state()
    claim = state.claims["C_ORDER_224G_STATUS"]
    claim.level = "mass_production"
    state.links = [l for l in state.links if l.claim_id == "C_ORDER_224G_STATUS"]
    state.add_document(
        make_document("DOC_media_only", source_type="media", url="https://x/media", source_group="M1", page_count=None, sections=None)
    )
    state.links[0].document_id = "DOC_media_only"
    state.links[0].support_type = "direct"
    issues = collect(state)
    assert "EVIDENCE_DIRECT_REQUIRED" in [i.code for i in issues]


# --------------------------------------------------------------------------- #
# P1
# --------------------------------------------------------------------------- #


def test_critical_claim_without_locator_is_p1():
    state = base_state()
    state.links[0].page = None
    state.links[0].section = None
    state.links[0].paragraph = None
    state.links[0].table = None
    issues = collect(state)
    hit = [i for i in issues if i.code == "EVIDENCE_LOCATOR_MISSING"]
    assert hit and hit[0].severity == "P1"


def test_critical_claim_without_evidence_text_is_p1():
    state = base_state()
    state.links[0].evidence_text = None
    issues = collect(state)
    hit = [i for i in issues if i.code == "EVIDENCE_TEXT_MISSING"]
    assert hit and hit[0].severity == "P1"


def test_page_out_of_range_is_p1():
    state = base_state()
    state.links[0].page = 999
    issues = collect(state)
    hit = [i for i in issues if i.code == "EVIDENCE_LOCATOR_INVALID"]
    assert hit and hit[0].severity == "P1"


def test_section_not_registered_is_p1():
    state = base_state()
    state.links[0].section = "并不存在的章节"
    issues = collect(state)
    assert "EVIDENCE_LOCATOR_INVALID" in [i.code for i in issues]


def test_document_published_after_research_date_is_p1():
    state = base_state()
    state.documents["DOC_h1report"].published_at = "2026-10-01"
    issues = collect(state)
    hit = [i for i in issues if i.code == "SOURCE_DATE_AFTER_RESEARCH_DATE"]
    assert hit and hit[0].severity == "P1"


def test_document_without_any_source_is_p1():
    state = base_state()
    state.documents["DOC_h1report"].url = None
    state.documents["DOC_h1report"].local_path = None
    issues = collect(state)
    hit = [i for i in issues if i.code == "EVIDENCE_NO_SOURCE"]
    assert hit and hit[0].severity == "P1"


def test_link_referencing_unknown_claim_is_p1():
    state = base_state()
    state.links.append(make_link("C_NOT_EXIST", "DOC_h1report"))
    issues = collect(state)
    assert "EVIDENCE_CLAIM_MISSING" in [i.code for i in issues]


def test_critical_claim_without_any_link_is_p1():
    from core.models import Claim

    state = base_state()
    state.add_claim(Claim(claim_id="C_RISK_NEW", claim="新增关键结论", category="risk", materiality="critical"))
    issues = collect(state)
    hit = [i for i in issues if i.code == "EVIDENCE_CLAIM_ORPHAN"]
    assert hit and hit[0].severity == "P1" and "C_RISK_NEW" in hit[0].message


def test_supported_but_evidence_gone_is_p1():
    state = base_state()
    state.links = [l for l in state.links if l.claim_id != "C_FIN_REV_2026H1"]
    issues = collect(state)
    assert "EVIDENCE_SUPPORT_BROKEN" in [i.code for i in issues]


def test_duplicate_evidence_id_is_p1():
    state = base_state()
    state.links.append(make_link())  # 与已有 evidence_id 完全相同
    issues = collect(state)
    assert "EVIDENCE_DUPLICATE_ID" in [i.code for i in issues]


# --------------------------------------------------------------------------- #
# P2 / 兼容模式
# --------------------------------------------------------------------------- #


def test_registered_hash_without_local_file_is_p2(tmp_path):
    state = base_state()
    state.documents["DOC_h1report"] = make_document(local_path=str(tmp_path / "缺失.pdf"), sha256="a" * 64)
    issues = collect(state)
    hit = [i for i in issues if i.code == "EVIDENCE_HASH_UNVERIFIED"]
    assert hit and hit[0].severity == "P2"


def test_url_only_document_is_p2_not_p0():
    state = base_state()
    issues = collect(state)
    assert "EVIDENCE_HASH_MISMATCH" not in [i.code for i in issues]
    assert "EVIDENCE_HASH_UNVERIFIED" in [i.code for i in issues]
    assert severities(state).get("P0", 0) == 0


def test_non_strict_mode_skips_semantic_checks():
    state = base_state()
    state.links[0].page = None
    state.links[0].section = None
    state.links[0].evidence_text = None
    result = codes(state, strict=False)
    assert result == ["EVIDENCE_STORE_SKIPPED"]


def test_hash_mismatch_blocks_even_in_url_case(tmp_path):
    """hash 不匹配必须报 P0；缺失文件只是 P2，两者不可混淆。"""
    path = tmp_path / "doc.txt"
    path.write_text("v1", encoding="utf-8")
    good = sha256_file(path)
    state = base_state()
    state.documents["DOC_h1report"] = make_document(local_path=str(path), sha256=good)
    assert severities(state).get("P0", 0) == 0
    path.write_text("v2", encoding="utf-8")
    assert severities(state).get("P0", 0) == 1


@pytest.mark.parametrize("research_date", [None, RESEARCH_DATE])
def test_research_date_from_param_or_state(research_date):
    state = base_state()
    if research_date is None:
        state.research_date = None
        state.documents["DOC_cls_media"].published_at = "2026-09-15"
        assert "SOURCE_DATE_AFTER_RESEARCH_DATE" not in codes(state, research_date=None)
    else:
        state.documents["DOC_cls_media"].published_at = "2026-09-15"
        assert "SOURCE_DATE_AFTER_RESEARCH_DATE" in codes(state, research_date=research_date)
