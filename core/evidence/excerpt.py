#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""摘录验证状态（v3.0.2 §9）：PDF 跳过子串校验 ≠ 摘录已验证。

背景：早期实现里，遇到 PDF 就「跳过子串校验」，于是「跳过」被当成了「通过」。
一条 `evidence_text` 可能只是人工抄录、甚至抄错，却在报告里充当可复核摘录。

本模块把这件事变成可重复执行的机器结论：

    摘录 + 原文文本 → 归一化 → 子串命中 → verified / unverified

原文文本按优先级解析（`resolve_verification_source`）：

    *.pdf  → 同名 *.textlayer.txt（官方文本层）   method=text_layer
    纯文本  → 文件本身                              method=direct_text

拿不到可比对文本（只有 URL、PDF 无文本层、文件缺失）→ 一律 `unverified`，
**绝不**因为「无法校验」而放行。比对实现只有一处：`verbatim.excerpt_in_file`。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

from ..models.document import SourceDocument
from ..models.evidence import EvidenceLink
from .verbatim import TEXT_SUFFIXES, excerpt_in_file, normalize_for_match

__all__ = [
    "TEXTLAYER_SUFFIX",
    "normalize_for_match",
    "resolve_verification_source",
    "verify_excerpt_against_text",
    "compute_excerpt_verification",
    "stamp_excerpt_verification",
]

TEXTLAYER_SUFFIX = ".textlayer.txt"


def resolve_verification_source(
    document: Optional[SourceDocument], base_dir: Optional[Path] = None
) -> Tuple[Optional[Path], Optional[str]]:
    """解析「用哪份文本比对摘录」，返回 (路径, 手段)；拿不到时返回 (None, None)。"""
    if document is None or not document.local_path:
        return None, None

    path = Path(document.local_path)
    if not path.is_absolute() and base_dir is not None:
        path = Path(base_dir) / path

    if path.suffix.lower() == ".pdf":
        textlayer = path.with_name(path.name[: -len(".pdf")] + TEXTLAYER_SUFFIX)
        if textlayer.is_file():
            return textlayer, "text_layer"
        return None, None  # PDF 无文本层：不可比对

    if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES:
        return path, "direct_text"

    return None, None


def verify_excerpt_against_text(evidence_text: Optional[str], source_text: Optional[str]) -> bool:
    """摘录（归一化后）是否为原文（归一化后）的子串。"""
    needle = normalize_for_match(evidence_text)
    if not needle:
        return False
    return needle in normalize_for_match(source_text)


def compute_excerpt_verification(
    link: EvidenceLink,
    document: Optional[SourceDocument],
    *,
    base_dir: Optional[Path] = None,
    relative_to: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    """计算一条链接的摘录验证状态。

    没有 `evidence_text` 时返回 None（无可验证对象，本模块不做任何声明）。
    """
    if not (link.evidence_text or "").strip():
        return None

    path, method = resolve_verification_source(document, base_dir)
    if path is None:
        return {"status": "unverified", "method": None, "source": None}

    ok, _why = excerpt_in_file(link.evidence_text, path)
    return {
        "status": "verified" if ok else "unverified",
        "method": method,
        "source": _display_path(path, relative_to),
    }


def _display_path(path: Path, relative_to: Optional[Path]) -> str:
    if relative_to is not None:
        try:
            return str(path.resolve().relative_to(Path(relative_to).resolve()))
        except ValueError:
            pass
    return str(path)


def stamp_excerpt_verification(
    store, base_dir: Optional[Path] = None, links: Optional[Iterable[EvidenceLink]] = None
) -> Dict[str, int]:
    """把 store 中每条带摘录的链接重新计算并写入验证状态。

    这是**唯一**写入 `excerpt_verification_*` 的通道：让状态来自真实的原文比对，
    而不是来自人手填写的「已验证」。返回 {"verified": n, "unverified": n, "skipped": n}。

    `links` 可指定只处理其中一部分（用于保留调用方已显式声明的结果）。
    """
    stats = {"verified": 0, "unverified": 0, "skipped": 0}
    root = Path(base_dir) if base_dir is not None else store.root
    for link in store.links if links is None else links:
        document = store.documents.get(link.document_id)
        result = compute_excerpt_verification(link, document, base_dir=root, relative_to=root)
        if result is None:
            stats["skipped"] += 1
            continue
        link.excerpt_verification_status = result["status"]
        link.excerpt_verification_method = result["method"]
        link.excerpt_verification_source = result["source"]
        stats[result["status"]] += 1
    return stats
