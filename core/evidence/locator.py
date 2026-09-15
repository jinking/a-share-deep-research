#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""证据定位（v3.0 §5.3 / §8.2 EVIDENCE_LOCATOR_MISSING）。

定位要求：page / section / paragraph / table 至少命中一种，
并且不能出现越界（如 page > 文档页数）。
"""

from __future__ import annotations

from typing import List, Optional

from ..models.document import SourceDocument
from ..models.evidence import EvidenceLink

__all__ = [
    "has_locator",
    "describe_locator",
    "validate_locator",
    "locator_coverage",
]


def has_locator(link: EvidenceLink) -> bool:
    return link.has_locator


def describe_locator(link: EvidenceLink) -> str:
    bits: List[str] = []
    if link.page is not None:
        bits.append(f"p.{link.page}")
    if link.section:
        bits.append(f"§{link.section}")
    if link.paragraph:
        bits.append(f"¶{link.paragraph}")
    if link.table:
        bits.append(f"表:{link.table}")
    return " / ".join(bits) if bits else "(无定位)"


def locator_coverage(links: List[EvidenceLink]) -> float:
    if not links:
        return 0.0
    return sum(1 for l in links if l.has_locator) / len(links)


def validate_locator(link: EvidenceLink, doc: Optional[SourceDocument] = None) -> List[str]:
    """返回定位层面的问题列表（空列表 = 无问题）。"""
    problems: List[str] = []

    if link.page is not None:
        try:
            page = int(link.page)
        except (TypeError, ValueError):
            problems.append(f"page 非整数: {link.page!r}")
            page = None
        if page is not None:
            if page <= 0:
                problems.append(f"page 必须为正整数: {page}")
            if doc is not None and doc.page_count and page > int(doc.page_count):
                problems.append(f"page 越界: p.{page} > 文档页数 {doc.page_count}")

    if doc is not None and link.section and doc.sections:
        known = {str(s).strip() for s in doc.sections}
        if str(link.section).strip() not in known:
            problems.append(
                f"section 不在文档登记的章节内: {link.section!r}；已登记 {sorted(known)}"
            )

    if not link.has_locator:
        problems.append("page / section / paragraph / table 全部为空，定位缺失")

    return problems
