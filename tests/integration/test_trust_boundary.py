# -*- coding: utf-8 -*-
"""Trust Boundary 负向夹具回归（v3.0.3 §10 / §13）。

每个夹具是一个**小型可运行产物**，模拟一条真实的绕过路径：

    tests/fixtures/invalid/
    ├── stale_claim_fingerprint/        只改 Claim 正文，锚点 id/level/status 全对
    ├── fake_verified_excerpt/          手工把摘录写成 verified
    ├── vendor_fake_primary/            服务商手改 JSONL 冒充一手来源
    └── manifest_missing_strict_claim/  从 manifest 删掉一条 strict Claim

它们与 `tests/validator/fixtures/` 的区别：那边是**单对象级**的 schema 夹具
（一个 document.json / claim.json），这边是**整库级**的绕过夹具 —— 需要走完整
加载 + 校验链路才能看出问题，正是「字段都合法、组合起来才错」的那一类。

约定（`case.json`）：

    validator          用哪条校验链路：evidence | report_claims
    expect_codes       {错误码: 级别}
    expect_exclusive   true 表示这个夹具**只**出这一条 fault（其余部分干净）

`expect_exclusive` 是这类夹具的价值所在：如果某个夹具开始顺带报出别的码，
说明它已经不能精确隔离那条绕过路径了，测试会直接喊出来。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for _p in (str(ROOT), str(ROOT / "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core.evidence import EvidenceStore
from core.report import parse_report_claims
from core.validation import validate_evidence, validate_report_claims

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "invalid"

CASES = sorted(p for p in FIXTURES.iterdir() if (p / "case.json").is_file())
CASE_IDS = [p.name for p in CASES]


def _case(path: Path):
    return json.loads((path / "case.json").read_text(encoding="utf-8"))


def _run(path: Path, case):
    """执行夹具，返回 [(severity, code), ...]。"""
    findings = []

    def emit(severity, code, message, detail=""):
        findings.append((severity, code))

    store = EvidenceStore.open(path / "evidence")

    if case["validator"] == "evidence":
        manifest_path = path / "manifest.v3.json"
        manifest = (
            json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest_path.is_file()
            else None
        )
        validate_evidence(
            store.state(),
            emit=emit,
            manifest=manifest,
            strict=True,
            store_issues=store.issues,
            documents_base_dir=str(path / "evidence"),
        )
    elif case["validator"] == "report_claims":
        manifest_path = path / "manifest.v3.json"
        manifest = (
            json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest_path.is_file()
            else {}
        )
        refs = parse_report_claims((path / "report.html").read_text(encoding="utf-8"))
        validate_report_claims(
            refs,
            claims=store.claims,
            evidence_refs=manifest.get("evidence_refs"),
            emit=emit,
        )
    else:
        raise AssertionError(f"未知 validator: {case['validator']}")

    # 只保留 P0/P1/P2（INFO 不算 fault）
    return [(s, c) for s, c in findings if s in {"P0", "P1", "P2"}]


@pytest.mark.parametrize("path", CASES, ids=CASE_IDS)
def test_fixture_has_case_contract(path):
    case = _case(path)
    for key in ("name", "title", "bypass", "validator", "expect_codes", "why"):
        assert case.get(key), f"{path.name}: case.json 缺 {key}"
    assert case["name"] == path.name


@pytest.mark.parametrize("path", CASES, ids=CASE_IDS)
def test_bypass_is_caught(path):
    case = _case(path)
    found = _run(path, case)
    codes = {c for _, c in found}
    for code, severity in case["expect_codes"].items():
        assert code in codes, f"{path.name}: 未报出 {code}；实际={sorted(codes)}"
        assert (severity, code) in found, (
            f"{path.name}: {code} 的级别应为 {severity}；实际={found}"
        )


@pytest.mark.parametrize("path", CASES, ids=CASE_IDS)
def test_bypass_is_caught_and_nothing_else_is(path):
    """`expect_exclusive`：夹具必须精确隔离那一条绕过路径。"""
    case = _case(path)
    if not case.get("expect_exclusive"):
        return
    found = _run(path, case)
    expected = {(severity, code) for code, severity in case["expect_codes"].items()}
    assert set(found) == expected, (
        f"{path.name}: 期望只出 {sorted(expected)}，实际 {sorted(set(found))}；"
        "夹具已不能精确隔离这条绕过路径"
    )


@pytest.mark.parametrize("path", CASES, ids=CASE_IDS)
def test_fixture_does_not_depend_on_llm_judgement(path):
    """结构断言：夹具的期望是「错误码 + 级别」，没有任何自然语言真假判断。"""
    case = _case(path)
    for code, severity in case["expect_codes"].items():
        assert severity in {"P0", "P1", "P2"}
        assert code.isupper() and "_" in code, code


# --------------------------------------------------------------------------- #
# 逐个夹具的语义断言：光「报错了」不够，要报对
# --------------------------------------------------------------------------- #


def _by_name(name):
    return next(p for p in CASES if p.name == name)


# --------------------------------------------------------------------------- #
# 闸门不许静默变小：v3.0.3 §11 Gate 5 点名要覆盖的绕过路径，一条都不能少
# --------------------------------------------------------------------------- #

REQUIRED_BYPASSES = {
    "stale_claim_fingerprint": "REPORT_CLAIM_REVISION_MISMATCH",
    "fake_verified_excerpt": "EVIDENCE_EXCERPT_VERIFICATION_MISMATCH",
    "vendor_fake_primary": "EVIDENCE_MODEL_INVALID",
    "manifest_missing_strict_claim": "MANIFEST_STRICT_CLAIM_MISSING",
}


def test_required_bypass_categories_are_all_present():
    """删掉一个夹具 = 闸门少管一条绕过路径。这条测试让那种改动无法悄悄发生。"""
    present = {p.name for p in CASES}
    missing = sorted(set(REQUIRED_BYPASSES) - present)
    assert not missing, (
        f"Gate 5 要求的绕过夹具缺失: {missing}；"
        "它们分别覆盖 Claim 版本漂移 / 假已验证摘录 / 服务商冒充一手 / manifest 反向覆盖"
    )


def test_required_bypass_categories_expect_the_named_codes():
    for name, code in REQUIRED_BYPASSES.items():
        case = _case(_by_name(name))
        assert list(case["expect_codes"]) == [code], f"{name}: 期望错误码被改动过"


def test_atomic_failure_regression_exists():
    """Gate 5 第 5 项（原子落盘故障注入）由独立测试文件承担，这里只确认它还在。"""
    path = Path(__file__).resolve().parent / "test_promotion_atomic.py"
    assert path.is_file(), "tests/integration/test_promotion_atomic.py 缺失：Gate 5b 会空跑"


def test_stale_fingerprint_keeps_id_level_status_correct():
    """这个夹具的说服力在于：id / level / status 三个属性都是**对的**。"""
    path = _by_name("stale_claim_fingerprint")
    html = (path / "report.html").read_text(encoding="utf-8")
    assert 'data-claim-id="C_ORDER_224G_STATUS"' in html
    assert 'data-claim-level="management_statement"' in html
    assert 'data-claim-status="supported"' in html
    # 只有指纹是旧版本的
    assert 'data-claim-fingerprint="4cf51f0241398c5f"' in html

    from core.models.claim import Claim
    from core.models.fingerprint import claim_fingerprint

    current = Claim.from_dict(
        json.loads((path / "evidence" / "claims.jsonl").read_text(encoding="utf-8").strip())
    )
    assert claim_fingerprint(current) == "197e4f42ddbec383"
    assert claim_fingerprint(current) != "4cf51f0241398c5f"


def test_fake_excerpt_original_says_the_opposite():
    """原件说的是「尚未进入量产」，摘录写成「已进入量产阶段」—— 文件在、可比对、不命中。"""
    path = _by_name("fake_verified_excerpt")
    original = (path / "evidence" / "raw" / "2026H1_excerpt.txt").read_text(encoding="utf-8")
    link = json.loads(
        (path / "evidence" / "evidence_links.jsonl").read_text(encoding="utf-8").strip()
    )
    assert "尚未进入量产" in original
    assert "已进入量产阶段" not in original
    assert "已进入量产阶段" in link["evidence_text"]
    assert link["excerpt_verification_status"] == "verified"


def test_vendor_fixture_records_the_upstream_it_claims():
    """服务商确实写了 upstream —— 证明「声明上游」不再是拿到 Primary 的通行证。"""
    path = _by_name("vendor_fake_primary")
    doc = json.loads(
        (path / "evidence" / "documents.jsonl").read_text(encoding="utf-8").strip()
    )
    assert doc["provider"] == "westock-data"
    assert doc["source_type"] == "official_database"
    assert doc["upstream_source_type"] == "official_database"

    store = EvidenceStore.open(path / "evidence")
    # 装载期即被拦下，根本没有进入内存状态
    assert doc["document_id"] not in store.documents


def test_manifest_fixture_only_registers_the_normal_claim():
    """被删掉的是 major：manifest 里只剩那条 normal 的。"""
    path = _by_name("manifest_missing_strict_claim")
    manifest = json.loads((path / "manifest.v3.json").read_text(encoding="utf-8"))
    refs = [r["claim_id"] for r in manifest["evidence_refs"]]
    assert refs == ["C_REV_2025_PAYOUT"]

    claims = [
        json.loads(line)
        for line in (path / "evidence" / "claims.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert {c["claim_id"]: c["materiality"] for c in claims} == {
        "C_REV_2025_PAYOUT": "normal",
        "C_MARGIN_DROP_2026H1": "major",
    }
