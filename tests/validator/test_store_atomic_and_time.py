#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""原子落盘 / 时间模型完整性 / datetime 精度 / load 幂等（v3.0.2 §10–§13）。

对应 §15 测试计划 E（Atomic Store / Time，7 例）。

这里每一条都对应一个真实事故形态：

    save() 中途失败        → 证据库半新半旧，hash 与内容对不上
    load() 重复调用        → links 被 append 两遍，同一份证据被算两次
    formal v3 少写时点      → 时效校验静默退化
    published_at 只写日期   → 拿 00:00 冒充真实发布时间，凭空造出时点结论
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

from core.evidence import store as store_module
from core.evidence import EvidenceStore, EvidenceStoreError
from core.models import Claim, SourceDocument
from core.validation import validate_evidence
from core.validation.manifest_validator import validate_manifest_v3
from helpers import make_claim, make_document, make_link


def _seed(tmp_path) -> EvidenceStore:
    store = EvidenceStore.init(tmp_path / "evidence")
    store.register_document(
        source_type="interim_report",
        title="测试公司 2026 年半年度报告",
        published_at="2026-08-25",
        url="https://www.cninfo.com.cn/002897/2026H1.pdf",
        source_group="CNINFO_002897_2026H1",
    )
    store.add_claim(make_claim())
    store.add_link(make_link())
    return store


def _snapshot(root: Path):
    return {
        p.name: p.read_text(encoding="utf-8")
        for p in sorted(root.glob("*.jsonl"))
    }


# --------------------------------------------------------------------------- #
# A. 原子落盘成功
# --------------------------------------------------------------------------- #


def test_save_atomic_success_leaves_no_temp_files(tmp_path):
    store = _seed(tmp_path)
    store.save_atomic()

    root = store.root
    assert (root / "documents.jsonl").read_text(encoding="utf-8").strip()
    assert (root / "claims.jsonl").read_text(encoding="utf-8").strip()
    assert (root / "evidence_links.jsonl").read_text(encoding="utf-8").strip()
    # 不留 .tmp / .bak 残渣
    assert not list(root.glob("*.tmp"))
    assert not list(root.glob("*.bak"))

    reopened = EvidenceStore.open(root)
    assert reopened.summary() == {"candidates": 0, "documents": 1, "claims": 1, "links": 1}


# --------------------------------------------------------------------------- #
# B. 第 1 / 第 2 个文件暂存失败 → 原证据库完全不变
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("fail_on_name", ["candidates.jsonl", "documents.jsonl"])
def test_save_atomic_stage_failure_keeps_store_untouched(tmp_path, monkeypatch, fail_on_name):
    store = _seed(tmp_path)
    store.save()
    before = _snapshot(store.root)

    real_stage = store_module._stage_text

    def failing_stage(target: Path, text: str):
        if target.name == fail_on_name:
            raise OSError(f"模拟写盘失败: {target.name}")
        return real_stage(target, text)

    monkeypatch.setattr(store_module, "_stage_text", failing_stage)

    with pytest.raises(OSError):
        store.save_atomic()

    assert _snapshot(store.root) == before, "落盘失败后原证据库必须一字不变"
    assert not list(store.root.glob("*.tmp"))


# --------------------------------------------------------------------------- #
# C. replace 阶段失败 → 已替换的部分必须被回滚
# --------------------------------------------------------------------------- #


def test_save_atomic_replace_failure_rolls_back(tmp_path, monkeypatch):
    store = _seed(tmp_path)
    store.save()
    before = _snapshot(store.root)

    real_replace = store_module.os.replace
    calls = {"n": 0}

    def failing_replace(src, dst):
        # 第 1 次是「原文件 → .bak」（阶段 2），第 2 次才是真正换入新内容
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("模拟 os.replace 失败")
        return real_replace(src, dst)

    monkeypatch.setattr(store_module.os, "replace", failing_replace)

    with pytest.raises(OSError):
        store.save_atomic()

    assert _snapshot(store.root) == before, "replace 失败必须回滚到替换前的状态"
    assert not list(store.root.glob("*.tmp"))
    assert not list(store.root.glob("*.bak"))


# --------------------------------------------------------------------------- #
# D. raw 文件 staging 回滚
# --------------------------------------------------------------------------- #


def test_add_raw_file_is_staged_and_verified(tmp_path):
    store = _seed(tmp_path)
    src = tmp_path / "kline.txt"
    src.write_text("| 2026-09-14 | 71.39 |\n", encoding="utf-8")

    target = store.add_raw_file(src)
    assert target == store.raw_dir / "kline.txt"
    assert target.is_file()
    assert not store.staging_dir.exists() or not any(store.staging_dir.iterdir())


def test_add_raw_file_hash_mismatch_leaves_no_residue(tmp_path):
    store = _seed(tmp_path)
    src = tmp_path / "kline.txt"
    src.write_text("| 2026-09-14 | 71.39 |\n", encoding="utf-8")

    with pytest.raises(EvidenceStoreError):
        store.add_raw_file(src, expected_sha256="0" * 64)

    assert not (store.raw_dir / "kline.txt").exists()
    assert not store.staging_dir.exists() or not any(store.staging_dir.iterdir())


