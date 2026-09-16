#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""为 Evidence Store 绑定本地原始文件，并补全 locator / 原文摘录（v3.0 §6）。

解决的真实问题：研究时已经取到了原始文件（行情表、公告 txt、财报 PDF），
但 Document 登记时不知道本地文件在哪，于是长期停留在「无 url 也无 local_path」，
严格模式下必然 EVIDENCE_NO_SOURCE。

本脚本做三件事：
1. 绑定/新建 Document 的本地文件（复制进 evidence/raw/、算真实 sha256）；
2. 为 EvidenceLink 补 locator（page/section/paragraph/table）与 evidence_text；
3. **防脑补硬闸**：若本地文件是文本类（.txt/.md/.csv/.json/.html/.htm），
   自动校验 evidence_text 是否为该文件的真实子串，不是就整体拒绝。

第 3 条是关键纪律的代码化：摘录只能来自原文，不能"看着像"就写。
校验实现统一在 `core.evidence.verbatim`，与 `promote_evidence_candidate.py`
共用同一套逻辑 —— 防脑补的闸门只能有一个，否则迟早两处漂移。

执行是两阶段的，保证原子性：
    Pass 1/2  只解析与校验（跑在虚拟文档视图上，不碰 store）
    Pass 3    全部通过后才真正改动 store 与 raw/ 目录

用法：
    python3 scripts/attach_local_evidence.py <evidence_dir> --plan attach_plan.json

    # 演练：完整跑一遍校验并打印将发生的改动，但不落盘
    python3 scripts/attach_local_evidence.py evidence --plan attach_plan.json --dry-run

计划文件格式（attach_plan.json）：
    {
      "documents": [
        {
          "key": "kline",                     // 可选别名，供 links 引用
          "document_id": "DOC_9dca3aa1",      // 已存在则绑定；不写则按内容寻址自动生成
          "source_type": "official_database",
          "title": "交易所日线行情数据（westock-data kline）",
          "issuer": "意华股份",
          "published_at": "2026-09-14",
          "url": null,
          "local_file": "raw/kline.txt",      // 相对「计划文件所在目录」解析
          "source_group": "WESTOCK_KLINE_002897",
          "note": "由 attach_local_evidence 绑定"
        }
      ],
      "links": [
        {
          "evidence_id": "EV_E006_01",        // 已存在则更新定位/摘录；否则新增
          "claim_id": "E006",
          "document_id": "DOC_9dca3aa1",      // 或 document_key
          "section": "日线行情表",
          "table": "近 60 个交易日",
          "evidence_text": "| 2026-09-14 | 63.99 | 71.39 | ...",
          "support_type": "partial",
          "confidence": 1.0,
          "note": "本条摘录仅覆盖收盘价与涨幅"
        }
      ]
    }

退出码：
    0 = 全部应用成功
    1 = 存在校验失败（摘录非原文子串 / 引用了不存在的对象等），未落盘
    2 = 参数或文件错误
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

from core.evidence import EvidenceStore  # noqa: E402
from core.evidence.excerpt import stamp_excerpt_verification  # noqa: E402
from core.evidence.hasher import make_document_id, sha256_file  # noqa: E402
from core.evidence.verbatim import TEXT_SUFFIXES, text_supports_excerpt  # noqa: E402
from core.models.base import iso_now  # noqa: E402
from core.models.document import SourceDocument  # noqa: E402
from core.models.evidence import EvidenceLink  # noqa: E402
from core.models.provenance import default_source_type_for  # noqa: E402

__all__ = ["apply_plan", "text_supports_excerpt", "AttachError", "TEXT_SUFFIXES"]


class AttachError(Exception):
    """计划文件本身有问题。"""


