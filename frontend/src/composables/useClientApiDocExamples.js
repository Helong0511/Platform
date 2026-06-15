/**
 * 组合式函数 - 客户 API 文档示例代码生成
 * @file composables/useClientApiDocExamples.js
 */
import { computed, ref } from 'vue';
import { useAuthStore } from '@/store';
import {
  formatTodayDate,
  generateClientApiSign
} from '@/utils/clientApiSignature';

/**
 * 组合式函数 - 客户 API 文档示例代码生成
 * @returns {Object} 响应式状态与业务操作方法
 */
export function useClientApiDocExamples() {
  const authStore = useAuthStore();
  // exampleReqTime 响应式状态
  const exampleReqTime = ref(Math.floor(Date.now() / 1000));

  const clientId = computed(() => {
    const client = authStore.userInfo?.client;
    if (client?.id != null) {
      return client.id;
    }
    if (authStore.userInfo?.client_id != null) {
      return authStore.userInfo.client_id;
    }
    return null;
  });

  const secretKey = computed(() => authStore.userInfo?.client?.key ?? '');
  const todayDate = computed(() => formatTodayDate());
  const hasCredentials = computed(
    () => clientId.value != null && Boolean(secretKey.value)
  );

  const cid = computed(() => clientId.value ?? '您的客户ID');
  const sk = computed(() =>
    secretKey.value ? secretKey.value : '您的API密钥'
  );
  const rt = computed(() => exampleReqTime.value);
  const td = computed(() => todayDate.value);

  const signProducts = computed(() => {
    if (!hasCredentials.value) return '';
    return generateClientApiSign(
      { clientId: clientId.value, reqTime: rt.value },
      secretKey.value
    );
  });

  const signAdDataAll = computed(() => {
    if (!hasCredentials.value) return '';
    return generateClientApiSign(
      {
        clientId: clientId.value,
        reqTime: rt.value,
        dataType: 'all',
        startDate: td.value,
        endDate: td.value
      },
      secretKey.value
    );
  });

  const signAdDataDay = computed(() => {
    if (!hasCredentials.value) return '';
    return generateClientApiSign(
      {
        clientId: clientId.value,
        reqTime: rt.value,
        dataType: 'day',
        startDate: td.value,
        endDate: td.value
      },
      secretKey.value
    );
  });

  const signAdDataAllCountry = computed(() => {
    if (!hasCredentials.value) return '';
    return generateClientApiSign(
      {
        clientId: clientId.value,
        reqTime: rt.value,
        dataType: 'all',
        dimension: 'country',
        startDate: td.value,
        endDate: td.value
      },
      secretKey.value
    );
  });

  const adDataSignTempStr = computed(() => {
    if (!hasCredentials.value) return '';
    return `client_id=${clientId.value}&data_type=all&end_date=${td.value}&req_time=${rt.value}&start_date=${td.value}&key=${secretKey.value}`;
  });

  const adDataSignWithDimensionTempStr = computed(() => {
    if (!hasCredentials.value) return '';
    return `client_id=${clientId.value}&data_type=all&dimension=country&end_date=${td.value}&req_time=${rt.value}&start_date=${td.value}&key=${secretKey.value}`;
  });

  const productSignTempStr = computed(() => {
    if (!hasCredentials.value) return '';
    return `client_id=${clientId.value}&req_time=${rt.value}&key=${secretKey.value}`;
  });

  const productRequestJson = computed(() => {
    if (!hasCredentials.value) {
      return `{
  "client_id": "您的客户ID",
  "req_time": ${rt.value},
  "sign": "登录后自动生成"
}`;
    }
    return JSON.stringify(
      {
        client_id: Number(clientId.value),
        req_time: rt.value,
        sign: signProducts.value
      },
      null,
      2
    );
  });

  const adDataRequestAllJson = computed(() => {
    if (!hasCredentials.value) {
      return `{
  "client_id": "您的客户ID",
  "req_time": ${rt.value},
  "sign": "登录后自动生成",
  "data_type": "all",
  "start_date": "${td.value}",
  "end_date": "${td.value}"
}`;
    }
    return JSON.stringify(
      {
        client_id: Number(clientId.value),
        req_time: rt.value,
        sign: signAdDataAll.value,
        data_type: 'all',
        start_date: td.value,
        end_date: td.value
      },
      null,
      2
    );
  });

  const adDataRequestAllWithDimensionJson = computed(() => {
    if (!hasCredentials.value) {
      return `{
  "client_id": "您的客户ID",
  "req_time": ${rt.value},
  "sign": "登录后自动生成",
  "data_type": "all",
  "dimension": "country",
  "start_date": "${td.value}",
  "end_date": "${td.value}"
}`;
    }
    return JSON.stringify(
      {
        client_id: Number(clientId.value),
        req_time: rt.value,
        sign: signAdDataAllCountry.value,
        data_type: 'all',
        dimension: 'country',
        start_date: td.value,
        end_date: td.value
      },
      null,
      2
    );
  });

  const adDataRequestDayJson = computed(() => {
    if (!hasCredentials.value) {
      return `{
  "client_id": "您的客户ID",
  "req_time": ${rt.value},
  "sign": "登录后自动生成",
  "data_type": "day",
  "start_date": "${td.value}",
  "end_date": "${td.value}"
}`;
    }
    return JSON.stringify(
      {
        client_id: Number(clientId.value),
        req_time: rt.value,
        sign: signAdDataDay.value,
        data_type: 'day',
        start_date: td.value,
        end_date: td.value
      },
      null,
      2
    );
  });

  const pythonSignProducts = computed(
    () => `import hashlib
import time

# 参数（查询产品接口）
client_id = ${cid.value}
req_time = ${rt.value}  # 页面加载时的时间戳（10位秒级），实际请求请用 int(time.time())
SECRET_KEY = '${sk.value}'

# 1. 准备参数
params = {
    'client_id': str(client_id),
    'req_time': str(req_time)
}

# 2. 按字母顺序排序
sorted_keys = sorted(params.keys())

# 3. 拼接字符串
temp_str = '&'.join([f"{key}={params[key]}" for key in sorted_keys])
# 结果: ${productSignTempStr.value || 'client_id=...&req_time=...'}

# 4. 追加密钥
temp_str = temp_str + f'&key={SECRET_KEY}'

# 5. MD5加密并转为小写
sign = hashlib.md5(temp_str.encode('utf-8')).hexdigest().lower()
# sign = ${signProducts.value ? `'${signProducts.value}'` : '（需配置密钥后生成）'}`
  );

  const pythonSignAdData = computed(
    () => `import hashlib
import time

# 参数（查询广告数据接口）
client_id = ${cid.value}
req_time = ${rt.value}  # 页面加载时的时间戳（10位秒级），实际请求请用 int(time.time())
data_type = 'all'  # 必填参数：'all' 或 'day'
dimension = 'country'  # 可选：country / ad_unit / country_ad_unit；不传则不过滤维度
start_date = '${td.value}'  # 当天日期
end_date = '${td.value}'  # 当天日期
SECRET_KEY = '${sk.value}'

# 1. 准备参数（data_type 是必填的）
params = {
    'client_id': str(client_id),
    'data_type': str(data_type),  # 必填参数
    'req_time': str(req_time)
}

# 添加可选参数（如果提供）
if dimension:
    params['dimension'] = str(dimension)
if start_date:
    params['start_date'] = str(start_date)
if end_date:
    params['end_date'] = str(end_date)

# 2. 按字母顺序排序
sorted_keys = sorted(params.keys())

# 3. 拼接字符串
temp_str = '&'.join([f"{key}={params[key]}" for key in sorted_keys])
# 结果: ${adDataSignWithDimensionTempStr.value || adDataSignTempStr.value || 'client_id=...&data_type=all&...'}

# 4. 追加密钥
temp_str = temp_str + f'&key={SECRET_KEY}'

# 5. MD5加密并转为小写
sign = hashlib.md5(temp_str.encode('utf-8')).hexdigest().lower()
# sign = ${signAdDataAllCountry.value ? `'${signAdDataAllCountry.value}'` : '（需配置密钥后生成）'}`
  );

  const pythonFullExample = computed(
    () => `import hashlib
import time
import requests
import json

# 配置信息
BASE_URL = 'https://client.btfrx.online/api/v1'
CLIENT_ID = ${cid.value}
SECRET_KEY = '${sk.value}'

def generate_signature(client_id, req_time, secret_key, data_type=None, dimension=None, start_date=None, end_date=None):
    """生成签名
    
    Args:
        client_id: 客户ID
        req_time: 请求时间戳
        secret_key: 密钥
        data_type: 数据类型（对于 /client_data 接口是必填的，'all' 或 'day'）
        dimension: 统计维度（可选，country / ad_unit / country_ad_unit）
        start_date: 起始日期（可选）
        end_date: 终止日期（可选）
    """
    params = {
        'client_id': str(client_id),
        'req_time': str(req_time)
    }
    
    # 添加参数（对于 /client_data 接口，data_type 是必填的）
    if data_type:
        params['data_type'] = str(data_type)
    if dimension:
        params['dimension'] = str(dimension)
    if start_date:
        params['start_date'] = str(start_date)
    if end_date:
        params['end_date'] = str(end_date)
    
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

def get_ad_data(data_type, start_date=None, end_date=None, dimension=None):
    """获取广告数据
    Args:
        data_type: 必填，'all' 明细 或 'day' 日汇总
        start_date: 可选，起始日期（格式：YYYY-MM-DD）
        end_date: 可选，终止日期（格式：YYYY-MM-DD）
        dimension: 可选，country / ad_unit / country_ad_unit（与后台报表一致；建议双 API 客户必传）
    """
    req_time = int(time.time())
    sign = generate_signature(CLIENT_ID, req_time, SECRET_KEY, data_type, dimension, start_date, end_date)
    
    params = {
        'client_id': CLIENT_ID,
        'req_time': req_time,
        'data_type': data_type,  # 必填参数
        'sign': sign
    }
    
    # 添加可选参数
    if dimension:
        params['dimension'] = dimension
    if start_date:
        params['start_date'] = start_date
    if end_date:
        params['end_date'] = end_date
    
    headers = {'Content-Type': 'application/json'}
    response = requests.post(
        f'{BASE_URL}/client_data',
        headers=headers,
        json=params,
        timeout=10
    )
    
    return response.json()

# 使用示例（日期为当天 ${td.value}）
if __name__ == '__main__':
    today = '${td.value}'
    
    # 获取产品列表
    products_result = get_products()
    print("产品列表:", json.dumps(products_result, indent=2, ensure_ascii=False))
    
    # 获取详细广告数据（按国家维度，推荐）
    ad_data_result = get_ad_data(data_type='all', dimension='country', start_date=today, end_date=today)
    print("按国家-详细数据:", json.dumps(ad_data_result, indent=2, ensure_ascii=False))
    
    # 获取每日汇总（按国家维度）
    daily_summary_result = get_ad_data(data_type='day', dimension='country', start_date=today, end_date=today)
    print("按国家-每日汇总:", json.dumps(daily_summary_result, indent=2, ensure_ascii=False))`
  );

  const javaFullExample = computed(() => {
    const id = cid.value;
    const key = sk.value;
    const today = td.value;
    return `import java.security.MessageDigest;
import java.time.Instant;
import java.util.*;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.URI;
import com.fasterxml.jackson.databind.ObjectMapper;

public class ClientAPI {
    private static final String BASE_URL = "https://client.btfrx.online/api/v1";
    private static final int CLIENT_ID = ${typeof id === 'number' ? id : id};
    private static final String SECRET_KEY = "${key}";
    
    // 查询产品接口的签名生成（不需要 data_type 参数）
    private static String generateSignature(int clientId, long reqTime, String secretKey) {
        return generateSignature(clientId, reqTime, secretKey, null, null, null, null);
    }
    
    // 查询广告数据接口的签名生成（data_type 是必填的）
    private static String generateSignature(int clientId, long reqTime, String secretKey, 
                                             String dataType, String dimension, String startDate, String endDate) {
        try {
            // 准备参数
            Map<String, String> params = new LinkedHashMap<>();
            params.put("client_id", String.valueOf(clientId));
            params.put("req_time", String.valueOf(reqTime));
            
            // 对于 /client_data 接口，data_type 是必填的
            if (dataType != null && !dataType.isEmpty()) {
                params.put("data_type", dataType);
            }
            if (dimension != null && !dimension.isEmpty()) {
                params.put("dimension", dimension);
            }
            
            // 添加可选参数（如果提供）
            if (startDate != null && !startDate.isEmpty()) {
                params.put("start_date", startDate);
            }
            if (endDate != null && !endDate.isEmpty()) {
                params.put("end_date", endDate);
            }
            
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
    
    /**
     * 获取广告数据
     * @param dataType 必填，数据类型，'all' 表示详细数据（按国家+广告单元），'day' 表示每日汇总（按产品+日期+广告单元）
     * @param startDate 可选，起始日期（格式：YYYY-MM-DD）
     * @param endDate 可选，终止日期（格式：YYYY-MM-DD）
     */
    public static String getAdData(String dataType, String startDate, String endDate, String dimension) throws Exception {
        long reqTime = Instant.now().getEpochSecond();
        String sign = generateSignature(CLIENT_ID, reqTime, SECRET_KEY, dataType, dimension, startDate, endDate);
        
        Map<String, Object> params = new HashMap<>();
        params.put("client_id", CLIENT_ID);
        params.put("req_time", reqTime);
        params.put("data_type", dataType);  // 必填参数
        params.put("sign", sign);
        
        // 添加可选参数
        if (dimension != null && !dimension.isEmpty()) {
            params.put("dimension", dimension);
        }
        if (startDate != null && !startDate.isEmpty()) {
            params.put("start_date", startDate);
        }
        if (endDate != null && !endDate.isEmpty()) {
            params.put("end_date", endDate);
        }
        
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
    
    // 使用示例（当天日期：${today}）
    public static void main(String[] args) throws Exception {
        String today = "${today}";
        getProducts();
        getAdData("all", today, today, "country");
        getAdData("day", today, today, "country");
    }
}`;
  });

  return {
    exampleReqTime,
    clientId,
    secretKey,
    todayDate,
    hasCredentials,
    productRequestJson,
    adDataRequestAllJson,
    adDataRequestAllWithDimensionJson,
    adDataRequestDayJson,
    pythonSignProducts,
    pythonSignAdData,
    pythonFullExample,
    javaFullExample
  };
}
