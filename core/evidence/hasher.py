#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""证据文件指纹（v3.0 §6、§8.1 EVIDENCE_HASH_MISMATCH）。"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional, Tuple

from ..models.base import clean_str

__all__ = [
    "sha256_bytes",
    "sha256_text",
    "sha256_file",
    "make_document_id",
    "document_fingerprint",
    "verify_file_hash",
]

_CHUNK = 1024 * 1024


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path) -> str:
    """流式计算文件 SHA256（本地证据文档可能上百 MB）。"""
    p = Path(path)
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def document_fingerprint(
    *,
    url: Optional[str] = None,
    title: Optional[str] = None,
    published_at: Optional[str] = None,
    issuer: Optional[str] = None,
) -> str:
    """用于生成稳定 document_id 的指纹串。

    优先使用 url（同一份文件的唯一入口）；无 url 时退化为
    issuer + published_at + title 的组合。
    """
    url = clean_str(url)
    if url:
        base = url
    else:
        parts = [clean_str(issuer) or "", clean_str(published_at) or "", clean_str(title) or ""]
        if not any(parts):
            raise ValueError("无法生成 document_id：url / issuer / published_at / title 全部为空")
        base = "|".join(parts)
    return base


def make_document_id(
    *,
    url: Optional[str] = None,
    title: Optional[str] = None,
    published_at: Optional[str] = None,
    issuer: Optional[str] = None,
) -> str:
    """生成 DOC_<hash前8位> 形式的稳定 ID。"""
    fp = document_fingerprint(url=url, title=title, published_at=published_at, issuer=issuer)
    return "DOC_" + sha256_text(fp)[:8]


def verify_file_hash(local_path, expected_sha256: Optional[str]) -> Tuple[bool, Optional[str]]:
    """校验本地文件 hash。

    返回 (ok, actual)：
    - 文件不存在或未登记 hash -> (False, None)，由调用方决定错误码；
    - expected 为空 -> (True, actual)（不强制，登记与否由来源规范决定）。
    """
    path = Path(local_path) if local_path else None
    if path is None or not path.exists() or not path.is_file():
        return False, None
    actual = sha256_file(path)
    if not expected_sha256:
        return True, actual
    return actual.lower() == str(expected_sha256).strip().lower(), actual
