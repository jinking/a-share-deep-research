#!/usr/bin/env bash
# 安装 westock Go CLI（腾讯官方自选股数据 CLI）到本技能私有目录。
#
# 与官方 setup.sh 的区别：本脚本**只装到技能私有目录**，不改动系统 PATH、
# 不需要 sudo，避免污染用户环境；卸载即删目录。
#
# 用法:
#   bash scripts/install_westock_cli.sh              # 安装到 <skill_root>/tools/bin
#   bash scripts/install_westock_cli.sh -v v0.0.4    # 指定版本
#   bash scripts/install_westock_cli.sh -n           # 只预览不安装
#
# 安装后 providers/westock_cli.py 会自动探测到该私有二进制。
# 若系统 PATH 中已有 westock，provider 优先使用系统版本。

set -uo pipefail

BASE="${WESTOCK_CLI_BASE:-https://stockbuddy.qq.com/release/workbuddy/cli}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
INSTALL_DIR="$SKILL_ROOT/tools/bin"

VERSION=""
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    -v|--version) VERSION="$2"; shift 2 ;;
    -b|--base)    BASE="$2"; shift 2 ;;
    -d|--dir)     INSTALL_DIR="$2"; shift 2 ;;
    -n|--dry-run) DRY_RUN=1; shift ;;
    -h|--help)    sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "未知参数: $1" >&2; exit 1 ;;
  esac
done

log()  { printf '%s\n' "$*"; }
err()  { printf '%s\n' "$*" >&2; }

# ---- 平台检测 ----
OS="$(uname -s | tr '[:upper:]' '[:lower:]')"
ARCH="$(uname -m)"
case "$ARCH" in
  x86_64|amd64) ARCH="amd64" ;;
  aarch64|arm64) ARCH="arm64" ;;
  *) err "不支持的架构: $ARCH"; exit 1 ;;
esac
case "$OS" in
  darwin|linux) ;;
  *) err "不支持的系统: $OS（Windows 请用官方 setup.ps1）"; exit 1 ;;
esac
ARTIFACT="westock-${OS}-${ARCH}"

# ---- 版本解析 ----
if [[ -z "$VERSION" ]]; then
  log "→ 读取发布版本 latest.txt ..."
  VERSION="$(curl -fsSL "$BASE/latest.txt" 2>/dev/null | tr -d '[:space:]')" || {
    err "无法获取 $BASE/latest.txt（网络不可达？）"; exit 1; }
fi
[[ "$VERSION" == v* ]] || VERSION="v$VERSION"
log "  版本: $VERSION"
log "  平台: $ARTIFACT"

BIN_URL="$BASE/$VERSION/$ARTIFACT"
SHA_URL="$BASE/$VERSION/SHA256.txt"
DEST="$INSTALL_DIR/westock"

log "  来源: $BIN_URL"
log "  目标: $DEST"

if [[ "$DRY_RUN" -eq 1 ]]; then
  log "(dry-run) 未做任何改动"; exit 0
fi

TMP_BIN="$(mktemp)"
TMP_SHA="$(mktemp)"
trap 'rm -f "$TMP_BIN" "$TMP_SHA"' EXIT

log "→ 下载二进制 ..."
if ! curl -fsSL "$BIN_URL" -o "$TMP_BIN"; then
  err "下载失败: $BIN_URL"; exit 1
fi

# ---- SHA256 校验（尽量做，无工具时告警不阻断）----
EXPECTED=""
if curl -fsSL "$SHA_URL" -o "$TMP_SHA" 2>/dev/null; then
  EXPECTED="$(awk -v a="$ARTIFACT" '$2 == a { print $1; exit }' "$TMP_SHA")"
fi

if [[ -n "$EXPECTED" ]]; then
  if command -v shasum >/dev/null 2>&1; then
    ACTUAL="$(shasum -a 256 "$TMP_BIN" | awk '{print $1}')"
  elif command -v sha256sum >/dev/null 2>&1; then
    ACTUAL="$(sha256sum "$TMP_BIN" | awk '{print $1}')"
  else
    ACTUAL=""
  fi
  if [[ -z "$ACTUAL" ]]; then
    log "  ⚠️ 无 shasum/sha256sum，跳过校验"
  elif [[ "$(printf '%s' "$ACTUAL" | tr 'A-Z' 'a-z')" != "$(printf '%s' "$EXPECTED" | tr 'A-Z' 'a-z')" ]]; then
    err "SHA256 校验失败（疑似下载损坏或被篡改），拒绝安装"
    err "  期望: $EXPECTED"
    err "  实际: $ACTUAL"
    exit 1
  else
    log "  ✅ SHA256 校验通过"
  fi
else
  log "  ⚠️ 未获取到 SHA256.txt，跳过校验"
fi

# ---- 安装 ----
mkdir -p "$INSTALL_DIR"
chmod +x "$TMP_BIN"
mv "$TMP_BIN" "$DEST"

log "✅ 已安装 → $DEST"
log ""
log "验证: $DEST --help"
log "后续 providers/westock_cli.py 会自动探测该路径，无需配置 PATH。"
