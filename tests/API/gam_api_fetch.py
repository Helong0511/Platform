"""
GAM 联调 CLI 兼容入口。

正式实现与业务规则见 app.scheduler_module.gam_api_fetch。
"""
from __future__ import annotations

import sys

from app.scheduler_module import gam_api_fetch

# 兼容旧脚本 `from tests.API.gam_api_fetch import ...`
from app.scheduler_module.gam_api_fetch import *  # noqa: F403

if __name__ == "__main__":
    sys.exit(gam_api_fetch.main())
