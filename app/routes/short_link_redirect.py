"""
短链接重定向路由模块

本模块负责处理短链接的重定向逻辑，是整个短链接系统的核心组件。

主要功能：
1. 短链接重定向：将短链接代码转换为完整的重定向URL
2. 占位符替换：支持在原始URL中使用占位符，动态替换为实际值
3. 点击记录：记录每次点击的详细信息（IP、设备、浏览器等）
4. 点击计数：异步更新短链接的点击次数
5. 缓存优化：使用Redis缓存提高性能
6. 参数合并：自动将请求参数合并到最终跳转URL

工作流程：
1. 用户访问短链接 → 2. 从缓存/数据库获取短链接信息 → 3. 生成点击ID → 
4. 收集请求信息 → 5. 替换占位符 → 6. 合并参数 → 7. 创建点击记录 → 
8. 更新点击计数 → 9. 302重定向

性能优化：
- Redis缓存：减少数据库查询
- 异步处理：点击记录和计数更新不阻塞重定向
- 批量处理：点击记录批量插入数据库
"""
import asyncio
import logging
import re
from typing import Optional, Dict, Any
from datetime import datetime
from urllib.parse import urlparse, urlencode, parse_qs, urlunparse, quote
from collections import OrderedDict

from fastapi import APIRouter, Depends, Query, Request, BackgroundTasks, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import get_db
from app.core.short_link_cache import (
    get_short_link_from_cache,
    set_short_link_to_cache,
    serialize_short_link
)
from app.core.short_link_click_counter import increment_click_count_async
from app.core.tracking.click_id_generator import generate_click_id_from_timestamp
from app.core.device_info import collect_request_info
from app.core.utils import get_app_now_naive, APP_TIMEZONE
from app.core.clicks_queue import enqueue_click
from app.core.offer_cache import set_offer_cache
from app.api.api_v1.endpoints.tracking.tracking import create_click_background
from app.models.models import ShortLink, Offer, Publisher, Advertiser

# 日志记录器
logger = logging.getLogger(__name__)

# 创建FastAPI路由实例，用于注册短链接相关的API端点
router = APIRouter()


