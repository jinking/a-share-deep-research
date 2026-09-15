# -*- coding: utf-8 -*-
"""验收问题的中性载体。

Core 层只产出 Issue，不关心调用方如何呈现；
scripts/validate_report.py 会把它转换成自身的 Finding 后写入验收报告。
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["Issue"]


@dataclass(frozen=True)
class Issue:
    severity: str  # P0 / P1 / P2 / INFO
    code: str
    message: str
    detail: str = ""

    def as_tuple(self):
        return (self.severity, self.code, self.message, self.detail)
