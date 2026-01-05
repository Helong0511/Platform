"""
Skymobi定时任务模块
功能：从Skymobi API获取广告数据，检查重复后插入到数据库
"""
import asyncio
import logging
from datetime import datetime, timedelta
import pytz
import httpx

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.ad_data_processor import process_api_ad_data
from app.core.auto_bot import send_telegram_message
from app.scheduler_module.task_names import SKYMOBI_API_TASK_NAME

# 获取当前模块的日志记录器
logger = logging.getLogger(__name__)

# 任务执行结果存储（用于保存到last_error字段）
# key: 任务名称, value: 执行结果信息
_task_results: dict[str, str] = {}


def get_task_result(task_name: str) -> str | None:
    """获取任务执行结果"""
    return _task_results.get(task_name)


def set_task_result(task_name: str, result: str) -> None:
    """设置任务执行结果"""
    _task_results[task_name] = result


# 应用时区配置（从统一配置读取）
# 用于将本地时间转换为标准时区
APP_TIMEZONE = pytz.timezone(settings.TIMEZONE)

# ========== Skymobi API配置 ==========
api_id = '10177'
api_key = '67b7c7fac2154bb8f59546d9b23058c9'


async def skymobi_api_task(
    start_date: str | None = None,
    end_date: str | None = None
) -> None:
    """
    Skymobi API定时任务主函数
    
    参数:
        start_date: 可选，日期 (格式: YYYY-MM-DD)，如果不提供则根据时间自动选择
        end_date: 可选，忽略（Skymobi API只使用一个日期参数）
    """
    # 获取应用配置时区的当前时间（用于日志记录）
    app_time = datetime.now(APP_TIMEZONE)
    current_time_str = app_time.strftime("%Y-%m-%d %H:%M:%S")

    # 记录任务开始执行的日志（只记录一次）
    logger.info(f"{SKYMOBI_API_TASK_NAME} 开始执行 - {current_time_str}（时区: {settings.TIMEZONE}）")

    try:
        # ============================================
        # 任务主逻辑开始
        # ============================================

        # 构建Skymobi API请求参数
        if start_date:
            # 使用传入的日期（Skymobi只使用一个日期）
            date_str = start_date
        else:
            # 原有的自动计算逻辑
            app_now = datetime.now(APP_TIMEZONE)
            app_yesterday = app_now - timedelta(days=1)
            yesterday_str = app_yesterday.strftime("%Y-%m-%d")
            today_str = app_now.strftime("%Y-%m-%d")
            
            if 0 <= app_now.hour <= 8:
                date_str = yesterday_str
            else:
                date_str = today_str
        
        Skymobi_url = f'https://crm.skymobi.online/api/adxh5?apikey={api_key}&date={date_str}&uid={api_id}&page=1&limit=1000'

        # 使用异步HTTP客户端调用Skymobi API
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                # 发送POST请求到Skymobi API
                response = await client.post(Skymobi_url)

                # 检查HTTP响应状态码
                if response.status_code != 200:
                    error_text = response.text[:500]  # 限制错误文本长度
                    logger.error(f'Skymobi API HTTP错误: 状态码={response.status_code}, 响应内容={error_text}')
                    raise Exception(f'API HTTP错误: 状态码={response.status_code}, 响应内容={error_text[:100]}')

                # 解析JSON响应
                try:
                    json_data = response.json()
                except Exception as json_error:
                    error_text = response.text[:500]  # 限制错误文本长度
                    logger.error(f'Skymobi API JSON解析错误: {str(json_error)}, 响应内容={error_text}')
                    raise Exception(f'API响应格式错误: 无法解析JSON, 响应内容={error_text[:100]}')

                # 记录API响应的详细信息（用于调试和排查问题）
                # 使用info级别确保能看到响应内容
                logger.info(f'Skymobi API响应: {json_data}')
                logger.debug(f'Skymobi API响应详情: ret={json_data.get("ret")}, msg={json_data.get("msg")}')

                # 检查json_data是否为空或None
                if not json_data:
                    logger.error(f'Skymobi API返回空响应: {response.text[:500]}')
                    raise Exception(f'API返回空响应: {response.text[:100]}')

                # 检查API响应状态
                # Skymobi API使用ret字段：0表示成功，其他值表示失败
                api_ret = json_data.get('ret')
                api_msg = json_data.get('msg', '')

                # 判断API是否成功：ret=0 表示成功
                if api_ret == 0:
                    # API调用成功，获取数据列表
                    # Skymobi API数据直接在list字段中
                    data = json_data.get('list', [])

                    # 如果返回的数据列表不为空，开始处理数据
                    if data:
                        # 创建数据库会话，所有数据操作都在这个会话中进行
                        # 使用上下文管理器确保会话正确关闭
                        async with AsyncSessionLocal() as db:
                            # ========== 获取管理员用户（用于产品查找/创建） ==========
                            from app.scheduler_module.task_utils import get_admin_user

                            admin_user = await get_admin_user(db)
                            if not admin_user:
                                logger.error("未找到管理员用户，无法处理产品，跳过本次任务")
                                return

                            result = await process_api_ad_data(
                                data=data,
                                db=db,
                                admin_user=admin_user,
                                source="Skymobi定时任务",
                                field_mapping={
                                    # 数据日期
                                    "date": "dt",

                                    # 产品名称
                                    "product_name": "link",

                                    # 国家代码
                                    "country_code": "country",

                                    # 请求数
                                    "request_count": "req",

                                    # 匹配数
                                    "match_count": "req_ef",

                                    # 展示数
                                    "display_count": "imp",

                                    # 点击数
                                    "click_count": "click",

                                    # 收益
                                    "revenue_before_deduct": "income",

                                    # ecpm
                                    "ecpm_before_deduct": "ecpm",

                                    # 覆盖率（可选，会自动计算）
                                    "coverage_rate": "coverage_rate",

                                    # 展示率（可选，会自动计算）
                                    "display_rate": "display_rate",

                                    # 点击率（可选，会自动计算）
                                    "click_rate": "click_rate"
                                }
                            )

                            # ========== 提交事务 ==========
                            # 所有数据都添加到会话后，一次性提交到数据库
                            # 这样可以提高性能，并且如果某条数据出错，可以回滚整个事务
                            try:
                                logger.info("开始提交主事务...")
                                await db.commit()
                                logger.info("主事务提交成功")
                            except Exception as commit_error:
                                # 提交失败，回滚事务
                                await db.rollback()
                                logger.error(f"数据提交失败，已回滚: {str(commit_error)}", exc_info=True)
                                raise Exception(f"数据提交失败: {str(commit_error)}")

                            # 记录数据导入完成的统计信息
                            inserted_count = result.get("inserted_count", 0)
                            updated_count = result.get("updated_count", 0)
                            skipped_count = result.get("skipped_count", 0)
                            error_count = result.get("error_count", 0)

                            # 使用工具函数格式化结果摘要
                            from app.scheduler_module.task_utils import format_result_summary
                            result_summary = format_result_summary(
                                inserted=inserted_count,
                                updated=updated_count,
                                skipped=skipped_count,
                                error=error_count
                            )
                            # 只记录一次，使用info级别（定时任务调度器会记录执行结果）
                            logger.info(f"数据导入完成: {result_summary}")

                            # 发送 Telegram 通知（仅在成功导入或更新数据时）
                            if inserted_count > 0 or updated_count > 0:
                                # 构建通知消息
                                telegram_msg = f"⏰ Skymobi 定时任务执行完成\n\n"
                                telegram_msg += f"执行时间: {current_time_str}\n"
                                telegram_msg += f"✅ 成功插入: {inserted_count} 条\n"
                                telegram_msg += f"✅ 成功更新: {updated_count} 条"

                                if skipped_count > 0:
                                    telegram_msg += f"\n⏭️ 跳过重复: {skipped_count} 条"
                                if error_count > 0:
                                    telegram_msg += f"\n❌ 错误: {error_count} 条"

                                # 使用 await 发送消息，设置超时避免阻塞太久
                                # send_telegram_message 内部已有完整的容错处理
                                try:
                                    await asyncio.wait_for(
                                        send_telegram_message(telegram_msg),
                                        timeout=5.0
                                    )
                                    logger.info(
                                        f"Telegram 通知发送成功: Skymobi任务, 插入:{inserted_count}, 更新:{updated_count}")
                                except asyncio.TimeoutError:
                                    logger.warning(f"发送 Telegram 通知超时: Skymobi任务")
                                # 其他异常已在 send_telegram_message 内部处理，这里不需要捕获

                            # 保存执行结果到全局存储（用于保存到last_error字段）
                            set_task_result(SKYMOBI_API_TASK_NAME, f"执行成功: {result_summary}")
                    else:
                        # API返回成功，但数据列表为空
                        logger.info('暂无产品数据')
                        logger.warning('[定时任务执行] 暂无产品数据')
                        # 保存执行结果到全局存储
                        set_task_result(SKYMOBI_API_TASK_NAME, "执行成功: 暂无产品数据")
                else:
                    # API返回错误状态（ret != 0）
                    api_ret = json_data.get('ret')
                    api_msg = json_data.get('msg', '未知错误')

                    # 构建错误详情
                    error_details = f'ret={api_ret}'
                    if api_msg and api_msg != '未知错误':
                        error_details += f', msg={api_msg}'

                    # 记录完整的错误信息
                    logger.error(f'Skymobi API业务错误: {error_details}')
                    logger.warning(f'[定时任务执行] API错误: {error_details}')
                    # 记录完整的响应内容（用于调试）
                    logger.info(f'Skymobi API完整响应: {json_data}')
                    # 抛出异常，让上层错误处理机制捕获
                    raise Exception(f'API错误: {error_details}')

        except httpx.TimeoutException as timeout_error:
            logger.error(f'Skymobi API请求超时: {str(timeout_error)}')
            raise Exception(f'API请求超时: 超过20秒未响应')
        except httpx.RequestError as request_error:
            logger.error(f'Skymobi API请求错误: {str(request_error)}')
            raise Exception(f'API请求失败: {str(request_error)}')

    except Exception as e:
        # ========== 全局错误处理 ==========

        # 捕获任务执行过程中的任何异常
        # 注意：如果任务执行失败，异常会被捕获并记录
        # 定时任务调度器的锁机制会自动释放，错误信息会保存到数据库

        error_msg = f"{SKYMOBI_API_TASK_NAME} 执行失败: {str(e)}"
        # 记录详细错误信息（包括完整的堆栈跟踪）
        logger.error(error_msg, exc_info=True)
        # 同时使用 logger.warning 确保即使日志级别设置为 WARNING 也能看到错误信息
        logger.warning(f"[Skymobi获取广告数据] {error_msg}")

        # 重新抛出异常，让定时任务调度器的锁机制能够记录错误状态
        # 这样可以在数据库中标记任务执行失败，便于后续排查问题
        raise
