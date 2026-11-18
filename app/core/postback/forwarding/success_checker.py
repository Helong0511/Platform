"""
成功检查器

检查 Postback 转发是否成功。配置无效或响应结构不符合预期时默认失败，
避免将下游错误响应误判为成功并丢弃重试任务。
"""
import json
import logging
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)


class SuccessChecker:
    """Postback 下游响应成功检查器"""

    DEFAULT_SUCCESS_CHECK = {
        "type": "status_range",
        "min": 200,
        "max": 399,
    }

    @staticmethod
    def check(
        status_code: int,
        response_content: str,
        success_check_config: Optional[str] = None,
    ) -> Tuple[bool, str]:
        config = SuccessChecker._parse_config(success_check_config)
        check_type = config.get("type", "status_range")

        if check_type == "status_code":
            expected = config.get("expected", 200)
            success = status_code == expected
            message = f"状态码检查：{status_code} {'==' if success else '!='} {expected}"
        elif check_type == "status_range":
            min_status = config.get("min", 200)
            max_status = config.get("max", 399)
            success = min_status <= status_code <= max_status
            message = (
                f"状态码范围检查：{status_code} "
                f"{'在' if success else '不在'} [{min_status}, {max_status}] 范围内"
            )
        elif check_type == "content":
            expected_content = config.get("content", "")
            success = bool(expected_content) and expected_content in (response_content or "")
            message = f"内容检查：{'找到' if success else '未找到'} '{expected_content}'"
        elif check_type == "json":
            json_path = config.get("path", config.get("json_path", ""))
            expected = config.get("expected", config.get("json_value", ""))
            success, message = SuccessChecker._check_json(
                response_content or "", json_path, expected
            )
        else:
            success = False
            message = f"不支持的成功检查类型：{check_type}"

        logger.info("Postback 成功检查：type=%s success=%s", check_type, success)
        return success, message

    @staticmethod
    def _parse_config(config_str: Optional[str]) -> Dict[str, Any]:
        if not config_str:
            return SuccessChecker.DEFAULT_SUCCESS_CHECK.copy()
        try:
            config = json.loads(config_str)
            if not isinstance(config, dict):
                raise ValueError("成功检查配置必须是 JSON 对象")
            return config
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            logger.warning("成功检查配置无效，使用默认状态码规则：%s", type(exc).__name__)
            return SuccessChecker.DEFAULT_SUCCESS_CHECK.copy()

    @staticmethod
    def _check_json(
        content: str,
        json_path: str,
        expected: Any,
    ) -> Tuple[bool, str]:
        try:
            data = json.loads(content)
        except (json.JSONDecodeError, TypeError) as exc:
            stripped = str(content).strip().lower()
            if not json_path and stripped in {"1", "10", "ok", "success", "true", "yes"}:
                return True, f"响应为明确的成功指示符：'{content}'"
            if not json_path and expected not in (None, "") and str(content).strip() == str(expected):
                return True, "非 JSON 响应与配置的预期值匹配"
            return False, f"JSON 解析失败或响应不匹配：{exc}"

        if json_path:
            value = data
            for key in json_path.split("."):
                if isinstance(value, dict):
                    if key not in value:
                        return False, f"JSON 路径不存在：{json_path}"
                    value = value[key]
                else:
                    return False, f"JSON 路径解析失败：{json_path}"
            success = str(value) == str(expected)
            return success, f"JSON 检查：{json_path} {'==' if success else '!='} {expected}"

        if expected in (None, ""):
            return False, "JSON 成功检查未配置 path 或 expected，按失败处理"

        success = str(data) == str(expected)
        return success, f"JSON 根值检查 {'匹配' if success else '不匹配'}预期值"
