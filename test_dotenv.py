#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试 dotenv 模块和环境变量读取
"""
import os
import sys
from pathlib import Path

# 配置日志
import logging
logging.basicConfig(
    level=logging.INFO,
    format='[PID:%(process)d] %(levelname)s - %(message)s'
)

# 测试 dotenv 模块
logging.info("开始测试 dotenv 模块...")
try:
    from dotenv import load_dotenv
    logging.info("dotenv 模块导入成功")
    
    # 加载 .env 文件
    load_dotenv(override=True)
    logging.info(".env 文件加载成功")
    
    # 读取环境变量
    telegram_enable = os.getenv("TELEGRAM_ENABLE")
    telegram_token = os.getenv("TELEGRAM_TOKEN")
    telegram_admin = os.getenv("TELEGRAM_ADMIN")
    
    logging.info(f"TELEGRAM_ENABLE: {telegram_enable}")
    logging.info(f"TELEGRAM_TOKEN: {telegram_token}")
    logging.info(f"TELEGRAM_ADMIN: {telegram_admin}")
    
except Exception as e:
    logging.error(f"测试失败: {e}", exc_info=True)

# 测试完成
logging.info("测试完成")