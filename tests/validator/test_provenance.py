#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Provider ≠ Source（v3.0.2 §8）与来源独立性合并。

对应 §15 测试计划 C（Provenance，8 例）。

核心命题：`westock-data` / `neodata` 是取数服务商，不是来源。搬运不产生一手性。
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
from core.evidence.independence import group_documents, independent_source_count
from core.models import EvidenceModelError, SourceDocument
from core.models.claim import PRIMARY_REQUIRED_LEVELS
from core.models.provenance import (
    default_source_type_for,
    is_data_vendor_provider,
    normalize_provider,
)
from helpers import make_claim, make_document, make_link


# --------------------------------------------------------------------------- #
# 1–2. westock 默认落 data_vendor；data_vendor 不是一手来源
# --------------------------------------------------------------------------- #


def test_westock_provider_defaults_to_data_vendor():
    assert default_source_type_for("westock-data") == "data_vendor"
    assert default_source_type_for("westock-data(kline)") == "data_vendor"
    assert default_source_type_for("neodata") == "data_vendor"


def test_unknown_provider_keeps_caller_default():
    """未知 provider 不得因为「看起来像官方」就被升级。"""
    assert default_source_type_for(None, "company_announcement") == "company_announcement"
    assert default_source_type_for("cninfo(巨潮资讯网)", "company_announcement") == "company_announcement"


def test_data_vendor_is_not_primary_source():
    doc = make_document(provider="westock-data", source_type="data_vendor")
    assert doc.is_data_vendor is True
    assert doc.is_primary is False
    # 确认级 Claim 依赖的一手来源集合不含 data_vendor → 无法独立支撑
    assert "data_vendor" not in PRIMARY_REQUIRED_LEVELS
    assert not doc.is_primary


# --------------------------------------------------------------------------- #
# 3. 声明了官方上游：上游关系照写，但一手性不会转移给服务商（v3.0.3 §7 收严）
# --------------------------------------------------------------------------- #


def test_data_vendor_with_declared_upstream_stays_non_primary():
    """v3.0.2 曾允许「声明 upstream 后服务商自称一手」——v3.0.3 已废弃该通行证。

    服务商只能写 data_vendor / third_party_database，且永远不是一手来源；
    一手性属于上游那份官方原件本身。详见 tests/validator/test_provider_primary.py。
    """
    doc = make_document(
        provider="westock-data",
        source_type="data_vendor",
        upstream_source_type="exchange_filing",
        upstream_document_id="DOC_exch01",
    )
    doc.validate()  # 不抛异常：上游关系本身是允许写的
    assert doc.has_declared_upstream is True
    assert doc.is_primary is False

    upgraded = make_document(
        provider="westock-data",
        source_type="exchange_filing",
        upstream_source_type="exchange_filing",
        upstream_document_id="DOC_exch01",
    )
    with pytest.raises(EvidenceModelError) as exc:
        upgraded.validate()
    assert "Provider" in str(exc.value)


# --------------------------------------------------------------------------- #
# 4. 同一上游只算一个独立来源
# --------------------------------------------------------------------------- #


def test_same_upstream_collapses_to_one_independent_source():
    """westock-data + 公司公告：来自同一官方原件 → 只能算一个独立来源。

    v3.0.3 §7 起，**外部**上游编号写在 `upstream_external_id`；
    `upstream_document_id` 专用于本库 Document（写悬空 ID 会被报 P1）。
    """
    announcement = make_document(
        "DOC_ann001",
        source_type="company_announcement",
        source_group="CNINFO_002897_2026H1",
    )
    vendor = make_document(
        "DOC_vendor01",
        source_type="data_vendor",
        provider="westock-data",
        source_group="WESTOCK_KLINE_002897",
        upstream_external_id="CNINFO_002897_2026H1",
    )
    docs = [announcement, vendor]
    groups = group_documents(docs)
    assert independent_source_count(docs) == 1, groups
    assert set(groups["CNINFO_002897_2026H1"]) == {"DOC_ann001", "DOC_vendor01"}


def test_upstream_chain_resolves_transitively():
    """上游不在库中时，外部上游 ID 就是合并键 —— 「同一份被引用的原件」仍然合并。"""
    a = make_document("DOC_a", source_group="SRC_A", upstream_external_id="CNINFO_X")
    b = make_document("DOC_b", source_group="SRC_B", upstream_external_id="CNINFO_X")
    c = make_document("DOC_c", source_group="CNINFO_X")  # 原件本身在库中
    assert independent_source_count([a, b]) == 1
    assert independent_source_count([a, b, c]) == 1


