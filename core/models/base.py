# -*- coding: utf-8 -*-
"""Evidence 层数据模型的公共工具。"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone, timedelta
from typing import Any, Optional

__all__ = [
    "EvidenceModelError",
    "parse_date",
    "parse_datetime",
    "iso_now",
    "is_sha256_hex",
    "clean_str",
    "as_jsonable",
]

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SHANGHAI = timezone(timedelta(hours=8))


class EvidenceModelError(ValueError):
    """模型字段非法（结构性错误，必须 fail-fast，不做静默修补）。"""


def clean_str(value: Any) -> Optional[str]:
    """把 None / 空串统一成 None，其余去首尾空白。"""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def parse_date(value: Any) -> Optional[date]:
    """尽力把 2026-08-25 / 20260825 / 2026/08/25 解析成 date，失败返回 None。"""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("/", "-").replace(".", "-")
    m = re.match(r"^(\d{4})-?(\d{2})-?(\d{2})$", text)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def parse_datetime(value: Any) -> Optional[datetime]:
    """解析 ISO8601 时间；纯日期按当日 00:00 (+08:00) 处理。"""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=_SHANGHAI)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=_SHANGHAI)
    text = str(value).strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        d = parse_date(text)
        return datetime(d.year, d.month, d.day, tzinfo=_SHANGHAI) if d else None
    return dt if dt.tzinfo else dt.replace(tzinfo=_SHANGHAI)


def iso_now() -> str:
    """当前时间（+08:00）。"""
    return datetime.now(_SHANGHAI).replace(microsecond=0).isoformat()


def is_sha256_hex(value: Any) -> bool:
    return bool(_SHA256_RE.match(str(value or "").strip().lower()))


def as_jsonable(value: Any) -> Any:
    """递归转成可 json.dumps 的结构，并剔除 None 之外的不可序列化对象。"""
    if isinstance(value, dict):
        return {k: as_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [as_jsonable(v) for v in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value
