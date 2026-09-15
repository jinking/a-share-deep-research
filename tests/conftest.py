# -*- coding: utf-8 -*-
"""pytest 公共配置：确保 core / tests 都能被直接导入。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = Path(__file__).resolve().parent

for path in (ROOT, TESTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
