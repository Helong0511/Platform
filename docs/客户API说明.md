# 客户API说明文档

## 概述

客户API提供客户通过API密钥访问的接口，包括查询产品信息和广告数据。所有接口都需要进行签名验证，确保请求的安全性。

**基础URL**: `https://client.btfrx.online/api/v1`

**请求格式**: JSON (Content-Type: application/json)

**响应格式**: JSON

---

## 认证方式

### 签名算法

所有API请求都需要进行MD5签名验证，签名算法如下：

1. **准备参数**：将 `client_id` 和 `req_time` 放入参数字典
2. **参数排序**：按字母顺序对参数键进行排序
3. **拼接字符串**：将参数拼接为 `key=value&key=value` 格式
4. **追加密钥**：在末尾追加 `&key={SECRET_KEY}`
5. **MD5加密**：对整个字符串进行MD5加密并转为小写

### 签名示例

```python
import hashlib
import time

# 参数
client_id = 1000
req_time = int(time.time())  # 当前时间戳（10位秒级）
SECRET_KEY = '3716607b-04cb-4f71-91c0-2dae7a87fa63'

# 1. 准备参数
params = {
    'client_id': str(client_id),
    'req_time': str(req_time)
}

# 2. 按字母顺序排序
sorted_keys = sorted(params.keys())

# 3. 拼接字符串
temp_str = '&'.join([f"{key}={params[key]}" for key in sorted_keys])
# 结果: client_id=1000&req_time=1745656222

# 4. 追加密钥
temp_str = temp_str + f'&key={SECRET_KEY}'
# 结果: client_id=1000&req_time=1745656222&key=3716607b-04cb-4f71-91c0-2dae7a87fa63

# 5. MD5加密并转为小写
sign = hashlib.md5(temp_str.encode('utf-8')).hexdigest().lower()
```

### 请求验证规则

1. **客户ID验证**：验证 `client_id` 是否存在且已激活
2. **时间戳验证**：请求时间戳与服务器时间差异不能超过5秒（正负5秒）
3. **签名验证**：验证MD5签名是否正确

**注意**：`SECRET_KEY` 不通过请求传递，而是从数据库查询客户的 `key` 字段进行验证。

---

## API接口列表

### 1. 查询产品信息

获取客户的所有激活产品列表。

**接口地址**: `/client_products`

**请求方法**: `POST`

**请求参数**:

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| client_id | int | 是 | 客户ID |
| req_time | int | 是 | 请求时间戳（10位秒级，Unix时间戳） |
| sign | string | 是 | MD5签名（小写） |

**请求示例**:

```json
{
  "client_id": 1000,
  "req_time": 1745656222,
  "sign": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"
}
```

**响应格式**:

```json
{
  "code": 200,
  "message": "成功获取 3 个产品",
  "data": [
    {
      "id": 1,
      "name": "产品A"
    },
    {
      "id": 2,
      "name": "产品B"
    },
    {
      "id": 3,
      "name": "产品C"
    }
  ]
}
```

**响应字段说明**:

| 字段名 | 类型 | 说明 |
|--------|------|------|
| code | int | 响应码，200表示成功 |
| message | string | 响应消息 |
| data | array | 产品列表 |
| data[].id | int | 产品ID（整数类型） |
| data[].name | string | 产品名称（确保不为null） |

**注意事项**:
- 如果客户没有产品，`data` 字段返回空数组 `[]`，而不是 `null`
- 产品按ID升序排列
- 只返回已激活的产品

---

### 2. 查询广告数据

获取客户当前月的广告数据。

**接口地址**: `/client_data`

**请求方法**: `POST`

**请求参数**:

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| client_id | int | 是 | 客户ID |
| req_time | int | 是 | 请求时间戳（10位秒级，Unix时间戳） |
| sign | string | 是 | MD5签名（小写） |

**请求示例**:

```json
{
  "client_id": 1000,
  "req_time": 1745656222,
  "sign": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"
}
```

**响应格式**:

