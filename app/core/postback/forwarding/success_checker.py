"""
成功检查器

检查 Postback 转发是否成功
"""
import json
import logging
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)


class SuccessChecker:
    """成功检查器"""
    
    # 默认成功检查配置
    DEFAULT_SUCCESS_CHECK = {
        'type': 'status_range',
        'min': 200,
        'max': 399
    }
    
    @staticmethod
    def check(
        status_code: int,
        response_content: str,
        success_check_config: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        检查转发是否成功
        
        Args:
            status_code: HTTP 状态码
            response_content: 响应内容
            success_check_config: 成功检查配置（JSON 字符串）
        
        Returns:
            tuple: (是否成功，消息)
        """
        # 解析配置
        config = SuccessChecker._parse_config(success_check_config)
        
        check_type = config.get('type', 'status_range')
        
        if check_type == 'status_code':
            expected = config.get('expected', 200)
            success = status_code == expected
            message = f"状态码检查：{status_code} {'==' if success else '!='} {expected}"
            
        elif check_type == 'status_range':
            min_status = config.get('min', 200)
            max_status = config.get('max', 399)
            success = min_status <= status_code <= max_status
            message = f"状态码范围检查：{status_code} {'在' if success else '不在'} [{min_status}, {max_status}] 范围内"
            
        elif check_type == 'content':
            expected_content = config.get('content', '')
            success = expected_content in response_content
            message = f"内容检查：{'找到' if success else '未找到'} '{expected_content}'"
            
        elif check_type == 'json':
            success, message = SuccessChecker._check_json(
                response_content,
                config.get('path', ''),
                config.get('expected', '')
            )
            
        else:
            # 默认检查状态码范围
            success = 200 <= status_code <= 399
            message = f"默认检查：状态码 {status_code} 在 [200, 399] 范围内"
        
        logger.info(f"成功检查结果：{message}, success={success}")
        return success, message
    
    @staticmethod
    def _parse_config(config_str: Optional[str]) -> Dict[str, Any]:
        """解析成功检查配置"""
        if not config_str:
            return SuccessChecker.DEFAULT_SUCCESS_CHECK
        
        try:
            return json.loads(config_str)
        except json.JSONDecodeError as e:
            logger.warning(f"成功检查配置解析失败：{e}，使用默认配置")
            return SuccessChecker.DEFAULT_SUCCESS_CHECK
    
    @staticmethod
    def _check_json(
        content: str,
        json_path: str,
        expected: Any
    ) -> Tuple[bool, str]:
        """检查 JSON 响应"""
        try:
            # 尝试解析 JSON
            data = json.loads(content)
            
            # 简单路径解析（支持 dot notation）
            value = data
            for key in json_path.split('.'):
                if isinstance(value, dict):
                    value = value.get(key)
                else:
                    return False, f"JSON 路径解析失败：{json_path}"
            
            success = str(value) == str(expected)
            message = f"JSON 检查：{json_path}={value} {'==' if success else '!='} {expected}"
            return success, message
            
        except json.JSONDecodeError as e:
            # 如果响应不是 JSON，但内容与预期值匹配，也视为成功
            if str(content).strip() == str(expected):
                return True, f"非 JSON 响应但内容匹配：'{content}' == '{expected}'"
            # 如果响应是简单的成功指示符，也视为成功
            simple_success_indicators = ['1', '10', 'ok', 'success', 'true', 'yes', 'success']
            if str(content).strip().lower() in simple_success_indicators:
                return True, f"非 JSON 响应但为成功指示符：'{content}'"
            # 如果没有预期值，且响应是简单字符串，也视为成功
            if not expected:
                return True, f"非 JSON 响应但状态码为 200：'{content}'"
            # 对于数字类型的响应，如 "1" 或 "10"，也视为成功
            if str(content).strip().isdigit():
                return True, f"非 JSON 响应但为数字成功指示符：'{content}'"
            return False, f"JSON 解析失败：{e}，响应内容：{content[:50]}"
        except Exception as e:
            return False, f"JSON 检查异常：{e}"
