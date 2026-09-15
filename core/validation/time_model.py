#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""研究时间模型（v3.0.1 §4）。

历史上只有一个 `research_date`，它同时隐含四种含义：数据截止日、研究基准日、
行情截止日、报告生成日。语义模糊到无法回答「这条证据是否超出了研究时点」——
这正是 Golden Sample 里 `research_date=2026-09-14` 与机构预期
`published_at=2026-09-15` 相冲突的根因。

v3.0.1 把它拆成三个明确时点：

    as_of              研究信息截止时点。正式结论可用的最晚证据时间。
                       规则：Evidence 的 published_at <= as_of
    market_data_as_of  行情数据截止时点。用于当前价 / 市值 / 技术面 / K 线
    generated_at       报告生成时间。必须与报告内时间戳（title / h1 small /
                       footer / 顶部注释）及文件名一致

Evidence 自身继续保留 `published_at` / `retrieved_at`，语义不变。

兼容策略（§4「向后兼容」）：
    - v2 manifest 继续读 `research_date`，行为零变化；
    - 旧 v3（只有 research_date）可兼容读取，报一条 P2 `TIME_MODEL_LEGACY`，
      不阻断迁移；
    - 新 v3 走 as_of，超出时点报 P1 `SOURCE_DATE_AFTER_AS_OF`。

本模块只输出结论，不修改任何产物（§19.2）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Callable, Dict, Optional

from ..models.base import clean_str, parse_date, parse_datetime
from .codes import severity_of

__all__ = [
    "TIME_FIELDS",
    "TimeModel",
    "build_time_model",
    "validate_time_model",
    "TIME_FIELD_LABELS",
]

# 新时间模型的三个字段（顺序即文档中的顺序）
TIME_FIELDS = ("as_of", "market_data_as_of", "generated_at")

TIME_FIELD_LABELS = {
    "as_of": "研究信息截止时点",
    "market_data_as_of": "行情数据截止时点",
    "generated_at": "报告生成时间",
}

Emit = Callable[..., None]


@dataclass
class TimeModel:
    as_of: Optional[datetime] = None
    market_data_as_of: Optional[datetime] = None
    generated_at: Optional[datetime] = None
    # 旧模型的字段；确定旧时间模型是否成立时要用到
    research_date: Optional[date] = None
    # 原始 meta（用于报错时回显真实文本，而不是解析后的对象）
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_new_model(self) -> bool:
        """是否已声明 as_of（新模型的锚点）。"""
        return self.as_of is not None

    @property
    def is_legacy(self) -> bool:
        """旧时间模型：有 research_date 但没有 as_of。"""
        return self.as_of is None and self.research_date is not None

    @property
    def has_any(self) -> bool:
        return any(
            (self.as_of, self.market_data_as_of, self.generated_at, self.research_date)
        )

    @property
    def info_cutoff(self) -> Optional[date]:
        """判定「证据是否超出研究时点」用的截止日。

        新模型用 `as_of`；旧模型退化为 `research_date`（并会另报 TIME_MODEL_LEGACY）。
        """
        if self.as_of is not None:
            return self.as_of.date()
        return self.research_date

    def describe(self) -> str:
        parts = []
        for key in TIME_FIELDS:
            value = self.raw.get(key)
            parts.append(f"{key}={value if value is not None else '(缺)'}")
        parts.append(f"research_date={self.raw.get('research_date') or '(缺)'}")
        return "；".join(parts)


def build_time_model(meta: Optional[Dict[str, Any]]) -> TimeModel:
    """从 manifest 的 `meta`（或等价字典）构建时间模型。

    解析失败（字段存在但不是合法日期）时该字段保持 None——由调用方决定如何报告，
    本函数不做静默兜底，也不臆造缺省值。
    """
    meta = meta or {}
    if not isinstance(meta, dict):
        meta = {}
    return TimeModel(
        as_of=parse_datetime(meta.get("as_of")),
        market_data_as_of=parse_datetime(meta.get("market_data_as_of")),
        generated_at=parse_datetime(meta.get("generated_at")),
        research_date=parse_date(meta.get("research_date")),
        raw={k: meta.get(k) for k in (*TIME_FIELDS, "research_date")},
    )


def validate_time_model(model: TimeModel, *, emit: Emit) -> None:
    """时间模型自身的校验：只报时间语义问题，不涉及证据内容。

    - 旧时间模型（只有 research_date）→ P2 `TIME_MODEL_LEGACY`
    - market_data_as_of 晚于 generated_at → P1 `MARKET_DATA_AFTER_GENERATED_AT`

    注意：as_of 缺失时**不**在这里报结构错误——「三字段一个都没有」属于
    manifest 结构问题，由 manifest_validator 报 MANIFEST_V3_STRUCTURE。
    """
    if model.is_legacy:
        emit(
            severity_of("TIME_MODEL_LEGACY"),
            "TIME_MODEL_LEGACY",
            "仍在使用旧时间模型（只有 research_date）",
            f"{model.describe()}；建议改用 as_of / market_data_as_of / generated_at，"
            "以区分信息截止时点与行情截止时点",
        )

    if (
        model.market_data_as_of is not None
        and model.generated_at is not None
        and model.market_data_as_of > model.generated_at
    ):
        emit(
            severity_of("MARKET_DATA_AFTER_GENERATED_AT"),
            "MARKET_DATA_AFTER_GENERATED_AT",
            "行情数据时点晚于报告生成时点",
            f"market_data_as_of={model.raw.get('market_data_as_of')}；"
            f"generated_at={model.raw.get('generated_at')}；"
            "行情不可能来自报告生成之后",
        )


def has_malformed_time_field(meta: Optional[Dict[str, Any]]) -> Optional[str]:
    """返回「声明了但解析不出」的字段名，用于报结构错误（没有则返回 None）。"""
    meta = meta or {}
    if not isinstance(meta, dict):
        return None
    for key in TIME_FIELDS:
        raw = clean_str(meta.get(key))
        if raw and parse_datetime(raw) is None:
            return key
    return None
