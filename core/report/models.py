#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""报告侧 Claim 锚点模型（v3.0.2 §5）。

v3.0/v3.0.1 解决的是「证据库可信」：Document → Claim → EvidenceLink 三层都能被机器校验。
但最终交付给人的报告仍然可以保留被人改过的旧结论——因为报告与 Claim Ledger 之间
没有任何可校验的连接（v3.0.2 §2 的真实案例：「送样阶段」在 Ledger 里已被纠正为
「在研」，HTML 却照旧）。

`ReportClaimRef` 就是那条连接：报告里的一段结论声明「我复述的是哪个 Claim、
按什么等级、什么状态」。

语义核心是**锚定即声明**：

    一旦某段结论绑定了 claim_id，它就不再只是「一段字」，而是对 Claim 的一次复述。
    复述必须与 Ledger 一致 —— 包括 level 与 status。

未显式声明 level / status 的锚点，按 DEFAULT_ASSERTED_* 解读（即以事实、已确认的口吻
陈述）。这不是苛求，而是唯一能拦住旧报告的写法：旧报告的锚点不会有 level/status
属性，如果「缺省 = 不检查」，那「Claim 被降级后旧报告必须 FAIL」就永远触发不了。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

__all__ = [
    "DEFAULT_ASSERTED_LEVEL",
    "DEFAULT_ASSERTED_STATUS",
    "ReportClaimRef",
]

# 「锚定即声明」的缺省读法：把 Claim 当成事实、当成已确认来陈述
DEFAULT_ASSERTED_LEVEL = "fact"
DEFAULT_ASSERTED_STATUS = "supported"


@dataclass
class ReportClaimRef:
    """报告里的一处 Claim 锚点。"""

    claim_id: str
    text: str = ""
    declared_level: Optional[str] = None
    declared_status: Optional[str] = None
    # 人类可读定位：HTML 为 "span#<n>"，Markdown 为 "line <n>"
    location: str = ""
    syntax: str = "html"  # html | markdown

    @property
    def effective_level(self) -> str:
        """报告实际声明的证据等级（未声明时按缺省读法）。"""
        return self.declared_level or DEFAULT_ASSERTED_LEVEL

    @property
    def effective_status(self) -> str:
        """报告实际声明的证据状态（未声明时按缺省读法）。"""
        return self.declared_status or DEFAULT_ASSERTED_STATUS

    def describe(self) -> str:
        bits = [self.claim_id or "(缺 claim_id)", f"@{self.location}"]
        if self.declared_level:
            bits.append(f"level={self.declared_level}")
        if self.declared_status:
            bits.append(f"status={self.declared_status}")
        return " ".join(bits)
