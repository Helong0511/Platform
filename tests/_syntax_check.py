"""
对 app/api_v1 与 app/schemas 做 ast.parse 语法检查，输出 SyntaxError 文件列表。

注释批处理后的回归脚本，不修改业务代码。
"""
import ast
from pathlib import Path

bad = []
for d in [Path("app/api_v1"), Path("app/schemas")]:
    for p in sorted(d.rglob("*.py")):
        try:
            ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError as e:
            bad.append((str(p), e.lineno, e.msg))
print(len(bad))
for b in bad:
    print(b)