async def _replace_short_link_placeholders(
    original_url: str,
    click_id: str,
    offer_id: Optional[int],
    publisher_id: Optional[int],
    advertiser_id: Optional[int],
    request_info: dict,
    db: AsyncSession
) -> str:
    """
    替换短链接原始URL中的占位符
    
    这是短链接系统的核心功能之一，用于将原始URL中的占位符（如 {click_id}、{channel_id}）
    替换为实际的值。支持多种占位符格式和别名。
    
    Args:
        original_url: 原始URL字符串，可能包含占位符，例如：
                     "http://example.com/track?click_id={click_id}&sub_affid={channel_id}"
        click_id: 系统生成的唯一点击ID，用于追踪每次点击
        offer_id: Offer的数据库主键ID（可选）
        publisher_id: 渠道（Publisher）的数据库主键ID（可选）
        advertiser_id: 广告主的数据库主键ID（可选）
        request_info: 请求信息字典，包含：
                     - ip: 客户端IP地址
                     - os: 操作系统名称
                     - device_type: 设备类型（mobile/tablet/desktop）
                     - country: 国家代码
                     - user_agent: 浏览器User-Agent
                     - referer: 来源页面URL
        db: 数据库异步会话，用于查询Offer、Publisher、Advertiser的详细信息
    
    Returns:
        替换后的URL字符串，所有占位符已被替换为实际值
    
    支持的占位符：
    - {click_id} / {clickId} / {clickid} / {aff_click_id}: 点击ID
    - {offer_id} / {offerId}: Offer ID
    - {publisher_id} / {channel_id} / {sub_affid}: 渠道ID（都映射到publisher_id）
    - {advertiser_id}: 广告主ID
    - {ip}: 客户端IP地址
    - {os}: 操作系统名称
    - {device_type}: 设备类型
    - {country}: 国家代码
    - {offer_name}: Offer名称（从数据库查询）
    - {publisher_name}: 渠道名称（从数据库查询）
    - {advertiser_name}: 广告主名称（从数据库查询）
    - 以及其他Offer、Publisher、Advertiser的字段
    
    处理逻辑：
    1. 使用正则表达式查找所有 {xxx} 格式的占位符
    2. 构建占位符值字典（包含基础值和从数据库查询的详细信息）
    3. 遍历每个占位符，进行别名映射和标准化
    4. 替换占位符为实际值（URL编码）
    5. 如果占位符值为空，移除包含该占位符的整个URL参数
    6. 统一将URL参数名转为小写
    
    示例：
        输入: "http://example.com/track?click_id={click_id}&sub_affid={channel_id}"
        输出: "http://example.com/track?click_id=abc123&sub_affid=3"
    """
    # 使用正则表达式查找所有占位符
    # 模式说明：\{([a-zA-Z_][a-zA-Z0-9_]*)\}
    # - \{ : 匹配左花括号（转义）
    # - ([a-zA-Z_][a-zA-Z0-9_]*) : 捕获组，匹配占位符名称
    #   - [a-zA-Z_] : 首字符必须是字母或下划线
    #   - [a-zA-Z0-9_]* : 后续字符可以是字母、数字或下划线
    # - \} : 匹配右花括号（转义）
    pattern = r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}'
    placeholders = re.findall(pattern, original_url)
    
    # 如果没有找到占位符，直接返回原始URL
    if not placeholders:
        return original_url
    
    # ==================== 构建基础占位符值字典 ====================
    # 这些值直接从函数参数和request_info中获取，不需要查询数据库
    values = {
        'click_id': click_id,  # 点击ID（系统生成）
        'ip': request_info.get('ip', ''),  # 客户端IP地址
        'os': request_info.get('os', ''),  # 操作系统（Windows/macOS/iOS/Android等）
        'device_type': request_info.get('device_type', ''),  # 设备类型（mobile/tablet/desktop）
        'country': request_info.get('country', ''),  # 国家代码（如果有）
        'user_agent': request_info.get('user_agent', ''),  # 浏览器User-Agent字符串
        'referer': request_info.get('referer', ''),  # 来源页面URL
    }
    
    # ==================== 并行查询数据库（优化性能） ====================
    # 使用 asyncio.gather 并行查询 Offer、Publisher、Advertiser
    # 这样可以减少总查询时间，特别是在需要查询多个实体时
    
    # 准备查询任务
    query_tasks = []
    
    # Offer 查询任务
    if offer_id:
        values['offer_id'] = str(offer_id)
        async def query_offer():
            try:
                offer_result = await db.execute(
                    select(Offer).where(Offer.id == offer_id)
                )
                return offer_result.scalars().first()
            except Exception as e:
                logger.warning(f"查询Offer信息失败: offer_id={offer_id}, error={e}")
                return None
        query_tasks.append(('offer', query_offer()))
    else:
        values['offer_id'] = ''
        values['offer_name'] = ''
        values['advertiser_offer_id'] = ''
    
    # Publisher 查询任务
    if publisher_id is not None:
        publisher_id_str = str(publisher_id)
        values['publisher_id'] = publisher_id_str
        values['channel_id'] = publisher_id_str
        async def query_publisher():
            try:
                publisher_result = await db.execute(
                    select(Publisher).where(Publisher.id == publisher_id)
                )
                return publisher_result.scalars().first()
            except Exception as e:
                logger.warning(f"查询Publisher信息失败: publisher_id={publisher_id}, error={e}")
                return None
        query_tasks.append(('publisher', query_publisher()))
    else:
        values['publisher_id'] = ''
        values['channel_id'] = ''
        values['publisher_name'] = ''
        values['publisher_email'] = ''
    
    # Advertiser 查询任务
    if advertiser_id:
        values['advertiser_id'] = str(advertiser_id)
        async def query_advertiser():
            try:
                advertiser_result = await db.execute(
                    select(Advertiser).where(Advertiser.id == advertiser_id)
                )
                return advertiser_result.scalars().first()
            except Exception as e:
                logger.warning(f"查询Advertiser信息失败: advertiser_id={advertiser_id}, error={e}")
                return None
        query_tasks.append(('advertiser', query_advertiser()))
    else:
        values['advertiser_id'] = ''
        values['advertiser_name'] = ''
        values['advertiser_email'] = ''
    
    # 并行执行所有查询
    if query_tasks:
        results = await asyncio.gather(*[task[1] for task in query_tasks], return_exceptions=True)
        
        # 处理查询结果
        for i, (entity_type, _) in enumerate(query_tasks):
            result = results[i]
            
            # 如果查询失败（异常），跳过
            if isinstance(result, Exception) or result is None:
                continue
            
            if entity_type == 'offer':
                offer = result
                if offer:
                    values['offer_name'] = offer.offer_name or ''
                    values['advertiser_offer_id'] = offer.advertiser_offer_id or ''
                    values['offer_payout'] = str(offer.payout) if offer.payout is not None else ''
                    values['affiliate_payout'] = str(offer.affiliate_payout) if offer.affiliate_payout is not None else ''
                    values['offer_country'] = offer.country or ''
                    values['offer_category'] = offer.category or ''
                    values['offer_type'] = offer.type or ''
                    values['offer_status'] = offer.status or ''
            elif entity_type == 'publisher':
                publisher = result
                if publisher:
                    values['publisher_name'] = publisher.publisher_name or ''
                    values['publisher_email'] = publisher.email or ''
            elif entity_type == 'advertiser':
                advertiser = result
                if advertiser:
                    values['advertiser_name'] = advertiser.advertiser_name or ''
                    values['advertiser_email'] = advertiser.email or ''
    
    # ==================== 占位符别名映射表 ====================
    # 支持多种命名格式的占位符，统一映射到标准键名
    # 例如：{clickId}、{clickid}、{aff_click_id} 都映射到 'click_id'
    alias_map = {
        # click_id 的别名（支持多种命名风格）
        'clickid': 'click_id',  # 全小写
        'clickId': 'click_id',  # 驼峰命名
        'clk_id': 'click_id',  # 缩写形式
        'cid': 'click_id',  # 更短缩写
        'aff_click_id': 'click_id',  # 带前缀
        'affclickid': 'click_id',  # 带前缀全小写
        
        # publisher_id 的别名
        'publisherId': 'publisher_id',
        'publisherid': 'publisher_id',
        
        # channel_id 的别名（注意：channel_id 最终会映射到 publisher_id）
        'channelId': 'channel_id',
        'channelid': 'channel_id',
        'sub_affid': 'channel_id',  # 常见的渠道ID参数名
        'subaffid': 'channel_id',
        
        # offer_id 的别名
        'offerId': 'offer_id',
        'offerid': 'offer_id',
    }
    
    # ==================== 开始替换占位符 ====================
    result_url = original_url  # 复制原始URL，避免修改原始字符串
    logger.debug(f"[占位符替换] 开始替换占位符，原始URL: {original_url}")
    logger.debug(f"[占位符替换] 找到的占位符: {placeholders}")
    logger.debug(f"[占位符替换] 可用值: click_id={click_id}, offer_id={offer_id}, publisher_id={publisher_id}, advertiser_id={advertiser_id}")
    
    # 记录未替换的占位符（这些占位符的值为空，需要移除包含它们的URL参数）
    unreplaced_placeholders = []
    
    # 遍历每个找到的占位符，进行替换
    for placeholder in placeholders:
        # 步骤1：标准化占位符键名（转为小写，便于匹配）
        normalized_key = placeholder.lower()
        original_normalized_key = normalized_key  # 保存原始值用于日志
        
        # 步骤2：检查别名映射表
        # 如果占位符在别名映射表中，使用映射后的标准键名
        if normalized_key in alias_map:
            normalized_key = alias_map[normalized_key]
            logger.debug(f"[占位符替换] 占位符 {{{placeholder}}} 通过别名映射: {original_normalized_key} -> {normalized_key}")
        else:
            # 如果不在别名映射表中，尝试将驼峰命名转换为下划线命名
            # 例如：{clickId} -> click_id, {offerId} -> offer_id
            # 正则说明：(?<!^)(?=[A-Z])
            # - (?<!^) : 负向后顾断言，确保不在字符串开头
            # - (?=[A-Z]) : 正向前瞻断言，匹配大写字母前的位置
            normalized_key = re.sub(r'(?<!^)(?=[A-Z])', '_', placeholder).lower()
            if normalized_key != original_normalized_key:
                logger.debug(f"[占位符替换] 占位符 {{{placeholder}}} 标准化: {original_normalized_key} -> {normalized_key}")
        
        # 步骤3：特殊映射规则
        # channel_id 和 sub_affid 都映射到 publisher_id（因为它们指向同一个值）
        if normalized_key == 'channel_id' or normalized_key == 'sub_affid':
            logger.debug(f"[占位符替换] 占位符 {{{placeholder}}} 映射到 publisher_id")
            normalized_key = 'publisher_id'
        
        # 步骤4：从值字典中获取对应的值
        value = values.get(normalized_key, '')
        
        # 步骤5：处理值为空的情况
        if not value:
            # 如果值为空，说明占位符无法替换（可能是未提供对应参数，或占位符无法识别）
            # 记录到未替换列表，稍后会移除包含该占位符的整个URL参数
            logger.warning(f"[占位符替换] 占位符 {{{placeholder}}} (映射到 {normalized_key}) 的值为空，将移除包含该占位符的参数")
            unreplaced_placeholders.append(placeholder)
            continue  # 跳过替换，继续处理下一个占位符
        
        # 步骤6：替换占位符为实际值
        # 使用URL编码确保特殊字符正确传输（例如空格、中文字符等）
        # quote() 函数会将特殊字符编码为 %XX 格式
        encoded_value = quote(str(value), safe='')
        result_url = result_url.replace(f'{{{placeholder}}}', encoded_value)
        logger.debug(f"[占位符替换] 占位符 {{{placeholder}}} -> {value} (编码后: {encoded_value})")
    
    # ==================== 移除包含未替换占位符的URL参数 ====================
    # 如果某些占位符无法替换（值为空），需要移除包含这些占位符的整个URL参数
    # 例如：如果 {channel_id} 无法替换，则移除 sub_affid={channel_id} 这个参数
    if unreplaced_placeholders:
        # 解析URL，提取查询参数
        parsed = urlparse(result_url)
        
        if parsed.query:
            # 解析查询字符串为字典格式
            # parse_qs() 返回字典，值为列表（因为URL参数可能有多个值）
            # keep_blank_values=True 保留空值参数
            query_params = parse_qs(parsed.query, keep_blank_values=True)
            # 将所有参数名转为小写（统一处理）
            query_params_lower = {k.lower(): v for k, v in query_params.items()}
            
            # 检查每个参数值，如果包含未替换的占位符，标记为需要移除
            params_to_remove = []
            for param_name, param_values in query_params_lower.items():
                # 遍历参数的所有值（因为一个参数可能有多个值）
                for param_value in param_values:
                    # 检查参数值中是否包含未替换的占位符
                    for unreplaced_placeholder in unreplaced_placeholders:
                        placeholder_pattern = f'{{{unreplaced_placeholder}}}'
                        # 检查原始占位符（URL编码后的占位符也会被检测到，因为占位符本身不会被编码）
                        if placeholder_pattern in param_value:
                            params_to_remove.append(param_name)
                            logger.info(f"[占位符替换] 移除参数 {param_name}={param_value}，因为包含未替换的占位符 {{{unreplaced_placeholder}}}")
                            break  # 找到就跳出内层循环
                    if param_name in params_to_remove:
                        break  # 如果参数已标记为移除，跳出值循环
            
            # 从参数字典中移除标记的参数
            for param_name in params_to_remove:
                query_params_lower.pop(param_name, None)
            
            # 重新构建查询字符串
            if query_params_lower:
                # 如果还有参数，重新编码为查询字符串
                new_query = urlencode(query_params_lower, doseq=True)
                result_url = urlunparse(parsed._replace(query=new_query))
            else:
                # 如果所有参数都被移除了，移除整个查询字符串部分
                result_url = urlunparse(parsed._replace(query=''))
    
    logger.debug(f"[占位符替换] 替换后的URL: {result_url}")
    
    # ==================== 统一URL参数名为小写 ====================
    # 为了保持一致性，将所有URL参数名转为小写
    # 例如：?OfferId=123 -> ?offerid=123
    parsed = urlparse(result_url)
    if parsed.query:
        # 重新解析查询参数
        query_params = parse_qs(parsed.query, keep_blank_values=True)
        # 将所有参数名转为小写
        query_params_lower = {k.lower(): v for k, v in query_params.items()}
        # 重新编码为查询字符串
        new_query = urlencode(query_params_lower, doseq=True)
        # 重新构建URL
        result_url = urlunparse(parsed._replace(query=new_query))
    
    return result_url


