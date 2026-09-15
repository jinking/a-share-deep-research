#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""attach_local_evidence.py 回归测试（v3.0 §17 DoD：正常 Case + 失败 Case）。

重点验证「防脑补硬闸」：evidence_text 必须是本地原文的真实子串，
以及两阶段执行带来的原子性（任何一条不通过就整体不落盘）。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT), str(ROOT / "scripts"), str(Path(__file__).resolve().parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from attach_local_evidence import apply_plan, text_supports_excerpt  # noqa: E402
from core.evidence import EvidenceStore  # noqa: E402
from helpers import make_claim, make_document  # noqa: E402


# ---------------------------------------------------------------- 防脑补硬闸


def test_excerpt_must_be_verbatim(tmp_path):
    f = tmp_path / "半年报.txt"
    f.write_text("营业收入 28.63 亿元，同比 -5.97%\n", encoding="utf-8")

    ok, why = text_supports_excerpt("营业收入 28.63 亿元", f)
    assert ok, why

    # 改一个数字就不再是原文子串 —— 必须拒绝
    ok, why = text_supports_excerpt("营业收入 28.64 亿元", f)
    assert not ok
    assert "臆造" in why


def test_excerpt_tolerates_whitespace_only(tmp_path):
    f = tmp_path / "t.txt"
    f.write_text("| 2026-09-14 | 71.39 |\n", encoding="utf-8")
    ok, why = text_supports_excerpt("| 2026-09-14   |    71.39 |", f)
    assert ok, why


def test_binary_file_skips_excerpt_check(tmp_path):
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    ok, why = text_supports_excerpt("无论如何都无从比对", pdf)
    assert ok
    assert "跳过" in why


# ---------------------------------------------------------------- apply_plan


def make_store(tmp_path: Path) -> EvidenceStore:
    """一个 Claim + 一个「无 url 也无 local_path」的 Document（迁移后的典型状态）。"""
    store = EvidenceStore.init(tmp_path / "evidence")
    store.add_claim(make_claim(claim_id="C1", materiality="critical", level="fact"))
    store.documents["DOC_old"] = make_document("DOC_old", url=None, local_path=None)
    store.save()
    return store


def test_apply_plan_binds_existing_and_creates_new(tmp_path):
    store = make_store(tmp_path)
    src = tmp_path / "src"
    src.mkdir()
    (src / "kline.txt").write_text("| 2026-09-14 | 63.99 | 71.39 |\n", encoding="utf-8")
    (src / "dv.txt").write_text("| 20251231 | 5.00 |\n", encoding="utf-8")

    plan = {
        "documents": [
            {"key": "k", "document_id": "DOC_old", "local_file": str(src / "kline.txt")},
            {
                "key": "d",
                "source_type": "official_database",
                "title": "分红数据",
                "local_file": str(src / "dv.txt"),
            },
        ],
        "links": [
            {
                "evidence_id": "EV_C1_01",
                "claim_id": "C1",
                "document_id": "DOC_old",
                "section": "日线行情表",
                "evidence_text": "| 2026-09-14 | 63.99 | 71.39 |",
            },
            {
                "evidence_id": "EV_C1_02",
                "claim_id": "C1",
                "document_key": "d",
                "section": "分红历史",
                "evidence_text": "| 20251231 | 5.00 |",
            },
        ],
    }

    ok, stats = apply_plan(store, plan, base_dir=tmp_path)

    assert ok, stats
    assert stats == {
        "documents_bound": 1,
        "documents_created": 1,
        "links_updated": 0,
        "links_added": 2,
    }

    bound = store.documents["DOC_old"]
    assert bound.local_path == "raw/kline.txt"
    assert bound.sha256
    assert (tmp_path / "evidence" / "raw" / "kline.txt").is_file()

    assert len(store.links) == 2
    created_link = next(l for l in store.links if l.evidence_id == "EV_C1_02")
    assert store.documents[created_link.document_id].local_path == "raw/dv.txt"


def test_apply_plan_rejects_fabricated_excerpt(tmp_path):
    store = make_store(tmp_path)
    src = tmp_path / "kline.txt"
    src.write_text("| 2026-09-14 | 63.99 | 71.39 |\n", encoding="utf-8")

    plan = {
        "documents": [{"key": "k", "document_id": "DOC_old", "local_file": str(src)}],
        "links": [
            {
                "evidence_id": "EV_C1_01",
                "claim_id": "C1",
                "document_id": "DOC_old",
                "section": "日线行情表",
                # 收盘价被"润色"成 99.99 —— 原文里没有
                "evidence_text": "| 2026-09-14 | 63.99 | 99.99 |",
            }
        ],
    }

    ok, stats = apply_plan(store, plan, base_dir=tmp_path)

    assert not ok
    assert stats["links_added"] == 0
    # 原子性：Document 也没被绑定
    assert store.documents["DOC_old"].local_path is None
    assert store.documents["DOC_old"].sha256 is None


def test_apply_plan_atomic_when_one_entry_invalid(tmp_path):
    """一条合法 + 一条引用不存在的 Claim → 合法那条也不得生效。"""
    store = make_store(tmp_path)
    src = tmp_path / "kline.txt"
    src.write_text("| 2026-09-14 | 63.99 | 71.39 |\n", encoding="utf-8")

    plan = {
        "documents": [{"key": "k", "document_id": "DOC_old", "local_file": str(src)}],
        "links": [
            {
                "evidence_id": "EV_C1_01",
                "claim_id": "C1",
                "document_id": "DOC_old",
                "section": "日线行情表",
                "evidence_text": "| 2026-09-14 | 63.99 | 71.39 |",
            },
            {
                "evidence_id": "EV_GHOST_01",
                "claim_id": "C_NOT_EXIST",
                "document_id": "DOC_old",
                "evidence_text": "| 2026-09-14 | 63.99 | 71.39 |",
            },
        ],
    }

    ok, _ = apply_plan(store, plan, base_dir=tmp_path)

    assert not ok
    assert store.links == []
    assert store.documents["DOC_old"].local_path is None


def test_apply_plan_rejects_excerpt_without_local_file(tmp_path):
    """给了摘录却没绑本地文件 —— 无法验证真实性，必须拒绝。"""
    store = make_store(tmp_path)
    plan = {
        "links": [
            {
                "evidence_id": "EV_C1_01",
                "claim_id": "C1",
                "document_id": "DOC_old",
                "section": "主要会计数据",
                "evidence_text": "营业收入 28.63 亿元",
            }
        ]
    }

    ok, _ = apply_plan(store, plan, base_dir=tmp_path)

    assert not ok
    assert store.links == []


def test_dry_run_makes_no_changes(tmp_path):
    store = make_store(tmp_path)
    src = tmp_path / "kline.txt"
    src.write_text("| 2026-09-14 | 63.99 | 71.39 |\n", encoding="utf-8")

    plan = {
        "documents": [{"key": "k", "document_id": "DOC_old", "local_file": str(src)}],
        "links": [
            {
                "evidence_id": "EV_C1_01",
                "claim_id": "C1",
                "document_id": "DOC_old",
                "section": "日线行情表",
                "evidence_text": "| 2026-09-14 | 63.99 | 71.39 |",
            }
        ],
    }

    ok, stats = apply_plan(store, plan, dry_run=True, base_dir=tmp_path)

    assert ok
    assert stats["documents_bound"] == 1 and stats["links_added"] == 1
    assert store.documents["DOC_old"].local_path is None
    assert store.links == []
    assert not (tmp_path / "evidence" / "raw" / "kline.txt").exists()


def test_apply_plan_updates_existing_link(tmp_path):
    """已存在的 evidence_id → 就地补定位与摘录，而不是新增一条。"""
    store = make_store(tmp_path)
    src = tmp_path / "kline.txt"
    src.write_text("| 2026-09-14 | 63.99 | 71.39 |\n", encoding="utf-8")

    # 先造一条无定位的 link（模拟迁移产物）
    store.documents["DOC_old"].local_path = "raw/kline.txt"
    store.documents["DOC_old"].sha256 = "x"
    from core.models.evidence import EvidenceLink

    store.links.append(
        EvidenceLink(evidence_id="EV_C1_01", claim_id="C1", document_id="DOC_old", support_type="direct")
    )
    store.save()

    plan = {
        "documents": [{"key": "k", "document_id": "DOC_old", "local_file": str(src)}],
        "links": [
            {
                "evidence_id": "EV_C1_01",
                "claim_id": "C1",
                "document_id": "DOC_old",
                "section": "日线行情表",
                "table": "近 60 个交易日",
                "evidence_text": "| 2026-09-14 | 63.99 | 71.39 |",
                "support_type": "partial",
            }
        ],
    }

    ok, stats = apply_plan(store, plan, base_dir=tmp_path)

    assert ok
    assert stats["links_updated"] == 1 and stats["links_added"] == 0
    assert len(store.links) == 1
    link = store.links[0]
    assert link.section == "日线行情表"
    assert link.evidence_text == "| 2026-09-14 | 63.99 | 71.39 |"
    assert link.support_type == "partial"
