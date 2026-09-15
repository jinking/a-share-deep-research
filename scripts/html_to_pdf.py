#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HTML 研报 → PDF 导出器（可选交付格式，非默认）。

**为什么不用 weasyprint/wkhtmltopdf**：本技能的图表（日 K、饼图、双轴柱线）全部由
ECharts 在浏览器里运行时渲染成 canvas，纯 CSS 排版引擎拿不到这些图，导出来是空框。
所以必须走**无头浏览器**（Chrome/Edge 优先，Playwright 兜底）。

引擎选择（--engine auto 默认，按可靠性自动降级）：
  1. shell      ：Playwright 缓存里的 `chrome-headless-shell`——**纯无头二进制，无 GUI 外壳**，
                  最可靠。Chrome.app 的无头模式仍挂在 GUI 应用外壳上，在无 GUI 会话的
                  进程上下文（自动化/agent shell）里会卡死在启动阶段；此二进制不受影响。
  2. chrome     ：本机 Google Chrome / Microsoft Edge 无头打印（有 GUI 会话时可用）
  3. playwright ：若已装 playwright（Python 版），用它（可等图表就绪，最稳但需依赖）

转换行为：
  · 按需注入**打印样式**（@page 尺寸/页边距 + 卡片图表防跨页断裂），
    只写进临时副本，**绝不改动源 HTML**；若源文件已有 @media print，仅追加 @page 覆盖。
  · 关闭页眉页脚（URL/日期），开启背景色（保住深浅底色与红涨绿跌）。
  · 转换后校验页数与内嵌图像数；若页面引用了 ECharts CDN 但产不出图，给出显式告警。

用法:
    python3 html_to_pdf.py <report.html>                       # 同名 .pdf（A4 竖版）
    python3 html_to_pdf.py <report.html> --out out.pdf
    python3 html_to_pdf.py <report.html> --engine playwright
    python3 html_to_pdf.py <report.html> --format A3 --landscape
    python3 html_to_pdf.py <report.html> --margin "14mm 12mm" --header-footer

退出码: 正常 0；找不到可用引擎 / 转换失败 1；参数错误 2。

⚠️ 前提：报告首页的 ECharts 走 CDN（cdn.jsdelivr.net），转换时**需联网**，
   否则图表为空。离线场景请先把 echarts.min.js 下载到本地并改报告引用路径。
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# ----------------------------------------------------------------------------
# 引擎探测
# ----------------------------------------------------------------------------
CHROME_CANDIDATES = {
    "darwin": [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    ],
    "linux": [
        "/usr/bin/google-chrome", "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium", "/usr/bin/chromium-browser",
        "/usr/bin/microsoft-edge", "/usr/bin/microsoft-edge-stable",
        "/snap/bin/chromium",
    ],
    "win32": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ],
}
CHROME_PATH_ENV = ("GOOGLE_CHROME_SHIM", "CHROME_PATH", "CHROMIUM_PATH")


def find_chrome():
    """返回本机 Chrome/Edge 可执行文件路径，找不到返回 None。"""
    for env in CHROME_PATH_ENV:
        v = os.environ.get(env)
        if v and Path(v).exists():
            return v
    for name in ("google-chrome", "google-chrome-stable", "chromium",
                 "chromium-browser", "microsoft-edge", "microsoft-edge-stable"):
        p = shutil.which(name)
        if p:
            return p
    for cand in CHROME_CANDIDATES.get(sys.platform, []):
        if Path(cand).exists():
            return cand
    return None


def find_headless_shell():
    """查找 Playwright 缓存里的 chrome-headless-shell（纯无头二进制，无 GUI 外壳）。

    这是本机最可靠的引擎：Chrome.app 的无头模式仍挂在 GUI 应用外壳上，
    在某些进程上下文（如自动化/无 GUI 会话）里会卡死在启动阶段；
    chrome-headless-shell 专为无头编译，不受此影响。
    """
    import glob
    pats = [
        # macOS
        "~/Library/Caches/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-mac-*/chrome-headless-shell",
        # Linux
        "~/.cache/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell",
        # Windows
        "~/AppData/Local/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-win64/chrome-headless-shell.exe",
    ]
    found = []
    for p in pats:
        found += glob.glob(os.path.expanduser(p))
    if not found:
        return None

    def ver(path):
        m = re.search(r"chromium_headless_shell-(\d+)", path)
        return int(m.group(1)) if m else 0

    return sorted(found, key=ver)[-1]


