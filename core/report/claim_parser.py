#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""报告 Claim 锚点解析器（v3.0.2 §5 / §6）。

两种书写形式，都只做**显式 metadata** 提取——不判断语气、不做语义理解
（§6「第一版禁止使用 LLM 判断语气强弱，只做显式 metadata 一致性」）。

HTML：

    <span data-claim-id="E007"
          data-claim-level="management_statement"
          data-claim-status="supported">
      224G 产品仍处于在研阶段
    </span>

Markdown：

    <!-- claim:E007 level=management_statement status=supported -->
    224G 产品仍处于在研阶段。

解析器**只负责把锚点找出来**，不做任何合法性裁决：
缺 claim_id、level 写成非法值等情况照原样返回，由
`core.validation.report_claim_validator` 统一报错误码
（这样「解析」与「裁决」的边界清晰，错误码只有一个出口）。
"""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .models import ReportClaimRef

__all__ = ["parse_report_claims", "parse_html_claims", "parse_markdown_claims", "visible_text"]

# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

_TAG_RE = re.compile(r"<\s*([A-Za-z][A-Za-z0-9:_-]*)([^>]*?)(/?)>", re.S)
_ATTR_RE = re.compile(
    r"""([A-Za-z_:][-A-Za-z0-9_:.]*)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+))""",
    re.S,
)
_VOID_TAGS = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
)
_BLOCK_TAGS = (
    "h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "tr", "td", "th", "div", "section", "br", "table",
)
_BLOCK_TAG_RE = re.compile(r"</?(?:%s)\b[^>]*>" % "|".join(_BLOCK_TAGS), re.I | re.S)
_ANY_TAG_RE = re.compile(r"<[^>]+>", re.S)


def visible_text(raw: str) -> str:
    """把一段 HTML 片段转成可见文本（去掉标签、压缩空白、还原实体）。

    块级标签换成空格、行内标签**直接删除**——否则 `<b>` 会把「亿元，同比」劈成
    「亿元， 同比」，凭空多出一个源文里没有的空格。
    """
    text = re.sub(r"<(?:script|style)\b[^>]*>.*?</(?:script|style)>", " ", raw, flags=re.I | re.S)
    text = _BLOCK_TAG_RE.sub(" ", text)
    text = _ANY_TAG_RE.sub("", text)
    text = html.unescape(text)
    text = text.replace("\u00a0", " ")
    return re.sub(r"\s+", " ", text).strip()


def _parse_attrs(attr_text: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for m in _ATTR_RE.finditer(attr_text or ""):
        name = m.group(1).lower()
        value = m.group(2) if m.group(2) is not None else (m.group(3) if m.group(3) is not None else m.group(4))
        out[name] = html.unescape(value or "")
    return out


def _element_inner(raw: str, tag: str, start: int, self_closing: bool) -> Tuple[str, int]:
    """返回 (元素内部 HTML, 元素结束后的下标)。

    用「同名标签配对计数」扫描，能正确处理嵌套同名标签（如 span 套 span）。
    找不到配对闭合标签时，退回文件末尾——解析器不因此报错，
    因为「结构是否合法」不是它的职责。
    """
    if self_closing or tag.lower() in _VOID_TAGS:
        return "", start
    pair_re = re.compile(rf"<\s*(/?){re.escape(tag)}\b[^>]*?(/?)>", re.I | re.S)
    depth = 1
    pos = start
    while True:
        m = pair_re.search(raw, pos)
        if not m:
            return raw[start:], len(raw)
        if m.group(1) == "/":
            depth -= 1
            if depth == 0:
                return raw[start:m.start()], m.end()
        elif m.group(2) == "/":
            pass  # 自闭合的同名标签，不增加深度
        else:
            depth += 1
        pos = m.end()


def parse_html_claims(raw: str) -> List[ReportClaimRef]:
    """提取所有带 `data-claim-*` 属性的 HTML 元素。

    判据是「带任一 `data-claim-*` 属性」而不是「带 data-claim-id」——只写了
    `data-claim-level` 却漏了 id 的元素显然是想做锚点，它必须被解析出来，
    由 validator 报 REPORT_CLAIM_UNKNOWN，而不是被静默忽略。
    """
    refs: List[ReportClaimRef] = []
    index = 0
    for m in _TAG_RE.finditer(raw or ""):
        attrs = _parse_attrs(m.group(2))
        if not any(key.startswith("data-claim-") for key in attrs):
            continue
        index += 1
        inner, _ = _element_inner(raw, m.group(1), m.end(), bool(m.group(3)))
        refs.append(
            ReportClaimRef(
                claim_id=(attrs.get("data-claim-id") or "").strip(),
                text=visible_text(inner),
                declared_level=(attrs.get("data-claim-level") or "").strip() or None,
                declared_status=(attrs.get("data-claim-status") or "").strip() or None,
                location=f"<{m.group(1).lower()}#{index}>",
                syntax="html",
            )
        )
    return refs


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------

_MD_CLAIM_RE = re.compile(r"<!--\s*claim\s*:([^>]*?)-->", re.I | re.S)
_MD_KV_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([^\s=]+)")


def parse_markdown_claims(raw: str) -> List[ReportClaimRef]:
    """提取 `<!-- claim:ID level=... status=... -->` 形式的锚点。

    关联文本的取法（确定性，无需语义判断）：

    1. 注释同行、注释**之前**的可见内容；
    2. 注释同行、注释**之后**的可见内容；
    3. 若注释独占一行，则取**下一个非空行**。

    1 与 2 同时存在时按「前 + 后」拼接。
    """
    refs: List[ReportClaimRef] = []
    lines = (raw or "").splitlines()
    # 每行的起始下标，便于把注释映射回行与行内偏移
    starts: List[int] = []
    cursor = 0
    for line in lines:
        starts.append(cursor)
        cursor += len(line) + 1

    def line_of(pos: int) -> int:
        lo, hi = 0, len(starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if starts[mid] <= pos:
                lo = mid
            else:
                hi = mid - 1
        return lo

    for m in _MD_CLAIM_RE.finditer(raw or ""):
        body = m.group(1).strip()
        if not body:
            continue
        parts = body.split(None, 1)
        claim_id = parts[0].strip()
        extras = dict(_MD_KV_RE.findall(parts[1])) if len(parts) > 1 else {}

        idx = line_of(m.start())
        line = lines[idx]
        offset = m.start() - starts[idx]
        before = line[:offset].strip()
        after = line[m.end() - starts[idx]:].strip()

        if before or after:
            text = " ".join(x for x in (before, after) if x)
        else:
            text = ""
            for nxt in lines[idx + 1:]:
                if nxt.strip():
                    text = nxt.strip()
                    break

        refs.append(
            ReportClaimRef(
                claim_id=claim_id,
                text=text,
                declared_level=(extras.get("level") or "").strip() or None,
                declared_status=(extras.get("status") or "").strip() or None,
                location=f"line {idx + 1}",
                syntax="markdown",
            )
        )
    return refs


# ---------------------------------------------------------------------------
# 统一入口
# ---------------------------------------------------------------------------


def parse_report_claims(raw: str, *, path: Optional[Path] = None) -> List[ReportClaimRef]:
    """解析报告中的全部 Claim 锚点（HTML + Markdown 两种语法一起扫）。

    两种语法互斥地出现在同一种文件里，合并扫描不会互相误伤：
    HTML 报告不会有 `<!-- claim:` 这类注释习惯，Markdown 报告不会有 `data-claim-id`。
    合并而不是按后缀二选一，是为了让 `.html` 里也能写注释锚点、`.md` 里也能贴 HTML 片段。
    """
    return parse_html_claims(raw) + parse_markdown_claims(raw)
