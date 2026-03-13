"""
测试程序：UniqueChannelSync API 测试
用于测试 UniqueChannelServer 的 POST 请求接口
"""
import httpx
import json
from typing import Dict, Any


class UniqueChannelTester:
    """UniqueChannelSync 测试类"""
    
    def __init__(self, base_url: str = "https://linkes.com/UniqueChannelServer/UniqueChannelSync"):
        """
        初始化测试器
        
        Args:
            base_url: API 基础 URL
        """
        self.base_url = base_url
        self.client = httpx.Client(timeout=30.0)  # 设置30秒超时
    
    def build_form_data(self, test_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        构建 form-data 格式的请求数据
        
        Args:
            test_data: 自定义测试数据，如果为 None 则使用默认数据
            
        Returns:
            form-data 格式的请求数据
        """
        if test_data:
            return test_data
        
        # 使用图片中的默认测试数据
        return {
            "data": "TEST123",
            "os": "test",
            "time": "20250202190608",
            "device": "test",
            "uuid": "test",
            "mac": "test",
            "testIp": "123.123.123.123",
            "testTime": "12345678901",
            "phone": "12345678910",
            "email": "12345678910@email.com",
            "deviceId": "test",
            "phone1": "12345678910",
            "ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 13_8_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 [FBAN/FBIOS;FBDV/iPhone12,1;FBMD/iPhone;FBSN/iOS;FBSV/13.8.1;FBSS/2;FBCR/;FBID/phone;FBLC/zh_CN;FBRV/0]"
        }
    
    def send_request(self, test_data: Dict[str, Any] = None) -> httpx.Response:
        """
        发送 POST 请求
        
        Args:
            test_data: 自定义测试数据
            
        Returns:
            HTTP 响应对象
        """
        form_data = self.build_form_data(test_data)
        
        print(f"[请求] 发送 POST 请求到: {self.base_url}")
        print(f"[请求] 请求数据:")
        for key, value in form_data.items():
            print(f"  {key}: {value}")
        
        try:
            # 发送 form-data 格式的 POST 请求
            response = self.client.post(
                self.base_url,
                data=form_data
            )
            
            print(f"\n[响应] 状态码: {response.status_code}")
            print(f"[响应] 响应头: {dict(response.headers)}")
            print(f"[响应] 响应内容:")
            
            try:
                # 尝试解析为 JSON
                json_response = response.json()
                print(json.dumps(json_response, ensure_ascii=False, indent=2))
            except:
                # 如果不是 JSON，直接打印文本
                print(response.text)
            
            return response
            
        except httpx.RequestError as e:
            print(f"\n[错误] 请求失败: {str(e)}")
            raise
    
    def close(self):
        """关闭 HTTP 客户端"""
        self.client.close()


def main():
    """主函数 - 运行测试"""
    print("=" * 60)
    print("UniqueChannelSync API 测试程序")
    print("=" * 60)
    
    # 创建测试器实例
    tester = UniqueChannelTester()
    
    try:
        # 发送测试请求
        print("\n开始执行测试...\n")
        response = tester.send_request()
        
        # 检查响应状态
        if response.status_code == 200:
            print("\n✓ 测试成功！")
        else:
            print(f"\n✗ 测试失败，状态码: {response.status_code}")
            
    except Exception as e:
        print(f"\n✗ 测试过程中发生错误: {str(e)}")
    finally:
        # 关闭客户端
        tester.close()
        print("\n" + "=" * 60)
        print("测试结束")
        print("=" * 60)


if __name__ == "__main__":
    main()
