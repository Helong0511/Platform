"""
Excel处理工具函数
提供文件验证、数据处理等工具函数
"""
from fastapi import HTTPException, status
from typing import Any
import pandas as pd
from datetime import datetime, timedelta

# 允许的Excel文件MIME类型
ALLOWED_MIME_TYPES = [
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel"
]
# 允许的文件扩展名
ALLOWED_EXTENSIONS = {"xlsx", "xls"}


def allowed_file(filename: str) -> bool:
    """检查文件扩展名是否允许"""
    return (
            "." in filename
            and filename.endswith(('.xlsx', '.xls'))
            and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


# validate_file函数已移至import_handler.py中的validate_and_read_excel
# 保留此文件用于其他工具函数


def parse_date_value(date_value: Any) -> datetime.date:
    """
    解析日期值，支持多种格式
    注意：Excel导入的日期默认是系统时区，不需要进行时区转换
    
    参数:
        date_value: 日期值（字符串、datetime对象、Excel日期序列号等）
    
    返回:
        date对象（系统时区）
    
    异常:
        ValueError: 如果日期格式无效
    """
    # 处理字符串格式
    if isinstance(date_value, str):
        # 去除前后空格
        date_value = date_value.strip()
        try:
            return datetime.strptime(date_value, "%Y-%m-%d").date()
        except ValueError:
            try:
                return datetime.strptime(date_value, "%Y/%m/%d").date()
            except ValueError:
                # 尝试其他常见格式
                try:
                    return datetime.strptime(date_value, "%Y-%m-%d %H:%M:%S").date()
                except ValueError:
                    try:
                        return datetime.strptime(date_value, "%Y/%m/%d %H:%M:%S").date()
                    except ValueError:
                        raise ValueError(f"日期格式无效，应为YYYY-MM-DD或YYYY/MM/DD")

    # 处理 datetime 对象
    elif isinstance(date_value, datetime):
        return date_value.date()

    # 处理 pandas Timestamp 对象
    elif hasattr(date_value, 'date') and hasattr(date_value, 'to_pydatetime'):
        # pandas Timestamp 对象
        try:
            return date_value.date()
        except (AttributeError, ValueError):
            pass

    # 处理数字类型（Excel 日期序列号）
    elif isinstance(date_value, (int, float)):
        # Excel 日期序列号：从 1900-01-01 开始的天数
        # 注意：Excel 有一个 bug，它认为 1900 年是闰年，所以需要调整
        # Excel 日期序列号范围：1 (1900-01-01) 到约 2958465 (9999-12-31)
        excel_epoch = datetime(1899, 12, 30)  # Excel 的基准日期（1900-01-01 是序列号 1）

        # 检查是否是合理的日期序列号（1 到 1000000 之间）
        if 1 <= date_value <= 1000000:
            try:
                # 计算日期：Excel 序列号 - 1 天（因为 Excel 认为 1900-01-01 是第 1 天）
                days = int(date_value) - 1
                result_date = (excel_epoch + timedelta(days=days)).date()

                # 验证日期是否合理（1900-01-01 到 2100-12-31）
                if datetime(1900, 1, 1).date() <= result_date <= datetime(2100, 12, 31).date():
                    return result_date
                else:
                    raise ValueError(f"日期序列号 {date_value} 转换后的日期 {result_date} 超出合理范围")
            except (ValueError, OverflowError) as e:
                raise ValueError(f"日期格式无效: 无法将序列号 {date_value} 转换为日期: {str(e)}")
        else:
            raise ValueError(f"日期格式无效: 序列号 {date_value} 不在合理范围内（应为 1-1000000）")

    # 其他类型
    else:
        raise ValueError(f"日期格式无效: {str(date_value)} (类型: {type(date_value).__name__})")


def calculate_rates(df: pd.DataFrame) -> pd.DataFrame:
    """
    计算缺失的比率字段
    优先使用Excel表中的映射关系数据，如果不存在或值为空/NaN，才按照计算公式计算
    
    计算公式：
    - 覆盖率（匹配率）= 匹配数/请求数 * 100
    - 展示率 = 展示数/匹配数 * 100
    - 点击率 = 点击数/展示数 * 100
    - eCPM = 收益/展示数 * 1000
    
    参数:
        df: DataFrame对象
    
    返回:
        更新后的DataFrame
    """
    # 覆盖率（匹配率）= 匹配数/请求数 * 100
    # 只有当字段不存在或值为NaN时，才计算（0是有效值，不计算）
    if 'coverage_rate' not in df.columns:
        # 字段不存在，创建新列并计算
        if 'request_count' in df.columns and 'match_count' in df.columns:
            # 避免除零错误
            df['coverage_rate'] = 0.0
            mask = df['request_count'] > 0
            df.loc[mask, 'coverage_rate'] = (df.loc[mask, 'match_count'] / df.loc[mask, 'request_count'] * 100).fillna(0)
    else:
        # 字段存在，但值为NaN的行才计算
        mask = df['coverage_rate'].isna()
        if mask.any() and 'request_count' in df.columns and 'match_count' in df.columns:
            calculated = 0.0
            valid_mask = mask & (df['request_count'] > 0)
            if valid_mask.any():
                calculated = (df.loc[valid_mask, 'match_count'] / df.loc[valid_mask, 'request_count'] * 100).fillna(0)
                df.loc[valid_mask, 'coverage_rate'] = calculated
            df.loc[mask & (df['request_count'] == 0), 'coverage_rate'] = 0

    # 展示率 = 展示数/匹配数 * 100
    if 'display_rate' not in df.columns:
        if 'match_count' in df.columns and 'display_count' in df.columns:
            df['display_rate'] = 0.0
            mask = df['match_count'] > 0
            df.loc[mask, 'display_rate'] = (df.loc[mask, 'display_count'] / df.loc[mask, 'match_count'] * 100).fillna(0)
    else:
        mask = df['display_rate'].isna()
        if mask.any() and 'match_count' in df.columns and 'display_count' in df.columns:
            valid_mask = mask & (df['match_count'] > 0)
            if valid_mask.any():
                calculated = (df.loc[valid_mask, 'display_count'] / df.loc[valid_mask, 'match_count'] * 100).fillna(0)
                df.loc[valid_mask, 'display_rate'] = calculated
            df.loc[mask & (df['match_count'] == 0), 'display_rate'] = 0

    # 点击率 = 点击数/展示数 * 100
    if 'click_rate' not in df.columns:
        if 'display_count' in df.columns and 'click_count' in df.columns:
            df['click_rate'] = 0.0
            mask = df['display_count'] > 0
            df.loc[mask, 'click_rate'] = (df.loc[mask, 'click_count'] / df.loc[mask, 'display_count'] * 100).fillna(0)
    else:
        mask = df['click_rate'].isna()
        if mask.any() and 'display_count' in df.columns and 'click_count' in df.columns:
            valid_mask = mask & (df['display_count'] > 0)
            if valid_mask.any():
                calculated = (df.loc[valid_mask, 'click_count'] / df.loc[valid_mask, 'display_count'] * 100).fillna(0)
                df.loc[valid_mask, 'click_rate'] = calculated
            df.loc[mask & (df['display_count'] == 0), 'click_rate'] = 0

    # eCPM = 收益/展示数 * 1000
    # 只有当 ecpm_before_deduct 不存在或值为NaN时，才从收益和展示数计算
    if 'ecpm_before_deduct' not in df.columns:
        if 'revenue_before_deduct' in df.columns and 'display_count' in df.columns:
            df['ecpm_before_deduct'] = 0.0
            mask = df['display_count'] > 0
            df.loc[mask, 'ecpm_before_deduct'] = (df.loc[mask, 'revenue_before_deduct'] / df.loc[mask, 'display_count'] * 1000).fillna(0)
    else:
        mask = df['ecpm_before_deduct'].isna()
        if mask.any() and 'revenue_before_deduct' in df.columns and 'display_count' in df.columns:
            valid_mask = mask & (df['display_count'] > 0)
            if valid_mask.any():
                calculated = (df.loc[valid_mask, 'revenue_before_deduct'] / df.loc[valid_mask, 'display_count'] * 1000).fillna(0)
                df.loc[valid_mask, 'ecpm_before_deduct'] = calculated
            df.loc[mask & (df['display_count'] == 0), 'ecpm_before_deduct'] = 0

    return df
