const https = require('https');
const crypto = require('crypto');

const BASE_URL = 'https://ch.tecnee.xyz';
const CLIENT_ID = 'KE11';
const PRIVATE_KEY = 'cded7587a3b1aad269b9c9f5248f8b7e';

const TARGET_DOMAIN = 'wo.kimdogtrainer.com';

function getTimestamp() {
    return Date.now();
}

function getTodayDate() {
    const today = new Date();
    const year = today.getFullYear();
    const month = String(today.getMonth() + 1).padStart(2, '0');
    const day = String(today.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

function generateSign(params, privateKey) {
    const allParams = { ...params, key: privateKey };
    const sortedKeys = Object.keys(allParams).sort();
    const queryString = sortedKeys.map(key => `${key}=${allParams[key]}`).join('&');
    return crypto.createHash('md5').update(queryString).digest('hex').toLowerCase();
}

function makeRequest(path, additionalParams = {}) {
    return new Promise((resolve, reject) => {
        const timestamp = getTimestamp();
        const params = { clientId: CLIENT_ID, timestamp: timestamp, ...additionalParams };
        const sign = generateSign(params, PRIVATE_KEY);
        const queryString = Object.keys({ ...params, sign })
            .map(key => `${key}=${encodeURIComponent({ ...params, sign }[key])}`)
            .join('&');
        const url = `${BASE_URL}${path}?${queryString}`;
        
        https.get(url, (res) => {
            let data = '';
            res.on('data', (chunk) => { data += chunk; });
            res.on('end', () => {
                try {
                    resolve({ statusCode: res.statusCode, data: JSON.parse(data) });
                } catch (error) {
                    resolve({ statusCode: res.statusCode, rawData: data });
                }
            });
        }).on('error', (error) => { reject(error); });
    });
}

async function checkDomainData() {
    const today = getTodayDate();
    console.log('========================================');
    console.log(`查询域名: ${TARGET_DOMAIN}`);
    console.log(`日期: ${today}`);
    console.log('========================================');
    
    const apis = [
 //       { name: '每日报告', path: '/api/channeldaily', key: 'domain_name', params: {} },
        { name: '国家报告', path: '/api/channelcountry', key: 'domain_name', params: {domain_name: TARGET_DOMAIN} },
     //   { name: '广告单元报告', path: '/api/channelunit', key: 'domain_name', params: {} }
    ];
    
    for (const api of apis) {
        console.log(`\n---------- ${api.name} ----------`);
        try {
            const params = {
                start_date: today,
                end_date: today,
                limit: 100
            }
            Object.assign(params, api.params)
            const result = await makeRequest(api.path, params);
            if (result.data && result.data.code === 1) {
                const data = result.data.data;
                const domainData = data.list.filter(item => item[api.key] === TARGET_DOMAIN);
                
                if (domainData.length > 0) {
                    console.log(`✅ 找到 ${domainData.length} 条数据:`);
                    domainData.forEach((item, index) => {
                        console.log(`\n数据 ${index + 1}:`);
                        if (item.date) console.log(`   日期: ${item.date}`);
                        if (item.domain_name) console.log(`   域名: ${item.domain_name}`);
                        if (item.country) console.log(`   国家: ${item.country}`);
                        if (item.ad_unit_id) console.log(`   广告单元ID: ${item.ad_unit_id}`);
                        if (item.ad_unit_name) console.log(`   广告单元名称: ${item.ad_unit_name}`);
                        if (item.ad_requests) console.log(`   广告请求: ${item.ad_requests}`);
                        if (item.ad_impressions) console.log(`   展示次数: ${item.ad_impressions}`);
                        if (item.clicks) console.log(`   点击次数: ${item.clicks}`);
                        if (item.estimated_earnings) console.log(`   预估收入: $${item.estimated_earnings}`);
                        if (item.channel_earnings) console.log(`   渠道收入: $${item.channel_earnings}`);
                        if (item.coverage_rate) console.log(`   覆盖率: ${item.coverage_rate}%`);
                        if (item.display_rate) console.log(`   展示率: ${item.display_rate}%`);
                        if (item.click_through_rate) console.log(`   点击率: ${item.click_through_rate}%`);
                        if (item.cpc) console.log(`   CPC: $${item.cpc}`);
                        if (item.ecpm) console.log(`   eCPM: $${item.ecpm}`);
                    });
                } else {
                    console.log(`❌ 未找到 ${TARGET_DOMAIN} 的数据`);
                }
            } else {
                console.log(`❌ 请求失败: ${result.data?.msg || '未知错误'}`);
            }
            
        } catch (error) {
            console.error(`❌ 请求异常: ${error.message}`);
        }
    }
    
    console.log('\n========================================');
}

checkDomainData();