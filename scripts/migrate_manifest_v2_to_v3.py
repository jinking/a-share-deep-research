#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v2 manifest → v3 manifest + Evidence Store 迁移（v3.0 §14）。

关键纪律（§19）：迁移只做「结构化搬运」，绝不自动宣称证据已验证。
所有迁移出的对象都会打上 migration_status = "needs_verification"。

用法：
    python3 scripts/migrate_manifest_v2_to_v3.py old_manifest.json \
      --out research_manifest.v3.json \
      --evidence-dir research_sz002897/evidence \
      --critical E001,E002,E007

    # 只产出 v3 manifest（不建证据库）
    python3 scripts/migrate_manifest_v2_to_v3.py old_manifest.json --out v3.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.evidence import EvidenceStore  # noqa: E402
from core.evidence.hasher import make_document_id  # noqa: E402
from core.models.base import iso_now  # noqa: E402
from core.models.claim import V2_LEVEL_ALIASES, Claim  # noqa: E402
from core.models.document import SourceDocument  # noqa: E402
from core.models.evidence import EvidenceLink  # noqa: E402

MIGRATION_STATUS = "needs_verification"

# 章节后缀：「2026 年半年度报告·分行业经营情况」与「…·现金流量表」是同一份文件
_TITLE_SUFFIX_RE = re.compile(r"[·・\-—–:：].*$")
# 明显属于「同一份文件的不同视角」的补充说明
_TITLE_NOISE = (
    "（未经审计）",
    "(未经审计)",
    "投资者关系活动记录",
)


def canonical_title(title: str) -> str:
    """把「半年报·分行业情况」这类标题收敛到同一份文件的规范键。"""
    text = str(title or "").strip()
    for noise in _TITLE_NOISE:
        text = text.replace(noise, "")
    text = _TITLE_SUFFIX_RE.sub("", text).strip()
    return text or str(title or "").strip()


def map_level(raw_level: str) -> Tuple[str, Optional[str]]:
    """v2 中文等级 → v3 等级；无法识别时降级为 unconfirmed 并回传说明。"""
    text = str(raw_level or "").strip()
    if text in V2_LEVEL_ALIASES:
        return V2_LEVEL_ALIASES[text], None
    for alias, level in V2_LEVEL_ALIASES.items():
        if alias and alias in text:
            return level, f"等级由模糊匹配得到: {raw_level!r} -> {level}"
    return "unconfirmed", f"无法识别的 v2 等级 {raw_level!r}，已降级为 unconfirmed，请人工确认"


