"""
将Markdown文档转换为PDF
使用方法: python scripts/md_to_pdf.py
"""
import sys
from pathlib import Path

# 检查依赖
try:
    import markdown
    from markdown.extensions import codehilite, tables, toc
except ImportError:
    print("请安装markdown库: pip install markdown")
    sys.exit(1)

try:
    from weasyprint import HTML, CSS
except ImportError:
    print("请安装weasyprint库: pip install weasyprint")
    print("注意: weasyprint需要系统依赖，Windows用户可能需要额外安装GTK+")
    sys.exit(1)


def markdown_to_html(md_content: str) -> str:
    """将Markdown转换为HTML"""
    md = markdown.Markdown(extensions=['extra', 'codehilite', 'tables', 'toc'])
    html = md.convert(md_content)
    return html


def html_to_pdf(html_content: str, output_pdf: str):
    """将HTML转换为PDF"""
    # CSS样式
    css = CSS(string='''
        @page {
            size: A4;
            margin: 2cm;
            @top-center {
                content: "CPL系统扣量和扣金额原理与操作说明";
                font-size: 10pt;
                color: #666;
            }
            @bottom-center {
                content: "第 " counter(page) " 页 / 共 " counter(pages) " 页";
                font-size: 10pt;
                color: #666;
            }
        }
        body {
            font-family: "Microsoft YaHei", "SimSun", Arial, sans-serif;
            font-size: 11pt;
            line-height: 1.6;
            color: #333;
            max-width: 100%;
        }
        h1 {
            font-size: 24pt;
            color: #2c3e50;
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
            margin-top: 30px;
            margin-bottom: 20px;
            page-break-after: avoid;
        }
        h2 {
            font-size: 18pt;
            color: #34495e;
            border-bottom: 2px solid #95a5a6;
            padding-bottom: 8px;
            margin-top: 25px;
            margin-bottom: 15px;
            page-break-after: avoid;
        }
        h3 {
            font-size: 14pt;
            color: #555;
            margin-top: 20px;
            margin-bottom: 10px;
            page-break-after: avoid;
        }
        h4 {
            font-size: 12pt;
            color: #666;
            margin-top: 15px;
            margin-bottom: 8px;
        }
        p {
            margin-bottom: 10px;
            text-align: justify;
        }
        code {
            background-color: #f4f4f4;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: "Consolas", "Monaco", monospace;
            font-size: 10pt;
        }
        pre {
            background-color: #f8f8f8;
            border: 1px solid #ddd;
            border-radius: 5px;
            padding: 15px;
            overflow-x: auto;
            page-break-inside: avoid;
        }
        pre code {
            background-color: transparent;
            padding: 0;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin: 15px 0;
            page-break-inside: avoid;
        }
        th, td {
            border: 1px solid #ddd;
            padding: 8px;
            text-align: left;
        }
        th {
            background-color: #3498db;
            color: white;
            font-weight: bold;
        }
        tr:nth-child(even) {
            background-color: #f9f9f9;
        }
        ul, ol {
            margin-left: 20px;
            margin-bottom: 10px;
        }
        li {
            margin-bottom: 5px;
        }
        blockquote {
            border-left: 4px solid #3498db;
            padding-left: 15px;
            margin: 15px 0;
            color: #666;
            font-style: italic;
        }
        .toc {
            background-color: #f8f9fa;
            border: 1px solid #dee2e6;
            border-radius: 5px;
            padding: 15px;
            margin: 20px 0;
        }
    ''')
    
    # 包装HTML
    full_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>CPL系统扣量和扣金额原理与操作说明</title>
    </head>
    <body>
        {html_content}
    </body>
    </html>
    """
    
    # 生成PDF
    HTML(string=full_html).write_pdf(output_pdf, stylesheets=[css])


def main():
    """主函数"""
    project_root = Path(__file__).parent.parent
    md_file = project_root / "docs" / "cpl_deduction_guide.md"
    pdf_file = project_root / "docs" / "CPL系统扣量和扣金额原理与操作说明.pdf"
    
    if not md_file.exists():
        print(f"错误: Markdown文件不存在: {md_file}")
        sys.exit(1)
    
    print(f"正在读取Markdown文件: {md_file}")
    with open(md_file, 'r', encoding='utf-8') as f:
        md_content = f.read()
    
    print("正在转换为HTML...")
    html_content = markdown_to_html(md_content)
    
    print(f"正在生成PDF: {pdf_file}")
    try:
        html_to_pdf(html_content, str(pdf_file))
        print(f"\n✅ 成功生成PDF文档!")
        print(f"📄 文件位置: {pdf_file}")
        print(f"📊 文件大小: {pdf_file.stat().st_size / 1024:.2f} KB")
    except Exception as e:
        print(f"❌ 生成PDF失败: {str(e)}")
        print("\n提示:")
        print("1. 如果提示缺少GTK+，请安装: https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer")
        print("2. 或者使用其他PDF生成工具，如: pandoc")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

