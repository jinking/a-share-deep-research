# -*- coding: utf-8 -*-
"""来源独立性：识别「共同上游来源伪装成双源」（v3.0 §8.2、§9.1 D）。"""

from __future__ import annotations

from core.evidence import group_documents, independent_source_count
from core.models import Claim
from helpers import base_state, codes, collect, make_document, make_link


def _state_with_two_docs(group_a: str, group_b: str, type_a: str = "media", type_b: str = "media"):
    state = base_state()
    state.claims["C_ORDER_224G_STATUS"] = Claim(
        claim_id="C_ORDER_224G_STATUS",
        claim="224G 已批量交付",
        category="order",
        level="batch_delivery",
        materiality="critical",
        status="supported",
        requires_two_sources=True,
    )
    state.links = [l for l in state.links if l.claim_id != "C_ORDER_224G_STATUS"]
    state.documents.pop("DOC_aichip_ir", None)
    state.add_document(
        make_document("DOC_a", source_type=type_a, url="https://a/1", source_group=group_a, page_count=None, sections=None)
    )
    state.add_document(
        make_document("DOC_b", source_type=type_b, url="https://b/2", source_group=group_b, page_count=None, sections=None)
    )
    state.add_link(make_link("C_ORDER_224G_STATUS", "DOC_a", page=None, section="正文", evidence_text="原文A"))
    state.add_link(
        make_link("C_ORDER_224G_STATUS", "DOC_b", page=None, section="正文", evidence_text="原文B")
    )
    return state


def test_two_media_from_same_agency_is_not_independent():
    """财联社原始报道 → 新浪转载 → 雪球转载，只能算 1 个独立来源。"""
    state = _state_with_two_docs("CLS_20260915_001", "CLS_20260915_001")
    issues = collect(state)
    hit = [i for i in issues if i.code == "EVIDENCE_SOURCE_NOT_INDEPENDENT"]
    assert hit and hit[0].severity == "P1"
    assert "同一上游来源" in hit[0].detail


def test_two_brokers_quoting_same_announcement_is_not_independent():
    state = _state_with_two_docs("CNINFO_002897_2026H1", "CNINFO_002897_2026H1", "broker_report", "broker_report")
    assert "EVIDENCE_SOURCE_NOT_INDEPENDENT" in codes(state)


def test_same_source_group_is_not_independent():
    state = _state_with_two_docs("GROUP_X", "GROUP_X", "media", "broker_report")
    assert state.independent_source_count("C_ORDER_224G_STATUS") == 1
    assert "EVIDENCE_SOURCE_NOT_INDEPENDENT" in codes(state)


def test_one_primary_plus_one_reprint_counts_as_two():
    """一手来源 + 另一家独立媒体转载，来源组不同，视为满足双源。"""
    state = _state_with_two_docs("CNINFO_X", "CLS_001", "interim_report", "media")
    assert independent_source_count(state.documents_of("C_ORDER_224G_STATUS")) == 2
    assert "EVIDENCE_SOURCE_NOT_INDEPENDENT" not in codes(state)


def test_two_truly_independent_primary_sources_pass():
    state = _state_with_two_docs("CNINFO_002897_2026H1", "SZSE_ANNOUNCE_2026_09", "interim_report", "company_announcement")
    assert "EVIDENCE_SOURCE_NOT_INDEPENDENT" not in codes(state)


def test_no_double_source_requirement_skips_check():
    state = base_state()
    state.documents["DOC_cls_media"].source_group = state.documents["DOC_h1report"].source_group
    assert "EVIDENCE_SOURCE_NOT_INDEPENDENT" not in codes(state)


def test_group_documents_groups_by_source_group():
    state = base_state()
    state.add_document(
        make_document("DOC_cls_reprint2", source_type="social_media", url="https://x/2", source_group="CLS_20260915_001", page_count=None, sections=None)
    )
    groups = group_documents(state.documents.values())
    assert "CLS_20260915_001" in groups
    assert len(groups["CLS_20260915_001"]) == 2
