#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""来源独立性判断（v3.0 §5.1 source_group、§8.2 EVIDENCE_SOURCE_NOT_INDEPENDENT）。

核心事实：财联社原始报道 → 新浪转载 → 雪球转载，是 3 个 Document、1 个独立来源。

v3.0.2 §8 追加一条同样重要的情形：

    westock-data（Provider） + 公司公告
    └─ 如果两者其实来自同一份官方原件，只能算一个独立来源

这条关系用 `upstream_document_id` 表达：声明了上游的 Document，其独立性键
由上游决定（可多级传递）。上游不在本库时直接用该上游 ID 作键 —— 这正是
「同一份被引用的官方原件」应有的合并语义。
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
]


def _resolve_root(
    doc: SourceDocument, docs_by_id: Optional[Mapping[str, SourceDocument]]
) -> Union[SourceDocument, str]:
    """沿 upstream_document_id 上溯到根；根不在库中时返回该上游 ID 字符串。"""
    seen = {doc.document_id}
    current: SourceDocument = doc
    while True:
        upstream = clean_str(current.upstream_document_id)
        if not upstream or upstream in seen:
            return current
        nxt = docs_by_id.get(upstream) if docs_by_id else None
        if nxt is None:
            return upstream
        seen.add(nxt.document_id)
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
