#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Evidence Store 构建与自检工具（v3.0 §6 / §21）。

所有确定性动作（生成 document_id、计算 sha256、建目录、读回校验）都在这里完成，
Agent 不再手工算 hash、手工建证据目录。

用法：
    # 1) 初始化一个研究的证据库
    python3 scripts/build_evidence.py init research_sz002897/evidence

    # 2) 登记一份原始文档（自动复制到 raw/ 并计算 sha256）
    python3 scripts/build_evidence.py register research_sz002897/evidence \
      --file ~/Downloads/2026H1.pdf \
      --type interim_report \
      --title "意华股份2026年半年度报告" \
      --issuer 意华股份 \
      --published-at 2026-08-25 \
      --url "https://www.cninfo.com.cn/..." \
      --group CNINFO_002897_2026H1 \
      --pages 168

    # 3) 只校验证据库自身（不需要报告 / manifest）
    python3 scripts/build_evidence.py validate research_sz002897/evidence

    # 4) 仅复核原始文件是否被替换
    python3 scripts/build_evidence.py verify research_sz002897/evidence

    # 5) 查看当前证据库清单
    python3 scripts/build_evidence.py show research_sz002897/evidence

    # 6) 登记一条「线索」——线索 ≠ 证据（v3.0.1 §5）
    python3 scripts/build_evidence.py add-candidate research_sz002897/evidence \
      --type media --title "财联社：意华股份高速连接器进展" \
      --url "https://www.cls.cn/detail/123" --claim C_ORDER_224G_STATUS \
      --provider neodata --upstream CLS_20260915_001

    # 7) 列出线索
    python3 scripts/build_evidence.py candidates research_sz002897/evidence

线索要变成正式证据，走 `promote_evidence_candidate.py`（唯一通道）：
    python3 scripts/promote_evidence_candidate.py research_sz002897/evidence --plan promote_plan.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.evidence import EvidenceStore, EvidenceStoreError, sha256_file  # noqa: E402
from core.evidence.locator import describe_locator  # noqa: E402
from core.issue import Issue  # noqa: E402
from core.models.base import iso_now  # noqa: E402
from core.models.candidate import (  # noqa: E402
    CANDIDATE_STATUSES,
    EvidenceCandidate,
    make_candidate_id,
)
from core.validation import validate_evidence_store  # noqa: E402


def _collector(bucket: List[Issue]):
    def emit(severity: str, code: str, message: str, detail: str = "") -> None:
        bucket.append(Issue(severity, code, message, detail))

    return emit


def _print_issues(issues: List[Issue]) -> None:
    for issue in issues:
        if issue.severity == "INFO":
            continue
        line = f"  [{issue.severity}] {issue.code}: {issue.message}"
        if issue.detail:
            line += f" | {issue.detail}"
        print(line)


def cmd_init(args) -> int:
    store = EvidenceStore.init(args.dir)
    print(f"✅ 已初始化 Evidence Store: {store.root}")
    print(f"   - {store.candidates_path.name}  （线索：线索 ≠ 证据）")
    print(f"   - {store.documents_path.name}")
    print(f"   - {store.claims_path.name}")
    print(f"   - {store.links_path.name}")
    print(f"   - {store.raw_dir.name}/  （原始证据文件放这里）")
    return 0


def cmd_add_candidate(args) -> int:
    store = EvidenceStore.open(args.dir) if Path(args.dir).exists() else EvidenceStore.init(args.dir)
    if not store.documents_path.exists():
        store.save()
    discovered_at = args.discovered_at or iso_now()
    try:
        cand_id = args.id or make_candidate_id(
            url=args.url,
            title=args.title,
            discovered_at=discovered_at,
            provider=args.provider,
        )
        candidate = EvidenceCandidate(
            candidate_id=cand_id,
            source_type=args.type,
            title=args.title,
            discovered_at=discovered_at,
            status=args.status,
            claim_id=args.claim,
            url=args.url,
            snippet=args.snippet,
            provider=args.provider,
            upstream_hint=args.upstream,
            note=args.note,
        )
        store.add_candidate(candidate)
    except Exception as exc:
        print(f"❌ {exc}")
        return 2
    store.save()
    print(f"✅ 已登记线索: {candidate.candidate_id}")
    print(f"   title        : {candidate.title}")
    print(f"   source_type  : {candidate.source_type}")
    print(f"   discovered_at: {candidate.discovered_at}")
    print(f"   url          : {candidate.url}")
    print(f"   upstream_hint: {candidate.upstream_hint}")
    print("   ⚠️  线索不是证据：要支撑 Claim 必须走 promote_evidence_candidate.py 拿到原件")
    return 0


