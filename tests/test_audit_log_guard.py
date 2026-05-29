"""审计日志调用静态守护：防止非法参数或白名单外 action_type 再次引入"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

VALID_KW = {
    "db", "action_type", "user", "user_id", "username", "resource_type",
    "resource_id", "resource_name", "request", "ip_address", "user_agent",
    "status_code", "success", "error_message", "details", "request_params",
}

HELPERS = {
    "log_login": {"db", "request", "user", "username", "success", "error_message"},
    "log_logout": {"db", "user", "request"},
    "log_create": {
        "db", "user", "resource_type", "resource_id", "resource_name",
        "request", "success", "error_message", "details",
    },
    "log_update": {
        "db", "user", "resource_type", "resource_id", "resource_name",
        "request", "success", "error_message", "details",
    },
    "log_delete": {
        "db", "user", "resource_type", "resource_id", "resource_name",
        "request", "success", "error_message", "details",
    },
    "log_activate": {
        "db", "user", "resource_type", "resource_id", "resource_name",
        "request", "success", "error_message", "details",
    },
    "log_deactivate": {
        "db", "user", "resource_type", "resource_id", "resource_name",
        "request", "success", "error_message", "details",
    },
    "log_runtime_error": {
        "db", "error_type", "error_message", "request", "user", "user_id",
        "username", "resource_type", "resource_id", "resource_name", "details",
    },
}

ALLOWED = {
    "LOGIN", "LOGOUT", "CREATE", "DELETE", "UPDATE", "IMPORT", "EXPORT",
    "ACTIVATE", "DEACTIVATE", "TASK_RUN", "API_ACCESS", "RUNTIME_ERROR",
    "REVOKE_SESSION", "REVOKE_ALL_SESSIONS", "CSRF_VIOLATION",
}

TARGET = {"log_user_action", *HELPERS.keys()}


def _const_str(node):
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _collect_issues():
    issues = []
    for path in (ROOT / "app").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.id if isinstance(node.func, ast.Name) else (
                node.func.attr if isinstance(node.func, ast.Attribute) else None
            )
            if name not in TARGET:
                continue
            kwargs = {kw.arg for kw in node.keywords if kw.arg}
            valid = VALID_KW if name == "log_user_action" else HELPERS[name]
            bad = sorted(kwargs - valid)
            if bad:
                issues.append(f"{rel}:{node.lineno} {name} 非法参数 {bad}")
            if name == "log_user_action":
                action = _const_str(next(
                    (kw.value for kw in node.keywords if kw.arg == "action_type"), None
                ))
                if action and action not in ALLOWED:
                    issues.append(f"{rel}:{node.lineno} 白名单外 action_type={action!r}")
    return issues


def test_audit_log_call_sites_have_valid_parameters():
    issues = _collect_issues()
    assert not issues, "审计日志调用存在问题:\n" + "\n".join(issues)
