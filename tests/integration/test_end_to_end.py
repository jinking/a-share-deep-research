# -*- coding: utf-8 -*-
"""端到端：validate_report.py --evidence-dir 的实际接线（v3.0 §21）。

这里跑的是真实 CLI（子进程），确保「报告 + manifest + Evidence Store」三段
串起来之后的退出码与错误码都是可预期的。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from core.evidence import sha256_file
from helpers import claim_anchor, make_claim, minimal_report_html, valid_manifest, write_store

ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = ROOT / "scripts" / "validate_report.py"

# 与 write_store() 里的 Claim 对齐：C_FIN_REV_2026H1 / fact / supported
# v3.0.3 §4：锚点还必须带上这一版 Claim 的指纹
GOOD_FINGERPRINT = make_claim().claim_fingerprint
GOOD_ANCHOR = claim_anchor("C_FIN_REV_2026H1", "fact", "supported", fingerprint=GOOD_FINGERPRINT)


def _manifest_v3(evidence_dir_name: str = "evidence"):
    data = valid_manifest()
    data["manifest_version"] = 3
    data["meta"]["evidence_dir"] = evidence_dir_name
    data["evidence_refs"] = [{"claim_id": "C_FIN_REV_2026H1", "importance": "critical"}]
    return data


def _run(tmp_path, manifest, *, anchors=(GOOD_ANCHOR,), extra_args=()) -> subprocess.CompletedProcess:
    report = tmp_path / "report.html"
    report.write_text(minimal_report_html(anchors=anchors), encoding="utf-8")
    manifest_path = tmp_path / "research_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return subprocess.run(
        [
            sys.executable,
            str(VALIDATOR),
            str(report),
            "--manifest",
            str(manifest_path),
            "--evidence-dir",
            str(tmp_path / "evidence"),
            "--out",
            str(tmp_path / "validation"),
            *extra_args,
        ],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )


def test_v3_artifact_passes_end_to_end(tmp_path):
    write_store(tmp_path)
    result = _run(tmp_path, _manifest_v3())
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS" in result.stdout

    payload = json.loads((tmp_path / "validation" / "validation_report.json").read_text(encoding="utf-8"))
    assert payload["status"] == "PASS"
    assert payload["summary"]["P0"] == 0 and payload["summary"]["P1"] == 0
    assert payload["evidence_summary"]["P0"] == 0 and payload["evidence_summary"]["P1"] == 0
    assert payload["claim_summary"]["P0"] == 0 and payload["claim_summary"]["P1"] == 0
    codes = [f["code"] for f in payload["findings"] if f["severity"] in {"P0", "P1"}]
    assert codes == []


def test_critical_claim_without_anchor_fails_end_to_end(tmp_path):
    """v3.0.2 §3：critical Claim 必须在报告里有落点，否则 P1 阻断。"""
    write_store(tmp_path)
    result = _run(tmp_path, _manifest_v3(), anchors=())
    assert result.returncode == 1
    assert "REPORT_CRITICAL_CLAIM_MISSING" in result.stdout
    payload = json.loads((tmp_path / "validation" / "validation_report.json").read_text(encoding="utf-8"))
    assert payload["claim_summary"]["P1"] == 1


def test_claim_only_mode_isolates_cross_artifact_check(tmp_path):
    write_store(tmp_path)
    result = _run(tmp_path, _manifest_v3(), extra_args=("--claim-only",))
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads((tmp_path / "validation" / "validation_report.json").read_text(encoding="utf-8"))
    assert payload["evidence_summary"] is None      # 只跑跨产物层
    assert payload["claim_summary"]["P0"] == 0

    bad = _run(
        tmp_path,
        _manifest_v3(),
        anchors=(claim_anchor("C_FIN_REV_2026H1", "inference", "supported", fingerprint=GOOD_FINGERPRINT),),
        extra_args=("--claim-only",),
    )
    assert bad.returncode == 1
    assert "REPORT_CLAIM_LEVEL_MISMATCH" in bad.stdout


def test_tampered_evidence_file_fails_end_to_end(tmp_path):
    store = write_store(tmp_path)
    (tmp_path / "evidence" / "raw" / "2026H1.txt").write_text("事后被替换的内容", encoding="utf-8")

    result = _run(tmp_path, _manifest_v3())
    assert result.returncode == 1
    payload = json.loads((tmp_path / "validation" / "validation_report.json").read_text(encoding="utf-8"))
    codes = [f["code"] for f in payload["findings"] if f["severity"] == "P0"]
    assert "EVIDENCE_HASH_MISMATCH" in codes
    # 登记的 hash 仍是原始文件的摘要
    doc = next(iter(store.documents.values()))
    assert doc.sha256 != sha256_file(tmp_path / "evidence" / "raw" / "2026H1.txt")


def test_v3_manifest_without_evidence_dir_fails(tmp_path):
    report = tmp_path / "report.html"
    report.write_text(minimal_report_html(), encoding="utf-8")
    manifest_path = tmp_path / "research_manifest.json"
    manifest_path.write_text(json.dumps(_manifest_v3(), ensure_ascii=False), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(VALIDATOR), str(report), "--manifest", str(manifest_path), "--out", str(tmp_path / "v")],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert result.returncode == 1
    assert "EVIDENCE_STORE_MISSING" in result.stdout


def test_v2_manifest_still_works_without_evidence_dir(tmp_path):
    report = tmp_path / "report.html"
    report.write_text(minimal_report_html(), encoding="utf-8")
    manifest_path = tmp_path / "research_manifest.json"
    manifest_path.write_text(json.dumps(valid_manifest(), ensure_ascii=False), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(VALIDATOR), str(report), "--manifest", str(manifest_path), "--out", str(tmp_path / "v")],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MANIFEST_V2_COMPAT" not in result.stdout  # INFO 行不打印，只有 P0/P1 打印
    payload = json.loads((tmp_path / "v" / "validation_report.json").read_text(encoding="utf-8"))
    assert "MANIFEST_V2_COMPAT" in [f["code"] for f in payload["findings"]]
