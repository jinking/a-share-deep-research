# -*- coding: utf-8 -*-
"""证据层：落盘、指纹、定位、独立性。"""

from __future__ import annotations

from .excerpt import (
    TEXTLAYER_SUFFIX,
    compare_excerpt_verification,
    compare_link_verification,
    compute_excerpt_verification,
    resolve_verification_source,
    stamp_excerpt_verification,
    verify_excerpt_against_text,
)
from .hasher import (
    document_fingerprint,
    make_document_id,
    sha256_bytes,
    sha256_file,
    sha256_text,
    verify_file_hash,
)
from .independence import (
    describe_groups,
    group_documents,
    independent_source_count,
    independence_key,
    shared_upstream_hint,
)
from .locator import describe_locator, has_locator, locator_coverage, validate_locator
from .store import (
    CANDIDATES_FILE,
    CLAIMS_FILE,
    DOCUMENTS_FILE,
    LINKS_FILE,
    RAW_DIR,
    EvidenceStore,
    EvidenceStoreError,
)
from .verbatim import (
    TEXT_SUFFIXES,
    VerbatimError,
    excerpt_in_file,
    extract_verbatim,
    normalize_for_match,
    text_supports_excerpt,
)

__all__ = [
    "EvidenceStore",
    "EvidenceStoreError",
    "CANDIDATES_FILE",
    "DOCUMENTS_FILE",
    "CLAIMS_FILE",
    "LINKS_FILE",
    "RAW_DIR",
    "TEXT_SUFFIXES",
    "VerbatimError",
    "text_supports_excerpt",
    "excerpt_in_file",
    "normalize_for_match",
    "extract_verbatim",
    "TEXTLAYER_SUFFIX",
    "resolve_verification_source",
    "verify_excerpt_against_text",
    "compute_excerpt_verification",
    "stamp_excerpt_verification",
    "compare_link_verification",
    "compare_excerpt_verification",
    "sha256_bytes",
    "sha256_text",
    "sha256_file",
    "make_document_id",
    "document_fingerprint",
    "verify_file_hash",
    "has_locator",
    "describe_locator",
    "validate_locator",
    "locator_coverage",
    "independence_key",
    "group_documents",
    "independent_source_count",
    "describe_groups",
    "shared_upstream_hint",
]
