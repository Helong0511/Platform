#!/usr/bin/env python3
"""
生成 RSA 密钥对用于 JWT RS256 算法

兼容 Windows 和 Linux/Ubuntu

使用方法:
    python scripts/generate_rsa_keys.py [--output-dir <目录>] [--key-size <大小>]

参数:
    --output-dir: 输出目录（默认: keys/）
    --key-size: 密钥大小，单位：位（默认: 2048）

示例:
    # Windows
    python scripts/generate_rsa_keys.py
    python scripts/generate_rsa_keys.py --output-dir keys --key-size 2048
    python scripts/generate_rsa_keys.py --output-dir E:\data\Platform\keys --key-size 2048
    
    # Linux/Ubuntu
    python3 scripts/generate_rsa_keys.py
    python3 scripts/generate_rsa_keys.py --output-dir /data/Platform/keys --key-size 2048
    python3 scripts/generate_rsa_keys.py --output-dir keys --key-size 2048
"""
import os
import sys
import argparse
import platform
from pathlib import Path
from typing import Tuple

try:
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.backends import default_backend
except ImportError:
    print("错误: 需要安装 cryptography 库")
    print("请运行: pip install cryptography")
    sys.exit(1)

# 检测操作系统
IS_WINDOWS = platform.system() == "Windows"
IS_LINUX = platform.system() == "Linux"


def generate_rsa_keypair(key_size: int = 2048) -> Tuple[str, str]:
    """
    生成 RSA 密钥对
    
    参数:
        key_size: 密钥大小（位），默认 2048
    
    返回:
        (private_key_pem, public_key_pem) 元组
    """
    # 生成私钥
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=key_size,
        backend=default_backend()
    )
    
    # 序列化私钥为 PEM 格式
    private_key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    ).decode('utf-8')
    
    # 获取公钥
    public_key = private_key.public_key()
    
    # 序列化公钥为 PEM 格式
    public_key_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode('utf-8')
    
    return private_key_pem, public_key_pem


def save_keys(private_key: str, public_key: str, output_dir: Path):
    """
    保存密钥到文件（跨平台兼容）
    
    参数:
        private_key: 私钥 PEM 字符串
        public_key: 公钥 PEM 字符串
        output_dir: 输出目录
    
    返回:
        (private_key_path, public_key_path) 元组
    """
    try:
        # 创建输出目录（跨平台兼容）
        output_dir.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        raise PermissionError(f"无法创建目录 {output_dir.absolute()}：权限不足")
    except Exception as e:
        raise Exception(f"创建目录失败: {e}")
    
    # 设置文件路径（使用 Path 对象，自动处理路径分隔符）
    private_key_path = output_dir / "private_key.pem"
    public_key_path = output_dir / "public_key.pem"
    
    # 保存私钥（使用 UTF-8 编码，跨平台兼容）
    try:
        with open(private_key_path, 'w', encoding='utf-8') as f:
            f.write(private_key)
    except PermissionError:
        raise PermissionError(f"无法写入文件 {private_key_path}：权限不足")
    except Exception as e:
        raise Exception(f"保存私钥失败: {e}")
    
    # 设置私钥文件权限（仅所有者可读）
    # Windows 不支持 chmod，但文件系统会自动处理权限
    if not IS_WINDOWS:
        try:
            os.chmod(private_key_path, 0o600)
        except Exception as e:
            print(f"警告: 无法设置私钥文件权限: {e}")
    
    # 保存公钥（使用 UTF-8 编码，跨平台兼容）
    try:
        with open(public_key_path, 'w', encoding='utf-8') as f:
            f.write(public_key)
    except PermissionError:
        raise PermissionError(f"无法写入文件 {public_key_path}：权限不足")
    except Exception as e:
        raise Exception(f"保存公钥失败: {e}")
    
    # 设置公钥文件权限（所有人可读）
    # Windows 不支持 chmod，但文件系统会自动处理权限
    if not IS_WINDOWS:
        try:
            os.chmod(public_key_path, 0o644)
        except Exception as e:
            print(f"警告: 无法设置公钥文件权限: {e}")
    
    return private_key_path, public_key_path