def _load_plan(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        raise AttachError(f"计划文件不存在: {path}")
    try:
        plan = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise AttachError(f"计划文件无法解析: {exc}") from exc
    if not isinstance(plan, dict):
        raise AttachError("计划文件根节点必须是 JSON 对象")
    return plan


def apply_plan(
    store: EvidenceStore,
    plan: Dict[str, Any],
    *,
    dry_run: bool = False,
    base_dir: Optional[Path] = None,
    emit=print,
) -> Tuple[bool, Dict[str, int]]:
    """把计划应用到 store；返回 (是否成功, 统计)。

    base_dir：解析计划内相对路径（local_file）的基准目录，默认当前工作目录。
    """
    base = Path(base_dir) if base_dir else Path.cwd()

    def resolve(p: str) -> Path:
        q = Path(str(p)).expanduser()
        return q if q.is_absolute() else (base / q)

    errors: List[str] = []
    stats = {"documents_bound": 0, "documents_created": 0, "links_updated": 0, "links_added": 0}

    virtual_docs: Dict[str, SourceDocument] = dict(store.documents)  # 含计划新建的文档
    source_of: Dict[str, Path] = {}  # document_id → 待绑定的源文件（用于校验摘录）
    key_map: Dict[str, str] = {}  # 计划内 key → 真实 document_id

    bind_actions: List[Tuple[SourceDocument, SourceDocument, Path]] = []  # (原对象, 期望状态, 源文件)
    create_actions: List[Tuple[SourceDocument, Path]] = []
    link_actions: List[Tuple[Dict[str, Any], Optional[EvidenceLink], Any]] = []

    # ---------------- Pass 1：documents ----------------
    for item in plan.get("documents") or []:
        if not isinstance(item, dict):
            errors.append(f"documents 条目不是对象: {item!r}")
            continue
        src: Optional[Path] = None
        if item.get("local_file"):
            src = resolve(item["local_file"])
            if not src.is_file():
                errors.append(f"本地文件不存在: {src}")
                continue

        doc_id = str(item.get("document_id") or "").strip()
        existing = store.documents.get(doc_id) if doc_id else None

        if existing is not None:
            if src is None:
                errors.append(f"{doc_id}: 已存在的 Document 必须提供 local_file 才能绑定")
                continue
            probe = copy.deepcopy(existing)
            probe.local_path = f"raw/{src.name}"
            probe.sha256 = sha256_file(src)
            if item.get("url") is not None:
                probe.url = item.get("url")
            if item.get("source_group"):
                probe.source_group = item["source_group"]
            if item.get("note"):
                probe.note = item["note"]
            # 溯源字段：Provider ≠ Source（v3.0.2 §8），外部上游 ID 单列（v3.0.3 §7）
            for field in (
                "provider",
                "upstream_source_type",
                "upstream_document_id",
                "upstream_external_id",
            ):
                if item.get(field) is not None:
                    setattr(probe, field, item[field])
            virtual_docs[doc_id] = probe
            source_of[doc_id] = src
            bind_actions.append((existing, probe, src))
        else:
            doc = SourceDocument(
                document_id=doc_id
                or make_document_id(
                    url=item.get("url"),
                    title=str(item.get("title") or (src.name if src else "")),
                    published_at=item.get("published_at"),
                    issuer=item.get("issuer"),
                ),
                source_type=str(
                    item.get("source_type")
                    or default_source_type_for(item.get("provider"), "official_database")
                ),
                title=str(item.get("title") or (src.name if src else "未命名文档")),
                retrieved_at=item.get("retrieved_at") or iso_now(),
                issuer=item.get("issuer"),
                published_at=item.get("published_at"),
                url=item.get("url"),
                local_path=f"raw/{src.name}" if src else None,
                sha256=sha256_file(src) if src else None,
                source_group=item.get("source_group"),
                note=item.get("note"),
                provider=item.get("provider"),
                upstream_source_type=item.get("upstream_source_type"),
                upstream_document_id=item.get("upstream_document_id"),
                upstream_external_id=item.get("upstream_external_id"),
            )
            try:
                doc.validate()
            except Exception as exc:
                errors.append(f"新建 Document {doc.document_id} 字段非法: {exc}")
                continue
            virtual_docs[doc.document_id] = doc
            if src is not None:
                source_of[doc.document_id] = src
            if item.get("key"):
                key_map[str(item["key"])] = doc.document_id
            create_actions.append((doc, src))

    # ---------------- Pass 2：links ----------------
    for item in plan.get("links") or []:
        if not isinstance(item, dict):
            errors.append(f"links 条目不是对象: {item!r}")
            continue
        evidence_id = str(item.get("evidence_id") or "").strip()
        claim_id = str(item.get("claim_id") or "").strip()
        document_id = str(item.get("document_id") or "").strip()
        if not document_id and item.get("document_key"):
            document_id = key_map.get(str(item["document_key"]), "")
            if not document_id:
                errors.append(f"{evidence_id}: document_key={item['document_key']} 未在 documents 中定义")
                continue
        if not all([evidence_id, claim_id, document_id]):
            errors.append(f"links 条目缺少 evidence_id/claim_id/document_id: {item!r}")
            continue
        if claim_id not in store.claims:
            errors.append(f"{evidence_id}: 引用了不存在的 Claim {claim_id}")
            continue
        doc = virtual_docs.get(document_id)
        if doc is None:
            errors.append(f"{evidence_id}: 引用了不存在的 Document {document_id}")
            continue

        excerpt = str(item.get("evidence_text") or "")

        # 防脑补硬闸：摘录必须来自真实原文
        if excerpt:
            verify_path = source_of.get(document_id)
            if verify_path is None:
                verify_path = store.resolve_local_path(doc)
            if verify_path is None or not verify_path.is_file():
                errors.append(
                    f"{evidence_id}: 提供了 evidence_text，但 {document_id} 没有可读的本地文件，"
                    "无法验证摘录真实性 —— 请先绑定 local_file"
                )
                continue
            ok, why = text_supports_excerpt(excerpt, verify_path)
            if not ok:
                errors.append(f"{evidence_id}: {why}（文件 {verify_path.name}）")
                continue

        payload = dict(
            evidence_id=evidence_id,
            claim_id=claim_id,
            document_id=document_id,
            page=item.get("page"),
            section=item.get("section"),
            paragraph=item.get("paragraph"),
            table=item.get("table"),
            evidence_text=excerpt or None,
            support_type=str(item.get("support_type") or "direct"),
            confidence=float(item.get("confidence", 1.0)),
            note=item.get("note"),
            excerpt_verification_status=item.get("excerpt_verification_status"),
            excerpt_verification_method=item.get("excerpt_verification_method"),
            excerpt_verification_source=item.get("excerpt_verification_source"),
        )
        target = next((l for l in store.links if l.evidence_id == evidence_id), None)
        if target is None:
            try:
                EvidenceLink(**payload).validate()
            except Exception as exc:
                errors.append(f"新增 EvidenceLink {evidence_id} 字段非法: {exc}")
                continue
        link_actions.append((payload, target, item.get("migration_status")))

    # ---------------- 校验闸门 ----------------
    if errors:
        emit("")
        emit("❌ 校验失败，未做任何改动：")
        for e in errors:
            emit(f"   - {e}")
        return False, stats

    stats["documents_bound"] = len(bind_actions)
    stats["documents_created"] = len(create_actions)
    stats["links_updated"] = sum(1 for _, t, _ in link_actions if t is not None)
    stats["links_added"] = sum(1 for _, t, _ in link_actions if t is None)

    if dry_run:
        for _, probe, src in bind_actions:
            emit(f"  · 将绑定 {probe.document_id} ← {src.name}（sha256={probe.sha256[:12]}…）")
        for doc, src in create_actions:
            name = src.name if src else "（无文件）"
            emit(f"  · 将新建 {doc.document_id}  ({doc.source_type})  {doc.title} ← {name}")
        for payload, target, _ in link_actions:
            verb = "更新" if target is not None else "新增"
            emit(f"  · 将{verb} {payload['evidence_id']} → {payload['document_id']}")
        emit("")
        emit("（dry-run：以上改动均未落盘）")
        return True, stats

    # ---------------- Pass 3：落盘 ----------------
    store.raw_dir.mkdir(parents=True, exist_ok=True)

    for existing, probe, src in bind_actions:
        target = store.raw_dir / src.name
        if src.resolve() != target.resolve():
            shutil.copy2(src, target)
        for field in (
            "local_path",
            "sha256",
            "url",
            "source_group",
            "note",
            "provider",
            "upstream_source_type",
            "upstream_document_id",
            "upstream_external_id",
        ):
            setattr(existing, field, getattr(probe, field))
        emit(f"  ✅ 绑定 {existing.document_id} ← {src.name}  sha256={existing.sha256[:12]}…")

    for doc, src in create_actions:
        if src is not None:
            target = store.raw_dir / src.name
            if src.resolve() != target.resolve():
                shutil.copy2(src, target)
        store.documents[doc.document_id] = doc
        emit(f"  ✅ 新建 {doc.document_id}  ({doc.source_type})  {doc.title}")

    for payload, target, migration_status in link_actions:
        if target is not None:
            for key, value in payload.items():
                setattr(target, key, value)
            target.migration_status = migration_status
            emit(f"  ✅ 更新 {payload['evidence_id']} → {payload['document_id']}")
        else:
            store.links.append(EvidenceLink(**payload))
            emit(f"  ✅ 新增 {payload['evidence_id']} → {payload['document_id']}")

    # ---------------- Pass 4：摘录验证状态（v3.0.2 §9） ----------------
    # 状态来自机器比对，而不是人手填写；plan 显式声明的验证结果予以保留。
    declared = {
        str(item.get("evidence_id"))
        for item in (plan.get("links") or [])
        if isinstance(item, dict) and item.get("excerpt_verification_status")
    }
    pending = [l for l in store.links if l.evidence_id not in declared]
    counts = stamp_excerpt_verification(store, base_dir=store.root, links=pending)
    emit(
        "  ℹ️ 摘录验证："
        f"verified={counts['verified']}  unverified={counts['unverified']}  "
        f"无需验证={counts['skipped']}（已显式声明 {len(declared)} 条）"
    )

    return True, stats


def main() -> int:
    ap = argparse.ArgumentParser(description="为证据库绑定本地原始文件并补全定位/摘录")
    ap.add_argument("evidence_dir", help="Evidence Store 目录（含 documents.jsonl）")
    ap.add_argument("--plan", required=True, help="计划文件 attach_plan.json")
    ap.add_argument("--dry-run", action="store_true", help="完整校验并打印改动，但不落盘")
    args = ap.parse_args()

    root = Path(args.evidence_dir)
    if not root.exists():
        print(f"❌ Evidence 目录不存在: {root}")
        return 2
    try:
        plan_path = Path(args.plan)
        plan = _load_plan(plan_path)
    except AttachError as exc:
        print(f"❌ {exc}")
        return 2

    store = EvidenceStore.open(root)
    print("=" * 72)
    print(f"绑定本地证据 → {root}")
    print(f"计划文件: {plan_path}（相对路径以此目录为基准）")
    print("=" * 72)
    ok, stats = apply_plan(store, plan, dry_run=args.dry_run, base_dir=plan_path.parent)
    if ok:
        if not args.dry_run:
            store.save()
        print("")
        print(
            f"✅ 完成：绑定 {stats['documents_bound']} / 新建 {stats['documents_created']} 文档；"
            f"更新 {stats['links_updated']} / 新增 {stats['links_added']} 证据链接"
            + ("（dry-run，未落盘）" if args.dry_run else "")
        )
    print("=" * 72)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