def _replace_param_value_placeholders(
    param_value: str,
    click_id: str,
    offer_id: Optional[int],
    channel_id: Optional[int],
    advertiser_id: Optional[int],
    request_info: dict
) -> tuple[str, bool]:
    """
    替换URL参数值中的占位符
    
    这个函数用于处理请求参数值中包含占位符的情况。
    例如：用户请求参数 test={click_id}，需要将 {click_id} 替换为实际的点击ID。
    
    与 _replace_short_link_placeholders 的区别：
    - _replace_short_link_placeholders: 替换原始URL中的占位符（整个URL）
    - _replace_param_value_placeholders: 替换单个参数值中的占位符（参数值字符串）
    
    Args:
        param_value: 参数值字符串，可能包含占位符，例如："{click_id}" 或 "test_{click_id}_end"
        click_id: 系统生成的唯一点击ID
        offer_id: Offer的数据库主键ID（可选）
        channel_id: 渠道（Publisher）的数据库主键ID（可选）
        advertiser_id: 广告主的数据库主键ID（可选）
        request_info: 请求信息字典，包含IP、OS、设备等信息
    
    Returns:
        tuple[str, bool]: 
            - str: 替换后的参数值字符串
            - bool: 是否所有占位符都被成功替换
                    True: 所有占位符都已替换
                    False: 有占位符无法识别或值为空（参数应该被丢弃）
    
    处理逻辑：
    1. 查找参数值中的所有占位符
    2. 构建占位符值字典（与 _replace_short_link_placeholders 保持一致）
    3. 遍历每个占位符，进行别名映射和标准化
    4. 替换占位符为实际值
    5. 如果所有占位符都能替换，返回 (替换后的值, True)
    6. 如果有占位符无法替换，返回 (部分替换的值, False)
    
    示例：
        输入: param_value="{click_id}", click_id="abc123"
        输出: ("abc123", True)
        
        输入: param_value="{click_id}_{unknown}", click_id="abc123"
        输出: ("abc123_{unknown}", False)  # 有占位符无法替换
    """
    # 使用正则表达式查找参数值中的所有占位符
    pattern = r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}'
    placeholders = re.findall(pattern, param_value)
    
    # 如果没有占位符，直接返回原值
    if not placeholders:
        return param_value, True
    
    # ==================== 构建占位符值字典 ====================
    # 注意：这里不查询数据库，只使用传入的参数值
    # 与 _replace_short_link_placeholders 保持一致，但简化了逻辑
    values = {
        'click_id': click_id,  # 点击ID（总是有值）
        'ip': request_info.get('ip', ''),  # IP地址
        'os': request_info.get('os', ''),  # 操作系统
        'device_type': request_info.get('device_type', ''),  # 设备类型
        'country': request_info.get('country', ''),  # 国家
        'user_agent': request_info.get('user_agent', ''),  # User-Agent
        'referer': request_info.get('referer', ''),  # 来源页面
    }
    
    # Offer字段
    if offer_id:
        values['offer_id'] = str(offer_id)
    else:
        values['offer_id'] = ''  # 空值，占位符将无法替换
    
    # Publisher/Channel字段（注意：channel_id 和 publisher_id 指向同一个值）
    if channel_id is not None:
        publisher_id_str = str(channel_id)
        values['publisher_id'] = publisher_id_str
        values['channel_id'] = publisher_id_str
    else:
        values['publisher_id'] = ''
        values['channel_id'] = ''
    
    # Advertiser字段
    if advertiser_id:
        values['advertiser_id'] = str(advertiser_id)
    else:
        values['advertiser_id'] = ''
    
    # ==================== 占位符别名映射表 ====================
    # 与 _replace_short_link_placeholders 中的别名映射保持一致
    alias_map = {
        'clickid': 'click_id',
        'clickId': 'click_id',
        'clk_id': 'click_id',
        'cid': 'click_id',
        'aff_click_id': 'click_id',
        'affclickid': 'click_id',
        'publisherId': 'publisher_id',
        'publisherid': 'publisher_id',
        'channelId': 'channel_id',
        'channelid': 'channel_id',
        'sub_affid': 'channel_id',
        'subaffid': 'channel_id',
        'offerId': 'offer_id',
        'offerid': 'offer_id',
    }
    
    # ==================== 开始替换占位符 ====================
    result_value = param_value  # 复制原值
    all_replaced = True  # 标记是否所有占位符都被成功替换
    
    for placeholder in placeholders:
        # 标准化占位符键名
        normalized_key = placeholder.lower()
        original_normalized_key = normalized_key
        
        # 检查别名映射
        if normalized_key in alias_map:
            normalized_key = alias_map[normalized_key]
        else:
            # 驼峰命名转下划线命名
            normalized_key = re.sub(r'(?<!^)(?=[A-Z])', '_', placeholder).lower()
        
        # 特殊映射：channel_id 和 sub_affid 都映射到 publisher_id
        if normalized_key == 'channel_id' or normalized_key == 'sub_affid':
            normalized_key = 'publisher_id'
        
        # 获取对应的值
        value = values.get(normalized_key, '')
        
        if not value:
            # 占位符无法识别或值为空
            # 标记为未完全替换，但继续处理其他占位符
            all_replaced = False
            logger.debug(f"[参数值占位符替换] 占位符 {{{placeholder}}} (映射到 {normalized_key}) 无法替换，值为空")
            continue  # 跳过这个占位符，不替换
        
        # 替换占位符为实际值（URL编码）
        encoded_value = quote(str(value), safe='')
        result_value = result_value.replace(f'{{{placeholder}}}', encoded_value)
        logger.debug(f"[参数值占位符替换] 占位符 {{{placeholder}}} -> {value}")
    
    # 返回替换后的值和是否完全替换的标志
    return result_value, all_replaced


