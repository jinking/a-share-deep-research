#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
研报首屏注入器 —— 给已有的 A股深度研究 HTML 报告，套上「V1 版式首屏」：
    header（kicker + 大标题 + 副标题）
    + 公司简介（蓝边浅底块，一段话讲清「这是一家什么公司」）
    + 首屏结论卡（左侧结论文字 + 右侧报告日真实行情 + 8 个 KPI）
    + 近 3 个月日 K 线卡（红涨绿跌，MA5/10/20）

只改开头，正文 0–16 章一律不动。可重复运行（带哨兵，跳过已注入）。

用法:
    python3 apply_firstscreen.py <report.html> <spec.json>   # 给报告注入/刷新首屏
    python3 apply_firstscreen.py --sync-template            # 把本文件 CSS 刷进 assets/报告模板.html
    python3 apply_firstscreen.py --check-template           # 校验模板与本文件是否脱钩（不一致退出码 1）

首屏 CSS 的**唯一来源是本文件的 CSS 常量**，assets/报告模板.html 里的同名区块是同步产物。
改完首屏样式务必 --sync-template；交付前跑 --check-template。

配色纪律：首屏只准引用宿主报告的 CSS 变量、不准硬编码色值——
蓝 var(--brand,var(--blue,…))、涨 var(--up,var(--red,…))、跌 var(--down,var(--green,…))、
字 var(--ink/--ink2/--ink3)、线 var(--line)、底 var(--bg/--card)。
两列布局用 Grid 而非 flex-wrap，否则价格块会被换行挤到左侧。

spec.json 字段:
{
  "name":"京泉华","code":"002885.SZ","industry":"其他电子Ⅱ",
  "subtitle":"磁性元器件 · 特种变压器 · 电源 ｜ … ｜ 数据截至 2026-09-14 收盘",
  "intro":"（公司简介：一段话讲清「这是一家什么公司」——成立/上市、主营与产品线、规模、行业位置、核心看点。允许用 <b></b> 加粗，其余标签会被转义）",
  "conclusion":"（一段话，取自本报告自身结论，不得杜撰）",
  "status":"观察",
  "quote":{"date":"2026-09-14","close":27.17,"chg":2.49,"mcap":73.61,
           "open":26.01,"high":27.50,"low":25.80,"amount":5.01,"turnover":7.80},
  "kpis":[{"lb":"2026H1 营业收入","vl":"19.32亿","sub":"同比 +12.10%","dir":"r"}, …],
  "source":"数据来源：…",
  "kline_dir":"/abs/path/research_sz002885",     // 内含 raw/kline.txt
  "generated_at":"2026-09-15 09:05:32"           // 可选；缺省=当前本地时间
}
dir 取值: "r"=红(涨/正), "g"=绿(跌/负), ""=中性

生成时间：副标题末尾自动追加「｜ 生成于 YYYY-MM-DD HH:MM:SS」（精确到秒）。
subtitle 里已手写「生成于 …」时不重复追加；最终以 scripts/stamp_report.py 的统一盖章为准。
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

SENTINEL = "<!-- FS-FIRSTSCREEN-INJECTED -->"

CSS_BEGIN = "/* FS-CSS:BEGIN（单一来源=本文件 CSS 常量；勿手改模板，用 --sync-template 同步） */"
CSS_END = "/* FS-CSS:END */"

