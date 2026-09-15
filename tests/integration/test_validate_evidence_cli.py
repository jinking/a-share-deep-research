# -*- coding: utf-8 -*-
"""validate_evidence.py 的退出码语义（真实 CLI，子进程）。

背景：examples/ 里的 Golden Sample 是**故意不完整**的——已归档的待补缺口
（P1）本来就该存在。CI 不该断言它完整，只需要断言一条不变量：

    「已提交的证据原件必须真实可校验」→ P0 与 P2 必须为 0。

因此验收器提供 --fail-on，让调用方声明「哪些等级才算失败」。本文件把
默认行为、放宽行为、非法取值三种情况都固定下来。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from helpers import write_store

ROOT = Path(__file__).resolve().parents[2]
VALIDATE_EVIDENCE = ROOT / "scripts" / "validate_evidence.py"


def _run(evidence_dir: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(VALIDATE_EVIDENCE), str(evidence_dir), *extra],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )


def _store_with_p1_only(tmp_path) -> Path:
    """P0=0、P2=0，但有 P1（critical Claim 缺定位与摘录）的证据库。"""
    store = write_store(tmp_path)
    link = store.links[0]
    link.page = None
    link.section = None
    link.table = None
    link.evidence_text = None
    store.save()
    return store.root


def test_default_fail_on_is_p0_p1(tmp_path):
    """默认行为不变：P0/P1 都阻断。"""
    root = _store_with_p1_only(tmp_path)
    result = _run(root)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "EVIDENCE_LOCATOR_MISSING" in result.stdout
    assert "阻断等级: P0,P1" in result.stdout


def test_fail_on_p0_p2_ignores_archived_p1_gaps(tmp_path):
    """样板场景：只有 P0/P2 才算失败，P1 缺口打印但不阻断。"""
    root = _store_with_p1_only(tmp_path)
    result = _run(root, "--fail-on", "P0,P2")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "状态: ✅ PASS" in result.stdout
    # 缺口仍然被如实打印出来，只是不阻断
    assert "EVIDENCE_LOCATOR_MISSING" in result.stdout
    assert "EVIDENCE_TEXT_MISSING" in result.stdout
    assert "阻断等级: P0,P2" in result.stdout


def test_fail_on_p0_p2_still_catches_missing_original(tmp_path):
    """放宽不等于放水：原件缺失仍需拦住。

    口径一致性：登记的 hash 还在、文件却没了 → P2（无法校验），
    与「文件在但摘要不符 = P0（证据被替换）」不可混淆。
    这条正是「raw/ 被 .gitignore 吃掉」这类事故的探测器。
    """
    store = write_store(tmp_path)
    link = store.links[0]
    link.evidence_text = None  # 制造 P1，确保 P1 不是唯一问题
    store.save()
    # 删掉已提交的原件
    (store.root / "raw" / "2026H1.txt").unlink()

    result = _run(store.root, "--fail-on", "P0,P2")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "P2=1" in result.stdout, result.stdout
    assert "P0=0" in result.stdout, result.stdout


def test_missing_original_is_not_confused_with_replaced(tmp_path):
    """P2（文件缺失）与 P0（文件被替换）必须区分开。"""
    store = write_store(tmp_path)
    store.save()
    raw = store.root / "raw" / "2026H1.txt"

    # 文件被替换 → P0
    raw.write_text("事后被替换的内容", encoding="utf-8")
    replaced = _run(store.root, "--fail-on", "P0,P2")
    assert replaced.returncode == 1
    assert "P0=1" in replaced.stdout, replaced.stdout

    # 文件缺失 → P2，不是 P0
    raw.unlink()
    missing = _run(store.root, "--fail-on", "P0,P2")
    assert missing.returncode == 1
    assert "P0=0" in missing.stdout and "P2=1" in missing.stdout, missing.stdout


def test_invalid_fail_on_value_is_arg_error(tmp_path):
    root = _store_with_p1_only(tmp_path)
    result = _run(root, "--fail-on", "ERROR001")
    assert result.returncode == 2
    assert "非法" in result.stdout


def test_missing_evidence_dir_is_file_error(tmp_path):
    result = _run(tmp_path / "nope")
    assert result.returncode == 2
    assert "不存在" in result.stdout