def merge_url_params(base_url: str, query_params: dict) -> str:
    """
    将查询参数合并到基础URL中
    
    这个函数用于将新的查询参数合并到已有的URL中，处理参数冲突和占位符检测。
    
    功能特性：
    1. 检测基础URL中是否已有占位符（如 {click_id}），如果有则不重复添加对应参数
    2. 过滤掉参数值中包含占位符的参数（避免未替换的占位符出现在最终URL中）
    3. 确保 click_id 参数位于查询字符串的最前面（便于追踪）
    4. 统一参数名为小写，避免大小写不一致导致的问题
    
    Args:
        base_url: 基础URL（可能已包含查询参数）
        query_params: 要合并的查询参数字典，格式为 {参数名: 参数值}
                     参数值可以是字符串或列表（支持多值参数）
    
    Returns:
        str: 合并后的完整URL
    
    处理流程：
    1. 解析基础URL，提取现有查询参数
    2. 检测基础URL中是否包含占位符（如 {click_id}、{offer_id} 等）
    3. 如果基础URL中已有占位符，标记对应参数为"跳过"（不重复添加）
    4. 过滤掉参数值中包含占位符的新参数（避免未替换的占位符）
    5. 合并参数（新参数覆盖旧参数，但跳过已在占位符中使用的参数）
    6. 确保 click_id 在最前面
    7. 重新构建URL
    
    示例：
        输入: base_url="http://example.com?test=1", query_params={"click_id": "abc", "offer_id": 123}
        输出: "http://example.com?click_id=abc&offer_id=123&test=1"
        
        输入: base_url="http://example.com?aff_click_id={click_id}", query_params={"click_id": "abc"}
        输出: "http://example.com?aff_click_id=abc"  # 不重复添加 click_id
    """
    # 如果没有要合并的参数，直接返回基础URL
    if not query_params:
        return base_url
    
    # ==================== 解析基础URL ====================
    parsed = urlparse(base_url)
    # 解析现有查询参数（keep_blank_values=True 保留空值参数）
    existing_params = parse_qs(parsed.query, keep_blank_values=True)
    # 统一参数名为小写（便于比较和合并）
    existing_params_lower = {k.lower(): v for k, v in existing_params.items()}
    
    # ==================== 定义占位符模式列表 ====================
    # 用于检测参数值中是否包含占位符（未替换的占位符应该被过滤掉）
    all_placeholder_patterns = [
        '{click_id}', '{clickId}', '{clickid}', '{ClickId}', '{CLICK_ID}',
        '{aff_click_id}', '{AFF_CLICK_ID}', '{affclickid}', '{AFFCLICKID}',
        '{offer_id}', '{offerId}', '{offerid}', '{OfferId}', '{OFFER_ID}',
        '{channel_id}', '{channelId}', '{channelid}', '{ChannelId}', '{CHANNEL_ID}',
        '{sub_affid}', '{SUB_AFFID}', '{subaffid}', '{SUBAFFID}',
        '{publisher_id}', '{publisherId}', '{publisherid}', '{PublisherId}', '{PUBLISHER_ID}',
        '{ip}', '{os}', '{device_type}', '{country}', '{advertiser_id}',
    ]
    
    # ==================== 检测基础URL中的占位符 ====================
    # 如果基础URL中已有占位符（如 {click_id}），则不需要再添加对应的查询参数
    # 这样可以避免重复添加参数
    placeholder_params = {'click_id', 'offer_id', 'channel_id', 'publisher_id'}
    skip_params = set()  # 需要跳过的参数集合
    
    for param in placeholder_params:
        # 生成占位符的各种变体（不同大小写、命名风格）
        placeholder_variants = [
            f'{{{param}}}',  # {click_id}
            f'{{{param.lower()}}}',  # {click_id}
            f'{{{param.upper()}}}',  # {CLICK_ID}
            f'{{{param.capitalize()}}}',  # {Click_id}
        ]
        # 生成驼峰命名变体（如 clickId）
        camel_case = ''.join(word.capitalize() if i > 0 else word.lower() 
                           for i, word in enumerate(param.split('_')))
        placeholder_variants.extend([
            f'{{{camel_case}}}',  # {clickId}
            f'{{{camel_case.lower()}}}',  # {clickid}
        ])
        
        # 检查基础URL中是否包含这些占位符变体
        if any(variant in base_url for variant in placeholder_variants):
            skip_params.add(param)  # 如果找到，标记为跳过
    
    # ==================== 过滤包含占位符的参数值 ====================
    # 如果新参数的参数值中包含占位符（未替换），应该被过滤掉
    # 例如：test={unknown_placeholder} 应该被移除
    filtered_query_params = {}
    for key, value in query_params.items():
        # 将参数值转为字符串（处理列表类型）
        param_value_str = str(value) if not isinstance(value, list) else str(value[0]) if value else ''
        # 检查参数值中是否包含任何占位符模式
        contains_placeholder = any(pattern in param_value_str for pattern in all_placeholder_patterns)
        
        if contains_placeholder:
            logger.debug(f"[合并URL参数] 跳过参数 {key}={value}，因为参数值中包含占位符")
            continue  # 跳过包含占位符的参数
        
        filtered_query_params[key] = value
    
    # 使用过滤后的参数（不包含占位符的参数）
    query_params = filtered_query_params
    
    # ==================== 分离 click_id 和其他参数 ====================
    # 为了确保 click_id 在最前面，需要单独处理
    click_id_value = None
    other_params = {}
    
    for key, value in query_params.items():
        key_lower = key.lower()
        
        # 如果参数已在占位符中使用，跳过（不重复添加）
        if key_lower in skip_params:
            continue
        
        # 分离 click_id 和其他参数
        if key_lower == 'click_id':
            # 统一转为列表格式（parse_qs 返回的是列表）
            click_id_value = [str(v) for v in value] if isinstance(value, list) else [str(value)]
        else:
            other_params[key_lower] = [str(v) for v in value] if isinstance(value, list) else [str(value)]
    
    # ==================== 合并参数 ====================
    # 将新参数合并到现有参数中（新参数覆盖旧参数）
    for key, value in other_params.items():
        existing_params_lower[key] = value
    
    # 添加 click_id（如果不在跳过列表中）
    if click_id_value and 'click_id' not in skip_params:
        existing_params_lower['click_id'] = click_id_value
    
    # ==================== 确保 click_id 在最前面 ====================
    # 使用 OrderedDict 保持参数顺序，确保 click_id 在第一位（便于追踪和调试）
    ordered_params = OrderedDict()
    if 'click_id' in existing_params_lower and 'click_id' not in skip_params:
        ordered_params['click_id'] = existing_params_lower['click_id']
    
    # 添加其他参数（click_id 除外）
    for key, value in existing_params_lower.items():
        if key != 'click_id':
            ordered_params[key.lower()] = value
    
    # ==================== 重新构建URL ====================
    # 将参数字典编码为查询字符串
    new_query = urlencode(ordered_params, doseq=True)
    # 替换URL的查询部分
    return urlunparse(parsed._replace(query=new_query))


