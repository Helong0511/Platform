#!/usr/bin/env python3
"""
PostBack 转发流程测试脚本

测试完整的 PostBack 转发流程，使用用户提供的示例数据
"""
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.postback.forwarding.placeholder_resolver import PlaceholderResolver
from app.core.postback.forwarding.url_builder import UrlBuilder


def test_placeholder_resolution():
    """测试占位符解析"""
    print("=== 测试占位符解析 ===")
    
    # 测试数据
    base_url = "http://d36nq33iarpos0.cloudfront.net/?clickid={click_id}&payout={payout}"
    
    click_association_data = {
        'click_id': 'braTzfrfdb9zeaYRhHAKYDbwWhfmKrMkdHJM9mrEwt',
        'offer_id': '71',
        'publisher_id': '4',
        'advertiser_id': '12',
        'short_link_id': '109',
        'url_params': {
            'offer_id': '71',
            'channel_id': '4',
            'click_id': '6022-7a218d01c01b151-5906-22'
        }
    }
    
    conversion_data = {
        'conversion_id': 'braTzfrfdb9zeaYRhHAKYDbwWhfmKrMkdHJM9mrEwt',
        'payout': 2.7,
        'event_name': 'conversion'
    }
    
    # 合并数据
    url_data = {**conversion_data, **click_association_data}
    
    # 解析占位符
    resolved_url = PlaceholderResolver.resolve(base_url, url_data)
    print(f"原始 URL: {base_url}")
    print(f"解析后 URL: {resolved_url}")
    print()
    
    return resolved_url


def test_url_builder(resolved_url):
    """测试 URL 构建"""
    print("=== 测试 URL 构建 ===")
    
    # 测试数据
    click_association_data = {
        'click_id': 'braTzfrfdb9zeaYRhHAKYDbwWhfmKrMkdHJM9mrEwt',
        'offer_id': '71',
        'publisher_id': '4',
        'advertiser_id': '12',
        'short_link_id': '109',
        'url_params': {
            'offer_id': '71',
            'channel_id': '4',
            'click_id': '6022-7a218d01c01b151-5906-22'
        }
    }
    
    conversion_data = {
        'conversion_id': 'braTzfrfdb9zeaYRhHAKYDbwWhfmKrMkdHJM9mrEwt',
        'payout': 2.7,
        'event_name': 'conversion'
    }
    
    # 构建 URL
    final_url, params = UrlBuilder.build_postback_url(
        resolved_url,
        conversion_data,
        click_association_data
    )
    
    print(f"最终 URL: {final_url}")
    print(f"构建的参数: {params}")
    print()
    
    return final_url, params


def test_post_data_construction():
    """测试 POST 数据构建"""
    print("=== 测试 POST 数据构建 ===")
    
    # 测试数据
    click_association_data = {
        'click_id': 'braTzfrfdb9zeaYRhHAKYDbwWhfmKrMkdHJM9mrEwt',
        'offer_id': '71',
        'publisher_id': '4',
        'advertiser_id': '12',
        'short_link_id': '109',
        'url_params': {
            'offer_id': '71',
            'channel_id': '4',
            'click_id': '6022-7a218d01c01b151-5906-22'
        }
    }
    
    conversion_data = {
        'conversion_id': 'braTzfrfdb9zeaYRhHAKYDbwWhfmKrMkdHJM9mrEwt',
        'payout': 2.7,
        'event_name': 'conversion'
    }
    
    # 模拟 POST 数据构建
    json_data = {}
    
    # 从 conversion_data 中提取数据
    if conversion_data.get('payout'):
        json_data['payout'] = conversion_data['payout']
    if conversion_data.get('conversion_id'):
        json_data['conversion_id'] = conversion_data['conversion_id']
    if conversion_data.get('event_name'):
        json_data['event_name'] = conversion_data['event_name']
    
    # 从 click_association 中提取数据，优先使用 url_params
    url_params = click_association_data.get('url_params', {})
    if url_params.get('click_id'):
        json_data['clickid'] = url_params['click_id']
        json_data['click_id'] = url_params['click_id']
    elif click_association_data.get('click_id'):
        json_data['clickid'] = click_association_data['click_id']
        json_data['click_id'] = click_association_data['click_id']
    
    if url_params.get('offer_id'):
        json_data['offer_id'] = url_params['offer_id']
    elif click_association_data.get('offer_id'):
        json_data['offer_id'] = click_association_data['offer_id']
    
    print(f"POST JSON 数据: {json_data}")
    print()
    
    return json_data


def main():
    """主测试函数"""
    print("PostBack 转发流程测试")
    print("=" * 50)
    
    # 测试 1: 占位符解析
    resolved_url = test_placeholder_resolution()
    
    # 测试 2: URL 构建
    final_url, params = test_url_builder(resolved_url)
    
    # 测试 3: POST 数据构建
    post_data = test_post_data_construction()
    
    print("=== 测试结果验证 ===")
    print(f"期望的 GET URL: http://d36nq33iarpos0.cloudfront.net/?clickid=6022-7a218d01c01b151-5906-22&payout=2.7")
    print(f"实际的 GET URL: {final_url}")
    print(f"URL 匹配: {final_url == 'http://d36nq33iarpos0.cloudfront.net/?clickid=6022-7a218d01c01b151-5906-22&payout=2.7'}")
    print()
    
    print(f"期望的 POST 数据: {{'clickid': '6022-7a218d01c01b151-5906-22', 'payout': 2.7}}")
    print(f"实际的 POST 数据: {post_data}")
    print(f"POST 数据匹配: {'clickid' in post_data and post_data['clickid'] == '6022-7a218d01c01b151-5906-22' and post_data['payout'] == 2.7}")
    print()
    
    print("测试完成!")


if __name__ == "__main__":
    main()
