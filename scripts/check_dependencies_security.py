"""
依赖安全检查脚本
检查依赖版本和安全漏洞
"""
import subprocess
import sys
import json
from pathlib import Path

def check_outdated_packages():
    """检查过期的包"""
    print("=" * 60)
    print("检查过期的依赖包...")
    print("=" * 60)
    
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "list", "--outdated", "--format=json"],
            capture_output=True,
            text=True,
            check=True
        )
        
        outdated = json.loads(result.stdout)
        
        if outdated:
            print(f"\n发现 {len(outdated)} 个过期包：\n")
            for pkg in outdated:
                print(f"  - {pkg['name']}: {pkg['version']} -> {pkg['latest_version']}")
        else:
            print("\n✅ 所有依赖包都是最新版本")
            
    except subprocess.CalledProcessError as e:
        print(f"❌ 检查失败: {e}")
    except json.JSONDecodeError:
        print("❌ 无法解析输出")


def check_security_vulnerabilities():
    """检查安全漏洞（需要 pip-audit）"""
    print("\n" + "=" * 60)
    print("检查安全漏洞...")
    print("=" * 60)
    
    try:
        # 检查是否安装了 pip-audit
        subprocess.run(
            [sys.executable, "-m", "pip", "show", "pip-audit"],
            capture_output=True,
            check=True
        )
        
        # 运行 pip-audit
        result = subprocess.run(
            [sys.executable, "-m", "pip_audit", "--format=json"],
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.returncode == 0:
            try:
                vulnerabilities = json.loads(result.stdout)
                if vulnerabilities.get("vulnerabilities"):
                    print(f"\n⚠️  发现 {len(vulnerabilities['vulnerabilities'])} 个安全漏洞：\n")
                    for vuln in vulnerabilities["vulnerabilities"]:
                        print(f"  - {vuln.get('name', 'Unknown')}: {vuln.get('id', 'Unknown')}")
                        if vuln.get("fix_versions"):
                            print(f"    修复版本: {', '.join(vuln['fix_versions'])}")
                else:
                    print("\n✅ 未发现已知安全漏洞")
            except json.JSONDecodeError:
                print("⚠️  无法解析漏洞信息，请查看原始输出")
                print(result.stdout)
        else:
            print("⚠️  pip-audit 检查失败，可能需要安装: pip install pip-audit")
            print(result.stderr)
            
    except subprocess.CalledProcessError:
        print("⚠️  pip-audit 未安装")
        print("   安装命令: pip install pip-audit")
        print("   然后运行: pip-audit")


def check_requirements_file():
    """检查 requirements.txt 文件"""
    print("\n" + "=" * 60)
    print("检查 requirements.txt...")
    print("=" * 60)
    
    req_file = Path(__file__).parent.parent / "requirements.txt"
    
    if not req_file.exists():
        print("❌ requirements.txt 文件不存在")
        return
    
    print(f"\n✅ 找到 requirements.txt: {req_file}")
    
    # 读取并分析
    with open(req_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    print(f"\n共 {len(lines)} 行依赖定义")
    
    # 检查是否有固定版本
    pinned = sum(1 for line in lines if "==" in line and not line.strip().startswith("#"))
    print(f"固定版本: {pinned} 个")
    
    # 检查是否有版本范围
    ranges = sum(1 for line in lines if any(op in line for op in [">=", "<=", ">", "<"]) and not line.strip().startswith("#"))
    print(f"版本范围: {ranges} 个")


def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("依赖安全检查工具")
    print("=" * 60)
    
    check_requirements_file()
    check_outdated_packages()
    check_security_vulnerabilities()
    
    print("\n" + "=" * 60)
    print("检查完成")
    print("=" * 60)
    print("\n建议：")
    print("1. 定期更新依赖包")
    print("2. 使用 pip-audit 检查安全漏洞")
    print("3. 在生产环境部署前进行安全检查")
    print("4. 考虑使用依赖锁定文件（requirements.lock）")


if __name__ == "__main__":
    main()

