# -*- coding: utf-8 -*-
"""摘录信任边界（v3.0.3 §5 / §12-B）。

v3.0.2 把「摘录验证状态」引了进来，但它仍然只是一个**字段**——只要它是字段，
就能被人改成 `verified`。这组用例钉的就是这件事：

    落盘的验证状态 = 机器结论的缓存 ≠ 用户可以自行声明的事实

因此本文件同时验证两个方向：

  · 状态不能被外部声明（计划文件里出现 `excerpt_verification_*` 直接拒绝）；
  · 状态可以被机器重新计算，并与落盘值比对（`stored=verified` 而重算不通过 = P0）。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for _p in (str(ROOT), str(ROOT / "scripts"), str(ROOT / "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core.evidence import EvidenceStore  # noqa: E402
from core.evidence.excerpt import (  # noqa: E402
    compare_excerpt_verification,
    stamp_excerpt_verification,
)
from core.models import EvidenceCandidate  # noqa: E402
from helpers import make_claim, make_link, validate_evidence  # noqa: E402
from promote_evidence_candidate import apply_promotion  # noqa: E402

CLAIM_ID = "C_FIN_REV_2026H1"
CAND_ID = "CAN_abc12345"
SOURCE_TEXT = "营业收入 2,863,000,000 元，同比下降 5.97%\n"
OFFICIAL_URL = "https://www.cninfo.com.cn/new/disclosure/detail?announcementId=1225497941"
VERIFY_CLI = ROOT / "scripts" / "verify_excerpts.py"


# --------------------------------------------------------------------- 构件


def text_store(tmp_path: Path) -> EvidenceStore:
    """纯文本原件的 store；写盘前用真实比对盖过章。"""
    store = EvidenceStore.init(tmp_path / "evidence")
    raw = store.raw_dir
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "2026H1.txt").write_text(SOURCE_TEXT, encoding="utf-8")
    doc = store.register_document(
        source_type="interim_report",
        title="测试公司 2026 年半年度报告",
        issuer="测试公司",
        published_at="2026-08-25",
        url="https://www.cninfo.com.cn/002897/2026H1.pdf",
        local_path="raw/2026H1.txt",
        source_group="CNINFO_002897_2026H1",
        page_count=168,
    )
    store.add_claim(make_claim(CLAIM_ID))
    store.add_link(make_link(CLAIM_ID, doc.document_id))
    stamp_excerpt_verification(store)
    store.save()
    return store


def pdf_store(tmp_path: Path, *, text: str = SOURCE_TEXT) -> EvidenceStore:
    """PDF 原件 + 官方文本层：比对走 text_layer。"""
    store = EvidenceStore.init(tmp_path / "evidence")
    raw = store.raw_dir
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "2026H1.pdf").write_bytes(b"%PDF-1.4\n(fake body)\n")
    (raw / "2026H1.textlayer.txt").write_text(text, encoding="utf-8")
    doc = store.register_document(
        source_type="interim_report",
        title="测试公司 2026 年半年度报告",
        issuer="测试公司",
        published_at="2026-08-25",
        url="https://www.cninfo.com.cn/002897/2026H1.pdf",
        local_path="raw/2026H1.pdf",
        source_group="CNINFO_002897_2026H1",
        page_count=168,
    )
    store.add_claim(make_claim(CLAIM_ID))
    store.add_link(make_link(CLAIM_ID, doc.document_id))
    stamp_excerpt_verification(store)
    store.save()
    return store


def _patch_first_link(store: EvidenceStore, **fields) -> None:
    """直接改 evidence_links.jsonl —— 模拟「有人手工声明了验证状态」。"""
    path = store.root / "evidence_links.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows[0].update(fields)
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
    )


def _reopen(store: EvidenceStore) -> EvidenceStore:
    """从磁盘重新读一遍。

    `_patch_first_link` 改的是 JSONL 文件，内存对象不会跟着变——要观察「落盘状态」
    就必须重新打开，否则测的还是改动前的那份数据。
    """
    return EvidenceStore.open(store.root)


def _codes(store: EvidenceStore) -> list:
    reopened = _reopen(store)
    out = []
    validate_evidence(
        reopened.state(research_date="2026-09-14"),
        emit=lambda s, c, m, d="": out.append((s, c)),
        strict=True,
        documents_base_dir=str(reopened.root),
    )
    return [c for _, c in out]


# ------------------------------------------------- 1. compare 的语义


def test_compare_reports_match_for_honest_store(tmp_path):
    store = text_store(tmp_path)
    rows = compare_excerpt_verification(_reopen(store))
    assert len(rows) == 1
    row = rows[0]
    assert row["stored"] == "verified"
    assert row["recomputed"] == "verified"
    assert row["match"] is True
    assert row["method"] == "direct_text"


def test_compare_flags_fake_verified(tmp_path):
    """核心绕过路径：摘录其实不在原文里，状态却是 verified。"""
    store = text_store(tmp_path)
    _patch_first_link(store, evidence_text="这句话根本不在原文里")
    row = compare_excerpt_verification(_reopen(store))[0]
    assert row["stored"] == "verified"
    assert row["recomputed"] == "unverified"
    assert row["match"] is False


def test_fake_verified_is_p0(tmp_path):
    store = text_store(tmp_path)
    _patch_first_link(store, evidence_text="这句话根本不在原文里")
    assert "EVIDENCE_EXCERPT_VERIFICATION_MISMATCH" in _codes(store)


def test_honest_store_has_no_mismatch_code(tmp_path):
    store = text_store(tmp_path)
    assert "EVIDENCE_EXCERPT_VERIFICATION_MISMATCH" not in _codes(store)


def test_textlayer_changed_invalidates_declared_verified(tmp_path):
    """原件文本层后来变了：PDF 的 sha256 没变（hash 算的是 .pdf），摘录却已对不上。"""
    store = pdf_store(tmp_path)
    assert compare_excerpt_verification(_reopen(store))[0]["match"] is True
    (store.root / "raw" / "2026H1.textlayer.txt").write_text(
        "营业收入 9,999,000,000 元，同比上升 88.88%\n", encoding="utf-8"
    )
    row = compare_excerpt_verification(_reopen(store))[0]
    assert row["stored"] == "verified" and row["recomputed"] == "unverified"
    assert "EVIDENCE_EXCERPT_VERIFICATION_MISMATCH" in _codes(store)


def test_conservative_cache_is_not_a_mismatch_code(tmp_path):
    """反向：存的是 unverified、实际可验证 —— 缓存陈旧，方向保守，不报 mismatch。

    它已经被 EVIDENCE_EXCERPT_UNVERIFIED 管着了，不必再来一条 P0。
    """
    store = text_store(tmp_path)
    _patch_first_link(
        store,
        excerpt_verification_status="unverified",
        excerpt_verification_method=None,
        excerpt_verification_source=None,
    )
    row = compare_excerpt_verification(_reopen(store))[0]
    assert row["match"] is False and row["recomputed"] == "verified"
    codes = _codes(store)
    assert "EVIDENCE_EXCERPT_VERIFICATION_MISMATCH" not in codes
    assert "EVIDENCE_EXCERPT_UNVERIFIED" in codes


def test_link_without_excerpt_is_not_compared(tmp_path):
    store = text_store(tmp_path)
    _patch_first_link(store, evidence_text=None, excerpt_verification_status=None)
    rows = compare_excerpt_verification(_reopen(store))
    assert rows == []


def test_recompute_never_mutates_store(tmp_path):
    """compare 必须只读——它是「质问缓存」，不是「刷新缓存」。"""
    store = text_store(tmp_path)
    before = json.dumps([l.to_dict() for l in store.links], ensure_ascii=False, sort_keys=True)
    compare_excerpt_verification(store)
    after = json.dumps([l.to_dict() for l in store.links], ensure_ascii=False, sort_keys=True)
    assert before == after


# ------------------------------------------------- 2. 计划文件不得自带验证状态


def _plan_with(**link_overrides) -> dict:
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


def _promotable(tmp_path: Path):
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
    (tmp_path / "2026H1.txt").write_text(SOURCE_TEXT, encoding="utf-8")
    store.save()
    return store


@pytest.mark.parametrize(
    "field",
    ["excerpt_verification_status", "excerpt_verification_method", "excerpt_verification_source"],
)
def test_plan_cannot_declare_verification_fields(tmp_path, field):
    store = _promotable(tmp_path)
    logs = []
    ok, _stats = apply_promotion(store, _plan_with(**{field: "verified"}), emit=logs.append)
    assert ok is False
    assert any("PROMOTION_VERIFICATION_FIELD_FORBIDDEN" in line for line in logs)


def test_forbidden_field_leaves_store_untouched(tmp_path):
    store = _promotable(tmp_path)
    before_links = len(store.links)
    before_docs = len(store.documents)
    ok, _stats = apply_promotion(
        store, _plan_with(excerpt_verification_status="verified"), emit=lambda *_: None
    )
    assert ok is False
    assert len(store.links) == before_links and len(store.documents) == before_docs


def test_plan_without_verification_fields_promotes_and_verifies_by_machine(tmp_path):
    """不带验证字段的计划正常通过，且状态由机器写（对得上原文 → verified）。"""
    store = _promotable(tmp_path)
    ok, stats = apply_promotion(store, _plan_with(), emit=lambda *_: None, base_dir=tmp_path)
    assert ok is True, stats
    assert stats["links_added"] == 1
    link = store.links[0]
    assert link.excerpt_verification_status == "verified"
    assert link.excerpt_verification_method == "direct_text"
    assert link.excerpt_verification_source, "机器必须留下比对来源，便于复核"


# ------------------------------------------------- 3. CLI 行为


def _run_cli(evidence_dir: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(VERIFY_CLI), str(evidence_dir), *extra],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )


def test_cli_passes_on_honest_store(tmp_path):
    store = text_store(tmp_path)
    result = _run_cli(store.root)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "mismatch=0" in result.stdout


def test_cli_fails_on_fake_verified(tmp_path):
    """默认行为：发现问题就返回非 0，而不是默默刷新缓存。"""
    store = text_store(tmp_path)
    _patch_first_link(store, evidence_text="这句话根本不在原文里")
    result = _run_cli(store.root)
    assert result.returncode == 1
    assert "mismatch=1" in result.stdout
    # 默认模式不落盘：伪造状态必须原样留着，等人工判断
    on_disk = json.loads(
        (store.root / "evidence_links.jsonl").read_text(encoding="utf-8").splitlines()[0]
    )
    assert on_disk["excerpt_verification_status"] == "verified"


def test_cli_write_refreshes_cache(tmp_path):
    """--write 刷新缓存后 mismatch 归零，但「原文里确实没有这句摘录」不会因此消失。"""
    store = text_store(tmp_path)
    _patch_first_link(store, evidence_text="这句话根本不在原文里")
    result = _run_cli(store.root, "--write")
    assert "刷新后 mismatch=0" in result.stdout
    reopened = EvidenceStore.open(store.root)
    assert reopened.links[0].excerpt_verification_status == "unverified"
    # critical Claim 的摘录仍无法在原文命中 → 仍返回非 0，CI 必须挡住
    assert result.returncode == 1


def test_cli_bad_dir_returns_2(tmp_path):
    result = _run_cli(tmp_path / "nope")
    assert result.returncode == 2
