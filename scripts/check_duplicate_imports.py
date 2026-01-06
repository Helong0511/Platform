"""
检查代码中的重复导入
"""
import os
import re
from collections import defaultdict
from pathlib import Path

def check_duplicate_imports(file_path):
    """检查单个文件的重复导入"""
    issues = []
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception as e:
        return [f"无法读取文件: {e}"]
    
    # 收集所有导入语句
    imports = defaultdict(list)  # {module: [line_numbers]}
    
    for i, line in enumerate(lines, 1):
        line = line.strip()
        
        # 匹配 from ... import ... 语句
        from_match = re.match(r'^from\s+([^\s]+)\s+import\s+(.+)$', line)
        if from_match:
            module = from_match.group(1)
            items = from_match.group(2)
            # 处理多行导入（如果有反斜杠或括号）
            if '\\' in items or '(' in items:
                # 多行导入，需要继续读取
                continue
            imports[module].append((i, items))
        
        # 匹配 import ... 语句
        import_match = re.match(r'^import\s+([^\s]+)(?:\s+as\s+\w+)?$', line)
        if import_match:
            module = import_match.group(1)
            imports[module].append((i, None))
    
    # 检查重复
    for module, occurrences in imports.items():
        if len(occurrences) > 1:
            line_nums = [str(occ[0]) for occ in occurrences]
            issues.append(f"  第 {', '.join(line_nums)} 行: 重复导入 '{module}'")
    
    return issues

def check_all_files(directory, extensions=('.py',)):
    """检查目录下所有文件的重复导入"""
    all_issues = {}
    
    for root, dirs, files in os.walk(directory):
        # 跳过一些目录
        dirs[:] = [d for d in dirs if d not in ['__pycache__', '.git', 'node_modules', 'venv', 'env']]
        
        for file in files:
            if file.endswith(extensions):
                file_path = os.path.join(root, file)
                issues = check_duplicate_imports(file_path)
                if issues:
                    all_issues[file_path] = issues
    
    return all_issues

if __name__ == '__main__':
    # 检查端点文件
    endpoints_dir = 'app/api/api_v1/endpoints'
    services_dir = 'app/services'
    
    print("=" * 80)
    print("检查端点文件中的重复导入...")
    print("=" * 80)
    
    endpoint_issues = check_all_files(endpoints_dir)
    if endpoint_issues:
        for file_path, issues in endpoint_issues.items():
            print(f"\n{file_path}:")
            for issue in issues:
                print(issue)
    else:
        print("✓ 端点文件未发现重复导入")
    
    print("\n" + "=" * 80)
    print("检查服务层文件中的重复导入...")
    print("=" * 80)
    
    service_issues = check_all_files(services_dir)
    if service_issues:
        for file_path, issues in service_issues.items():
            print(f"\n{file_path}:")
            for issue in issues:
                print(issue)
    else:
        print("✓ 服务层文件未发现重复导入")
    
    print("\n" + "=" * 80)
    total_issues = len(endpoint_issues) + len(service_issues)
    if total_issues > 0:
        print(f"发现 {total_issues} 个文件存在重复导入问题")
    else:
        print("✓ 所有文件检查通过，未发现重复导入")