```json
{
  "code": 200,
  "message": "成功获取 30 条广告数据",
  "data": [
    {
      "date": "2024-01-15",
      "product_name": "产品A",
      "request_count": 10000,
      "match_count": 8000,
      "coverage_rate": 80.0,
      "display_count": 7500,
      "display_rate": 93.75,
      "click_count": 500,
      "click_rate": 6.67,
      "ecpm": 5.25,
      "revenue": 393.75
    },
    {
      "date": "2024-01-16",
      "product_name": "产品A",
      "request_count": 12000,
      "match_count": 9600,
      "coverage_rate": 80.0,
      "display_count": 9000,
      "display_rate": 93.75,
      "click_count": 600,
      "click_rate": 6.67,
      "ecpm": 5.30,
      "revenue": 477.0
    }
  ]
}
```

**响应字段说明**:

| 字段名 | 类型 | 说明 |
|--------|------|------|
| code | int | 响应码，200表示成功 |
| message | string | 响应消息 |
| data | array | 广告数据列表 |
| data[].date | string | 数据日期（ISO格式：YYYY-MM-DD） |
| data[].product_name | string | 产品名称（确保不为null） |
| data[].request_count | int | 请求数（整数） |
| data[].match_count | int | 匹配数（整数） |
| data[].coverage_rate | float | 覆盖率（%，浮点数，保留2位小数） |
| data[].display_count | int | 展示数（整数） |
| data[].display_rate | float | 展示率（%，浮点数，保留2位小数） |
| data[].click_count | int | 点击数（整数） |
| data[].click_rate | float | 点击率（%，浮点数，保留2位小数） |
| data[].ecpm | float | eCPM（减扣后的，浮点数，保留2位小数） |
| data[].revenue | float | 收益（减扣后的，浮点数，保留2位小数） |

**数据说明**:

- **覆盖率** = 匹配数 / 请求数 × 100
- **展示率** = 展示数 / 匹配数 × 100
- **点击率** = 点击数 / 展示数 × 100
- **eCPM**: 每千次展示的有效成本（减扣后）
- **收益**: 实际收益（减扣后）

**注意事项**:
- 默认返回当前月的数据（从当月1日到最后一天）
- 数据按日期升序排列
- 如果当月没有数据，`data` 字段返回空数组 `[]`，而不是 `null`
- 所有数值类型明确（int/float），不会返回字符串
- 浮点数保留2位小数

---

## 错误码说明

### 成功响应

```json
{
  "code": 200,
  "message": "操作成功",
  "data": [...]
}
```

### 错误响应

所有错误响应都返回HTTP状态码200，通过响应体中的 `code` 字段区分错误类型：

```json
{
  "code": 2205,
  "message": "参数验证不通过",
  "detail": "请求时间差异过大（9秒），请确保系统时间正确（允许正负5秒）"
}
```

### 错误码列表

| 错误码 | 说明 | 解决方案 |
|--------|------|----------|
| 200 | 成功 | - |
| 2201 | 客户不存在或未激活 | 检查 client_id 是否正确，确认客户已激活 |
| 2205 | 参数验证不通过 | 检查以下项：<br>1. 请求时间戳是否在允许范围内（正负5秒）<br>2. 签名是否正确<br>3. 参数格式是否正确 |
| 2501 | 操作失败 | 查看 detail 字段获取详细错误信息 |

---

## 完整示例代码

### Python示例

```python
import hashlib
import time
import requests
import json

# 配置信息
BASE_URL = 'https://client.btfrx.online/api/v1'
CLIENT_ID = 1000
SECRET_KEY = '3716607b-04cb-4f71-91c0-2dae7a87fa63'

def generate_signature(client_id, req_time, secret_key):
    """生成签名"""
    params = {
        'client_id': str(client_id),
        'req_time': str(req_time)
    }
    
    sorted_keys = sorted(params.keys())
    temp_str = '&'.join([f"{key}={params[key]}" for key in sorted_keys])
    temp_str = temp_str + f'&key={secret_key}'
    
    sign = hashlib.md5(temp_str.encode('utf-8')).hexdigest().lower()
    return sign

def get_products():
    """获取产品列表"""
    req_time = int(time.time())
    sign = generate_signature(CLIENT_ID, req_time, SECRET_KEY)
    
    params = {
        'client_id': CLIENT_ID,
        'req_time': req_time,
        'sign': sign
    }
    
    headers = {'Content-Type': 'application/json'}
    response = requests.post(
        f'{BASE_URL}/client_products',
        headers=headers,
        json=params,
        timeout=10
    )
    
    return response.json()

def get_ad_data():
    """获取广告数据"""
    req_time = int(time.time())
    sign = generate_signature(CLIENT_ID, req_time, SECRET_KEY)
    
    params = {
        'client_id': CLIENT_ID,
        'req_time': req_time,
        'sign': sign
    }
    
    headers = {'Content-Type': 'application/json'}
    response = requests.post(
        f'{BASE_URL}/client_data',
        headers=headers,
        json=params,
        timeout=10
    )
    
    return response.json()

# 使用示例
if __name__ == '__main__':
    # 获取产品列表
    products_result = get_products()
    print("产品列表:", json.dumps(products_result, indent=2, ensure_ascii=False))
    
    # 获取广告数据
    ad_data_result = get_ad_data()
    print("广告数据:", json.dumps(ad_data_result, indent=2, ensure_ascii=False))
```

