"""
pytest 公共配置：在导入 app 模块前设置 CI/单测环境变量。
"""
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

os.environ.setdefault("UNIT_TEST", "1")
os.environ.setdefault("PRODUCTION_ENV", "development")
os.environ.setdefault(
    "DATABASE_URL",
    "sqlite+aiosqlite:///:memory:",
)
os.environ.setdefault(
    "SECRET_KEY",
    "ci-test-secret-key-must-be-at-least-32-chars-long",
)
os.environ.setdefault("ENABLE_CSRF", "false")
os.environ.setdefault("ENABLE_SCHEDULER", "false")
os.environ.setdefault("TELEGRAM_ENABLE", "false")
