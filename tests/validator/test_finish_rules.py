# -*- coding: utf-8 -*-
"""v3.0.1 §9 收尾错误码：注册一致性 + FAIL Case 覆盖度（Task 6）。

§9 定了五个「本版本必须落地」的错误码。落地容易，**每条都有 FAIL Case** 容易漏，
所以这里做两件机械但有用的事：

1. 五个码必须在 `core/validation/codes.py` 里注册，且等级与 §9 完全一致；
2. 每个码都在测试套件里被真正断言过（不是只写在 codes.py 里当装饰）。

第 2 条是防「注册了但从未触发」的：一个永远不出现的错误码，等于没有这条规则。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for _p in (str(ROOT), str(ROOT / "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core.validation.codes import severity_of  # noqa: E402
from helpers import base_state, codes, make_candidate, make_link, severities  # noqa: E402

# §9「新增固定错误码」：码 → 计划规定等级
FINISH_CODES = {
    "CLAIM_BASIS_UNKNOWN": "P1",
    "TIME_MODEL_LEGACY": "P2",
    "SOURCE_DATE_AFTER_AS_OF": "P1",
    "MARKET_DATA_AFTER_GENERATED_AT": "P1",
    "CANDIDATE_USED_AS_EVIDENCE": "P0",
}

# §8 必测 Case 需要可断言的结构性错误码（计划未点名，但缺了就测不了）
TASK5_CODES = {
    "CLAIM_BASIS_LEVEL_INVALID": "P1",
    "CLAIM_UNCONFIRMED_SUPPORTED": "P1",
}

TEST_DIR = Path(__file__).resolve().parents[1]
THIS_FILE = Path(__file__).resolve()


@pytest.mark.parametrize("code,expected", sorted(FINISH_CODES.items()))
def test_finish_code_registered_with_planned_severity(code, expected):
    assert severity_of(code, default="") == expected, f"{code} 等级应为 {expected}"


@pytest.mark.parametrize("code,expected", sorted(TASK5_CODES.items()))
def test_task5_code_registered(code, expected):
    assert severity_of(code, default="") == expected


@pytest.mark.parametrize("code", sorted({**FINISH_CODES, **TASK5_CODES}))
def test_every_code_is_actually_asserted_somewhere(code):
    """每个错误码都要在**别处**被断言过，否则它只是 codes.py 里的一行字符串。"""
    hits = []
    for path in TEST_DIR.rglob("test_*.py"):
        if path.resolve() == THIS_FILE:
            continue
        if code in path.read_text(encoding="utf-8"):
            hits.append(path.name)
    assert hits, f"{code} 没有任何 FAIL Case —— 请补一个断言它会出现的用例"


def test_candidate_used_as_evidence_is_p0_and_blocks():
    """五个码里唯一的 P0：把线索当证据用，必须直接阻断交付。"""
    state = base_state()
    state.add_candidate(make_candidate("CAN_aaaabbbb", claim_id=None))
    state.add_link(make_link(claim_id="CAN_aaaabbbb", document_id="DOC_h1report"))

    result = severities(state)
    assert result["P0"] >= 1
    assert "CANDIDATE_USED_AS_EVIDENCE" in codes(state)


def test_document_pointing_at_candidate_is_p0_too():
    """绑定关系反过来写错（document_id 指向线索）同样是 P0。"""
    state = base_state()
    state.add_candidate(make_candidate("CAN_ccccdddd", claim_id=None))
    state.add_link(make_link(claim_id="C_FIN_REV_2026H1", document_id="CAN_ccccdddd"))

    assert severities(state)["P0"] >= 1
    assert "CANDIDATE_USED_AS_EVIDENCE" in codes(state)


def test_only_candidate_code_is_p0_among_finish_codes():
    """把等级关系写死：其余四个码都是 P1/P2，不该悄悄升级成阻断。"""
    assert FINISH_CODES["CANDIDATE_USED_AS_EVIDENCE"] == "P0"
    assert all(
        sev != "P0" for code, sev in FINISH_CODES.items() if code != "CANDIDATE_USED_AS_EVIDENCE"
    )