### Java示例

```java
import java.security.MessageDigest;
import java.time.Instant;
import java.util.*;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.URI;
import com.fasterxml.jackson.databind.ObjectMapper;

public class ClientAPI {
    private static final String BASE_URL = "https://client.btfrx.online/api/v1";
    private static final int CLIENT_ID = 1000;
    private static final String SECRET_KEY = "3716607b-04cb-4f71-91c0-2dae7a87fa63";
    
    private static String generateSignature(int clientId, long reqTime, String secretKey) {
        try {
            // 准备参数
            Map<String, String> params = new LinkedHashMap<>();
            params.put("client_id", String.valueOf(clientId));
            params.put("req_time", String.valueOf(reqTime));
            
            // 排序并拼接
            List<String> sortedKeys = new ArrayList<>(params.keySet());
            Collections.sort(sortedKeys);
            
            StringBuilder sb = new StringBuilder();
            for (String key : sortedKeys) {
                if (sb.length() > 0) {
                    sb.append("&");
                }
                sb.append(key).append("=").append(params.get(key));
            }
            
            // 追加密钥
            sb.append("&key=").append(secretKey);
            
            // MD5加密
            MessageDigest md = MessageDigest.getInstance("MD5");
            byte[] digest = md.digest(sb.toString().getBytes("UTF-8"));
            
            // 转为小写十六进制字符串
            StringBuilder hexString = new StringBuilder();
            for (byte b : digest) {
                String hex = Integer.toHexString(0xff & b);
                if (hex.length() == 1) {
                    hexString.append('0');
                }
                hexString.append(hex);
            }
            
            return hexString.toString().toLowerCase();
        } catch (Exception e) {
            throw new RuntimeException("生成签名失败", e);
        }
    }
    
    public static String getProducts() throws Exception {
        long reqTime = Instant.now().getEpochSecond();
        String sign = generateSignature(CLIENT_ID, reqTime, SECRET_KEY);
        
        Map<String, Object> params = new HashMap<>();
        params.put("client_id", CLIENT_ID);
        params.put("req_time", reqTime);
        params.put("sign", sign);
        
        ObjectMapper mapper = new ObjectMapper();
        String jsonBody = mapper.writeValueAsString(params);
        
        HttpClient client = HttpClient.newHttpClient();
        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create(BASE_URL + "/client_products"))
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(jsonBody))
            .build();
        
        HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());
        return response.body();
    }
    
    public static String getAdData() throws Exception {
        long reqTime = Instant.now().getEpochSecond();
        String sign = generateSignature(CLIENT_ID, reqTime, SECRET_KEY);
        
        Map<String, Object> params = new HashMap<>();
        params.put("client_id", CLIENT_ID);
        params.put("req_time", reqTime);
        params.put("sign", sign);
        
        ObjectMapper mapper = new ObjectMapper();
        String jsonBody = mapper.writeValueAsString(params);
        
        HttpClient client = HttpClient.newHttpClient();
        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create(BASE_URL + "/client_data"))
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(jsonBody))
            .build();
        
        HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());
        return response.body();
    }
}
```

---

## 注意事项

1. **时间同步**：确保客户端系统时间准确，请求时间戳与服务器时间差异不能超过5秒
2. **签名大小写**：签名必须使用小写MD5值
3. **数据类型**：响应中的数值类型明确（int/float），不会返回字符串
4. **空值处理**：如果查询结果为空，`data` 字段返回空数组 `[]`，而不是 `null`
5. **时区**：所有时间戳使用UTC时区
6. **请求频率**：建议控制请求频率，避免过于频繁的请求

---

## 技术支持

如有问题，请联系技术支持团队。

**API版本**: v1  
**最后更新**: 2024-01-15

