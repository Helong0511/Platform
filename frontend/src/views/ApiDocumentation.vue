<!--
  API 文档页：客户对接接口说明
  @file views/ApiDocumentation.vue
-->
<template>
  <!-- 页面主模板 -->
<div class="api-documentation-container">
    <el-card class="documentation-card">
      <!-- 卡片标题栏 -->
    <template #header>
        <div class="card-header">
          <h1>客户API对接文档</h1>
          <el-tag type="info" size="large">API版本: v1</el-tag>
        </div>
      </template>

      <el-alert
        v-if="!hasCredentials"
        title="未获取到您的 API 对接参数"
        type="warning"
        :closable="false"
        show-icon
        style="margin-bottom: 16px;"
      >
        请确认已使用客户账号登录，且管理员已为您开启 API 并配置密钥。如仍无法显示，请刷新页面或联系管理员。
      </el-alert>
      <div v-else class="info-box credentials-box">
        <p><strong>您的对接参数（已自动填入下方所有示例）</strong></p>
        <ul>
          <li><strong>client_id</strong>：<code>{{ clientId }}</code></li>
          <li><strong>SECRET_KEY</strong>：<code>{{ secretKey }}</code>（仅用于签名，请勿通过请求体传递）</li>
          <li><strong>查询日期</strong>：<code>{{ todayDate }}</code>（<code>start_date</code> 与 <code>end_date</code> 均为当天）</li>
          <li><strong>示例 req_time</strong>：<code>{{ exampleReqTime }}</code>（页面加载时生成；JSON 示例中的 <code>sign</code> 已按此时间戳计算，实际调用请使用 <code>int(time.time())</code> 并重新签名）</li>
        </ul>
      </div>

      <!-- 概述 -->
      <section class="doc-section">
        <h2>概述</h2>
        <p>客户API提供客户通过API密钥访问的接口，包括查询产品信息和广告数据。所有接口都需要进行签名验证，确保请求的安全性。</p>
        <div class="info-box">
          <p><strong>基础URL</strong>: <code>https://client.btfrx.online/api/v1</code></p>
          <p><strong>请求格式</strong>: JSON (Content-Type: application/json)</p>
          <p><strong>响应格式</strong>: JSON</p>
        </div>
      </section>

      <!-- 认证方式 -->
      <section class="doc-section">
        <h2>认证方式</h2>
        <h3>签名算法</h3>
        <p>所有API请求都需要进行MD5签名验证，签名算法如下：</p>
        <ol>
          <li><strong>准备参数</strong>：将请求参数放入参数字典
            <ul>
              <li><code>/client_products</code> 接口：<code>client_id</code>、<code>req_time</code></li>
              <li><code>/client_data</code> 接口：<code>client_id</code>、<code>req_time</code>、<code>data_type</code>（必填），以及可选参数 <code>dimension</code>、<code>start_date</code>、<code>end_date</code>（如果提供则参与签名）</li>
            </ul>
          </li>
          <li><strong>参数排序</strong>：按字母顺序对参数键进行排序</li>
          <li><strong>拼接字符串</strong>：将参数拼接为 <code>key=value&key=value</code> 格式</li>
          <li><strong>追加密钥</strong>：在末尾追加 <code>&key={SECRET_KEY}</code></li>
          <li><strong>MD5加密</strong>：对整个字符串进行MD5加密并转为小写</li>
        </ol>
        <div class="info-box">
          <p><strong>注意</strong>：</p>
          <ul>
            <li><code>/client_data</code> 接口的 <code>data_type</code> 参数是必填的，必须包含在签名计算中</li>
            <li><code>dimension</code> 为可选参数；传入时须参与签名。取值：<code>country</code>（按国家）、<code>ad_unit</code>（按广告单元）、<code>ad_unit_country</code>（按广告单元+国家，<code>country_ad_unit</code> 为兼容别名）</li>
            <li>若同时存在国家 API 与广告单元 API 数据，强烈建议传入 <code>dimension</code>，否则不传时返回全量行可能重复统计</li>
            <li>只有非空参数才参与签名计算。如果未提供可选参数，则不包含在签名中</li>
          </ul>
        </div>

        <el-collapse class="code-example">
          <el-collapse-item title="Python签名示例（查询产品）" name="python-products">
            <pre><code>{{ pythonSignProducts }}</code></pre>
          </el-collapse-item>
          <el-collapse-item title="Python签名示例（查询广告数据）" name="python-ad-data">
            <pre><code>{{ pythonSignAdData }}</code></pre>
          </el-collapse-item>
          <el-collapse-item title="Java签名示例（查询产品）" name="java-products">
            <pre><code>import java.security.MessageDigest;