@router.get("/s/{short_code}",
            summary="短链接重定向（推荐）",
            tags=["短链接服务"],
            description="✅ 推荐使用的短链接重定向路由，带缓存优化，性能更好")
async def redirect_short_link_public(
    short_code: str,
    offer_id: Optional[int] = Query(None, description="Offer ID（从URL参数获取）"),
    channel_id: Optional[int] = Query(None, description="渠道ID（从URL参数获取）"),
    request: Request = None,
    background_tasks: BackgroundTasks = None,
    db: AsyncSession = Depends(get_db)
):
    """
    短链接重定向（公开接口，无需认证）
    
    ✅ **推荐路由**：这是系统推荐使用的短链接重定向路由
    
    性能优化：
    - 使用Redis缓存减少数据库查询，提高响应速度
    - 异步更新点击次数，不阻塞重定向
    - 适合高并发场景
    
    功能特性：
    - 支持查询参数自动合并到原始URL
    - 自动生成click_id并添加到重定向URL
    - 完整的点击记录追踪（IP、设备信息、浏览器信息等）
    """
    try:
        request_url = str(request.url)
        request_params = {k.lower(): v for k, v in request.query_params.items()}
        logger.debug(
            f"[短链接重定向] 收到请求: short_code={short_code}, "
            f"完整URL={request_url}, 查询参数={request_params}"
        )
        
        # 尝试从缓存获取
        cached_data = await get_short_link_from_cache(short_code)
        
        if cached_data:
            return await _handle_cached_redirect(
                short_code, cached_data, offer_id, channel_id,
                request, background_tasks, db, request_params
            )
        else:
            return await _handle_database_redirect(
                short_code, offer_id, channel_id,
                request, background_tasks, db, request_params
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"[短链接重定向] 处理异常: short_code={short_code}, error={str(e)}",
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"短链接重定向失败: {str(e)}"
        )


async def _handle_cached_redirect(
    short_code: str,
    cached_data: dict,
    offer_id: Optional[int],
    channel_id: Optional[int],
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession,
    request_params: dict
) -> RedirectResponse:
    """
    处理缓存命中的短链接重定向
    
    当短链接数据在Redis缓存中命中时，使用此函数处理重定向。
    相比数据库查询，缓存命中可以显著提高响应速度。
    
    处理流程：
    1. 验证短链接状态（是否激活、是否过期）
    2. 验证原始URL格式
    3. 生成点击ID
    4. 解析 offer_id 和 channel_id（优先使用URL参数，否则使用缓存数据）
    5. 创建点击记录（异步）
    6. 更新点击次数（异步）
    7. 替换URL中的占位符
    8. 构建最终重定向URL
    9. 记录详细日志
    10. 返回重定向响应
    
    Args:
        short_code: 短链接代码（唯一标识）
        cached_data: 从Redis缓存获取的短链接数据字典
                    包含：original_url, is_active, expires_at, id, offer_id, channel_id 等
        offer_id: 从URL参数获取的Offer ID（可选）
        channel_id: 从URL参数获取的渠道ID（可选）
        request: FastAPI请求对象，用于获取请求信息（IP、User-Agent等）
        background_tasks: FastAPI后台任务对象，用于异步处理点击记录
        db: 数据库会话（用于查询Offer信息等）
        request_params: 用户请求时携带的查询参数字典
    
    Returns:
        RedirectResponse: HTTP 302重定向响应，指向最终的目标URL
    
    Raises:
        HTTPException: 
            - 404: 短链接不存在、已禁用或已过期
            - 500: 原始URL格式无效
    """
    original_url = cached_data["original_url"]
    is_active = cached_data["is_active"]
    expires_at_str = cached_data.get("expires_at")
    
    if not is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="短链接已禁用"
        )
    
    # 检查过期
    if expires_at_str:
        try:
            expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
            if expires_at.tzinfo is not None:
                expires_at = expires_at.astimezone(APP_TIMEZONE).replace(tzinfo=None)
        except (ValueError, AttributeError):
            expires_at = None
        
        now = get_app_now_naive()
        if expires_at and expires_at < now:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="短链接已过期"
            )
    
    if not original_url or not original_url.startswith(('http://', 'https://')):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="短链接配置错误：原始URL格式无效"
        )
    
    click_id = generate_click_id_from_timestamp()
    short_link_id = cached_data.get("id")
    if not short_link_id:
        try:
            result = await db.execute(
                select(ShortLink.id).where(ShortLink.short_code == short_code)
            )
            short_link_id = result.scalar()
        except Exception:
            short_link_id = None
    
    request_info = collect_request_info(request) if request else {}
    
    # 如果没有从URL参数传入，从短链接记录中获取offer_id和channel_id
    if not offer_id:
        offer_id = cached_data.get("offer_id")
    if not channel_id:
        channel_id = cached_data.get("channel_id")
    
    final_channel_id = channel_id
    final_offer_id, advertiser_id = await _resolve_offer_id(offer_id, db)
    
    # 创建点击记录
    if short_link_id:
        await _create_click_record(
            click_id, short_link_id, final_offer_id, final_channel_id,
            advertiser_id, request_info, background_tasks
        )
    
    # 更新点击次数
    await increment_click_count_async(short_code)
    
    # 保存原始URL用于检查占位符
    original_url_before_replace = original_url
    
    # 替换占位符并合并参数
    original_url_after_replace = await _replace_short_link_placeholders(
        original_url, click_id, final_offer_id, final_channel_id,
        advertiser_id, request_info, db
    )
    
    final_url = _build_final_url(original_url_before_replace, original_url_after_replace, click_id, offer_id, channel_id,
                                 final_channel_id, request_params, request_info, advertiser_id)
    
    # 打印最终跳转链接详细信息   helong
    original_request_url = str(request.url) if request else "N/A"
    logger.warning("=" * 180)
    logger.warning(f"[短链接重定向] 原始点击URL: {original_request_url}")
    logger.warning(f"[短链接重定向] 短链接代码: {short_code}")
    logger.warning(f"[短链接重定向] 点击ID: {click_id}")
    logger.warning(f"[短链接重定向] Offer ID: {final_offer_id}")
    logger.warning(f"[短链接重定向] 渠道ID: {final_channel_id}")
    logger.warning(f"[短链接重定向] 广告主ID: {advertiser_id}")
    logger.warning(f"[短链接重定向] 点击携带的参数: {request_params}")
    logger.warning(f"[短链接重定向] 原始URL（替换前）: {original_url_before_replace}")
    logger.warning(f"[短链接重定向] 替换占位符后: {original_url_after_replace}")
    logger.warning(f"[短链接重定向] 最终跳转URL: {final_url}")
    logger.warning("=" * 180)
    
    return RedirectResponse(url=final_url, status_code=302)


