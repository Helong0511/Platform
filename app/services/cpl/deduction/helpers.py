"""
转化扣减配置辅助函数。

功能说明：
- 目标存在性校验、激活配置冲突检查
- 配置字段组装、Redis 缓存失效
- 配置层级与目标 ID 解析
"""
from typing import Any, Dict, Literal, Optional, Tuple

from sqlalchemy import and_, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload

from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception
from app.core.infrastructure.cache_compat import invalidate_cache
from app.models.models import (
    Advertiser,
    ConversionDeductionConfig,
    Offer,
    Publisher,
)

ConfigLevel = Literal["advertiser", "offer", "publisher"]

async def lock_deduction_scopes(
    db: AsyncSession,
    scopes: list[Tuple[ConfigLevel, int]],
) -> None:
    """在调用方事务中按固定顺序锁定扣量 scope；本函数绝不提交事务。"""
    normalized_set = set()
    for level, target_id in scopes:
        if level not in {"advertiser", "offer", "publisher"}:
            raise_api_exception(
                ErrorCode.INVALID_PARAMETER,
                detail="扣量 scope 类型无效",
            )
        if (
            not isinstance(target_id, int)
            or isinstance(target_id, bool)
            or target_id <= 0
        ):
            raise_api_exception(
                ErrorCode.INVALID_PARAMETER,
                detail="扣量 scope ID 必须为正整数",
            )
        normalized_set.add((level, target_id))

    normalized = sorted(normalized_set, key=lambda item: (item[0], item[1]))
    if not normalized:
        return

    dialect = db.bind.dialect.name if db.bind is not None else ""
    for level, target_id in normalized
        if dialect == "mysql":
            await db.execute(
                text(
                    "INSERT INTO conversion_deduction_scope_locks "
                    "(scope_type, scope_id) VALUES (:scope_type, :scope_id) "
                    "ON DUPLICATE KEY UPDATE scope_id = VALUES(scope_id)"
                ),
                {"scope_type": level, "scope_id": target_id},
            )
        elif dialect == "sqlite":
            await db.execute(
                text(
                    "INSERT OR IGNORE INTO conversion_deduction_scope_locks "
                    "(scope_type, scope_id) VALUES (:scope_type, :scope_id)"
                ),
                {"scope_type": level, "scope_id": target_id},
            )
        else:
            raise RuntimeError(
                f"扣量 scope 锁不支持当前数据库方言: {dialect or 'unknown'}"
            )

        result = await db.execute(
            text(
                "SELECT scope_id FROM conversion_deduction_scope_locks "
                "WHERE scope_type = :scope_type AND scope_id = :scope_id "
                "FOR UPDATE"
            ) if dialect == "mysql" else text(
                "SELECT scope_id FROM conversion_deduction_scope_locks "
                "WHERE scope_type = :scope_type AND scope_id = :scope_id"
            ),
            {"scope_type": level, "scope_id": target_id},
        )
        if result.scalar_one_or_none() is None:
            raise RuntimeError(
                f"扣量 scope 锁记录缺失: {level}:{target_id}"
            )


_LEVEL_NAMES = {"advertiser": "广告主", "offer": "Offer", "publisher": "渠道"}


def resolve_config_level_target(
    config: ConversionDeductionConfig,
) -> Tuple[Optional[ConfigLevel], Optional[int]]:
    """严格解析配置层级；空目标或多目标均视为数据完整性错误。"""
    targets = (
        ("advertiser", config.advertiser_id),
        ("offer", config.offer_id),
        ("publisher", config.publisher_id),
    )
    selected = [(level, target_id) for level, target_id in targets if target_id is not None]
    if len(selected) != 1:
        raise_api_exception(
            ErrorCode.INVALID_PARAMETER,
            detail="扣减配置层级数据异常：广告主、Offer、渠道目标必须且只能设置一个",
        )

    level, target_id = selected[0]
    if not isinstance(target_id, int) or isinstance(target_id, bool) or target_id <= 0:
        raise_api_exception(
            ErrorCode.INVALID_PARAMETER,
            detail="扣减配置目标 ID 必须为正整数",
        )
    return level, target_id


