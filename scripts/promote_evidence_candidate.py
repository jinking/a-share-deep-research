#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Candidate → Document 摄入工作流（v3.0.1 §6 / Task 3）。

为什么单独一个脚本：§5 把「线索 ≠ 证据」定死了，§6 又规定了从线索到证据的
**唯一**通道。通道只有一条，就该只有一个入口 —— 否则迟早有人绕过它。

标准流程（不可跳步）：

    Candidate（线索）
      → 确认原始来源（url 或 local_file 至少有其一）
      → 保存原始资料
      → register Document（自动算 sha256）
      → 绑定 source_group（决定来源独立性）
      → 生成 EvidenceLink（补 locator）
      → 从原文抽取 evidence_text（文本原件强制子串校验）
      → Candidate.status = promoted

硬规则（代码化，不靠自觉）：

  1. 无 url 且无 local_file → 拒绝。线索不能凭「我记得看过」变成证据。
  2. 文本原件的 evidence_text 必须是文件真实子串（忽略空白差异）。
     也可以不给摘录、只给 `excerpt_anchor`，让脚本从原文**剪**出片段。
  3. PDF 等二进制第一版不做 OCR：允许只有 page/section/table；
     缺 evidence_text 时 validator 仍会给 critical Claim 报 P1，这里不代为消解。
  4. 原子执行：两阶段，任何一条不通过就整体不落盘；落盘阶段异常会回滚内存状态。
  5. promote 不改 Claim.status —— Claim 能不能 supported 由 Document + Link 决定，
     不由 Candidate 决定。本脚本永不写 claims.jsonl。

幂等：同一 Candidate 重复 promote 到同一份 Document → 视为无变化并放行；
指向另一份 Document → 明确拒绝（不许悄悄改指向）。

用法：
    python3 scripts/promote_evidence_candidate.py <evidence_dir> --plan promote_plan.json
    python3 scripts/promote_evidence_candidate.py <evidence_dir> --plan promote_plan.json --dry-run

计划文件格式（promote_plan.json）：
    {
      "promotions": [
        {
          "candidate_id": "CAN_3f9a1b2c",
          "document": {
            "source_type": "interim_report",
            "title": "意华股份2026年半年度报告",
            "issuer": "意华股份",
            "published_at": "2026-08-25",
            "url": "https://www.cninfo.com.cn/...",
            "local_file": "raw/2026H1.txt",       // 相对「计划文件所在目录」解析
            "source_group": "CNINFO_002897_2026H1",
            "page_count": 168,
            "sections": ["主要会计数据"]
          },
          "links": [
            {
              "claim_id": "C_FIN_REV_2026H1",
              "section": "主要会计数据",
              // 二选一：人工写摘录（会被子串校验），或给锚点让脚本剪
              "excerpt_anchor": "营业收入 2,863,320,150.75 元",
              "excerpt_tail": 24,
              "support_type": "direct"
            }
          ]
        }
      ]
    }

退出码：
    0 = 全部成功（含「已 promote 且内容一致」的幂等重放）
    1 = 校验失败，未落盘
    2 = 参数/文件错误
