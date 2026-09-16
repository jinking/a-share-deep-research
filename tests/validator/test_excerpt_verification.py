#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""摘录验证状态（v3.0.2 §9）与原子落盘 / 时间模型 / load 幂等。

对应 §15 测试计划 D（PDF Verification，8 例）与 E（Atomic Store / Time）。

核心命题：「跳过校验」不等于「校验通过」。一条 PDF 摘录在没有任何可比对文本时，
状态必须是 unverified；critical Claim 带着未验证摘录 = P1，禁止交付。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for _p in (str(ROOT), str(ROOT / "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core.evidence import EvidenceStore
from core.evidence.excerpt import (
    compute_excerpt_verification,
    resolve_verification_source,
    stamp_excerpt_verification,
    verify_excerpt_against_text,
)
from core.evidence.verbatim import excerpt_in_file, text_supports_excerpt
from core.models import Claim, EvidenceModelError, EvidenceLink, SourceDocument
from core.validation import validate_evidence
from helpers import make_claim, make_link


TEXT = "营业收入 2,863,000,000 元，同比下降 5.97%\n"

# --------------------------------------------------------------------------- #
# 构件
# --------------------------------------------------------------------------- #


def _store_with_pdf(tmp_path, *, with_textlayer: bool, excerpt: str | None = None):
    store = EvidenceStore.init(tmp_path / "evidence")
    raw = store.raw_dir
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "1225497942.pdf").write_bytes(b"%PDF-1.4\n% stub\n")
    if with_textlayer:
        (raw / "1225497942.textlayer.txt").write_text(TEXT, encoding="utf-8")

    doc = store.register_document(
        source_type="interim_report",
        title="意华股份 2026 年半年度报告",
        published_at="2026-08-25",
        local_path="raw/1225497942.pdf",
        source_group="CNINFO_002897_2026H1",
        page_count=163,
    )
    store.add_claim(
        make_claim("C_FIN_REV", materiality="critical", level="fact", status="supported")
    )
    store.add_link(
        make_link(
            "C_FIN_REV",
            doc.document_id,
            page=8,
            section="主要会计数据",
            evidence_text=(TEXT.strip() if excerpt is None else excerpt),
        )
    )
    return store, doc


# --------------------------------------------------------------------------- #
# 1. 纯文本 → direct_text → verified
# --------------------------------------------------------------------------- #


def test_plain_text_is_verified_by_direct_text(tmp_path):
    store = EvidenceStore.init(tmp_path / "evidence")
    (store.raw_dir / "kline.txt").write_text(TEXT, encoding="utf-8")
    doc = store.register_document(
        source_type="data_vendor",
        title="westock-data 日行情",
        local_path="raw/kline.txt",
        provider="westock-data",
    )
    store.add_claim(make_claim("C1", materiality="critical"))
    store.add_link(make_link("C1", doc.document_id, evidence_text=TEXT.strip(), page=None, section="日线行情表"))

    counts = stamp_excerpt_verification(store)
    assert counts == {"verified": 1, "unverified": 0, "skipped": 0}
    link = store.links[0]
    assert link.excerpt_verification_status == "verified"
    assert link.excerpt_verification_method == "direct_text"
    assert link.excerpt_verification_source == "raw/kline.txt"


# --------------------------------------------------------------------------- #
# 2. PDF 无文本层 → unverified（不得当成「跳过=通过」）
# --------------------------------------------------------------------------- #


def test_pdf_without_textlayer_is_unverified(tmp_path):
    store, doc = _store_with_pdf(tmp_path, with_textlayer=False)

    path, method = resolve_verification_source(doc, store.root)
    assert (path, method) == (None, None)

    counts = stamp_excerpt_verification(store)
    assert counts == {"verified": 0, "unverified": 1, "skipped": 0}
    assert store.links[0].excerpt_verification_status == "unverified"
    assert store.links[0].excerpt_verification_method is None


def test_pdf_without_textlayer_blocks_critical_claim(tmp_path):
    """PDF 摘录无文本层可比对 → critical Claim 报 P1 EVIDENCE_EXCERPT_UNVERIFIED。"""
    store, _ = _store_with_pdf(tmp_path, with_textlayer=False)
    stamp_excerpt_verification(store)

    bucket = []
    summary = validate_evidence(store.state(), emit=lambda s, c, m, d="": bucket.append((s, c)))
    assert ("P1", "EVIDENCE_EXCERPT_UNVERIFIED") in bucket
    assert summary["P1"] >= 1


# --------------------------------------------------------------------------- #
# 3. PDF + 文本层 → verified
# --------------------------------------------------------------------------- #


def test_pdf_with_textlayer_is_verified(tmp_path):
    store, doc = _store_with_pdf(tmp_path, with_textlayer=True)

    path, method = resolve_verification_source(doc, store.root)
    assert method == "text_layer" and path.name == "1225497942.textlayer.txt"

    counts = stamp_excerpt_verification(store)
    assert counts == {"verified": 1, "unverified": 0, "skipped": 0}
    link = store.links[0]
    assert link.excerpt_verification_status == "verified"
    assert link.excerpt_verification_method == "text_layer"
    assert link.excerpt_verification_source == "raw/1225497942.textlayer.txt"

    bucket = []
    validate_evidence(store.state(), emit=lambda s, c, m, d="": bucket.append((s, c)))
    assert all(c != "EVIDENCE_EXCERPT_UNVERIFIED" for _, c in bucket)


# --------------------------------------------------------------------------- #
# 4–5. 错误摘录 / 错误文本层 → FAIL
# --------------------------------------------------------------------------- #


def test_wrong_excerpt_is_unverified_and_blocks(tmp_path):
    store, _ = _store_with_pdf(tmp_path, with_textlayer=True, excerpt="营业收入 2,864,000,000 元")
    stamp_excerpt_verification(store)
    assert store.links[0].excerpt_verification_status == "unverified"

    bucket = []
    validate_evidence(store.state(), emit=lambda s, c, m, d="": bucket.append((s, c)))
    assert ("P1", "EVIDENCE_EXCERPT_UNVERIFIED") in bucket


def test_textlayer_missing_excerpt_is_unverified(tmp_path):
    """文本层存在但里面没有这段 —— 与「抽错原文」同样是硬失败，不因文件存在而放行。"""
    store, doc = _store_with_pdf(tmp_path, with_textlayer=True)
    (store.raw_dir / "1225497942.textlayer.txt").write_text("完全不相关的一段文字\n", encoding="utf-8")
    stamp_excerpt_verification(store)
    assert store.links[0].excerpt_verification_status == "unverified"

    bucket = []
    validate_evidence(store.state(), emit=lambda s, c, m, d="": bucket.append((s, c)))
    assert ("P1", "EVIDENCE_EXCERPT_UNVERIFIED") in bucket


# --------------------------------------------------------------------------- #
# 6–7. critical → P1；normal → 不阻断
# --------------------------------------------------------------------------- #


def test_critical_unverified_is_p1(tmp_path):
    """未声明状态同样按未验证处理 —— 否则「什么都不写」最省事。"""
    store = EvidenceStore.init(tmp_path / "evidence")
    (store.raw_dir / "a.txt").write_text(TEXT, encoding="utf-8")
    doc = store.register_document(source_type="media", title="媒体稿", local_path="raw/a.txt")
    store.add_claim(make_claim("C_CRIT", materiality="critical"))
    store.add_link(
        EvidenceLink(
            evidence_id="EV_C_CRIT_01",
            claim_id="C_CRIT",
            document_id=doc.document_id,
            page=1,
            evidence_text=TEXT.strip(),
        )
    )
    bucket = []
    summary = validate_evidence(store.state(), emit=lambda s, c, m, d="": bucket.append((s, c)))
    assert ("P1", "EVIDENCE_EXCERPT_UNVERIFIED") in bucket
    assert summary["P1"] >= 1


def test_normal_unverified_does_not_block(tmp_path):
    """normal Claim 的摘录未验证不阻断交付（v3.0.2 只对 critical 强制）。"""
    store = EvidenceStore.init(tmp_path / "evidence")
    (store.raw_dir / "a.txt").write_text(TEXT, encoding="utf-8")
    doc = store.register_document(source_type="media", title="媒体稿", local_path="raw/a.txt")
    store.add_claim(make_claim("C_NORM", materiality="normal"))
    store.add_link(
        EvidenceLink(
            evidence_id="EV_C_NORM_01",
            claim_id="C_NORM",
            document_id=doc.document_id,
            page=1,
            evidence_text=TEXT.strip(),
        )
    )
    bucket = []
    validate_evidence(store.state(), emit=lambda s, c, m, d="": bucket.append((s, c)))
    assert all(
        c != "EVIDENCE_EXCERPT_UNVERIFIED" for s, c in bucket if s in {"P0", "P1"}
    ), bucket


# --------------------------------------------------------------------------- #
# 8. 直接文本校验的边界：缺失文件 / 空摘录 / 无摘录
# --------------------------------------------------------------------------- #


def test_excerpt_in_file_is_strict_about_missing_and_binary(tmp_path):
    missing = tmp_path / "nope.txt"
    ok, why = excerpt_in_file("任意内容", missing)
    assert ok is False and "不存在" in why

    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    ok, why = excerpt_in_file("任意内容", pdf)
    assert ok is False and "无法做子串校验" in why
    # 与 attach 路径的既有语义形成对照：那里是「跳过」，这里必须是「不通过」
    loosened, loose_why = text_supports_excerpt("任意内容", pdf)
    assert loosened is True and "跳过" in loose_why

    blank = tmp_path / "a.txt"
    blank.write_text(TEXT, encoding="utf-8")
    ok, why = excerpt_in_file("   ", blank)
    assert ok is False and "为空" in why


def test_link_without_excerpt_has_no_verification_claim(tmp_path):
    store = EvidenceStore.init(tmp_path / "evidence")
    doc = store.register_document(source_type="media", title="媒体稿", url="https://example.com/a")
    link = EvidenceLink(
        evidence_id="EV_X_01", claim_id="C_X", document_id=doc.document_id, section="正文"
    )
    assert compute_excerpt_verification(link, doc, base_dir=store.root) is None
    assert stamp_excerpt_verification(store) == {"verified": 0, "unverified": 0, "skipped": 0}


# --------------------------------------------------------------------------- #
# 模型层：verified 必须说明手段；枚举必须固定
# --------------------------------------------------------------------------- #


def test_verified_requires_method_and_enums_are_closed():
    with pytest.raises(EvidenceModelError) as exc:
        EvidenceLink(
            evidence_id="EV_1", claim_id="C1", document_id="DOC_a",
            excerpt_verification_status="verified",
        ).validate()
    assert "method" in str(exc.value)

    with pytest.raises(EvidenceModelError):
        EvidenceLink(
            evidence_id="EV_1", claim_id="C1", document_id="DOC_a",
            excerpt_verification_status="maybe",
        ).validate()

    with pytest.raises(EvidenceModelError):
        EvidenceLink(
            evidence_id="EV_1", claim_id="C1", document_id="DOC_a",
            excerpt_verification_status="verified",
            excerpt_verification_method="vibes",
        ).validate()


def test_normalize_for_match_ignores_layout():
    assert verify_excerpt_against_text(
        "| 2026-09-14   |    71.39 |", "| 2026-09-14 | 71.39 |"
    )
    assert verify_excerpt_against_text("意华控股集团有\n限公司", "意华控股集团有限公司")
    assert not verify_excerpt_against_text("71.40", "| 2026-09-14 | 71.39 |")
