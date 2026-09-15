# -*- coding: utf-8 -*-
"""Candidate → Document 摄入工作流（v3.0.1 §6 / Task 3）。

纪律回顾（§5）：**线索 ≠ 证据**。

promote 的含义不是「把线索升格成证据」，而是「顺着线索拿到了原件，于是才
有资格谈证据」。所以本文件把 §6 的每条硬规则都固定成用例：

    1. 没有 url 或 local_file → 拒绝（不许凭印象升格）
    2. 文本原件的 evidence_text 必须是文件真实子串 → 否则拒绝
    3. PDF 不要求 OCR，允许只有定位；缺摘录的 P1 交给 validator，不在这里消解
    4. 原子执行：任一条失败整体不落盘
    5. Candidate 不能直接改 Claim.status，必须经由 Document + EvidenceLink

第 5 条在本文件里体现为「即使计划里写了 claim_status，Claim 也不会被动过」。
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for _p in (str(ROOT), str(ROOT / "scripts"), str(ROOT / "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core.evidence import EvidenceStore, sha256_file  # noqa: E402
from core.models import EvidenceCandidate  # noqa: E402
from helpers import make_claim  # noqa: E402
from promote_evidence_candidate import (  # noqa: E402
    PromotionError,
    apply_promotion,
    load_plan,
)

CLAIM_ID = "C_FIN_REV_2026H1"
CAND_ID = "CAN_abc12345"

# 与意华股份 2026 半年报口径一致的真实数字（Golden Sample 用得上）
SOURCE_TEXT = (
    "一、主要会计数据\n"
    "营业收入 2,863,320,150.75 元，同比下降 5.97%\n"
    "归属于上市公司股东的净利润 100,364,975.19 元，同比下降 37.87%\n"
)
OFFICIAL_URL = "https://www.cninfo.com.cn/new/disclosure/detail?announcementId=1225497941"


def _quiet(*_args, **_kwargs) -> None:  # emit 替身
    return None


def build_store(tmp_path: Path, *, with_source: bool = True):
    """一个含 1 个 Claim + 1 条 new 线索的证据库。"""
    store = EvidenceStore.init(tmp_path / "evidence")
    store.add_claim(make_claim(CLAIM_ID))
    candidate = store.add_candidate(
        EvidenceCandidate(
            candidate_id=CAND_ID,
            source_type="media",
            title="财联社：意华股份 2026 半年报披露",
            discovered_at="2026-09-15T08:00:00+08:00",
            status="new",
            claim_id=CLAIM_ID,
            url=OFFICIAL_URL,
            upstream_hint="CLS_20260915_001",
        )
    )
    src = tmp_path / "2026H1.txt"
    if with_source:
        src.write_text(SOURCE_TEXT, encoding="utf-8")
    store.save()
    return store, candidate, src


def doc_payload(src: Path, **overrides) -> dict:
    data = {
        "source_type": "interim_report",
        "title": "意华股份2026年半年度报告",
        "issuer": "意华股份",
        "published_at": "2026-08-25",
        "url": OFFICIAL_URL,
        "local_file": str(src),
        "source_group": "CNINFO_002897_2026H1",
        "page_count": 168,
        "sections": ["主要会计数据"],
    }
    data.update(overrides)
    return data


def promo_plan(document=None, links=None, candidate_id=CAND_ID, **extra) -> dict:
    item = {
        "candidate_id": candidate_id,
        "document": document,
        "links": links
        if links is not None
        else [
            {
                "claim_id": CLAIM_ID,
                "section": "主要会计数据",
                "evidence_text": "营业收入 2,863,320,150.75 元，同比下降 5.97%",
                "support_type": "direct",
            }
        ],
    }
    item.update(extra)
    return {"promotions": [item]}


def reload(store: EvidenceStore) -> EvidenceStore:
    """从磁盘重新读一遍 —— 用来证明「落盘」而不只是「内存里改了」。"""
    return EvidenceStore.open(store.root)


# --------------------------------------------------------------------------- #
# 硬规则 1：没有原始来源就不能 promote
# --------------------------------------------------------------------------- #


def test_reject_without_url_and_local_file(tmp_path):
    store, candidate, src = build_store(tmp_path)
    plan = promo_plan(document=doc_payload(src, url=None, local_file=None))

    ok, stats = apply_promotion(store, plan, base_dir=tmp_path, emit=_quiet)

    assert not ok
    assert stats["promoted"] == 0
    assert candidate.status == "new"
    assert candidate.promoted_document_id is None
    # 磁盘上必须什么都没变
    fresh = reload(store)
    assert fresh.documents == {}
    assert fresh.links == []
    assert fresh.candidate_of(CAND_ID).status == "new"


def test_reject_when_local_file_missing(tmp_path):
    store, _, src = build_store(tmp_path)
    plan = promo_plan(document=doc_payload(src, local_file=str(tmp_path / "不存在.txt")))

    ok, stats = apply_promotion(store, plan, base_dir=tmp_path, emit=_quiet)

    assert not ok
    assert reload(store).documents == {}


def test_reject_without_source_group_and_without_upstream_hint(tmp_path):
    """source_group 决定来源独立性；没有它也没法回退 → 拒绝。"""
    store, candidate, src = build_store(tmp_path)
    candidate.upstream_hint = None
    plan = promo_plan(document=doc_payload(src, source_group=None))

    ok, _ = apply_promotion(store, plan, base_dir=tmp_path, emit=_quiet)

    assert not ok
    assert reload(store).documents == {}


def test_source_group_falls_back_to_upstream_hint(tmp_path):
    store, _, src = build_store(tmp_path)
    plan = promo_plan(document=doc_payload(src, source_group=None))

    ok, _ = apply_promotion(store, plan, base_dir=tmp_path, emit=_quiet)
    store.save()

    assert ok
    doc = next(iter(reload(store).documents.values()))
    assert doc.source_group == "CLS_20260915_001"


def test_unknown_candidate_rejected(tmp_path):
    store, _, src = build_store(tmp_path)
    plan = promo_plan(document=doc_payload(src), candidate_id="CAN_deadbeef")

    ok, _ = apply_promotion(store, plan, base_dir=tmp_path, emit=_quiet)

    assert not ok
    assert reload(store).documents == {}


def test_unknown_claim_rejected(tmp_path):
    store, _, src = build_store(tmp_path)
    plan = promo_plan(
        document=doc_payload(src),
        links=[{"claim_id": "C_NOT_EXIST", "section": "主要会计数据"}],
    )

    ok, _ = apply_promotion(store, plan, base_dir=tmp_path, emit=_quiet)

    assert not ok


# --------------------------------------------------------------------------- #
# 硬规则 2：摘录必须来自原文
# --------------------------------------------------------------------------- #


def test_reject_when_excerpt_is_not_verbatim(tmp_path):
    store, candidate, src = build_store(tmp_path)
    plan = promo_plan(
        document=doc_payload(src),
        links=[
            {
                "claim_id": CLAIM_ID,
                "section": "主要会计数据",
                "evidence_text": "营业收入 2,863,320,150.75 元，同比增长 5.97%",  # 篡改了方向
            }
        ],
    )

    ok, _ = apply_promotion(store, plan, base_dir=tmp_path, emit=_quiet)

    assert not ok
    assert candidate.status == "new"
    fresh = reload(store)
    assert fresh.documents == {} and fresh.links == []


def test_reject_when_excerpt_provided_but_no_readable_source(tmp_path):
    """没有原件却写了摘录 —— 无从验证，只能拒绝。"""
    store, _, _ = build_store(tmp_path, with_source=False)
    plan = promo_plan(
        document=doc_payload(tmp_path / "2026H1.txt"),
        links=[{"claim_id": CLAIM_ID, "section": "主要会计数据", "evidence_text": "任意摘录"}],
    )

    ok, _ = apply_promotion(store, plan, base_dir=tmp_path, emit=_quiet)

    assert not ok


def test_excerpt_tolerates_whitespace_but_not_numbers(tmp_path):
    store, _, src = build_store(tmp_path)
    plan = promo_plan(
        document=doc_payload(src),
        links=[
            {
                "claim_id": CLAIM_ID,
                "section": "主要会计数据",
                "evidence_text": "营业收入  2,863,320,150.75  元，同比下降 5.97%",
            }
        ],
    )

    ok, stats = apply_promotion(store, plan, base_dir=tmp_path, emit=_quiet)

    assert ok
    assert stats["links_added"] == 1


def test_binary_source_skips_substring_but_still_needs_locator(tmp_path):
    """§6 硬规则 3：PDF 第一版不要求 OCR，但定位不能缺。"""
    store, _, _ = build_store(tmp_path)
    pdf = tmp_path / "2026H1.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")

    # 只有定位、没有摘录 → 放行（缺摘录的 P1 由 validator 负责）
    ok, _ = apply_promotion(
        store,
        promo_plan(
            document=doc_payload(pdf, page_count=168, sections=["主要会计数据"]),
            links=[{"claim_id": CLAIM_ID, "page": 12, "section": "主要会计数据"}],
        ),
        base_dir=tmp_path,
        emit=_quiet,
    )
    assert ok

    # 连定位都没有 → 拒绝
    store2, _, _ = build_store(tmp_path / "second")
    ok2, _ = apply_promotion(
        store2,
        promo_plan(
            document=doc_payload(pdf, page_count=168, sections=[]),
            links=[{"claim_id": CLAIM_ID}],
        ),
        base_dir=tmp_path,
        emit=_quiet,
    )
    assert not ok2


def test_locator_out_of_range_rejected(tmp_path):
    store, _, src = build_store(tmp_path)
    plan = promo_plan(
        document=doc_payload(src),
        links=[{"claim_id": CLAIM_ID, "page": 9999, "section": "主要会计数据"}],
    )

    ok, _ = apply_promotion(store, plan, base_dir=tmp_path, emit=_quiet)

    assert not ok


# --------------------------------------------------------------------------- #
# 从原文「剪」摘录（人给锚点，机器剪 —— 比人写摘录更不容易出错）
# --------------------------------------------------------------------------- #


def test_excerpt_anchor_cuts_verbatim_from_source(tmp_path):
    store, _, src = build_store(tmp_path)
    plan = promo_plan(
        document=doc_payload(src),
        links=[
            {
                "claim_id": CLAIM_ID,
                "section": "主要会计数据",
                "excerpt_anchor": "营业收入 2,863,320,150.75 元",
                "excerpt_tail": 11,  # 连“，同比下降 5.97%”一起剪进来
                "support_type": "direct",
            }
        ],
    )

    ok, _ = apply_promotion(store, plan, base_dir=tmp_path, emit=_quiet)
    store.save()

    assert ok
    link = reload(store).links[0]
    assert link.evidence_text == "营业收入 2,863,320,150.75 元，同比下降 5.97%"
    assert link.evidence_text in src.read_text(encoding="utf-8")


def test_excerpt_anchor_not_found_is_rejected(tmp_path):
    """锚点找不到就必须报错，绝不允许「就近取一段差不多的」。"""
    store, _, src = build_store(tmp_path)
    plan = promo_plan(
        document=doc_payload(src),
        links=[
            {
                "claim_id": CLAIM_ID,
                "section": "主要会计数据",
                "excerpt_anchor": "营业收入 2,999,999,999.99 元",
            }
        ],
    )

    ok, _ = apply_promotion(store, plan, base_dir=tmp_path, emit=_quiet)

    assert not ok
    assert reload(store).links == []


# --------------------------------------------------------------------------- #
# 硬规则 5：Candidate 不能直接改 Claim 状态
# --------------------------------------------------------------------------- #


def test_plan_cannot_set_claim_status(tmp_path):
    store, _, src = build_store(tmp_path)
    before = copy.deepcopy(store.claims[CLAIM_ID].status)
    plan = promo_plan(document=doc_payload(src), claim_status="supported")

    ok, _ = apply_promotion(store, plan, base_dir=tmp_path, emit=_quiet)

    assert not ok
    assert store.claims[CLAIM_ID].status == before
    # claims.jsonl 不该被本脚本碰过
    assert reload(store).claims[CLAIM_ID].status == before


# --------------------------------------------------------------------------- #
# 正常路径：hash / source_group / 落盘 / promoted
# --------------------------------------------------------------------------- #


def test_hash_is_generated_automatically(tmp_path):
    store, _, src = build_store(tmp_path)
    plan = promo_plan(document=doc_payload(src, sha256=None))

    ok, _ = apply_promotion(store, plan, base_dir=tmp_path, emit=_quiet)
    store.save()

    assert ok
    doc = next(iter(reload(store).documents.values()))
    assert doc.sha256 == sha256_file(src)
    # 原件被复制进 evidence/raw/
    assert (store.raw_dir / src.name).is_file()
    assert doc.local_path == f"raw/{src.name}"


def test_document_and_link_are_persisted_together(tmp_path):
    store, candidate, src = build_store(tmp_path)
    plan = promo_plan(document=doc_payload(src))

    ok, stats = apply_promotion(store, plan, base_dir=tmp_path, emit=_quiet)
    store.save()

    assert ok
    assert stats["documents_created"] == 1
    assert stats["links_added"] == 1

    fresh = reload(store)
    assert len(fresh.documents) == 1
    assert len(fresh.links) == 1
    link = fresh.links[0]
    doc = next(iter(fresh.documents.values()))
    assert link.document_id == doc.document_id
    assert link.claim_id == CLAIM_ID
    assert link.evidence_text in src.read_text(encoding="utf-8")
    assert fresh.candidate_of(CAND_ID).status == "promoted"
    assert fresh.candidate_of(CAND_ID).promoted_document_id == doc.document_id


def test_candidate_is_marked_promoted_with_real_document(tmp_path):
    store, candidate, src = build_store(tmp_path)

    ok, _ = apply_promotion(store, promo_plan(document=doc_payload(src)), base_dir=tmp_path, emit=_quiet)

    assert ok
    assert candidate.status == "promoted"
    assert candidate.is_terminal
    assert candidate.promoted_document_id is not None
    assert candidate.promoted_document_id in store.documents


def test_multiple_links_in_one_promotion(tmp_path):
    store, _, src = build_store(tmp_path)
    store.add_claim(
        make_claim(
            "C_FIN_NP_2026H1",
            claim="2026H1 归母净利润 1.00 亿元（同比 -37.87%）",
        )
    )
    plan = promo_plan(
        document=doc_payload(src),
        links=[
            {
                "claim_id": CLAIM_ID,
                "section": "主要会计数据",
                "evidence_text": "营业收入 2,863,320,150.75 元，同比下降 5.97%",
            },
            {
                "claim_id": "C_FIN_NP_2026H1",
                "section": "主要会计数据",
                "evidence_text": "归属于上市公司股东的净利润 100,364,975.19 元，同比下降 37.87%",
            },
        ],
    )

    ok, stats = apply_promotion(store, plan, base_dir=tmp_path, emit=_quiet)

    assert ok
    assert stats["links_added"] == 2
    ids = {l.evidence_id for l in store.links}
    assert len(ids) == 2  # 自动分配的 evidence_id 不能撞车


# --------------------------------------------------------------------------- #
# 硬规则 4：原子性
# --------------------------------------------------------------------------- #


def test_partial_failure_leaves_no_artifacts(tmp_path):
    """第一条合法、第二条摘录造假 → 两条都不许落盘。"""
    store, _, src = build_store(tmp_path)
    store.add_candidate(
        EvidenceCandidate(
            candidate_id="CAN_bad00002",
            source_type="media",
            title="某媒体转述",
            discovered_at="2026-09-15T09:00:00+08:00",
            status="new",
            url="https://example.com/a",
        )
    )
    store.save()

    good = {
        "candidate_id": CAND_ID,
        "document": doc_payload(src),
        "links": [
            {
                "claim_id": CLAIM_ID,
                "section": "主要会计数据",
                "evidence_text": "营业收入 2,863,320,150.75 元，同比下降 5.97%",
            }
        ],
    }
    bad = {
        "candidate_id": "CAN_bad00002",
        "document": doc_payload(
            src,
            title="某媒体转述稿",
            url="https://example.com/media/1",
            source_group="MEDIA_X_001",
        ),
        "links": [
            {
                "claim_id": CLAIM_ID,
                "section": "主要会计数据",
                "evidence_text": "这家公司的营收暴涨了 300%",  # 原文里根本没有
            }
        ],
    }

    ok, stats = apply_promotion(store, {"promotions": [good, bad]}, base_dir=tmp_path, emit=_quiet)

    assert not ok
    assert stats["promoted"] == 0
    fresh = reload(store)
    assert fresh.documents == {}
    assert fresh.links == []
    assert fresh.candidate_of(CAND_ID).status == "new"
    assert fresh.candidate_of("CAN_bad00002").status == "new"
    # 连原件都不该被复制进 raw/
    assert list(store.raw_dir.glob("*.txt")) == []


def test_dry_run_writes_nothing(tmp_path):
    store, candidate, src = build_store(tmp_path)
    plan = promo_plan(document=doc_payload(src))

    ok, stats = apply_promotion(store, plan, dry_run=True, base_dir=tmp_path, emit=_quiet)

    assert ok
    assert stats["documents_created"] == 1
    assert candidate.status == "new"
    fresh = reload(store)
    assert fresh.documents == {} and fresh.links == []
    assert not (store.raw_dir / src.name).exists()


# --------------------------------------------------------------------------- #
# 幂等 / 冲突
# --------------------------------------------------------------------------- #


def test_duplicate_promote_is_idempotent(tmp_path):
    store, candidate, src = build_store(tmp_path)
    plan = promo_plan(document=doc_payload(src))

    ok1, _ = apply_promotion(store, plan, base_dir=tmp_path, emit=_quiet)
    store.save()
    assert ok1

    ok2, stats2 = apply_promotion(store, plan, base_dir=tmp_path, emit=_quiet)

    assert ok2
    assert stats2["unchanged"] == 1
    assert stats2["documents_created"] == 0
    assert stats2["links_added"] == 0
    fresh = reload(store)
    assert len(fresh.documents) == 1
    assert len(fresh.links) == 1


def test_conflicting_duplicate_promote_is_rejected(tmp_path):
    """同一线索已被 promote 到另一份 Document → 明确拒绝，不许悄悄改指向。"""
    store, candidate, src = build_store(tmp_path)
    ok, _ = apply_promotion(store, promo_plan(document=doc_payload(src)), base_dir=tmp_path, emit=_quiet)
    assert ok
    first_doc = candidate.promoted_document_id
    assert first_doc

    other = tmp_path / "other.txt"
    other.write_text(SOURCE_TEXT, encoding="utf-8")
    plan = promo_plan(document=doc_payload(other, document_id="DOC_ffffffff"))

    ok2, _ = apply_promotion(store, plan, base_dir=tmp_path, emit=_quiet)

    assert not ok2
    assert candidate.promoted_document_id == first_doc


def test_empty_promotions_is_config_error(tmp_path):
    store, _, _ = build_store(tmp_path)
    with pytest.raises(PromotionError):
        apply_promotion(store, {"promotions": []}, base_dir=tmp_path, emit=_quiet)


def test_load_plan_rejects_broken_json(tmp_path):
    bad = tmp_path / "plan.json"
    bad.write_text("{ 这不是 JSON", encoding="utf-8")
    with pytest.raises(PromotionError):
        load_plan(bad)


# --------------------------------------------------------------------------- #
# CLI 冒烟
# --------------------------------------------------------------------------- #


def _run_cli(evidence_dir: Path, plan: Path, *extra: str) -> subprocess.CompletedProcess:
    script = ROOT / "scripts" / "promote_evidence_candidate.py"
    return subprocess.run(
        [sys.executable, str(script), str(evidence_dir), "--plan", str(plan), *extra],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )


def test_cli_promotes_and_exits_zero(tmp_path):
    store, _, src = build_store(tmp_path)
    plan_path = tmp_path / "promote_plan.json"
    plan_path.write_text(json.dumps(promo_plan(document=doc_payload(src)), ensure_ascii=False), encoding="utf-8")

    result = _run_cli(store.root, plan_path)

    assert result.returncode == 0, result.stdout + result.stderr
    fresh = reload(store)
    assert len(fresh.documents) == 1 and len(fresh.links) == 1
    assert fresh.candidate_of(CAND_ID).status == "promoted"


def test_cli_returns_one_when_validation_fails(tmp_path):
    store, _, src = build_store(tmp_path)
    plan_path = tmp_path / "promote_plan.json"
    plan_path.write_text(
        json.dumps(
            promo_plan(
                document=doc_payload(src, url=None, local_file=None),
            ),
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = _run_cli(store.root, plan_path)

    assert result.returncode == 1
    assert reload(store).documents == {}


def test_cli_dry_run_does_not_write(tmp_path):
    store, _, src = build_store(tmp_path)
    plan_path = tmp_path / "promote_plan.json"
    plan_path.write_text(json.dumps(promo_plan(document=doc_payload(src)), ensure_ascii=False), encoding="utf-8")

    result = _run_cli(store.root, plan_path, "--dry-run")

    assert result.returncode == 0, result.stdout + result.stderr
    fresh = reload(store)
    assert fresh.documents == {} and fresh.links == []
