#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CPL API测试脚本
用于测试FuseClick的getOffers API
"""

import requests
import json

def get_offers(api_key, domain, page=1, limit=500, country=None, status=None):
    """
    获取Offer数据
    
    Args:
        api_key (str): API密钥
        domain (str): 应用域名
        page (int): 页码，默认为1
        limit (int): 每页数量，默认为500
        country (str): 国家代码，可选
        status (str): 状态，可选
    
    Returns:
        dict: API返回的JSON数据
    """
    # 构建API URL
    url = f"http://{domain}/api/v2/getOffers"
    
    # 构建参数
    params = {
        "key": api_key,
        "page": page,
        "limit": limit,
        "a": 6
    }
    
    # 添加可选参数
    if country:
        params["country"] = country
    if status:
        params["status"] = status
    
    try:
        # 发送GET请求
        response = requests.get(url, params=params)
        
        # 尝试解析响应内容
        try:
            data = response.json()
            return data
        except json.JSONDecodeError as e:
            print(f"JSON解析失败: {e}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"请求失败: {e}")
        return None

def main():
    """
    主函数
    """
    # 配置参数
    API_KEY = "933FA279AECBD04D1ED32780F1E938DE"
    DOMAIN = "fusionsky.fuseclick.com"  # 实际应用域名
    
    # 调用API获取数据
    print("正在获取Offer数据...")
    result = get_offers(
        api_key=API_KEY,
        domain=DOMAIN,
        page=1,
        limit=500,
        # country="CN",  # 示例：获取中国的Offer
        status="Active"  # 示例：获取活跃状态的Offer
    )
    
    # 处理结果
    if result:
        print(result)
        print("\nAPI响应状态:")
        print(f"HTTP状态码: {result.get('httpStatus')}")
        print(f"错误码: {result.get('errorCode')}")
        print(f"错误信息: {result.get('errorMessage')}")
        print(f"消息: {result.get('message')}")
        
        # 打印数据部分
        data_dict = result.get('data', {})
        offers = data_dict.get('content', [])
        print(f"\n获取到 {len(offers)} 个Offer:")
        
        # 打印前几个Offer的简要信息
        for i, offer in enumerate(offers, 1):  # 只打印前5个
            print(f"\nOffer {i}:")
            print(f"ID: {offer.get('id')}")
            print(f"名称: {offer.get('name')}")
            print(f"状态: {offer.get('status')}")
            print(f"类型: {offer.get('type')}")
            print(f"预览URL: {offer.get('preview_url')}")
            print(f"跟踪URL: {offer.get('tracking_link')}")
    else:
        print("未获取到数据")

if __name__ == "__main__":
    main()
