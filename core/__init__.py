# -*- coding: utf-8 -*-
"""a-share-deep-research v3.0 核心包。

设计原则（见仓库根目录 v3.0 升级方案）：
- 确定性逻辑进入代码，不再依赖 Agent 阅读 Prompt 后自行执行；
- 生成与验收职责分离，Validator 只检查、不修改产物；
- v2 / v3 产物并存，向后兼容。

本包不依赖 scripts/ 与 providers/，可被独立导入与单测。
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "3.0.0a1"
