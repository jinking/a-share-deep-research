# -*- coding: utf-8 -*-
"""Provider 永远不能成为 Primary Source（v3.0.3 §7）。

v3.0.2 只堵住了「服务商自称一手来源」这一种写法，但留了一条缝：

    provider=westock-data + source_type=official_database + 随便声明一个 upstream_*
    → 放行，且 is_primary=True

于是「上游」变成了一句可以随口声明的话——只要写上它，取数服务商就重新拿到
一手来源资格，`EVIDENCE_PRIMARY_REQUIRED` 再次形同虚设。

v3.0.3 把这条缝焊死，并要求上游关系本身可核实：

1. `is_data_vendor` ⇒ `is_primary` 恒为 False（无例外，声明上游也不行）；
2. 服务商的 `source_type` 只允许 `data_vendor` / `third_party_database`；
3. `upstream_document_id` 指向本库 Document 时必须真实存在（P1 `EVIDENCE_UPSTREAM_UNKNOWN`）；
4. 需要保存**外部**上游 ID 时改用 `upstream_external_id`，不再与「本库对象 ID」混用一个字段。

对应 §12 测试计划 C（Provider / Primary，10 例）与 §15 验收「Vendor fake primary FAIL」。
"""

from __future__ import annotations

import json
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
from core.models.provenance import VENDOR_SOURCE_TYPES
from core.validation import validate_evidence
from helpers import make_claim, make_document, make_link

VENDOR = "westock-data"


def _codes(summary_bucket):
    return [c for _, c in summary_bucket]


def _validate_store(store):
    bucket = []
    summary = validate_evidence(
        store.state(),
        emit=lambda s, c, m, d="": bucket.append((s, c)),
        strict=True,
        store_issues=store.issues,
    )
    return summary, bucket


def _store(tmp_path, docs, *, claims=(), links=()):
    root = tmp_path / "evidence"
    store = EvidenceStore.init(root)
    for spec in docs:
        store.register_document(**spec)
    for claim in claims:
        store.add_claim(claim)
    for link in links:
        store.add_link(link)
    store.save()
    return EvidenceStore.open(root)


# --------------------------------------------------------------------------- #
# 1–5. 服务商只能是非一手：允许的写法通过，升级写法一律拒绝
# --------------------------------------------------------------------------- #


def test_vendor_allowed_source_types_are_non_primary():
    for source_type in sorted(VENDOR_SOURCE_TYPES):
        doc = make_document(source_type=source_type, provider=VENDOR)
        doc.validate()  # 不抛异常
        assert doc.is_data_vendor is True
        assert doc.is_primary is False, source_type


def test_westock_with_official_database_is_rejected():
    """§10.3 验收：westock-data + source_type=official_database 必须 FAIL。"""
    doc = make_document(source_type="official_database", provider=VENDOR)
    with pytest.raises(EvidenceModelError) as exc:
        doc.validate()
    assert "Provider" in str(exc.value)


def test_neodata_with_official_database_is_rejected():
    doc = make_document(source_type="official_database", provider="neodata")
    with pytest.raises(EvidenceModelError):
        doc.validate()


def test_vendor_with_declared_upstream_is_still_rejected():
    """声明 upstream 不再是通行证 —— 一手类型的 source_type 连写都不许写。"""
    doc = make_document(
        source_type="exchange_filing",
        provider=VENDOR,
        upstream_source_type="exchange_filing",
        upstream_document_id="DOC_exch01",
    )
    with pytest.raises(EvidenceModelError) as exc:
        doc.validate()
    assert "Provider" in str(exc.value)


def test_vendor_with_upstream_remains_non_primary():
    """上游关系照写，但一手性不会随之转移给服务商。"""
    doc = make_document(
        source_type="data_vendor",
        provider=VENDOR,
        upstream_source_type="exchange_filing",
        upstream_document_id="DOC_exch01",
    )
    doc.validate()
    assert doc.has_declared_upstream is True
    assert doc.is_primary is False


