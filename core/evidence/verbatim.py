#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""原文摘录的真实性校验与「确定性抽取」（v3.0 §6 硬规则 2、v3.0.1 §6）。

这是整条证据链上唯一一处「人工输入会直接变成证据」的接口，所以必须只有一个实现。
两件事：

1. `text_supports_excerpt` —— 校验：给一段人工写的摘录，判断它是不是原文的真实子串。
   这是**防脑补硬闸**：看着像不算数，字符级命中才算数。
2. `extract_verbatim` —— 抽取：给一个锚点，让机器从原文里**剪**出片段，
   人手一个字都不碰。锚点找不到就报错，绝不「就近取一段差不多的」。

从「人写摘录」改成「人给锚点、机器剪摘录」是这条纪律的关键一步：
前者需要信任，后者只需要复核。
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import List, Optional, Tuple

__all__ = [
    "TEXT_SUFFIXES",
    "VerbatimError",
    "normalize_for_match",
    "excerpt_in_file",
    "text_supports_excerpt",
    "extract_verbatim",
]

# 可以参与「摘录必须来自原文」校验的文本类后缀
TEXT_SUFFIXES = (".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".jsonl", ".html", ".htm")


class VerbatimError(Exception):
    """无法从原文中确定性地取出摘录。"""


_WS_RE = re.compile(r"\s+")


def normalize_for_match(text: Optional[str]) -> str:
    """比对用归一化：NFKC 折叠全角/半角，再去掉所有空白。

    摘录与原文的换行位置几乎不可能一致（文本层按排版断行，人工摘录按语义断行），
    所以比对必须忽略空白；而 NFKC 让「１．」与「1.」这类差异不至于造成假阴性。
    """
    if not text:
        return ""
    return _WS_RE.sub("", unicodedata.normalize("NFKC", str(text)))


def excerpt_in_file(excerpt: str, path) -> Tuple[bool, str]:
    """**严格**校验摘录是否为文本原件的真实子串（不做任何「跳过」）。

    与 `text_supports_excerpt` 的唯一区别就在这里：非文本后缀**不**被视为通过，
    而是明确的失败 —— 「无法校验」不能等价于「校验通过」（v3.0.2 §9）。
    """
    p = Path(path)
    if not p.is_file():
        return False, f"原件不存在: {p}"
    if p.suffix.lower() not in TEXT_SUFFIXES:
        return False, f"非文本原件（{p.suffix.lower() or '无后缀'}），无法做子串校验"
    if not (excerpt or "").strip():
        return False, "evidence_text 为空"
    try:
        content = p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return False, "文件非 UTF-8，无法做子串校验"

    if normalize_for_match(excerpt) in normalize_for_match(content):
        return True, "摘录命中原文"
    return False, "evidence_text 不是原文子串 —— 疑似臆造摘录，已拒绝"


def text_supports_excerpt(excerpt: str, path) -> Tuple[bool, str]:
    """校验 excerpt 是否为文本文件真实子串。

    返回 (是否通过, 说明)。无法判定时（二进制文件）返回 (True, 说明)。

    注意这里的「跳过」语义是为 attach 流程保留的：PDF 原件交给
    `excerpt_in_file` + 文本层去严格比对，本函数不改变既有行为。
    """
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix not in TEXT_SUFFIXES:
        return True, f"非文本后缀（{suffix or '无'}），跳过子串校验"
    if not excerpt:
        return False, "evidence_text 为空"
    try:
        content = p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return True, "文件非 UTF-8，跳过子串校验"

    if excerpt in content:
        return True, "摘录命中原文"

    # 宽容处理：换行/连续空白差异（表格逐行摘录时常见）
    if normalize_for_match(excerpt) in normalize_for_match(content):
        return True, "摘录命中原文（忽略空白差异）"
    return False, "evidence_text 不是原文子串 —— 疑似臆造摘录，已拒绝"


def extract_verbatim(
    path,
    *,
    anchor: Optional[str] = None,
    lines: Optional[Tuple[int, int]] = None,
    tail: int = 0,
) -> str:
    """从文本原件中剪出一段**保证是原文子串**的摘录。

    二选一定位方式：

    - ``anchor``：摘录的起始字面量；``tail`` 表示在锚点之后再多吃几个字符。
    - ``lines``：1-based 闭区间的行号 (start, end)。

    无论走哪条路，结果都会再过一遍 `text_supports_excerpt`：
    抽取和校验用了两套独立逻辑，任何不一致都会当场暴露，而不是悄悄写进证据。
    """
    p = Path(path)
    if not p.is_file():
        raise VerbatimError(f"原件不存在: {p}")
    suffix = p.suffix.lower()
    if suffix not in TEXT_SUFFIXES:
        raise VerbatimError(f"无法从非文本原件抽取摘录（{suffix or '无后缀'}）")
    try:
        content = p.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise VerbatimError(f"文件非 UTF-8，无法确定性抽取: {exc}") from exc

    if anchor:
        idx = content.find(anchor)
        if idx < 0:
            raise VerbatimError(f"锚点在原文中找不到（{anchor[:40]!r}…）—— 拒绝「取一段差不多的」")
        end = idx + len(anchor) + max(0, int(tail or 0))
        excerpt = content[idx:end]
    elif lines:
        start, stop = int(lines[0]), int(lines[1])
        if start < 1 or stop < start:
            raise VerbatimError(f"行号区间非法: {lines}")
        rows: List[str] = content.splitlines()
        if stop > len(rows):
            raise VerbatimError(f"行号越界: {stop} > 文件共 {len(rows)} 行")
        excerpt = "\n".join(rows[start - 1 : stop])
    else:
        raise VerbatimError("必须提供 anchor 或 lines 之一")

    excerpt = excerpt.strip()
    if not excerpt:
        raise VerbatimError("抽取结果为空")

    ok, why = text_supports_excerpt(excerpt, p)
    if not ok:
        raise VerbatimError(f"抽取结果未通过子串复核：{why}")
    return excerpt
