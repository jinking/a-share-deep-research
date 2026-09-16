#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Claim 指纹（v3.0.3 §4）：报告引用的是不是「这一版 Claim」。

v3.0.2 的报告锚点只校验 `claim_id / level / status` 三件事，于是还留着一条缝：

    claim_id 正确
    level    正确
    status   正确
    但 Claim 正文已经被改写过了

例如 Ledger 里的 E007 从「处于在研阶段」被改成「已进入量产阶段」，level 仍是
`management_statement`、status 仍是 `supported` —— 三者全对，旧报告却仍然在
陈述一个**已经被推翻的结论**。这不是措辞漂移，这是结论漂移。

指纹把「哪一版」这件事变成可机器比对的字符串：

    claim_fingerprint = sha256(canonical_json({
        claim_id, claim(归一化), level, status
    }))[:16]

刻意**不做**人工递增的 revision number（§4）：人会忘记递增，而哈希不会。

同时也刻意**不做** `hash(报告可见文本) == hash(claim.claim)` —— 报告允许对
Claim 做人类可读的改写（「营业收入 28.63 亿元」写成「营收 28.63 亿」是正常的），
第一版只保证「报告锚点对应当前 Claim 版本」，不保证逐字复述。

归一化只做空白与全角/半角（NFKC）层面的收敛，**不动标点、不动词序**：
指纹必须对「同一个 Claim 的不同排版」稳定，但要对「改过的句子」敏感——
这两件事的边界就是「排版 vs 内容」，多归一化一步越界，少一步则误报。
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from typing import Any, Dict, Mapping, Protocol

__all__ = [
    "CLAIM_FINGERPRINT_LENGTH",
    "FINGERPRINT_HEX_RE",
    "claim_fingerprint_payload",
    "canonical_json",
    "claim_fingerprint",
    "claim_fingerprint_of",
    "is_valid_fingerprint",
    "normalize_claim_text",
]

# 16 位十六进制：撞车概率对本场景可忽略，且人眼可读、日志里不占地方
CLAIM_FINGERPRINT_LENGTH = 16

FINGERPRINT_HEX_RE = re.compile(r"^[0-9a-f]{%d}$" % CLAIM_FINGERPRINT_LENGTH)

_WS_RE = re.compile(r"\s+")


class _HasClaimFields(Protocol):
    """指纹只需要四个字段，不关心传入的是不是 Claim 实例。

    这样 fingerprint 模块可以**不 import claim 模块**（claim 要 import 它），
    避免环形依赖 —— 也让 fingerprint 能被任意轻量对象复用。
    """

    claim_id: str
    claim: str
    level: str
    status: str


def normalize_claim_text(text: Any) -> str:
    """Claim 正文的归一化：NFKC + 全空白折叠 + 去首尾。

    只收敛「排版差异」：全角空格、连续空格、换行、制表符、NBSP。
    **不改标点、不大小写折叠、不做同义词替换** —— 那些属于内容，改了就等于
    放过了真正的改写。
    """
    raw = "" if text is None else str(text)
    raw = unicodedata.normalize("NFKC", raw)
    raw = raw.replace("\u00a0", " ").replace("\u3000", " ")
    return _WS_RE.sub(" ", raw).strip()


def canonical_json(payload: Mapping[str, Any]) -> str:
    """确定性 JSON：键排序 + 紧凑分隔符 + 不转义非 ASCII。

    `ensure_ascii=False` 让中文以 UTF-8 原样参与哈希（编码本身是确定的），
    好处是调试时能把 payload 直接打出来看。
    """
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def claim_fingerprint_payload(
    claim_id: Any,
    claim_text: Any,
    level: Any,
    status: Any,
) -> Dict[str, str]:
    """指纹的输入载荷——单独抽出来，方便测试与文档对齐。"""
    return {
        "claim_id": str(claim_id or "").strip(),
        "claim": normalize_claim_text(claim_text),
        "level": str(level or "").strip(),
        "status": str(status or "").strip(),
    }


def claim_fingerprint_of(
    claim_id: Any,
    claim_text: Any,
    level: Any,
    status: Any,
) -> str:
    """由四个字段直接算指纹。"""
    payload = claim_fingerprint_payload(claim_id, claim_text, level, status)
    digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    return digest[:CLAIM_FINGERPRINT_LENGTH]


def claim_fingerprint(claim: _HasClaimFields) -> str:
    """算出一个 Claim 的指纹。

    注意 `category` / `materiality` **不参与**：报告锚点不声明这两者，
    把它们算进去只会让「补了个分类」这种无关变更把报告判为过期。
    """
    return claim_fingerprint_of(
        getattr(claim, "claim_id", ""),
        getattr(claim, "claim", ""),
        getattr(claim, "level", ""),
        getattr(claim, "status", ""),
    )


def is_valid_fingerprint(value: Any) -> bool:
    """形状校验：16 位小写十六进制。"""
    return bool(FINGERPRINT_HEX_RE.match(str(value or "").strip()))
