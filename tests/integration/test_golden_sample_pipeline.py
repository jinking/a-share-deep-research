#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sprint 4a 端到端：v2 manifest → v3 迁移 → 绑定本地原件 → 证据校验。

验证「证据链真的能跑」：
迁移出来的 critical Claim 一开始必然缺定位与摘录（P1），
绑定真实原文并补全 hash / locator / 摘录后，这些 P1 应当消失。

这是一条**可重复执行**的链路，不依赖 examples/ 目录，可在 CI 中跑。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for _p in (str(ROOT), str(ROOT / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from attach_local_evidence import apply_plan  # noqa: E402
from core.evidence import EvidenceStore  # noqa: E402
from core.validation import validate_evidence  # noqa: E402
from migrate_manifest_v2_to_v3 import migrate  # noqa: E402

RESEARCH_DATE = "2026-09-14"

V2_MANIFEST = {
    "meta": {"company": "测试公司", "code": "002897.SZ", "research_date": RESEARCH_DATE},
    "forecast": {},
    "valuation": {},
    "sotp": {},
    "quarterly_tracking": [],
    "final": {},
    "evidence": [
        {
            "claim_id": "E001",
            "claim": "2026-09-14 收盘 71.39 元",
            "level": "事实",
            "source_type": "official_database",
            "source_title": "交易所日线行情数据",
            "source_date": RESEARCH_DATE,
            "source_ref": "westock-data kline sz002897",
        }
    ],
}

# 本地一手原件（真实存在的那两行）
KLINE = "| 2026-09-14 | 63.99 | 71.39 | 71.39 | 61.04 | 244364 | 1621049895 | 13.25 |\n"


def codes_of(store: EvidenceStore):
    issues = []
    validate_evidence(
        store.state(research_date=RESEARCH_DATE),
        emit=lambda s, c, m, d="": issues.append((s, c, m, d)),
        documents_base_dir=str(store.root),
        research_date=RESEARCH_DATE,
    )
    return [c for _, c, _, _ in issues]


def test_migration_then_attach_clears_evidence_gaps(tmp_path):
    ev_dir = tmp_path / "evidence"

    # ---------- 1) v2 → v3 ----------
    v3, stats = migrate(V2_MANIFEST, evidence_dir=ev_dir, critical_ids=["E001"])
    assert stats["claims"] == 1 and stats["links"] == 1
    assert v3["manifest_version"] == 3
    assert v3["evidence_refs"] == [{"claim_id": "E001", "importance": "critical"}]

    store = EvidenceStore.open(ev_dir)
    claim = store.claims["E001"]
    assert claim.migration_status == "needs_verification"
    assert claim.materiality == "critical"
    assert claim.level == "fact"

    doc_id = next(iter(store.documents))
    doc = store.documents[doc_id]
    assert doc.local_path is None and doc.url is None and doc.sha256 is None

    # ---------- 2) 迁移后：必然有缺口 ----------
    before = codes_of(store)
    assert "EVIDENCE_NO_SOURCE" in before, before
    assert "EVIDENCE_LOCATOR_MISSING" in before, before
    assert "EVIDENCE_TEXT_MISSING" in before, before

    # ---------- 3) 绑定真实原件并补全定位/摘录 ----------
    raw = tmp_path / "kline.txt"
    raw.write_text(KLINE, encoding="utf-8")

    plan = {
        "documents": [
            {
                "key": "k",
                "document_id": doc_id,
                "local_file": str(raw),
                "source_group": "WESTOCK_KLINE_002897",
            }
        ],
        "links": [
            {
                "evidence_id": "EV_E001_01",
                "claim_id": "E001",
                "document_id": doc_id,
                "section": "日线行情表",
                "table": "近 60 个交易日",
                "evidence_text": KLINE.strip(),
                "support_type": "direct",
            }
        ],
    }
    ok, astats = apply_plan(store, plan, base_dir=tmp_path)
    assert ok, astats
    assert astats == {
        "documents_bound": 1,
        "documents_created": 0,
        "links_updated": 1,
        "links_added": 0,
    }
    store.save()

    # ---------- 4) 重新读取：缺口应已消除 ----------
    reopened = EvidenceStore.open(ev_dir)
    bound = reopened.documents[doc_id]
    assert bound.local_path == "raw/kline.txt"
    assert bound.sha256 and len(bound.sha256) == 64
    assert (ev_dir / "raw" / "kline.txt").is_file()

    link = reopened.links[0]
    assert link.section == "日线行情表" and link.evidence_text == KLINE.strip()

    after = codes_of(reopened)
    for gone in ("EVIDENCE_NO_SOURCE", "EVIDENCE_LOCATOR_MISSING", "EVIDENCE_TEXT_MISSING"):
        assert gone not in after, f"{gone} 仍然存在: {after}"
    assert "EVIDENCE_HASH_MISMATCH" not in after


def test_evidence_file_replaced_is_detected(tmp_path):
    """证据文件被替换 → EVIDENCE_HASH_MISMATCH（P0），且与『文件缺失』不可混淆。"""
    ev_dir = tmp_path / "evidence"
    migrate(V2_MANIFEST, evidence_dir=ev_dir, critical_ids=["E001"])

    store = EvidenceStore.open(ev_dir)
    doc_id = next(iter(store.documents))
    raw = tmp_path / "kline.txt"
    raw.write_text(KLINE, encoding="utf-8")

    ok, _ = apply_plan(
        store,
        {
            "documents": [{"document_id": doc_id, "local_file": str(raw)}],
            "links": [
                {
                    "evidence_id": "EV_E001_01",
                    "claim_id": "E001",
                    "document_id": doc_id,
                    "section": "日线行情表",
                    "evidence_text": KLINE.strip(),
                }
            ],
        },
        base_dir=tmp_path,
    )
    assert ok
    store.save()
    assert "EVIDENCE_HASH_MISMATCH" not in codes_of(EvidenceStore.open(ev_dir))

    # 篡改 raw/ 里的副本
    (ev_dir / "raw" / "kline.txt").write_text("| 2026-09-14 | 63.99 | 99.99 |\n", encoding="utf-8")

    tampered = codes_of(EvidenceStore.open(ev_dir))
    assert "EVIDENCE_HASH_MISMATCH" in tampered