def test_vendor_cannot_fabricate_two_primaries():
    """两个服务商都自称 official_database：谁也升不上去，Primary 来源数仍为 0。"""
    docs = [
        make_document(f"DOC_v{i}", source_type="official_database", provider=VENDOR)
        for i in (1, 2)
    ]
    for doc in docs:
        with pytest.raises(EvidenceModelError):
            doc.validate()
    assert sum(1 for d in docs if d.is_primary) == 0


# --------------------------------------------------------------------------- #
# 6–8. 真正的一手来源不受影响；券商仍然不是
# --------------------------------------------------------------------------- #


def test_official_document_remains_primary():
    doc = make_document("DOC_ann01", source_type="company_announcement")
    doc.validate()
    assert doc.is_primary is True


def test_government_document_remains_primary():
    doc = make_document("DOC_gov01", source_type="government")
    assert doc.is_primary is True


def test_broker_report_remains_non_primary():
    doc = make_document("DOC_broker01", source_type="broker_report")
    assert doc.is_primary is False


def test_third_party_database_without_vendor_provider_is_non_primary():
    doc = make_document("DOC_tp01", source_type="third_party_database")
    assert doc.is_primary is False


# --------------------------------------------------------------------------- #
# 9. 服务商与它搬运的官方原件：只算一个独立来源，且只有原件是一手
# --------------------------------------------------------------------------- #


def test_vendor_and_official_sharing_upstream_count_once():
    official = make_document(
        "DOC_exch01", source_type="official_database", source_group="CNINFO_2026H1"
    )
    vendor = make_document(
        "DOC_vendor01",
        source_type="data_vendor",
        provider=VENDOR,
        source_group="WESTOCK_KLINE",
        upstream_document_id="DOC_exch01",
    )
    docs = [official, vendor]
    groups = group_documents(docs)
    assert independent_source_count(docs) == 1, groups
    assert sum(1 for d in docs if d.is_primary) == 1


def test_external_upstream_id_also_collapses_sources():
    """外部上游（不在本库）改用 `upstream_external_id`，合并语义不变。"""
    official = make_document("DOC_ann01", source_type="company_announcement",
                             source_group="CNINFO_2026H1")
    vendor = make_document(
        "DOC_vendor01",
        source_type="data_vendor",
        provider=VENDOR,
        source_group="WESTOCK_KLINE",
        upstream_external_id="CNINFO_2026H1",
    )
    docs = [official, vendor]
    groups = group_documents(docs)
    assert independent_source_count(docs) == 1, groups
    assert groups["CNINFO_2026H1"] == ["DOC_ann01", "DOC_vendor01"]


# --------------------------------------------------------------------------- #
# 10. 上游引用必须真实存在（P1），成环同样不能放过
# --------------------------------------------------------------------------- #


def test_unknown_local_upstream_is_p1(tmp_path):
    store = _store(
        tmp_path,
        [
            dict(
                document_id="DOC_a",
                source_type="data_vendor",
                title="服务商镜像",
                url="https://example.com/a",
                provider=VENDOR,
                upstream_document_id="DOC_does_not_exist",
            )
        ],
    )
    summary, bucket = _validate_store(store)
    assert "EVIDENCE_UPSTREAM_UNKNOWN" in _codes(bucket)
    assert summary["P1"] >= 1


def test_known_local_upstream_is_clean(tmp_path):
    store = _store(
        tmp_path,
        [
            dict(
                document_id="DOC_exch01",
                source_type="official_database",
                title="交易所原始数据",
                url="https://example.com/exch",
            ),
            dict(
                document_id="DOC_vendor01",
                source_type="data_vendor",
                title="服务商镜像",
                url="https://example.com/mirror",
                provider=VENDOR,
                upstream_document_id="DOC_exch01",
            ),
        ],
    )
    summary, bucket = _validate_store(store)
    assert "EVIDENCE_UPSTREAM_UNKNOWN" not in _codes(bucket)