"""

from __future__ import annotations

import argparse
import copy
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.evidence import EvidenceStore, sha256_file, validate_locator  # noqa: E402
from core.evidence.excerpt import stamp_excerpt_verification  # noqa: E402
from core.evidence.hasher import make_document_id  # noqa: E402
from core.evidence.verbatim import VerbatimError, extract_verbatim, text_supports_excerpt  # noqa: E402
from core.models.base import clean_str, iso_now  # noqa: E402
from core.models.candidate import is_candidate_id  # noqa: E402
from core.models.document import SourceDocument  # noqa: E402
from core.models.evidence import EvidenceLink  # noqa: E402
from core.models.provenance import default_source_type_for  # noqa: E402

__all__ = ["PromotionError", "load_plan", "apply_promotion"]

EMPTY_STATS = {
    "promoted": 0,
    "documents_created": 0,
    "documents_reused": 0,
    "links_added": 0,
    "unchanged": 0,
}

# 复用既有 Document 时，允许被本次计划补齐/覆盖的字段
_BINDABLE_FIELDS = (
    "local_path",
    "sha256",
    "url",
    "source_group",
    "note",
    "provider",
    "upstream_source_type",
    "upstream_document_id",
)


class PromotionError(Exception):
    """计划文件本身有问题（无法解析、结构不对）。"""


def load_plan(path) -> Dict[str, Any]:
    p = Path(path)
    if not p.is_file():
        raise PromotionError(f"计划文件不存在: {p}")
    try:
        plan = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PromotionError(f"计划文件无法解析: {exc}") from exc
    if not isinstance(plan, dict):
        raise PromotionError("计划文件根节点必须是 JSON 对象")
    promotions = plan.get("promotions")
    if not isinstance(promotions, list) or not promotions:
        raise PromotionError("计划文件缺少非空的 promotions 数组")
    return plan


def _clean(value: Any) -> str:
    return clean_str(value) or ""


def _coerce_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def apply_promotion(
    store: EvidenceStore,
    plan: Dict[str, Any],
    *,
    dry_run: bool = False,
    base_dir=None,
    emit=print,
) -> Tuple[bool, Dict[str, int]]:
    """把 promote 计划应用到 store；返回 (是否成功, 统计)。

    两阶段：先把所有改动算进动作列表并校验，全部通过后才 commit。
    base_dir：解析计划内相对路径（local_file）的基准目录，默认当前工作目录。
    """
    if not isinstance(plan, dict):
        raise PromotionError("计划文件根节点必须是 JSON 对象")
    promotions = plan.get("promotions")
    if not isinstance(promotions, list) or not promotions:
        raise PromotionError("计划文件缺少非空的 promotions 数组")
    if plan.get("claim_status_updates"):
        raise PromotionError(
            "promote 不接受 claim_status_updates —— Claim 状态只能由正式 Document + EvidenceLink 决定（§6 硬规则 5）"
        )

    base = Path(base_dir) if base_dir else Path.cwd()

    def resolve(p: str) -> Path:
        q = Path(str(p)).expanduser()
        return q if q.is_absolute() else (base / q)

    errors: List[str] = []
    stats = dict(EMPTY_STATS)

    virtual_docs: Dict[str, SourceDocument] = dict(store.documents)
    source_of: Dict[str, Path] = {}
    used_evidence_ids = {l.evidence_id for l in store.links}
    claimed_doc_ids: Dict[str, str] = {}

    doc_actions: List[Tuple[Optional[SourceDocument], SourceDocument, Optional[Path]]] = []
    link_actions: List[EvidenceLink] = []
    cand_actions: List[Tuple[Any, str]] = []
    unchanged: List[str] = []

    def allocate_evidence_id(claim_id: str) -> str:
        n = 1
        while f"EV_{claim_id}_{n:02d}" in used_evidence_ids:
            n += 1
        eid = f"EV_{claim_id}_{n:02d}"
        used_evidence_ids.add(eid)
        return eid

    # ---------------- Pass 1/2：解析 + 校验（不碰任何东西） ----------------
    for item in promotions:
        start = len(errors)
        if not isinstance(item, dict):
            errors.append(f"promotions 条目不是对象: {item!r}")
            continue

        cand_id = _clean(item.get("candidate_id"))
        if not cand_id:
            errors.append("promotions 条目缺少 candidate_id")
            continue
        if item.get("claim_status") is not None:
            errors.append(f"{cand_id}: 不允许在 promote 里写 claim_status（§6 硬规则 5）")
            continue

        candidate = store.candidate_of(cand_id)
        if candidate is None:
            errors.append(f"未知 candidate_id: {cand_id}（不在 candidates.jsonl 中）")
            continue

        doc_spec = item.get("document")
        if not isinstance(doc_spec, dict):
            errors.append(f"{cand_id}: 缺少 document 定义")
            continue

        # 硬规则 1
        url = _clean(doc_spec.get("url"))
        local_file = _clean(doc_spec.get("local_file")) or _clean(doc_spec.get("local_path"))
        if not url and not local_file:
            errors.append(
                f"{cand_id}: 无 url 也无 local_file —— 线索不能直接升格为证据（§6 硬规则 1）"
            )
            continue
        src: Optional[Path] = None
        if local_file:
            src = resolve(local_file)
            if not src.is_file():
                errors.append(f"{cand_id}: 本地文件不存在: {src}")
                continue

        # source_group 决定来源独立性
        source_group = _clean(doc_spec.get("source_group")) or _clean(candidate.upstream_hint)
        if not source_group:
            errors.append(
                f"{cand_id}: 缺少 source_group（也没有 candidate.upstream_hint 可回退）—— 无法判定来源独立性"
            )
            continue

        title = _clean(doc_spec.get("title")) or (src.name if src else "")
        if not title:
            errors.append(f"{cand_id}: 缺少 document.title")
            continue

        doc_id = _clean(doc_spec.get("document_id")) or make_document_id(
            url=url or None,
            title=title,
            published_at=_clean(doc_spec.get("published_at")) or None,
            issuer=_clean(doc_spec.get("issuer")) or None,
        )
        if is_candidate_id(doc_id):
            errors.append(f"{cand_id}: document_id 不能是 Candidate ID: {doc_id}")
            continue
        if doc_id in claimed_doc_ids:
            errors.append(
                f"{cand_id}: 与 {claimed_doc_ids[doc_id]} 争用同一 document_id {doc_id} —— 一次计划里同一份 Document 只能被 promote 一次"
            )
            continue
        claimed_doc_ids[doc_id] = cand_id

        # 幂等 / 冲突
        if candidate.status == "promoted":
            if candidate.promoted_document_id != doc_id:
                errors.append(
                    f"{cand_id}: 已 promote 到 {candidate.promoted_document_id}，与本次 {doc_id} 不一致 —— 明确拒绝"
                    "（如需改指向，请先重置该 Candidate 的 status）"
                )
            elif doc_id not in store.documents or not any(
                l.document_id == doc_id for l in store.links
            ):
                errors.append(
                    f"{cand_id}: status=promoted 但落盘缺 Document/EvidenceLink —— 状态与产物不一致"
                )
            else:
                unchanged.append(cand_id)
            continue

        # 组装目标 Document
        existing_doc = store.documents.get(doc_id)
        if existing_doc is not None:
            probe = copy.deepcopy(existing_doc)
            if src is not None:
                digest = sha256_file(src)
                if probe.sha256 and probe.sha256.lower() != digest.lower():
                    errors.append(
                        f"{cand_id}: 已有 Document {doc_id} 的 sha256 与本次原件不一致 —— 拒绝覆盖（证据可能被替换）"
                    )
                    continue
                probe.local_path = f"raw/{src.name}"
                probe.sha256 = digest
            if url and not probe.url:
                probe.url = url
            if source_group and not probe.source_group:
                probe.source_group = source_group
            for field in ("provider", "upstream_source_type", "upstream_document_id"):
                value = _clean(doc_spec.get(field))
                if value and not getattr(probe, field):
                    setattr(probe, field, value)
            doc_actions.append((existing_doc, probe, src))
        else:
            provider = _clean(doc_spec.get("provider")) or None
            try:
                probe = SourceDocument(
                    document_id=doc_id,
                    # Provider ≠ Source（v3.0.2 §8）：取数服务商默认落 data_vendor
                    source_type=_clean(doc_spec.get("source_type"))
                    or default_source_type_for(provider, "official_database"),
                    title=title,
                    retrieved_at=_clean(doc_spec.get("retrieved_at")) or iso_now(),
                    issuer=_clean(doc_spec.get("issuer")) or None,
                    published_at=_clean(doc_spec.get("published_at")) or None,
                    url=url or None,
                    local_path=f"raw/{src.name}" if src else None,
                    sha256=sha256_file(src) if src else None,
                    source_group=source_group,
                    page_count=_coerce_int(doc_spec.get("page_count")),
                    sections=[str(s) for s in (doc_spec.get("sections") or [])],
                    note=_clean(doc_spec.get("note")) or None,
                    provider=provider,
                    upstream_source_type=_clean(doc_spec.get("upstream_source_type")) or None,
                    upstream_document_id=_clean(doc_spec.get("upstream_document_id")) or None,
                )
                probe.validate()
            except Exception as exc:
                errors.append(f"{cand_id}: Document 字段非法: {exc}")
                continue
            doc_actions.append((None, probe, src))

        virtual_docs[doc_id] = probe
        if src is not None:
            source_of[doc_id] = src

        # 组装 EvidenceLink
        links_spec = item.get("links")
        if not isinstance(links_spec, list) or not links_spec:
            errors.append(
                f"{cand_id}: 没有任何 links —— promote 必须同时形成 Document 与 EvidenceLink（§6 硬规则 5）"
            )
            continue

        local_links: List[EvidenceLink] = []
        for lk in links_spec:
            if not isinstance(lk, dict):
                errors.append(f"{cand_id}: links 条目不是对象: {lk!r}")
                continue
            claim_id = _clean(lk.get("claim_id"))
            if not claim_id:
                errors.append(f"{cand_id}: link 缺少 claim_id")
                continue
            if claim_id not in store.claims:
                errors.append(f"{cand_id}: 引用了不存在的 Claim {claim_id}")
                continue

            verify_path = source_of.get(doc_id) or store.resolve_local_path(probe)
            excerpt = _clean(lk.get("evidence_text"))
            anchor = _clean(lk.get("excerpt_anchor"))
            if anchor:
                # 「从原文抽取」优先于「人写摘录」：能剪就别写
                if verify_path is None or not verify_path.is_file():
                    errors.append(
                        f"{cand_id}: 指定了 excerpt_anchor 但 {doc_id} 没有可读原件，无法抽取摘录"
                    )
                    continue
                try:
                    excerpt = extract_verbatim(
                        verify_path,
                        anchor=anchor,
                        tail=_coerce_int(lk.get("excerpt_tail")) or 0,
                    )
                except VerbatimError as exc:
                    errors.append(f"{cand_id}: 从原文抽取摘录失败: {exc}")
                    continue

            # 硬规则 2
            if excerpt:
                if verify_path is None or not verify_path.is_file():
                    errors.append(
                        f"{cand_id}: 提供了 evidence_text 但 {doc_id} 没有可读原件，"
                        "无法验证摘录真实性 —— 请先绑定 local_file"
                    )
                    continue
                ok_ex, why = text_supports_excerpt(excerpt, verify_path)
                if not ok_ex:
                    errors.append(f"{cand_id}: {why}（文件 {verify_path.name}）")
                    continue

            explicit_id = _clean(lk.get("evidence_id"))
            if explicit_id:
                if explicit_id in used_evidence_ids:
                    errors.append(f"{cand_id}: evidence_id 已存在: {explicit_id}")
                    continue
                evidence_id = explicit_id
                used_evidence_ids.add(evidence_id)
            else:
                evidence_id = allocate_evidence_id(claim_id)

            try:
                link = EvidenceLink(
                    evidence_id=evidence_id,
                    claim_id=claim_id,
                    document_id=doc_id,
                    page=_coerce_int(lk.get("page")),
                    section=_clean(lk.get("section")) or None,
                    paragraph=_clean(lk.get("paragraph")) or None,
                    table=_clean(lk.get("table")) or None,
                    evidence_text=excerpt or None,
                    support_type=_clean(lk.get("support_type")) or "direct",
                    confidence=float(lk.get("confidence", 1.0)),
                    note=_clean(lk.get("note")) or None,
                    excerpt_verification_status=_clean(lk.get("excerpt_verification_status")) or None,
                    excerpt_verification_method=_clean(lk.get("excerpt_verification_method")) or None,
                    excerpt_verification_source=_clean(lk.get("excerpt_verification_source")) or None,
                )
                link.validate()
            except Exception as exc:
                errors.append(f"{cand_id}: EvidenceLink 字段非法: {exc}")
                continue

            problems = validate_locator(link, probe)
            if problems:
                errors.append(f"{cand_id}: {link.evidence_id} 定位不合法: {'; '.join(problems)}")
                continue

            local_links.append(link)

        if not local_links:
            if len(errors) == start:
                errors.append(
                    f"{cand_id}: 没有任何合法的 EvidenceLink —— promote 必须同时形成 Document + Link"
                )
            continue

        link_actions.extend(local_links)
        cand_actions.append((candidate, doc_id))

    # ---------------- 校验闸门 ----------------
    if errors:
        emit("")
        emit("❌ 校验失败，未做任何改动：")
        for e in errors:
            emit(f"   - {e}")
        return False, dict(EMPTY_STATS)

    stats["documents_created"] = sum(1 for old, _, _ in doc_actions if old is None)
    stats["documents_reused"] = sum(1 for old, _, _ in doc_actions if old is not None)
    stats["links_added"] = len(link_actions)
    stats["promoted"] = len(cand_actions)
    stats["unchanged"] = len(unchanged)

    if dry_run:
        for cid in unchanged:
            emit(f"  · {cid} 已是 promoted 且内容一致，跳过")
        for old, new, src in doc_actions:
            verb = "复用" if old is not None else "新建"
            name = src.name if src else "（无文件）"
            emit(f"  · 将{verb} Document {new.document_id}  {new.title} ← {name}")
        for link in link_actions:
            emit(f"  · 将新增 {link.evidence_id} → {link.claim_id} @ {link.document_id}")
        for cand, doc_id in cand_actions:
            emit(f"  · 将 {cand.candidate_id} 标记为 promoted（{doc_id}）")
        emit("")
        emit("（dry-run：以上改动均未落盘）")
        return True, stats

    # ---------------- Pass 3：落盘（异常则回滚内存状态） ----------------
    snapshot = copy.deepcopy(store)
    try:
        store.raw_dir.mkdir(parents=True, exist_ok=True)

        for old, new, src in doc_actions:
            if src is not None:
                target = store.raw_dir / src.name
                if src.resolve() != target.resolve():
                    shutil.copy2(src, target)
            if old is None:
                store.documents[new.document_id] = new
                emit(f"  ✅ 新建 Document {new.document_id}  ({new.source_type})  {new.title}")
            else:
                for field in _BINDABLE_FIELDS:
                    setattr(old, field, getattr(new, field))
                emit(f"  ✅ 复用 Document {old.document_id}  {old.title}")

        for link in link_actions:
            store.links.append(link)
            emit(f"  ✅ 新增 {link.evidence_id} → {link.claim_id} @ {link.document_id}")

        for cand, doc_id in cand_actions:
            cand.status = "promoted"
            cand.promoted_document_id = doc_id
            emit(f"  ✅ {cand.candidate_id} → promoted（{doc_id}）")

        # ---------------- Pass 4：摘录验证状态（v3.0.2 §9） ----------------
        declared = {l.evidence_id for l in link_actions if l.excerpt_verification_status}
        pending = [l for l in store.links if l.evidence_id not in declared]
        counts = stamp_excerpt_verification(store, base_dir=store.root, links=pending)
        emit(
            "  ℹ️ 摘录验证："
            f"verified={counts['verified']}  unverified={counts['unverified']}  "
            f"无需验证={counts['skipped']}（已显式声明 {len(declared)} 条）"
        )
    except Exception as exc:  # 落盘阶段异常 → 回滚，不留半成品
        store.documents = snapshot.documents
        store.claims = snapshot.claims
        store.links = snapshot.links
        store.candidates = snapshot.candidates
        emit(f"❌ 落盘阶段异常，已回滚：{exc}")
        return False, dict(EMPTY_STATS)

    return True, stats


def main() -> int:
    ap = argparse.ArgumentParser(description="把 EvidenceCandidate 摄入为正式 Document + EvidenceLink")
    ap.add_argument("evidence_dir", help="Evidence Store 目录（含 candidates.jsonl）")
    ap.add_argument("--plan", required=True, help="计划文件 promote_plan.json")
    ap.add_argument("--dry-run", action="store_true", help="完整校验并打印改动，但不落盘")
    args = ap.parse_args()

    root = Path(args.evidence_dir)
    if not root.exists():
        print(f"❌ Evidence 目录不存在: {root}")
        return 2
    plan_path = Path(args.plan)
    try:
        plan = load_plan(plan_path)
    except PromotionError as exc:
        print(f"❌ {exc}")
        return 2

    store = EvidenceStore.open(root)
    print("=" * 72)
    print(f"摄入线索为正式证据 → {root}")
    print(f"计划文件: {plan_path}（相对路径以此目录为基准）")
    print("=" * 72)
    ok, stats = apply_promotion(
        store, plan, dry_run=args.dry_run, base_dir=plan_path.parent
    )
    if ok:
        if not args.dry_run:
            store.save()
        print("")
        print(
            f"✅ 完成：promote {stats['promoted']} 条线索；"
            f"新建 {stats['documents_created']} / 复用 {stats['documents_reused']} 份 Document；"
            f"新增 {stats['links_added']} 条链接"
            + (f"；跳过 {stats['unchanged']} 条（已是 promoted）" if stats["unchanged"] else "")
            + ("（dry-run，未落盘）" if args.dry_run else "")
        )
    print("=" * 72)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
