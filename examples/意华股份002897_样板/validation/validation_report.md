# A股个股深度研究 · 产物验收报告

- Validator: v1.0.0
- 研究报告: `examples/意华股份002897_深度研究_20260915_090532.html`
- Manifest: `examples/意华股份002897_样板/research_manifest.json`
- **最终状态: PASS**
- P0: 0 ｜ P1: 0 ｜ P2: 0 ｜ INFO: 5

## 验收结果

| 等级 | 代码 | 结果 | 详情 |
|---|---|---|---|
| INFO | `STRUCT_CHAPTERS` | 0–16章结构完整 |  |
| INFO | `EVIDENCE_LABELS` | 证据标签体系存在 |  |
| INFO | `FORECAST_YEARS` | 识别到至少3个预测年度: [2026, 2027, 2028] |  |
| INFO | `TRACKER_ROWS` | 季度跟踪指标数量合格: 12 |  |
| INFO | `STRICT_MODE` | 严格模式：将继续校验结构化 manifest |  |

## 判定规则

- **P0**：硬错误。数学冲突、三情景/三年缺失、确认级证据误标等；禁止交付。
- **P1**：重要缺陷。核心模块不完整、跟踪指标不足等；严格模式下禁止交付。
- **P2**：改进项。不会单独阻断交付，但必须在下一版修复。
- **INFO**：通过项或说明。