# -*- coding: utf-8 -*-
"""数据模型与 Evidence Store（v3.0 §5、§6）。"""

from __future__ import annotations

import json

import pytest

from core.evidence import EvidenceStore, sha256_file
from core.evidence.hasher import make_document_id, verify_file_hash
from core.models import Claim, EvidenceLink, EvidenceModelError, SourceDocument
from helpers import base_state, make_claim, make_document, make_link, write_store


# --------------------------------------------------------------------------- #
# 模型校验：结构性错误必须 fail-fast
# --------------------------------------------------------------------------- #


def test_document_valid():
    make_document().validate()


def test_document_bad_source_type():
    with pytest.raises(EvidenceModelError):
        make_document(source_type="weibo").validate()


def test_document_bad_id_prefix():
    with pytest.raises(EvidenceModelError):
        make_document("H1REPORT").validate()


def test_document_bad_sha256():
    with pytest.raises(EvidenceModelError):
        make_document(sha256="deadbeef").validate()


def test_document_bad_published_at():
    with pytest.raises(EvidenceModelError):
        make_document(published_at="去年八月").validate()


def test_claim_bad_level():
    with pytest.raises(EvidenceModelError):
        make_claim(level="已确认订单").validate()  # v2 中文等级不是 v3 合法值


def test_claim_bad_materiality_and_status():
    with pytest.raises(EvidenceModelError):
        make_claim(materiality="high").validate()
    with pytest.raises(EvidenceModelError):
        make_claim(status="ok").validate()


def test_claim_bad_id_pattern():
    with pytest.raises(EvidenceModelError):
        make_claim("007-fin").validate()


def test_link_bad_support_type_page_confidence():
    with pytest.raises(EvidenceModelError):
        make_link(support_type="strong").validate()
    with pytest.raises(EvidenceModelError):
        make_link(page=0).validate()
    with pytest.raises(EvidenceModelError):
        make_link(confidence=1.5).validate()


# --------------------------------------------------------------------------- #
# document_id 稳定性
# --------------------------------------------------------------------------- #


def test_document_id_is_stable_and_url_first():
    a = make_document_id(url="https://x/a.pdf", title="A 报告")
    b = make_document_id(url="https://x/a.pdf", title="完全不同的标题")
    assert a == b
    assert a.startswith("DOC_") and len(a) == 12
    assert make_document_id(title="A 报告", issuer="X", published_at="2026-08-25") != a


def test_document_id_requires_something():
    with pytest.raises(ValueError):
        make_document_id()


# --------------------------------------------------------------------------- #
# Store：建库 / 落盘 / 读回 / 指纹
# --------------------------------------------------------------------------- #


def test_store_init_creates_layout(tmp_path):
    store = EvidenceStore.init(tmp_path / "evidence")
    assert store.documents_path.exists()
    assert store.claims_path.exists()
    assert store.links_path.exists()
    assert store.raw_dir.is_dir()


def test_store_roundtrip(tmp_path):
    store = write_store(tmp_path)
    reloaded = EvidenceStore.open(tmp_path / "evidence")
    assert reloaded.summary() == store.summary()
    assert reloaded.issues == []
    doc = next(iter(reloaded.documents.values()))
    assert doc.sha256 == sha256_file(tmp_path / "evidence" / "raw" / "2026H1.txt")
    assert doc.local_path == "raw/2026H1.txt"
    claim = reloaded.claims["C_FIN_REV_2026H1"]
    assert claim.materiality == "critical"
    assert reloaded.links_of("C_FIN_REV_2026H1")[0].page == 12


def test_store_register_requires_existing_file(tmp_path):
    store = EvidenceStore.init(tmp_path / "evidence")
    with pytest.raises(Exception):
        store.register_document(source_type="interim_report", title="X", local_file=tmp_path / "nope.pdf")


def test_store_cannot_accept_both_local_file_and_local_path(tmp_path):
    store = EvidenceStore.init(tmp_path / "evidence")
    (store.raw_dir / "a.txt").write_text("x", encoding="utf-8")
    with pytest.raises(Exception):
        store.register_document(
            source_type="interim_report",
            title="X",
            local_file=store.raw_dir / "a.txt",
            local_path="raw/a.txt",
        )


def test_verify_file_hash_detects_replacement(tmp_path):
    path = tmp_path / "a.txt"
    path.write_text("原始内容", encoding="utf-8")
    digest = sha256_file(path)
    ok, actual = verify_file_hash(path, digest)
    assert ok and actual == digest
    path.write_text("被替换的内容", encoding="utf-8")
    ok, actual = verify_file_hash(path, digest)
    assert not ok and actual != digest


def test_store_reports_duplicate_and_parse_issues(tmp_path):
    store = write_store(tmp_path)
    with store.claims_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"claim_id": "C_FIN_REV_2026H1", "claim": "重复定义", "materiality": "normal"}, ensure_ascii=False) + "\n")
        fh.write("{不是合法 JSON\n")
    reloaded = EvidenceStore.open(tmp_path / "evidence")
    codes = [i.code for i in reloaded.issues]
    assert "EVIDENCE_DUPLICATE_ID" in codes
    assert "EVIDENCE_PARSE" in codes


def test_state_integrity_flags_missing_document():
    state = base_state()
    state.links[0].document_id = "DOC_not_exist"
    codes = [i.code for i in state.check_integrity()]
    assert "EVIDENCE_DOC_MISSING" in codes


def test_state_integrity_flags_orphan_link():
    state = base_state()
    state.links[0].claim_id = "C_NOT_REGISTERED"
    codes = [i.code for i in state.check_integrity()]
    assert "EVIDENCE_CLAIM_MISSING" in codes


def test_independent_source_count_collapses_shared_group():
    state = base_state()
    state.add_document(
        make_document("DOC_cls_reprint", source_type="media", source_group="CLS_20260915_001", url="https://x/cls", title="转载")
    )
    state.add_link(
        make_link("C_VAL_CONSENSUS", "DOC_cls_reprint", page=None, section="正文", support_type="context")
    )
    # DOC_cls_media 与 DOC_cls_reprint 同源（CLS_20260915_001）→ 只算 1 个独立来源
    assert state.independent_source_count("C_VAL_CONSENSUS") == 1


def test_json_serialization_roundtrip():
    doc = make_document()
    assert SourceDocument.from_dict(doc.to_dict()) == doc
    claim = make_claim()
    assert Claim.from_dict(claim.to_dict()) == claim
    link = make_link()
    assert EvidenceLink.from_dict(link.to_dict()) == link