CSS = """
/* ===== 首屏（ V1 版式；配色一律继承宿主报告的主题令牌，缺令牌时回退 V1 色 ） ===== */
.fs-head{margin-bottom:22px}
.fs-kicker{display:inline-block;font-size:12px;letter-spacing:.14em;font-weight:600;border-radius:4px;padding:3px 10px;
  color:var(--brand,var(--blue,#2563c9));background:#e8effb;
  background:color-mix(in srgb,var(--brand,var(--blue,#2563c9)) 12%,#fff)}
.fs-head h1{font-size:31px;margin:14px 0 6px;letter-spacing:-.4px;line-height:1.25;font-weight:700;color:var(--ink,#1a1d24)}
.fs-head h1 small{display:block;font-size:14px;font-weight:400;color:var(--ink3,#8a92a3);letter-spacing:0;margin-top:8px}
.fs-card{background:var(--card,#fff);border:1px solid var(--line,#e4e7ee);border-radius:12px;padding:20px 22px;box-shadow:0 1px 3px rgba(20,25,40,.04);margin-bottom:16px}
.fs-intro{background:#f2f7fe;background:color-mix(in srgb,var(--brand,var(--blue,#2563c9)) 6%,#fff);
  border:1px solid var(--line,#e4e7ee);border-left:4px solid var(--brand,var(--blue,#2563c9));border-radius:0 12px 12px 0;padding:14px 20px;margin-bottom:16px}
.fs-intro .fs-lb{font-size:12px;color:var(--brand,var(--blue,#2563c9));letter-spacing:.1em;font-weight:700;margin-bottom:6px}
.fs-intro p{font-size:15px;color:var(--ink2,#4a5160);margin:0;line-height:1.8;max-width:880px}
.fs-intro b{color:var(--ink,#1a1d24)}
/* 结论 + 行情：两列网格（不是 flex-wrap）——价格块恒钉右侧，永不换行；窄屏才转单列 */
.fs-top{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:20px;align-items:start}
.fs-concl{min-width:0}
.fs-lbl{font-size:12px;color:var(--ink3,#8a92a3);letter-spacing:.1em;font-weight:600}
.fs-concl p{font-size:15.5px;color:var(--ink2,#4a5160);margin:8px 0 0;max-width:760px;line-height:1.75}
.fs-pill{display:inline-block;font-size:12px;font-weight:700;border-radius:20px;padding:2px 10px;margin-left:6px;vertical-align:middle;
  color:var(--brand,var(--blue,#2563c9));background:#e8effb;
  background:color-mix(in srgb,var(--brand,var(--blue,#2563c9)) 12%,#fff)}
.fs-quote{text-align:right;justify-self:end;min-width:200px}
.fs-lbl2{font-size:12px;color:var(--ink3,#8a92a3)}
.fs-big{font-size:26px;font-weight:700;letter-spacing:-.6px;color:var(--ink,#1a1d24)}
.fs-big span{font-size:15px}
.fs-big.r{color:var(--up,var(--red,#d5342b))}
.fs-big.g{color:var(--down,var(--green,#1f9c62))}
.fs-chg{font-size:12px;font-weight:700;color:var(--ink2,#4a5160)}
.fs-chg.r{color:var(--up,var(--red,#d5342b))}
.fs-chg.g{color:var(--down,var(--green,#1f9c62))}
.fs-mc{font-size:12px;color:var(--ink3,#8a92a3);margin-top:6px}
.fs-ohlc{font-size:11.5px;color:var(--ink3,#8a92a3);margin-top:4px}
.fs-kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin-top:18px}
.fs-kpi{min-width:0;border:1px solid var(--line,#e4e7ee);border-radius:10px;padding:14px 16px;background:var(--card,#fff)}
.fs-kpi .lb{font-size:12px;color:var(--ink3,#8a92a3);margin-bottom:4px}
.fs-kpi .vl{font-size:22px;font-weight:700;letter-spacing:-.5px;color:var(--ink,#1a1d24);font-variant-numeric:tabular-nums}
.fs-kpi .vl.r{color:var(--up,var(--red,#d5342b))}
.fs-kpi .vl.g{color:var(--down,var(--green,#1f9c62))}
.fs-kpi .sub{font-size:12px;color:var(--ink3,#8a92a3);margin-top:3px}
.fs-kpi .sub.r{color:var(--up,var(--red,#d5342b))}
.fs-kpi .sub.g{color:var(--down,var(--green,#1f9c62))}
.fs-src{font-size:11.5px;color:var(--ink3,#8a92a3);margin-top:12px}
.fs-chart{width:100%;height:340px}
@media(max-width:860px){
  .fs-top{grid-template-columns:1fr;gap:14px}
  .fs-quote{text-align:left;justify-self:start}
  .fs-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}
}
@media(max-width:560px){.fs-kpis{grid-template-columns:1fr}}
"""

CSS_BLOCK = "\n" + CSS_BEGIN + "\n" + CSS + CSS_END + "\n"


def parse_kline(text):
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        c = [x.strip() for x in line.strip("|").split("|")]
        if len(c) < 6 or not re.match(r"^\d{4}-\d{2}-\d{2}$", c[0]):
            continue
        try:
            rows.append((c[0], float(c[1]), float(c[2]), float(c[3]), float(c[4]), int(float(c[5]))))
        except ValueError:
            continue
    rows.sort(key=lambda r: r[0])
    return rows


def esc(x):
    """最小 HTML 转义，防止 <5% 之类被解析成标签。"""
    return str(x).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def n2(x):
    """统一保留两位小数，避免 27.50 被显示成 27.5。"""
    return "%.2f" % float(x)