import java.time.Instant;
import java.util.*;

public String generateSignature(int clientId, long reqTime, String secretKey) {
    // 准备参数（查询产品接口）
    Map&lt;String, String&gt; params = new LinkedHashMap&lt;&gt;();
    params.put("client_id", String.valueOf(clientId));
    params.put("req_time", String.valueOf(reqTime));
    
    // 排序并拼接
    List&lt;String&gt; sortedKeys = new ArrayList&lt;&gt;(params.keySet());
    Collections.sort(sortedKeys);
    
    StringBuilder sb = new StringBuilder();
    for (String key : sortedKeys) {
        if (sb.length() &gt; 0) {
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
}</code></pre>
          </el-collapse-item>
          <el-collapse-item title="Java签名示例（查询广告数据）" name="java-ad-data">
            <pre><code>import java.security.MessageDigest;
import java.time.Instant;
import java.util.*;

public String generateSignature(int clientId, long reqTime, String secretKey, 
                                 String dataType, String dimension, String startDate, String endDate) {
    try {
        // 准备参数（查询广告数据接口，data_type 是必填的）
        Map&lt;String, String&gt; params = new LinkedHashMap&lt;&gt;();
        params.put("client_id", String.valueOf(clientId));
        params.put("data_type", dataType);  // 必填参数
        params.put("req_time", String.valueOf(reqTime));
        
        // 添加可选参数（如果提供）
        if (dimension != null && !dimension.isEmpty()) {
            params.put("dimension", dimension);
        }
        if (startDate != null && !startDate.isEmpty()) {
            params.put("start_date", startDate);
        }
        if (endDate != null && !endDate.isEmpty()) {
            params.put("end_date", endDate);
        }
        
        // 排序并拼接
        List&lt;String&gt; sortedKeys = new ArrayList&lt;&gt;(params.keySet());
        Collections.sort(sortedKeys);
        
        StringBuilder sb = new StringBuilder();
        for (String key : sortedKeys) {
            if (sb.length() &gt; 0) {
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
}</code></pre>
          </el-collapse-item>
        </el-collapse>

        <div class="warning-box">
          <el-alert
            title="请求验证规则"
            type="warning"
            :closable="false"
            show-icon
          >
            <ul>
              <li><strong>客户ID验证</strong>：验证 <code>client_id</code> 是否存在且已激活</li>
              <li><strong>时间戳验证</strong>：请求时间戳与服务器时间差异不能超过5秒（正负5秒）</li>
              <li><strong>签名验证</strong>：验证MD5签名是否正确</li>
            </ul>
            <p><strong>注意</strong>：<code>SECRET_KEY</code> 不通过请求传递，而是从数据库查询客户的 <code>key</code> 字段进行验证。</p>
          </el-alert>
        </div>
      </section>

      <!-- API接口列表 -->
      <section class="doc-section">
        <h2>API接口列表</h2>

        <!-- 查询产品信息 -->
        <el-card class="api-card" shadow="hover">
          <template #header>
            <div class="api-header">
              <el-tag type="success" size="large">POST</el-tag>
              <span class="api-path">/client_products</span>
              <span class="api-title">查询产品信息</span>
            </div>
          </template>

          <p>获取客户的所有激活产品列表。</p>

          <h4>请求参数</h4>
          <el-table :data="productRequestParams" border style="width: 100%">
            <el-table-column prop="name" label="参数名" width="150" />
            <el-table-column prop="type" label="类型" width="100" />
            <el-table-column prop="required" label="必填" width="80" />
            <el-table-column prop="description" label="说明" />
          </el-table>

          <h4>请求示例</h4>
          <el-collapse>
            <el-collapse-item title="查看请求示例" name="product-request">
              <pre><code>{{ productRequestJson }}</code></pre>
            </el-collapse-item>
          </el-collapse>

          <h4>响应示例</h4>
          <el-collapse>
            <el-collapse-item title="查看响应示例" name="product-response">
              <pre><code>{
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
}</code></pre>
            </el-collapse-item>
          </el-collapse>

          <div class="note-box">
            <p><strong>注意事项</strong>：</p>
            <ul>
              <li>如果客户没有产品，<code>data</code> 字段返回空数组 <code>[]</code>，而不是 <code>null</code></li>
              <li>产品按ID升序排列</li>
              <li>只返回已激活的产品</li>
            </ul>
          </div>
        </el-card>

        <!-- 查询广告数据 -->
        <el-card class="api-card" shadow="hover" style="margin-top: 20px;">
          <template #header>
            <div class="api-header">
              <el-tag type="success" size="large">POST</el-tag>
              <span class="api-path">/client_data</span>
              <span class="api-title">查询广告数据</span>
            </div>
          </template>

          <p>获取客户的广告数据。支持明细（<code>data_type=all</code>）与日汇总（<code>data_type=day</code>）。可通过可选参数 <code>dimension</code> 指定统计维度，与后台「广告数据」报表一致。</p>

          <h4>请求参数</h4>
          <el-table :data="adDataRequestParams" border style="width: 100%">
            <el-table-column prop="name" label="参数名" width="150" />
            <el-table-column prop="type" label="类型" width="100" />
            <el-table-column prop="required" label="必填" width="80" />
            <el-table-column prop="description" label="说明" />
          </el-table>

          <h4>请求示例</h4>
          <el-collapse>
            <el-collapse-item title="查看请求示例（详细数据，兼容旧版不传 dimension）" name="ad-data-request-all">
              <pre><code>{{ adDataRequestAllJson }}</code></pre>
            </el-collapse-item>
            <el-collapse-item title="查看请求示例（详细数据，按国家 dimension=country）" name="ad-data-request-all-dimension">
              <pre><code>{{ adDataRequestAllWithDimensionJson }}</code></pre>
            </el-collapse-item>
            <el-collapse-item title="查看请求示例（每日汇总）" name="ad-data-request-day">
              <pre><code>{{ adDataRequestDayJson }}</code></pre>
            </el-collapse-item>
          </el-collapse>

          <h4>响应示例</h4>
          <el-collapse>
            <el-collapse-item title="查看响应示例（详细数据模式）" name="ad-data-response-all">
              <pre><code>{
  "code": 200,
  "message": "成功获取 30 条广告数据",
  "data": [
    {
      "date": "2024-01-15",
      "product_name": "产品A",
      "ad_unit": "banner_us",
      "country_code": "US",
      "country_name_zh": "美国",
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
      "date": "2024-01-15",
      "product_name": "产品A",
      "ad_unit": "",
      "country_code": "CN",
      "country_name_zh": "中国",
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
}</code></pre>
            </el-collapse-item>
            <el-collapse-item title="查看响应示例（每日汇总模式）" name="ad-data-response-day">
              <pre><code>{
  "code": 200,
  "message": "成功获取 15 条广告数据",
  "data": [
    {
      "date": "2024-01-15",
      "product_name": "产品A",
      "ad_unit": "",
      "country_code": "ZZ",
      "country_name_zh": "全部区域",
      "request_count": 50000,
      "match_count": 40000,
      "coverage_rate": 80.0,
      "display_count": 37500,
      "display_rate": 93.75,
      "click_count": 2500,
      "click_rate": 6.67,
      "ecpm": 5.25,
      "revenue": 1968.75
    },
    {
      "date": "2024-01-15",
      "product_name": "产品A",
      "ad_unit": "slot_01",
      "country_code": "ZZ",
      "country_name_zh": "全部区域",
      "request_count": 12000,
      "match_count": 9600,
      "coverage_rate": 80.0,
      "display_count": 9000,
      "display_rate": 93.75,
      "click_count": 600,
      "click_rate": 6.67,
      "ecpm": 5.30,
      "revenue": 477.0
    },
    {
      "date": "2024-01-16",
      "product_name": "产品A",
      "ad_unit": "",
      "country_code": "ZZ",
      "country_name_zh": "全部区域",
      "request_count": 60000,
      "match_count": 48000,
      "coverage_rate": 80.0,
      "display_count": 45000,
      "display_rate": 93.75,
      "click_count": 3000,
      "click_rate": 6.67,
      "ecpm": 5.30,
      "revenue": 2385.0
    }
  ]
}</code></pre>
            </el-collapse-item>
          </el-collapse>

          <h4>响应字段说明</h4>
          <el-table :data="adDataResponseFields" border style="width: 100%">
            <el-table-column prop="field" label="字段名" width="180" />
            <el-table-column prop="type" label="类型" width="100" />
            <el-table-column prop="description" label="说明" />
          </el-table>

          <div class="note-box">
            <p><strong>数据说明</strong>：</p>
            <ul>
              <li><strong>覆盖率</strong> = 匹配数 / 请求数 × 100</li>
              <li><strong>展示率</strong> = 展示数 / 匹配数 × 100</li>
              <li><strong>点击率</strong> = 点击数 / 展示数 × 100</li>
              <li><strong>eCPM</strong>: 每千次展示的有效成本</li>
              <li><strong>收益</strong>: 实际收益</li>
            </ul>
            <p><strong>统计维度（dimension，可选）</strong>：</p>
            <ul>
              <li><code>country</code>：国家维度（<code>ad_unit</code> 为空，有国家代码，含 AA/ZZ）</li>
              <li><code>ad_unit</code>：广告单元维度（无国家代码即 NULL/空串，<code>ad_unit</code> 有值）</li>
              <li><code>ad_unit_country</code>：广告单元与国家交叉明细（<code>country_ad_unit</code> 为兼容别名）</li>
              <li>不传：返回库中全部匹配行（兼容旧版；双 API 场景可能重复统计）</li>
            </ul>
            <p><strong>数据模式说明</strong>：</p>
            <ul>
              <li><strong>data_type='all'（详细数据）</strong>：返回明细行；配合 <code>dimension</code> 时与后台「详细报表」一致</li>
              <li><strong>data_type='day'（每日汇总）</strong>：按日汇总；配合 <code>dimension</code> 时与后台「每日统计」一致；未传 <code>dimension</code> 时仍按「日期+产品+广告单元」汇总（历史行为）</li>
            </ul>
            <p><strong>广告单元（ad_unit）说明</strong>：</p>
            <ul>
              <li>类型为字符串，始终返回，不会为 <code>null</code></li>
              <li>无广告单元或为空时返回 <code>""</code>（空字符串）</li>
              <li>字段顺序在 JSON 中位于 <code>product_name</code> 之后、<code>country_code</code> 之前</li>
            </ul>
            <p><strong>国家代码说明</strong>：</p>
            <ul>
              <li><strong>详细模式（data_type='all'）</strong>：返回实际的国家二字代码（如 "US"、"CN"、"GB" 等），如果无法识别国家则返回 "AA"（未知区域），如果为空则返回空字符串</li>
              <li><strong>汇总模式（data_type='day'）</strong>：统一返回 "ZZ"（全部区域），表示该数据是多个国家的汇总</li>
              <li><strong>特殊代码</strong>：
                <ul>
                  <li><code>"ZZ"</code>: 全部区域（汇总数据）</li>
                  <li><code>"AA"</code>: 未知区域（无法识别的国家）</li>
                </ul>
              </li>
            </ul>
            <p><strong>注意事项</strong>：</p>
            <ul>
              <li>如果不提供 <code>start_date</code> 和 <code>end_date</code>，默认返回当前月的数据（从当月1日到最后一天）</li>
              <li>如果只提供 <code>start_date</code> 或 <code>end_date</code>，另一个使用当前月的对应日期</li>
              <li>数据按日期升序排列</li>
              <li>如果查询范围内没有数据，<code>data</code> 字段返回空数组 <code>[]</code>，而不是 <code>null</code></li>
              <li>所有数值类型明确（int/float），不会返回字符串</li>
              <li>浮点数保留2位小数</li>
              <li>数据查询遵循产品历史分配表，只返回分配给该客户的产品数据</li>
            </ul>
          </div>
        </el-card>
      </section>

      <!-- 错误码说明 -->
      <section class="doc-section">
        <h2>错误码说明</h2>
        
        <el-alert
          title="重要提示"
          type="info"
          :closable="false"
          show-icon
          style="margin-bottom: 20px;"
        >
          所有错误响应都返回HTTP状态码200，通过响应体中的 <code>code</code> 字段区分错误类型。
        </el-alert>

        <el-table :data="errorCodes" border style="width: 100%">
          <el-table-column prop="code" label="错误码" width="100" />
          <el-table-column prop="message" label="说明" />
          <el-table-column prop="solution" label="解决方案" />
        </el-table>
      </section>

      <!-- 完整示例代码 -->
      <section class="doc-section">
        <h2>完整示例代码</h2>
        
        <el-tabs v-model="activeTab" type="border-card">
          <el-tab-pane label="Python示例" name="python">
            <pre><code>{{ pythonFullExample }}</code></pre>
          </el-tab-pane>
          <el-tab-pane label="Java示例" name="java">
            <pre><code>{{ javaFullExample }}</code></pre>
          </el-tab-pane>
        </el-tabs>
      </section>

      <!-- 注意事项 -->
      <section class="doc-section">
        <h2>注意事项</h2>
        <el-alert
          type="warning"
          :closable="false"
          show-icon
        >
          <ul>
            <li><strong>时间同步</strong>：确保客户端系统时间准确，请求时间戳与服务器时间差异不能超过5秒</li>
            <li><strong>签名大小写</strong>：签名必须使用小写MD5值</li>
            <li><strong>数据类型</strong>：响应中的数值类型明确（int/float），不会返回字符串</li>
            <li><strong>空值处理</strong>：如果查询结果为空，<code>data</code> 字段返回空数组 <code>[]</code>，而不是 <code>null</code></li>
            <li><strong>时区</strong>：所有时间戳使用UTC时区</li>
            <li><strong>请求频率</strong>：建议控制请求频率，避免过于频繁的请求</li>
          </ul>
        </el-alert>
      </section>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue';
import { ElCard, ElTag, ElCollapse, ElCollapseItem, ElTable, ElTableColumn, ElAlert, ElTabs, ElTabPane } from 'element-plus';
import { useAuthStore } from '@/store';
import { getCurrentUserInfo } from '@/api/user';
import { useClientApiDocExamples } from '@/composables/useClientApiDocExamples';
import { logger } from '@/utils/logger';

const authStore = useAuthStore();
const activeTab = ref('python');

const {
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
} = useClientApiDocExamples();

onMounted(async () => {
  if (authStore.userInfo?.client?.key) {
    return;
  }
  try {
    const userData = await getCurrentUserInfo({ silent: true });
    if (userData && typeof userData === 'object') {
      authStore.userInfo = { ...authStore.userInfo, ...userData };
      sessionStorage.setItem('userInfo', JSON.stringify(authStore.userInfo));
    }
  } catch (err) {
    logger.warn('API 对接文档页加载客户密钥失败:', err);
    // 不登出：页面顶部已有未获取参数的提示
  }
});

// 产品接口请求参数
const productRequestParams = [
  { name: 'client_id', type: 'int', required: '是', description: '客户ID' },
  { name: 'req_time', type: 'int', required: '是', description: '请求时间戳（10位秒级，Unix时间戳）' },
  { name: 'sign', type: 'string', required: '是', description: 'MD5签名（小写）' }
];

// 广告数据接口请求参数
const adDataRequestParams = [
  { name: 'client_id', type: 'int', required: '是', description: '客户ID' },
  { name: 'req_time', type: 'int', required: '是', description: '请求时间戳（10位秒级，Unix时间戳）' },
  { name: 'data_type', type: 'string', required: '是', description: '数据类型：\'all\' 明细，\'day\' 日汇总' },
  { name: 'dimension', type: 'string', required: '否', description: '统计维度：country / ad_unit / ad_unit_country（country_ad_unit 为兼容别名）；与后台报表一致，双 API 客户建议必传' },
  { name: 'start_date', type: 'string', required: '否', description: '起始日期（格式：YYYY-MM-DD），可选，不提供则使用当前月第一天' },
  { name: 'end_date', type: 'string', required: '否', description: '终止日期（格式：YYYY-MM-DD），可选，不提供则使用当前月最后一天' },
  { name: 'sign', type: 'string', required: '是', description: 'MD5签名（小写），包含所有非空参数' }
];

// 广告数据响应字段
const adDataResponseFields = [
  { field: 'date', type: 'string', description: '数据日期（ISO格式：YYYY-MM-DD）' },
  { field: 'product_name', type: 'string', description: '产品名称（确保不为null）' },
  { field: 'ad_unit', type: 'string', description: '广告单元（可为空字符串）' },
  { field: 'country_code', type: 'string', description: '国家二字代码；dimension=country 时为实际国家；dimension=ad_unit 或 day 未传 dimension 时多为 ZZ；dimension=ad_unit_country 时为实际国家' },
  { field: 'country_name_zh', type: 'string', description: '国家中文名称；与 country_code 对应，无国家拆分时为「全部区域」' },
  { field: 'request_count', type: 'int', description: '请求数（整数）' },
  { field: 'match_count', type: 'int', description: '匹配数（整数）' },
  { field: 'coverage_rate', type: 'float', description: '覆盖率（%，浮点数，保留2位小数）' },
  { field: 'display_count', type: 'int', description: '展示数（整数）' },
  { field: 'display_rate', type: 'float', description: '展示率（%，浮点数，保留2位小数）' },
  { field: 'click_count', type: 'int', description: '点击数（整数）' },
  { field: 'click_rate', type: 'float', description: '点击率（%，浮点数，保留2位小数）' },
  { field: 'ecpm', type: 'float', description: 'eCPM（浮点数，保留2位小数）' },
  { field: 'revenue', type: 'float', description: '收益（浮点数，保留2位小数）' }
];

// 错误码列表
const errorCodes = [
  { code: 200, message: '成功', solution: '-' },
  { code: 2201, message: '客户不存在或未激活', solution: '检查 client_id 是否正确，确认客户已激活' },
  { code: 2205, message: '参数验证不通过', solution: '检查以下项：1. 请求时间戳是否在允许范围内（正负5秒） 2. 签名是否正确 3. 参数格式是否正确' },
  { code: 2501, message: '操作失败', solution: '查看 detail 字段获取详细错误信息' }
];
</script>

<style scoped>
.api-documentation-container {
  padding: 20px;
  max-width: 1200px;
  margin: 0 auto;
}

.documentation-card {
  min-height: calc(100vh - 200px);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-header h1 {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
}

.doc-section {
  margin-bottom: 40px;
}

.doc-section h2 {
  font-size: 20px;
  font-weight: 600;
  margin-bottom: 16px;
  padding-bottom: 8px;
  border-bottom: 2px solid #e4e7ed;
}

.doc-section h3 {
  font-size: 18px;
  font-weight: 600;
  margin-top: 24px;
  margin-bottom: 12px;
}

.doc-section h4 {
  font-size: 16px;
  font-weight: 600;
  margin-top: 20px;
  margin-bottom: 12px;
}

.credentials-box {
  margin-bottom: 20px;
}

.info-box {
  background-color: var(--primary-light);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  padding: var(--spacing-lg);
  margin: var(--spacing-lg) 0;
}

.info-box p {
  margin: var(--spacing-sm) 0;
  color: var(--text-primary);
}

.info-box code {
  background-color: var(--bg-secondary);
  padding: var(--spacing-xs) var(--spacing-sm);
  border-radius: var(--radius-sm);
  font-family: 'Courier New', monospace;
  color: var(--primary-color);
}

.warning-box {
  margin: 20px 0;
}

.warning-box ul {
  margin: 8px 0;
  padding-left: 20px;
}

.code-example {
  margin: 16px 0;
}

.code-example pre {
  background-color: #f5f5f5;
  border: 1px solid #ddd;
  border-radius: 4px;
  padding: 16px;
  overflow-x: auto;
  margin: 0;
}

.code-example code {
  font-family: 'Courier New', monospace;
  font-size: 14px;
  line-height: 1.5;
}

.api-card {
  margin-bottom: 20px;
}

.api-header {
  display: flex;
  align-items: center;
  gap: 12px;
}

.api-path {
  font-family: 'Courier New', monospace;
  font-weight: var(--font-weight-semibold);
  color: var(--primary-color);
}

.api-title {
  font-size: 16px;
  font-weight: 600;
}

.note-box {
  background-color: var(--warning-light);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  padding: var(--spacing-lg);
  margin-top: var(--spacing-lg);
}

.note-box ul {
  margin: 8px 0;
  padding-left: 20px;
}

.note-box p {
  margin: 8px 0;
  font-weight: 600;
}

pre {
  background-color: #f5f5f5;
  border: 1px solid #ddd;
  border-radius: 4px;
  padding: 16px;
  overflow-x: auto;
  margin: 12px 0;
}

pre code {
  font-family: 'Courier New', monospace;
  font-size: 14px;
  line-height: 1.5;
}

code {
  background-color: #f5f5f5;
  padding: 2px 6px;
  border-radius: 3px;
  font-family: 'Courier New', monospace;
  font-size: 14px;
}

ol, ul {
  margin: 12px 0;
  padding-left: 24px;
}

li {
  margin: 8px 0;
}

/* 响应式设计 - 统一使用标准断点 */
/* 平板端优化 (768px - 1024px) */
@media (min-width: 768px) and (max-width: 1024px) {
  .api-documentation-container {
    padding: var(--spacing-lg);
  }
  
  .documentation-card :deep(.el-card__body) {
    padding: var(--spacing-lg);
  }
}

/* 移动端优化 (< 768px) */
@media (max-width: 767px) {
  .api-documentation-container {
    padding: var(--spacing-md);
  }

  .card-header {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--spacing-md);
  }

  .api-header {
    flex-wrap: wrap;
  }
  
  .documentation-card :deep(.el-card__body) {
    padding: var(--spacing-md);
  }
  
  .doc-section {
    margin-bottom: var(--spacing-lg);
  }
  
  .doc-section h2 {
    font-size: var(--font-size-xl);
  }
  
  .doc-section h3 {
    font-size: var(--font-size-lg);
  }
  
  .info-box,
  .note-box {
    padding: var(--spacing-md);
    margin: var(--spacing-md) 0;
  }
  
  pre {
    padding: var(--spacing-md);
    font-size: var(--font-size-sm);
  }
  
  /* 移动端表格优化 */
  .el-table {
    font-size: var(--font-size-sm);
    min-width: 500px; /* 确保表格有最小宽度，可以横向滚动 */
  }
  
  .el-table :deep(.el-table__cell) {
    padding: var(--spacing-xs) var(--spacing-sm);
    word-break: break-word;
  }
  
  .el-table :deep(.el-table__header th),
  .el-table :deep(.el-table__body td) {
    font-size: var(--font-size-xs);
    padding: var(--spacing-xs);
  }
  
  /* 表格容器优化 */
  .api-card :deep(.el-card__body) {
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }
  
  .el-table :deep(.el-table__header-wrapper) {
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }
  
  .el-table :deep(.el-table__body-wrapper) {
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }
}

/* 小屏手机优化 (< 480px) */
@media (max-width: 480px) {
  .api-documentation-container {
    padding: var(--spacing-sm);
  }
  
  .documentation-card :deep(.el-card__body) {
    padding: var(--spacing-sm);
  }
  
  .doc-section h2 {
    font-size: var(--font-size-lg);
  }
  
  .doc-section h3 {
    font-size: var(--font-size-base);
  }
  
  pre {
    padding: var(--spacing-sm);
    font-size: var(--font-size-xs);
  }
}
</style>

