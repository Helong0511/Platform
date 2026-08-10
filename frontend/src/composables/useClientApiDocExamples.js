/**
 * 组合式函数 - 客户 API 文档示例代码生成
 * @file composables/useClientApiDocExamples.js
 */
import { computed, onMounted, ref, watch } from 'vue';
import { useAuthStore } from '@/store';
import {
  buildClientApiSignString,
  formatTodayDate,
  generateClientApiSign
} from '@/utils/clientApiSignature';
import { getClientApiKey } from '@/api/client-api';

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

  const secretKey = ref('');

  onMounted(async () => {
    if (!clientId.value) return;
    try {
      const data = await getClientApiKey();
      secretKey.value = data?.key ?? '';
      await refreshSigns();
    } catch {
      secretKey.value = '';
    }
  });

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

  const signProducts = ref('');
  const signAdDataAll = ref('');
  const signAdDataDay = ref('');
  const signAdDataAllCountry = ref('');
  const signAdDataWithPage = ref('');

  async function refreshSigns() {
    if (!hasCredentials.value) {
      signProducts.value = '';
      signAdDataAll.value = '';
      signAdDataDay.value = '';
      signAdDataAllCountry.value = '';
      signAdDataWithPage.value = '';
      return;
    }
    const base = { clientId: clientId.value, reqTime: rt.value };
    const skVal = secretKey.value;
    signProducts.value = await generateClientApiSign(base, skVal);
    signAdDataAll.value = await generateClientApiSign(
      { ...base, dataType: 'all', startDate: td.value, endDate: td.value },
      skVal
    );
    signAdDataDay.value = await generateClientApiSign(
      { ...base, dataType: 'day', startDate: td.value, endDate: td.value },
      skVal
    );
    signAdDataAllCountry.value = await generateClientApiSign(
      {
        ...base,
        dataType: 'all',
        dimension: 'country',
        startDate: td.value,
        endDate: td.value
      },
      skVal
    );
    signAdDataWithPage.value = await generateClientApiSign(
      {
        ...base,
        dataType: 'all',
        dimension: 'country',
        startDate: td.value,
        endDate: td.value,
        page: 1,
        pageSize: 1000
      },
      skVal
    );
  }

  watch([clientId, secretKey, exampleReqTime, todayDate], refreshSigns, {
    immediate: true
  });

  const adDataSignTempStr = computed(() => {
    if (!hasCredentials.value) return '';
    return buildClientApiSignString(
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

  const adDataSignWithDimensionTempStr = computed(() => {
    if (!hasCredentials.value) return '';
    return buildClientApiSignString(
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

  const productSignTempStr = computed(() => {
    if (!hasCredentials.value) return '';
    return buildClientApiSignString(
      { clientId: clientId.value, reqTime: rt.value },
      secretKey.value
    );
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

  const adDataRequestWithPageJson = computed(() => {
    if (!hasCredentials.value) {
      return `{
  "client_id": "您的客户ID",
  "req_time": ${rt.value},
  "sign": "登录后自动生成",
  "data_type": "all",
  "dimension": "country",
  "start_date": "${td.value}",
  "end_date": "${td.value}",
  "page": 1,
  "page_size": 1000
}`;
    }
    return JSON.stringify(
      {
        client_id: Number(clientId.value),
        req_time: rt.value,
        sign: signAdDataWithPage.value,
        data_type: 'all',
        dimension: 'country',
        start_date: td.value,
        end_date: td.value,
        page: 1,
        page_size: 1000
      },
      null,
      2
    );
  });

  const pythonSignProducts = computed(
    () => `import hmac
import hashlib
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

# 5. HMAC-SHA256 签名（推荐；MD5 仍兼容）
sign = hmac.new(
    SECRET_KEY.encode('utf-8'),
    temp_str.encode('utf-8'),
    hashlib.sha256,
).hexdigest().lower()
# sign = ${signProducts.value ? `'${signProducts.value}'` : '（需配置密钥后生成）'}`
  );

  const pythonSignAdData = computed(
    () => `import hmac
import hashlib
import time

# 参数（查询广告数据接口）
client_id = ${cid.value}
req_time = ${rt.value}  # 页面加载时的时间戳（10位秒级），实际请求请用 int(time.time())
data_type = 'all'  # 必填参数：'all' 或 'day'
dimension = 'country'  # 可选：country / ad_unit / ad_unit_country / all；明细不传默认 country
start_date = '${td.value}'  # 当天日期
end_date = '${td.value}'  # 当天日期
page = 1  # 可选；显式传入时须参与签名
page_size = 1000  # 可选；不传默认 1000，最大 5000；显式传入时须参与签名
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
if page is not None:
    params['page'] = str(page)
if page_size is not None:
    params['page_size'] = str(page_size)

# 2. 按字母顺序排序
sorted_keys = sorted(params.keys())

# 3. 拼接字符串
temp_str = '&'.join([f"{key}={params[key]}" for key in sorted_keys])
# 结果: ${adDataSignWithDimensionTempStr.value || adDataSignTempStr.value || 'client_id=...&data_type=all&...'}

# 4. 追加密钥
temp_str = temp_str + f'&key={SECRET_KEY}'

# 5. HMAC-SHA256 签名（推荐；MD5 仍兼容）
sign = hmac.new(
    SECRET_KEY.encode('utf-8'),
    temp_str.encode('utf-8'),
    hashlib.sha256,
).hexdigest().lower()
# sign = ${signAdDataWithPage.value ? `'${signAdDataWithPage.value}'` : '（需配置密钥后生成）'}`
  );

  const pythonFullExample = computed(
    () => `import hmac
import hashlib
import time
import requests
import json

# 配置信息
BASE_URL = 'https://client.btfrx.online/api/v1'
CLIENT_ID = ${cid.value}
SECRET_KEY = '${sk.value}'

def generate_signature(client_id, req_time, secret_key, data_type=None, dimension=None,
                       start_date=None, end_date=None, page=None, page_size=None):
    """生成 HMAC-SHA256 签名（MD5 仍向后兼容）
    注意：page / page_size 仅在显式传入时参与签名；不传则服务端默认 page=1、page_size=1000。
    """
    params = {
        'client_id': str(client_id),
        'req_time': str(req_time)
    }
    
    if data_type:
        params['data_type'] = str(data_type)
    if dimension:
        params['dimension'] = str(dimension)
    if start_date:
        params['start_date'] = str(start_date)
    if end_date:
        params['end_date'] = str(end_date)
    if page is not None:
        params['page'] = str(page)
    if page_size is not None:
        params['page_size'] = str(page_size)
    
    sorted_keys = sorted(params.keys())
    temp_str = '&'.join([f"{key}={params[key]}" for key in sorted_keys])
    temp_str = temp_str + f'&key={secret_key}'
    
    return hmac.new(
        secret_key.encode('utf-8'),
        temp_str.encode('utf-8'),
        hashlib.sha256,
    ).hexdigest().lower()

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

def get_ad_data(data_type, start_date=None, end_date=None, dimension=None, page=None, page_size=None):
    """获取广告数据
    Args:
        data_type: 必填，'all' 明细 或 'day' 日汇总
        start_date: 可选，起始日期（格式：YYYY-MM-DD）
        end_date: 可选，终止日期（格式：YYYY-MM-DD）
        dimension: 可选，country / ad_unit / ad_unit_country / all；all 仅用于原始全量明细
        page: 可选，页码（1～100000）；不传默认 1；显式传入须参与签名
        page_size: 可选，每页条数；不传默认 1000，最大 5000；显式传入须参与签名
    """
    req_time = int(time.time())
    sign = generate_signature(
        CLIENT_ID, req_time, SECRET_KEY, data_type, dimension,
        start_date, end_date, page, page_size
    )
    
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
    if page is not None:
        params['page'] = page
    if page_size is not None:
        params['page_size'] = page_size
    
    headers = {'Content-Type': 'application/json'}
    response = requests.post(
        f'{BASE_URL}/client_data',
        headers=headers,
        json=params,
        timeout=10
    )
    
    return response.json()

def get_all_ad_data(data_type, start_date=None, end_date=None, dimension=None, page_size=5000):
    """分页拉取固定数据集；若拉取期间数据变化则中止并要求重试。"""
    all_rows = []
    seen_detail_ids = set()
    expected_total = None
    page = 1
    total_pages = 1
    while page <= total_pages:
        if page > 100000:
            raise RuntimeError('总页数超过接口上限 100000，请缩小日期范围')
        result = get_ad_data(
            data_type=data_type,
            start_date=start_date,
            end_date=end_date,
            dimension=dimension,
            page=page,
            page_size=page_size,
        )
        if int(result.get('code') or 0) != 200:
            raise RuntimeError(f"接口请求失败: {result.get('message') or result}")
        rows = result.get('data') or []
        total = int(result.get('total') or 0)
        if expected_total is None:
            expected_total = total
        elif total != expected_total:
            raise RuntimeError('分页期间 total 发生变化，请从第 1 页重新拉取')
        total_pages = int(result.get('total_pages') or (1 if total == 0 else 0))
        for row in rows:
            row_id = row.get('id')
            if data_type == 'all' and row_id is not None:
                if row_id in seen_detail_ids:
                    raise RuntimeError('检测到跨页重复 ID，数据可能正在变化，请重新拉取')
                seen_detail_ids.add(row_id)
            all_rows.append(row)
        page += 1
        if not rows:
            break
    if expected_total is not None and len(all_rows) != expected_total:
        raise RuntimeError(
            f'分页结果不完整：期望 {expected_total} 条，实际 {len(all_rows)} 条，请重新拉取'
        )
    return {'total': len(all_rows), 'data': all_rows}

# 使用示例（日期为当天 ${td.value}）
if __name__ == '__main__':
    today = '${td.value}'
    
    # 获取产品列表
    products_result = get_products()
    print("产品列表:", json.dumps(products_result, indent=2, ensure_ascii=False))
    
    # 获取详细广告数据（按国家维度，推荐；带分页）
    ad_data_result = get_ad_data(
        data_type='all', dimension='country',
        start_date=today, end_date=today, page=1, page_size=1000
    )
    print("按国家-详细数据:", json.dumps(ad_data_result, indent=2, ensure_ascii=False))
    
    # 获取每日汇总（按国家维度）
    daily_summary_result = get_ad_data(data_type='day', dimension='country', start_date=today, end_date=today)
    print("按国家-每日汇总:", json.dumps(daily_summary_result, indent=2, ensure_ascii=False))`
  );

  const javaFullExample = computed(() => {
    const id = cid.value;
    const key = sk.value;
    const today = td.value;
    return `import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
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
    
    private static String generateSignature(int clientId, long reqTime, String secretKey) {
        return generateSignature(clientId, reqTime, secretKey, null, null, null, null, null, null);
    }
    
    private static String generateSignature(int clientId, long reqTime, String secretKey, 
                                             String dataType, String dimension, String startDate, String endDate,
                                             Integer page, Integer pageSize) {
        try {
            Map<String, String> params = new LinkedHashMap<>();
            params.put("client_id", String.valueOf(clientId));
            params.put("req_time", String.valueOf(reqTime));
            
            if (dataType != null && !dataType.isEmpty()) {
                params.put("data_type", dataType);
            }
            if (dimension != null && !dimension.isEmpty()) {
                params.put("dimension", dimension);
            }
            if (startDate != null && !startDate.isEmpty()) {
                params.put("start_date", startDate);
            }
            if (endDate != null && !endDate.isEmpty()) {
                params.put("end_date", endDate);
            }
            if (page != null) {
                params.put("page", String.valueOf(page));
            }
            if (pageSize != null) {
                params.put("page_size", String.valueOf(pageSize));
            }
            
            List<String> sortedKeys = new ArrayList<>(params.keySet());
            Collections.sort(sortedKeys);
            
            StringBuilder sb = new StringBuilder();
            for (String key : sortedKeys) {
                if (sb.length() > 0) {
                    sb.append("&");
                }
                sb.append(key).append("=").append(params.get(key));
            }
            sb.append("&key=").append(secretKey);
            
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(secretKey.getBytes("UTF-8"), "HmacSHA256"));
            byte[] digest = mac.doFinal(sb.toString().getBytes("UTF-8"));
            
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
     * @param dataType 必填，'all' 明细 或 'day' 日汇总
     * @param startDate 可选，起始日期（格式：YYYY-MM-DD）
     * @param endDate 可选，终止日期（格式：YYYY-MM-DD）
     * @param dimension 可选，country / ad_unit / ad_unit_country / all；all 仅用于原始全量明细
     * @param page 可选，页码（1～100000）；不传默认 1；显式传入须参与签名
     * @param pageSize 可选，每页条数；不传默认 1000，最大 5000；显式传入须参与签名
     */
    public static String getAdData(String dataType, String startDate, String endDate, String dimension,
                                   Integer page, Integer pageSize) throws Exception {
        long reqTime = Instant.now().getEpochSecond();
        String sign = generateSignature(CLIENT_ID, reqTime, SECRET_KEY, dataType, dimension,
                                        startDate, endDate, page, pageSize);
        
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
        if (page != null) {
            params.put("page", page);
        }
        if (pageSize != null) {
            params.put("page_size", pageSize);
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
        getAdData("all", today, today, "country", 1, 1000);
        getAdData("day", today, today, "country", null, null);
    }
}`;
  });

  return {
    exampleReqTime,
    clientId,
    secretKey,
    todayDate,
    hasCredentials,
    signProducts,
    signAdDataAll,
    signAdDataDay,
    signAdDataAllCountry,
    signAdDataWithPage,
    productRequestJson,
    adDataRequestAllJson,
    adDataRequestAllWithDimensionJson,
    adDataRequestDayJson,
    adDataRequestWithPageJson,
    pythonSignProducts,
    pythonSignAdData,
    pythonFullExample,
    javaFullExample
  };
}