def main():
    parser = argparse.ArgumentParser(
        description='生成 RSA 密钥对用于 JWT RS256 算法（兼容 Windows 和 Linux/Ubuntu）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # Windows - 使用默认设置（输出到 keys/ 目录，2048位）
  python scripts/generate_rsa_keys.py
  
  # Windows - 指定输出目录
  python scripts/generate_rsa_keys.py --output-dir keys
  python scripts/generate_rsa_keys.py --output-dir E:\\data\\Platform\\keys
  
  # Linux/Ubuntu - 使用默认设置
  python3 scripts/generate_rsa_keys.py
  
  # Linux/Ubuntu - 指定输出目录
  python3 scripts/generate_rsa_keys.py --output-dir /data/Platform/keys
  python3 scripts/generate_rsa_keys.py --output-dir keys
  
  # 生成 4096 位密钥（更安全但更慢）
  python scripts/generate_rsa_keys.py --key-size 4096
        """
    )
    
    parser.add_argument(
        '--output-dir',
        type=str,
        default='keys',
        help='输出目录（默认: keys/）'
    )
    
    parser.add_argument(
        '--key-size',
        type=int,
        default=2048,
        choices=[1024, 2048, 3072, 4096],
        help='密钥大小，单位：位（默认: 2048，可选: 1024, 2048, 3072, 4096）'
    )
    
    args = parser.parse_args()
    
    # 转换为 Path 对象（自动处理 Windows 和 Linux 路径）
    # 如果路径是相对路径，则相对于当前工作目录
    output_dir = Path(args.output_dir)
    
    # 如果路径是相对路径，尝试相对于项目根目录
    if not output_dir.is_absolute():
        # 尝试获取脚本所在目录的父目录（项目根目录）
        script_dir = Path(__file__).parent
        project_root = script_dir.parent
        # 如果当前工作目录是项目根目录，使用相对路径
        # 否则使用绝对路径
        if Path.cwd() == project_root:
            output_dir = project_root / args.output_dir
        else:
            output_dir = Path.cwd() / args.output_dir
    
    print("=" * 60)
    print("RSA 密钥对生成工具")
    print("=" * 60)
    print(f"操作系统: {platform.system()} {platform.release()}")
    print(f"密钥大小: {args.key_size} 位")
    print(f"输出目录: {output_dir.absolute()}")
    print()
    
    try:
        print("正在生成 RSA 密钥对...")
        private_key, public_key = generate_rsa_keypair(args.key_size)
        print("✓ 密钥对生成成功")
        
        print(f"\n正在保存密钥到 {output_dir.absolute()}...")
        private_key_path, public_key_path = save_keys(private_key, public_key, output_dir)
        print(f"✓ 私钥已保存: {private_key_path}")
        print(f"✓ 公钥已保存: {public_key_path}")
        
        print("\n" + "=" * 60)
        print("配置说明")
        print("=" * 60)
        print("\n在 .env 文件中添加以下配置：")
        print(f"\n# 方法1: 使用绝对路径（推荐）")
        # 在 Windows 上，使用正斜杠或反斜杠都可以，但为了跨平台兼容，使用正斜杠
        # Path.as_posix() 将路径转换为使用正斜杠的字符串
        private_path_str = private_key_path.absolute().as_posix()
        public_path_str = public_key_path.absolute().as_posix()
        print(f"RSA_PRIVATE_KEY_PATH={private_path_str}")
        print(f"RSA_PUBLIC_KEY_PATH={public_path_str}")
        
        # 如果使用相对路径，也提供相对路径选项
        try:
            # 尝试获取项目根目录
            script_dir = Path(__file__).parent
            project_root = script_dir.parent
            env_file = project_root / ".env"
            
            if env_file.exists():
                # 计算相对路径
                try:
                    private_relative = private_key_path.relative_to(project_root)
                    public_relative = public_key_path.relative_to(project_root)
                    print(f"\n# 方法2: 使用相对路径（相对于项目根目录）")
                    print(f"RSA_PRIVATE_KEY_PATH={private_relative.as_posix()}")
                    print(f"RSA_PUBLIC_KEY_PATH={public_relative.as_posix()}")
                except ValueError:
                    # 如果无法计算相对路径（不在同一驱动器等），跳过
                    pass
        except Exception:
            pass
        
        print(f"\n# 方法3: 使用环境变量（适合容器部署）")
        print("# 注意：私钥内容需要包含换行符，可以使用 \\n 或直接多行输入")
        print("# RSA_PRIVATE_KEY=\"\"\"")
        print("# <私钥内容>")
        print("# \"\"\"")
        print("# RSA_PUBLIC_KEY=\"\"\"")
        print("# <公钥内容>")
        print("# \"\"\"")
        
        print("\n" + "=" * 60)
        print("安全提示")
        print("=" * 60)
        print("⚠ 私钥文件包含敏感信息，请妥善保管！")
        print("⚠ 不要将私钥文件提交到版本控制系统（Git）")
        if not IS_WINDOWS:
            print("⚠ 已自动设置文件权限：私钥 600（仅所有者可读），公钥 644（所有人可读）")
        else:
            print("⚠ Windows 系统：请确保私钥文件仅对授权用户可见")
        print("⚠ 生产环境建议使用 2048 位或更大的密钥")
        
        if args.key_size < 2048:
            print(f"\n⚠ 警告: {args.key_size} 位密钥可能不够安全，建议使用 2048 位或更大")
        
        # 检查是否在 Git 仓库中，如果是，提醒添加到 .gitignore
        try:
            script_dir = Path(__file__).parent
            project_root = script_dir.parent
            gitignore_file = project_root / ".gitignore"
            
            if gitignore_file.exists():
                gitignore_content = gitignore_file.read_text(encoding='utf-8')
                if "keys/" not in gitignore_content and "private_key.pem" not in gitignore_content:
                    print(f"\n💡 提示: 建议在 .gitignore 中添加以下内容以忽略密钥文件：")
                    print("   keys/")
                    print("   *.pem")
                    print("   private_key.pem")
                    print("   public_key.pem")
        except Exception:
            pass
        
        print("\n✓ 完成！")
        
    except Exception as e:
        print(f"\n✗ 错误: 生成密钥对时出错: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()