def cmd_candidates(args) -> int:
    store = EvidenceStore.open(args.dir)
    rows = sorted(store.candidates.values(), key=lambda c: c.candidate_id)
    if args.status:
        rows = [c for c in rows if c.status == args.status]
    print(f"线索（candidates.jsonl）: {len(rows)} 条   ← 线索 ≠ 证据，不参与证据校验")
    for cand in rows:
        print(f"  {cand.candidate_id}  [{cand.status}/{cand.source_type}] {cand.title}")
        if cand.claim_id:
            print(f"      claim: {cand.claim_id}")
        if cand.url:
            print(f"      url  : {cand.url}")
        if cand.promoted_document_id:
            print(f"      → {cand.promoted_document_id}")
        if cand.note:
            print(f"      note : {cand.note}")
    if store.issues:
        print("\n[STORE 读取问题]")
        _print_issues(list(store.issues))
    return 0


def cmd_register(args) -> int:
    store = EvidenceStore.open(args.dir) if Path(args.dir).exists() else EvidenceStore.init(args.dir)
    if not Path(args.dir).joinpath("documents.jsonl").exists():
        store.save()
    try:
        doc = store.register_document(
            source_type=args.type,
            title=args.title,
            issuer=args.issuer,
            published_at=args.published_at,
            url=args.url,
            local_file=args.file,
            local_path=args.local_path,
            source_group=args.group,
            page_count=args.pages,
            sections=args.sections or [],
            copy_into_raw=not args.no_copy,
        )
    except EvidenceStoreError as exc:
        print(f"❌ {exc}")
        return 2
    store.save()
    print(f"✅ 已登记 Document: {doc.document_id}")
    print(f"   title       : {doc.title}")
    print(f"   source_type : {doc.source_type}（{'一手来源' if doc.is_primary else '非一手来源'}）")
    print(f"   published_at: {doc.published_at}")
    print(f"   local_path  : {doc.local_path}")
    print(f"   sha256      : {doc.sha256}")
    print(f"   source_group: {doc.source_group}")
    return 0


def cmd_verify(args) -> int:
    store = EvidenceStore.open(args.dir)
    failed = 0
    for doc in store.documents.values():
        path = store.resolve_local_path(doc)
        if path is None:
            print(f"  ⚠️  {doc.document_id} 无本地文件（仅 URL），无法复核原始版本")
            continue
        if not path.is_file():
            print(f"  ❌ {doc.document_id} 本地文件缺失: {path}")
            failed += 1
            continue
        if not doc.sha256:
            print(f"  ⚠️  {doc.document_id} 未登记 sha256，跳过复核")
            continue
        actual = sha256_file(path)
        if actual.lower() != doc.sha256.lower():
            print(f"  ❌ {doc.document_id} hash 不一致（证据可能被替换）")
            print(f"       登记={doc.sha256}")
            print(f"       实际={actual}")
            failed += 1
        else:
            print(f"  ✅ {doc.document_id} hash 一致")
    print("-" * 72)
    print(f"复核文件: {len(store.documents)} ｜ 失败: {failed}")
    return 1 if failed else 0


def cmd_validate(args) -> int:
    store = EvidenceStore.open(args.dir)
    issues: List[Issue] = []
    summary = validate_evidence_store(
        store.state(),
        emit=_collector(issues),
        research_date=args.research_date,
        documents_base_dir=str(store.root),
        store_issues=store.issues,
    )
    print("=" * 72)
    print("Evidence Store 自检")
    print(f"状态: {'✅ PASS' if summary.get('P0', 0) == 0 and summary.get('P1', 0) == 0 else '❌ FAIL'}")
    print(
        f"P0={summary.get('P0', 0)}  P1={summary.get('P1', 0)}  P2={summary.get('P2', 0)}"
    )
    _print_issues(issues)
    print("=" * 72)
    return 0 if summary.get("P0", 0) == 0 and summary.get("P1", 0) == 0 else 1


