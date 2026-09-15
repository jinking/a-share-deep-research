# -*- coding: utf-8 -*-
"""v2 → v3 迁移脚本（v3.0 §14、§9.1 Evidence/迁移）。"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from core.evidence import EvidenceStore
from core.validation import validate_evidence
from helpers import RESEARCH_DATE

ROOT = Path(__file__).resolve().parents[2]
SAMPLE_V2 = ROOT / "examples" / "意华股份002897_样板" / "research_manifest.json"

# 精简副本（例如技能安装目录）可能不带 examples/，此时跳过整个迁移集成测试
pytestmark = pytest.mark.skipif(
    not SAMPLE_V2.exists(), reason=f"缺少真实样板 {SAMPLE_V2}（examples/ 未随包分发）"
)


def _migrator():
    spec = importlib.util.spec_from_file_location(
        "migrator_v2_to_v3", ROOT / "scripts" / "migrate_manifest_v2_to_v3.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def migrator():
    return _migrator()


def test_level_mapping(migrator):
    assert migrator.map_level("事实") == ("fact", None)
    assert migrator.map_level("管理层口径") == ("management_statement", None)
    assert migrator.map_level("已确认订单") == ("confirmed_order", None)
    assert migrator.map_level("已批量交付") == ("batch_delivery", None)


def test_unknown_level_degrades_to_unconfirmed_with_reason(migrator):
    level, why = migrator.map_level("相当确定的那种")
    assert level == "unconfirmed"
    assert why


def test_canonical_title_collapses_same_document_variants(migrator):
    a = migrator.canonical_title("意华股份 2026 年半年度报告·分行业经营情况")
    b = migrator.canonical_title("意华股份 2026 年半年度报告·现金流量表")
    c = migrator.canonical_title("意华股份 2026 年半年度报告（未经审计）")
    assert a == b == c


def test_migrate_without_evidence_dir_only_writes_manifest(migrator, tmp_path):
    data = json.loads(SAMPLE_V2.read_text(encoding="utf-8"))
    v3, stats = migrator.migrate(data)
    assert v3["manifest_version"] == 3
    assert len(v3["evidence_refs"]) == len(data["evidence"])
    assert all(r["importance"] == "normal" for r in v3["evidence_refs"])
    assert stats["claims"] == 0  # 未指定 evidence_dir 时不建库
    assert v3["meta"]["research_date"] == data["meta"]["research_date"]


def test_migrate_with_evidence_dir_builds_store(migrator, tmp_path):
    data = json.loads(SAMPLE_V2.read_text(encoding="utf-8"))
    evidence_dir = tmp_path / "evidence"
    v3, stats = migrator.migrate(data, evidence_dir=evidence_dir, research_date=RESEARCH_DATE)
    store = EvidenceStore.open(evidence_dir)
    assert stats["claims"] == len(data["evidence"])
    assert len(store.claims) == len(data["evidence"])
    assert len(store.links) == len(data["evidence"])
    # 半年报的多个视角（主要会计数据 / 分行业 / 现金流量表 …）应收敛到同一份 Document
    assert 1 <= len(store.documents) < len(data["evidence"])
    assert v3["meta"]["evidence_dir"] == "evidence"


def test_migration_marks_needs_verification(migrator, tmp_path):
    data = json.loads(SAMPLE_V2.read_text(encoding="utf-8"))
    evidence_dir = tmp_path / "evidence"
    migrator.migrate(data, evidence_dir=evidence_dir)
    store = EvidenceStore.open(evidence_dir)
    assert all(c.migration_status == "needs_verification" for c in store.claims.values())
    assert all(d.migration_status == "needs_verification" for d in store.documents.values())
    assert all(l.migration_status == "needs_verification" for l in store.links)
    assert all(c.status == "pending" for c in store.claims.values())


def test_migration_never_claims_evidence_verified(migrator, tmp_path):
    """迁移产物不得被自动当成「已验证」：critical 必须人工补 locator 后才可能通过。"""
    data = json.loads(SAMPLE_V2.read_text(encoding="utf-8"))
    evidence_dir = tmp_path / "evidence"
    migrator.migrate(data, evidence_dir=evidence_dir, critical_ids=["E001", "E007"])
    store = EvidenceStore.open(evidence_dir)
    assert store.claims["E001"].materiality == "critical"

    bucket = []
    validate_evidence(
        store.state(),
        emit=lambda s, c, m, d="": bucket.append((s, c)),
        research_date=RESEARCH_DATE,
        documents_base_dir=str(evidence_dir),
        store_issues=store.issues,
    )
    codes = [c for _, c in bucket]
    # 迁移出的 critical Claim 没有 locator / evidence_text，必须被拦下
    assert "EVIDENCE_LOCATOR_MISSING" in codes
    assert "EVIDENCE_TEXT_MISSING" in codes
    # 但不应该有「引用不存在的 Document」这类结构性错误
    assert "EVIDENCE_DOC_MISSING" not in codes


def test_migrated_store_passes_integrity(migrator, tmp_path):
    data = json.loads(SAMPLE_V2.read_text(encoding="utf-8"))
    evidence_dir = tmp_path / "evidence"
    migrator.migrate(data, evidence_dir=evidence_dir)
    store = EvidenceStore.open(evidence_dir)
    assert [i.code for i in store.issues] == []
    assert store.state().check_integrity() == []