def has_playwright():
    try:
        import playwright.sync_api  # noqa: F401
        return True
    except Exception:
        return False


# ----------------------------------------------------------------------------
# 打印样式注入（只进临时副本）
# ----------------------------------------------------------------------------
PAGE_MARK = "__pdf_export_print__"

BREAK_CSS = """
  /* ===== 打印 / 导出 PDF（自动注入） ===== */
  @media print{
    body{background:#fff;}
    /* 只对「小而原子」的块防断裂（图表/表格行/图片/KPI 小格）。
       注意：不要给 .card / .fs-card 这类可能高于一页的大容器加 break-inside:avoid，
       否则整卡被推到下一页，前一页会大片留白。 */
    .chart-wrap,.chart,figure,img,tr,.fs-kpi,pre,blockquote{break-inside:avoid;page-break-inside:avoid;}
    /* 标题不与后继内容分离 */
    h1,h2,h3,h4{break-after:avoid;page-break-after:avoid;}
    a{color:inherit;text-decoration:none;}
  }
"""


def build_print_css(fmt, landscape, margin, with_breaks):
    orientation = "landscape" if landscape else "portrait"
    css = "\n<style>/* %s */\n  @page{size:%s %s;margin:%s;}\n%s</style>\n" % (
        PAGE_MARK, fmt, orientation, margin, BREAK_CSS if with_breaks else "")
    return css


def inject_print_css(html_text, fmt, landscape, margin):
    """在 <head> 末尾（或 </body> 前）注入打印样式；已有 @media print 就只加 @page 覆盖。"""
    with_breaks = "@media print" not in html_text and "@media  print" not in html_text
    block = build_print_css(fmt, landscape, margin, with_breaks)
    for anchor in ("</head>", "</body>", "</html>"):
        i = html_text.lower().rfind(anchor)
        if i != -1:
            return html_text[:i] + block + html_text[i:], with_breaks
    return html_text + block, with_breaks


# ----------------------------------------------------------------------------
# 转换后端
# ----------------------------------------------------------------------------
def convert_chrome(chrome, url, out_pdf, vtb, timeout, header_footer=False, no_sandbox=False,
                   headless_flag="--headless=new"):
    with tempfile.TemporaryDirectory(prefix="html2pdf_profile_") as profile:
        cmd = [
            chrome,
            headless_flag,
            "--disable-gpu",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-extensions",
            "--disable-background-networking",
            "--run-all-compositor-stages-before-draw",
            "--virtual-time-budget=%d" % vtb,
            "--user-data-dir=%s" % profile,
            "--print-to-pdf=%s" % out_pdf,
        ]
        if no_sandbox:
            # macOS 上若外层已有沙箱（如 agent 沙箱），Chrome 自身的 Seatbelt 会
            # 初始化失败（sandbox initialization failed: Operation not permitted），
            # 导致 GPU/渲染进程起不来、整个进程 FATAL 退出。此时需要关掉 Chrome 内层沙箱。
            cmd.insert(2, "--no-sandbox")
        if not header_footer:
            cmd.append("--no-pdf-header-footer")
        cmd.append(url)
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=timeout)
    return proc


def parse_margin(s):
    """CSS margin 简写 → {top,right,bottom,left}（1/2/3/4 值）。"""
    parts = (s or "12mm 10mm 14mm 10mm").split()
    if len(parts) == 1:
        t = r = b = l = parts[0]
    elif len(parts) == 2:
        t = b = parts[0]; r = l = parts[1]
    elif len(parts) == 3:
        t = parts[0]; r = l = parts[1]; b = parts[2]
    else:
        t, r, b, l = parts[:4]
    return {"top": t, "right": r, "bottom": b, "left": l}


