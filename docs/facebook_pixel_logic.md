# Facebook 像素配置逻辑说明

## 核心逻辑

```
dp 参数（HTML 名称） → FACEBOOK_PIXEL_CONFIG[dp] → 获取 pixel_id 和 access_token
```

## 数据流

```
1. 用户访问：/change/temp_42e8c1b0?dp=master
   ↓
2. router.py 获取参数：dp="master", short_code="temp_42e8c1b0"
   ↓
3. 调用映射服务：get_cloak_pixel_config(dp="master", short_code="temp_42e8c1b0")
   ↓
4. cloak_pixel_mapping.py 查找配置：
   - 优先级 1: 数据库配置（short_link.facebook_pixel_id）
   - 优先级 2: FACEBOOK_PIXEL_CONFIG.get("master")  ← 使用 dp 参数作为键
   - 优先级 3: 全局配置
   ↓
5. 返回配置字典：
   {
       "facebook_pixel_id": "1234567890123456",
       "facebook_access_token": "EAAU...",
       "facebook_api_version": "v21.0"
   }
   ↓
6. router.py 将配置传给 send_third_party_report()
   ↓
7. 上报 Facebook
```

## 配置示例（.env 文件）

```bash
FACEBOOK_PIXEL_CONFIG='{
  "master": {
    "pixel_id": "1483729203107246",
    "access_token": "EAAc...",
    "api_version": "v21.0"
  },
  "test": {
    "pixel_id": "1273446968230624",
    "access_token": "EAAU...",
    "api_version": "v21.0"
  }
}'
```

## 关键点

- ✅ `dp` 参数是 HTML 名称（如 `master`, `test`）
- ✅ `FACEBOOK_PIXEL_CONFIG` 的键名是 `dp` 参数的值
- ✅ 像素配置从 `FACEBOOK_PIXEL_CONFIG[dp]` 获取
- ✅ `dp` 参数本身不包含像素信息，只是配置字典的键

## 代码位置

- 路由处理：`app/routes/short_link/router.py#L534-L584`
- 映射服务：`app/services/cloak_pixel_mapping.py#L154`
- 配置定义：`app/core/config.py#L439-L453`
- 上报服务：`app/core/third_party_report.py#L148-L164`
