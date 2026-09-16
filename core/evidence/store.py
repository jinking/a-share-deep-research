#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Evidence Store：证据对象的落盘与读取（v3.0 §6）。

目录约定：
    research_XXXXXX/
    └── evidence/
        ├── candidates.jsonl      # 线索（v3.0.1）：候选 ≠ 证据
        ├── documents.jsonl
        ├── claims.jsonl
        ├── evidence_links.jsonl
        └── raw/            # 原始证据文件（PDF / HTML / 截图等）

一行一个 JSON 对象；空行被忽略；文件必须是 UTF-8。
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from ..issue import Issue
from ..models.base import EvidenceModelError, iso_now
from ..models.candidate import EvidenceCandidate
from ..models.claim import Claim
from ..models.document import SourceDocument
from ..models.evidence import EvidenceLink
from ..models.research_state import ResearchState
from .hasher import make_document_id, sha256_file

__all__ = [
    "EvidenceStoreError",
    "EvidenceStore",
    "CANDIDATES_FILE",
    "DOCUMENTS_FILE",
    "CLAIMS_FILE",
    "LINKS_FILE",
    "RAW_DIR",
    "STAGING_DIR",
]

CANDIDATES_FILE = "candidates.jsonl"
DOCUMENTS_FILE = "documents.jsonl"
CLAIMS_FILE = "claims.jsonl"
LINKS_FILE = "evidence_links.jsonl"
RAW_DIR = "raw"
# raw 文件的暂存目录：校验通过后才 os.replace 进 raw/（v3.0.2 §10）
STAGING_DIR = ".staging"


class EvidenceStoreError(Exception):
    """Evidence Store 使用错误（目录不存在、JSON 无法解析等）。"""