async def _handle_database_redirect(
    short_code: str,
    offer_id: Optional[int],
    channel_id: Optional[int],
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession,
    request_params: dict
) -> RedirectResponse:
    """
    处理数据库查询的短链接重定向
    
    当短链接数据不在Redis缓存中时，从数据库查询并处理重定向。
    查询完成后会将数据写入缓存，以便后续请求可以命中缓存。
    
    处理流程：
    1. 从数据库查询短链接记录
    2. 验证短链接状态（是否存在、是否激活、是否过期）
    3. 验证并修复原始URL格式（自动添加协议等）
    4. 将短链接数据写入Redis缓存（供后续请求使用）
    5. 生成点击ID
    6. 解析 offer_id 和 channel_id（优先使用URL参数，否则使用数据库记录）
    7. 创建点击记录（异步）
    8. 更新点击次数（异步）
    9. 替换URL中的占位符
    10. 构建最终重定向URL
    11. 记录详细日志
    12. 返回重定向响应
    
    Args:
        short_code: 短链接代码（唯一标识）
        offer_id: 从URL参数获取的Offer ID（可选）
        channel_id: 从URL参数获取的渠道ID（可选）
        request: FastAPI请求对象，用于获取请求信息（IP、User-Agent等）
        background_tasks: FastAPI后台任务对象，用于异步处理点击记录
        db: 数据库会话（用于查询短链接和Offer信息）
        request_params: 用户请求时携带的查询参数字典
    
    Returns:
        RedirectResponse: HTTP 302重定向响应，指向最终的目标URL
    
    Raises:
        HTTPException: 
            - 404: 短链接不存在、已禁用或已过期
            - 500: 原始URL格式无效
    
    性能优化：
    - 查询完成后立即写入缓存，后续请求可以命中缓存
    - 点击记录和点击次数更新都是异步处理，不阻塞重定向响应
    """
    result = await db.execute(
        select(ShortLink).where(ShortLink.short_code == short_code)
    )
    short_link = result.scalars().first()
    
    if not short_link:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"短链接不存在: {short_code}"
        )
    
    if not short_link.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="短链接已禁用"
        )
    
    # 检查过期
    if short_link.expires_at:
        expires_at = short_link.expires_at
        if expires_at.tzinfo is not None:
            expires_at = expires_at.astimezone(APP_TIMEZONE).replace(tzinfo=None)
        now = get_app_now_naive()
        if expires_at < now:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="短链接已过期"
            )
    
    original_url = short_link.original_url
    if not original_url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="短链接配置错误：原始URL为空"
        )
    
    original_url = original_url.strip()
    if not original_url.startswith(('http://', 'https://')):
        if original_url and not original_url.startswith('/'):
            original_url = f"https://{original_url}"
            logger.warning(f"短链接 {short_code} 的原始URL缺少协议，已自动添加https://")
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"短链接配置错误：原始URL格式无效"
            )
    
    # 写入缓存
    await set_short_link_to_cache(short_code, serialize_short_link(short_link))
    
    click_id = generate_click_id_from_timestamp()
    request_info = collect_request_info(request) if request else {}
    
    # 如果没有从URL参数传入，从短链接记录中获取offer_id和channel_id
    if not offer_id:
        offer_id = short_link.offer_id
    if not channel_id:
        channel_id = short_link.channel_id
    
    final_channel_id = channel_id
    final_offer_id, advertiser_id = await _resolve_offer_id(offer_id, db)
    
    # 创建点击记录
    await _create_click_record(
        click_id, short_link.id, final_offer_id, final_channel_id,
        advertiser_id, request_info, background_tasks
    )
    
    # 更新点击次数
    await increment_click_count_async(short_code)
    
    # 保存原始URL用于检查占位符
    original_url_before_replace = original_url
    
    # 替换占位符并合并参数
    original_url_after_replace = await _replace_short_link_placeholders(
        original_url, click_id, final_offer_id, final_channel_id,
        advertiser_id, request_info, db
    )
    
    final_url = _build_final_url(original_url_before_replace, original_url_after_replace, click_id, offer_id, channel_id, final_channel_id, request_params, request_info, advertiser_id)
    
    # 打印最终跳转链接详细信息
    logger.warning("=" * 80)
    logger.warning(f"[短链接重定向] 短链接代码: {short_code}")
    logger.warning(f"[短链接重定向] 原始URL（替换前）: {original_url_before_replace}")
    logger.warning(f"[短链接重定向] 替换占位符后: {original_url_after_replace}")
    logger.warning(f"[短链接重定向] 最终跳转URL: {final_url}")
    logger.warning(f"[短链接重定向] 点击ID: {click_id}")
    logger.warning(f"[短链接重定向] Offer ID: {final_offer_id}")
    logger.warning(f"[短链接重定向] 渠道ID: {final_channel_id}")
    logger.warning(f"[短链接重定向] 广告主ID: {advertiser_id}")
    logger.warning(f"[短链接重定向] 点击携带的参数: {request_params}")
    logger.warning("=" * 80)
    
    return RedirectResponse(url=final_url, status_code=302)


async def _resolve_offer_id(offer_id: Optional[int], db: AsyncSession) -> tuple[Optional[int], Optional[int]]:
    """
    解析Offer ID，返回(offer_id, advertiser_id)
    
    这个函数用于解析和验证Offer ID，并获取对应的广告主ID。
    支持两种查询方式：
    1. 作为主键ID查询（优先）
    2. 作为上游Offer ID查询（如果主键查询失败）
    
    Args:
        offer_id: Offer的ID（可能是主键ID或上游Offer ID）
        db: 数据库会话
    
    Returns:
        tuple[Optional[int], Optional[int]]: 
            - 第一个元素：Offer的主键ID（如果找到）
            - 第二个元素：广告主ID（如果找到Offer）
            如果 offer_id 为 None 或找不到，返回 (None, None)
    
    查询逻辑：
    1. 如果 offer_id 为 None，直接返回 (None, None)
    2. 先尝试作为主键ID查询（Offer.id == offer_id）
    3. 如果找不到，尝试作为上游Offer ID查询（Offer.advertiser_offer_id == offer_id）
    4. 如果找到Offer，返回 (Offer.id, Offer.advertiser_id)
    5. 如果都找不到，返回 (None, None)
    
    异常处理：
    - 查询过程中的异常会被捕获并记录警告日志
    - 异常不会中断主流程，返回 (None, None)
    """
    if not offer_id:
        return None, None
    
    try:
        # 先尝试作为主键ID查询
        offer_result = await db.execute(
            select(Offer).where(Offer.id == offer_id)
        )
        offer = offer_result.scalars().first()
        
        # 如果找不到，尝试作为上游Offer ID查询
        if not offer:
            offer_result = await db.execute(
                select(Offer).where(Offer.advertiser_offer_id == str(offer_id))
            )
            offer = offer_result.scalars().first()
        
        if offer:
            await set_offer_cache(offer.id, offer.advertiser_id, offer.offer_name)
            return offer.id, offer.advertiser_id
    except Exception as e:
        logger.warning(f"查询Offer失败: offer_id={offer_id}, error={e}")
    
    return None, None


