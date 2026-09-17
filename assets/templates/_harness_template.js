#!/usr/bin/env node
/**
 * harness 模板 —— 报告内联 JS 的 DOM/echarts 桩冒烟测试。
 *
 * 用法：
 *   1. 从报告抽出内联 JS：python3 -c "..."（见 SKILL.md）写入 /tmp/_js<code>.js
 *   2. 复制本文件为 /tmp/_harness<code>.js，改 CONFIG 里的期望值
 *   3. node /tmp/_harness<code>.js
 *
 * 断言：setOption 调用次数 = 图表数；各图 series 数据点数与注入数据一致。
 * 教训：已两次踩到内联 JS 语法错（注入 hex 没加引号、行数组多一层 [），
 * 整块 script 挂掉 → 图全白，而 validate_report PASS ≠ 图表能画。
 */

const CONFIG = {
  jsFile: "/tmp/_js930.js",       // TODO
  expectSetOption: 3,             // 图表数
  expectDataPoints: {
    0: [60],                      // 图0：K线 60 根
    1: [3],                       // 图1：饼图 3 块
    2: [7, 7, 4],                 // 图2：双轴柱 7+7+4（TODO 按实际）
  },
};

const fs = require("fs");
const vm = require("vm");

const html = fs.readFileSync(CONFIG.jsFile, "utf-8");

let setOptionCalls = [];
const makeChart = (id) => ({
  id,
  setOption: (opt) => setOptionCalls.push({ id, opt }),
  resize: () => {},
});

const charts = {};
const fakeEcharts = {
  init: (_el, _theme, _opts) => {
    const id = Object.keys(charts).length;
    charts[id] = makeChart(id);
    return charts[id];
  },
};

const sandbox = {
  echarts: fakeEcharts,
  document: {
    getElementById: () => ({ style: {}, clientWidth: 800, clientHeight: 400 }),
    querySelectorAll: () => [],
    addEventListener: () => {},
  },
  window: { addEventListener: () => {}, innerWidth: 1200 },
  getComputedStyle: () => ({ getPropertyValue: () => "" }),
  console,
};
vm.createContext(sandbox);
vm.runInContext(html, sandbox, { timeout: 10000 });

// ── 断言 ──
let fail = 0;
if (setOptionCalls.length !== CONFIG.expectSetOption) {
  console.log(`❌ setOption ${setOptionCalls.length} 次 != 期望 ${CONFIG.expectSetOption}`);
  fail = 1;
} else {
  console.log(`✅ setOption ${setOptionCalls.length} 次`);
}
for (const [idx, expects] of Object.entries(CONFIG.expectDataPoints)) {
  const call = setOptionCalls[Number(idx)];
  if (!call) { console.log(`❌ 图${idx} 无 setOption`); fail = 1; continue; }
  const series = (call.opt.series || []).map(s =>
    (s.data || []).length ?? (Array.isArray(s.data) ? s.data.length : 1));
  const ok = JSON.stringify(series) === JSON.stringify(expects);
  console.log(`${ok ? "✅" : "❌"} 图${idx} 数据点 [${series}] ${ok ? "==" : "!= 期望 [" + expects + "]"}`);
  if (!ok) fail = 1;
}
process.exit(fail);
