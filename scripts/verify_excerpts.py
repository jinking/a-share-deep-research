#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""重算 Evidence Store 的摘录验证状态（v3.0.2 §9）。

用法：
    # 只报告，不改动
    python3 scripts/verify_excerpts.py examples/意华股份002897_样板/evidence

    # 把结果写回 evidence_links.jsonl
    python3 scripts/verify_excerpts.py examples/意华股份002897_样板/evidence --write

状态**只由机器比对产生**：拿 Document 本地原件的文本（PDF 走同名 .textlayer.txt
文本层，纯文本走文件本身），与 `evidence_text` 做归一化子串比对。

    verified   摘录确实是原文子串
    unverified 比对不通过，或没有可比对的文本（PDF 无文本层 / 只有 URL / 文件缺失）

退出码：
    0 = 校验完成（可存在 unverified，由 Validator 决定是否阻断）
    1 = 参数/文件错误
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
    compute_excerpt_verification,
    resolve_verification_source,
)

__all__ = ["describe_store"]


def describe_store(store: EvidenceStore):
    """返回 [(link, document, 解析出的源路径, 手段, 结果)]，不修改任何对象。"""
    rows = []
    for link in store.links:
        document = store.documents.get(link.document_id)
        path, method = resolve_verification_source(document, store.root)
        result = compute_excerpt_verification(
            link, document, base_dir=store.root, relative_to=store.root
        )
        rows.append((link, document, path, method, result))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="重算 Evidence Store 的摘录验证状态")
    ap.add_argument("evidence_dir", help="Evidence Store 目录")
    ap.add_argument("--write", action="store_true", help="把结果写回 evidence_links.jsonl")
    args = ap.parse_args()

    root = Path(args.evidence_dir)
    if not root.exists():
        print(f"❌ Evidence 目录不存在: {root}")
        return 1
    try:
        store = EvidenceStore.open(root)
    except EvidenceStoreError as exc:
        print(f"❌ Evidence Store 无法读取: {exc}")
        return 1

    from core.evidence.excerpt import stamp_excerpt_verification

    rows = describe_store(store)
    counts = {"verified": 0, "unverified": 0, "skipped": 0}
    print("=" * 72)
    print(f"摘录验证 → {root}")
    print("=" * 72)
    for link, document, path, method, result in rows:
        if result is None:
            counts["skipped"] += 1
            continue
        counts[result["status"]] += 1
        if result["status"] == "verified":
            print(f"  ✅ {link.evidence_id}  {method}  ← {result['source']}")
        else:
            why = "无可比对文本" if path is None else f"未命中 {path.name}"
            print(f"  ❌ {link.evidence_id}  unverified（{why}）")
    print("-" * 72)
    print(
        f"verified={counts['verified']}  unverified={counts['unverified']}  "
        f"无需验证={counts['skipped']}"
    )

    if args.write:
        written = stamp_excerpt_verification(store, base_dir=store.root)
        store.save()
        print(
            f"已写回 {root / 'evidence_links.jsonl'}（verified={written['verified']}  "
            f"unverified={written['unverified']}）"
        )
    else:
        print("（未加 --write，未改动任何文件）")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
