# CPL服务层使用指南

## 概述

CPL服务层封装了CPL系统（广告主、Offer、渠道、转化）的所有业务逻辑。

## 服务列表

### 1. AdvertiserService（广告主服务）

```python
from app.core.dependencies import get_advertiser_service
from app.services.cpl.advertiser_service import AdvertiserService

@router.get("/advertisers")
async def get_advertisers(
    page: int = Query(1),
    advertiser_service: AdvertiserService = Depends(get_advertiser_service),
    current_user: User = Depends(get_current_user)
):
    advertisers, total = await advertiser_service.get_advertisers(
        current_user=current_user,
        page=page,
        page_size=20
    )
    return ResponseBaseSchema.success(data=advertisers, total=total)
```

### 2. PublisherService（渠道服务）

```python
from app.core.dependencies import get_publisher_service
from app.services.cpl.publisher_service import PublisherService

@router.get("/publishers")
async def get_publishers(
    publisher_service: PublisherService = Depends(get_publisher_service),
    current_user: User = Depends(get_current_user)
):
    publishers, total = await publisher_service.get_publishers(
        current_user=current_user,
        page=1,
        page_size=20
    )
    return ResponseBaseSchema.success(data=publishers, total=total)
```

### 3. OfferService（Offer服务）

**特点：**
- ✅ 自动批量加载广告主信息（避免N+1查询）
- ✅ 批量加载渠道分配信息
- ✅ 支持权限过滤（客户只能查看分配给自己的Offer）

```python
from app.core.dependencies import get_offer_service
from app.services.cpl.offer_service import OfferService

@router.get("/offers")
async def get_offers(
    offer_service: OfferService = Depends(get_offer_service),
    current_user: User = Depends(get_current_user)
):
    # 返回：offers列表、总数、渠道分配映射
    offers, total, assignments_map = await offer_service.get_offers(
        current_user=current_user,
        page=1,
        page_size=20
    )
    
    # 构建响应（assignments_map已包含渠道分配信息）
    offer_list = []
    for offer in offers:
        offer_data = OfferResponse.model_validate(offer)
        offer_data.advertiser_name = offer.advertiser.advertiser_name
        offer_data.assigned_publishers = assignments_map.get(offer.id, [])
        offer_list.append(offer_data)
    
    return ResponseBaseSchema.success(data=offer_list, total=total)
```

### 4. ConversionService（转化服务）

**特点：**
- ✅ 批量查询优化，避免N+1问题
- ✅ 自动批量加载Offer、Publisher、Advertiser信息

```python
from app.core.dependencies import get_conversion_service
from app.services.cpl.conversion_service import ConversionService

@router.get("/conversion-summary")
async def get_conversion_summary(
    conversion_service: ConversionService = Depends(get_conversion_service),
    current_user: User = Depends(get_current_user)
):
    summary = await conversion_service.get_conversion_summary(
        current_user=current_user,
        start_date="2024-01-01",
        end_date="2024-01-31"
    )
    return ResponseBaseSchema.success(data=summary)
```

## 查询优化说明

### 优化前（N+1查询问题）

```python
# 每个offer都查询一次advertiser
offers = await db.execute(select(Offer))
for offer in offers:
    advertiser = await db.execute(
        select(Advertiser).where(Advertiser.id == offer.advertiser_id)
    )  # N+1查询！
```

### 优化后（批量加载）

```python
# 使用joinedload，一次查询加载所有关联数据
query = select(Offer).options(joinedload(Offer.advertiser))
offers = await db.execute(query)
# 所有advertiser信息已加载，无额外查询
```

## 缓存使用

```python
from app.core.infrastructure.cache import cached, CacheInvalidator

class OfferService:
    @cached("offer:{offer_id}", ttl=3600)
    async def get_offer_by_id(self, offer_id: int, ...):
        # 自动缓存1小时
        pass
    
    async def update_offer(self, offer_id: int, ...):
        # 更新后失效缓存
        await CacheInvalidator.invalidate_offer_cache(offer_id)
```

## 权限控制

所有服务层方法都包含权限检查：
- 管理员：可以访问所有数据
- 客户：只能访问自己的数据

权限检查在服务层完成，endpoint无需关心。

