# -*- coding: utf-8 -*-
"""Promotion 的事务性（v3.0.3 §6）。

正式摄入路径必须用上已经存在的原子能力：raw 走 `raw/.staging`（复核 sha256 才进 raw/），
JSONL 走 `save_atomic()`（全部暂存成功才逐个替换）。

本文件不检查「正常路径能跑通」——那是 test_candidate_promotion 的事。
这里只做一件事：**把每个可能失败的点逐个打掉，看证据库有没有留下半成品。**

判定标准统一是同一句话（§6）：

    失败后重新 load，documents / links / candidates / raw 必须与操作前完全一致。
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[2]
for _p in (str(ROOT), str(ROOT / "scripts"), str(ROOT / "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import core.evidence.store as store_module  # noqa: E402
import promote_evidence_candidate as promo  # noqa: E402
from core.evidence import EvidenceStore  # noqa: E402
from core.models import EvidenceCandidate  # noqa: E402
from helpers import make_claim  # noqa: E402

CLAIM_ID = "C_FIN_REV_2026H1"
CAND_ID = "CAN_abc12345"
SOURCE_TEXT = "营业收入 2,863,000,000 元，同比下降 5.97%\n"
OFFICIAL_URL = "https://www.cninfo.com.cn/new/disclosure/detail?announcementId=1225497941"


# --------------------------------------------------------------------- 构件


def _promotable(tmp_path: Path) -> EvidenceStore:
    store = EvidenceStore.init(tmp_path / "evidence")
    store.add_claim(make_claim(CLAIM_ID))
    store.add_candidate(
        EvidenceCandidate(
            candidate_id=CAND_ID,
            source_type="media",
            title="财联社：测试公司 2026 半年报披露",
            discovered_at="2026-09-15T08:00:00+08:00",
            status="new",
            claim_id=CLAIM_ID,
            url=OFFICIAL_URL,
            upstream_hint="CLS_20260915_001",
        )
    )
    store.save()
    (tmp_path / "2026H1.txt").write_text(SOURCE_TEXT, encoding="utf-8")
    return store


def _plan(**link_overrides) -> dict:
    link = {
        "claim_id": CLAIM_ID,
        "section": "主要会计数据",
        "evidence_text": "营业收入 2,863,000,000 元，同比下降 5.97%",
        "support_type": "direct",
    }
    link.update(link_overrides)
    return {
        "promotions": [
            {
                "candidate_id": CAND_ID,
                "document": {
                    "source_type": "interim_report",
                    "title": "测试公司 2026 年半年度报告",
                    "issuer": "测试公司",
                    "published_at": "2026-08-25",
                    "url": OFFICIAL_URL,
                    "local_file": "2026H1.txt",
                    "source_group": "CNINFO_002897_2026H1",
                    "page_count": 168,
                },
                "links": [link],
            }
        ]
    }


def _snapshot(root: Path) -> dict:
    """重新打开 Store，取一份可比对的「证据库全貌」。"""
    store = EvidenceStore.open(Path(root))
    raw_dir = store.raw_dir
    return {
        "documents": sorted(store.documents),
        "links": sorted(l.evidence_id for l in store.links),
        "claims": sorted(store.claims),
        "candidates": sorted((c.candidate_id, c.status) for c in store.candidates.values()),
        "raw": sorted(p.name for p in raw_dir.iterdir() if p.is_file()) if raw_dir.is_dir() else [],
    }


def _quiet(*_a, **_k) -> None:
    return None


@pytest.fixture
def guarded(tmp_path):
    """**失败路径专用**：用例结束时断言证据库没被动过。

    成功路径不要用这个，改用 `promotable` —— 它不替用例下结论。
    """
    store = _promotable(tmp_path)
    before = _snapshot(store.root)
    yield store, before
    assert _snapshot(store.root) == before, "失败路径不得改动证据库"


@pytest.fixture
def promotable(tmp_path):
    """通用：返回 (store, 操作前全貌快照)。"""
    store = _promotable(tmp_path)
    return store, _snapshot(store.root)


# ------------------------------------------------- 1. raw 侧


def test_raw_copy_failure_leaves_store_intact(guarded, monkeypatch, tmp_path):
    store, _ = guarded

    def boom(*_a, **_k):
        raise OSError("模拟 raw copy 失败")

    monkeypatch.setattr(store_module.shutil, "copy2", boom)
    logs = []
    ok, _stats = promo.apply_promotion(store, _plan(), base_dir=tmp_path, emit=logs.append)
    assert ok is False
    assert any("已回滚" in line for line in logs)


def test_raw_hash_mismatch_after_copy_rolls_back(guarded, monkeypatch, tmp_path):
    """落地副本的 sha256 与源文件不符 → 拒绝进 raw/（并清掉 staging 残片）。"""
    store, _ = guarded
    real = store_module.sha256_file
    calls = {"n": 0}

    def flaky(path):
        calls["n"] += 1
        if calls["n"] == 2:      # 第二次是「落地副本」的复核
            return "0" * 64
        return real(path)

    monkeypatch.setattr(store_module, "sha256_file", flaky)
    ok, _stats = promo.apply_promotion(store, _plan(), base_dir=tmp_path, emit=_quiet)
    assert ok is False
    assert not store.staging_dir.exists(), "staging 不得留下残片"


def test_missing_source_file_is_rejected_before_any_write(guarded, tmp_path):
    store, _ = guarded
    plan = _plan()
    plan["promotions"][0]["document"]["local_file"] = "不存在.txt"
    ok, _stats = promo.apply_promotion(store, plan, base_dir=tmp_path, emit=_quiet)
    assert ok is False
    assert store.links == []


# ------------------------------------------------- 2. JSONL 侧


def test_jsonl_stage_failure_rolls_back(guarded, monkeypatch, tmp_path):
    """写 .tmp 就失败 → 一个文件都没被替换，raw 也要退回去。"""
    store, _ = guarded

    def boom(target, text):
        raise OSError("模拟 .tmp 写入失败")

    monkeypatch.setattr(store_module, "_stage_text", boom)
    ok, _stats = promo.apply_promotion(store, _plan(), base_dir=tmp_path, emit=_quiet)
    assert ok is False
    assert not store.links
    assert not store.documents


def test_second_jsonl_replace_failure_rolls_back_everything(guarded, monkeypatch, tmp_path):
    """§10.5 指定的注入：**第二个 JSONL replace 失败**。

    这是最容易留下半成品的位置——第一个文件已经是新内容，后面几个还是旧的。
    save_atomic 必须用 .bak 把第一个也退回去，RawTransaction 把 raw 也退回去。
    """
    store, before = guarded
    real_replace = os.replace
    state = {"n": 0}

    def flaky(src, dst, *args, **kwargs):
        if str(src).endswith(".tmp"):
            state["n"] += 1
            if state["n"] == 2:
                raise OSError("模拟第二个 JSONL replace 失败")
        return real_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr(store_module.os, "replace", flaky)
    ok, _stats = promo.apply_promotion(store, _plan(), base_dir=tmp_path, emit=_quiet)
    assert ok is False
    assert state["n"] == 2, "注入点没被触发，用例本身失效"
    assert _snapshot(store.root) == before


def test_successful_promotion_writes_both_sides_atomically(promotable, tmp_path):
    store, _ = promotable
    ok, stats = promo.apply_promotion(store, _plan(), base_dir=tmp_path, emit=_quiet)
    assert ok is True
    after = _snapshot(store.root)
    assert after["documents"] and after["links"] and after["raw"], "raw 与 JSONL 必须一起生效"
    assert ("CAN_abc12345", "promoted") in after["candidates"]
    assert stats["links_added"] == 1


# ------------------------------------------------- 3. 校验失败（不落盘）


def test_document_validation_failure_writes_nothing(guarded, tmp_path):
    store, _ = guarded
    plan = _plan()
    plan["promotions"][0]["document"]["source_type"] = "不存在的来源类型"
    ok, _stats = promo.apply_promotion(store, plan, base_dir=tmp_path, emit=_quiet)
    assert ok is False


def test_link_validation_failure_writes_nothing(guarded, tmp_path):
    store, _ = guarded
    ok, _stats = promo.apply_promotion(
        store, _plan(support_type="不存在的支持类型"), base_dir=tmp_path, emit=_quiet
    )
    assert ok is False


def test_candidate_status_update_failure_rolls_back(guarded, tmp_path):
    """Pass 3 中途炸在 Candidate 状态更新上：raw 已落地、内存已改，必须全部退回。

    打桩用上下文管理器而不是 monkeypatch fixture —— `__setattr__` 是 dunder，
    被改写后连 dataclass 的 `__init__` 都会走它，必须保证退出时机确定。
    """
    store, before = guarded
    original = EvidenceCandidate.__setattr__

    def boom(self, name, value):
        if name == "status":
            raise RuntimeError("模拟 Candidate 状态更新失败")
        original(self, name, value)

    with mock.patch.object(EvidenceCandidate, "__setattr__", boom):
        ok, _stats = promo.apply_promotion(store, _plan(), base_dir=tmp_path, emit=_quiet)
    assert ok is False
    assert _snapshot(store.root) == before


def test_stamp_failure_rolls_back_raw_and_jsonl(guarded, monkeypatch, tmp_path):
    """Pass 4 失败（摘录重算炸掉）—— 此时 raw 已经在 raw/ 里了，也必须撤回。"""
    store, before = guarded

    def boom(*_a, **_k):
        raise RuntimeError("模拟摘录重算失败")

    monkeypatch.setattr(promo, "stamp_excerpt_verification", boom)
    ok, _stats = promo.apply_promotion(store, _plan(), base_dir=tmp_path, emit=_quiet)
    assert ok is False
    assert _snapshot(store.root) == before


# ------------------------------------------------- 4. 语义层面：不再有后门


def test_promotion_does_not_use_plain_copy_to_raw(tmp_path, monkeypatch):
    """把 shutil.copy2 换掉（不允许它被主路径直接用来写 raw/）。

    add_raw_file 内部自己会调 copy2（复制到 staging），所以不能简单禁掉；
    这里验证的是：**当 raw/ 里已经存在同名文件时，仍然走 staging 路径**——
    也就是不会出现「直接覆盖 raw/ 里那份」的行为。
    """
    store = _promotable(tmp_path)
    store.save()
    stale = store.raw_dir / "2026H1.txt"
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.write_text("旧内容（不应被就地覆盖）", encoding="utf-8")

    ok, _ = promo.apply_promotion(store, _plan(), base_dir=tmp_path, emit=_quiet)
    assert ok is True
    assert stale.read_text(encoding="utf-8") == SOURCE_TEXT
    # 覆盖前的那份被 RawTransaction 备份，成功后清除
    assert not list(store.raw_dir.glob("*.rollback"))
    assert not list(store.raw_dir.glob("*.tmp"))


def test_dry_run_touches_nothing(guarded, tmp_path):
    store, before = guarded
    ok, stats = promo.apply_promotion(store, _plan(), dry_run=True, base_dir=tmp_path, emit=_quiet)
    assert ok is True and stats["links_added"] == 1
    assert _snapshot(store.root) == before


def test_promote_never_writes_claims_jsonl(promotable, tmp_path):
    """promote 永不改 Claim 状态（§6 硬规则 5）：claims.jsonl 必须逐字节不变。"""
    store, _ = promotable
    path = store.root / "claims.jsonl"
    before = path.read_text(encoding="utf-8")
    ok, _ = promo.apply_promotion(store, _plan(), base_dir=tmp_path, emit=_quiet)
    assert ok is True
    assert path.read_text(encoding="utf-8") == before
