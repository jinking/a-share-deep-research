# -*- coding: utf-8 -*-
"""报告侧解析（v3.0.2）：把最终交付报告中的结论锚点提取成可校验对象。"""

from __future__ import annotations

from .claim_parser import parse_html_claims, parse_markdown_claims, parse_report_claims, visible_text
from .models import DEFAULT_ASSERTED_LEVEL, DEFAULT_ASSERTED_STATUS, ReportClaimRef

__all__ = [
    "DEFAULT_ASSERTED_LEVEL",
    "DEFAULT_ASSERTED_STATUS",
    "ReportClaimRef",
    "parse_report_claims",
    "parse_html_claims",
    "parse_markdown_claims",
    "visible_text",
]