def convert_playwright(url, out_pdf, fmt, landscape, margin, timeout, header_footer=False):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.emulate_media(media="print")
        page.goto(url, wait_until="networkidle", timeout=timeout * 1000)
        # 让 ECharts 画完（网络空闲后再宽限一点）
        page.wait_for_timeout(1200)
        page.evaluate(
            "() => { if (window.echarts) { document.querySelectorAll('div').forEach(function(d){"
            " try { var i = window.echarts.getInstanceByDom(d); if (i) i.resize(); } catch (e) {} }); } }"
        )
        page.wait_for_timeout(400)
        page.pdf(path=out_pdf, format=fmt, landscape=landscape,
                 print_background=True, display_header_footer=header_footer,
                 margin=parse_margin(margin))
        browser.close()


# ----------------------------------------------------------------------------
# 结果校验
# ----------------------------------------------------------------------------
def pdf_stats(pdf_path):
    data = Path(pdf_path).read_bytes()
    pages = len(re.findall(rb"/Type\s*/Page[^s]", data))
    images = len(re.findall(rb"/Subtype\s*/Image", data))
    return pages, images, len(data)


def main():
    ap = argparse.ArgumentParser(add_help=True,
                                 description="把 A股深度研究 HTML 研报导出为 PDF（无头浏览器）")
    ap.add_argument("report", help="报告 HTML 路径")
    ap.add_argument("--out", default=None, help="输出 PDF 路径（缺省=与 HTML 同目录同名）")
    ap.add_argument("--engine", choices=["auto", "shell", "chrome", "playwright"], default="auto",
                    help="转换引擎；auto=按可靠性降级（shell→chrome→playwright）")
    ap.add_argument("--format", default="A4", help="纸张：A4/A3/A5/Letter（默认 A4）")
    ap.add_argument("--landscape", action="store_true", help="横向")
    ap.add_argument("--margin", default="12mm 10mm 14mm 10mm",
                    help="页边距，CSS 语法（默认 12mm 10mm 14mm 10mm）")
    ap.add_argument("--header-footer", action="store_true",
                    help="保留页眉页脚（URL/日期/页码）；默认关闭")
    ap.add_argument("--virtual-time-budget", type=int, default=15000,
                    help="Chrome 虚拟时间预算毫秒（默认 15000，等图表渲染）")
    ap.add_argument("--timeout", type=int, default=120, help="整体超时秒数（默认 120）")
    ap.add_argument("--chrome", default=None, help="手动指定 Chrome/Edge 可执行路径")
    ap.add_argument("--chrome-no-sandbox", action="store_true",
                    help="给 Chrome 加 --no-sandbox（外层已有沙箱时必须，见下方说明）")
    ap.add_argument("--quiet", action="store_true", help="精简输出")
    args = ap.parse_args()

    src = Path(args.report)
    if not src.exists():
        sys.exit("❌ 未找到 HTML：%s" % src)
    if src.suffix.lower() not in (".html", ".htm"):
        sys.exit("❌ 输入必须是 .html/.htm：%s" % src)

    out = Path(args.out) if args.out else src.with_suffix(".pdf")
    out.parent.mkdir(parents=True, exist_ok=True)

    # --- 引擎决议（auto = 按可靠性排序，失败自动降级）---
    shell_bin = find_headless_shell()
    chrome = args.chrome or find_chrome()
    if args.engine == "auto":
        cands = []
        if shell_bin:
            cands.append(("shell", shell_bin))
        if chrome:
            cands.append(("chrome", chrome))
        if has_playwright():
            cands.append(("playwright", None))
    else:
        cands = {"shell": [("shell", shell_bin)],
                 "chrome": [("chrome", chrome)],
                 "playwright": [("playwright", None)]}[args.engine]
        if cands[0][0] != "playwright" and not cands[0][1]:
            sys.exit("❌ 指定引擎不可用：%s。可用 --engine chrome/playwright，或用 --chrome <路径> 指定。"
                     % args.engine)
    if not cands:
        sys.exit("❌ 无可用转换引擎：本机既无 chrome-headless-shell，也无 Chrome/Edge，也未装 playwright。")

    # --- 注入打印样式到临时副本（不动源文件）---
    original = src.read_text(encoding="utf-8")
    patched, injected_breaks = inject_print_css(original, args.format, args.landscape, args.margin)

    tmp_dir = tempfile.mkdtemp(prefix="html2pdf_")
    tmp_html = Path(tmp_dir) / src.name
    tmp_html.write_text(patched, encoding="utf-8")
    url = tmp_html.as_uri()

    if not args.quiet:
        print("🖨  导出 PDF：%s" % src.name)
        print("   · 候选引擎  : %s" % " → ".join(e for e, _ in cands))
        print("   · 纸张/方向 : %s %s" % (args.format, "横向" if args.landscape else "纵向"))
        print("   · 打印样式  : %s" % ("注入 @page + 防断裂规则" if injected_breaks
                                       else "源文件已有 @media print，仅追加 @page 覆盖"))

    def _sandbox_denied(proc):
        if proc is None or not proc.stderr:
            return False
        s = proc.stderr.decode("utf-8", "ignore")
        return "sandbox initialization failed" in s or "Failed to initialize sandbox" in s

    HEADLESS_FLAG = {"shell": "--headless", "chrome": "--headless=new"}
    used, last_err, proc = None, "", None
    try:
        for idx, (eng, exe) in enumerate(cands):
            if idx and not args.quiet:
                print("   · %s 未成功（%s），降级重试…" % (cands[idx - 1][0], last_err or "无产出"))
            try:
                if eng == "playwright":
                    convert_playwright(url, str(out), args.format, args.landscape,
                                       args.margin, args.timeout,
                                       header_footer=args.header_footer)
                    proc = None
                else:
                    proc = convert_chrome(exe, url, str(out), args.virtual_time_budget,
                                          args.timeout, header_footer=args.header_footer,
                                          no_sandbox=args.chrome_no_sandbox,
                                          headless_flag=HEADLESS_FLAG[eng])
                    if (not out.exists() or out.stat().st_size < 1024) \
                            and not args.chrome_no_sandbox and _sandbox_denied(proc):
                        if not args.quiet:
                            print("   · 检测到内层沙箱初始化失败，自动加 --no-sandbox 重试…")
                        proc = convert_chrome(exe, url, str(out), args.virtual_time_budget,
                                              args.timeout, header_footer=args.header_footer,
                                              no_sandbox=True, headless_flag=HEADLESS_FLAG[eng])
            except subprocess.TimeoutExpired:
                last_err = "超时(%ds)" % args.timeout
                continue
            except Exception as e:
                last_err = str(e)
                continue
            if out.exists() and out.stat().st_size >= 1024:
                used = eng
                break
            last_err = "未产出有效 PDF"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    if not (out.exists() and out.stat().st_size >= 1024):
        err = ""
        if proc is not None and proc.stderr:
            err = "\n   ".join(proc.stderr.decode("utf-8", "ignore").strip().splitlines()[-3:])
        sys.exit("❌ 所有引擎均失败（最后错误：%s）。%s" % (last_err or "无产出",
                                                     ("\n   " + err) if err else ""))

    pages, images, size = pdf_stats(out)

    # --- 图表缺失告警 ---
    warn = ""
    if ("echarts" in original) and images == 0:
        warn = ("\n   ⚠️  报告引用了 ECharts 但 PDF 内无嵌入图像——图表可能未渲染。"
                "\n      常见原因：转换时无网络（CDN 拉不到 echarts.min.js）。")

    if not args.quiet:
        print("   · 实际引擎  : %s" % used)
        print("   · 页数      : %d 页" % pages)
        print("   · 内嵌图像  : %d 个" % images)
        print("   · 体积      : %.2f MB" % (size / 1024 / 1024))
        print("✅ 已输出  : %s%s" % (out, warn))
    else:
        print("%s  (%s, %d 页, %.2f MB)%s" % (out, used, pages, size / 1024 / 1024, warn))


if __name__ == "__main__":
    main()