def _stage_text(target: Path, text: str) -> Path:
    """把内容写进同目录的 `<name>.tmp` 并 fsync，返回暂存路径。

    同目录很关键：`os.replace` 只在同一文件系统内保证原子性。
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    return tmp


def _discard(path: Path) -> None:
    """删除临时/备份文件；不存在就什么都不做。"""
    try:
        Path(path).unlink()
    except FileNotFoundError:
        pass


def _read_jsonl(path: Path, issues: List[Issue], label: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not path.exists():
        return rows
    text = path.read_text(encoding="utf-8")
    for lineno, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            issues.append(
                Issue(
                    "P1",
                    "EVIDENCE_PARSE",
                    f"{label} 第 {lineno} 行 JSON 解析失败",
                    str(exc),
                )
            )
            continue
        if not isinstance(obj, dict):
            issues.append(
                Issue("P1", "EVIDENCE_PARSE", f"{label} 第 {lineno} 行不是 JSON 对象", repr(obj)[:120])
            )
            continue
        rows.append(obj)
    return rows


def _write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(r, ensure_ascii=False, sort_keys=False) for r in rows]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


class EvidenceStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.candidates: Dict[str, EvidenceCandidate] = {}
        self.documents: Dict[str, SourceDocument] = {}
        self.claims: Dict[str, Claim] = {}
        self.links: List[EvidenceLink] = []
        self.issues: List[Issue] = []

    # ---------- 路径 ----------

    @property
    def candidates_path(self) -> Path:
        return self.root / CANDIDATES_FILE

    @property
    def documents_path(self) -> Path:
        return self.root / DOCUMENTS_FILE

    @property
    def claims_path(self) -> Path:
        return self.root / CLAIMS_FILE

    @property
    def links_path(self) -> Path:
        return self.root / LINKS_FILE

    @property
    def raw_dir(self) -> Path:
        return self.root / RAW_DIR

    @property
    def staging_dir(self) -> Path:
        """raw 文件的暂存目录（校验通过前不进入 raw/）。"""
        return self.raw_dir / STAGING_DIR

    def resolve_local_path(self, doc: SourceDocument) -> Optional[Path]:
        """把 document.local_path 解析为绝对路径（相对路径以 evidence/ 为基准）。"""
        if not doc.local_path:
            return None
        p = Path(doc.local_path)
        return p if p.is_absolute() else (self.root / p)

    # ---------- 生命周期 ----------

    @classmethod
    def init(cls, root) -> "EvidenceStore":
        store = cls(Path(root))
        store.root.mkdir(parents=True, exist_ok=True)
        store.raw_dir.mkdir(parents=True, exist_ok=True)
        for path in (
            store.candidates_path,
            store.documents_path,
            store.claims_path,
            store.links_path,
        ):
            if not path.exists():
                path.write_text("", encoding="utf-8")
        return store

    @classmethod
    def open(cls, root) -> "EvidenceStore":
        store = cls(Path(root))
        store.load()
        return store

    def load(self) -> "EvidenceStore":
        if not self.root.exists():
            raise EvidenceStoreError(f"Evidence 目录不存在: {self.root}")
        # v3.0.2 §13：load 必须幂等。之前只清 issues，links 是 list，
        # 第二次 load 会把同一批链接再 append 一遍 —— 重复调用会污染状态。
        self.candidates.clear()
        self.documents.clear()
        self.claims.clear()
        self.links.clear()
        self.issues = []

        for row in _read_jsonl(self.candidates_path, self.issues, CANDIDATES_FILE):
            try:
                candidate = EvidenceCandidate.from_dict(row)
                candidate.validate()
            except EvidenceModelError as exc:
                self.issues.append(
                    Issue(
                        "P1",
                        "EVIDENCE_MODEL_INVALID",
                        f"{CANDIDATES_FILE} 存在非法 EvidenceCandidate",
                        str(exc),
                    )
                )
                continue
            if candidate.candidate_id in self.candidates:
                self.issues.append(
                    Issue(
                        "P1",
                        "EVIDENCE_DUPLICATE_ID",
                        f"candidate_id 重复: {candidate.candidate_id}",
                        f"{CANDIDATES_FILE} 中存在多行同一 candidate_id",
                    )
                )
            self.candidates[candidate.candidate_id] = candidate

        for row in _read_jsonl(self.documents_path, self.issues, DOCUMENTS_FILE):
            try:
                doc = SourceDocument.from_dict(row)
                doc.validate()
            except EvidenceModelError as exc:
                self.issues.append(
                    Issue("P1", "EVIDENCE_MODEL_INVALID", f"{DOCUMENTS_FILE} 存在非法 Document", str(exc))
                )
                continue
            if doc.document_id in self.documents:
                self.issues.append(
                    Issue(
                        "P1",
                        "EVIDENCE_DUPLICATE_ID",
                        f"document_id 重复: {doc.document_id}",
                        f"{DOCUMENTS_FILE} 中存在多行同一 document_id",
                    )
                )
            self.documents[doc.document_id] = doc

        for row in _read_jsonl(self.claims_path, self.issues, CLAIMS_FILE):
            try:
                claim = Claim.from_dict(row)
                claim.validate()
            except EvidenceModelError as exc:
                self.issues.append(
                    Issue("P1", "EVIDENCE_MODEL_INVALID", f"{CLAIMS_FILE} 存在非法 Claim", str(exc))
                )
                continue
            if claim.claim_id in self.claims:
                self.issues.append(
                    Issue(
                        "P1",
                        "EVIDENCE_DUPLICATE_ID",
                        f"claim_id 重复: {claim.claim_id}",
                        f"{CLAIMS_FILE} 中存在多行同一 claim_id",
                    )
                )
            self.claims[claim.claim_id] = claim

        for row in _read_jsonl(self.links_path, self.issues, LINKS_FILE):
            try:
                link = EvidenceLink.from_dict(row)
                link.validate()
            except EvidenceModelError as exc:
                self.issues.append(
                    Issue("P1", "EVIDENCE_MODEL_INVALID", f"{LINKS_FILE} 存在非法 EvidenceLink", str(exc))
                )
                continue
            self.links.append(link)

        return self

    def save(self) -> None:
        """把内存状态写回 JSONL（按 evidence_id 排序，便于 diff）。"""
        _write_jsonl(
            self.candidates_path,
            [c.to_dict() for c in sorted(self.candidates.values(), key=lambda c: c.candidate_id)],
        )
        _write_jsonl(self.documents_path, [d.to_dict() for d in self.documents.values()])
        _write_jsonl(self.claims_path, [c.to_dict() for c in self.claims.values()])
        ordered = sorted(self.links, key=lambda l: (l.claim_id, l.evidence_id))
        _write_jsonl(self.links_path, [l.to_dict() for l in ordered])

    # ---------- 原子落盘（v3.0.2 §10） ----------

    def _payloads(self) -> List["tuple[Path, str]"]:
        """把所有 JSONL 的**目标内容先在内存里算完**，再进入落盘阶段。"""

        def render(rows: Iterable[Dict[str, Any]]) -> str:
            lines = [json.dumps(r, ensure_ascii=False, sort_keys=False) for r in rows]
            return "\n".join(lines) + ("\n" if lines else "")

        return [
            (
                self.candidates_path,
                render(
                    [
                        c.to_dict()
                        for c in sorted(self.candidates.values(), key=lambda c: c.candidate_id)
                    ]
                ),
            ),
            (self.documents_path, render([d.to_dict() for d in self.documents.values()])),
            (self.claims_path, render([c.to_dict() for c in self.claims.values()])),
            (
                self.links_path,
                render(
                    [
                        l.to_dict()
                        for l in sorted(self.links, key=lambda l: (l.claim_id, l.evidence_id))
                    ]
                ),
            ),
        ]

    def save_atomic(self) -> None:
        """真正原子地落盘：全部暂存成功后才替换，任何失败都保持原状。

        步骤（§10）：

            1. 每个目标文件写一份 `<name>.tmp` 并 fsync；
            2. 全部写成功后，把原文件 rename 为 `<name>.bak`；
            3. `<name>.tmp` → `<name>`（os.replace，同目录内原子）；
            4. 任一步失败 → 用 `.bak` 回滚已完成的部分，再抛异常。

        与 `save()` 的区别：`save()` 是「逐个文件直接覆盖」，中途失败会留下
        半新半旧的证据库 —— 那正好是最危险的状态（hash 与内容对不上）。
        """
        staged: List["tuple[Path, Path]"] = []
        try:
            for target, text in self._payloads():
                staged.append((_stage_text(target, text), target))
        except BaseException:
            for tmp, _ in staged:
                _discard(tmp)
            raise

        backups: List["tuple[Path, Path]"] = []  # (bak, target)
        replaced: List[Path] = []
        try:
            for tmp, target in staged:
                if target.exists():
                    bak = target.with_name(target.name + ".bak")
                    os.replace(target, bak)
                    backups.append((bak, target))
                os.replace(tmp, target)
                replaced.append(target)
        except BaseException:
            for target in replaced:
                _discard(target)
            for bak, target in backups:
                os.replace(bak, target)
            for tmp, _ in staged:
                _discard(tmp)
            raise
        else:
            for bak, _ in backups:
                _discard(bak)

    def add_raw_file(
        self,
        source,
        *,
        expected_sha256: Optional[str] = None,
        name: Optional[str] = None,
    ) -> Path:
        """把原始文件经 `raw/.staging/` 落进 `raw/`，失败不留残片（v3.0.2 §10）。

        - 先复制到 staging 并**复核落地副本的 sha256**；
        - 校验通过才 `os.replace` 进 raw/；
        - 任何一步失败都把 staging 里的临时文件删掉，raw/ 保持原样。
        """
        src = Path(source)
        if not src.is_file():
            raise EvidenceStoreError(f"原始文件不存在: {src}")
        digest = sha256_file(src)
        if expected_sha256 and digest.lower() != str(expected_sha256).strip().lower():
            raise EvidenceStoreError(
                f"原始文件 sha256 与登记值不符: {src.name}（实际={digest}）"
            )

        self.staging_dir.mkdir(parents=True, exist_ok=True)
        staged = self.staging_dir / (name or src.name)
        try:
            shutil.copy2(src, staged)
            landed = sha256_file(staged)
            if landed.lower() != digest.lower():
                raise EvidenceStoreError(
                    f"落盘副本 sha256 与源文件不一致: {staged.name}（{landed} != {digest}）"
                )
            target = self.raw_dir / (name or src.name)
            os.replace(staged, target)
        except BaseException:
            _discard(staged)
            raise
        finally:
            if self.staging_dir.is_dir() and not any(self.staging_dir.iterdir()):
                self.staging_dir.rmdir()
        return target

    # ---------- 写入 ----------

    def register_document(
        self,
        *,
        source_type: str,
        title: str,
        issuer: Optional[str] = None,
        published_at: Optional[str] = None,
        url: Optional[str] = None,
        local_file: Optional[str] = None,
        local_path: Optional[str] = None,
        source_group: Optional[str] = None,
        document_id: Optional[str] = None,
        page_count: Optional[int] = None,
        sections: Optional[List[str]] = None,
        retrieved_at: Optional[str] = None,
        copy_into_raw: bool = False,
        note: Optional[str] = None,
        provider: Optional[str] = None,
        upstream_source_type: Optional[str] = None,
        upstream_document_id: Optional[str] = None,
    ) -> SourceDocument:
        """登记一个 Document。

        local_file：磁盘上原始文件的路径；登记时会计算 sha256。
                    若 copy_into_raw=True，会复制到 evidence/raw/ 并把 local_path 写成相对路径。
        local_path：直接指定相对 evidence/ 的路径（不复制）；若该文件已存在，同样会计算 sha256。
        """
        if local_file and local_path:
            raise EvidenceStoreError("local_file 与 local_path 不能同时指定（前者会复制，后者只登记）")

        retrieved_at = retrieved_at or iso_now()
        digest: Optional[str] = None

        if local_file:
            src = Path(local_file)
            if not src.is_file():
                raise EvidenceStoreError(f"原始文件不存在: {src}")
            digest = sha256_file(src)
            if copy_into_raw:
                self.raw_dir.mkdir(parents=True, exist_ok=True)
                target = self.raw_dir / src.name
                if src.resolve() != target.resolve():
                    shutil.copy2(src, target)
                local_path = f"{RAW_DIR}/{src.name}"
            else:
                local_path = str(src)
        elif local_path:
            candidate = Path(local_path)
            if not candidate.is_absolute():
                candidate = self.root / candidate
            if candidate.is_file():
                digest = sha256_file(candidate)

        doc = SourceDocument(
            document_id=document_id
            or make_document_id(url=url, title=title, published_at=published_at, issuer=issuer),
            source_type=source_type,
            title=title,
            retrieved_at=retrieved_at,
            issuer=issuer,
            published_at=published_at,
            url=url,
            local_path=local_path,
            sha256=digest,
            source_group=source_group,
            page_count=page_count,
            sections=list(sections or []),
            note=note,
            provider=provider,
            upstream_source_type=upstream_source_type,
            upstream_document_id=upstream_document_id,
        )
        doc.validate()
        self.documents[doc.document_id] = doc
        return doc

    def add_candidate(self, candidate: EvidenceCandidate) -> EvidenceCandidate:
        """登记一条线索。线索不是证据——它不会进入任何证据校验的通过口径。"""
        candidate.validate()
        self.candidates[candidate.candidate_id] = candidate
        return candidate

    def candidate_of(self, candidate_id: str) -> Optional[EvidenceCandidate]:
        return self.candidates.get(candidate_id)

    def add_claim(self, claim: Claim) -> Claim:
        claim.validate()
        self.claims[claim.claim_id] = claim
        return claim

    def add_link(self, link: EvidenceLink) -> EvidenceLink:
        link.validate()
        self.links.append(link)
        return link

    def next_evidence_id(self, claim_id: str) -> str:
        n = len([l for l in self.links if l.claim_id == claim_id]) + 1
        return f"EV_{claim_id}_{n:02d}"

    def links_of(self, claim_id: str) -> List[EvidenceLink]:
        return [l for l in self.links if l.claim_id == claim_id]

    def document_of(self, link: EvidenceLink) -> Optional[SourceDocument]:
        return self.documents.get(link.document_id)

    # ---------- 读取 ----------

    def state(
        self,
        *,
        research_date: Optional[str] = None,
        as_of: Optional[str] = None,
        market_data_as_of: Optional[str] = None,
        generated_at: Optional[str] = None,
    ) -> ResearchState:
        return ResearchState(
            documents=dict(self.documents),
            claims=dict(self.claims),
            links=list(self.links),
            candidates=dict(self.candidates),
            research_date=research_date,
            as_of=as_of,
            market_data_as_of=market_data_as_of,
            generated_at=generated_at,
        )

    def summary(self) -> Dict[str, int]:
        return {
            "candidates": len(self.candidates),
            "documents": len(self.documents),
            "claims": len(self.claims),
            "links": len(self.links),
        }