def cmd_show(args) -> int:
    store = EvidenceStore.open(args.dir)
    print(f"Evidence Store: {store.root}")
    print(
        f"candidates={len(store.candidates)}（线索，不计入证据）  "
        f"documents={len(store.documents)}  claims={len(store.claims)}  links={len(store.links)}"
    )
    if store.documents:
        print("\n[DOCUMENTS]")
        for doc in store.documents.values():
            flag = "一手" if doc.is_primary else "非一手"
            print(f"  {doc.document_id}  [{doc.source_type}/{flag}] {doc.title} ({doc.published_at or '无日期'})")
    if store.claims:
        print("\n[CLAIMS]")
        for claim in store.claims.values():
            links = store.links_of(claim.claim_id)
            print(f"  {claim.claim_id}  [{claim.category}/{claim.level}/{claim.materiality}/{claim.status}] {claim.claim}")
            for link in links:
                doc = store.document_of(link)
                src = f"{link.document_id}({doc.source_type})" if doc else f"{link.document_id}(缺失)"
                print(f"      - {link.evidence_id} -> {src} [{link.support_type}] {describe_locator(link)}")
    if store.issues:
        print("\n[STORE 读取问题]")
        _print_issues(list(store.issues))
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Evidence Store 构建与自检")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="初始化 Evidence Store 目录结构")
    p.add_argument("dir")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("register", help="登记一个 Document（自动算 sha256）")
    p.add_argument("dir")
    p.add_argument("--file", help="原始文件路径（会复制到 evidence/raw/）")
    p.add_argument("--local-path", dest="local_path", help="直接登记相对 evidence/ 的路径（不复制）")
    p.add_argument("--type", required=True, help="source_type，如 interim_report")
    p.add_argument("--title", required=True)
    p.add_argument("--issuer")
    p.add_argument("--published-at", dest="published_at")
    p.add_argument("--url")
    p.add_argument("--group", dest="group", help="source_group（同一上游转载填同一个值）")
    p.add_argument("--pages", type=int, help="页数，用于定位越界校验")
    p.add_argument("--sections", nargs="*", help="已登记章节标题，用于定位校验")
    p.add_argument("--no-copy", dest="no_copy", action="store_true", help="不复制到 raw/")
    p.set_defaults(func=cmd_register)

    p = sub.add_parser("verify", help="复核本地文件 hash 是否被替换")
    p.add_argument("dir")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("validate", help="只校验证据库自身")
    p.add_argument("dir")
    p.add_argument("--research-date", dest="research_date")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("show", help="查看证据库清单")
    p.add_argument("dir")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("add-candidate", help="登记一条线索（线索 ≠ 证据）")
    p.add_argument("dir")
    p.add_argument("--type", required=True, help="source_type")
    p.add_argument("--title", required=True)
    p.add_argument("--url", help="线索出处链接")
    p.add_argument("--claim", help="该线索想支持的 Claim id")
    p.add_argument("--provider", help="发现渠道，如 neodata / westock")
    p.add_argument("--upstream", dest="upstream", help="上游出处提示（判断是否同源）")
    p.add_argument("--snippet", help="线索摘要（会被注明为非证据）")
    p.add_argument("--discovered-at", dest="discovered_at")
    p.add_argument("--status", default="new", choices=list(CANDIDATE_STATUSES))
    p.add_argument("--id", dest="id", help="显式 candidate_id（默认按 url/标题指纹生成）")
    p.add_argument("--note")
    p.set_defaults(func=cmd_add_candidate)

    p = sub.add_parser("candidates", help="列出线索（不参与证据校验）")
    p.add_argument("dir")
    p.add_argument("--status", choices=list(CANDIDATE_STATUSES))
    p.set_defaults(func=cmd_candidates)

    return ap


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