def migrate(
    data: Dict[str, Any],
    *,
    evidence_dir: Optional[Path] = None,
    critical_ids: Optional[List[str]] = None,
    research_date: Optional[str] = None,
) -> Tuple[Dict[str, Any], Dict[str, int]]:
    critical_ids = set(critical_ids or [])
    company = (data.get("meta") or {}).get("company") or ""
    research_date = research_date or (data.get("meta") or {}).get("research_date")

    v3: Dict[str, Any] = {
        "manifest_version": 3,
        "meta": dict(data.get("meta") or {}),
        "forecast": data.get("forecast") or {},
        "valuation": data.get("valuation") or {},
        "sotp": data.get("sotp") or {},
        "quarterly_tracking": data.get("quarterly_tracking") or [],
        "final": data.get("final") or {},
        "evidence_refs": [],
    }
    if evidence_dir is not None:
        v3["meta"].setdefault("evidence_dir", evidence_dir.name)

    evidence_dir_msg: List[str] = []
    store: Optional[EvidenceStore] = None
    if evidence_dir is not None:
        store = EvidenceStore.init(evidence_dir)

    stats = {"documents": 0, "claims": 0, "links": 0, "unnamed_levels": 0}

    for idx, raw in enumerate(data.get("evidence") or [], start=1):
        if not isinstance(raw, dict):
            continue
        claim_id = str(raw.get("claim_id") or f"E{idx:03d}").strip()
        raw_level = str(raw.get("level") or "")
        level, why = map_level(raw_level)
        if why:
            stats["unnamed_levels"] += 1
            evidence_dir_msg.append(f"[{claim_id}] {why}")

        notes = [f"v2 原文等级={raw_level or '(空)'}"]
        if raw.get("source_ref"):
            notes.append(f"v2 source_ref={raw['source_ref']}")
        if why:
            notes.append(why)

        materiality = "critical" if claim_id in critical_ids else "normal"
        claim_note = "；".join(notes)
        if store is not None:
            store.add_claim(
                Claim(
                    claim_id=claim_id,
                    claim=str(raw.get("claim") or "").strip() or f"{claim_id}（v2 未填写 claim 文本）",
                    category="other",
                    level=level,
                    materiality=materiality,
                    status="pending",
                    migration_status=MIGRATION_STATUS,
                    note=claim_note,
                )
            )
            stats["claims"] += 1

            source_title = str(raw.get("source_title") or "").strip() or f"{claim_id} 来源（v2 未填写）"
            doc_id = make_document_id(
                title=canonical_title(source_title),
                published_at=str(raw.get("source_date") or ""),
                issuer=company,
            )
            doc = SourceDocument(
                document_id=doc_id,
                source_type=str(raw.get("source_type") or "media"),
                title=source_title,
                retrieved_at=iso_now(),
                issuer=company or None,
                published_at=str(raw.get("source_date") or "") or None,
                url=None,
                local_path=None,
                sha256=None,
                source_group=f"MIGRATED_{doc_id}",
                migration_status=MIGRATION_STATUS,
                note=f"由 v2 evidence[{idx}] 迁移，source_ref={raw.get('source_ref')}；尚未校验原始文件",
            )
            try:
                doc.validate()
            except Exception as exc:  # 非法 source_type 等：保留数据但标注
                doc.note = f"{doc.note}；字段校验未通过: {exc}"
                doc.source_type = "media"
            store.documents.setdefault(doc_id, doc)
            stats["documents"] = len(store.documents)

            store.add_link(
                EvidenceLink(
                    evidence_id=f"EV_{claim_id}_01",
                    claim_id=claim_id,
                    document_id=doc_id,
                    support_type="direct",
                    confidence=1.0,
                    evidence_text=None,
                    migration_status=MIGRATION_STATUS,
                    note="迁移生成：无 locator / 无 evidence_text，必须人工补全后方可作为确认级证据",
                )
            )
            stats["links"] += 1

        v3["evidence_refs"].append({"claim_id": claim_id, "importance": materiality})

    if store is not None:
        store.save()

    if evidence_dir_msg:
        print("迁移提示：")
        for line in evidence_dir_msg:
            print(f"  - {line}")

    return v3, stats


def main() -> int:
    ap = argparse.ArgumentParser(description="v2 manifest → v3 manifest 迁移")
    ap.add_argument("manifest", help="v2 research_manifest.json")
    ap.add_argument("--out", required=True, help="输出的 v3 manifest 路径")
    ap.add_argument("--evidence-dir", help="同时生成 Evidence Store 的目录")
    ap.add_argument("--critical", help="逗号分隔的 claim_id，迁移时标记为 critical")
    ap.add_argument("--research-date", help="覆盖 meta.research_date")
    args = ap.parse_args()

    src = Path(args.manifest)
    if not src.is_file():
        print(f"❌ manifest 不存在: {src}")
        return 2
    try:
        data = json.loads(src.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"❌ manifest 无法解析: {exc}")
        return 2

    version = data.get("manifest_version")
    if version not in (None, 2) and "evidence_refs" in data:
        print(f"⚠️  输入看起来已经是 v3（manifest_version={version}），迁移仍会执行，请确认是否需要")

    critical = [x.strip() for x in (args.critical or "").split(",") if x.strip()]
    v3, stats = migrate(
        data,
        evidence_dir=Path(args.evidence_dir) if args.evidence_dir else None,
        critical_ids=critical,
        research_date=args.research_date,
    )

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(v3, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("=" * 72)
    print(f"✅ 已生成 v3 manifest: {out}")
    print(
        f"   documents={stats['documents']}  claims={stats['claims']}  links={stats['links']}"
        f"  evidence_refs={len(v3['evidence_refs'])}"
    )
    print(f"   无法识别的 v2 等级: {stats['unnamed_levels']}")
    print("   ⚠️  所有迁移对象 migration_status=needs_verification：不构成「证据已验证」")
    if args.evidence_dir:
        print(f"   Evidence Store: {args.evidence_dir}")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