async def _create_click_record(
    click_id: str,
    short_link_id: int,
    offer_id: Optional[int],
    publisher_id: Optional[int],
    advertiser_id: Optional[int],
    request_info: dict,
    background_tasks: BackgroundTasks
):
    """
    创建点击记录（异步处理）
    
    这个函数用于创建点击记录，但不阻塞重定向响应。
    点击记录会先尝试加入Redis队列，如果队列已满，则使用FastAPI后台任务处理。
    
    性能优化：
    - 优先使用Redis队列（clicks_queue），批量处理效率更高
    - 如果队列已满，降级到FastAPI后台任务（background_tasks）
    - 异步处理，不阻塞HTTP响应
    
    Args:
        click_id: 系统生成的唯一点击ID
        short_link_id: 短链接的数据库主键ID
        offer_id: Offer的数据库主键ID（可选）
        publisher_id: 渠道（Publisher）的数据库主键ID（可选）
        advertiser_id: 广告主的数据库主键ID（可选）
        request_info: 请求信息字典，包含：
                     - ip: IP地址
                     - os: 操作系统
                     - device_type: 设备类型
                     - country: 国家
                     - user_agent: User-Agent字符串
                     - referer: 来源页面URL
        background_tasks: FastAPI后台任务对象，用于异步处理
    
    处理流程：
    1. 构建点击记录数据字典
    2. 尝试将记录加入Redis队列（clicks_queue）
    3. 如果队列加入成功，记录完成
    4. 如果队列已满或失败，使用FastAPI后台任务处理
    5. 后台任务会在HTTP响应返回后执行，将记录写入数据库
    
    数据字段说明：
    - click_id: 点击的唯一标识
    - short_link_id: 关联的短链接ID
    - offer_id: 关联的Offer ID（用于统计和追踪）
    - publisher_id: 关联的渠道ID（用于统计和追踪）
    - advertiser_id: 关联的广告主ID（用于统计和追踪）
    - click_time: 点击时间（如果队列失败，在后台任务中设置）
    - 其他字段来自 request_info（IP、设备信息等）
    """
    click_data = {
        "click_id": click_id,
        "short_link_id": short_link_id,
        "offer_id": offer_id,
        "publisher_id": publisher_id,
        "advertiser_id": advertiser_id,
        "click_time": get_app_now_naive().isoformat(),
        "ip": request_info.get('ip'),
        "user_agent": request_info.get('user_agent'),
        "referer": request_info.get('referer'),
        "country": None,
        "os": request_info.get('os'),
        "os_version": request_info.get('os_version'),
        "browser": request_info.get('browser'),
        "browser_version": request_info.get('browser_version'),
        "accept_language": request_info.get('accept_language'),
        "accept_encoding": request_info.get('accept_encoding'),
        "is_bot": request_info.get('is_bot', False),
        "device_type": request_info.get('device_type'),
        "device_brand": request_info.get('device_brand'),
        "device_model": request_info.get('device_model'),
        "url_params": request_info.get('url_params'),
        "all_headers": request_info.get('all_headers'),
        "device": request_info.get('device_type')
    }
    
    enqueued = await enqueue_click(click_data)
    if not enqueued:
        click_data['click_time'] = get_app_now_naive()
        background_tasks.add_task(create_click_background, click_data)


