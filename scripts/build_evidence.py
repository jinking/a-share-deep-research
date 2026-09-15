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
    print(f"   - {store.documents_path.name}")
    print(f"   - {store.claims_path.name}")
    print(f"   - {store.links_path.name}")
    print(f"   - {store.raw_dir.name}/  （原始证据文件放这里）")
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
    print(f"documents={len(store.documents)}  claims={len(store.claims)}  links={len(store.links)}")
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

    return ap


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
