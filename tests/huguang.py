# !/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CPL API测试脚本
用于测试FuseClick的getOffers API
"""

import json

import requests


def get_ad_data(api_key, domain):
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
    url = f"http://{domain}:5858/api/country"

    # 构建参数
    post_data = {
        "key": api_key,
        "startdate": "2026-03-10",
        "enddate": "2026-03-15",
        "username": "yinghe"
    }

    try:
        # 发送GET请求
        response = requests.post(url, json=post_data)

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
    api_key = "0bb7cedcb40997a5784d1fd38df601e1"
    domain = "103.146.79.52"  # 实际应用域名

    # 调用API获取数据
    print("正在获取Offer数据...")
    ret_set = get_ad_data(api_key=api_key, domain=domain)

    if ret_set is not None:
        data = ret_set.get('data',{})
        print(data)

    else:
        print("未获取到数据")


if __name__ == "__main__":
    main()
