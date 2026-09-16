# -*- coding: utf-8 -*-
"""报告结论漂移回归（v3.0.2 §14 Gate 4 / §17）。

这里是 v3.0.2 的核心命题的可执行版本：

    「当证据层已经把一个结论改掉以后，最终交付给人的报告还能不能继续保留旧结论？」
    → 不能。Validator 必须阻断。

两类用例：
1. §17 的负 Golden Sample —— 真实存在的一份「旧结论漂移样板」，必须 FAIL；
2. §14 的四个故障注入 —— 分别把 Ledger 或报告改坏，看闸门是否真的抓得住。

第 2 类里有一条特别值得留意：**把 Claim 改成 pending 之后，报告哪怕「一个字没动」也必须 FAIL**，
因为未声明 level/status 的锚点会按「事实 / supported」解读（锚定即声明）。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

from helpers import claim_anchor, minimal_report_html, valid_manifest

from core.evidence import EvidenceStore
from core.evidence.excerpt import stamp_excerpt_verification
from core.models import Claim, EvidenceLink

ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = ROOT / "scripts" / "validate_report.py"
NEGATIVE_SAMPLE = ROOT / "examples" / "invalid" / "意华股份002897_旧结论漂移样板"
SHARED_EVIDENCE = ROOT / "examples" / "意华股份002897_样板" / "evidence"

GENERATED_AT = "2026-09-15T09:05:32+08:00"          # manifest.meta.generated_at
GENERATED_AT_TEXT = "2026-09-15 09:05:32"           # 报告内「生成于 …」
GENERATED_AT_STAMP = "20260915_090532"              # 文件名时间戳
AS_OF = "2026-09-14T15:00:00+08:00"


def _run(report: Path, manifest: Path, evidence_dir: Path, out: Path, *extra: str):
    return subprocess.run(
        [
            sys.executable, str(VALIDATOR), str(report),
            "--manifest", str(manifest),
            "--evidence-dir", str(evidence_dir),
            "--out", str(out),
            *extra,
        ],
        capture_output=True, text=True, cwd=str(ROOT),
    )


def _codes(out_dir: Path) -> List[str]:
    payload = json.loads((out_dir / "validation_report.json").read_text(encoding="utf-8"))
    return [f["code"] for f in payload["findings"] if f["severity"] in {"P0", "P1"}]


# --------------------------------------------------------------------------- #
# 1. §17 负 Golden Sample
# --------------------------------------------------------------------------- #


def test_negative_sample_exists_and_retains_old_conclusions():
    """负样本必须真的保留旧结论，否则它证明不了任何事。"""
    report = NEGATIVE_SAMPLE / "意华股份002897_深度研究_20260915_090532.html"
    assert report.is_file()
    text = report.read_text(encoding="utf-8")
    assert "送样阶段" in text
    assert "53.83×" in text
    assert "4.22 亿元" in text


def test_negative_sample_must_fail(tmp_path):
    """旧结论漂移样板必须 FAIL —— 这正是 v3.0.2 存在的理由。"""
    report = NEGATIVE_SAMPLE / "意华股份002897_深度研究_20260915_090532.html"
    manifest = NEGATIVE_SAMPLE / "research_manifest.v3.json"
    result = _run(report, manifest, SHARED_EVIDENCE, tmp_path / "v")

    assert result.returncode == 1, result.stdout
    codes = _codes(tmp_path / "v")
    # 三类旧结论各自对应的 P0
    assert "REPORT_CLAIM_LEVEL_MISMATCH" in codes          # E007：在研被当成普通事实
    assert "REPORT_UNCONFIRMED_AS_FACT" in codes           # PE(TTM) / 一致预期被写成事实
    assert "REPORT_PENDING_CLAIM_ASSERTED" in codes        # pending 状态被当成确定性结论


# --------------------------------------------------------------------------- #
# 2. §14 故障注入（用最小构件，不依赖 5.8MB 样板）
# --------------------------------------------------------------------------- #

CLAIMS = [
    {"claim_id": "E001", "level": "fact", "status": "supported", "materiality": "critical",
     "anchor_level": "fact", "anchor_status": "supported"},
    {"claim_id": "E007", "level": "management_statement", "status": "supported", "materiality": "critical",
     "anchor_level": "management_statement", "anchor_status": "supported"},
    {"claim_id": "C_MKT_CAP", "level": "inference", "status": "supported", "materiality": "critical",
     "anchor_level": "inference", "anchor_status": "supported"},
    {"claim_id": "C_PE", "level": "unconfirmed", "status": "pending", "materiality": "normal",
     "anchor_level": "unconfirmed", "anchor_status": "pending"},
]

_BASELINE_BY_ID = {c["claim_id"]: c for c in CLAIMS}


def _claim_obj(c: Dict[str, Any]) -> Claim:
    return Claim(
        claim_id=c["claim_id"],
        claim=f"{c['claim_id']} 的结论",
        category="financial",
        level=c["level"],
        materiality=c["materiality"],
        status=c["status"],
    )


def _baseline_fingerprint(claim_id: str) -> str:
    """报告锚点写的是**基线版本**的指纹 —— 因为报告是在基线状态下生成的。

    注入测试改的是 Ledger、不动报告，于是指纹成了「报告有没有跟上 Ledger」的探针。
    这正是 v3.0.3 §4 存在的理由：claim_id/level/status 可能全都对得上，报告却仍然
    停留在被推翻的那一版结论上。
    """
    return _claim_obj(_BASELINE_BY_ID[claim_id]).claim_fingerprint


def _build(tmp_path, *, claims: List[Dict[str, Any]] = CLAIMS) -> Dict[str, Path]:
    """建一个最小但**完整且合法**的三段组合：报告 + v3 manifest + Evidence Store。

    这里必须真的能 PASS —— 否则后面任何一个 FAIL 都说不清是「注入造成的」还是
    「基线本来就不合法」。所以三段都按正式产物口径构造：

    - 报告：0–16 章 / 三情景 / 三年 / 12 行跟踪表 / 证据标签 / 生成时间戳 / Claim 指纹；
    - manifest：完整 v3（meta+forecast+valuation+final）+ 全套时间模型 + evidence_refs；
    - Evidence Store：真实原始文件（可校验 sha256）+ critical Claim 的定位与摘录。
    """
    # ---- Evidence Store：与 helpers.write_store 同口径，保证 hash 可校验 ----
    ev = tmp_path / "evidence"
    store = EvidenceStore.init(ev)
    excerpt = "营业收入 2,863,000,000 元，同比下降 5.97%"
    (store.raw_dir / "2026H1.txt").write_text(
        "测试公司 2026 年半年度报告（节选）\n" + excerpt + "\n", encoding="utf-8"
    )
    doc = store.register_document(
        source_type="interim_report",
        title="测试公司 2026 年半年度报告",
        issuer="测试公司",
        published_at="2026-08-25",
        url="https://www.cninfo.com.cn/002897/2026H1.pdf",
        local_path="raw/2026H1.txt",
        source_group="CNINFO_002897_2026H1",
        page_count=168,
    )
    for c in claims:
        store.add_claim(_claim_obj(c))
        store.add_link(
            EvidenceLink(
                evidence_id=f"EV_{c['claim_id']}_01",
                claim_id=c["claim_id"],
                document_id=doc.document_id,
                page=12,
                section="主要会计数据",
                evidence_text=excerpt,
                support_type="direct",
                confidence=1.0,
            )
        )
    stamp_excerpt_verification(store)   # 摘录验证状态来自真实比对（v3.0.2 §9）
    store.save()

    # ---- 报告：结构完整 + Claim 锚点（带基线指纹）+ 生成时间戳 ----
    anchors = [
        claim_anchor(
            c["claim_id"],
            c["anchor_level"],
            c["anchor_status"],
            f"{c['claim_id']} 旧口径结论",
            fingerprint=_baseline_fingerprint(c["claim_id"]),
        )
        for c in claims
        if c.get("anchor_level") is not None
    ]
    report = tmp_path / f"report_{GENERATED_AT_STAMP}.html"
    report.write_text(
        minimal_report_html(anchors=anchors, generated_at=GENERATED_AT_TEXT),
        encoding="utf-8",
    )

    # ---- manifest：完整 v3，evidence_refs 与 Ledger 的 materiality 对齐 ----
    manifest = valid_manifest()
    manifest["manifest_version"] = 3
    manifest["meta"].update(
        {"as_of": AS_OF, "market_data_as_of": AS_OF, "generated_at": GENERATED_AT}
    )
    manifest["evidence"] = []  # v3 用 evidence_refs 承载证据，不再保留 v2 的 evidence[]
    manifest["evidence_refs"] = [
        {"claim_id": c["claim_id"], "importance": c["materiality"]} for c in claims
    ]
    manifest_path = tmp_path / "research_manifest.v3.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return {"report": report, "manifest": manifest_path, "evidence": ev}


def test_baseline_passes_then_each_injection_fails(tmp_path):
    """基线必须 PASS —— 否则后面所有 FAIL 都不能说明是注入造成的。"""
    paths = _build(tmp_path)
    assert _run(paths["report"], paths["manifest"], paths["evidence"], tmp_path / "ok").returncode == 0


def test_injection_claim_downgraded_to_pending_fails(tmp_path):
    """注入 ①：把 E007 改成 pending，报告仍写 supported → FAIL。"""
    claims = [dict(c) for c in CLAIMS]
    for c in claims:
        if c["claim_id"] == "E007":
            c["status"] = "pending"
    paths = _build(tmp_path, claims=claims)
    result = _run(paths["report"], paths["manifest"], paths["evidence"], tmp_path / "v")
    assert result.returncode == 1
    assert "REPORT_PENDING_CLAIM_ASSERTED" in _codes(tmp_path / "v")


def test_injection_claim_level_changed_to_inference_fails(tmp_path):
    """注入 ②：把 E007 的 level 改成 inference，报告仍声明 fact → FAIL。"""
    claims = [dict(c) for c in CLAIMS]
    for c in claims:
        if c["claim_id"] == "E007":
            c["level"] = "inference"
            c["anchor_level"] = "fact"
    paths = _build(tmp_path, claims=claims)
    result = _run(paths["report"], paths["manifest"], paths["evidence"], tmp_path / "v")
    assert result.returncode == 1
    assert "REPORT_CLAIM_LEVEL_MISMATCH" in _codes(tmp_path / "v")


def test_injection_unknown_claim_reference_fails(tmp_path):
    """注入 ③：报告引用不存在的 Claim → FAIL。"""
    paths = _build(tmp_path)
    paths["report"].write_text(
        paths["report"].read_text(encoding="utf-8").replace(
            'data-claim-id="E001"', 'data-claim-id="E999"'
        ),
        encoding="utf-8",
    )
    result = _run(paths["report"], paths["manifest"], paths["evidence"], tmp_path / "v")
    assert result.returncode == 1
    assert "REPORT_CLAIM_UNKNOWN" in _codes(tmp_path / "v")


def test_injection_removing_critical_anchor_fails(tmp_path):
    """注入 ④：删掉 critical Claim 的落点 → FAIL。"""
    paths = _build(tmp_path)
    text = paths["report"].read_text(encoding="utf-8")
    # 删掉 C_MKT_CAP 那一整个 span（连同内容）
    start = text.index('<span data-claim-id="C_MKT_CAP"')
    end = text.index("</span>", start) + len("</span>")
    paths["report"].write_text(text[:start] + text[end:], encoding="utf-8")
    result = _run(paths["report"], paths["manifest"], paths["evidence"], tmp_path / "v")
    assert result.returncode == 1
    assert "REPORT_CRITICAL_CLAIM_MISSING" in _codes(tmp_path / "v")


def test_injection_omitting_level_status_declaration_fails(tmp_path):
    """注入 ⑤（最隐蔽的一种）：锚点不写 level/status，靠「缺省不检查」蒙混过关。

    锚定即声明 —— 缺省按「事实 / supported」解读，所以 pending 的 Claim 照样被抓住。
    """
    paths = _build(tmp_path)
    text = paths["report"].read_text(encoding="utf-8")
    text = text.replace(' data-claim-level="unconfirmed" data-claim-status="pending"', "")
    paths["report"].write_text(text, encoding="utf-8")
    result = _run(paths["report"], paths["manifest"], paths["evidence"], tmp_path / "v")
    assert result.returncode == 1
    assert "REPORT_PENDING_CLAIM_ASSERTED" in _codes(tmp_path / "v")


def test_claim_only_mode_catches_the_same_injection(tmp_path):
    """Gate 4 用的 --claim-only 必须与全链路判定一致（否则两个闸门会打架）。"""
    claims = [dict(c) for c in CLAIMS]
    for c in claims:
        if c["claim_id"] == "E007":
            c["status"] = "pending"
    paths = _build(tmp_path, claims=claims)
    result = _run(paths["report"], paths["manifest"], paths["evidence"], tmp_path / "v", "--claim-only")
    assert result.returncode == 1
    assert "REPORT_PENDING_CLAIM_ASSERTED" in _codes(tmp_path / "v")
