# -*- coding: utf-8 -*-
"""证据层：落盘、指纹、定位、独立性。"""

from __future__ import annotations

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
    CLAIMS_FILE,
    DOCUMENTS_FILE,
    LINKS_FILE,
    RAW_DIR,
    EvidenceStore,
    EvidenceStoreError,
)

__all__ = [
    "EvidenceStore",
    "EvidenceStoreError",
    "DOCUMENTS_FILE",
    "CLAIMS_FILE",
    "LINKS_FILE",
    "RAW_DIR",
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
