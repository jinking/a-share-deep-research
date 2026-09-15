#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Evidence Store 独立验收（v3.0 §21 第 2 步）。

只检查 Evidence 层，不需要报告与 manifest；返回退出码便于 CI 使用。

用法：
    python3 scripts/validate_evidence.py research_sz002897/evidence
    python3 scripts/validate_evidence.py research_sz002897/evidence --research-date 2026-09-14
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.evidence import EvidenceStore, EvidenceStoreError  # noqa: E402
from core.issue import Issue  # noqa: E402
from core.validation import validate_evidence_store  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Evidence Store 独立验收")
    ap.add_argument("evidence_dir", help="evidence/ 目录")
    ap.add_argument("--research-date", dest="research_date", help="研究日期（YYYY-MM-DD）")
    ap.add_argument("--out", help="验收报告输出目录（可选，写 validation_report.md）")
    args = ap.parse_args()

    path = Path(args.evidence_dir)
    if not path.exists():
        print(f"❌ Evidence 目录不存在: {path}")
        return 2

    try:
        store = EvidenceStore.open(path)
    except EvidenceStoreError as exc:
        print(f"❌ Evidence Store 无法读取: {exc}")
        return 2

    issues: List[Issue] = []
    summary = validate_evidence_store(
        store.state(research_date=args.research_date),
        emit=lambda s, c, m, d="": issues.append(Issue(s, c, m, d)),
        research_date=args.research_date,
        documents_base_dir=str(path),
        store_issues=store.issues,
    )

    passed = summary.get("P0", 0) == 0 and summary.get("P1", 0) == 0
    print("=" * 72)
    print(f"Evidence Validator — {path}")
    print(f"状态: {'✅ PASS' if passed else '❌ FAIL'}")
    print(f"P0={summary.get('P0',0)}  P1={summary.get('P1',0)}  P2={summary.get('P2',0)}")
    for issue in issues:
        if issue.severity in {"P0", "P1"}:
            print(f"  [{issue.severity}] {issue.code}: {issue.message}" + (f" | {issue.detail}" if issue.detail else ""))
    print(f"documents={len(store.documents)}  claims={len(store.claims)}  links={len(store.links)}")
    print("=" * 72)

    if args.out:
        outdir = Path(args.out)
        outdir.mkdir(parents=True, exist_ok=True)
        lines = [
            "# Evidence Store 验收报告",
            "",
            f"- 目录: `{path}`",
            f"- 状态: {'PASS' if passed else 'FAIL'}",
            f"- P0: {summary.get('P0',0)} ｜ P1: {summary.get('P1',0)} ｜ P2: {summary.get('P2',0)}",
            "",
            "| 等级 | 代码 | 结果 | 详情 |",
            "|---|---|---|---|",
        ]
        for issue in issues:
            lines.append(
                f"| {issue.severity} | `{issue.code}` | {issue.message.replace('|', '/')} | {issue.detail.replace('|', '/')} |"
            )
        (outdir / "evidence_validation_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"验收报告: {outdir / 'evidence_validation_report.md'}")

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
