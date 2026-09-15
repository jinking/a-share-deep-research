# -*- coding: utf-8 -*-
"""Evidence 层数据模型。"""

from __future__ import annotations

from .base import EvidenceModelError, as_jsonable, clean_str, iso_now, parse_date, parse_datetime
from .candidate import (
    CANDIDATE_ID_PREFIX,
    CANDIDATE_STATUSES,
    TERMINAL_CANDIDATE_STATUSES,
    EvidenceCandidate,
    is_candidate_id,
    make_candidate_id,
)
from .claim import (
    CLAIM_CATEGORIES,
    CLAIM_LEVELS,
    CLAIM_STATUSES,
    DIRECT_REQUIRED_LEVELS,
    MATERIALITIES,
    PRIMARY_REQUIRED_LEVELS,
    STRICT_MATERIALITIES,
    Claim,
    is_semantic_claim_id,
)
from .document import PRIMARY_SOURCE_TYPES, SOURCE_TYPES, SourceDocument
from .evidence import LOCATOR_FIELDS, SUPPORT_TYPES, EvidenceLink
from .research_state import ResearchState

__all__ = [
    "EvidenceModelError",
    "as_jsonable",
    "clean_str",
    "iso_now",
    "parse_date",
    "parse_datetime",
    "Claim",
    "CLAIM_CATEGORIES",
    "CLAIM_LEVELS",
    "CLAIM_STATUSES",
    "MATERIALITIES",
    "PRIMARY_REQUIRED_LEVELS",
    "DIRECT_REQUIRED_LEVELS",
    "STRICT_MATERIALITIES",
    "is_semantic_claim_id",
    "SourceDocument",
    "SOURCE_TYPES",
    "PRIMARY_SOURCE_TYPES",
    "EvidenceLink",
    "SUPPORT_TYPES",
    "LOCATOR_FIELDS",
    "ResearchState",
    "EvidenceCandidate",
    "CANDIDATE_ID_PREFIX",
    "CANDIDATE_STATUSES",
    "TERMINAL_CANDIDATE_STATUSES",
    "is_candidate_id",
    "make_candidate_id",
]
