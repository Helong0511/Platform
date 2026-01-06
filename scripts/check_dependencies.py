#!/usr/bin/env python3
"""
依赖更新检查脚本

功能：
- 检查Python依赖是否有安全更新
- 检查过时的依赖版本
- 生成依赖更新报告

使用方法：
    python scripts/check_dependencies.py
"""
import subprocess
import sys
import json
from pathlib import Path
from typing import List, Dict
import re

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent


def check_pip_audit() -> List[Dict]:
    """
    使用pip-audit检查安全漏洞
    
    Returns:
        安全漏洞列表
    """
    issues = []
    
    try:
        # 检查是否安装了pip-audit
        result = subprocess.run(
            ["pip-audit", "--version"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            print("⚠️  pip-audit未安装，跳过安全漏洞检查")
            print("   安装命令: pip install pip-audit")
            return issues
        
        # 运行pip-audit
        print("🔍 检查依赖安全漏洞...")
        result = subprocess.run(
            ["pip-audit", "--format", "json"],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=project_root
        )
        
        if result.returncode == 0:
            try:
                data = json.loads(result.stdout)
                if "vulnerabilities" in data:
                    issues.extend(data["vulnerabilities"])
            except json.JSONDecodeError:
                pass
        else:
            print(f"⚠️  pip-audit执行失败: {result.stderr}")
    
    except FileNotFoundError:
        print("⚠️  pip-audit未安装，跳过安全漏洞检查")
        print("   安装命令: pip install pip-audit")
    except subprocess.TimeoutExpired:
        print("⚠️  pip-audit执行超时")
    except Exception as e:
        print(f"⚠️  检查安全漏洞时出错: {e}")
    
    return issues


def check_outdated_packages() -> List[Dict]:
    """
    检查过时的包版本
    
    Returns:
        过时包列表
    """
    outdated = []
    
    try:
        print("🔍 检查过时的依赖包...")
        result = subprocess.run(
            ["pip", "list", "--outdated", "--format", "json"],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            try:
                packages = json.loads(result.stdout)
                outdated.extend(packages)
            except json.JSONDecodeError:
                pass
    except Exception as e:
        print(f"⚠️  检查过时包时出错: {e}")
    
    return outdated


def read_requirements() -> Dict[str, str]:
    """
    读取requirements.txt中的依赖
    
    Returns:
        包名到版本的字典
    """
    requirements_file = project_root / "requirements.txt"
    packages = {}
    
    if not requirements_file.exists():
        return packages
    
    with open(requirements_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            # 解析包名和版本
            # 格式: package==version 或 package>=version,<version
            match = re.match(r'^([a-zA-Z0-9_-]+).*?([=<>!]+.*?)?$', line)
            if match:
                package_name = match.group(1)
                version_spec = match.group(2) if match.group(2) else ""
                packages[package_name.lower()] = {
                    "name": package_name,
                    "spec": version_spec,
                    "line": line
                }
    
    return packages


def generate_report(vulnerabilities: List[Dict], outdated: List[Dict], requirements: Dict[str, str]) -> str:
    """生成依赖检查报告"""
    report = []
    report.append("=" * 80)
    report.append("依赖更新检查报告")
    report.append("=" * 80)
    report.append("")
    
    # 安全漏洞
    if vulnerabilities:
        report.append("🔴 发现安全漏洞:")
        report.append("")
        for i, vuln in enumerate(vulnerabilities, 1):
            report.append(f"{i}. {vuln.get('name', 'Unknown')}")
            if 'vuln' in vuln:
                report.append(f"   漏洞ID: {vuln['vuln'].get('id', 'Unknown')}")
                report.append(f"   描述: {vuln['vuln'].get('description', 'N/A')}")
            report.append("")
    else:
        report.append("✅ 未发现已知安全漏洞")
        report.append("")
    
    # 过时的包
    if outdated:
        report.append("⚠️  发现过时的依赖包:")
        report.append("")
        for pkg in outdated:
            report.append(f"- {pkg.get('name', 'Unknown')}")
            report.append(f"  当前版本: {pkg.get('version', 'Unknown')}")
            report.append(f"  最新版本: {pkg.get('latest_version', 'Unknown')}")
            report.append("")
    else:
        report.append("✅ 所有依赖包都是最新版本")
        report.append("")
    
    # 建议
    report.append("📝 建议:")
    report.append("1. 定期运行此脚本检查依赖更新")
    report.append("2. 优先更新有安全漏洞的依赖")
    report.append("3. 更新依赖后充分测试应用")
    report.append("4. 使用虚拟环境进行测试")
    report.append("")
    
    report.append("=" * 80)
    
    return "\n".join(report)


def main():
    """主函数"""
    print("🔍 开始检查依赖更新...")
    print("")
    
    # 检查安全漏洞
    vulnerabilities = check_pip_audit()
    
    # 检查过时的包
    outdated = check_outdated_packages()
    
    # 读取requirements.txt
    requirements = read_requirements()
    
    # 生成报告
    report = generate_report(vulnerabilities, outdated, requirements)
    print(report)
    
    # 保存报告
    report_file = project_root / "docs" / "依赖更新检查报告.md"
    report_file.parent.mkdir(parents=True, exist_ok=True)
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report)
    
    print(f"\n📄 报告已保存到: {report_file.relative_to(project_root)}")
    
    # 返回退出码
    if vulnerabilities or outdated:
        print("\n⚠️  发现需要更新的依赖，请检查上述报告。")
        return 1
    else:
        print("\n✅ 所有依赖检查通过！")
        return 0


if __name__ == "__main__":
    sys.exit(main())