def test_truly_independent_sources_stay_two():
    announcement = make_document("DOC_ann001", source_group="CNINFO_A")
    media = make_document("DOC_media01", source_type="media", source_group="CLS_B")
    assert independent_source_count([announcement, media]) == 2


# --------------------------------------------------------------------------- #
# 5–6. provider != source；broker 不是一手来源
# --------------------------------------------------------------------------- #


def test_normalize_provider_strips_parenthetical_suffix():
    assert normalize_provider("westock-data(kline)") == "westock-data"
    assert normalize_provider(" Westock-Data （dividend）") == "westock-data"
    assert normalize_provider(None) == ""
    assert is_data_vendor_provider("neodata") is True
    assert is_data_vendor_provider("cninfo(巨潮资讯网)") is False


def test_broker_report_is_not_primary_source():
    doc = make_document("DOC_broker01", source_type="broker_report")
    assert doc.is_primary is False


# --------------------------------------------------------------------------- #
# 7–8. official_database 只有非服务商才能用；错误升级必须 FAIL
# --------------------------------------------------------------------------- #


def test_official_database_without_vendor_provider_is_primary():
    doc = make_document("DOC_exch01", source_type="official_database")
    doc.validate()
    assert doc.is_primary is True


def test_vendor_claiming_primary_without_upstream_is_rejected():
    doc = make_document(provider="westock-data", source_type="official_database")
    with pytest.raises(EvidenceModelError) as exc:
        doc.validate()
    assert "Provider" in str(exc.value)


def test_store_load_surfaces_upgraded_provider_as_p1(tmp_path):
    """写进 documents.jsonl 的非法来源声明，必须变成可阻断的 P1。"""
    from core.validation import validate_evidence

    root = tmp_path / "evidence"
    store = EvidenceStore.init(root)
    store.register_document(
        source_type="official_database",
        title="westock-data 冒充一手来源",
        url="https://example.com/kline",
    )
    store.save()  # 先落盘，再模拟历史脏数据
    # 绕过模型校验直接把 provider 塞进 JSONL（模拟历史脏数据）
    import json

    rows = []
    for line in store.documents_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            row["provider"] = "westock-data"
            rows.append(row)
    store.documents_path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8"
    )

    reopened = EvidenceStore.open(root)
    assert any(i.code == "EVIDENCE_MODEL_INVALID" for i in reopened.issues), reopened.issues

    bucket = []
    summary = validate_evidence(
        reopened.state(),
        emit=lambda s, c, m, d="": bucket.append((s, c)),
        strict=True,
        store_issues=reopened.issues,   # Store 装载期的字段非法同样必须进入结论
    )
    assert summary["P1"] >= 1
    assert "EVIDENCE_MODEL_INVALID" in [c for _, c in bucket]


# --------------------------------------------------------------------------- #
# 端到端：westock 数据不能独立支撑确认级订单
# --------------------------------------------------------------------------- #


def test_data_vendor_cannot_support_confirmed_order(tmp_path):
    """data_vendor 单独支撑 confirmed_order → EVIDENCE_PRIMARY_REQUIRED（P0）。"""
    from core.validation import validate_evidence

    root = tmp_path / "evidence"
    store = EvidenceStore.init(root)
    store.register_document(
        source_type="data_vendor",
        title="westock-data 订单快照",
        url="https://example.com/order",
        provider="westock-data",
        source_group="WESTOCK_ORDER_002897",
    )
    doc_id = next(iter(store.documents))
    store.add_claim(
        make_claim(
            "C_ORDER_CONFIRMED",
            claim="已确认订单 3 亿元",
            category="order",
            level="confirmed_order",
            materiality="critical",
        )
    )
    store.add_link(make_link("C_ORDER_CONFIRMED", doc_id, page=1, note="仅服务商口径"))
    store.save()

    bucket = []
    summary = validate_evidence(
        EvidenceStore.open(root).state(), emit=lambda s, c, m, d="": bucket.append((s, c))
    )
    codes = [c for _, c in bucket]
    assert "EVIDENCE_PRIMARY_REQUIRED" in codes
    assert "EVIDENCE_DIRECT_REQUIRED" in codes
    assert summary["P0"] >= 2