async def validate_target_exists(db: AsyncSession, level: ConfigLevel, target_id: int) -> None:
    """校验扣减配置目标（广告主/Offer/渠道）是否存在。"""
    if level == "advertiser":
        result = await db.execute(select(Advertiser).where(Advertiser.id == target_id))
        if not result.scalars().first():
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail=f"广告主ID {target_id} 不存在",
            )
    elif level == "offer":
        result = await db.execute(select(Offer).where(Offer.id == target_id))
        if not result.scalars().first():
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail=f"Offer ID {target_id} 不存在",
            )
    elif level == "publisher":
        result = await db.execute(select(Publisher).where(Publisher.id == target_id))
        if not result.scalars().first():
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail=f"渠道ID {target_id} 不存在",
            )
    else:
        raise_api_exception(
            ErrorCode.INVALID_PARAMETER,
            detail=f"无效的配置层级: {level}",
        )


async def check_existing_config(
    db: AsyncSession,
    level: ConfigLevel,
    target_id: int,
    exclude_config_id: Optional[int] = None,
    exclude_config_ids: Optional[set[int]] = None,
) -> None:
    """同一层级目标不可存在第二条激活配置。"""
    conditions = [ConversionDeductionConfig.is_active == True]

    if level == "advertiser":
        conditions.append(ConversionDeductionConfig.advertiser_id == target_id)
    elif level == "offer":
        conditions.append(ConversionDeductionConfig.offer_id == target_id)
    elif level == "publisher":
        conditions.append(ConversionDeductionConfig.publisher_id == target_id)

    if exclude_config_id is not None:
        conditions.append(ConversionDeductionConfig.id != exclude_config_id)
    if exclude_config_ids:
        conditions.append(ConversionDeductionConfig.id.notin_(exclude_config_ids))

    result = await db.execute(select(ConversionDeductionConfig).where(and_(*conditions)))
    if result.scalars().first():
        level_name = _LEVEL_NAMES[level]
        raise_api_exception(
            ErrorCode.RESOURCE_ALREADY_EXISTS,
            detail=f"{level_name}ID {target_id} 已存在激活的扣减配置",
        )


def build_config_fields(
    level: ConfigLevel,
    target_id: int,
    config_data: Dict[str, Any],
) -> Dict[str, Any]:
    """按层级组装 ConversionDeductionConfig 字段字典。"""
    fields = {
        "enable_volume_deduction": config_data.get("enable_volume_deduction", False),
        "volume_deduction_ratio": config_data.get("volume_deduction_ratio", 0),
        "deduction_strategy": config_data.get("deduction_strategy", "random"),
        "enable_amount_deduction": config_data.get("enable_amount_deduction", False),
        "amount_deduction_ratio": config_data.get("amount_deduction_ratio", 0),
        "priority": config_data.get("priority", 0),
        "is_active": config_data.get("is_active", True),
    }

    if level == "advertiser":
        fields["advertiser_id"] = target_id
        fields["offer_id"] = None
        fields["publisher_id"] = None
    elif level == "offer":
        fields["advertiser_id"] = None
        fields["offer_id"] = target_id
        fields["publisher_id"] = None
    elif level == "publisher":
        fields["advertiser_id"] = None
        fields["offer_id"] = None
        fields["publisher_id"] = target_id

    return fields


async def invalidate_config_cache(
    level: Optional[ConfigLevel] = None,
    target_id: Optional[int] = None,
) -> None:
    """失效扣减配置 Redis 缓存。"""
    if level and target_id:
        await invalidate_cache(f"cpl:deduction_config:{level}:{target_id}")
    else:
        await invalidate_cache("cpl:deduction_config:*")


async def load_config_with_relations(
    db: AsyncSession,
    config_id: int,
) -> ConversionDeductionConfig:
    """加载配置及广告主/Offer/渠道关联。"""
    query = (
        select(ConversionDeductionConfig)
        .where(ConversionDeductionConfig.id == config_id)
        .options(
            joinedload(ConversionDeductionConfig.advertiser),
            joinedload(ConversionDeductionConfig.offer),
            joinedload(ConversionDeductionConfig.publisher),
        )
    )
    result = await db.execute(query)
    config = result.unique().scalars().first()
    if not config:
        raise_api_exception(
            ErrorCode.RESOURCE_NOT_FOUND,
            detail=f"扣减配置ID {config_id} 不存在",
        )
    return config