def _build_final_url(
    original_url_before_replace: str,
    original_url_after_replace: str,
    click_id: str,
    offer_id: Optional[int],
    channel_id: Optional[int],
    final_channel_id: Optional[int],
    request_params: dict,
    request_info: Optional[dict] = None,
    advertiser_id: Optional[int] = None
) -> str:
    """
    构建最终的重定向URL
    
    这是短链接重定向流程中的核心函数，负责：
    1. 检测原始URL中是否已有占位符（避免重复添加参数）
    2. 处理请求参数中包含占位符的情况（尝试替换或过滤）
    3. 合并所有参数到最终URL中
    
    设计理念：
    - 如果原始URL中已有占位符（如 {click_id}），则占位符会被替换为实际值
    - 如果原始URL中没有占位符，则添加对应的查询参数（如 click_id=xxx）
    - 如果请求参数值中包含占位符，尝试替换；如果无法替换，则过滤掉该参数
    
    Args:
        original_url_before_replace: 替换占位符之前的原始URL
                                    用于检测是否已有占位符，避免重复添加参数
                                    例如：http://example.com?aff_click_id={click_id}
        original_url_after_replace: 替换占位符之后的URL
                                   用于作为基础URL，合并新的查询参数
                                   例如：http://example.com?aff_click_id=abc123
        click_id: 系统生成的唯一点击ID（总是有值）
        offer_id: Offer的数据库主键ID（可选，可能为None）
        channel_id: 渠道ID（从URL参数获取，可能为None）
        final_channel_id: 最终使用的渠道ID（可能来自URL参数或短链接记录）
        request_params: 用户请求时携带的查询参数字典
                       例如：{"test": "value", "param": "{click_id}"}
        request_info: 请求信息字典，包含IP、OS、设备等信息（可选）
        advertiser_id: 广告主的数据库主键ID（可选）
    
    Returns:
        str: 最终的重定向URL，包含所有合并后的查询参数
    
    处理流程：
    1. 检测原始URL中是否已有占位符（click_id、offer_id、channel_id等）
    2. 如果原始URL中没有占位符，准备添加对应的查询参数
    3. 处理请求参数：
       a. 如果参数值包含占位符，尝试替换
       b. 如果所有占位符都能替换，保留参数（使用替换后的值）
       c. 如果有占位符无法识别，过滤掉该参数
    4. 合并所有参数到替换后的URL中
    
    示例：
        输入:
            original_url_before_replace = "http://example.com?aff_click_id={click_id}"
            original_url_after_replace = "http://example.com?aff_click_id=abc123"
            click_id = "abc123"
            request_params = {"test": "value", "param": "{click_id}"}
        输出:
            "http://example.com?aff_click_id=abc123&test=value&param=abc123"
            # 注意：不会重复添加 click_id，因为原始URL中已有占位符
    """
    # ==================== 初始化占位符检测正则表达式 ====================
    # 用于动态检测参数值中的任何 {xxx} 格式占位符
    # 正则说明：\{[a-zA-Z_][a-zA-Z0-9_]*\}
    # - \{ : 匹配左花括号（转义）
    # - [a-zA-Z_] : 第一个字符必须是字母或下划线
    # - [a-zA-Z0-9_]* : 后续字符可以是字母、数字或下划线
    # - \} : 匹配右花括号（转义）
    placeholder_pattern_regex = re.compile(r'\{[a-zA-Z_][a-zA-Z0-9_]*\}')
    
    # ==================== 检测原始URL中的占位符 ====================
    # 如果原始URL中已有占位符（如 {click_id}），则占位符会被替换为实际值
    # 此时不需要再添加对应的查询参数，避免重复
    # 例如：原始URL = "http://example.com?aff_click_id={click_id}"
    #      替换后 = "http://example.com?aff_click_id=abc123"
    #      不需要再添加 click_id=abc123
    placeholder_params_to_check = {
        'click_id': ['{click_id}', '{clickId}', '{clickid}', '{ClickId}', '{CLICK_ID}', '{aff_click_id}', '{AFF_CLICK_ID}'],
        'offer_id': ['{offer_id}', '{offerId}', '{offerid}', '{OfferId}', '{OFFER_ID}'],
        'channel_id': ['{channel_id}', '{channelId}', '{channelid}', '{ChannelId}', '{CHANNEL_ID}', '{sub_affid}', '{SUB_AFFID}'],
        'publisher_id': ['{publisher_id}', '{publisherId}', '{publisherid}', '{PublisherId}', '{PUBLISHER_ID}'],
    }
    
    # 检测每个参数是否在原始URL中有占位符
    has_placeholder = {}
    for param_name, placeholder_variants in placeholder_params_to_check.items():
        # 检查原始URL中是否包含任何占位符变体
        has_placeholder[param_name] = any(variant in original_url_before_replace for variant in placeholder_variants)
    
    # ==================== 准备要合并的参数 ====================
    # 这个字典将包含所有要添加到最终URL的查询参数
    request_params_with_click = {}
    
    # ==================== 添加系统参数（如果原始URL中没有占位符） ====================
    # 如果原始URL中没有占位符，需要添加对应的查询参数
    # 例如：原始URL = "http://example.com?test=1"
    #      需要添加 click_id=abc123
    for param_name, has_placeholder_flag in has_placeholder.items():
        if not has_placeholder_flag:
            # 占位符不存在，需要添加查询参数
            if param_name == 'click_id':
                # 总是添加 click_id（因为总是有值）
                request_params_with_click['click_id'] = click_id
            elif param_name == 'offer_id' and offer_id:
                # 只有当 offer_id 有值时才添加
                request_params_with_click['offer_id'] = offer_id
            elif param_name == 'channel_id' and final_channel_id:
                # channel_id 和 publisher_id 是同一个概念（都代表渠道ID）
                # 只有当 channel_id 有值且原始URL中没有 publisher_id 占位符时才添加
                # （如果原始URL中有 {publisher_id} 占位符，它会被替换为 channel_id 的值，避免重复）
                if not has_placeholder.get('publisher_id', False):
                    request_params_with_click['channel_id'] = final_channel_id
            # 注意：channel_id 和 publisher_id 是同一个概念，只使用 channel_id
            # 不再自动添加 publisher_id 参数，避免在最终URL中同时出现两个相同含义的参数
    
    # ==================== 处理用户请求参数 ====================
    # 用户请求时可能携带额外的查询参数，需要合并到最终URL中
    # 但需要处理以下情况：
    # 1. 如果参数值包含占位符，尝试替换；如果无法替换，过滤掉
    # 2. 如果参数在原始URL中已有占位符，跳过（避免重复）
    # 3. 处理 channel_id 和 publisher_id 的互斥关系
    
    # 参数名映射表：用于识别请求参数对应的系统参数
    # 例如：aff_click_id -> click_id, sub_affid -> channel_id
    param_name_mapping = {
        'click_id': ['click_id', 'aff_click_id', 'clickid', 'clickId', 'CLICK_ID', 'AFF_CLICK_ID'],
        'offer_id': ['offer_id', 'offerid', 'offerId', 'OFFER_ID'],
        'channel_id': ['channel_id', 'sub_affid', 'channelid', 'channelId', 'CHANNEL_ID', 'SUB_AFFID'],
        'publisher_id': ['publisher_id', 'publisherid', 'publisherId', 'PUBLISHER_ID'],
    }
    
    # 记录被过滤掉的参数（包含无法识别的占位符的参数）
    filtered_params = []
    
    # 构建用于替换占位符的请求信息字典
    # 如果 request_info 为空，使用默认空值
    request_info_for_replace = request_info if request_info else {
        'ip': '',
        'os': '',
        'device_type': '',
        'country': '',
        'user_agent': '',
        'referer': '',
    }
    
    # ==================== 遍历用户请求参数 ====================
    for key, value in request_params.items():
        key_lower = key.lower()  # 统一转为小写
        
        # 步骤1：检查参数值中是否包含占位符
        # 将参数值转为字符串（处理列表类型）
        param_value_str = str(value) if not isinstance(value, list) else str(value[0]) if value else ''
        # 使用正则表达式检测是否包含任何 {xxx} 格式的占位符
        contains_placeholder = bool(placeholder_pattern_regex.search(param_value_str))
        
        if contains_placeholder:
            # 步骤2：参数值包含占位符，尝试替换
            # 调用 _replace_param_value_placeholders 尝试替换所有占位符
            replaced_value, all_replaced = _replace_param_value_placeholders(
                param_value_str,
                click_id,
                offer_id,
                final_channel_id,
                advertiser_id if advertiser_id is not None else None,
                request_info_for_replace
            )
            
            if all_replaced:
                # 步骤3a：所有占位符都被成功替换
                # 保留参数，使用替换后的值
                logger.info(f"[构建最终URL] 参数 {key} 中的占位符已替换: {param_value_str} -> {replaced_value}")
                request_params_with_click[key_lower] = replaced_value
            else:
                # 步骤3b：有占位符无法识别或值为空
                # 丢弃该参数，避免未替换的占位符出现在最终URL中
                filtered_params.append(f"{key}={value}")
                logger.warning(f"[构建最终URL] 跳过参数 {key}={value}，因为参数值中包含无法识别的占位符")
            continue  # 处理下一个参数
        
        # 步骤4：参数值不包含占位符，检查是否需要跳过
        # 查找该参数对应的系统参数名（通过别名映射）
        corresponding_param_name = None
        for param_name, possible_names in param_name_mapping.items():
            if key_lower in [name.lower() for name in possible_names]:
                corresponding_param_name = param_name
                break
        
        # 步骤5：如果该参数在原始URL中使用了占位符，跳过
        # 因为占位符已经被替换为实际值，不需要再添加查询参数
        # 例如：原始URL = "http://example.com?aff_click_id={click_id}"
        #      替换后 = "http://example.com?aff_click_id=abc123"
        #      如果请求参数中有 click_id=abc123，应该跳过（避免重复）
        if corresponding_param_name and has_placeholder.get(corresponding_param_name, False):
            continue
        
        # 步骤6：处理 channel_id 和 publisher_id 的互斥关系
        # channel_id 和 publisher_id 是同一个概念（都代表渠道ID）
        # 如果原始URL中已有 publisher_id 的占位符，跳过用户请求中的 channel_id 参数（避免重复）
        if key_lower == 'channel_id' and has_placeholder.get('publisher_id', False):
            continue
        # 如果原始URL中已有 channel_id 的占位符，跳过用户请求中的 publisher_id 参数（避免重复）
        if key_lower == 'publisher_id' and has_placeholder.get('channel_id', False):
            continue
        # 注意：如果用户在请求URL中明确提供了 publisher_id，会保留它
        # 系统不会自动添加 publisher_id（只会在原始URL有占位符时替换）
        
        # 步骤7：参数通过所有检查，添加到合并列表
        request_params_with_click[key_lower] = value
    
    # ==================== 记录过滤信息 ====================
    # 如果有被过滤掉的参数，记录日志（便于调试）
    if filtered_params:
        logger.info(f"[构建最终URL] 已过滤掉包含占位符的参数: {', '.join(filtered_params)}")
    
    # ==================== 合并参数到最终URL ====================
    # 使用 merge_url_params 函数将准备好的参数合并到替换后的URL中
    # merge_url_params 会处理参数冲突、占位符检测、参数排序等
    return merge_url_params(original_url_after_replace, request_params_with_click)