def rich(x):
    """先全量转义，再放行 <b>/</b> 两个标签——简介需要加粗，但不能引入任意 HTML。"""
    return esc(x).replace("&lt;b&gt;", "<b>").replace("&lt;/b&gt;", "</b>")


def gen_stamp(spec):
    """生成时间戳：精确到秒，缺省取当前本地时间。"""
    return spec.get("generated_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def build_firstscreen(spec):
    q = spec["quote"]
    chg_cls = "r" if q["chg"] >= 0 else "g"
    subtitle = spec.get("subtitle", "")
    if "生成于" not in subtitle:
        subtitle = subtitle.rstrip() + " ｜ 生成于 " + gen_stamp(spec)
    kpis = "".join(
        '<div class="fs-kpi"><div class="lb">%s</div><div class="vl %s">%s</div><div class="sub %s">%s</div></div>'
        % (esc(k["lb"]), k.get("dir", ""), esc(k["vl"]), k.get("dir", ""), esc(k["sub"]))
        for k in spec["kpis"]
    )
    intro_block = ""
    if spec.get("intro"):
        intro_block = """
<!-- 公司简介：一段话讲清「这是一家什么公司」 -->
<div class="fs-intro">
  <div class="fs-lb">— 公司简介 —</div>
  <p>%s</p>
</div>
""" % rich(spec["intro"])
    return """%(sent)s
<header class="fs-head">
  <span class="fs-kicker">个股深度研究 · %(industry)s</span>
  <h1>%(name)s（%(code)s）
    <small>%(subtitle)s</small>
  </h1>
</header>
%(intro)s
<!-- 首屏结论（报告日真实行情 + 关键指标） -->
<div class="fs-card">
  <div class="fs-top">
    <div class="fs-concl">
      <div class="fs-lbl">— 核心结论 —</div>
      <p>%(concl)s<span class="fs-pill">研究状态：%(status)s</span></p>
    </div>
    <div class="fs-quote">
      <div class="fs-lbl2">最新收盘价（报告日）</div>
      <div class="fs-big %(chgcls)s">%(close)s<span>元</span></div>
      <div class="fs-chg %(chgcls)s">%(chg)s%%（%(date)s）</div>
      <div class="fs-mc">总市值 %(mcap)s 亿元</div>
      <div class="fs-ohlc">开 %(open)s ｜ 高 %(high)s ｜ 低 %(low)s ｜ 额 %(amount)s 亿 ｜ 换手 %(turnover)s%%</div>
    </div>
  </div>
  <div class="fs-kpis">%(kpis)s</div>
  <div class="fs-src">%(source)s</div>
</div>

<!-- 近 3 个月日 K 线 -->
<div class="fs-card">
  <h3 style="margin:0 0 6px;font-size:15px;color:var(--ink,#1a1d24);">近 3 个月日 K 线（截至 %(date)s）</h3>
  <div class="fs-chart" id="fsKline"></div>
  <div class="fs-src">来源：westock-data 日 K 线（近 %(nbar)d 个交易日，raw/kline.txt）；MA5/MA10/MA20 自算。A 股口径红涨绿跌。</div>
</div>
""" % {
        "sent": SENTINEL,
        "industry": spec.get("industry", ""),
        "name": spec["name"], "code": spec["code"], "subtitle": subtitle,
        "intro": intro_block,
        "concl": esc(spec["conclusion"]), "status": esc(spec.get("status", "观察")),
        "chgcls": chg_cls,
        "close": n2(q["close"]), "chg": ("%+.2f" % q["chg"]), "date": esc(q["date"]),
        "mcap": n2(q["mcap"]), "open": n2(q["open"]), "high": n2(q["high"]), "low": n2(q["low"]),
        "amount": n2(q["amount"]), "turnover": n2(q["turnover"]),
        "kpis": kpis, "source": esc(spec.get("source", "")), "nbar": spec.get("nbar", 60),
    }


def build_script(spec, rows):
    kd = "[" + ",".join("'%s'" % r[0] for r in rows) + "]"
    kr = "[" + ",".join("[%.2f,%.2f,%.2f,%.2f,%d]" % (r[1], r[2], r[4], r[3], r[5]) for r in rows) + "]"
    first, last = rows[0], rows[-1]
    chg = (last[2] / first[1] - 1) * 100
    return """
<script>
/* 首屏：近 3 个月日 K 线（数据来自 %(dir)s/raw/kline.txt，%(n)d 个交易日 %(a)s ~ %(b)s，区间 %(c)+.2f%%） */
var fsDates=%(kd)s;
var fsRaw=%(kr)s;  /* [开,收,低,高,量] */
/* 图表配色同步读取宿主报告的主题令牌，缺令牌时回退 V1 色——避免"图一套色、正文一套色" */
function fsVar(n){try{var v=getComputedStyle(document.documentElement).getPropertyValue(n);return (v||'').trim();}catch(e){return '';}}
function fsPick(ns,fb){for(var i=0;i<ns.length;i++){var v=fsVar(ns[i]);if(v)return v;}return fb;}
var fsInk2=fsPick(['--ink2'],'#4a5160'), fsInk3=fsPick(['--ink3'],'#8a92a3'), fsLine=fsPick(['--line'],'#e4e7ee');
var fsRed=fsPick(['--up','--red'],'#d5342b'), fsGreen=fsPick(['--down','--green'],'#1f9c62');
var fsBlue=fsPick(['--brand','--blue'],'#2563c9'), fsAmber=fsPick(['--amber','--gold'],'#c8871a'), fsPurple=fsPick(['--purple'],'#6b4fc4');
(function(){
  var el=document.getElementById('fsKline'); if(!el||!window.echarts) return;
  var ohlc=fsRaw.map(function(r){return [r[0],r[1],r[2],r[3]];});
  var vol=fsRaw.map(function(r){return r[4];});
  function ma(n){var a=[];for(var i=0;i<fsRaw.length;i++){if(i<n-1){a.push('-');continue;}var s=0;for(var j=0;j<n;j++){s+=fsRaw[i-j][1];}a.push(+(s/n).toFixed(2));}return a;}
  var ch=echarts.init(el);
  ch.setOption({
    tooltip:{trigger:'axis',axisPointer:{type:'cross'}},
    legend:{data:['日K','MA5','MA10','MA20'],textStyle:{color:fsInk2},itemWidth:10,itemHeight:10},
    axisPointer:{link:[{xAxisIndex:'all'}]},
    grid:[{left:56,right:20,top:46,height:194},{left:56,right:20,top:264,height:56}],
    xAxis:[
      {type:'category',data:fsDates,gridIndex:0,boundaryGap:false,axisLine:{lineStyle:{color:fsLine}},axisLabel:{show:false},axisTick:{show:false}},
      {type:'category',data:fsDates,gridIndex:1,boundaryGap:false,axisLine:{lineStyle:{color:fsLine}},axisLabel:{color:fsInk2}}
    ],
    yAxis:[
      {scale:true,gridIndex:0,name:'价格(元)',nameTextStyle:{color:fsInk3},axisLabel:{color:fsInk2},splitLine:{lineStyle:{color:fsLine}}},
      {gridIndex:1,name:'量(手)',nameTextStyle:{color:fsInk3},axisLabel:{show:false},splitLine:{show:false},axisLine:{show:false},axisTick:{show:false}}
    ],
    dataZoom:[{type:'inside',xAxisIndex:[0,1],start:0,end:100}],
    series:[
      {name:'日K',type:'candlestick',xAxisIndex:0,yAxisIndex:0,data:ohlc,
        itemStyle:{color:fsRed,color0:fsGreen,borderColor:fsRed,borderColor0:fsGreen}},
      {name:'MA5',type:'line',xAxisIndex:0,yAxisIndex:0,data:ma(5),smooth:true,symbol:'none',lineStyle:{width:1.3,color:fsAmber}},
      {name:'MA10',type:'line',xAxisIndex:0,yAxisIndex:0,data:ma(10),smooth:true,symbol:'none',lineStyle:{width:1.3,color:fsBlue}},
      {name:'MA20',type:'line',xAxisIndex:0,yAxisIndex:0,data:ma(20),smooth:true,symbol:'none',lineStyle:{width:1.3,color:fsPurple}},
      {name:'成交量',type:'bar',xAxisIndex:1,yAxisIndex:1,data:vol,
        itemStyle:{color:function(p){return fsRaw[p.dataIndex][1]>=fsRaw[p.dataIndex][0]?fsRed:fsGreen;}}}
    ]
  });
  window.addEventListener('resize',function(){ch.resize();});
})();
</script>
""" % {"dir": spec.get("kline_dir", ""), "kd": kd, "kr": kr,
       "n": len(rows), "a": first[0], "b": last[0], "c": chg}


TEMPLATE = Path(__file__).resolve().parent.parent / "assets" / "报告模板.html"


def _replace_block(text, block):
    """把 text 里 FS-CSS 标记区间替换为 block；无标记则插到 </style> 前。"""
    a = text.find(CSS_BEGIN)
    b = text.find(CSS_END, a + 1) if a >= 0 else -1
    if a >= 0 and b > a:
        return text[:a] + block.lstrip("\n") + text[b + len(CSS_END):], "替换标记区间"
    if "</style>" not in text:
        sys.exit("❌ 模板里既没有 FS-CSS 标记，也没有 </style>")
    return text.replace("</style>", block + "</style>", 1), "插入 </style> 前"


def sync_template(quiet=False):
    """把本文件的 CSS 常量刷进 assets/报告模板.html —— 保证模板与生成器永不脱钩。"""
    if not TEMPLATE.exists():
        sys.exit("❌ 未找到模板：%s" % TEMPLATE)
    t = TEMPLATE.read_text(encoding="utf-8")
    out, how = _replace_block(t, CSS_BLOCK)
    changed = out != t
    if changed:
        TEMPLATE.write_text(out, encoding="utf-8")
    if not quiet:
        print("✅ 模板首屏 CSS 已同步（%s，%s）" % (how, "有改动" if changed else "无改动"))
    return changed


def check_template():
    """校验模板首屏 CSS 与本文件是否一致；不一致则退出码 1。"""
    t = TEMPLATE.read_text(encoding="utf-8")
    a = t.find(CSS_BEGIN)
    b = t.find(CSS_END, a + 1) if a >= 0 else -1
    if a < 0 or b <= a:
        print("❌ 模板缺少 FS-CSS 标记区间")
        return False
    cur = t[a + len(CSS_BEGIN):b]
    if cur.strip() == CSS.strip():
        print("✅ 模板首屏 CSS 与生成器一致")
        return True
    print("❌ 模板首屏 CSS 与生成器不一致——跑 --sync-template 同步")
    return False


def main():
    args = sys.argv[1:]
    if args and args[0] == "--sync-template":
        sync_template()
        return
    if args and args[0] == "--check-template":
        sys.exit(0 if check_template() else 1)
    if len(args) < 2:
        sys.exit(__doc__)
    html_path = Path(args[0])
    spec = json.loads(Path(args[1]).read_text(encoding="utf-8"))
    html = html_path.read_text(encoding="utf-8")

    if SENTINEL in html:
        sys.exit("⚠️ 已注入过首屏（发现哨兵），未改动。")

    rows = parse_kline((Path(spec["kline_dir"]) / "raw" / "kline.txt").read_text(encoding="utf-8"))
    spec["nbar"] = len(rows)
    fs_html = build_firstscreen(spec)
    script = build_script(spec, rows)

    # 1) CSS 注入
    if "</style>" not in html:
        sys.exit("❌ 未找到 </style>")
    html = html.replace("</style>", CSS_BLOCK + "</style>", 1)

    # 1.5) 可选：删除已有的「旧首屏结论块」（标记区间左闭右开）
    rb = spec.get("remove_block")
    if rb and len(rb) == 2:
        a = html.find(rb[0])
        b = html.find(rb[1], a + 1) if a >= 0 else -1
        if a >= 0 and b > a:
            html = html[:a] + html[b:]
            print("   · 已移除旧结论块（%d 字符）" % (b - a))
        else:
            print("   · ⚠️ remove_block 标记未匹配，跳过")

    # 2) 删掉原有的第一个 <header>…</header>，插入新首屏
    m = re.search(r"\n?<header[\s>].*?</header>\s*", html, re.S)
    if m:
        html = html[:m.start()] + "\n" + fs_html + "\n" + html[m.end():]
    else:
        anchor = '<div class="wrap">'
        i = html.find(anchor)
        if i < 0:
            sys.exit("❌ 未找到 <div class=\"wrap\">")
        i += len(anchor)
        html = html[:i] + "\n" + fs_html + "\n" + html[i:]

    # 3) K 线脚本
    if "</body>" not in html:
        sys.exit("❌ 未找到 </body>")
    html = html.replace("</body>", script + "</body>", 1)

    html_path.write_text(html, encoding="utf-8")
    print("✅ 已注入首屏 → %s（K线 %d 个交易日）" % (html_path, len(rows)))
    print("   ⏱  交付前跑 scripts/stamp_report.py %s 统一盖生成时间戳（精确到秒）" % html_path.name)


if __name__ == "__main__":
    main()
