#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""neodata —— 语义检索源（search），WorkBuddy 平台金融数据服务。

它用 **自然语言** 查询股票基本面里最难结构化的一块，恰好补上结构化源的盲区：

    财报全文语义检索 / 主营构成拆解 / 供应链关系（供应商·客户）
    / 业绩发布会纪要 / 机构评级与一致预期 / 股权质押·解禁·风险事件

调用方式
--------
端点：https://copilot.tencent.com/agenttool/v1/neodata （POST JSON）
固定字段：channel=neodata、sub_channel=workbuddy

凭证：由 WorkBuddy 平台下发，本地缓存于 ~/.workbuddy/.neodata_token（12 小时有效）。
  - 缓存有效 → 直接查
  - 失效 / 缺失 → 需要 Agent 调用 connect_cloud_service 取新凭证，再执行：
        python3 providers/neodata.py --save-token "<凭证>"

> ⚠️ 凭证只写入本机 600 权限文件，禁止明文内联到命令行历史以外的地方，也禁止回显。

命令行
------
    python3 providers/neodata.py --status                 # 查看凭证状态
    python3 providers/neodata.py --query "贵州茅台最新财报"
    python3 providers/neodata.py --save-token "<凭证>"     # 保存/刷新凭证
"""

from __future__ import annotations

import json
import stat
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

try:  # 作为包模块导入
    from .base import DEFAULT_TIMEOUT, SEARCH_TASKS, FetchResult, SearchProvider
except ImportError:  # 直接以脚本运行
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from providers.base import (  # type: ignore
        DEFAULT_TIMEOUT, SEARCH_TASKS, FetchResult, SearchProvider,
    )

ENDPOINT = "https://copilot.tencent.com/agenttool/v1/neodata"
TOKEN_FILE = Path.home() / ".workbuddy" / ".neodata_token"
TOKEN_TTL = 12 * 3600

# Agent 侧刷新凭证的引导语（available() 不可用时打印）
_REFRESH_HINT = (
    '凭证缺失或已过期：请调用 connect_cloud_service 工具取回凭证后，执行 '
    '`python3 providers/neodata.py --save-token "<凭证>"` 刷新'
)


# ---------------------------------------------------------------- 凭证
def load_token() -> tuple[str, str]:
    """读取本地缓存凭证。返回 (token, 状态)，状态 ∈ ok/missing/expired/broken。"""
    try:
        raw = TOKEN_FILE.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return "", "missing"
    except (PermissionError, OSError):
        return "", "broken"
    if not raw:
        return "", "missing"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return "", "expired"  # 旧格式（纯文本），视为过期
    token = str(data.get("token", "")).strip()
    saved_at = data.get("saved_at", 0)
    if not token:
        return "", "missing"
    if time.time() - float(saved_at or 0) > TOKEN_TTL:
        return "", "expired"
    return token, "ok"


def save_token(token: str) -> Path:
    """把凭证写入缓存文件（600 权限）。"""
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(
        json.dumps({"token": token.strip(), "saved_at": int(time.time())}),
        encoding="utf-8",
    )
    try:
        TOKEN_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    return TOKEN_FILE


def token_status_text() -> str:
    _, st = load_token()
    return {
        "ok": "✅ 凭证有效",
        "missing": "❌ 无凭证缓存（首次使用）",
        "expired": "⚠️ 凭证已过期（超过 12 小时）",
        "broken": "❌ 凭证文件不可读",
    }.get(st, f"未知状态: {st}")


# ---------------------------------------------------------------- HTTP
def _post(query: str, data_type: str, token: str, timeout: int) -> dict:
    payload: dict = {
        "query": query,
        "channel": "neodata",
        "sub_channel": "workbuddy",
    }
    if data_type and data_type != "all":
        payload["data_type"] = data_type

    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def render(data: dict) -> str:
    """把 neodata 返回体压成可读文本（结构化块 + 文档块）。"""
    lines: list[str] = []

    entity = ((data.get("apiData") or {}).get("entity")) or []
    if entity:
        names = [f"{e.get('name', '')}({e.get('code', '')})" for e in entity if isinstance(e, dict)]
        if names:
            lines.append("【命中标的】" + "、".join(names))

    for block in ((data.get("apiData") or {}).get("apiRecall")) or []:
        if not isinstance(block, dict):
            continue
        lines.append("")
        lines.append(f"── {block.get('desc') or block.get('type') or '结构化数据'} ──")
        content = block.get("content")
        if isinstance(content, (dict, list)):
            lines.append(json.dumps(content, ensure_ascii=False, indent=2))
        elif content:
            lines.append(str(content))

    for group in ((data.get("docData") or {}).get("docRecall")) or []:
        if not isinstance(group, dict):
            continue
        docs = group.get("docList") or []
        if not docs:
            continue
        lines.append("")
        lines.append(f"── 文档召回：{group.get('extQuery', '')} ──")
        for d in docs:
            if not isinstance(d, dict):
                continue
            title = d.get("title") or d.get("docTitle") or "(无标题)"
            summary = d.get("summary") or d.get("content") or d.get("abstract") or ""
            summary = str(summary).strip().replace("\n", " ")
            if len(summary) > 600:
                summary = summary[:600] + "…"
            lines.append(f"  · {title}")
            if summary:
                lines.append(f"    {summary}")

    return "\n".join(lines).strip()


# ---------------------------------------------------------------- Provider
class NeodataProvider(SearchProvider):
    name = "neodata"
    desc = "语义检索源：WorkBuddy 平台金融数据（财报全文/主营构成/供应链/业绩会/一致预期/风险）"
    supports = set(SEARCH_TASKS)

    def available(self) -> tuple[bool, str]:
        token, st = load_token()
        if st == "ok":
            return True, "凭证有效（12 小时缓存）"
        return False, _REFRESH_HINT

    def search(self, query: str, data_type: str = "all",
               timeout: int = 90) -> FetchResult:
        token, st = load_token()
        if st != "ok":
            return FetchResult("search", False, error=f"TOKEN_{st.upper()}: {_REFRESH_HINT}")
        try:
            body = _post(query, data_type, token, timeout)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                return FetchResult("search", False,
                                   error=f"AUTH_ERROR: HTTP {e.code}，凭证失效，请刷新")
            return FetchResult("search", False, error=f"HTTP {e.code}: {e.reason}")
        except urllib.error.URLError as e:
            return FetchResult("search", False, error=f"网络错误: {e.reason}")
        except Exception as e:  # noqa: BLE001
            return FetchResult("search", False, error=f"ERROR: {e}")

        code = str(body.get("code", ""))
        if code == "40101":
            return FetchResult("search", False, error="AUTH_ERROR: 服务返回凭证校验失败，请刷新")
        if code not in ("200", "0", "") and not body.get("suc", False):
            return FetchResult("search", False,
                               error=f"接口错误 code={code} msg={body.get('msg', '')}")

        text = render(body.get("data") or {})
        if not text:
            return FetchResult("search", True, text="(无召回结果)")
        return FetchResult("search", True, text=text)


# ---------------------------------------------------------------- CLI
def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="neodata 语义检索源 / 凭证管理")
    ap.add_argument("--query", "-q", help="自然语言查询")
    ap.add_argument("--data-type", "-d", default="all", choices=["all", "api", "doc"])
    ap.add_argument("--save-token", metavar="TOKEN", help="保存/刷新凭证后退出")
    ap.add_argument("--status", action="store_true", help="查看凭证状态后退出")
    args = ap.parse_args()

    if args.save_token:
        p = save_token(args.save_token)
        print(f"✅ 凭证已保存到 {p}（有效期 12 小时）")
        return 0

    if args.status:
        print(token_status_text())
        return 0

    if not args.query:
        ap.error("需要 --query、--save-token 或 --status 之一")

    p = NeodataProvider()
    r = p.search(args.query, data_type=args.data_type)
    if not r.ok:
        print(f"❌ {r.error}", file=sys.stderr)
        return 1
    print(r.text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
