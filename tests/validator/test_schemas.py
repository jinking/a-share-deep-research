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