def test_external_upstream_is_not_flagged_unknown(tmp_path):
    """显式写成 external 的上游不按「本库 Document」校验，不该误报。"""
    store = _store(
        tmp_path,
        [
            dict(
                document_id="DOC_vendor01",
                source_type="data_vendor",
                title="服务商镜像",
                url="https://example.com/mirror",
                provider=VENDOR,
                upstream_external_id="CNINFO_002897_2026H1",
            )
        ],
    )
    summary, bucket = _validate_store(store)
    assert "EVIDENCE_UPSTREAM_UNKNOWN" not in _codes(bucket)


def _cycle_store(tmp_path):
    """A ↔ B 互相声明对方为上游。"""
    return _store(
        tmp_path,
        [
            dict(
                document_id="DOC_a",
                source_type="data_vendor",
                title="A",
                url="https://example.com/a",
                upstream_document_id="DOC_b",
            ),
            dict(
                document_id="DOC_b",
                source_type="data_vendor",
                title="B",
                url="https://example.com/b",
                upstream_document_id="DOC_a",
            ),
        ],
    )


def test_upstream_cycle_is_flagged(tmp_path):
    _summary, bucket = _validate_store(_cycle_store(tmp_path))
    assert "EVIDENCE_UPSTREAM_UNKNOWN" in _codes(bucket)


def test_upstream_cycle_does_not_manufacture_independence(tmp_path):
    """互相引用不能伪装成两个独立来源 —— 整环只算一个。

    否则「双源确认」可以用两条互相转载的稿件满足，这正是要堵的口子。
    """
    docs = list(_cycle_store(tmp_path).documents.values())
    assert independent_source_count(docs) == 1, group_documents(docs)


def test_upstream_cycle_detail_names_the_cycle(tmp_path):
    store = _cycle_store(tmp_path)
    details = []
    validate_evidence(
        store.state(),
        emit=lambda s, c, m, d="": details.append(d),
        strict=True,
        store_issues=store.issues,
    )
    assert any("循环" in d for d in details), details


# --------------------------------------------------------------------------- #
# 11–12. 落盘的历史脏数据同样必须被拦住
# --------------------------------------------------------------------------- #


def test_stored_vendor_fake_primary_is_model_invalid(tmp_path):
    """直接改 JSONL 伪造一手声明：装载期就要报出来，不能等到有人调用 validate。"""
    root = tmp_path / "evidence"
    store = EvidenceStore.init(root)
    store.register_document(
        source_type="data_vendor",
        title="westock-data 镜像",
        url="https://example.com/kline",
        provider=VENDOR,
    )
    store.save()

    rows = []
    for line in store.documents_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        row["source_type"] = "official_database"  # 手工升级
        row["upstream_source_type"] = "official_database"
        rows.append(row)
    store.documents_path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8"
    )

    reopened = EvidenceStore.open(root)
    assert any(i.code == "EVIDENCE_MODEL_INVALID" for i in reopened.issues), reopened.issues
    summary, bucket = _validate_store(reopened)
    assert summary["P1"] >= 1
    assert "EVIDENCE_MODEL_INVALID" in _codes(bucket)


def test_vendor_cannot_back_a_confirmed_claim_even_with_upstream(tmp_path):
    """端到端：服务商（哪怕声明了上游）不能独立支撑确认级 Claim。"""
    summary, bucket = _validate_store(
        _store(
            tmp_path,
            [
                dict(
                    document_id="DOC_vendor01",
                    source_type="data_vendor",
                    title="服务商口径订单快照",
                    url="https://example.com/vendor",
                    provider=VENDOR,
                    upstream_external_id="CNINFO_2026H1",
                )
            ],
            claims=[
                make_claim(
                    "C_ORDER_CONFIRMED",
                    claim="已确认订单 3 亿元",
                    category="order",
                    level="confirmed_order",
                    materiality="critical",
                )
            ],
            links=[
                make_link(
                    "C_ORDER_CONFIRMED", "DOC_vendor01", page=1, note="服务商口径"
                )
            ],
        )
    )
    codes = _codes(bucket)
    assert "EVIDENCE_PRIMARY_REQUIRED" in codes
    assert "EVIDENCE_DIRECT_REQUIRED" in codes
    assert summary["P0"] >= 2
