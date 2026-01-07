"""
将Markdown文档转换为PDF
需要安装: pip install markdown weasyprint
"""
import os
import sys
from pathlib import Path

try:
    import markdown
    from weasyprint import HTML, CSS
except ImportError:
    print("请先安装依赖: pip install markdown weasyprint")
    sys.exit(1)


def markdown_to_pdf(markdown_file: str, output_pdf: str):
    """
    将Markdown文件转换为PDF
    
    Args:
        markdown_file: Markdown文件路径
        output_pdf: 输出PDF文件路径
    """
    # 读取Markdown文件
    with open(markdown_file, 'r', encoding='utf-8') as f:
        md_content = f.read()
    
    # 将Markdown转换为HTML
    html_content = markdown.markdown(
        md_content,
        extensions=['extra', 'codehilite', 'tables', 'toc']
    )
    
    # 添加CSS样式
    html_with_style = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            @page {{
                size: A4;
                margin: 2cm;
                @top-center {{
                    content: "CPL系统扣量和扣金额原理与操作说明";
                    font-size: 10pt;
                    color: #666;
                }}
                @bottom-center {{
                    content: "第 " counter(page) " 页 / 共 " counter(pages) " 页";
                    font-size: 10pt;
                    color: #666;
                }}
            }}
            body {{
                font-family: "Microsoft YaHei", "SimSun", Arial, sans-serif;
                font-size: 11pt;
                line-height: 1.6;
                color: #333;
            }}
            h1 {{
                font-size: 24pt;
                color: #2c3e50;
                border-bottom: 3px solid #3498db;
                padding-bottom: 10px;
                margin-top: 30px;
                margin-bottom: 20px;
                page-break-after: avoid;
            }}
            h2 {{
                font-size: 18pt;
                color: #34495e;
                border-bottom: 2px solid #95a5a6;
                padding-bottom: 8px;
                margin-top: 25px;
                margin-bottom: 15px;
                page-break-after: avoid;
            }}
            h3 {{
                font-size: 14pt;
                color: #555;
                margin-top: 20px;
                margin-bottom: 10px;
                page-break-after: avoid;
            }}
            h4 {{
                font-size: 12pt;
                color: #666;
                margin-top: 15px;
                margin-bottom: 8px;
                page-break-after: avoid;
            }}
            p {{
                margin-bottom: 10px;
                text-align: justify;
            }}
            code {{
                background-color: #f4f4f4;
                padding: 2px 6px;
                border-radius: 3px;
                font-family: "Consolas", "Monaco", monospace;
                font-size: 10pt;
            }}
            pre {{
                background-color: #f8f8f8;
                border: 1px solid #ddd;
                border-radius: 5px;
                padding: 15px;
                overflow-x: auto;
                page-break-inside: avoid;
            }}
            pre code {{
                background-color: transparent;
                padding: 0;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                margin: 15px 0;
                page-break-inside: avoid;
            }}
            th, td {{
                border: 1px solid #ddd;
                padding: 8px;
                text-align: left;
            }}
            th {{
                background-color: #3498db;
                color: white;
                font-weight: bold;
            }}
            tr:nth-child(even) {{
                background-color: #f9f9f9;
            }}
            ul, ol {{
                margin-left: 20px;
                margin-bottom: 10px;
            }}
            li {{
                margin-bottom: 5px;
            }}
            blockquote {{
                border-left: 4px solid #3498db;
                padding-left: 15px;
                margin: 15px 0;
                color: #666;
                font-style: italic;
            }}
            .toc {{
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 5px;
                padding: 15px;
                margin: 20px 0;
                page-break-inside: avoid;
            }}
            .toc ul {{
                list-style-type: none;
                margin-left: 0;
            }}
            .toc li {{
                margin-bottom: 5px;
            }}
            .toc a {{
                color: #3498db;
                text-decoration: none;
            }}
            hr {{
                border: none;
                border-top: 2px solid #eee;
                margin: 30px 0;
            }}
            strong {{
                color: #2c3e50;
                font-weight: bold;
            }}
        </style>
    </head>
    <body>
        {html_content}
    </body>
    </html>
    """
    
    # 转换为PDF
    HTML(string=html_with_style).write_pdf(output_pdf)
    print(f"PDF已生成: {output_pdf}")


if __name__ == "__main__":
    # 获取项目根目录
    project_root = Path(__file__).parent.parent
    
    # Markdown文件路径
    md_file = project_root / "docs" / "cpl_deduction_guide.md"
    
    # PDF输出路径
    pdf_file = project_root / "docs" / "CPL系统扣量和扣金额原理与操作说明.pdf"
    
    if not md_file.exists():
        print(f"错误: Markdown文件不存在: {md_file}")
        sys.exit(1)
    
    try:
        markdown_to_pdf(str(md_file), str(pdf_file))
        print(f"\n✅ 成功生成PDF文档!")
        print(f"📄 文件位置: {pdf_file}")
    except Exception as e:
        print(f"❌ 生成PDF失败: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

