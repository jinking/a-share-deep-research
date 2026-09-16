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
    CLAIM_SCOPES,
    CLAIM_STATUSES,
    DIRECT_REQUIRED_LEVELS,
    MATERIALITIES,
    PRIMARY_REQUIRED_LEVELS,
    STRICT_MATERIALITIES,
    Claim,
    is_semantic_claim_id,
)
from .document import PRIMARY_SOURCE_TYPES, SOURCE_TYPES, SourceDocument
from .evidence import (
    EXCERPT_VERIFICATION_METHODS,
    EXCERPT_VERIFICATION_STATUSES,
    LOCATOR_FIELDS,
    SUPPORT_TYPES,
    EvidenceLink,
)
from .provenance import (
    DATA_VENDOR_PROVIDERS,
    VENDOR_SOURCE_TYPES,
    default_source_type_for,
    is_data_vendor_provider,
    is_vendor_source_type_allowed,
    normalize_provider,
)
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
    "CLAIM_SCOPES",
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
    "EXCERPT_VERIFICATION_STATUSES",
    "EXCERPT_VERIFICATION_METHODS",
    "DATA_VENDOR_PROVIDERS",
    "VENDOR_SOURCE_TYPES",
    "normalize_provider",
    "is_data_vendor_provider",
    "is_vendor_source_type_allowed",
    "default_source_type_for",
    "ResearchState",
    "EvidenceCandidate",
    "CANDIDATE_ID_PREFIX",
    "CANDIDATE_STATUSES",
    "TERMINAL_CANDIDATE_STATUSES",
    "is_candidate_id",
    "make_candidate_id",
]
