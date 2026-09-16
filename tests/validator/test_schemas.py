# -*- coding: utf-8 -*-
"""JSON Schema 与数据模型的一致性（v3.0 §4 schemas/）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.models import Claim, EvidenceCandidate, EvidenceLink, SourceDocument

jsonschema = pytest.importorskip("jsonschema")

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"

SCHEMAS = {
    "document": ROOT / "schemas" / "document.schema.json",
    "claim": ROOT / "schemas" / "claim.schema.json",
    "evidence_link": ROOT / "schemas" / "evidence_link.schema.json",
    "candidate": ROOT / "schemas" / "evidence_candidate.schema.json",
    "manifest": ROOT / "schemas" / "research_manifest.v3.schema.json",
}


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _validator(name: str):
    schema = _load(SCHEMAS[name])
    validator_cls = jsonschema.validators.validator_for(schema)
    validator_cls.check_schema(schema)
    return validator_cls(schema)


@pytest.mark.parametrize("name,fixture", [
    ("document", "valid/document.json"),
    ("claim", "valid/claim.json"),
    ("evidence_link", "valid/evidence_link.json"),
    ("candidate", "valid/candidate.json"),
    ("manifest", "valid/manifest_v3_new_time.json"),
])
def test_valid_fixtures_match_schema(name, fixture):
    _validator(name).validate(_load(FIXTURES / fixture))


@pytest.mark.parametrize("name,fixture", [
    ("document", "invalid/document_no_source.json"),
    ("claim", "invalid/claim_bad_level.json"),
    ("evidence_link", "invalid/evidence_link_bad_support.json"),
    ("candidate", "invalid/candidate_bad_status.json"),
    ("manifest", "invalid/manifest_v3_no_refs.json"),
])
def test_invalid_fixtures_are_rejected(name, fixture):
    with pytest.raises(jsonschema.ValidationError):
        _validator(name).validate(_load(FIXTURES / fixture))


def test_all_schemas_are_themselves_valid():
    for name in SCHEMAS:
        validator_cls = jsonschema.validators.validator_for(_load(SCHEMAS[name]))
        validator_cls.check_schema(_load(SCHEMAS[name]))


def test_model_and_schema_agree_on_source_types():
    """模型里的 source_type 必须都能通过 schema 校验，避免两处枚举漂移。"""
    from core.models import SOURCE_TYPES

    schema_enum = set(_load(SCHEMAS["document"])["properties"]["source_type"]["enum"])
    assert set(SOURCE_TYPES) == schema_enum


def test_model_and_schema_agree_on_claim_levels():
    from core.models import CLAIM_LEVELS

    schema_enum = set(_load(SCHEMAS["claim"])["properties"]["level"]["enum"])
    assert set(CLAIM_LEVELS) == schema_enum


def test_model_and_schema_agree_on_support_types():
    from core.models import SUPPORT_TYPES

    schema_enum = set(_load(SCHEMAS["evidence_link"])["properties"]["support_type"]["enum"])
    assert set(SUPPORT_TYPES) == schema_enum


def test_model_and_schema_agree_on_candidate_statuses():
    from core.models import CANDIDATE_STATUSES

    schema_enum = set(_load(SCHEMAS["candidate"])["properties"]["status"]["enum"])
    assert set(CANDIDATE_STATUSES) == schema_enum


def test_candidate_schema_reuses_source_types():
    """线索与 Document 共用同一套来源类型，避免两处枚举漂移。"""
    from core.models import SOURCE_TYPES

    schema_enum = set(_load(SCHEMAS["candidate"])["properties"]["source_type"]["enum"])
    assert set(SOURCE_TYPES) == schema_enum


def test_model_from_dict_accepts_schema_valid_fixtures():
    doc = SourceDocument.from_dict(_load(FIXTURES / "valid/document.json"))
    doc.validate()
    claim = Claim.from_dict(_load(FIXTURES / "valid/claim.json"))
    claim.validate()
    link = EvidenceLink.from_dict(_load(FIXTURES / "valid/evidence_link.json"))
    link.validate()
    candidate = EvidenceCandidate.from_dict(_load(FIXTURES / "valid/candidate.json"))
    candidate.validate()


# --------------------------------------------------------------------------- #
# v3.0.2 新增字段：溯源（§8）与摘录验证状态（§9）
# --------------------------------------------------------------------------- #


def test_model_and_schema_agree_on_excerpt_verification_enums():
    from core.models import EXCERPT_VERIFICATION_METHODS, EXCERPT_VERIFICATION_STATUSES

    link = _load(SCHEMAS["evidence_link"])["properties"]
    assert set(EXCERPT_VERIFICATION_STATUSES) == set(link["excerpt_verification_status"]["enum"]) - {None}
    assert set(EXCERPT_VERIFICATION_METHODS) == set(link["excerpt_verification_method"]["enum"]) - {None}


def test_schema_accepts_provenance_and_excerpt_verification():
    doc = {
        "document_id": "DOC_vendor01",
        "source_type": "data_vendor",
        "title": "westock-data 日行情（sz002897）",
        "retrieved_at": "2026-09-15T22:51:00+08:00",
        "provider": "westock-data",
        "upstream_source_type": "exchange_filing",
        "upstream_document_id": "CNINFO_002897_2026H1",
        "local_path": "raw/kline.txt",
    }
    _validator("document").validate(doc)
    SourceDocument.from_dict(doc).validate()

    link = {
        "evidence_id": "EV_C_MKT_CLOSE_01",
        "claim_id": "C_MKT_CLOSE_20260914",
        "document_id": "DOC_vendor01",
        "support_type": "direct",
        "evidence_text": "| 2026-09-14 | 63.99 | 71.39 |",
        "excerpt_verification_status": "verified",
        "excerpt_verification_method": "direct_text",
        "excerpt_verification_source": "raw/kline.txt",
    }
    _validator("evidence_link").validate(link)
    EvidenceLink.from_dict(link).validate()


def test_schema_rejects_unknown_excerpt_status():
    bad = {
        "evidence_id": "EV_X_01",
        "claim_id": "C_X",
        "document_id": "DOC_a",
        "support_type": "direct",
        "excerpt_verification_status": "probably_fine",
    }
    with pytest.raises(jsonschema.ValidationError):
        _validator("evidence_link").validate(bad)
    with pytest.raises(Exception):
        EvidenceLink.from_dict(bad).validate()


def test_schema_rejects_bad_upstream_source_type():
    bad = {
        "document_id": "DOC_x",
        "source_type": "data_vendor",
        "title": "t",
        "retrieved_at": "2026-09-15T00:00:00+08:00",
        "upstream_source_type": "friend_told_me",
    }
    with pytest.raises(jsonschema.ValidationError):
        _validator("document").validate(bad)
