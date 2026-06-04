"""
pytest 公共配置：在导入 app 模块前设置 CI/单测环境变量。
"""
import os
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

os.environ["UNIT_TEST"] = "1"
os.environ["PRODUCTION_ENV"] = "development"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["SECRET_KEY"] = "ci-test-secret-key-must-be-at-least-32-chars-long"
os.environ["ENABLE_CSRF"] = "false"
os.environ["ENABLE_SCHEDULER"] = "false"
os.environ["TELEGRAM_ENABLE"] = "false"

# 双轨/令牌测试用固定主密钥（64 位 hex，非生产密钥）
TEST_MASTER_KEY_HEX = "0123456789abcdef" * 4


@pytest.fixture
def dual_track_env(monkeypatch):
    """双轨模式：令牌 + 写 clicks 表。"""
    monkeypatch.setenv("USE_TRACKING_TOKEN", "true")
    monkeypatch.setenv("PERSIST_CLICKS_TO_DB", "true")
    monkeypatch.setenv("AD_TRACKING_MASTER_KEY_HEX", TEST_MASTER_KEY_HEX)
    from app.core import config

    monkeypatch.setattr(config.settings, "USE_TRACKING_TOKEN", True)
    monkeypatch.setattr(
        config.settings, "AD_TRACKING_MASTER_KEY_HEX", TEST_MASTER_KEY_HEX
    )
    return config.settings


@pytest.fixture
def tracking_token_env(monkeypatch):
    """仅启用追踪令牌，不写 clicks 表（默认双轨之一）。"""
    monkeypatch.delenv("PERSIST_CLICKS_TO_DB", raising=False)
    monkeypatch.setenv("USE_TRACKING_TOKEN", "true")
    monkeypatch.setenv("AD_TRACKING_MASTER_KEY_HEX", TEST_MASTER_KEY_HEX)
    from app.core import config

    monkeypatch.setattr(config.settings, "USE_TRACKING_TOKEN", True)
    monkeypatch.setattr(
        config.settings, "AD_TRACKING_MASTER_KEY_HEX", TEST_MASTER_KEY_HEX
    )
    return config.settings
