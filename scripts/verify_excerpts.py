#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""重算并**比对** Evidence Store 的摘录验证状态（v3.0.2 §9 / v3.0.3 §5）。

用法：

    # 重算 + 与落盘值比对（默认行为；不改动任何文件）
    python3 scripts/verify_excerpts.py examples/意华股份002897_样板/evidence

    # 刷新缓存：把重算结果写回 evidence_links.jsonl
    python3 scripts/verify_excerpts.py examples/意华股份002897_样板/evidence --write

默认行为是**质疑缓存**，而不是刷新它。原因（§5 核心原则）：

    Persisted verification state = machine-derived cache
                                  ≠ user assertion

落盘的 `excerpt_verification_status` 只是一个字段，谁都能改。所以这里先重算，
再逐条与落盘值比对，把不一致报出来——而不是默默用重算结果覆盖掉证据。

比对只抓**单向**：`stored=verified` 而重算不通过才算 mismatch。反过来
（存的是 unverified、实际能验证）只是缓存陈旧、方向保守，不算违规，
`--write` 会顺手刷新它。

退出码：
    0 = 全部一致，且没有 critical Claim 的摘录处于 unverified
    1 = 存在 mismatch，或存在 critical Claim 的未验证摘录
    2 = 参数/文件错误
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.evidence import EvidenceStore, EvidenceStoreError  # noqa: E402
from core.evidence.excerpt import (  # noqa: E402
    compare_excerpt_verification,
    stamp_excerpt_verification,
)

__all__ = ["collect_rows", "critical_unverified_of"]


def collect_rows(store: EvidenceStore):
    """重算全部链接并与落盘值比对。返回 compare 行列表（只读）。"""
    return compare_excerpt_verification(store, base_dir=store.root)


def critical_unverified_of(store: EvidenceStore, rows):
    """重算结果为 unverified、且其 Claim 是 critical 的摘录。"""
    out = []
    for row in rows:
        if row["recomputed"] == "verified":
            continue
        claim = store.claims.get(row["claim_id"])
        if claim is not None and claim.materiality == "critical":
            out.append(row)
    return out


def _short(row) -> str:
    src = row["source"] or "无可比对文本"
    return f"stored={row['stored'] or '未声明'} / recomputed={row['recomputed']}  ← {src}"


def main() -> int:
    ap = argparse.ArgumentParser(description="重算并比对 Evidence Store 的摘录验证状态")
    ap.add_argument("evidence_dir", help="Evidence Store 目录")
    ap.add_argument("--write", action="store_true", help="把重算结果写回 evidence_links.jsonl（刷新缓存）")
    args = ap.parse_args()

    root = Path(args.evidence_dir)
    if not root.is_dir():
        print(f"❌ Evidence 目录不存在: {root}")
        return 2
    try:
        store = EvidenceStore.open(root)
    except EvidenceStoreError as exc:
        print(f"❌ Evidence Store 无法读取: {exc}")
        return 2

    rows = collect_rows(store)
    # 「真比对过、结果不符」才算 mismatch；拿不到原文是 incomparable（无法校验），
    # 两者不可混淆——后者证明的是「现在比不了」，不是「摘录是假的」。
    mismatches = [r for r in rows if not r["match"] and r["source"] is not None]
    incomparable = [r for r in rows if not r["match"] and r["source"] is None]
    critical_unverified = critical_unverified_of(store, rows)
    verified = sum(1 for r in rows if r["recomputed"] == "verified")
    unverified = len(rows) - verified

    print("=" * 72)
    print(f"摘录验证（重算并比对）→ {root}")
    print("=" * 72)
    for row in rows:
        mark = "✅" if row["match"] else ("⚠️" if row["source"] is None else "❌")
        print(f"  {mark} {row['evidence_id']}  {_short(row)}")
    if not rows:
        print("  （没有任何带摘录的链接）")
    print("-" * 72)
    print(f"链接 {len(rows)}  verified {verified}  unverified {unverified}")
    print(
        f"mismatch={len(mismatches)}  incomparable={len(incomparable)}  "
        f"critical unverified={len(critical_unverified)}"
    )

    if args.write:
        written = stamp_excerpt_verification(store, base_dir=store.root)
        store.save()
        print(
            f"已写回 {root / 'evidence_links.jsonl'}"
            f"（刷新 verified={written['verified']}  unverified={written['unverified']}）"
        )
        refreshed = collect_rows(store)
        remaining = [r for r in refreshed if not r["match"] and r["source"] is not None]
        crit_remaining = critical_unverified_of(store, refreshed)
        print(f"刷新后 mismatch={len(remaining)}  critical unverified={len(crit_remaining)}")
        # 刷新缓存能消掉 mismatch，但消不掉「原文里确实没有这句摘录」
        if crit_remaining:
            print("❌ 仍有 critical Claim 的摘录无法在原文中命中 —— 需要补齐原件或撤回该摘录")
            print("=" * 72)
            return 1
        print("=" * 72)
        return 0

    if mismatches or critical_unverified:
        for row in mismatches:
            print(f"  ⚠️ {row['evidence_id']}：{_short(row)}（缓存与重算结果不符）")
        for row in critical_unverified:
            print(f"  ⚠️ {row['evidence_id']}：critical Claim {row['claim_id']} 的摘录未能在原文命中")
        print("   跑 `verify_excerpts.py … --write` 刷新缓存，或修正摘录/补齐原件")
        print("=" * 72)
        return 1
    if incomparable:
        print(f"  ℹ️ {len(incomparable)} 条无法比对（原件缺失或无文本层）：无法校验 ≠ 已被证伪，")
        print("     由 EVIDENCE_HASH_UNVERIFIED / EVIDENCE_EXCERPT_UNVERIFIED 分别处理")

    print("✅ 全部一致，且没有 critical Claim 的未验证摘录")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
