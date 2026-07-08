"""
敏感路径分级规则：路径模式 → 预警等级 → 处置策略。

等级（数值越大越严重）：
  LOW(1)      指纹/文档探测 — INFO + 404 + 仅入库
  MEDIUM(2)   常见 CMS/中间件扫描 — WARNING + 404 + 累计达阈值自动封禁
  HIGH(3)     凭证/配置/路径穿越 — WARNING + 404 + 更低阈值自动封禁
  CRITICAL(4) RCE/已知利用链 — WARNING + 404 + 最低阈值自动封禁 + Telegram 预警（防抖）
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
import logging
import re
from typing import Optional

from app.core.config import settings


class SensitivePathLevel(IntEnum):
    """敏感路径预警等级，数值越大处置越严格。"""

    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


LEVEL_LABELS: dict[int, str] = {
    SensitivePathLevel.LOW: "低危",
    SensitivePathLevel.MEDIUM: "中危",
    SensitivePathLevel.HIGH: "高危",
    SensitivePathLevel.CRITICAL: "危急",
}


@dataclass(frozen=True)
class LevelActionPolicy:
    """单等级默认处置策略（阈值可由 settings 覆盖）。"""

    log_level: int
    http_status: int  # 404 或 403（黑名单 IP 在 middleware 层单独处理）
    auto_block_threshold: int  # 窗口内命中次数达到则写入 IP 黑名单；0 表示不自动封禁
    telegram_alert: bool  # 是否发送 Telegram 预警（仍受全局开关与防抖约束）


DEFAULT_LEVEL_POLICIES: dict[SensitivePathLevel, LevelActionPolicy] = {
    SensitivePathLevel.LOW: LevelActionPolicy(
        log_level=logging.INFO,
        http_status=404,
        auto_block_threshold=0,
        telegram_alert=False,
    ),
    SensitivePathLevel.MEDIUM: LevelActionPolicy(
        log_level=logging.WARNING,
        http_status=404,
        auto_block_threshold=50,
        telegram_alert=False,
    ),
    SensitivePathLevel.HIGH: LevelActionPolicy(
        log_level=logging.WARNING,
        http_status=404,
        auto_block_threshold=20,
        telegram_alert=False,
    ),
    SensitivePathLevel.CRITICAL: LevelActionPolicy(
        log_level=logging.WARNING,
        http_status=404,
        auto_block_threshold=5,
        telegram_alert=True,
    ),
}


def get_level_policy(level: SensitivePathLevel) -> LevelActionPolicy:
    """合并环境变量中的自动封禁阈值。"""
    base = DEFAULT_LEVEL_POLICIES[level]
    overrides = {
        SensitivePathLevel.MEDIUM: getattr(
            settings, "SENSITIVE_PATH_AUTO_BLOCK_MEDIUM", base.auto_block_threshold
        ),
        SensitivePathLevel.HIGH: getattr(
            settings, "SENSITIVE_PATH_AUTO_BLOCK_HIGH", base.auto_block_threshold
        ),
        SensitivePathLevel.CRITICAL: getattr(
            settings, "SENSITIVE_PATH_AUTO_BLOCK_CRITICAL", base.auto_block_threshold
        ),
    }
    threshold = overrides.get(level, base.auto_block_threshold)
    if level == SensitivePathLevel.CRITICAL:
        alert = getattr(settings, "SENSITIVE_PATH_ALERT_CRITICAL", True)
        return LevelActionPolicy(
            log_level=base.log_level,
            http_status=base.http_status,
            auto_block_threshold=int(threshold),
            telegram_alert=bool(alert),
        )
    return LevelActionPolicy(
        log_level=base.log_level,
        http_status=base.http_status,
        auto_block_threshold=int(threshold),
        telegram_alert=base.telegram_alert,
    )


@dataclass(frozen=True)
class PathRule:
    """单条路径匹配规则：子串包含或精确路径。"""

    pattern: str
    level: SensitivePathLevel
    exact: bool = False


@dataclass(frozen=True)
class SensitivePathMatch:
    """路径匹配成功后的完整上下文（规则名、等级、处置策略）。"""

    matched_rule: str
    level: SensitivePathLevel
    policy: LevelActionPolicy


# ---------- 精确路径（按等级） ----------
_EXACT_RULES: tuple[PathRule, ...] = (
    PathRule("/.env", SensitivePathLevel.HIGH, exact=True),
    PathRule("/env", SensitivePathLevel.HIGH, exact=True),
    PathRule("/.git/config", SensitivePathLevel.HIGH, exact=True),
    PathRule("/server-status", SensitivePathLevel.HIGH, exact=True),
    PathRule("/server-info", SensitivePathLevel.HIGH, exact=True),
)

# ---------- 子串规则：危急（RCE / 利用链） ----------
_CRITICAL_MARKERS: tuple[str, ...] = (
    "/eval-stdin.php",
    "/vendor/phpunit",
    "/_ignition",
    "/jolokia",
    "/shell.php",
    "/c99.php",
    "/r57.php",
    "/wso.php",
    "/b374k.php",
    "/alfa.php",
    "/webshell",
)

# ---------- 高危（凭证、穿越、备份） ----------
_HIGH_MARKERS: tuple[str, ...] = (
    "/.env",
    "/.git",
    "/.aws",
    "/.htaccess",
    "/.git-credentials",
    "/docker-compose",
    "/wp-config",
    "/../",
    "/..\\",
    "/database.sql",
    "/backup.sql",
    "/db.sql",
    "/dump.sql",
    "/id_rsa",
    "/.ssh/",
    "/secrets.",
    "/credentials",
)

# ---------- 中危（框架/CMS/管理端扫描） ----------
_MEDIUM_MARKERS: tuple[str, ...] = (
    "/wp-admin",
    "/wp-login",
    "/wp-content",
    "/wp-includes",
    "/xmlrpc.php",
    "/phpmyadmin",
    "/pma/",
    "/mysql",
    "/adminer",
    "/admin.php",
    "/config.php",
    "/setup.php",
    "/install.php",
    "/actuator",
    "/manage",
    "/heapdump",
    "/phpinfo",
    "/swagger-ui",
    "/swagger.json",
    "/api-docs",
    "/cgi-bin/",
    "/composer.json",
    "/composer.lock",
    "/telescope",
    "/wlwmanifest",
    "/console",
    "/debug/",
    "/_profiler",
    "/solr/",
    "/jenkins",
    "/grafana",
    "/kibana",
    "/elasticsearch",
    "/redis/",
    "/mongodb",
    "/.dockerenv",
    "/requirements.txt",
    "/pyproject.toml",
)

# ---------- 低危（版本库指纹、生产文档） ----------
_LOW_MARKERS: tuple[str, ...] = (
    "/.svn",
    "/.hg",
    "/.DS_Store",
    "/.idea/",
    "/.vscode/",
)

_PROD_LOW_DOC_MARKERS: tuple[str, ...] = (
    "/docs",
    "/redoc",
    "/openapi.json",
)

# JS 打包产物中的模板变量名（如 ${e}、${u}）被安全扫描器当作字面路径探测
_BUNDLE_TEMPLATE_PLACEHOLDER_RE = re.compile(
    r"\$\{[^}/]+\}|%24%7b[^%/]+%7d",
    re.IGNORECASE,
)


def _marker_rules() -> tuple[PathRule, ...]:
    """合并内置子串规则、生产环境低危文档路径及 SENSITIVE_PATH_BLOCK_EXTRA 扩展。"""
    rules: list[PathRule] = []
    for m in _CRITICAL_MARKERS:
        rules.append(PathRule(m, SensitivePathLevel.CRITICAL))
    for m in _HIGH_MARKERS:
        rules.append(PathRule(m, SensitivePathLevel.HIGH))
    for m in _MEDIUM_MARKERS:
        rules.append(PathRule(m, SensitivePathLevel.MEDIUM))
    for m in _LOW_MARKERS:
        rules.append(PathRule(m, SensitivePathLevel.LOW))
    if settings.is_production:
        for m in _PROD_LOW_DOC_MARKERS:
            rules.append(PathRule(m, SensitivePathLevel.LOW))
    extra = (getattr(settings, "SENSITIVE_PATH_BLOCK_EXTRA", None) or "").strip()
    if extra:
        for part in extra.split(","):
            p = part.strip().lower()
            if not p:
                continue
            pattern = p if p.startswith("/") else f"/{p}"
            # 额外规则默认中危，可在规则串用 !critical:/path 等形式扩展（见 parse_extra_rule）
            level, pattern = _parse_extra_rule(pattern)
            rules.append(PathRule(pattern, level))
    return tuple(rules)


def _parse_extra_rule(raw: str) -> tuple[SensitivePathLevel, str]:
    """
    支持环境变量扩展语法：!critical:/eval-stdin.php 或 !high:/backup
    无前缀默认为中危。
    """
    for prefix, level in (
        ("!critical:", SensitivePathLevel.CRITICAL),
        ("!high:", SensitivePathLevel.HIGH),
        ("!medium:", SensitivePathLevel.MEDIUM),
        ("!low:", SensitivePathLevel.LOW),
    ):
        if raw.startswith(prefix):
            return level, raw[len(prefix) :]
    return SensitivePathLevel.MEDIUM, raw


_MARKER_RULES_CACHE: Optional[tuple[PathRule, ...]] = None


def all_marker_rules() -> tuple[PathRule, ...]:
    """返回全部子串规则（带进程内缓存，配置变更需 reload_marker_rules）。"""
    global _MARKER_RULES_CACHE
    if _MARKER_RULES_CACHE is None:
        _MARKER_RULES_CACHE = _marker_rules()
    return _MARKER_RULES_CACHE


def reload_marker_rules() -> None:
    """配置热更新时清空规则缓存（测试用）。"""
    global _MARKER_RULES_CACHE
    _MARKER_RULES_CACHE = None


def is_bundle_template_placeholder_path(path: str) -> bool:
    """
    检测前端打包 JS 中的模板占位符被扫描器原样请求的 URL。

    例如 /api/v1/clients/${u}、/api/v1/ad-data/%24%7Be%7D。
    正常业务请求不会出现此类路径。
    """
    if not path:
        return False
    return bool(_BUNDLE_TEMPLATE_PLACEHOLDER_RE.search(path))


def match_sensitive_path(path: str) -> Optional[SensitivePathMatch]:
    """
    匹配敏感路径，若多条规则命中则取最高等级。
    """
    path_l = (path or "").lower()
    best: Optional[SensitivePathMatch] = None

    if is_bundle_template_placeholder_path(path):
        return _build_match("bundle_template_placeholder", SensitivePathLevel.LOW)

    for rule in _EXACT_RULES:
        if path_l == rule.pattern:
            candidate = _build_match(f"exact:{rule.pattern}", rule.level)
            if best is None or candidate.level > best.level:
                best = candidate

    for rule in all_marker_rules():
        if rule.pattern in path_l:
            candidate = _build_match(f"marker:{rule.pattern}", rule.level)
            if best is None or candidate.level > best.level:
                best = candidate

    return best


def _build_match(matched_rule: str, level: SensitivePathLevel) -> SensitivePathMatch:
    """根据等级组装 SensitivePathMatch，并合并 settings 中的阈值覆盖。"""
    return SensitivePathMatch(
        matched_rule=matched_rule,
        level=level,
        policy=get_level_policy(level),
    )


def level_label(level: int) -> str:
    """将等级数值转为中文标签（低危/中危/高危/危急）。"""
    return LEVEL_LABELS.get(int(level), f"L{level}")
