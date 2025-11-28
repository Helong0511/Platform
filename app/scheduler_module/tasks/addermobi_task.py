"""
Addermobi定时任务模块
功能：从Addermobi API获取广告数据，检查重复后插入到数据库
"""
import asyncio
import json
import logging
from datetime import datetime, timedelta
import pytz
import httpx

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.ad_data_processor import process_api_ad_data
from app.core.auto_bot import send_telegram_message
from app.scheduler_module.task_names import ADDERMOBI_API_TASK_NAME

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


async def addermobi_api_task(
    start_date: str | None = None,
    end_date: str | None = None
) -> None:
    """
    Addermobi定时任务主函数
    
    参数:
        start_date: 可选，起始日期 (格式: YYYY-MM-DD)，如果不提供则根据时间自动选择
        end_date: 可选，结束日期 (格式: YYYY-MM-DD)，如果不提供则使用start_date
    """
    # ========== Addermobi API配置 ==========
    # HTTP请求头配置
    Headers = {'Content-Type': 'application/json'}

    username = 'Leadwin'
    password = 'lw145667'

    # 验证凭证是否配置
    if not username or not password:
        error_msg = "Addermobi API 凭证未配置，请设置 ADDERMOBI_API_USERNAME 和 ADDERMOBI_API_PASSWORD 环境变量"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # 获取应用配置时区的当前时间（用于日志记录）
    app_time = datetime.now(APP_TIMEZONE)
    current_time_str = app_time.strftime("%Y-%m-%d %H:%M:%S")

    # 记录任务开始执行的日志
    # 使用 logger.warning 确保即使日志级别设置为 WARNING 也能看到执行信息
    logger.info(f"{ADDERMOBI_API_TASK_NAME} 开始执行 - {current_time_str}（时区: {settings.TIMEZONE}）")
    logger.warning(
        f"[Addermobi API获取数据] 每隔10分钟执行一次 开始执行 - {current_time_str}（时区: {settings.TIMEZONE}）")

    try:
        # ============================================
        # 任务主逻辑开始
        # ============================================

        token_post = {
            "userName": username,
            "password": password
        }

        try:
            # 创建 HTTP 客户端
            async with httpx.AsyncClient(timeout=20, verify=False) as token:
                t_res = await token.post('https://api.addermobi.com/api/User/loginApi', headers=Headers,
                                         json=token_post)

                if t_res.status_code != 200:
                    error_text = t_res.text[:500]  # 限制错误文本长度
                    logger.error(f'Addermobi API HTTP错误: 状态码={t_res.status_code}, 响应内容={error_text}')
                    raise Exception(f'API HTTP错误: 状态码={t_res.status_code}, 响应内容={error_text[:100]}')

                # 解析JSON响应
                try:
                    json_data = t_res.json()
                except Exception as json_error:
                    error_text = t_res.text[:500]  # 限制错误文本长度
                    logger.error(f'Addermobi API JSON解析错误: {str(json_error)}, 响应内容={error_text}')
                    raise Exception(f'API响应格式错误: 无法解析JSON, 响应内容={error_text[:100]}')

                # 记录API响应的详细信息（用于调试和排查问题）
                logger.info(f'Addermobi API响应: {json_data}')
                logger.debug(f'Addermobi API响应详情: state={json_data.get("state")}, code={json_data.get("code")}')

                # 检查json_data是否为空或None
                if not json_data:
                    error_text = t_res.text[:500]
                    logger.error(f'Addermobi API返回空响应: {error_text}')
                    raise Exception(f'API返回空响应: {error_text[:100]}')

                # 获取访问令牌（可能在 data.token 或直接在 token 字段中）
                access_token = None
                if 'data' in json_data and isinstance(json_data['data'], dict):
                    access_token = json_data['data'].get('token') or json_data['data'].get('access_token')
                else:
                    access_token = json_data.get('token') or json_data.get('access_token')

                if not access_token:
                    logger.error(f'Addermobi API返回的响应中缺少 access_token: {json_data}')
                    raise Exception(f'API响应中缺少 access_token')

                Headers['Authorization'] = f'Bearer {access_token}'
        except httpx.TimeoutException as timeout_error:
            logger.error(f'Addermobi API获取 token 请求超时: {str(timeout_error)}')
            raise Exception(f'API请求超时: 超过20秒未响应')
        except httpx.RequestError as request_error:
            logger.error(f'Addermobi API获取token请求错误: {str(request_error)}')
            raise Exception(f'Addermobi API获取token请求失败: {str(request_error)}')

        # 修改日期计算逻辑
        if start_date:
            # 使用传入的日期
            if end_date:
                start_date_str = start_date
                end_date_str = end_date
            else:
                # 如果没有提供end_date，使用start_date
                start_date_str = start_date
                end_date_str = start_date
        else:
            # 原有的自动计算逻辑
            app_now = datetime.now(APP_TIMEZONE)
            app_yesterday = app_now - timedelta(days=1)
            yesterday_str = app_yesterday.strftime("%Y-%m-%d")
            today_str = app_now.strftime("%Y-%m-%d")
            
            if 0 <= app_now.hour <= 8:
                start_date_str = yesterday_str
                end_date_str = yesterday_str
            else:
                start_date_str = today_str
                end_date_str = today_str
        
        # Addermobi API使用两个条件：大于等于起始日期，小于等于结束日期
        p1 = [
            {"name": "Revenue_time", "value": start_date_str, "displayType": "thanorequal"},
            {"name": "Revenue_time", "value": end_date_str, "displayType": "lessorequal"}
        ]

        tbsj_params = {
            "page": 1,
            "rows": 1000,
            "sort": "Revenue_time,Product_id",
            "order": "desc",
            "wheres": json.dumps(p1)
        }
        # 使用异步HTTP客户端调用Addermobi API
        try:
            # 创建 HTTP 客户端
            async with httpx.AsyncClient(timeout=20, verify=False) as client:
                # 发送POST请求到Addermobi API
                response = await client.post(
                    url='https://api.addermobi.com/api/Revenue_DetailReports/GetData',
                    headers=Headers,
                    json=tbsj_params
                )

                # 检查HTTP响应状态码
                if response.status_code != 200:
                    error_text = response.text[:500]  # 限制错误文本长度
                    logger.error(f'Addermobi API HTTP错误: 状态码={response.status_code}, 响应内容={error_text}')
                    raise Exception(f'API HTTP错误: 状态码={response.status_code}, 响应内容={error_text[:100]}')

                # 解析JSON响应
                try:
                    json_data = response.json()
                except Exception as json_error:
                    error_text = response.text[:500]  # 限制错误文本长度
                    logger.error(f'Addermobi API JSON解析错误: {str(json_error)}, 响应内容={error_text}')
                    raise Exception(f'API响应格式错误: 无法解析JSON, 响应内容={error_text[:100]}')

                # 记录API响应的详细信息（用于调试和排查问题）
                # 使用info级别确保能看到响应内容
                logger.info(f'Addermobi API响应: {json_data}')
                logger.debug(f'Addermobi API响应详情: state={json_data.get("state")}, code={json_data.get("code")}')

                # 检查json_data是否为空或None
                if not json_data:
                    logger.error(f'Addermobi API返回空响应: {response.text[:500]}')
                    raise Exception(f'API返回空响应: {response.text[:100]}')

                # 检查API响应状态
                # Addermobi API使用code字段：20000表示成功，其他值表示失败

                api_code = json_data.get('status')  # 获取code字段

                # 判断API是否成功：code=0表示成功
                if api_code == 0:
                    # API调用成功，获取数据列表
                    # Addermobi API数据在 rows 字段中（可能是列表或字典）
                    ad_data = None
                    if 'rows' in json_data:
                        rows_value = json_data['rows']
                        # 如果 rows 是列表，直接使用
                        if isinstance(rows_value, list):
                            ad_data = rows_value
                        # 如果 rows 是字典，尝试获取其中的列表字段
                        elif isinstance(rows_value, dict):
                            # 尝试常见的列表字段名
                            ad_data = rows_value.get('list', rows_value.get('items', rows_value.get('data', [])))
                        else:
                            ad_data = []
                    else:
                        # 如果没有 rows 字段，尝试其他可能的字段
                        ad_data = json_data.get('data', json_data.get('list', []))

                    # 如果返回的数据列表不为空，开始处理数据
                    if ad_data:
                        # 创建数据库会话，所有数据操作都在这个会话中进行
                        # 使用上下文管理器确保会话正确关闭
                        async with AsyncSessionLocal() as db:
                            # ========== 获取管理员用户（用于产品查找/创建） ==========
                            from app.scheduler_module.task_utils import get_admin_user

                            admin_user = await get_admin_user(db)
                            if not admin_user:
                                logger.error("未找到管理员用户，无法处理产品，跳过本次任务")
                                return

                            # ========== 数据预处理：修正匹配数 ==========
                            # 如果匹配数为0但覆盖率不为0，则计算：匹配数 = 请求数 * 覆盖率
                            for item in ad_data:
                                try:
                                    # 获取匹配数、请求数和覆盖率
                                    match_count = item.get("MatchedAdRequests", 0) or 0
                                    request_count = item.get("AdRequests", 0) or 0
                                    coverage_rate = item.get("AdRequestsCoverage", 0) or 0

                                    # 尝试转换为数值类型
                                    try:
                                        match_count = float(match_count) if match_count else 0
                                        request_count = float(request_count) if request_count else 0
                                        coverage_rate = float(coverage_rate) if coverage_rate else 0
                                    except (ValueError, TypeError):
                                        continue

                                    # 如果匹配数为0但覆盖率不为0，计算匹配数
                                    if match_count == 0 and coverage_rate != 0 and request_count > 0:
                                        calculated_match_count = request_count * coverage_rate
                                        item["MatchedAdRequests"] = int(calculated_match_count)
                                        logger.debug(
                                            f"修正匹配数: 请求数={request_count}, 覆盖率={coverage_rate}, "
                                            f"原匹配数=0, 计算后匹配数={calculated_match_count:.2f}"
                                        )
                                except Exception as e:
                                    # 单条数据处理失败不影响其他数据
                                    logger.warning(f"预处理数据项时出错: {str(e)}")
                                    continue

                            # ========== 使用标准化的数据处理函数 ==========
                            result = await process_api_ad_data(
                                data=ad_data,
                                db=db,
                                admin_user=admin_user,
                                source="Addermobi定时任务",
                                field_mapping={
                                    # 数据日期
                                    "date": "Revenue_time",

                                    # 产品名称
                                    "product_name": "link",

                                    # 国家代码
                                    "country_code": "Country_Code",

                                    # 请求数
                                    "request_count": "AdRequests",

                                    # 匹配数
                                    "match_count": "MatchedAdRequests",

                                    # 展示数
                                    "display_count": "Impressions",

                                    # 点击数
                                    "click_count": "Clicks",

                                    # CPC
                                    "cpc": "CPC",

                                    # ecpm
                                    "ecpm_before_deduct": "eCPM",

                                    # 覆盖率（可选，会自动计算）
                                    "coverage_rate": "AdRequestsCoverage",

                                    # 展示率（可选，会自动计算）
                                    "display_rate": "ad_impression_rate",

                                    # 点击率（可选，会自动计算）
                                    "click_rate": "ctr",

                                    # 收益
                                    "revenue_before_deduct": "EstimatedEarnings"
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
                            logger.info(f"数据导入完成: {result_summary}")
                            # 使用warning级别确保日志可见
                            logger.warning(f"[定时任务执行] 数据导入完成: {result_summary}")

                            # 发送 Telegram 通知（仅在成功导入或更新数据时）
                            if inserted_count > 0 or updated_count > 0:
                                # 构建通知消息
                                telegram_msg = f"⏰ Addermobi 定时任务执行完成\n\n"
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
                                        f"Telegram 通知发送成功: Addermobi任务, 插入:{inserted_count}, 更新:{updated_count}")
                                except asyncio.TimeoutError:
                                    logger.warning(f"发送 Telegram 通知超时: Addermobi API获取数据任务")
                                # 其他异常已在 send_telegram_message 内部处理，这里不需要捕获

                            # 保存执行结果到全局存储（用于保存到last_error字段）
                            set_task_result(ADDERMOBI_API_TASK_NAME, f"执行成功: {result_summary}")
                    else:
                        # API返回成功，但数据列表为空
                        logger.info('暂无产品数据')
                        logger.warning('[定时任务执行] 暂无产品数据')
                        # 保存执行结果到全局存储
                        set_task_result(ADDERMOBI_API_TASK_NAME, "执行成功: 暂无产品数据")
                else:
                    # API返回错误状态（state != 'ok' 或 code != 200）
                    api_state = json_data.get('state')
                    api_code = json_data.get('code')
                    error_message = json_data.get('message', json_data.get('msg', '未知错误'))

                    # 构建错误详情
                    if api_state:
                        error_details = f'state={api_state}'
                        if api_code:
                            error_details += f', code={api_code}'
                        if error_message and error_message != '未知错误':
                            error_details += f', message={error_message}'
                    elif api_code:
                        error_details = f'code={api_code}'
                        if error_message and error_message != '未知错误':
                            error_details += f', message={error_message}'
                    else:
                        # 既没有state也没有code，说明响应格式异常
                        logger.error(
                            f'Addermobi API获取数据响应格式异常: 缺少state和code字段, 完整响应={json_data}')
                        logger.warning(f'[Addermobi API获取数据定时任务执行] API响应格式异常: 缺少state和code字段')
                        logger.info(f'Addermobi API获取数据完整响应内容: {json_data}')
                        raise Exception(f'API响应格式异常: 缺少state和code字段, 响应内容={str(json_data)[:200]}')

                    # 记录完整的错误信息
                    logger.error(f'Addermobi API获取数据业务错误: {error_details}')
                    logger.warning(f'[Addermobi API获取数据 定时任务执行] API错误: {error_details}')
                    # 记录完整的响应内容（用于调试）
                    logger.info(f'Addermobi API获取数据完整响应: {json_data}')
                    # 抛出异常，让上层错误处理机制捕获
                    raise Exception(f'API错误: {error_details}')

        except httpx.TimeoutException as timeout_error:
            logger.error(f'Addermobi API获取数据请求超时: {str(timeout_error)}')
            raise Exception(f'API请求超时: 超过20秒未响应')
        except httpx.RequestError as request_error:
            logger.error(f'Addermobi API获取数据请求错误: {str(request_error)}')
            raise Exception(f'Addermobi API获取数据请求失败: {str(request_error)}')

    except Exception as e:
        # ========== 全局错误处理 ==========
        error_msg = f"{ADDERMOBI_API_TASK_NAME} 执行失败: {str(e)}"
        # 记录详细错误信息（包括完整的堆栈跟踪）
        logger.error(error_msg, exc_info=True)
        # 同时使用 logger.warning 确保即使日志级别设置为 WARNING 也能看到错误信息
        logger.warning(f"[Addermobi API获取数据] {error_msg}")
        raise
