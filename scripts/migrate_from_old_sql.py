"""
从旧SQL文件迁移数据到当前项目
处理表结构差异，确保数据完整性

使用方法:
    python scripts/migrate_from_old_sql.py [sql_file_path] [--skip-existing]

说明:
    - 默认SQL文件路径: scripts/platform_old.sql
    - --skip-existing: 跳过已存在的记录（默认启用）
    - --no-skip-existing: 不跳过已存在的记录
"""
import asyncio
import re
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
import logging

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import AsyncSessionLocal, engine
from app.models.models import (
    User, Client, Product, AdData, ProductAssignment, 
    ScheduledTask, UserAuditLog, CountryInfo, Base
)
from app.models.session import UserSession, TokenBlacklist

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SQLFileParser:
    """解析SQL文件，提取表结构和数据"""
    
    def __init__(self, sql_file_path: str):
        self.sql_file_path = Path(sql_file_path)
        self.tables_data: Dict[str, Dict[str, Any]] = {}
        
    def parse(self):
        """解析SQL文件"""
        logger.info(f"开始解析SQL文件: {self.sql_file_path}")
        
        with open(self.sql_file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 提取所有表的数据
        table_pattern = r'CREATE TABLE `(\w+)`.*?-- Records of \1.*?(?=-- |CREATE TABLE|SET FOREIGN_KEY|$)'
        matches = re.finditer(table_pattern, content, re.DOTALL)
        
        for match in matches:
            table_name = match.group(1)
            table_sql = match.group(0)
            
            # 提取INSERT语句
            insert_pattern = r'INSERT INTO `' + re.escape(table_name) + r'` VALUES\s*\((.*?)\);'
            insert_matches = re.finditer(insert_pattern, table_sql, re.DOTALL)
            
            records = []
            for insert_match in insert_matches:
                values_str = insert_match.group(1)
                # 解析VALUES中的值
                values = self._parse_values(values_str)
                records.append(values)
            
            self.tables_data[table_name] = {
                'records': records,
                'count': len(records)
            }
            logger.info(f"表 {table_name}: 找到 {len(records)} 条记录")
        
        logger.info(f"解析完成，共找到 {len(self.tables_data)} 个表")
        return self.tables_data
    
    def _parse_values(self, values_str: str) -> List[Any]:
        """解析VALUES字符串为Python值"""
        values = []
        current_value = ""
        in_string = False
        string_char = None
        i = 0
        
        while i < len(values_str):
            char = values_str[i]
            
            if not in_string:
                if char in ("'", '"'):
                    in_string = True
                    string_char = char
                    current_value += char
                elif char == ',':
                    # 结束当前值
                    val = current_value.strip()
                    values.append(self._convert_value(val))
                    current_value = ""
                else:
                    current_value += char
            else:
                current_value += char
                if char == string_char:
                    # 检查是否是转义的引号
                    if i + 1 < len(values_str) and values_str[i + 1] == string_char:
                        current_value += values_str[i + 1]
                        i += 1
                    else:
                        in_string = False
                        string_char = None
            
            i += 1
        
        # 添加最后一个值
        if current_value.strip():
            val = current_value.strip()
            values.append(self._convert_value(val))
        
        return values
    
    def _convert_value(self, val: str) -> Any:
        """转换SQL值为Python值"""
        val = val.strip()
        
        # NULL
        if val.upper() == 'NULL':
            return None
        
        # 字符串（去除引号）
        if (val.startswith("'") and val.endswith("'")) or (val.startswith('"') and val.endswith('"')):
            val = val[1:-1]
            # 处理转义字符
            val = val.replace("''", "'").replace('""', '"')
            return val
        
        # 数字
        try:
            if '.' in val:
                return float(val)
            return int(val)
        except ValueError:
            return val


class DataMigrator:
    """数据迁移器"""
    
    def __init__(self, sql_file_path: str):
        self.sql_file_path = sql_file_path
        self.parser = SQLFileParser(sql_file_path)
        self.stats = {
            'users': 0,
            'clients': 0,
            'products': 0,
            'ad_data': 0,
            'product_assignments': 0,
            'scheduled_tasks': 0,
            'user_audit_logs': 0,
            'user_sessions': 0,
            'token_blacklist': 0,
            'countries': 0,
            'errors': []
        }
    
    async def migrate(self, skip_existing: bool = True):
        """执行迁移"""
        logger.info("=" * 60)
        logger.info("开始数据迁移")
        logger.info("=" * 60)
        
        # 解析SQL文件
        tables_data = self.parser.parse()
        
        # 创建表（如果不存在）
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("数据库表已创建/验证")
        
        async with AsyncSessionLocal() as session:
            try:
                # 按依赖顺序迁移表
                # 1. 国家信息（countries/country_info）
                if 'country_info' in tables_data:
                    await self._migrate_countries(session, tables_data['country_info'], skip_existing)
                
                # 2. 用户
                if 'users' in tables_data:
                    await self._migrate_users(session, tables_data['users'], skip_existing)
                
                # 3. 客户
                if 'clients' in tables_data:
                    await self._migrate_clients(session, tables_data['clients'], skip_existing)
                
                # 4. 产品
                if 'products' in tables_data:
                    await self._migrate_products(session, tables_data['products'], skip_existing)
                
                # 5. 广告数据
                if 'ad_data' in tables_data:
                    await self._migrate_ad_data(session, tables_data['ad_data'], skip_existing)
                
                # 6. 产品分配
                if 'product_assignments' in tables_data:
                    await self._migrate_product_assignments(session, tables_data['product_assignments'], skip_existing)
                
                # 7. 定时任务
                if 'scheduled_tasks' in tables_data:
                    await self._migrate_scheduled_tasks(session, tables_data['scheduled_tasks'], skip_existing)
                
                # 8. 审计日志
                if 'user_audit_logs' in tables_data:
                    await self._migrate_user_audit_logs(session, tables_data['user_audit_logs'], skip_existing)
                
                # 9. 用户会话
                if 'user_sessions' in tables_data:
                    await self._migrate_user_sessions(session, tables_data['user_sessions'], skip_existing)
                
                # 10. Token黑名单
                if 'token_blacklist' in tables_data:
                    await self._migrate_token_blacklist(session, tables_data['token_blacklist'], skip_existing)
                
                await session.commit()
                logger.info("=" * 60)
                logger.info("数据迁移完成")
                logger.info("=" * 60)
                self._print_stats()
                
            except Exception as e:
                await session.rollback()
                logger.error(f"迁移失败: {e}", exc_info=True)
                raise
    
    async def _migrate_countries(self, session: AsyncSession, table_data: Dict, skip_existing: bool):
        """迁移国家信息表（country_info -> countries）"""
        logger.info("迁移国家信息...")
        records = table_data['records']
        
        for record in records:
            try:
                # 旧表字段: id, iso_code_2, iso_code_3, iso_code_numeric, name_en, name_zh
                # 新表字段: id, alpha_2_code, alpha_3_code, numeric_code, country_name_en, country_name_zh, ...
                if len(record) < 6:
                    continue
                
                old_id, iso_code_2, iso_code_3, iso_code_numeric, name_en, name_zh = record[:6]
                
                # 检查是否已存在
                if skip_existing:
                    result = await session.execute(
                        select(CountryInfo).where(CountryInfo.alpha_2_code == iso_code_2)
                    )
                    if result.scalar_one_or_none():
                        continue
                
                country = CountryInfo(
                    alpha_2_code=iso_code_2,
                    alpha_3_code=iso_code_3,
                    numeric_code=iso_code_numeric,
                    country_name_en=name_en,
                    country_name_zh=name_zh,
                    independent_status=True,  # 默认值
                    continent=None,  # 旧数据中没有
                    subregion=None  # 旧数据中没有
                )
                session.add(country)
                self.stats['countries'] += 1
                
            except Exception as e:
                logger.error(f"迁移国家信息失败: {record}, 错误: {e}")
                self.stats['errors'].append(f"countries: {e}")
        
        await session.flush()
        logger.info(f"国家信息迁移完成: {self.stats['countries']} 条")
    
    async def _migrate_users(self, session: AsyncSession, table_data: Dict, skip_existing: bool):
        """迁移用户表"""
        logger.info("迁移用户...")
        records = table_data['records']
        
        for record in records:
            try:
                # 字段顺序: id, username, hashed_password, full_name, email, role, is_active, 
                #           login_restricted, login_message, created_at, updated_at
                if len(record) < 11:
                    continue
                
                old_id, username, hashed_password, full_name, email, role, is_active, \
                    login_restricted, login_message, created_at, updated_at = record[:11]
                
                # 检查是否已存在
                if skip_existing:
                    result = await session.execute(
                        select(User).where(User.username == username)
                    )
                    if result.scalar_one_or_none():
                        continue
                
                user = User(
                    username=username,
                    hashed_password=hashed_password,
                    full_name=full_name,
                    email=email,
                    role=role,
                    is_active=bool(is_active) if is_active is not None else True,
                    login_restricted=bool(login_restricted) if login_restricted is not None else False,
                    login_message=login_message,
                    created_at=self._parse_datetime(created_at),
                    updated_at=self._parse_datetime(updated_at)
                )
                session.add(user)
                self.stats['users'] += 1
                
            except Exception as e:
                logger.error(f"迁移用户失败: {record}, 错误: {e}")
                self.stats['errors'].append(f"users: {e}")
        
        await session.flush()
        logger.info(f"用户迁移完成: {self.stats['users']} 条")
    
    async def _migrate_clients(self, session: AsyncSession, table_data: Dict, skip_existing: bool):
        """迁移客户表（注意：旧表有chat_id字段，新表没有）"""
        logger.info("迁移客户...")
        records = table_data['records']
        
        # 先获取所有用户，建立ID映射
        result = await session.execute(select(User))
        users = {u.username: u.id for u in result.scalars().all()}
        
        for record in records:
            try:
                # 旧表字段: id, user_id, company_name, contact_person, phone, address, allowed_ips,
                #           key, is_active, api_enabled, password_change_enabled, chat_id, created_at, updated_at
                if len(record) < 13:
                    continue
                
                old_id, user_id, company_name, contact_person, phone, address, allowed_ips, \
                    key, is_active, api_enabled, password_change_enabled, chat_id, created_at, updated_at = record[:14]
                
                # 检查是否已存在
                if skip_existing:
                    result = await session.execute(
                        select(Client).where(Client.key == key)
                    )
                    if result.scalar_one_or_none():
                        continue
                
                # 验证user_id是否存在
                result = await session.execute(select(User).where(User.id == user_id))
                if not result.scalar_one_or_none():
                    logger.warning(f"客户 {company_name} 的 user_id {user_id} 不存在，跳过")
                    continue
                
                client = Client(
                    user_id=user_id,
                    key=key,
                    company_name=company_name,
                    contact_person=contact_person,
                    phone=phone,
                    address=address,
                    allowed_ips=allowed_ips,
                    is_active=bool(is_active) if is_active is not None else True,
                    api_enabled=bool(api_enabled) if api_enabled is not None else False,
                    password_change_enabled=bool(password_change_enabled) if password_change_enabled is not None else False,
                    created_at=self._parse_datetime(created_at),
                    updated_at=self._parse_datetime(updated_at)
                    # 注意：chat_id字段在新表中不存在，跳过
                )
                session.add(client)
                self.stats['clients'] += 1
                
            except Exception as e:
                logger.error(f"迁移客户失败: {record}, 错误: {e}")
                self.stats['errors'].append(f"clients: {e}")
        
        await session.flush()
        logger.info(f"客户迁移完成: {self.stats['clients']} 条")
    
    async def _migrate_products(self, session: AsyncSession, table_data: Dict, skip_existing: bool):
        """迁移产品表"""
        logger.info("迁移产品...")
        records = table_data['records']
        
        for record in records:
            try:
                # 字段顺序: id, client_id, name, ecpm_deduct_ratio, revenue_deduct_ratio, 
                #           is_active, created_at, updated_at
                if len(record) < 8:
                    continue
                
                old_id, client_id, name, ecpm_deduct_ratio, revenue_deduct_ratio, \
                    is_active, created_at, updated_at = record[:8]
                
                # 检查是否已存在（通过client_id和name）
                if skip_existing:
                    result = await session.execute(
                        select(Product).where(
                            Product.client_id == client_id,
                            Product.name == name
                        )
                    )
                    if result.scalar_one_or_none():
                        continue
                
                # 验证client_id是否存在
                result = await session.execute(select(Client).where(Client.id == client_id))
                if not result.scalar_one_or_none():
                    logger.warning(f"产品 {name} 的 client_id {client_id} 不存在，跳过")
                    continue
                
                product = Product(
                    client_id=client_id,
                    name=name,
                    ecpm_deduct_ratio=float(ecpm_deduct_ratio) if ecpm_deduct_ratio else 0.0,
                    revenue_deduct_ratio=float(revenue_deduct_ratio) if revenue_deduct_ratio else 0.0,
                    is_active=bool(is_active) if is_active is not None else True,
                    created_at=self._parse_datetime(created_at),
                    updated_at=self._parse_datetime(updated_at)
                )
                session.add(product)
                self.stats['products'] += 1
                
            except Exception as e:
                logger.error(f"迁移产品失败: {record}, 错误: {e}")
                self.stats['errors'].append(f"products: {e}")
        
        await session.flush()
        logger.info(f"产品迁移完成: {self.stats['products']} 条")
    
    async def _migrate_ad_data(self, session: AsyncSession, table_data: Dict, skip_existing: bool):
        """迁移广告数据表（注意：旧表没有country_code字段）"""
        logger.info("迁移广告数据...")
        records = table_data['records']
        
        # 获取所有产品，建立ID映射
        result = await session.execute(select(Product))
        products = {p.id: p for p in result.scalars().all()}
        
        for record in records:
            try:
                # 旧表字段: id, date, product_id, request_count, match_count, display_count, click_count,
                #           ecpm_before_deduct, ecpm_after_deduct, revenue_before_deduct, revenue_after_deduct,
                #           created_at, updated_at
                # 新表有country_code字段，旧表没有，设为NULL
                if len(record) < 13:
                    continue
                
                old_id, date, product_id, request_count, match_count, display_count, click_count, \
                    ecpm_before_deduct, ecpm_after_deduct, revenue_before_deduct, revenue_after_deduct, \
                    created_at, updated_at = record[:13]
                
                # 验证product_id是否存在
                if product_id not in products:
                    logger.warning(f"广告数据的 product_id {product_id} 不存在，跳过")
                    continue
                
                # 检查是否已存在（通过date, product_id, country_code）
                if skip_existing:
                    result = await session.execute(
                        select(AdData).where(
                            AdData.date == self._parse_datetime(date),
                            AdData.product_id == product_id,
                            AdData.country_code == None  # 旧数据没有country_code
                        )
                    )
                    if result.scalar_one_or_none():
                        continue
                
                ad_data = AdData(
                    date=self._parse_datetime(date),
                    product_id=product_id,
                    country_code=None,  # 旧数据没有country_code
                    request_count=int(request_count) if request_count else 0,
                    match_count=int(match_count) if match_count else 0,
                    display_count=int(display_count) if display_count else 0,
                    click_count=int(click_count) if click_count else 0,
                    ecpm_before_deduct=float(ecpm_before_deduct) if ecpm_before_deduct else 0.0,
                    ecpm_after_deduct=float(ecpm_after_deduct) if ecpm_after_deduct else 0.0,
                    revenue_before_deduct=float(revenue_before_deduct) if revenue_before_deduct else 0.0,
                    revenue_after_deduct=float(revenue_after_deduct) if revenue_after_deduct else 0.0,
                    created_at=self._parse_datetime(created_at),
                    updated_at=self._parse_datetime(updated_at)
                )
                session.add(ad_data)
                self.stats['ad_data'] += 1
                
            except Exception as e:
                logger.error(f"迁移广告数据失败: {record}, 错误: {e}")
                self.stats['errors'].append(f"ad_data: {e}")
        
        await session.flush()
        logger.info(f"广告数据迁移完成: {self.stats['ad_data']} 条")
    
    async def _migrate_product_assignments(self, session: AsyncSession, table_data: Dict, skip_existing: bool):
        """迁移产品分配表"""
        logger.info("迁移产品分配...")
        records = table_data['records']
        
        for record in records:
            try:
                # 字段顺序: id, product_id, client_id, start_date, end_date, created_at, updated_at
                if len(record) < 7:
                    continue
                
                old_id, product_id, client_id, start_date, end_date, created_at, updated_at = record[:7]
                
                # 验证product_id和client_id是否存在
                result = await session.execute(select(Product).where(Product.id == product_id))
                if not result.scalar_one_or_none():
                    logger.warning(f"产品分配的 product_id {product_id} 不存在，跳过")
                    continue
                
                result = await session.execute(select(Client).where(Client.id == client_id))
                if not result.scalar_one_or_none():
                    logger.warning(f"产品分配的 client_id {client_id} 不存在，跳过")
                    continue
                
                # 检查是否已存在
                if skip_existing:
                    result = await session.execute(
                        select(ProductAssignment).where(
                            ProductAssignment.product_id == product_id,
                            ProductAssignment.client_id == client_id,
                            ProductAssignment.start_date == self._parse_date(start_date)
                        )
                    )
                    if result.scalar_one_or_none():
                        continue
                
                assignment = ProductAssignment(
                    product_id=product_id,
                    client_id=client_id,
                    start_date=self._parse_date(start_date),
                    end_date=self._parse_date(end_date) if end_date else None,
                    created_at=self._parse_datetime(created_at),
                    updated_at=self._parse_datetime(updated_at)
                )
                session.add(assignment)
                self.stats['product_assignments'] += 1
                
            except Exception as e:
                logger.error(f"迁移产品分配失败: {record}, 错误: {e}")
                self.stats['errors'].append(f"product_assignments: {e}")
        
        await session.flush()
        logger.info(f"产品分配迁移完成: {self.stats['product_assignments']} 条")
    
    async def _migrate_scheduled_tasks(self, session: AsyncSession, table_data: Dict, skip_existing: bool):
        """迁移定时任务表"""
        logger.info("迁移定时任务...")
        records = table_data['records']
        
        for record in records:
            try:
                # 字段顺序: id, task_name, last_run_time, is_running, last_run_pid, last_run_host,
                #           run_count, success_count, error_count, last_error, is_active, 
                #           cron_expression, description, function_path, created_at, updated_at
                if len(record) < 16:
                    continue
                
                old_id, task_name, last_run_time, is_running, last_run_pid, last_run_host, \
                    run_count, success_count, error_count, last_error, is_active, \
                    cron_expression, description, function_path, created_at, updated_at = record[:16]
                
                # 检查是否已存在
                if skip_existing:
                    result = await session.execute(
                        select(ScheduledTask).where(ScheduledTask.task_name == task_name)
                    )
                    if result.scalar_one_or_none():
                        continue
                
                task = ScheduledTask(
                    task_name=task_name,
                    last_run_time=self._parse_datetime(last_run_time) if last_run_time else None,
                    is_running=bool(is_running) if is_running is not None else False,
                    last_run_pid=int(last_run_pid) if last_run_pid else None,
                    last_run_host=last_run_host,
                    run_count=int(run_count) if run_count else 0,
                    success_count=int(success_count) if success_count else 0,
                    error_count=int(error_count) if error_count else 0,
                    last_error=last_error,
                    is_active=bool(is_active) if is_active is not None else True,
                    cron_expression=cron_expression,
                    description=description,
                    function_path=function_path,
                    created_at=self._parse_datetime(created_at),
                    updated_at=self._parse_datetime(updated_at)
                )
                session.add(task)
                self.stats['scheduled_tasks'] += 1
                
            except Exception as e:
                logger.error(f"迁移定时任务失败: {record}, 错误: {e}")
                self.stats['errors'].append(f"scheduled_tasks: {e}")
        
        await session.flush()
        logger.info(f"定时任务迁移完成: {self.stats['scheduled_tasks']} 条")
    
    async def _migrate_user_audit_logs(self, session: AsyncSession, table_data: Dict, skip_existing: bool):
        """迁移用户审计日志表"""
        logger.info("迁移用户审计日志...")
        records = table_data['records']
        
        for record in records:
            try:
                # 字段顺序: id, user_id, username, action_type, resource_type, resource_id,
                #           resource_name, ip_address, user_agent, request_method, request_path,
                #           request_params, status_code, success, error_message, details, created_at
                if len(record) < 17:
                    continue
                
                old_id, user_id, username, action_type, resource_type, resource_id, \
                    resource_name, ip_address, user_agent, request_method, request_path, \
                    request_params, status_code, success, error_message, details, created_at = record[:17]
                
                log = UserAuditLog(
                    user_id=int(user_id) if user_id else None,
                    username=username,
                    action_type=action_type,
                    resource_type=resource_type,
                    resource_id=int(resource_id) if resource_id else None,
                    resource_name=resource_name,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    request_method=request_method,
                    request_path=request_path,
                    request_params=request_params,
                    status_code=int(status_code) if status_code else None,
                    success=bool(success) if success is not None else True,
                    error_message=error_message,
                    details=details,
                    created_at=self._parse_datetime(created_at)
                )
                session.add(log)
                self.stats['user_audit_logs'] += 1
                
            except Exception as e:
                logger.error(f"迁移审计日志失败: {record}, 错误: {e}")
                self.stats['errors'].append(f"user_audit_logs: {e}")
        
        await session.flush()
        logger.info(f"用户审计日志迁移完成: {self.stats['user_audit_logs']} 条")
    
    async def _migrate_user_sessions(self, session: AsyncSession, table_data: Dict, skip_existing: bool):
        """迁移用户会话表"""
        logger.info("迁移用户会话...")
        records = table_data['records']
        
        for record in records:
            try:
                # 字段顺序: id, user_id, token_jti, ip_address, user_agent, device_info, 
                #           location, is_active, last_activity, created_at, expires_at
                if len(record) < 11:
                    continue
                
                old_id, user_id, token_jti, ip_address, user_agent, device_info, \
                    location, is_active, last_activity, created_at, expires_at = record[:11]
                
                # 检查是否已存在
                if skip_existing:
                    result = await session.execute(
                        select(UserSession).where(UserSession.token_jti == token_jti)
                    )
                    if result.scalar_one_or_none():
                        continue
                
                session_obj = UserSession(
                    user_id=user_id,
                    token_jti=token_jti,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    device_info=device_info,
                    location=location,
                    is_active=bool(is_active) if is_active is not None else True,
                    last_activity=self._parse_datetime(last_activity),
                    created_at=self._parse_datetime(created_at),
                    expires_at=self._parse_datetime(expires_at)
                )
                session.add(session_obj)
                self.stats['user_sessions'] += 1
                
            except Exception as e:
                logger.error(f"迁移用户会话失败: {record}, 错误: {e}")
                self.stats['errors'].append(f"user_sessions: {e}")
        
        await session.flush()
        logger.info(f"用户会话迁移完成: {self.stats['user_sessions']} 条")
    
    async def _migrate_token_blacklist(self, session: AsyncSession, table_data: Dict, skip_existing: bool):
        """迁移Token黑名单表"""
        logger.info("迁移Token黑名单...")
        records = table_data['records']
        
        for record in records:
            try:
                # 字段顺序: id, token_jti, user_id, revoked_at, expires_at, reason
                if len(record) < 6:
                    continue
                
                old_id, token_jti, user_id, revoked_at, expires_at, reason = record[:6]
                
                # 检查是否已存在
                if skip_existing:
                    result = await session.execute(
                        select(TokenBlacklist).where(TokenBlacklist.token_jti == token_jti)
                    )
                    if result.scalar_one_or_none():
                        continue
                
                blacklist = TokenBlacklist(
                    token_jti=token_jti,
                    user_id=int(user_id) if user_id else None,
                    revoked_at=self._parse_datetime(revoked_at),
                    expires_at=self._parse_datetime(expires_at),
                    reason=reason
                )
                session.add(blacklist)
                self.stats['token_blacklist'] += 1
                
            except Exception as e:
                logger.error(f"迁移Token黑名单失败: {record}, 错误: {e}")
                self.stats['errors'].append(f"token_blacklist: {e}")
        
        await session.flush()
        logger.info(f"Token黑名单迁移完成: {self.stats['token_blacklist']} 条")
    
    def _parse_datetime(self, value: Any) -> Optional[datetime]:
        """解析datetime值"""
        if value is None:
            return None
        
        if isinstance(value, datetime):
            return value
        
        if isinstance(value, str):
            # 处理MySQL datetime格式
            try:
                # 尝试多种格式
                for fmt in ['%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d']:
                    try:
                        return datetime.strptime(value, fmt)
                    except ValueError:
                        continue
                return datetime.now()
            except:
                return datetime.now()
        
        return datetime.now()
    
    def _parse_date(self, value: Any) -> Optional[datetime]:
        """解析date值"""
        if value is None:
            return None
        
        if isinstance(value, datetime):
            return value.date()
        
        if isinstance(value, str):
            try:
                return datetime.strptime(value, '%Y-%m-%d').date()
            except:
                return None
        
        return None
    
    def _print_stats(self):
        """打印统计信息"""
        logger.info("\n" + "=" * 60)
        logger.info("迁移统计:")
        logger.info("=" * 60)
        for key, value in self.stats.items():
            if key != 'errors':
                logger.info(f"  {key}: {value} 条")
        
        if self.stats['errors']:
            logger.warning(f"\n错误数量: {len(self.stats['errors'])}")
            for error in self.stats['errors'][:10]:  # 只显示前10个错误
                logger.warning(f"  - {error}")
        logger.info("=" * 60)


async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='从旧SQL文件迁移数据')
    parser.add_argument('sql_file', help='SQL文件路径', default='platform_old.sql', nargs='?')
    parser.add_argument('--skip-existing', action='store_true', default=True, 
                       help='跳过已存在的记录（默认: True）')
    parser.add_argument('--no-skip-existing', dest='skip_existing', action='store_false',
                       help='不跳过已存在的记录（会尝试更新）')
    
    args = parser.parse_args()
    
    sql_file_path = Path(args.sql_file)
    if not sql_file_path.exists():
        logger.error(f"SQL文件不存在: {sql_file_path}")
        return
    
    migrator = DataMigrator(str(sql_file_path))
    await migrator.migrate(skip_existing=args.skip_existing)


if __name__ == '__main__':
    asyncio.run(main())

