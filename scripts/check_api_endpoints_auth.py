#!/usr/bin/env python3
"""
API端点权限检查脚本

功能：
- 自动检查所有API端点是否使用了正确的权限依赖
- 识别缺少认证或授权的端点
- 生成检查报告

使用方法：
    python scripts/check_api_endpoints_auth.py
"""
import ast
import os
import sys
from pathlib import Path
from typing import List, Dict, Tuple
import re

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class EndpointChecker:
    """API端点检查器"""
    
    def __init__(self):
        self.endpoints_dir = project_root / "app" / "api" / "api_v1" / "endpoints"
        self.issues: List[Dict] = []
        self.stats = {
            "total_endpoints": 0,
            "with_auth": 0,
            "with_admin": 0,
            "missing_auth": 0,
            "public_endpoints": 0
        }
    
    def check_file(self, file_path: Path) -> List[Dict]:
        """检查单个文件中的端点"""
        issues = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                tree = ast.parse(content, filename=str(file_path))
        except Exception as e:
            print(f"⚠️  无法解析文件 {file_path}: {e}")
            return issues
        
        # 检查文件中的路由装饰器
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # 检查函数装饰器
                decorators = [self._get_decorator_name(d) for d in node.decorator_list]
                
                # 查找路由装饰器
                router_decorator = None
                for decorator in decorators:
                    if decorator and ('router.get' in decorator or 
                                     'router.post' in decorator or 
                                     'router.put' in decorator or 
                                     'router.delete' in decorator or
                                     'router.patch' in decorator):
                        router_decorator = decorator
                        break
                
                if router_decorator:
                    self.stats["total_endpoints"] += 1
                    
                    # 检查函数参数中的依赖
                    has_auth = False
                    has_admin = False
                    is_public = False
                    
                    # 检查是否是公开端点（登录、登出等）
                    if node.name in ['login', 'logout'] or 'login' in node.name.lower():
                        is_public = True
                        self.stats["public_endpoints"] += 1
                    
                    # 检查函数参数
                    for arg in node.args.args:
                        if isinstance(arg.annotation, ast.Name):
                            if arg.annotation.id == 'User':
                                has_auth = True
                        elif isinstance(arg.annotation, ast.Attribute):
                            if arg.annotation.attr == 'User':
                                has_auth = True
                    
                    # 检查默认值中的Depends
                    for default in node.args.defaults:
                        if isinstance(default, ast.Call):
                            func_name = self._get_function_name(default.func)
                            if 'get_current_user' in func_name:
                                has_auth = True
                                self.stats["with_auth"] += 1
                            elif 'require_admin' in func_name:
                                has_admin = True
                                has_auth = True
                                self.stats["with_admin"] += 1
                    
                    # 检查dependencies参数（在装饰器中）
                    for decorator in node.decorator_list:
                        if isinstance(decorator, ast.Call):
                            for keyword in decorator.keywords:
                                if keyword.arg == 'dependencies':
                                    if isinstance(keyword.value, ast.List):
                                        for dep in keyword.value.elts:
                                            dep_name = self._get_function_name(dep)
                                            if 'require_admin' in dep_name:
                                                has_admin = True
                                                has_auth = True
                                                self.stats["with_admin"] += 1
                                            elif 'get_current_user' in dep_name:
                                                has_auth = True
                                                self.stats["with_auth"] += 1
                    
                    # 判断是否需要认证
                    if not is_public and not has_auth:
                        # 检查路径是否包含公开路径
                        path_patterns = ['/login', '/logout', '/s/', '/postback', '/client_', '/bft/']
                        file_str = str(file_path)
                        is_public_path = any(pattern in file_str for pattern in path_patterns)
                        
                        if not is_public_path:
                            self.stats["missing_auth"] += 1
                            issues.append({
                                "file": str(file_path.relative_to(project_root)),
                                "function": node.name,
                                "line": node.lineno,
                                "decorator": router_decorator,
                                "issue": "缺少认证依赖（应使用 Depends(get_current_user) 或 Depends(require_admin)）"
                            })
        
        return issues
    
    def _get_decorator_name(self, decorator) -> str:
        """获取装饰器名称"""
        if isinstance(decorator, ast.Name):
            return decorator.id
        elif isinstance(decorator, ast.Attribute):
            return f"{self._get_attr_name(decorator)}"
        elif isinstance(decorator, ast.Call):
            return self._get_function_name(decorator.func)
        return None
    
    def _get_attr_name(self, node: ast.Attribute) -> str:
        """获取属性名称"""
        if isinstance(node.value, ast.Name):
            return f"{node.value.id}.{node.attr}"
        elif isinstance(node.value, ast.Attribute):
            return f"{self._get_attr_name(node.value)}.{node.attr}"
        return node.attr
    
    def _get_function_name(self, node) -> str:
        """获取函数名称"""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return self._get_attr_name(node)
        return str(node)
    
    def check_all(self) -> Tuple[List[Dict], Dict]:
        """检查所有端点文件"""
        if not self.endpoints_dir.exists():
            print(f"❌ 端点目录不存在: {self.endpoints_dir}")
            return [], {}
        
        # 遍历所有Python文件
        for file_path in self.endpoints_dir.rglob("*.py"):
            # 跳过__init__.py和example文件
            if file_path.name.startswith('__') or 'example' in file_path.name.lower():
                continue
            
            issues = self.check_file(file_path)
            self.issues.extend(issues)
        
        return self.issues, self.stats
    
    def generate_report(self) -> str:
        """生成检查报告"""
        report = []
        report.append("=" * 80)
        report.append("API端点权限检查报告")
        report.append("=" * 80)
        report.append("")
        
        # 统计信息
        report.append("📊 统计信息:")
        report.append(f"  总端点数: {self.stats['total_endpoints']}")
        report.append(f"  有认证: {self.stats['with_auth']}")
        report.append(f"  需要管理员: {self.stats['with_admin']}")
        report.append(f"  公开端点: {self.stats['public_endpoints']}")
        report.append(f"  缺少认证: {self.stats['missing_auth']}")
        report.append("")
        
        # 问题列表
        if self.issues:
            report.append("⚠️  发现的问题:")
            report.append("")
            for i, issue in enumerate(self.issues, 1):
                report.append(f"{i}. {issue['file']}:{issue['line']}")
                report.append(f"   函数: {issue['function']}")
                report.append(f"   装饰器: {issue['decorator']}")
                report.append(f"   问题: {issue['issue']}")
                report.append("")
        else:
            report.append("✅ 未发现问题！所有端点都有正确的权限检查。")
            report.append("")
        
        report.append("=" * 80)
        
        return "\n".join(report)


def main():
    """主函数"""
    print("🔍 开始检查API端点权限...")
    print("")
    
    checker = EndpointChecker()
    issues, stats = checker.check_all()
    
    report = checker.generate_report()
    print(report)
    
    # 保存报告到文件
    report_file = project_root / "docs" / "API端点权限检查报告.md"
    report_file.parent.mkdir(parents=True, exist_ok=True)
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report)
    
    print(f"\n📄 报告已保存到: {report_file.relative_to(project_root)}")
    
    # 返回退出码
    if issues:
        print("\n❌ 发现需要修复的问题，请检查上述报告。")
        return 1
    else:
        print("\n✅ 所有端点权限检查通过！")
        return 0


if __name__ == "__main__":
    sys.exit(main())