def test_add_raw_file_copy_failure_leaves_no_residue(tmp_path, monkeypatch):
    store = _seed(tmp_path)

    # 源文件不存在 → 直接拒绝，raw/ 与 staging 都不该出现任何东西
    with pytest.raises(EvidenceStoreError):
        store.add_raw_file(tmp_path / "missing-source.txt")

    def boom(*_a, **_k):
        raise OSError("模拟复制失败")

    monkeypatch.setattr(store_module.shutil, "copy2", boom)
    src = tmp_path / "a.txt"
    src.write_text("x", encoding="utf-8")
    with pytest.raises(OSError):
        store.add_raw_file(src)

    assert not (store.raw_dir / "a.txt").exists()
    assert not store.staging_dir.exists() or not any(store.staging_dir.iterdir())


# --------------------------------------------------------------------------- #
# E. load 幂等
# --------------------------------------------------------------------------- #


def test_load_is_idempotent(tmp_path):
    store = _seed(tmp_path)
    store.save()

    reopened = EvidenceStore.open(store.root)
    first = reopened.summary()
    assert first == {"candidates": 0, "documents": 1, "claims": 1, "links": 1}

    for _ in range(3):
        reopened.load()
        assert reopened.summary() == first
        assert len(reopened.links) == 1  # links 是 list，最容易在这里翻倍
        assert reopened.issues == []


# --------------------------------------------------------------------------- #
# F. published_at 的 datetime 精度
# --------------------------------------------------------------------------- #


def test_published_datetime_only_when_time_is_actually_written():
    day = make_document(published_at="2026-08-25")
    assert day.published_datetime is None           # 只知道到日
    assert day.published_date.isoformat() == "2026-08-25"

    precise = make_document(published_at="2026-08-25T18:30:00+08:00")
    assert precise.published_datetime is not None
    assert precise.published_date.isoformat() == "2026-08-25"
    precise.validate()  # datetime 形式必须合法


def test_datetime_after_as_of_is_caught_even_on_same_day(tmp_path):
    """同日盘中：as_of 15:00，证据 20:00 发布 → 必须报晚于截止时点。"""
    store = EvidenceStore.init(tmp_path / "evidence")
    store.register_document(
        source_type="media",
        title="当日盘后报道",
        published_at="2026-09-14T20:30:00+08:00",
        url="https://example.com/a",
        source_group="MEDIA_A",
    )
    bucket = []
    validate_evidence(
        store.state(
            as_of="2026-09-14T15:00:00+08:00",
            market_data_as_of="2026-09-14T15:00:00+08:00",
        ),
        emit=lambda s, c, m, d="": bucket.append((s, c)),
    )
    assert ("P1", "SOURCE_DATE_AFTER_AS_OF") in bucket

    # 只写日期的同类证据：信息不足，只能 day-level，不得凭空报错
    store2 = EvidenceStore.init(tmp_path / "evidence2")
    store2.register_document(
        source_type="media",
        title="当日报道（只到日）",
        published_at="2026-09-14",
        url="https://example.com/b",
        source_group="MEDIA_B",
    )
    bucket2 = []
    validate_evidence(
        store2.state(as_of="2026-09-14T15:00:00+08:00"),
        emit=lambda s, c, m, d="": bucket2.append((s, c)),
    )
    assert ("P1", "SOURCE_DATE_AFTER_AS_OF") not in bucket2


# --------------------------------------------------------------------------- #
# G. 正式 v3 时间模型必须完整
# --------------------------------------------------------------------------- #


def _manifest_with_meta(meta):
    return {
        "manifest_version": 3,
        "meta": meta,
        "forecast": {"中性": [{"year": 2026}]},
        "valuation": {"method": "PE"},
        "final": {"status": "观察"},
        "evidence_refs": [{"claim_id": "C1", "importance": "critical"}],
    }


def test_formal_v3_with_full_time_model_passes():
    findings = []
    validate_manifest_v3(
        _manifest_with_meta(
            {
                "as_of": "2026-09-14T15:00:00+08:00",
                "market_data_as_of": "2026-09-14T15:00:00+08:00",
                "generated_at": "2026-09-15T09:05:32+08:00",
            }
        ),
        emit=lambda s, c, m, d="": findings.append((s, c)),
    )
    assert not [c for _, c in findings if c == "TIME_MODEL_INCOMPLETE"]


def test_formal_v3_missing_a_time_field_is_incomplete():
    findings = []
    validate_manifest_v3(
        _manifest_with_meta(
            {
                "as_of": "2026-09-14T15:00:00+08:00",
                "market_data_as_of": "2026-09-14T15:00:00+08:00",
                # generated_at 缺失
            }
        ),
        emit=lambda s, c, m, d="": findings.append((s, c)),
    )
    assert ("P1", "TIME_MODEL_INCOMPLETE") in findings


def test_legacy_v3_with_only_research_date_stays_compatible():
    """只写 research_date 的旧 v3 走兼容路径：P2 提示，不报 INCOMPLETE。"""
    findings = []
    validate_manifest_v3(
        _manifest_with_meta({"research_date": "2026-09-14"}),
        emit=lambda s, c, m, d="": findings.append((s, c)),
    )
    codes = [c for _, c in findings]
    assert "TIME_MODEL_INCOMPLETE" not in codes
    assert "TIME_MODEL_LEGACY" in codes
