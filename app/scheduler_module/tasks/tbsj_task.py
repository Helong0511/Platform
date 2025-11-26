import httpx  # 异步HTTP客户端，用于调用外部API
import logging  # 日志记录模块
import asyncio  # 异步操作支持
from datetime import datetime, timedelta  # 日期时间处理
import pytz  # 时区处理
from app.core.config import settings  # 应用配置（含时区等）
from app.core.database import AsyncSessionLocal  # 异步数据库会话工厂
from app.models.models import User, UserRole  # 数据模型
from sqlalchemy import select  # SQLAlchemy查询构建器
from app.core.ad_data_processor import process_api_ad_data  # 标准化的API数据处理函数
from app.core.auto_bot import send_telegram_message  # Telegram消息发送
from app.scheduler_module.task_names import TBSJ_API_TASK_NAME  # 任务名称常量

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




async def tbsj_api_task() -> None:
    """
    yangyangdeyi定时任务主函数
    
    功能说明：
    1. 从yangyangdeyi API获取昨天的广告数据
    2. 对每条数据进行验证和重复检查
    3. 将新数据插入到数据库的ad_data表中
    4. 根据产品的减扣比例自动计算减扣后的eCPM和收益
    
    处理流程：
    - 调用yangyangdeyi API获取数据
    - 遍历返回的数据列表
    - 验证日期和产品名称
    - 查找对应的产品记录
    - 检查是否已存在相同日期和产品的数据（防重复）
    - 解析数值字段并计算减扣后的值
    - 插入新数据到数据库
    
    注意：
    - 这是异步函数，可以直接使用await
    - 所有数据库操作都在事务中执行，确保数据一致性
    - 单条数据出错不会影响其他数据的处理
    """
    # yangyangdeyi API获取数据 配置

    # HTTP请求头配置
    Headers = {'Content-Type': 'application/json;charset=utf-8'}

    # 请求地址
    tbsj_url = 'https://data.tongbaishijia.com/api/thirdservice'

    # 从环境变量获取用户名和密码
    username = 'BOFIT'
    password = '5e2296fa9fd1434bf8a60c03cf745ce9'
    
    # 验证凭证是否配置
    if not username or not password:
        error_msg = "TBSJ API 凭证未配置，请设置 TBSJ_API_USERNAME 和 TBSJ_API_PASSWORD 环境变量"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # 获取应用配置时区的当前时间（用于日志记录）
    app_time = datetime.now()
    current_time_str = app_time.strftime("%Y-%m-%d %H:%M:%S")

    # 记录任务开始执行的日志
    # 使用 logger.warning 确保即使日志级别设置为 WARNING 也能看到执行信息
    logger.info(f"{TBSJ_API_TASK_NAME} 开始执行 - {current_time_str}（时区: {settings.TIMEZONE}）")
    logger.warning(
        f"[yangyangdeyi API获取数据] 每隔10分钟执行一次 开始执行 - {current_time_str}（时区: {settings.TIMEZONE}）")

    try:
        # ============================================
        # 任务主逻辑开始
        # ============================================

        token_post = {
            "username": username,
            "password": password
        }

        try:
            # 创建 HTTP 客户端
            async with httpx.AsyncClient(timeout=20, verify=False) as token:
                t_res = await token.post(tbsj_url + '/token', headers=Headers, json=token_post)

                if t_res.status_code != 200:
                    error_text = t_res.text[:500]  # 限制错误文本长度
                    logger.error(f'yangyangdeyi API HTTP错误: 状态码={t_res.status_code}, 响应内容={error_text}')
                    raise Exception(f'API HTTP错误: 状态码={t_res.status_code}, 响应内容={error_text[:100]}')

                # 解析JSON响应
                try:
                    json_data = t_res.json()
                except Exception as json_error:
                    error_text = t_res.text[:500]  # 限制错误文本长度
                    logger.error(f'yangyangdeyi API JSON解析错误: {str(json_error)}, 响应内容={error_text}')
                    raise Exception(f'API响应格式错误: 无法解析JSON, 响应内容={error_text[:100]}')

                # 记录API响应的详细信息（用于调试和排查问题）
                logger.info(f'yangyangdeyi API响应: {json_data}')
                logger.debug(f'yangyangdeyi API响应详情: state={json_data.get("state")}, code={json_data.get("code")}')

                # 检查json_data是否为空或None
                if not json_data:
                    error_text = t_res.text[:500]
                    logger.error(f'yangyangdeyi API返回空响应: {error_text}')
                    raise Exception(f'API返回空响应: {error_text[:100]}')

                access_token = json_data.get('access_token', '')
                if not access_token:
                    logger.error(f'yangyangdeyi API返回的响应中缺少 access_token: {json_data}')
                    raise Exception(f'API响应中缺少 access_token')
                
                Headers['Authorization'] = f'Bearer {access_token}'
        except httpx.TimeoutException as timeout_error:
            logger.error(f'yangyangdeyi API获取 token 请求超时: {str(timeout_error)}')
            raise Exception(f'API请求超时: 超过20秒未响应')
        except httpx.RequestError as request_error:
            logger.error(f'yangyangdeyi API获取token请求错误: {str(request_error)}')
            raise Exception(f'yangyangdeyi API获取token请求失败: {str(request_error)}')

        app_now = datetime.now()
        app_yesterday = app_now - timedelta(days=1)
        yesterday_str = app_yesterday.strftime("%Y-%m-%d")
        today_str = app_now.strftime("%Y-%m-%d")

        if 0 <= datetime.now().hour <= 8:
            tbsj_params = {
                "page": 1,
                "limit": 5000,
                "start": yesterday_str,
                "end": yesterday_str
            }
        else:
            tbsj_params = {
                "page": 1,
                "limit": 5000,
                "start": today_str,
                "end": today_str
            }

        # 使用异步HTTP客户端调用yangyangdeyi API
        try:
            # 创建 HTTP 客户端
            async with httpx.AsyncClient(timeout=20, verify=False) as client:
                # 发送POST请求到yangyangdeyi API
                response = await client.post(tbsj_url + '/adunit', headers=Headers, json=tbsj_params)

                # 检查HTTP响应状态码
                if response.status_code != 200:
                    error_text = response.text[:500]  # 限制错误文本长度
                    logger.error(f'yangyangdeyi API HTTP错误: 状态码={response.status_code}, 响应内容={error_text}')
                    raise Exception(f'API HTTP错误: 状态码={response.status_code}, 响应内容={error_text[:100]}')

                # 解析JSON响应
                try:
                    json_data = response.json()
                except Exception as json_error:
                    error_text = response.text[:500]  # 限制错误文本长度
                    logger.error(f'yangyangdeyi API JSON解析错误: {str(json_error)}, 响应内容={error_text}')
                    raise Exception(f'API响应格式错误: 无法解析JSON, 响应内容={error_text[:100]}')

                # 记录API响应的详细信息（用于调试和排查问题）
                # 使用info级别确保能看到响应内容
                logger.info(f'yangyangdeyi API响应: {json_data}')
                logger.debug(f'yangyangdeyi API响应详情: state={json_data.get("state")}, code={json_data.get("code")}')

                # 检查json_data是否为空或None
                if not json_data:
                    logger.error(f'yangyangdeyi API返回空响应: {response.text[:500]}')
                    raise Exception(f'API返回空响应: {response.text[:100]}')

                # 检查API响应状态
                # yangyangdeyi API使用code字段：20000表示成功，其他值表示失败

                api_code = json_data.get('code')  # 获取code字段

                # 判断API是否成功：code=20000表示成功
                if api_code == 20000:
                    # API调用成功，获取数据列表
                    # 数据可能在data.list中，也可能直接在list中
                    data = None
                    if 'data' in json_data and isinstance(json_data['data'], dict):
                        data = json_data['data'].get('items', [])
                    else:
                        data = json_data.get('items', [])

                    # 如果返回的数据列表不为空，开始处理数据
                    if data:
                        # 创建数据库会话，所有数据操作都在这个会话中进行
                        # 使用上下文管理器确保会话正确关闭
                        async with AsyncSessionLocal() as db:
                            # ========== 获取管理员用户（用于产品查找/创建） ==========

                            # 查找管理员用户（优先查找username为'admin'的管理员）
                            admin_user_query = select(User).where(User.role == UserRole.ADMIN,
                                                                  User.username == 'admin').limit(1)
                            admin_user_result = await db.execute(admin_user_query)
                            admin_user = admin_user_result.scalar_one_or_none()

                            # 如果没有找到username为'admin'的管理员，查找任意一个管理员
                            if not admin_user:
                                admin_user_query = select(User).where(User.role == UserRole.ADMIN).limit(1)
                                admin_user_result = await db.execute(admin_user_query)
                                admin_user = admin_user_result.scalar_one_or_none()

                            if not admin_user:
                                logger.error("未找到管理员用户，无法处理产品，跳过本次任务")
                                return

                            # ========== 使用标准化的数据处理函数 ==========
                            result = await process_api_ad_data(
                                data=data,
                                db=db,
                                admin_user=admin_user,
                                source="yangyangdeyi定时任务",
                                field_mapping={
                                    # 数据日期
                                    "date": "date",

                                    # 产品名称
                                    "product_name": "product",

                                    # 国家代码
                                    "country_code": "country_code",

                                    # 请求数
                                    "request_count": "ad_requests",

                                    # 匹配数
                                    "match_count": "ad_matches",

                                    # 展示数
                                    "display_count": "ad_impressions",

                                    # 点击数
                                    "click_count": "ad_clicks",

                                    # ecpm
                                    "ecpm_before_deduct": "ecpm",

                                    # 覆盖率（可选，会自动计算）
                                    "coverage_rate": "ad_coverage",

                                    # 展示率（可选，会自动计算）
                                    "display_rate": "ad_impression_rate",

                                    # 点击率（可选，会自动计算）
                                    "click_rate": "ctr",

                                    # 收益
                                    "revenue_before_deduct": "earnings"
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

                            result_summary = (
                                f"成功插入 {inserted_count} 条, "
                                f"成功更新 {updated_count} 条, "
                                f"跳过重复 {skipped_count} 条, "
                                f"错误 {error_count} 条"
                            )
                            logger.info(f"数据导入完成: {result_summary}")
                            # 使用warning级别确保日志可见
                            logger.warning(f"[定时任务执行] 数据导入完成: {result_summary}")

                            # 发送 Telegram 通知（仅在成功导入或更新数据时）
                            if inserted_count > 0 or updated_count > 0:
                                # 构建通知消息
                                telegram_msg = f"⏰ yangyangdeyi 定时任务执行完成\n\n"
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
                                        f"Telegram 通知发送成功: yangyangdeyi任务, 插入:{inserted_count}, 更新:{updated_count}")
                                except asyncio.TimeoutError:
                                    logger.warning(f"发送 Telegram 通知超时: yangyangdeyi API获取数据任务")
                                # 其他异常已在 send_telegram_message 内部处理，这里不需要捕获

                            # 保存执行结果到全局存储（用于保存到last_error字段）
                            set_task_result(TBSJ_API_TASK_NAME, f"执行成功: {result_summary}")
                    else:
                        # API返回成功，但数据列表为空
                        logger.info('暂无产品数据')
                        logger.warning('[定时任务执行] 暂无产品数据')
                        # 保存执行结果到全局存储
                        set_task_result(TBSJ_API_TASK_NAME, "执行成功: 暂无产品数据")
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
                            f'yangyangdeyi API获取数据响应格式异常: 缺少state和code字段, 完整响应={json_data}')
                        logger.warning(f'[yangyangdeyi API获取数据定时任务执行] API响应格式异常: 缺少state和code字段')
                        logger.info(f'yangyangdeyi API获取数据完整响应内容: {json_data}')
                        raise Exception(f'API响应格式异常: 缺少state和code字段, 响应内容={str(json_data)[:200]}')

                    # 记录完整的错误信息
                    logger.error(f'yangyangdeyi API获取数据业务错误: {error_details}')
                    logger.warning(f'[yangyangdeyi API获取数据 定时任务执行] API错误: {error_details}')
                    # 记录完整的响应内容（用于调试）
                    logger.info(f'yangyangdeyi API获取数据完整响应: {json_data}')
                    # 抛出异常，让上层错误处理机制捕获
                    raise Exception(f'API错误: {error_details}')

        except httpx.TimeoutException as timeout_error:
            logger.error(f'yangyangdeyi API获取数据请求超时: {str(timeout_error)}')
            raise Exception(f'API请求超时: 超过20秒未响应')
        except httpx.RequestError as request_error:
            logger.error(f'yangyangdeyi API获取数据请求错误: {str(request_error)}')
            raise Exception(f'yangyangdeyi API获取数据请求失败: {str(request_error)}')

    except Exception as e:
        # ========== 全局错误处理 ==========

        # 捕获任务执行过程中的任何异常
        # 注意：如果任务执行失败，异常会被捕获并记录
        # 定时任务调度器的锁机制会自动释放，错误信息会保存到数据库

        error_msg = f"{TBSJ_API_TASK_NAME} 执行失败: {str(e)}"
        # 记录详细错误信息（包括完整的堆栈跟踪）
        logger.error(error_msg, exc_info=True)
        # 同时使用 logger.warning 确保即使日志级别设置为 WARNING 也能看到错误信息
        logger.warning(f"[yangyangdeyi API获取数据] {error_msg}")

        # 重新抛出异常，让定时任务调度器的锁机制能够记录错误状态
        # 这样可以在数据库中标记任务执行失败，便于后续排查问题
        raise
