#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""来源独立性判断（v3.0 §5.1 source_group、§8.2 EVIDENCE_SOURCE_NOT_INDEPENDENT）。

核心事实：财联社原始报道 → 新浪转载 → 雪球转载，是 3 个 Document、1 个独立来源。
"""

from __future__ import annotations

from typing import Dict, Iterable, List

from ..models.document import SourceDocument

__all__ = [
    "independence_key",
    "group_documents",
    "independent_source_count",
    "describe_groups",
    "shared_upstream_hint",
]


def independence_key(doc: SourceDocument) -> str:
    return doc.independence_key


def group_documents(docs: Iterable[SourceDocument]) -> Dict[str, List[str]]:
    """按独立性键聚合：key -> [document_id, ...]。"""
    groups: Dict[str, List[str]] = {}
    for doc in docs:
        groups.setdefault(independence_key(doc), []).append(doc.document_id)
    return groups


def independent_source_count(docs: Iterable[SourceDocument]) -> int:
    return len(group_documents(docs))


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
