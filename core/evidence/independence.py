#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""来源独立性判断（v3.0 §5.1 source_group、§8.2 EVIDENCE_SOURCE_NOT_INDEPENDENT）。

核心事实：财联社原始报道 → 新浪转载 → 雪球转载，是 3 个 Document、1 个独立来源。

v3.0.2 §8 追加一条同样重要的情形：

    westock-data（Provider） + 公司公告
    └─ 如果两者其实来自同一份官方原件，只能算一个独立来源

这条关系用 `upstream_document_id` 表达：声明了上游的 Document，其独立性键
由上游决定（可多级传递）。

v3.0.3 §7 补两条同样不能漏的边界：

1. 上游**不在本库**时，用 `upstream_external_id`（外部引用 ID）作键；两者都没有
   才退回这个悬空引用本身。悬空引用会被 Validator 报 P1 `EVIDENCE_UPSTREAM_UNKNOWN`，
   但在独立性上仍然按「同一上游」合并 —— 报错与合并是两件事，且这里的方向是保守的。
2. 上游成环（A→B→A）时整环收敛成**一个**键。否则「两条互相转载的稿件」就能满足
   双源确认 —— 那是把环路当成了两个独立来源，方向恰好是危险的。
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Mapping, Optional, Union

from ..models.base import clean_str
from ..models.document import SourceDocument

__all__ = [
    "independence_key",
    "group_documents",
    "independent_source_count",
    "describe_groups",
    "shared_upstream_hint",
    "upstream_cycle",
]


def _resolve_root(
    doc: SourceDocument, docs_by_id: Optional[Mapping[str, SourceDocument]]
) -> Union[SourceDocument, str]:
    """沿 upstream_document_id 上溯到根；上游不在库中时返回该上游 ID 字符串。"""
    seen = {doc.document_id}
    current: SourceDocument = doc
    while True:
        upstream = clean_str(current.upstream_document_id)
        if upstream and upstream not in seen:
            nxt = docs_by_id.get(upstream) if docs_by_id else None
            if nxt is not None:
                seen.add(nxt.document_id)
                current = nxt
                continue
            # 上游不在本库：能用外部上游 ID 就用它，否则用这个引用本身作合并键。
            return clean_str(current.upstream_external_id) or upstream
        # 无本库上游，或已回到走过的节点（成环）：
        # 外部上游 ID 同样是一个有效的合并键（如「服务商镜像」与「官方原件」共用 CNINFO 编号）。
        external = clean_str(current.upstream_external_id)
        if external:
            return external
        if upstream:
            # 成环：整环只算一个来源（取环上最小 document_id 作稳定键）。
            return min(seen)
        return current


def upstream_cycle(
    doc: SourceDocument, docs_by_id: Optional[Mapping[str, SourceDocument]] = None
) -> Optional[List[str]]:
    """若 `doc` 的上游链成环，返回环上的 document_id 列表；否则返回 None。

    只读，供 Validator 报告用（`EVIDENCE_UPSTREAM_UNKNOWN` 的成因之一）。
    """
    if docs_by_id is None:
        return None
    seen: Dict[str, int] = {doc.document_id: 0}
    order: List[str] = [doc.document_id]
    current = doc
    while True:
        upstream = clean_str(current.upstream_document_id)
        if not upstream:
            return None
        if upstream in seen:
            return order[seen[upstream]:]
        nxt = docs_by_id.get(upstream)
        if nxt is None:
            return None
        seen[nxt.document_id] = len(order)
        order.append(nxt.document_id)
        current = nxt


def independence_key(
    doc: SourceDocument, docs_by_id: Optional[Mapping[str, SourceDocument]] = None
) -> str:
    """独立性键：同一上游（含多级传递）的转载共享同一个键。"""
    root = _resolve_root(doc, docs_by_id)
    if isinstance(root, str):
        return root
    return root.source_group or root.document_id


def group_documents(
    docs: Iterable[SourceDocument],
    docs_by_id: Optional[Mapping[str, SourceDocument]] = None,
) -> Dict[str, List[str]]:
    """按独立性键聚合：key -> [document_id, ...]。"""
    items = list(docs)
    if docs_by_id is None:
        docs_by_id = {d.document_id: d for d in items}
    groups: Dict[str, List[str]] = {}
    for doc in items:
        groups.setdefault(independence_key(doc, docs_by_id), []).append(doc.document_id)
    return groups


def independent_source_count(
    docs: Iterable[SourceDocument],
    docs_by_id: Optional[Mapping[str, SourceDocument]] = None,
) -> int:
    return len(group_documents(docs, docs_by_id))


def describe_groups(groups: Dict[str, List[str]]) -> str:
    return "; ".join(
        f"{key} -> [{', '.join(ids)}]" for key, ids in sorted(groups.items())
    )


def shared_upstream_hint(groups: Dict[str, List[str]]) -> str:
    """给人工排查用的提示：哪些 Document 其实是同一上游。"""
    shared = {k: v for k, v in groups.items() if len(v) > 1}
    if not shared:
        return ""
    return "同一上游来源（只算一个独立来源）: " + describe_groups(shared)
